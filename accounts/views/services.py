import ctypes
import os
import platform
import shutil
import socket
import ssl
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import connections
from django.db.models import Q
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from producao.models import (
    Apontamento,
    ApontamentoComponente,
    BaixaComponente,
    PacoteTempoERP,
)
from producao.services.envia_tempos_erp import (
    WEBSERVICE_TIMEOUT_SEGUNDOS as TIMEOUT_TEMPOS_ERP_SEGUNDOS,
)
from producao.services.status import listar_status_services
from producao.views.logs_apontamento_componentes import (
    WEBSERVICE_TIMEOUT_SEGUNDOS as TIMEOUT_COMPONENTES_SEGUNDOS,
)
from producao.views.logs_apontamentos import WEBSERVICE_TIMEOUT_SEGUNDOS as TIMEOUT_LOGS_SEGUNDOS
from producao.views.logs_baixa_componentes import (
    WEBSERVICE_TIMEOUT_SEGUNDOS as TIMEOUT_BAIXAS_COMPONENTES_SEGUNDOS,
)
from setores.qualidade.models import LiberacaoLote
from setores.qualidade.models.estrutura import WMS_IntegraçãoOP
from setores.qualidade.views.consulta_lote import (
    WEBSERVICE_TIMEOUT_SEGUNDOS as TIMEOUT_LOTES_SEGUNDOS,
)
from setores.qualidade.views.wms_views import (
    WEBSERVICE_TIMEOUT_SEGUNDOS as TIMEOUT_WMS_SEGUNDOS,
)
from setores.qualidade.views.wms_views import (
    integracoes_wms_enviaveis,
)


def _status_certificado_https():
    """Consulta o certificado que o endereço público do portal apresenta."""
    portal_url = urlparse(settings.PORTAL_BASE_URL)
    if portal_url.scheme != "https" or not portal_url.hostname:
        return {
            "habilitado": False,
            "disponivel": False,
            "mensagem": "HTTPS não configurado nesta instância.",
        }

    try:
        contexto = ssl.create_default_context()
        with socket.create_connection((portal_url.hostname, 443), timeout=3) as conexao:
            with contexto.wrap_socket(conexao, server_hostname=portal_url.hostname) as conexao_tls:
                certificado = conexao_tls.getpeercert()

        expira_em = datetime.strptime(
            certificado["notAfter"],
            "%b %d %H:%M:%S %Y %Z",
        ).replace(tzinfo=UTC)
        expira_em = timezone.localtime(expira_em)
        segundos_restantes = (expira_em - timezone.now()).total_seconds()
        dias_restantes = max(0, int(segundos_restantes // 86400))
        return {
            "habilitado": True,
            "disponivel": True,
            "dominio": portal_url.hostname,
            "expira_em": expira_em,
            "dias_restantes": dias_restantes,
            "critico": segundos_restantes < 7 * 86400,
            "alerta": segundos_restantes < 30 * 86400,
        }
    except (KeyError, OSError, ssl.SSLError, ValueError) as exc:
        return {
            "habilitado": True,
            "disponivel": False,
            "dominio": portal_url.hostname,
            "mensagem": f"Não foi possível consultar o certificado: {exc}",
        }


def _formatar_segundos(valor):
    if valor is None:
        return "-"
    valor = max(float(valor), 0)
    if valor < 1:
        return f"{round(valor * 1000)} ms"
    segundos = int(valor)
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    if horas:
        return f"{horas}h {minutos:02d}min"
    if minutos:
        return f"{minutos}min {segundos:02d}s"
    return f"{segundos}s"


def _formatar_bytes(valor):
    if valor is None:
        return "-"
    valor = float(valor)
    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if valor < 1024 or unidade == "TB":
            return f"{valor:.1f} {unidade}" if unidade != "B" else f"{int(valor)} B"
        valor /= 1024
    return "-"


def _percentual(usado, total):
    if not total:
        return None
    return round((float(usado) / float(total)) * 100, 1)


def _descricao_estado_conexao(estado):
    return {
        "active": "Em uso",
        "idle": "Livre para reutilização",
        "idle in transaction": "Parada dentro de transação",
        "idle in transaction (aborted)": "Transação com erro aguardando fim",
    }.get(estado, estado or "-")


def _descricao_espera_conexao(espera):
    if espera in (None, "-"):
        return "Sem espera"
    if espera == "Client: ClientRead":
        return "Aguardando próximo comando"
    if espera.startswith("Lock:"):
        return "Aguardando liberação de lock"
    return espera


def _cpu_percent_windows(intervalo=1.0):
    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", ctypes.c_ulong),
            ("dwHighDateTime", ctypes.c_ulong),
        ]

    def _filetime_para_int(valor):
        return (valor.dwHighDateTime << 32) + valor.dwLowDateTime

    def _tempos_cpu():
        idle = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        ok = ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        if not ok:
            return None
        return _filetime_para_int(idle), _filetime_para_int(kernel), _filetime_para_int(user)

    inicio = _tempos_cpu()
    if not inicio:
        return None
    time.sleep(intervalo)
    fim = _tempos_cpu()
    if not fim:
        return None

    idle_delta = fim[0] - inicio[0]
    total_delta = (fim[1] - inicio[1]) + (fim[2] - inicio[2])
    if total_delta <= 0:
        return None
    return round((1 - (idle_delta / total_delta)) * 100, 1)


def _memoria_windows():
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    memoria = MEMORYSTATUSEX()
    memoria.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memoria))
    if not ok:
        return None
    usado = memoria.ullTotalPhys - memoria.ullAvailPhys
    return {
        "total": memoria.ullTotalPhys,
        "usado": usado,
        "livre": memoria.ullAvailPhys,
        "percentual": round(float(memoria.dwMemoryLoad), 1),
    }


def _status_servidor():
    raiz_disco = Path.cwd().anchor or os.getcwd()
    disco = shutil.disk_usage(raiz_disco)
    dados = {
        "hostname": socket.gethostname(),
        "sistema": f"{platform.system()} {platform.release()}",
        "cpu_percentual": None,
        "cpu_por_nucleo": [],
        "cpu_nucleos": os.cpu_count(),
        "memoria": None,
        "disco": {
            "path": raiz_disco,
            "total": disco.total,
            "usado": disco.used,
            "livre": disco.free,
            "percentual": _percentual(disco.used, disco.total),
        },
        "observacao": "",
    }

    try:
        import psutil
    except Exception:
        psutil = None

    if psutil:
        memoria = psutil.virtual_memory()
        cpu_por_nucleo = psutil.cpu_percent(interval=1.0, percpu=True)
        dados["cpu_por_nucleo"] = cpu_por_nucleo
        dados["cpu_percentual"] = (
            round(sum(cpu_por_nucleo) / len(cpu_por_nucleo), 1)
            if cpu_por_nucleo
            else psutil.cpu_percent(interval=None)
        )
        dados["cpu_nucleos"] = psutil.cpu_count(logical=True)
        dados["memoria"] = {
            "total": memoria.total,
            "usado": memoria.used,
            "livre": memoria.available,
            "percentual": memoria.percent,
        }
        return dados

    if platform.system().lower() == "windows":
        try:
            dados["cpu_percentual"] = _cpu_percent_windows()
            dados["memoria"] = _memoria_windows()
        except Exception as exc:
            dados["observacao"] = f"CPU/memória indisponíveis: {exc}"
    else:
        dados["observacao"] = "CPU/memória detalhadas exigem psutil neste sistema."

    return dados


def _formatar_status_servidor(status):
    memoria = status.get("memoria") or {}
    disco = status.get("disco") or {}
    cpu_por_nucleo = [
        {
            "numero": indice,
            "percentual": percentual,
            "percentual_formatado": f"{percentual:.1f}%",
        }
        for indice, percentual in enumerate(status.get("cpu_por_nucleo") or [], start=1)
    ]
    return {
        **status,
        "cpu_por_nucleo": cpu_por_nucleo,
        "cpu_percentual_formatado": (
            f"{status['cpu_percentual']:.1f}%" if status.get("cpu_percentual") is not None else "-"
        ),
        "memoria_total_formatada": _formatar_bytes(memoria.get("total")),
        "memoria_usada_formatada": _formatar_bytes(memoria.get("usado")),
        "memoria_livre_formatada": _formatar_bytes(memoria.get("livre")),
        "memoria_percentual_formatada": (
            f"{memoria['percentual']:.1f}%" if memoria.get("percentual") is not None else "-"
        ),
        "disco_total_formatado": _formatar_bytes(disco.get("total")),
        "disco_usado_formatado": _formatar_bytes(disco.get("usado")),
        "disco_livre_formatada": _formatar_bytes(disco.get("livre")),
        "disco_percentual_formatado": (
            f"{disco['percentual']:.1f}%" if disco.get("percentual") is not None else "-"
        ),
    }


def _status_conexoes_postgres():
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    current_setting('max_connections')::int,
                    current_setting('superuser_reserved_connections')::int,
                    count(*) FILTER (WHERE backend_type = 'client backend'),
                    count(*) FILTER (WHERE backend_type = 'client backend' AND state = 'active')
                FROM pg_stat_activity
                """
            )
            maximo, reservadas, total, ativas = cursor.fetchone()
            cursor.execute(
                """
                SELECT
                    pid,
                    usename,
                    datname,
                    nullif(application_name, '') AS application_name,
                    coalesce(client_addr::text, 'local') AS client_addr,
                    state AS state,
                    coalesce(nullif(wait_event_type, '') || ': ' || nullif(wait_event, ''), '-') AS wait_event,
                    backend_start,
                    state_change,
                    left(query, 500) AS query
                FROM pg_stat_activity
                WHERE backend_type = 'client backend'
                ORDER BY backend_start
                """
            )
            colunas = [coluna.name for coluna in cursor.description]
            sessoes = [dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()]
            for sessao in sessoes:
                sessao["estado_descricao"] = _descricao_estado_conexao(sessao["state"])
                sessao["espera_descricao"] = _descricao_espera_conexao(sessao["wait_event"])
    except Exception:
        return {"disponivel": False}

    capacidade_normal = max(maximo - reservadas, 0)
    return {
        "disponivel": True,
        "total": total,
        "ativas": ativas,
        "capacidade_normal": capacidade_normal,
        "percentual": _percentual(total, capacidade_normal),
        "sessoes": sessoes,
    }


def _status_pgbouncer():
    if os.getenv("POSTGRES_USA_PGBOUNCER", "").strip().lower() not in {"1", "true", "sim", "yes"}:
        return {"habilitado": False}

    config_banco = connections.databases["default"]
    conexao = None
    try:
        conexao = psycopg2.connect(
            dbname="pgbouncer",
            user=config_banco["USER"],
            password=config_banco["PASSWORD"],
            host=config_banco.get("HOST") or "127.0.0.1",
            port=config_banco.get("PORT") or "6432",
            application_name="sigma-status-pgbouncer",
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
            pools = [dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()]
            pool = next((item for item in pools if item["database"] == config_banco["NAME"]), None)
            cursor.execute("SHOW SERVERS")
            colunas = [coluna.name for coluna in cursor.description]
            servidores = [dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()]
    except Exception:
        return {"habilitado": True, "disponivel": False}
    finally:
        if conexao is not None:
            conexao.close()

    if not banco or not pool:
        return {"habilitado": True, "disponivel": False}

    limite = banco["max_connections"]
    usadas = banco["current_connections"]
    return {
        "habilitado": True,
        "disponivel": True,
        "usadas": usadas,
        "limite": limite,
        "percentual": _percentual(usadas, limite),
        "esperando": pool["cl_waiting"],
        "clientes_ativos": pool["cl_active"],
        "pool": pool,
        "pids_postgres": [
            servidor["remote_pid"]
            for servidor in servidores
            if servidor.get("database") == config_banco["NAME"] and servidor.get("remote_pid")
        ],
    }


def _status_filas_integracao():
    wms_pendentes = WMS_IntegraçãoOP.objects.filter(status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO)
    lotes_pendentes = LiberacaoLote.objects.filter(status=LiberacaoLote.Status.NAO_INTEGRADO)

    return [
        {
            "nome": "Logs Apontamentos",
            "url": reverse("logs_apontamentos"),
            "pendentes": Apontamento.objects.filter(
                status=Apontamento.Status.NAO_INTEGRADO
            ).count(),
            "pendentes_elegiveis": None,
            "bloqueados": None,
            "processando": Apontamento.objects.filter(
                status=Apontamento.Status.PROCESSANDO
            ).count(),
            "timeout_webservice": _formatar_segundos(TIMEOUT_LOGS_SEGUNDOS),
            "observacao": "Respeita ordem por chave de OP/estágio.",
        },
        {
            "nome": "Log Tempos ERP",
            "url": reverse("logs_tempos_erp"),
            # Falha de envio não tem estado próprio nesta fila: permanece
            # PENDENTE (reenviável), com o motivo registrado no log — pendência
            # é o status PENDENTE somente.
            "pendentes": PacoteTempoERP.objects.filter(
                status=PacoteTempoERP.Status.PENDENTE
            ).count(),
            "pendentes_elegiveis": None,
            "bloqueados": None,
            "processando": PacoteTempoERP.objects.filter(
                status=PacoteTempoERP.Status.PROCESSANDO
            ).count(),
            "timeout_webservice": _formatar_segundos(TIMEOUT_TEMPOS_ERP_SEGUNDOS),
            "observacao": "Reenvia pacotes pendentes; falha fica registrada no log.",
        },
        {
            "nome": "Log Apontamento Componentes",
            "url": reverse("logs_apontamento_componentes"),
            "pendentes": ApontamentoComponente.objects.filter(
                status=ApontamentoComponente.Status.NAO_INTEGRADO
            ).count(),
            "pendentes_elegiveis": None,
            "bloqueados": None,
            "processando": ApontamentoComponente.objects.filter(
                status=ApontamentoComponente.Status.PROCESSANDO
            ).count(),
            "timeout_webservice": _formatar_segundos(TIMEOUT_COMPONENTES_SEGUNDOS),
            "observacao": "Envia apontamentos de componentes pela fila assíncrona.",
        },
        {
            "nome": "Baixa Componentes",
            "url": reverse("logs_baixa_componentes"),
            "pendentes": BaixaComponente.objects.filter(
                status=BaixaComponente.Status.NAO_INTEGRADO
            ).count(),
            "pendentes_elegiveis": None,
            "bloqueados": None,
            "processando": BaixaComponente.objects.filter(
                status=BaixaComponente.Status.PROCESSANDO
            ).count(),
            "timeout_webservice": _formatar_segundos(TIMEOUT_BAIXAS_COMPONENTES_SEGUNDOS),
            "observacao": "Respeita a ordem de integração por lote de consumo.",
        },
        {
            "nome": "WMS Integrações",
            "url": reverse("qualidade:integracao_wms"),
            "pendentes": wms_pendentes.count(),
            "pendentes_elegiveis": integracoes_wms_enviaveis(wms_pendentes).count(),
            "bloqueados": wms_pendentes.filter(
                reuniao__isnull=False, reuniao__data_hora_fim__isnull=True
            ).count(),
            "processando": WMS_IntegraçãoOP.objects.filter(
                status=WMS_IntegraçãoOP.Status.PROCESSANDO
            ).count(),
            "timeout_webservice": _formatar_segundos(TIMEOUT_WMS_SEGUNDOS),
            "observacao": "Bloqueados são registros vinculados a reunião ainda aberta.",
        },
        {
            "nome": "Consulta de Lotes",
            "url": reverse("qualidade:consulta_lote"),
            "pendentes": lotes_pendentes.count(),
            "pendentes_elegiveis": lotes_pendentes.filter(
                Q(reuniao__isnull=True) | Q(reuniao__data_hora_fim__isnull=False)
            ).count(),
            "bloqueados": lotes_pendentes.filter(
                reuniao__isnull=False,
                reuniao__data_hora_fim__isnull=True,
            ).count(),
            "processando": LiberacaoLote.objects.filter(
                status=LiberacaoLote.Status.PROCESSANDO
            ).count(),
            "timeout_webservice": _formatar_segundos(TIMEOUT_LOTES_SEGUNDOS),
            "observacao": "Elegíveis ignoram registros de reunião aberta.",
        },
    ]


# Decisão do sênior (fatia Autorizações): painel de serviços fica
# staff-only — expõe sessões PostgreSQL, disco e certificado; não entra no
# modelo de permissões por rotina.
def _is_staff(user):
    return user.is_staff


@login_required
@user_passes_test(_is_staff)
def status_services(request):
    services = []
    filas_workers = []
    for service in listar_status_services():
        codigo = service.get("codigo") or ""
        item = {
            **service,
            "eh_fila": codigo.startswith("fila_"),
            "intervalo_formatado": _formatar_segundos(service.get("intervalo_segundos")),
            "limite_ciclo_formatado": _formatar_segundos(
                service.get("tempo_limite_ciclo_segundos")
            ),
            "uptime_formatado": _formatar_segundos(service.get("uptime_segundos")),
            "ciclo_atual_formatado": _formatar_segundos(service.get("ciclo_atual_segundos")),
            "duracao_formatada": _formatar_segundos(service.get("ultima_duracao_segundos")),
            "proximo_formatado": _formatar_segundos(service.get("segundos_para_proximo")),
        }
        if codigo == "coleta_telemetria":
            from telemetria.services.coleta import obter_status_coleta

            status_telemetria = obter_status_coleta()
            item["fontes_telemetria"] = status_telemetria["fontes"]
        if item["eh_fila"]:
            filas_workers.append(item)
        else:
            services.append(item)

    conexoes_postgres = _status_conexoes_postgres()
    pgbouncer = _status_pgbouncer()
    pids_pgbouncer = set(pgbouncer.get("pids_postgres", []))
    for conexao in conexoes_postgres.get("sessoes", []):
        conexao["rota"] = "PgBouncer" if conexao["pid"] in pids_pgbouncer else "Direta"

    return render(
        request,
        "accounts/status_services.html",
        {
            "titulo": "Status dos Services",
            "services": services,
            "filas_workers": filas_workers,
            "filas_integracao": _status_filas_integracao(),
            "servidor": _formatar_status_servidor(_status_servidor()),
            "conexoes_postgres": conexoes_postgres,
            "pgbouncer": pgbouncer,
            "certificado_https": _status_certificado_https(),
            "atualizado_em": timezone.now(),
        },
    )
