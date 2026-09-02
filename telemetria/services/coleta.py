import json
import logging
import math
import threading
import time

import requests
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from accounts.models import Recurso
from producao.services.paradas_automaticas import (
    EstadoParadaAutomatica,
    avaliar_e_aplicar_parada_automatica,
)
from producao.services.status import (
    marcar_service_aguardando,
    marcar_service_iniciado,
    marcar_service_parado,
    registrar_service,
)
from telemetria.models import FonteColetaHTTP, LeituraTelemetria, Sensor
from telemetria.validacao_http import validar_url_coleta

logger = logging.getLogger(__name__)
SERVICE_CODIGO = "coleta_telemetria"
SERVICE_NOME = "Coleta de Telemetria"
# Log gravado em FonteColetaHTTP.log a cada tentativa bem-sucedida (a falha
# tem texto livre). Comparar por sucesso é mais resistente do que casar o
# texto exato de algum erro; consumidores de fora importam esta constante.
LOG_COLETA_SUCESSO = "Coleta concluída."
_AUSENTE = object()
_CHAVE_CONTAGEM_BOBINAS = "contagemBobinas"
_CHAVE_ESTOURO_CONTAGEM = "estouroDeContagem"
_LIMITE_CONTAGEM_BOBINAS = 32000
_CHAVE_PESO_BALANCA = "pesoBalanca"
_LIMITE_PESO_BALANCA = 5000


class ErroColetaTelemetria(Exception):
    pass


def converter_valor(valor, tipo):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if tipo == Sensor.TipoValor.TEXTO:
        return str(valor).strip()
    if tipo == Sensor.TipoValor.BOOLEANO:
        normalizado = str(valor).strip().lower()
        if normalizado in {"1", "true", "sim", "yes", "on"}:
            return True
        if normalizado in {"0", "false", "nao", "não", "no", "off"}:
            return False
        raise ErroColetaTelemetria(f"Booleano inválido: {valor!r}.")
    try:
        texto = str(valor).strip()
        numero = float(texto.replace(".", "").replace(",", ".") if "," in texto else texto)
        if tipo == Sensor.TipoValor.INTEIRO:
            if not numero.is_integer():
                raise ValueError
            return int(numero)
        return numero
    except (TypeError, ValueError) as exc:
        raise ErroColetaTelemetria(f"Valor {valor!r} inválido para {tipo}.") from exc


def _calcular_numero_bobina(bloco):
    if _CHAVE_CONTAGEM_BOBINAS not in bloco or _CHAVE_ESTOURO_CONTAGEM not in bloco:
        return None
    try:
        contagem = int(bloco[_CHAVE_CONTAGEM_BOBINAS])
        estouro = int(bloco[_CHAVE_ESTOURO_CONTAGEM])
    except TypeError, ValueError:
        return None
    return estouro * _LIMITE_CONTAGEM_BOBINAS + contagem


def _obter_peso_balanca(bloco):
    if _CHAVE_PESO_BALANCA not in bloco:
        return None
    try:
        peso = converter_valor(bloco[_CHAVE_PESO_BALANCA], Sensor.TipoValor.DECIMAL)
    except ErroColetaTelemetria:
        return None
    if peso is None or not math.isfinite(peso) or not 0 <= peso <= _LIMITE_PESO_BALANCA:
        return None
    return peso


def coletar_fonte(fonte, cliente_http=None):
    validar_url_coleta(fonte.url)
    resposta = None
    try:
        resposta = (cliente_http or requests.get)(
            fonte.url,
            timeout=min(fonte.timeout_segundos, settings.TELEMETRIA_TIMEOUT_MAX_SEGUNDOS),
            allow_redirects=False,
            stream=True,
        )
        resposta.raise_for_status()
        limite = settings.TELEMETRIA_RESPOSTA_MAX_BYTES
        if (
            resposta.headers.get("Content-Length")
            and int(resposta.headers["Content-Length"]) > limite
        ):
            raise ErroColetaTelemetria("Resposta HTTP excede o tamanho permitido.")
        partes, tamanho = [], 0
        for parte in resposta.iter_content(chunk_size=8192):
            tamanho += len(parte)
            if tamanho > limite:
                raise ErroColetaTelemetria("Resposta HTTP excede o tamanho permitido.")
            partes.append(parte)
        dados = json.loads(b"".join(partes).decode(resposta.encoding or "utf-8", errors="replace"))
        if not isinstance(dados, dict):
            raise ErroColetaTelemetria("Resposta HTTP deve ser um objeto JSON.")
        return dados
    except requests.Timeout as exc:
        raise ErroColetaTelemetria("Timeout na requisição HTTP.") from exc
    except requests.RequestException as exc:
        raise ErroColetaTelemetria("Falha na requisição HTTP.") from exc
    except json.JSONDecodeError as exc:
        raise ErroColetaTelemetria("Resposta HTTP não contém JSON válido.") from exc
    finally:
        if resposta is not None:
            resposta.close()


def _deve_salvar(vinculo, anterior, atual):
    if anterior == atual or not vinculo.monitorar_variacao:
        return False
    if vinculo.sensor.tipo_valor in {Sensor.TipoValor.BOOLEANO, Sensor.TipoValor.TEXTO}:
        return True
    if anterior is None or atual is None:
        return True
    diferenca = abs(atual - anterior)
    return (
        diferenca >= vinculo.tolerancia
        if vinculo.tipo_tolerancia == "absoluta"
        else (
            atual != anterior
            if anterior == 0
            else (diferenca / abs(anterior)) * 100 >= vinculo.tolerancia
        )
    )


def processar_snapshot_recurso(
    recurso_id, vinculos, bloco, anterior=_AUSENTE, processar_snapshot=None, invalidar_snapshot=None
):
    valores = {
        v.sensor.chave_origem: converter_valor(bloco[v.sensor.chave_origem], v.sensor.tipo_valor)
        for v in vinculos
        if v.sensor.chave_origem in bloco
    }
    if not valores:
        if invalidar_snapshot:
            invalidar_snapshot(recurso_id)
        return None
    if processar_snapshot:
        processar_snapshot(recurso_id, valores)
    if anterior is _AUSENTE:
        leitura = (
            LeituraTelemetria.objects.filter(recurso_id=recurso_id).order_by("-coletado_em").first()
        )
        anterior = leitura.valores if leitura else None
    # Sem leitura anterior, só grava a baseline se algum vínculo relevante de
    # fato monitorar variação; senão nunca haverá comparação futura para ela.
    vinculos_relevantes = [v for v in vinculos if v.sensor.chave_origem in valores]
    if anterior is None:
        salvar = any(v.monitorar_variacao for v in vinculos_relevantes)
    else:
        salvar = any(
            _deve_salvar(v, anterior.get(v.sensor.chave_origem), valores.get(v.sensor.chave_origem))
            for v in vinculos_relevantes
        )
    if salvar:
        LeituraTelemetria.objects.create(recurso_id=recurso_id, valores=valores)
        return valores
    return anterior


class CoordenadorColetaTelemetria(threading.Thread):
    _instancia = None

    def __init__(self):
        super().__init__(name="CoordenadorColetaTelemetria", daemon=True)
        self.parar, self.acordar = threading.Event(), threading.Event()
        self.lock_reagendamento = threading.Lock()
        self.fontes, self.proximos = {}, {}
        self.fontes_reagendadas = set()
        self.ultimas_leituras, self.ultimos_snapshots, self.estados = {}, {}, {}
        self.ultimas_bobinas = {}
        self.ultimos_pesos_balanca = {}
        self.recursos_peso_balanca_por_fonte = {}
        self.fonte_em_coleta_id = None
        registrar_service(
            SERVICE_CODIGO, SERVICE_NOME, None, "Coleta HTTP contínua por fonte JSON.", 0
        )

    def recarregar(self):
        fontes = FonteColetaHTTP.objects.filter(coleta_ativa=True).prefetch_related(
            "sensores__recursos__recurso"
        )
        self.fontes = {fonte.pk: fonte for fonte in fontes}
        self.proximos = {id_: x for id_, x in self.proximos.items() if id_ in self.fontes}

        with self.lock_reagendamento:
            fontes_reagendadas = self.fontes_reagendadas
            self.fontes_reagendadas = set()
        agora = time.monotonic()
        for fonte_id in fontes_reagendadas:
            if fonte_id in self.fontes:
                self.proximos[fonte_id] = agora

    def reagendar_fonte(self, fonte_id):
        with self.lock_reagendamento:
            self.fontes_reagendadas.add(fonte_id)
        self.acordar.set()

    def _invalidar(self, recurso_id):
        if recurso_id in self.estados:
            self.estados[recurso_id].reiniciar()

    def _snapshot(self, recurso_id, valores):
        self.ultimos_snapshots[recurso_id] = dict(valores)
        return avaliar_e_aplicar_parada_automatica(
            recurso_id, valores, self.estados.setdefault(recurso_id, EstadoParadaAutomatica())
        )

    def _atualizar_bobinas(self, dados):
        for codigo, bloco in dados.items():
            if not isinstance(bloco, dict):
                continue
            numero_bobina = _calcular_numero_bobina(bloco)
            if numero_bobina is None:
                continue
            anterior = self.ultimas_bobinas.get(codigo, _AUSENTE)
            if anterior is _AUSENTE:
                recurso = Recurso.objects.filter(codigo=codigo).only("id", "bobina").first()
                if recurso is None:
                    continue
                anterior = recurso.bobina
            if anterior == numero_bobina:
                self.ultimas_bobinas[codigo] = numero_bobina
                continue
            Recurso.objects.filter(codigo=codigo).update(bobina=numero_bobina)
            self.ultimas_bobinas[codigo] = numero_bobina

    def _enviar_atualizacao_balanca(self, recurso_id, peso):
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"balanca_{recurso_id}", {"type": "balanca_update", "balanca": peso}
            )
        except Exception:
            logger.exception("Falha ao atualizar a balança do recurso %s", recurso_id)

    def _atualizar_pesos_balanca(self, fonte_id, dados):
        for codigo, bloco in dados.items():
            if not isinstance(bloco, dict):
                continue
            recurso = Recurso.objects.filter(codigo=codigo).only("id").first()
            if recurso is None:
                continue
            peso = _obter_peso_balanca(bloco)
            if peso is None:
                peso = 0
            self.ultimos_pesos_balanca[recurso.id] = peso
            self.recursos_peso_balanca_por_fonte.setdefault(fonte_id, set()).add(recurso.id)
            self._enviar_atualizacao_balanca(recurso.id, peso)

    def _zerar_pesos_balanca_fonte(self, fonte_id):
        for recurso_id in self.recursos_peso_balanca_por_fonte.get(fonte_id, set()):
            self.ultimos_pesos_balanca[recurso_id] = 0
            self._enviar_atualizacao_balanca(recurso_id, 0)

    def _coletar(self, fonte):
        close_old_connections()
        try:
            dados, por_recurso = coletar_fonte(fonte), {}
            self._atualizar_bobinas(dados)
            self._atualizar_pesos_balanca(fonte.id, dados)
            for sensor in fonte.sensores.all():
                if not sensor.ativo:
                    continue
                for vinculo in sensor.recursos.all():
                    por_recurso.setdefault(vinculo.recurso_id, []).append(vinculo)
            for recurso_id, vinculos in por_recurso.items():
                bloco = dados.get(vinculos[0].recurso.codigo)
                if not isinstance(bloco, dict):
                    self._invalidar(recurso_id)
                    continue
                resultado = processar_snapshot_recurso(
                    recurso_id,
                    vinculos,
                    bloco,
                    self.ultimas_leituras.get(recurso_id, _AUSENTE),
                    self._snapshot,
                    self._invalidar,
                )
                if resultado is not None:
                    self.ultimas_leituras[recurso_id] = resultado
            FonteColetaHTTP.objects.filter(pk=fonte.pk).update(
                log=LOG_COLETA_SUCESSO, ultima_coleta_em=timezone.now()
            )
            return fonte.pausa_sucesso_segundos
        except Exception:
            logger.exception("Falha na coleta da fonte %s", fonte.pk)
            self._zerar_pesos_balanca_fonte(fonte.id)
            FonteColetaHTTP.objects.filter(pk=fonte.pk).update(
                log="Falha na coleta de telemetria.", ultima_coleta_em=timezone.now()
            )
            return fonte.backoff_erro_segundos

    def _proxima_espera(self):
        if not self.proximos:
            return None
        return max(min(self.proximos.values()) - time.monotonic(), 0)

    def run(self):
        marcar_service_iniciado(SERVICE_CODIGO)
        self.recarregar()
        while not self.parar.is_set():
            if self.acordar.is_set():
                self.acordar.clear()
                self.recarregar()

            fonte = next(
                (
                    fonte
                    for fonte_id, fonte in self.fontes.items()
                    if time.monotonic() >= self.proximos.get(fonte_id, 0)
                ),
                None,
            )
            if fonte is not None:
                self.fonte_em_coleta_id = fonte.id
                pausa = self._coletar(fonte)
                self.fonte_em_coleta_id = None
                self.proximos[fonte.id] = time.monotonic() + pausa
                continue

            if not self.fontes:
                marcar_service_aguardando(SERVICE_CODIGO)
            self.acordar.wait(self._proxima_espera())
        marcar_service_parado(SERVICE_CODIGO)

    def encerrar(self):
        self.parar.set()
        self.acordar.set()


def start_coleta_telemetria():
    instancia = CoordenadorColetaTelemetria._instancia
    if not instancia or not instancia.is_alive():
        instancia = CoordenadorColetaTelemetria()
        CoordenadorColetaTelemetria._instancia = instancia
        instancia.start()
    return instancia


def notificar_alteracao_fonte(fonte_id):
    instancia = start_coleta_telemetria()
    instancia.reagendar_fonte(fonte_id)


def notificar_alteracao_recurso(_recurso_id):
    notificar_alteracao_fonte(None)


def invalidar_estado_parada_automatica(recurso_id):
    if CoordenadorColetaTelemetria._instancia:
        CoordenadorColetaTelemetria._instancia._invalidar(recurso_id)


def obter_cache_recurso(recurso_id):
    instancia = CoordenadorColetaTelemetria._instancia
    return (
        None
        if not instancia or not instancia.is_alive()
        else {
            "recurso_id": recurso_id,
            "ultimo_snapshot": instancia.ultimos_snapshots.get(recurso_id),
            "ultima_leitura_salva": instancia.ultimas_leituras.get(recurso_id),
        }
    )


def obter_status_coleta():
    fontes = FonteColetaHTTP.objects.filter(coleta_ativa=True).order_by("url")
    instancia = CoordenadorColetaTelemetria._instancia
    proximos = getattr(instancia, "proximos", {})
    fonte_em_coleta_id = getattr(instancia, "fonte_em_coleta_id", None)
    return {
        "fontes": [
            {
                "url": fonte.url,
                "timeout_segundos": fonte.timeout_segundos,
                "pausa_sucesso_segundos": fonte.pausa_sucesso_segundos,
                "backoff_erro_segundos": fonte.backoff_erro_segundos,
                "situacao": "Coletando" if fonte.id == fonte_em_coleta_id else "Aguardando",
                "proxima_segundos": None
                if fonte.id == fonte_em_coleta_id
                else max(proximos.get(fonte.id, time.monotonic()) - time.monotonic(), 0),
                "log": fonte.log,
                "ultima_coleta_em": fonte.ultima_coleta_em,
            }
            for fonte in fontes
        ]
    }
