#!/bin/bash
# O supervisord inicia postgresql e daphne "ao mesmo tempo" (por prioridade,
# sem espera real). accounts/apps.py::iniciar_workers_em_background() tenta
# conectar no PostgreSQL assim que SIGMA/asgi.py é importado, sem retry — se o
# banco ainda não aceitar conexões nesse instante, os workers em background
# nunca sobem para aquele processo. Este wrapper espera o PostgreSQL responder
# antes de exec'ar o Daphne, fechando essa corrida.
set -euo pipefail

log() {
    echo "[wait-for-postgres] $*"
}

PGHOST="${DB_DEFAULT_HOST:-127.0.0.1}"
PGPORT="${DB_DEFAULT_PORT:-5432}"

ate=60
while ! pg_isready -q -h "${PGHOST}" -p "${PGPORT}"; do
    ate=$((ate - 1))
    if [ "${ate}" -le 0 ]; then
        log "PostgreSQL não respondeu a tempo; abortando."
        exit 1
    fi
    sleep 1
done

log "PostgreSQL pronto; iniciando o Daphne."
exec /opt/SIGMA/.venv/bin/daphne -b 127.0.0.1 -p 8000 SIGMA.asgi:application
