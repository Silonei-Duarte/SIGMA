import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

import psycopg2
from django.apps import AppConfig
from django.conf import settings
from django.db import close_old_connections, connections
from django.db.models.signals import post_migrate

_conexao_trava_workers = None
_CHAVE_TRAVA_WORKERS = 20260430
_supervisor_workers_iniciado = False
_monitor_conexoes_iniciado = False
logger = logging.getLogger(__name__)


def _coletar_fila_pgbouncer():
    if os.getenv("POSTGRES_USA_PGBOUNCER", "").strip().lower() not in {"1", "true", "sim", "yes"}:
        return None

    config_banco = settings.DATABASES["default"]
    conexao = None
    try:
        conexao = psycopg2.connect(
            dbname="pgbouncer",
            user=config_banco["USER"],
            password=config_banco["PASSWORD"],
            host=config_banco.get("HOST") or "127.0.0.1",
            port=config_banco.get("PORT") or "6432",
            application_name="sigma-monitor-pgbouncer",
            connect_timeout=2,
        )
        conexao.autocommit = True
        with conexao.cursor() as cursor:
            cursor.execute("SHOW DATABASES")
            colunas = [coluna.name for coluna in cursor.description]
            banco = next(
                (
                    dict(zip(colunas, linha, strict=False))
                    for linha in cursor.fetchall()
                    if linha[colunas.index("name")] == config_banco["NAME"]
                ),
                None,
            )
            cursor.execute("SHOW POOLS")
            colunas = [coluna.name for coluna in cursor.description]
            pool = next(
                (
                    dict(zip(colunas, linha, strict=False))
                    for linha in cursor.fetchall()
                    if linha[colunas.index("database")] == config_banco["NAME"]
                ),
                None,
            )
    except Exception:
        return None
    finally:
        if conexao is not None:
            conexao.close()

    if not banco or not pool:
        return None

    return {
        "esperando": pool["cl_waiting"],
        "maxwait": pool["maxwait"],
        "clientes_ativos": pool["cl_active"],
        "servidores_ativos": pool["sv_active"],
        "conexoes_reais": banco["current_connections"],
        "limite_conexoes_reais": banco["max_connections"],
    }


def _monitorar_conexoes_postgres():
    """Registra um snapshot somente ao cruzar o limite de alerta."""
    intervalo = int(os.getenv("POSTGRES_MONITOR_INTERVALO_SEGUNDOS", "5"))
    limite = int(os.getenv("POSTGRES_MONITOR_LIMITE_CONEXOES", "100"))
    rearmar_abaixo = int(os.getenv("POSTGRES_MONITOR_REARMAR_ABAIXO", "70"))
    em_alerta = False
    fila_pgbouncer_em_alerta = False

    while True:
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('application_name', 'sigma-monitor-conexoes', false)"
                )
                cursor.execute(
                    """
                    SELECT
                        current_setting('max_connections')::int,
                        count(*) FILTER (WHERE backend_type = 'client backend'),
                        json_agg(
                            json_build_object(
                                'pid', pid,
                                'usuario', usename,
                                'banco', datname,
                                'aplicacao', application_name,
                                'origem', coalesce(client_addr::text, 'local'),
                                'estado', state,
                                'inicio', backend_start,
                                'mudanca_estado', state_change,
                                'query', left(query, 300)
                            )
                            ORDER BY backend_start
                        ) FILTER (WHERE backend_type = 'client backend')
                    FROM pg_stat_activity
                    """
                )
                maximo, total, sessoes = cursor.fetchone()

            fila_pgbouncer = _coletar_fila_pgbouncer()

            if total >= limite and not em_alerta:
                logger.error(
                    "[POSTGRES_CONEXOES_ALTA] %s",
                    json.dumps(
                        {
                            "total_clientes": total,
                            "max_connections": maximo,
                            "limite_alerta": limite,
                            "sessoes": sessoes or [],
                        },
                        default=str,
                        ensure_ascii=False,
                    ),
                )
                em_alerta = True
            elif em_alerta and total <= rearmar_abaixo:
                logger.warning(
                    "[POSTGRES_CONEXOES_NORMALIZADO] total_clientes=%s limite_rearme=%s",
                    total,
                    rearmar_abaixo,
                )
                em_alerta = False

            if fila_pgbouncer and fila_pgbouncer["esperando"] > 0 and not fila_pgbouncer_em_alerta:
                logger.error(
                    "[PGBOUNCER_FILA] %s",
                    json.dumps(fila_pgbouncer, ensure_ascii=False),
                )
                fila_pgbouncer_em_alerta = True
            elif fila_pgbouncer_em_alerta and (
                not fila_pgbouncer or fila_pgbouncer["esperando"] == 0
            ):
                logger.warning("[PGBOUNCER_FILA_NORMALIZADA]")
                fila_pgbouncer_em_alerta = False
        except Exception:
            logger.exception("[POSTGRES_CONEXOES_MONITOR] Falha ao coletar snapshot")
        finally:
            connections.close_all()
        time.sleep(max(intervalo, 1))


def _eh_comando_gerenciamento_django():
    script_name = Path(sys.argv[0]).name.lower() if sys.argv else ""
    return script_name in {"manage.py", "django-admin", "django-admin.exe"}


def _deve_iniciar_workers_em_background():
    # Em comandos do Django, os workers só devem subir no runserver.
    if _eh_comando_gerenciamento_django():
        command = sys.argv[1].lower() if len(sys.argv) > 1 else ""
        if command != "runserver":
            return False
        # O autoreload cria um processo pai e outro filho; só o filho deve iniciar.
        if command == "runserver" and os.environ.get("RUN_MAIN") != "true":
            return False

    return True


def _tentar_adquirir_trava_workers():
    global _conexao_trava_workers

    if _conexao_trava_workers is not None:
        return True

    config_banco = settings.DATABASES["default"]
    if config_banco.get("ENGINE") != "django.db.backends.postgresql":
        return False

    try:
        # A conexao fica aberta para manter a trava ativa durante a vida do processo.
        conexao = psycopg2.connect(
            dbname=config_banco["NAME"],
            user=config_banco["USER"],
            password=config_banco["PASSWORD"],
            # A advisory lock é de sessão. Com PgBouncer em pool por transação,
            # ela precisa continuar diretamente no PostgreSQL.
            host=os.getenv("POSTGRES_DIRECT_HOST", config_banco.get("HOST") or ""),
            port=os.getenv("POSTGRES_DIRECT_PORT", config_banco.get("PORT") or ""),
            application_name="sigma-worker-lock",
        )
        conexao.autocommit = True

        with conexao.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [_CHAVE_TRAVA_WORKERS])
            trava_adquirida = cursor.fetchone()[0]
    except Exception:
        return False

    if not trava_adquirida:
        conexao.close()
        return False

    _conexao_trava_workers = conexao
    return True


def _iniciar_ou_reiniciar_workers():
    from producao.services.consolida_tempos_erp import start_consolida_tempos_erp_scheduler
    from producao.services.envia_pendencias import start_envia_pendencias_scheduler
    from producao.services.importa_palete import start_importa_palete_scheduler
    from producao.services.sincroniza_ops_encerradas import (
        start_sincroniza_ops_encerradas_scheduler,
    )
    from telemetria.services.coleta import start_coleta_telemetria

    from .services.oee_planejado_service import start_oee_planejado_scheduler

    start_oee_planejado_scheduler()
    start_importa_palete_scheduler()
    start_sincroniza_ops_encerradas_scheduler()
    start_consolida_tempos_erp_scheduler()
    start_envia_pendencias_scheduler()
    start_coleta_telemetria()


def _monitorar_timeouts_workers():
    from producao.services.envia_pendencias import SERVICES_MONITORADOS_TIMEOUT
    from producao.services.status import matar_services_travados

    interrompidos = matar_services_travados(SERVICES_MONITORADOS_TIMEOUT)
    if interrompidos:
        print(f"[WORKERS] Services interrompidos por timeout: {', '.join(interrompidos)}")


def _supervisionar_workers():
    while True:
        close_old_connections()
        try:
            _iniciar_ou_reiniciar_workers()
            _monitorar_timeouts_workers()
        except Exception as exc:
            print(f"[WORKERS] Falha ao supervisionar workers: {exc}")
        finally:
            connections.close_all()
        time.sleep(30)


def _iniciar_monitor_conexoes():
    global _monitor_conexoes_iniciado
    if _monitor_conexoes_iniciado:
        return
    _monitor_conexoes_iniciado = True
    threading.Thread(
        target=_monitorar_conexoes_postgres,
        name="MonitorConexoesPostgres",
        daemon=True,
    ).start()


def iniciar_workers_em_background():
    """Inicia os workers depois que o Django concluiu a carga das apps."""
    global _supervisor_workers_iniciado
    if not _deve_iniciar_workers_em_background():
        return

    if not _tentar_adquirir_trava_workers():
        return

    if _supervisor_workers_iniciado:
        return

    _supervisor_workers_iniciado = True
    time.sleep(2)
    close_old_connections()
    try:
        _iniciar_ou_reiniciar_workers()
    finally:
        connections.close_all()
    threading.Thread(
        target=_supervisionar_workers,
        name="SupervisorWorkersSigma",
        daemon=True,
    ).start()
    _iniciar_monitor_conexoes()


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        # Não consultar o banco aqui: o Django ainda está inicializando as apps.
        # A permissão de cadastros nasce pós-migrate (o signal nativo
        # create_permissions é desconectado em manage.py) e o decorator das
        # rotas privadas confia nela. Import local: evita ciclo no startup.

        # O service de configurações conecta no import os signals que
        # mantêm o cache de `obter()` fresco (post_save/post_delete).
        # Registrá-lo no ready garante que qualquer processo Django
        # (web, workers, manage.py) invalide o cache quando o dado muda.
        from accounts.services import configuracoes  # noqa: F401

        def _criar_permissoes_accounts(sender, **kwargs):
            from django.db.utils import IntegrityError

            from accounts.models.permissoes import (
                criar_permissao_administrar_acessos,
                criar_permissao_configurar_aplicacao,
                criar_permissao_manipular_cadastros,
            )

            for criar in (
                criar_permissao_manipular_cadastros,
                criar_permissao_administrar_acessos,
                criar_permissao_configurar_aplicacao,
            ):
                try:
                    criar()
                except IntegrityError:
                    # Bancos provisionados antes deste gancho já têm a permissão;
                    # outro ciclo/sinal pode tê-la criado em paralelo. Em ambos os
                    # casos a linha válida já existe e nada deve ser alterado.
                    logger.info("Permissão de accounts já presente; reuso.")

        post_migrate.connect(
            _criar_permissoes_accounts,
            dispatch_uid="accounts.criar_permissoes_accounts",
        )
