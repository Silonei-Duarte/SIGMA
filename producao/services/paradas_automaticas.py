"""Avaliação segura e aplicação das paradas automáticas por telemetria."""

import unicodedata
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import Recurso
from producao.models import LogTrocaOPAtiva, ParadaMaquina, RegraParadaRecurso
from producao.utils.paradas import (
    congelar_justificativa_aberta,
    criar_parada_nos_periodos,
    pode_encerrar_parada,
    reconciliar_periodos_da_parada,
)
from telemetria.models import Sensor, SensorRecurso

PARADO = "PARADO"
FUNCIONANDO = "FUNCIONANDO"
INDETERMINADO = "INDETERMINADO"

_COMPARACOES_NUMERICAS = {
    "igual",
    "diferente",
    "maior",
    "maior_ou_igual",
    "menor",
    "menor_ou_igual",
}
_COMPARACOES_SIMPLES = {"igual", "diferente"}


def _chave(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return (
        "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
        .strip()
        .lower()
    )


def _operador_grupo(valor):
    normalizado = _chave(valor)
    return {"e": "E", "ou": "OU", "nao": "NAO"}.get(normalizado)


def _comparacao(valor):
    normalizado = _chave(valor).replace("-", "_").replace(" ", "_")
    aliases = {
        "maior_igual": "maior_ou_igual",
        "menor_igual": "menor_ou_igual",
    }
    return aliases.get(normalizado, normalizado)


def _sensores_vinculados(recurso):
    return {
        vinculo.sensor.chave_origem: vinculo.sensor
        for vinculo in SensorRecurso.objects.filter(
            recurso=recurso,
            sensor__ativo=True,
        ).select_related("sensor")
    }


def _converter_numerico(valor, inteiro=False):
    if isinstance(valor, bool):
        raise ValueError
    texto = str(valor).strip()
    if not texto:
        raise ValueError
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(texto)
    except InvalidOperation, ValueError:
        raise ValueError from None
    if inteiro:
        if numero != numero.to_integral_value():
            raise ValueError
        return int(numero)
    return numero


def _converter_booleano(valor):
    if isinstance(valor, bool):
        return valor
    normalizado = _chave(valor)
    if normalizado in {"1", "true", "sim", "yes", "on"}:
        return True
    if normalizado in {"0", "false", "nao", "no", "off"}:
        return False
    raise ValueError


def _valor_esperado(valor, tipo):
    if tipo == Sensor.TipoValor.DECIMAL:
        return _converter_numerico(valor)
    if tipo == Sensor.TipoValor.INTEIRO:
        return _converter_numerico(valor, inteiro=True)
    if tipo == Sensor.TipoValor.BOOLEANO:
        return _converter_booleano(valor)
    if not isinstance(valor, str):
        raise ValueError
    return valor


def _valor_snapshot(valor, tipo):
    if tipo == Sensor.TipoValor.DECIMAL:
        if not isinstance(valor, (int, float, Decimal)) or isinstance(valor, bool):
            raise ValueError
        return Decimal(str(valor))
    if tipo == Sensor.TipoValor.INTEIRO:
        if not isinstance(valor, int) or isinstance(valor, bool):
            raise ValueError
        return valor
    if tipo == Sensor.TipoValor.BOOLEANO:
        if not isinstance(valor, bool):
            raise ValueError
        return valor
    if not isinstance(valor, str):
        raise ValueError
    return valor


def _validar_no(no, sensores, caminho="raiz"):
    if not isinstance(no, dict):
        raise ValidationError(f"{caminho}: cada item da regra deve ser um objeto.")

    tipo = _chave(no.get("tipo"))
    if tipo == "grupo":
        operador = _operador_grupo(no.get("operador"))
        itens = no.get("itens")
        if operador is None:
            raise ValidationError(f"{caminho}: operador de grupo inválido.")
        if not isinstance(itens, list) or not itens:
            raise ValidationError(f"{caminho}: o grupo precisa possuir ao menos uma condição.")
        if operador == "NAO" and len(itens) != 1:
            raise ValidationError(f"{caminho}: o grupo NÃO aceita exatamente um item.")
        for indice, item in enumerate(itens, start=1):
            _validar_no(item, sensores, f"{caminho}.{indice}")
        return

    if tipo != "condicao":
        raise ValidationError(f"{caminho}: tipo de item inválido.")

    codigo = no.get("sensor")
    if not isinstance(codigo, str) or not codigo.strip():
        raise ValidationError(f"{caminho}: informe o código do sensor.")
    sensor = sensores.get(codigo)
    if sensor is None:
        raise ValidationError(
            f"{caminho}: sensor {codigo!r} não está ativo e vinculado ao recurso."
        )

    comparacao = _comparacao(no.get("comparacao"))
    permitidas = (
        _COMPARACOES_NUMERICAS
        if sensor.tipo_valor
        in {
            Sensor.TipoValor.DECIMAL,
            Sensor.TipoValor.INTEIRO,
        }
        else _COMPARACOES_SIMPLES
    )
    if comparacao not in permitidas:
        raise ValidationError(
            f"{caminho}: comparação incompatível com o tipo {sensor.tipo_valor} do sensor {codigo}."
        )
    if "valor" not in no:
        raise ValidationError(f"{caminho}: informe o valor esperado.")
    try:
        _valor_esperado(no["valor"], sensor.tipo_valor)
    except TypeError, ValueError:
        raise ValidationError(
            f"{caminho}: valor esperado incompatível com o sensor {codigo}."
        ) from None


def validar_regra_parada(regra, recurso):
    """Valida a árvore JSON sem executar conteúdo armazenado."""
    if not isinstance(regra, dict):
        raise ValidationError("A regra deve ser um objeto JSON.")
    _validar_no(regra, _sensores_vinculados(recurso))


def _comparar(atual, esperado, comparacao):
    if comparacao == "igual":
        return atual == esperado
    if comparacao == "diferente":
        return atual != esperado
    if comparacao == "maior":
        return atual > esperado
    if comparacao == "maior_ou_igual":
        return atual >= esperado
    if comparacao == "menor":
        return atual < esperado
    if comparacao == "menor_ou_igual":
        return atual <= esperado
    raise ValueError


def _avaliar_no(no, snapshot, sensores):
    tipo = _chave(no.get("tipo"))
    if tipo == "condicao":
        codigo = no.get("sensor")
        sensor = sensores.get(codigo)
        if sensor is None or codigo not in snapshot:
            return None
        try:
            atual = _valor_snapshot(snapshot[codigo], sensor.tipo_valor)
            esperado = _valor_esperado(no.get("valor"), sensor.tipo_valor)
            return _comparar(atual, esperado, _comparacao(no.get("comparacao")))
        except TypeError, ValueError, InvalidOperation:
            return None

    if tipo != "grupo":
        return None
    operador = _operador_grupo(no.get("operador"))
    itens = no.get("itens")
    if operador is None or not isinstance(itens, list) or not itens:
        return None
    resultados = [_avaliar_no(item, snapshot, sensores) for item in itens]
    if any(resultado is None for resultado in resultados):
        return None
    if operador == "E":
        return all(resultados)
    if operador == "OU":
        return any(resultados)
    if operador == "NAO" and len(resultados) == 1:
        return not resultados[0]
    return None


def avaliar_regra_parada(recurso, regra, snapshot):
    """Retorna PARADO, FUNCIONANDO ou INDETERMINADO para um snapshot."""
    if not getattr(regra, "ativa", False) or not isinstance(snapshot, dict):
        return INDETERMINADO
    try:
        validar_regra_parada(regra.regra, recurso)
        resultado = _avaliar_no(regra.regra, snapshot, _sensores_vinculados(recurso))
    except ValidationError, TypeError, ValueError:
        return INDETERMINADO
    if resultado is None:
        return INDETERMINADO
    return PARADO if resultado else FUNCIONANDO


@dataclass
class EstadoParadaAutomatica:
    carregado: bool = False
    inicio_sinal_parado: object = None
    inicio_parada_automatica_aberta: object = None

    def reiniciar(self):
        self.carregado = False
        self.inicio_sinal_parado = None
        self.inicio_parada_automatica_aberta = None


def _carregar_estado_operacional(recurso_id, estado):
    parada_aberta = (
        ParadaMaquina.objects.filter(
            recurso_id=recurso_id,
            fim__isnull=True,
            tipo=2,
        )
        .order_by("-inicio", "-id")
        .first()
    )
    estado.inicio_parada_automatica_aberta = parada_aberta.inicio if parada_aberta else None
    estado.carregado = True


def abrir_parada_por_sinal(recurso_id, agora=None):
    agora = (agora or timezone.now()).replace(microsecond=0)
    with transaction.atomic():
        recurso = Recurso.objects.select_for_update().get(pk=recurso_id)
        regra = (
            RegraParadaRecurso.objects.select_for_update()
            .filter(recurso=recurso, ativa=True)
            .first()
        )
        if (
            not regra
            or not recurso.aponta_parada
            or recurso.tempo_parada_aut is None
            or recurso.tempo_parada_aut < timedelta()
        ):
            return None
        periodos = list(
            LogTrocaOPAtiva.objects.select_for_update()
            .filter(recurso=recurso, horario_saida__isnull=True)
            .order_by("-horario_troca", "-id")
        )
        if not periodos:
            return None
        parada_aberta = (
            ParadaMaquina.objects.select_for_update()
            .filter(recurso=recurso, fim__isnull=True)
            .order_by("id")
            .first()
        )
        if parada_aberta:
            return None
        periodo_atual = periodos[0]
        return criar_parada_nos_periodos(
            periodos=periodos,
            operador=periodo_atual.id_operador,
            usuario=periodo_atual.usuario,
            inicio=agora,
            tipo=2,
            data_hora=agora,
            limite_fim=agora,
        )


def fechar_parada_por_sinal(recurso_id, agora=None):
    agora = (agora or timezone.now()).replace(microsecond=0)
    with transaction.atomic():
        recurso = Recurso.objects.select_for_update().get(pk=recurso_id)
        regra = (
            RegraParadaRecurso.objects.select_for_update()
            .filter(recurso=recurso, ativa=True)
            .first()
        )
        if not regra or recurso.tempo_parada_aut is None or recurso.tempo_parada_aut < timedelta():
            return None
        periodos = list(
            LogTrocaOPAtiva.objects.select_for_update().filter(recurso=recurso).order_by("id")
        )
        parada = (
            ParadaMaquina.objects.select_for_update()
            .filter(recurso=recurso, fim__isnull=True)
            .order_by("-inicio", "-id")
            .first()
        )
        if (
            not parada
            or (parada.tipo != 2 and not recurso.telemetria_encerra_parada_manual)
            or not pode_encerrar_parada(parada, agora)
        ):
            return None
        parada.fim = agora
        parada.save(update_fields=["fim"])
        congelar_justificativa_aberta(parada, agora=agora)
        reconciliar_periodos_da_parada(parada, periodos=periodos, agora=agora)
        return parada


def avaliar_e_aplicar_parada_automatica(recurso_id, snapshot, estado, agora=None):
    """Abre após detecção contínua de parada e fecha no primeiro sinal de operação."""
    agora = (agora or timezone.now()).replace(microsecond=0)
    try:
        regra = RegraParadaRecurso.objects.select_related("recurso").get(recurso_id=recurso_id)
    except RegraParadaRecurso.DoesNotExist:
        estado.reiniciar()
        return {"avaliacao": INDETERMINADO, "acao": None}

    avaliacao = avaliar_regra_parada(regra.recurso, regra, snapshot)
    if avaliacao == INDETERMINADO:
        estado.reiniciar()
        return {"avaliacao": avaliacao, "acao": None}

    espera = regra.recurso.tempo_parada_aut
    if espera is None or espera < timedelta():
        estado.reiniciar()
        return {"avaliacao": avaliacao, "acao": None}

    if not estado.carregado:
        _carregar_estado_operacional(recurso_id, estado)

    if avaliacao == PARADO:
        parada = None
        if estado.inicio_parada_automatica_aberta is not None:
            estado.inicio_sinal_parado = None
        elif ParadaMaquina.objects.filter(recurso_id=recurso_id, fim__isnull=True).exists():
            # Uma parada manual já representa esta interrupção; quando ela for
            # encerrada, exige-se uma nova janela contínua do sinal parado.
            estado.inicio_sinal_parado = None
        else:
            if estado.inicio_sinal_parado is None:
                estado.inicio_sinal_parado = agora
            if agora >= estado.inicio_sinal_parado + espera:
                parada = abrir_parada_por_sinal(recurso_id, agora=agora)
                if parada:
                    estado.inicio_parada_automatica_aberta = parada.inicio
                    estado.inicio_sinal_parado = None
        acao = "aberta" if parada else None
    else:
        estado.inicio_sinal_parado = None
        parada = None
        if (
            estado.inicio_parada_automatica_aberta is not None
            or regra.recurso.telemetria_encerra_parada_manual
        ):
            parada = fechar_parada_por_sinal(recurso_id, agora=agora)
            estado.inicio_parada_automatica_aberta = None
        acao = "fechada" if parada else None

    return {"avaliacao": avaliacao, "acao": acao, "parada_id": parada.id if parada else None}
