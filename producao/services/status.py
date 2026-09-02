import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta

from django.utils import timezone

from producao.utils.codificacao import safe_str

_SERVICES: dict[str, dict] = {}


def registrar_service(
    codigo, nome, intervalo_segundos=None, descricao="", tempo_limite_ciclo_segundos=None
):
    service = _SERVICES.setdefault(codigo, {})
    service.update(
        {
            "codigo": codigo,
            "nome": nome,
            "descricao": descricao,
            "intervalo_segundos": intervalo_segundos,
            "tempo_limite_ciclo_segundos": tempo_limite_ciclo_segundos,
            "rodando": service.get("rodando", False),
            "ciclo_em_andamento": service.get("ciclo_em_andamento", False),
            "iniciado_em": service.get("iniciado_em"),
            "ultimo_ciclo_inicio": service.get("ultimo_ciclo_inicio"),
            "ultimo_ciclo_fim": service.get("ultimo_ciclo_fim"),
            "ultima_duracao_segundos": service.get("ultima_duracao_segundos"),
            "proximo_ciclo_em": service.get("proximo_ciclo_em"),
            "thread_ident": service.get("thread_ident"),
            "ultima_atividade_em": service.get("ultima_atividade_em"),
            "atividade_valida_ate": service.get("atividade_valida_ate"),
            "interrompido_por_timeout": service.get("interrompido_por_timeout", False),
            "ultimo_status": service.get("ultimo_status", "Não iniciado"),
            "ultimo_erro": service.get("ultimo_erro", ""),
        }
    )


def marcar_service_iniciado(codigo):
    service = _SERVICES.setdefault(codigo, {"codigo": codigo, "nome": codigo})
    agora = timezone.now()
    service.update(
        {
            "rodando": True,
            "iniciado_em": service.get("iniciado_em") or agora,
            "ultimo_status": "Rodando",
            "ultimo_erro": "",
        }
    )


def marcar_service_aguardando(codigo):
    service = _SERVICES.setdefault(codigo, {"codigo": codigo, "nome": codigo})
    service.update(
        {
            "ciclo_em_andamento": False,
            "thread_ident": None,
            "atividade_valida_ate": None,
            "ultimo_status": "Aguardando próximo ciclo",
            "ultimo_erro": "",
        }
    )


def marcar_service_parado(codigo, erro=""):
    service = _SERVICES.setdefault(codigo, {"codigo": codigo, "nome": codigo})

    service.update(
        {
            "rodando": False,
            "ciclo_em_andamento": False,
            "proximo_ciclo_em": None,
            "thread_ident": None,
            "ultimo_status": "Parado com erro" if erro else "Parado",
            "ultimo_erro": safe_str(erro),
        }
    )


def marcar_ciclo_inicio(codigo):
    service = _SERVICES.setdefault(codigo, {"codigo": codigo, "nome": codigo})
    service.update(
        {
            "ciclo_em_andamento": True,
            "ultimo_ciclo_inicio": timezone.now(),
            "ultima_atividade_em": timezone.now(),
            "atividade_valida_ate": None,
            "thread_ident": threading.get_ident(),
            "interrompido_por_timeout": False,
            "ultimo_status": "Ciclo em andamento",
            "ultimo_erro": "",
        }
    )


def marcar_ciclo_fim(codigo, duracao_segundos, intervalo_segundos=None, erro=""):
    service = _SERVICES.setdefault(codigo, {"codigo": codigo, "nome": codigo})
    fim = timezone.now()
    intervalo = intervalo_segundos
    if intervalo is None:
        intervalo = service.get("intervalo_segundos")

    service.update(
        {
            "ciclo_em_andamento": False,
            "ultimo_ciclo_fim": fim,
            "ultima_duracao_segundos": duracao_segundos,
            "proximo_ciclo_em": fim + timedelta(seconds=intervalo) if intervalo else None,
            "thread_ident": None,
            "ultimo_status": "Erro no último ciclo" if erro else "Aguardando próximo ciclo",
            "ultimo_erro": safe_str(erro),
        }
    )


def listar_status_services():
    agora = timezone.now()
    services = []
    for service in _SERVICES.values():
        item = deepcopy(service)
        iniciado_em = item.get("iniciado_em")
        ciclo_inicio = item.get("ultimo_ciclo_inicio")
        ultima_atividade = item.get("ultima_atividade_em")
        atividade_valida_ate = item.get("atividade_valida_ate")
        proximo = item.get("proximo_ciclo_em")
        tempo_limite = item.get("tempo_limite_ciclo_segundos")
        item["uptime_segundos"] = (agora - iniciado_em).total_seconds() if iniciado_em else None
        item["ciclo_atual_segundos"] = (
            (agora - ciclo_inicio).total_seconds()
            if item.get("ciclo_em_andamento") and ciclo_inicio
            else None
        )
        item["segundos_desde_atividade"] = (
            (agora - ultima_atividade).total_seconds()
            if item.get("ciclo_em_andamento") and ultima_atividade
            else None
        )
        aguardando_retorno = bool(atividade_valida_ate and atividade_valida_ate > agora)
        item["ciclo_travado"] = (
            bool(item.get("ciclo_em_andamento"))
            and item["ciclo_atual_segundos"] is not None
            and tempo_limite is not None
            and item["ciclo_atual_segundos"] > tempo_limite
            and not aguardando_retorno
        )
        item["segundos_para_proximo"] = (
            max((proximo - agora).total_seconds(), 0) if proximo else None
        )
        services.append(item)
    return sorted(services, key=lambda item: item.get("nome") or item.get("codigo"))


def matar_service_travado(codigo):
    service = _SERVICES.get(codigo)
    if not service or not service.get("ciclo_em_andamento"):
        return False

    inicio = service.get("ultimo_ciclo_inicio")
    limite = service.get("tempo_limite_ciclo_segundos")
    if not inicio or limite is None:
        return False

    duracao = (timezone.now() - inicio).total_seconds()
    if duracao < limite:
        return False

    atividade_valida_ate = service.get("atividade_valida_ate")
    if atividade_valida_ate and atividade_valida_ate > timezone.now():
        return False

    # Python não oferece cancelamento seguro de thread. Injetar SystemExit em uma
    # thread arbitrária pode interromper um driver ou lock no meio da operação.
    # O supervisor só marca a ocorrência; o worker encerra pelo timeout próprio
    # da integração e libera suas reservas no fluxo normal.
    service["ultimo_status"] = "Timeout sinalizado; aguardando término seguro"
    service["ultimo_erro"] = (
        f"Ciclo excedeu {int(limite)}s; aguardando o worker encerrar com segurança."
    )
    service["interrompido_por_timeout"] = True
    return True


def matar_services_travados(codigos):
    return [codigo for codigo in codigos if matar_service_travado(codigo)]


def marcar_atividade_service(codigo, tempo_espera_retorno_segundos=None):
    service = _SERVICES.setdefault(codigo, {"codigo": codigo, "nome": codigo})
    agora = timezone.now()
    service["ultima_atividade_em"] = agora
    service["atividade_valida_ate"] = (
        agora + timedelta(seconds=tempo_espera_retorno_segundos)
        if tempo_espera_retorno_segundos
        else None
    )


def consumir_interrupcao_timeout(codigo):
    service = _SERVICES.get(codigo)
    if (
        not service
        or service.get("ciclo_em_andamento")
        or not service.get("interrompido_por_timeout")
    ):
        return False
    service["interrompido_por_timeout"] = False
    return True


@contextmanager
def ciclo_service(codigo, intervalo_segundos=None):
    inicio = time.time()
    erro = ""
    marcar_service_iniciado(codigo)
    marcar_ciclo_inicio(codigo)
    try:
        yield
    except Exception as exc:
        erro = exc
        raise
    finally:
        duracao = time.time() - inicio
        marcar_ciclo_fim(codigo, duracao, intervalo_segundos, erro)
        marcar_service_parado(codigo, erro)
