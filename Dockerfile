# syntax=docker/dockerfile:1

# Imagem única do SIGMA: aplicação Django (Daphne/Channels) + PostgreSQL 18 com
# TimescaleDB + Nginx no mesmo container. Decisão do sênior (2026-09, ver
# docker/README.md): nada de docker-compose/múltiplos containers — o objetivo é
# simplicidade de instalação para qualquer pessoa do time subir rápido, e
# portabilidade para o cenário em que a infra só libera "um Docker numa VM",
# sem gestão de banco separada. TLS fica fora de escopo desta primeira versão:
# o Nginx escuta HTTP simples na porta 80 dentro do container (ver
# docker/nginx.conf e docker/README.md).
#
# Base Ubuntu 24.04 LTS: mesma versão documentada em
# docs/sigma/03-servidor-e-hospedagem.md para o servidor de produção real
# (paridade de pacote com o que já foi validado).
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    UV_LINK_MODE=copy \
    PATH="/root/.local/bin:${PATH}"

# --- PostgreSQL 18 + TimescaleDB (repositório oficial PGDG) ------------------
# postgresql-common traz o script que registra o repositório PGDG para a
# versão exata documentada em docs/sigma/03-servidor-e-hospedagem.md §3.4.3.1.
# `postgresql-18-timescaledb` é o pacote real, confirmado ao vivo no servidor
# de produção (`dpkg -l`, repositório `noble-pgdg`) — o PGDG já empacota a
# extensão junto, não precisa de repositório separado da Timescale (a
# primeira versão deste Dockerfile usava por engano o pacote
# `timescaledb-2-postgresql-18` do repositório próprio da Timescale, que
# existe mas não é o que produção roda).
# libpq-dev + pg_config são exigidos para compilar o pacote `psycopg2` (não
# binário) declarado no pyproject.toml; build-essential/gcc + libldap2-dev/
# libsasl2-dev compilam o `python-ldap` (sem wheel pronta para Linux).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg lsb-release wget \
        postgresql-common \
        build-essential gcc libpq-dev libldap2-dev libsasl2-dev libssl-dev \
        nginx supervisor \
    && /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-18 postgresql-18-timescaledb \
    && rm -rf /var/lib/apt/lists/*

# --- Node.js: só para compilar o Tailwind durante o build --------------------
# Não roda em tempo de execução; ver CLAUDE.md: "Depois de alterar token ou
# classe Tailwind: cd theme/static_src && npm run build".
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# --- uv: gerenciador de pacote Python do projeto -----------------------------
# Instala o Python >=3.14 exigido pelo pyproject.toml — o Python de sistema do
# Ubuntu 24.04 (3.12) não atende, por isso não se usa `apt install python3`.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /opt/SIGMA

# Camada de dependências isolada do restante do código para cache do build.
COPY pyproject.toml uv.lock ./
RUN uv python install 3.14 \
    && uv sync --frozen --no-dev

COPY . .

# Tailwind: gera theme/static/css/dist/styles.css — STATICFILES_DIRS
# (SIGMA/settings.py) já aponta para theme/static.
RUN cd theme/static_src \
    && npm ci \
    && npm run build

# collectstatic exige que SIGMA/settings.py importe sem erro, o que exige
# DJANGO_SECRET_KEY definido (settings.py levanta ImproperlyConfigured senão).
# O valor abaixo NÃO é segredo real: existe só para esta instrução RUN, nunca
# vira variável de ambiente da imagem (por isso não se usa `ENV` aqui) — o
# segredo de verdade continua vindo exclusivamente de fora, via
# `docker run --env-file`.
RUN DJANGO_SECRET_KEY=build-collectstatic-nao-e-segredo-real \
    uv run --frozen python manage.py collectstatic --noinput

# --- Usuário dedicado para o Daphne (não roda como root) --------------------
# Sistema sem home real nem shell de login: o Daphne processa requisição de
# rede externa direto (view, formulário, WebSocket), não deveria rodar com
# privilégio de root. entrypoint.sh e supervisord continuam root (precisam
# criar/ajustar o cluster do PostgreSQL, que é setup de sistema, não código
# exposto a entrada não confiável). Ver docker/supervisord.conf (`user=sigma`
# no programa daphne) e docker/wait-for-postgres.sh (não usa mais `su
# postgres`, só client-side `pg_isready`, que não exige privilégio nenhum).
RUN useradd --system --no-create-home --home-dir /opt/SIGMA --shell /usr/sbin/nologin sigma \
    && chown -R sigma:sigma /opt/SIGMA

# --- Nginx: config mínima e autocontida (substitui a padrão do pacote) ------
COPY docker/nginx.conf /etc/nginx/nginx.conf

# --- supervisord: mantém postgresql + daphne + nginx no mesmo container -----
# Os workers em background do SIGMA (envia_pendencias e afins) já rodam como
# threads dentro do próprio processo Daphne via accounts/apps.py
# (AppConfig.ready() / SIGMA/asgi.py), não precisam de processo à parte aqui.
COPY docker/supervisord.conf /etc/supervisor/supervisord.conf
COPY docker/wait-for-postgres.sh /usr/local/bin/wait-for-postgres.sh
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/wait-for-postgres.sh /usr/local/bin/entrypoint.sh \
    && mkdir -p /var/log/supervisor

# Diretório de dados do cluster PostgreSQL 18: precisa sobreviver à recriação
# do container. O `apt install postgresql-18` já criou um cluster inicial
# durante o build (nesta camada da imagem); um volume montado por fora fica
# vazio na primeira execução e sombreia esse cluster de build — é o
# entrypoint.sh que detecta isso (arquivo PG_VERSION ausente) e recria o
# cluster dentro do volume na primeira subida.
VOLUME ["/var/lib/postgresql"]

EXPOSE 80

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
