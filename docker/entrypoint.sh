#!/bin/bash
# Ponto de entrada do container único do SIGMA.
#
# Responsabilidade deste script: preparar o cluster PostgreSQL (criando-o na
# primeira execução, ou reaproveitando o que já está no volume), garantir
# usuário/banco/extensão TimescaleDB, rodar as migrations do Django e então
# entregar o processo principal ao supervisord (postgresql + daphne + nginx).
#
# Depois do handoff este script não continua rodando — quem mantém os três
# processos vivos é o supervisord (docker/supervisord.conf).
set -euo pipefail

PG_MAJOR="18"
PG_CLUSTER="main"
DATA_DIR="/var/lib/postgresql/${PG_MAJOR}/${PG_CLUSTER}"

log() {
    echo "[entrypoint] $*"
}

: "${DB_DEFAULT_NAME:?Defina DB_DEFAULT_NAME no --env-file}"
: "${DB_DEFAULT_USER:?Defina DB_DEFAULT_USER no --env-file}"
: "${DB_DEFAULT_PASSWORD:?Defina DB_DEFAULT_PASSWORD no --env-file}"
: "${DJANGO_SECRET_KEY:?Defina DJANGO_SECRET_KEY no --env-file}"

# O volume nomeado (docker run -v ...:/var/lib/postgresql) cobre todo o
# diretório de dados do PostgreSQL. Quando o Docker cria o volume do zero, ele
# nasce de propriedade de root; o cluster recusa iniciar se o dono não for
# "postgres".
mkdir -p "/var/lib/postgresql/${PG_MAJOR}"
chown -R postgres:postgres /var/lib/postgresql

if [ ! -f "${DATA_DIR}/PG_VERSION" ]; then
    log "Cluster PostgreSQL ausente em ${DATA_DIR} (volume novo ou vazio); criando."
    # pg_dropcluster limpa o registro de config em /etc/postgresql que ficou
    # do cluster criado durante o `apt install` no build — esse cluster de
    # build usa os MESMOS caminhos e fica sombreado pelo volume vazio montado
    # em runtime, então seu registro precisa ser refeito apontando para os
    # dados novos que pg_createcluster vai inicializar dentro do volume.
    pg_dropcluster --stop "${PG_MAJOR}" "${PG_CLUSTER}" 2>/dev/null || true
    pg_createcluster "${PG_MAJOR}" "${PG_CLUSTER}"
    PRIMEIRA_EXECUCAO=1
else
    log "Cluster PostgreSQL existente em ${DATA_DIR}; reaproveitando sem recriar."
    PRIMEIRA_EXECUCAO=0
fi

log "Subindo PostgreSQL temporariamente para preparar banco e rodar migrations."
pg_ctlcluster "${PG_MAJOR}" "${PG_CLUSTER}" start

log "Garantindo usuário, banco e extensão TimescaleDB (idempotente a cada subida)."
# PostgreSQL exige apóstrofo duplicado dentro de literal de string ('') e
# aspas duplas duplicadas dentro de identificador (""). Sem isso, um
# DB_DEFAULT_USER/DB_DEFAULT_PASSWORD com apóstrofo ou aspas quebra o SQL
# interpolado abaixo (na melhor hipótese, erro de sintaxe; na pior, o
# restante do valor é interpretado como SQL). Escapado uma vez aqui, para
# os dois usos (literal e identificador) do heredoc.
DB_USER_LITERAL="${DB_DEFAULT_USER//\'/\'\'}"
DB_USER_IDENT="${DB_DEFAULT_USER//\"/\"\"}"
DB_PASSWORD_LITERAL="${DB_DEFAULT_PASSWORD//\'/\'\'}"
su postgres -c "psql -v ON_ERROR_STOP=1" <<-SQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER_LITERAL}') THEN
            CREATE ROLE "${DB_USER_IDENT}" LOGIN PASSWORD '${DB_PASSWORD_LITERAL}';
        ELSE
            ALTER ROLE "${DB_USER_IDENT}" WITH PASSWORD '${DB_PASSWORD_LITERAL}';
        END IF;
    END
    \$\$;
SQL

DB_NAME_LITERAL="${DB_DEFAULT_NAME//\'/\'\'}"
DB_NAME_IDENT="${DB_DEFAULT_NAME//\"/\"\"}"
if ! su postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname = '${DB_NAME_LITERAL}'\"" | grep -q 1; then
    log "Banco ${DB_DEFAULT_NAME} não existe; criando."
    su postgres -c "createdb -O \"${DB_USER_IDENT}\" \"${DB_NAME_IDENT}\""
fi

su postgres -c "psql -v ON_ERROR_STOP=1 -d \"${DB_DEFAULT_NAME}\" -c 'CREATE EXTENSION IF NOT EXISTS timescaledb;'"

log "Rodando manage.py migrate (idempotente a cada subida)."
cd /opt/SIGMA
uv run --frozen python manage.py migrate --noinput

if ! uv run --frozen python manage.py shell -c "
from django.contrib.auth import get_user_model
import sys
sys.exit(0 if get_user_model().objects.filter(is_superuser=True).exists() else 1)
" 2>/dev/null; then
    if [ -t 0 ]; then
        log "Nenhum superusuário existe ainda. Criando agora (Ctrl+C pula esta etapa)."
        uv run --frozen python manage.py createsuperuser || log "Criação de superusuário pulada ou cancelada."
    else
        log "Nenhum superusuário existe ainda. Container sem terminal interativo (rodando com -d)" \
            "não pode perguntar aqui — crie depois com:" \
            "docker exec -it <container> uv run --frozen python manage.py createsuperuser"
    fi
fi

log "Parando o PostgreSQL de preparação; o supervisord assume o processo definitivo."
pg_ctlcluster "${PG_MAJOR}" "${PG_CLUSTER}" stop

log "Handoff para o supervisord (postgresql + daphne + nginx). PRIMEIRA_EXECUCAO=${PRIMEIRA_EXECUCAO}"
exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
