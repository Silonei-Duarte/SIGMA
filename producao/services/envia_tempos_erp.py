import json
import logging
import re
import threading
from datetime import timedelta
from xml.sax.saxutils import escape

from django.conf import settings
from django.db import close_old_connections, connections, transaction
from django.utils import timezone

from producao.models import ItemPacoteTempoERP, PacoteTempoERP
from producao.services.sapiens import enviar_soap_sapiens
from producao.services.status import ciclo_service, marcar_atividade_service, registrar_service
from producao.utils.codificacao import get_response_text, safe_str
from producao.utils.sapiens_soap import escapar_cdata_sapiens
from SIGMA.segredos import mascarar_segredos

logger = logging.getLogger(__name__)
PROCESSAMENTO_TEMPOS_ERP_LOCK = threading.Lock()
WEBSERVICE_TIMEOUT_SEGUNDOS = 180
TEMPO_LIMITE_CICLO_SEGUNDOS = 1800
SERVICE_CODIGO = "fila_tempos_erp"
SERVICE_NOME = "Fila Log Tempos ERP"

registrar_service(
    SERVICE_CODIGO,
    SERVICE_NOME,
    None,
    "Processa os pacotes de produção e parada para o ERP.",
    TEMPO_LIMITE_CICLO_SEGUNDOS,
)


def _chave_op(pacote):
    troca = pacote.troca_op_ativa
    codemp = troca.recurso.centro_recurso.setor.departamento.filial.empresa.codemp
    return codemp, troca.origem, troca.op, troca.estagio, troca.seqrot, troca.recurso_id


def reservar_pacotes_tempo_erp_para_envio(chaves_ignoradas=None):
    chaves_ignoradas = chaves_ignoradas or set()
    with transaction.atomic():
        pacotes = list(
            # Falha não tem estado próprio: erro É pendente, o log diferencia.
            PacoteTempoERP.objects.filter(status=PacoteTempoERP.Status.PENDENTE)
            .select_for_update(skip_locked=True)
            .select_related(
                "troca_op_ativa__recurso__centro_recurso__setor__departamento__filial__empresa"
            )
            .order_by("corte_fim_real", "id")
        )
        chaves_processando = {
            _chave_op(pacote)
            for pacote in PacoteTempoERP.objects.filter(
                status=PacoteTempoERP.Status.PROCESSANDO
            ).select_related(
                "troca_op_ativa__recurso__centro_recurso__setor__departamento__filial__empresa"
            )
        }
        ids = []
        chaves_reservadas = set()
        for pacote in pacotes:
            chave = _chave_op(pacote)
            if (
                chave in chaves_ignoradas
                or chave in chaves_processando
                or chave in chaves_reservadas
            ):
                continue
            ids.append(pacote.id)
            chaves_reservadas.add(chave)

        if ids:
            PacoteTempoERP.objects.filter(id__in=ids).update(
                status=PacoteTempoERP.Status.PROCESSANDO,
                log="Aguardando processamento background",
                data_hora_log=timezone.now(),
            )
    return ids


def reservar_pacote_tempo_erp_para_envio(pacote_id):
    with transaction.atomic():
        pacote = (
            PacoteTempoERP.objects.select_for_update()
            .select_related(
                "troca_op_ativa__recurso__centro_recurso__setor__departamento__filial__empresa"
            )
            .filter(pk=pacote_id)
            .first()
        )
        if not pacote or pacote.status != PacoteTempoERP.Status.PENDENTE:
            return False, "O pacote não está disponível para envio."

        troca = pacote.troca_op_ativa
        mesma_chave = PacoteTempoERP.objects.filter(
            troca_op_ativa__recurso_id=troca.recurso_id,
            troca_op_ativa__origem=troca.origem,
            troca_op_ativa__op=troca.op,
            troca_op_ativa__estagio=troca.estagio,
            troca_op_ativa__seqrot=troca.seqrot,
        ).exclude(pk=pacote.id)
        anterior = (
            mesma_chave.filter(
                status__in=[
                    PacoteTempoERP.Status.PENDENTE,
                    PacoteTempoERP.Status.PROCESSANDO,
                ],
            )
            .filter(
                corte_fim_real__lt=pacote.corte_fim_real,
            )
            .exists()
        )
        if anterior or mesma_chave.filter(status=PacoteTempoERP.Status.PROCESSANDO).exists():
            return False, "Aguardando integração de pacote anterior da mesma OP."

        PacoteTempoERP.objects.filter(pk=pacote.id).update(
            status=PacoteTempoERP.Status.PROCESSANDO,
            log="Aguardando processamento background",
            data_hora_log=timezone.now(),
        )
    return True, ""


def liberar_pacotes_tempo_erp_processando_antigos(idade_segundos=None):
    pacotes = PacoteTempoERP.objects.filter(status=PacoteTempoERP.Status.PROCESSANDO)
    if idade_segundos is not None:
        pacotes = pacotes.filter(
            data_hora_log__lt=timezone.now() - timedelta(seconds=idade_segundos)
        )
    return pacotes.update(
        status=PacoteTempoERP.Status.PENDENTE,
        log="Processamento anterior interrompido. Disponível para novo envio.",
        data_hora_log=timezone.now(),
    )


def _data_hora(data, hora):
    hora = hora.replace(second=0, microsecond=0)
    return data.strftime("%d/%m/%Y"), hora.strftime("%H:%M:%S")


def montar_payload_apontamento_tempos(pacote):
    troca = pacote.troca_op_ativa
    producoes = []
    paradas = []
    for item in pacote.itens.all().order_by("data_inicio", "hora_inicio", "id"):
        data_inicio, hora_inicio = _data_hora(item.data_inicio, item.hora_inicio)
        data_fim, hora_fim = _data_hora(item.data_fim, item.hora_fim)
        registro = {
            "operador": item.operador,
            "data_inicio": data_inicio,
            "hora_inicio": hora_inicio,
            "data_fim": data_fim,
            "hora_fim": hora_fim,
        }
        if item.tipo_registro == ItemPacoteTempoERP.TipoRegistro.PARADA:
            registro["motivo"] = item.motivo or ""
            paradas.append(registro)
        else:
            producoes.append(registro)

    return {
        "wacao": "APONTAMENTO-TEMPOS",
        "empresa": troca.recurso.centro_recurso.setor.departamento.filial.empresa.codemp,
        "origem": troca.origem,
        "op": troca.op,
        "estagio": troca.estagio,
        "roteiro": troca.seqrot,
        "maquina": troca.recurso.centro_recurso.codigo_integrador,
        "producoes": producoes,
        "paradas": paradas,
    }


def chamar_apontamento_tempos_erp(payload):
    url = f"{settings.SAPIENS_URL_BASE}/g5-senior-services/sapiens_Synccustom.senior.man.producao"
    dados = json.dumps(payload, ensure_ascii=False)
    envelope = f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<soapenv:Envelope xmlns:soapenv="http://www.w3.org/2003/05/soap-envelope" xmlns:ser="http://services.senior.com.br">
  <soapenv:Header/>
  <soapenv:Body>
    <ser:ApontamentoTempos>
      <user>{escape(str(settings.SAPIENS_USERNAME))}</user>
      <password>{escape(str(settings.SAPIENS_PASSWORD))}</password>
      <encryption>0</encryption>
      <parameters><flowInstanceID></flowInstanceID><flowName></flowName><tabelaEntradas><chave>wdados</chave><valor><![CDATA[{escapar_cdata_sapiens(dados)}]]></valor></tabelaEntradas></parameters>
    </ser:ApontamentoTempos>
  </soapenv:Body>
</soapenv:Envelope>"""
    logger.debug("SOAP enviado (ApontamentoTempos): %s", mascarar_segredos(envelope))
    resposta = enviar_soap_sapiens(
        url,
        envelope,
        timeout=WEBSERVICE_TIMEOUT_SEGUNDOS,
        validar_status=False,
    )
    retorno = get_response_text(resposta)
    logger.debug("Resposta SOAP (ApontamentoTempos): %s", mascarar_segredos(retorno))
    if not resposta.ok:
        raise RuntimeError(f"HTTP {resposta.status_code}: {mascarar_segredos(retorno)}")
    return retorno


def _retorno_sucesso(retorno):
    encontrado = re.search(r"<waRetorno>(.*?)</waRetorno>", retorno, re.DOTALL | re.IGNORECASE)
    conteudo = encontrado.group(1) if encontrado else retorno
    try:
        resposta = json.loads(conteudo)
    except TypeError, json.JSONDecodeError:
        return "processado com sucesso" in conteudo.lower(), conteudo
    sucesso = resposta.get("status") == "OK" or resposta.get("message") == "OK"
    return sucesso, conteudo


def _processar_pacote(pacote_id):
    pacote = (
        PacoteTempoERP.objects.select_related(
            "troca_op_ativa__recurso__centro_recurso__setor__departamento__filial__empresa"
        )
        .prefetch_related("itens")
        .get(pk=pacote_id)
    )
    marcar_atividade_service(SERVICE_CODIGO, WEBSERVICE_TIMEOUT_SEGUNDOS)
    try:
        retorno = chamar_apontamento_tempos_erp(montar_payload_apontamento_tempos(pacote))
        sucesso, log = _retorno_sucesso(retorno)
        # Mascara o mais perto possivel da gravacao: log pode ecoar o envelope da
        # requisicao em SOAP faults, mesmo vindo do conteudo de negocio do waRetorno.
        log = mascarar_segredos(log)
        # Falha de negócio não tem estado próprio (alinhamento com as demais
        # filas): volta a PENDENTE, reenviável pelo scheduler e pela tela —
        # quem diferencia o desfecho é o log mascarado gravado abaixo.
        PacoteTempoERP.objects.filter(
            pk=pacote.id, status=PacoteTempoERP.Status.PROCESSANDO
        ).update(
            status=(PacoteTempoERP.Status.INTEGRADO if sucesso else PacoteTempoERP.Status.PENDENTE),
            log=log,
            data_hora_log=timezone.now(),
        )
        return sucesso, _chave_op(pacote)
    except Exception as exc:
        log = mascarar_segredos(f"Erro ao enviar pacote {pacote.id}: {safe_str(exc)}")
        logger.error(log)
        # Mesmo desfecho da falha de negócio: pendente com log, reenviável.
        PacoteTempoERP.objects.filter(
            pk=pacote.id, status=PacoteTempoERP.Status.PROCESSANDO
        ).update(
            status=PacoteTempoERP.Status.PENDENTE,
            log=log,
            data_hora_log=timezone.now(),
        )
        return False, _chave_op(pacote)


def processar_pacotes_tempo_erp(ids=None):
    close_old_connections()
    try:
        if not PROCESSAMENTO_TEMPOS_ERP_LOCK.acquire(blocking=False):
            return 0, 0
        with ciclo_service(SERVICE_CODIGO):
            sucessos = erros = 0
            chaves_com_erro = set()
            try:
                while True:
                    pacote_ids = ids or reservar_pacotes_tempo_erp_para_envio(chaves_com_erro)
                    if not pacote_ids:
                        break
                    for pacote_id in pacote_ids:
                        sucesso, chave = _processar_pacote(pacote_id)
                        sucessos += int(sucesso)
                        erros += int(not sucesso)
                        if not sucesso:
                            chaves_com_erro.add(chave)
                    if ids is not None:
                        break
                return sucessos, erros
            finally:
                PROCESSAMENTO_TEMPOS_ERP_LOCK.release()
    finally:
        connections.close_all()


def disparar_envio_tempos_erp(ids=None):
    threading.Thread(target=processar_pacotes_tempo_erp, args=(ids,), daemon=True).start()
