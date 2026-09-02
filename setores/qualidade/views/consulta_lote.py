import json
import re
import threading
from datetime import timedelta
from urllib.parse import urlencode
from xml.sax.saxutils import escape

import qrcode
from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import close_old_connections, connections, transaction
from django.db.models import Max, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from qrcode.image.svg import SvgPathImage
from reportlab.graphics import renderSVG
from reportlab.graphics.barcode import createBarcodeDrawing

from producao.services.sapiens import enviar_soap_sapiens
from producao.services.status import ciclo_service, marcar_atividade_service, registrar_service
from producao.utils.codificacao import get_response_text, safe_str
from producao.utils.sapiens_soap import escapar_cdata_sapiens
from setores.qualidade.models import LiberacaoLote
from setores.qualidade.views.liberar_lotes import buscar_recurso_por_codigo
from SIGMA.autorizacao import permissao_requerida
from SIGMA.integracoes.oracle import cursor_oracle_erp
from SIGMA.segredos import mascarar_segredos

PROCESSAMENTO_LOTES_LOCK = threading.Lock()
TEMPO_LIMITE_CICLO_SEGUNDOS = 1800
WEBSERVICE_TIMEOUT_SEGUNDOS = 180
SERVICE_CODIGO = "fila_consulta_lotes"
SERVICE_NOME = "Fila Consulta de Lotes"

registrar_service(
    SERVICE_CODIGO,
    SERVICE_NOME,
    None,
    "Processa a fila assíncrona de consulta/liberação de lotes.",
    TEMPO_LIMITE_CICLO_SEGUNDOS,
)


# Busca os parâmetros de refugo efetivos do recurso ou da filial.
def _parametros_refugo(recurso):
    parametros = recurso.get_parametros_efetivos()
    return (
        str(parametros.get("produto_refugo", "") or ""),
        ""
        if parametros.get("derivacao_refugo") is None
        else str(parametros.get("derivacao_refugo", "")),
    )


# Monta o payload enviado ao webservice de movimentação do ERP.
def montar_dados_webservice_lote(registro):
    if not registro.codemp:
        raise ValueError(
            "Registro sem empresa vinculada. Recrie a destinação do lote para salvar o CODEMP correto."
        )

    recurso = buscar_recurso_por_codigo(registro.codemp, registro.codigo_integrador)
    if not recurso:
        raise ValueError(
            f"Recurso integrador {registro.codigo_integrador} não encontrado para empresa {registro.codemp}."
        )

    filial = recurso.centro_recurso.setor.departamento.filial
    empresa = filial.empresa

    codtns = str(registro.codtns or "")
    if not codtns:
        raise ValueError("Transação ERP não salva no registro.")

    usu_res = getattr(registro.usuario, "idintegracao", None)
    if usu_res in (None, ""):
        raise ValueError(f"Usuário {registro.usuario} sem ID de integração configurado.")

    qtd_liberada = float(registro.qtdlibe or 0)
    qtd_refugada = float(registro.qtdrefu or 0)
    qtd_reclassificada = float(registro.qtdrecl or 0)
    deptrf = str(registro.deptrf or "")
    lot_trf = str(registro.lottrf or "")
    pro_trf = ""
    der_trf = ""

    if qtd_liberada > 0:
        codpro = str(registro.codpro or "")
        codder = "" if registro.codder is None else str(registro.codder)
        qtdmov = qtd_liberada
        destino = "liberação"
    elif qtd_refugada > 0:
        codpro = str(registro.codpro or "")
        codder = "" if registro.codder is None else str(registro.codder)
        pro_trf, der_trf = _parametros_refugo(recurso)
        qtdmov = qtd_refugada
        destino = "refugo"
    elif qtd_reclassificada > 0:
        codpro = str(registro.codpro or "")
        codder = "" if registro.codder is None else str(registro.codder)
        pro_trf = str(registro.codpro_recl or "")
        der_trf = "" if registro.codder_recl is None else str(registro.codder_recl)
        qtdmov = qtd_reclassificada
        destino = "reclassificação"
    else:
        raise ValueError("Linha sem quantidade liberada, refugada ou reclassificada para envio.")

    if not codpro:
        raise ValueError(f"Produto obrigatório para envio de {destino}.")
    if qtd_refugada > 0 and not pro_trf:
        raise ValueError("Produto de transferência obrigatório para envio de refugo.")
    if qtd_reclassificada > 0 and not pro_trf:
        raise ValueError("Produto de transferência obrigatório para envio de reclassificação.")
    if not deptrf:
        raise ValueError(f"Depósito de destino não salvo no registro de {destino}.")

    wacao = (
        "TRANSFERENCIA-PRODUTO"
        if qtd_refugada > 0 or qtd_reclassificada > 0
        else "MOVIMENTAR-ESTOQUE"
    )
    dados = {
        "wacao": wacao,
        "acaoBotao": "A",
        "codEmp": empresa.codemp,
        "codFil": filial.codfil,
        "codPro": codpro,
        "codDer": codder,
        "codDep": str(registro.coddep or ""),
        "codTns": codtns,
        "codLot": str(registro.codlot or ""),
        "lotTrf": lot_trf,
        "numDoc": str(registro.numorp or ""),
        "oriOrp": str(registro.codori or ""),
        "qtdMov": qtdmov,
        "usuRes": usu_res,
        "depTrf": deptrf,
        "proTrf": pro_trf,
        "derTrf": der_trf,
        "coddft": str(registro.coddft or ""),
        "motMvp": f"MOVIMENTO VIA {getattr(settings, 'APPLICATION_NAME', '')}",
    }

    return dados


def retorno_movimentar_estoque_confirmado(dados_retorno):
    """Reconhece o retorno interno de sucesso do MovimentarEstoque."""
    resultado = dados_retorno.get("result") or {}
    retorno_movimento = resultado.get("retornoMovimento") or {}
    return (
        retorno_movimento.get("retorno") == "OK"
        and resultado.get("tipoRetorno") == "1"
        and "processado com sucesso" in str(resultado.get("mensagemRetorno") or "").lower()
        and not resultado.get("erroExecucao")
    )


# Envia um registro de liberação/refugo/reclassificação ao webservice do ERP.
def chamar_webservice_liberacao_lote(registro):
    dados = montar_dados_webservice_lote(registro)
    json_dados = json.dumps(dados, ensure_ascii=False)
    servico = (
        "TransferenciaProduto"
        if (registro.qtdrefu or 0) > 0 or (registro.qtdrecl or 0) > 0
        else "MovimentarEstoque"
    )
    print(f"[LiberacaoLote] Enviando registro {registro.id}: {json_dados}")
    print(f"[LiberacaoLote] Serviço registro {registro.id}: {servico}")
    envelope = f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<soapenv:Envelope xmlns:soapenv="http://www.w3.org/2003/05/soap-envelope"
                  xmlns:ser="http://services.senior.com.br">
  <soapenv:Header/>
  <soapenv:Body>
    <ser:{servico}>
      <user>{escape(str(settings.SAPIENS_USERNAME))}</user>
      <password>{escape(str(settings.SAPIENS_PASSWORD))}</password>
      <encryption>0</encryption>
      <parameters>
        <flowInstanceID></flowInstanceID>
        <flowName></flowName>
        <tabelaEntradas>
            <chave>wdados</chave>
            <valor><![CDATA[{escapar_cdata_sapiens(json_dados)}]]></valor>
        </tabelaEntradas>
      </parameters>
    </ser:{servico}>
  </soapenv:Body>
</soapenv:Envelope>"""
    sapiens_base = getattr(settings, "SAPIENS_URL_BASE", "http://erp01:18080")
    url = f"{sapiens_base}/g5-senior-services/sapiens_Synccustom.senior.man.producao"
    print(f"[LiberacaoLote] POST registro {registro.id}: {url}")

    # validar_status=False: a leitura de waRetorno abaixo decide sucesso/erro,
    # inclusive para HTTP != 200 (mesma resposta de negócio do Sapiens).
    r = enviar_soap_sapiens(
        url, envelope, timeout=WEBSERVICE_TIMEOUT_SEGUNDOS, validar_status=False
    )
    resposta = get_response_text(r)

    log_retorno = resposta
    sucesso = False
    retorno = re.search(r"<waRetorno>(.*?)</waRetorno>", resposta, re.DOTALL)
    if retorno:
        log_retorno = retorno.group(1).strip()
        try:
            dados_retorno = json.loads(log_retorno)
            status_retorno = dados_retorno.get("status")
            sucesso = (
                status_retorno == "OK"
                if status_retorno is not None
                else dados_retorno.get("message") == "OK"
            )
            if not sucesso and servico == "MovimentarEstoque":
                sucesso = retorno_movimentar_estoque_confirmado(dados_retorno)
        except json.JSONDecodeError, TypeError:
            sucesso = "Processado com sucesso" in resposta
    else:
        sucesso = "Processado com sucesso" in resposta or "Processado com Sucesso" in resposta

    # log_retorno normalmente é só o conteúdo de <waRetorno> (JSON de negócio, sem
    # credencial). Só cai para a resposta HTTP inteira quando o Sapiens não devolve essa
    # tag — e alguns SOAP faults ecoam o envelope da requisição no corpo do erro. Mascara
    # por precaução, sem mudar o que é gravado no campo log do registro.
    print(
        f"[LiberacaoLote] Retorno registro {registro.id}: sucesso={sucesso} "
        f"log={mascarar_segredos(log_retorno)}"
    )
    return sucesso, log_retorno


# Reserva registros pendentes com lock transacional para evitar processamento duplicado.
def reservar_lotes_para_envio(queryset):
    with transaction.atomic():
        ids_elegiveis = list(
            queryset.filter(status=LiberacaoLote.Status.NAO_INTEGRADO)
            .order_by("id")
            .values_list("id", flat=True)
        )
        if not ids_elegiveis:
            print("[LiberacaoLote] Reserva solicitada. Nenhum ID elegível encontrado.")
            return []

        ids = list(
            LiberacaoLote.objects.filter(
                id__in=ids_elegiveis, status=LiberacaoLote.Status.NAO_INTEGRADO
            )
            .select_for_update(skip_locked=True)
            .order_by("id")
            .values_list("id", flat=True)
        )
        print(f"[LiberacaoLote] Reserva solicitada. IDs encontrados: {ids}")
        if not ids:
            return []

        LiberacaoLote.objects.filter(id__in=ids, status=LiberacaoLote.Status.NAO_INTEGRADO).update(
            status=LiberacaoLote.Status.PROCESSANDO,
            log="Aguardando processamento background",
            data_hora=timezone.now(),
        )
        print(f"[LiberacaoLote] IDs reservados como Processando: {ids}")
        return ids


def _registrar_resultado_liberacao_lote(registro_id, sucesso, log):
    # Máscara aplicada o mais perto possível da gravação: cobre qualquer chamador,
    # mesmo que a origem do texto mude no futuro e esqueça de mascarar antes.
    log = mascarar_segredos(log)
    agora = timezone.now()
    if sucesso:
        LiberacaoLote.objects.filter(pk=registro_id).update(
            status=LiberacaoLote.Status.INTEGRADO,
            log=log,
            data_hora=agora,
        )
        return True

    atualizados = (
        LiberacaoLote.objects.filter(pk=registro_id)
        .exclude(status=LiberacaoLote.Status.INTEGRADO)
        .update(
            status=LiberacaoLote.Status.NAO_INTEGRADO,
            log=log,
            data_hora=agora,
        )
    )
    return bool(atualizados)


# Processa em background os lotes pendentes ou uma lista específica de IDs.
def processar_lotes_pendentes(ids=None):
    close_old_connections()
    print(f"[LiberacaoLote] Thread iniciada. IDs recebidos: {ids}")
    try:
        if ids is not None and not ids:
            print("[LiberacaoLote] Thread encerrada: lista de IDs vazia.")
            return 0, 0

        if not PROCESSAMENTO_LOTES_LOCK.acquire(blocking=False):
            print("[LiberacaoLote] Thread bloqueada: já existe processamento em andamento.")
            if ids is not None:
                LiberacaoLote.objects.filter(
                    id__in=ids, status=LiberacaoLote.Status.PROCESSANDO
                ).update(
                    status=LiberacaoLote.Status.NAO_INTEGRADO,
                    log="Aguardando processamento background",
                    data_hora=timezone.now(),
                )
            return 0, 0

        with ciclo_service(SERVICE_CODIGO):
            sucessos = 0
            falhas = 0
            ids_tentados_no_ciclo = set()
            try:
                while True:
                    reservados_ids = ids
                    if ids is None:
                        queryset_pendentes = LiberacaoLote.objects.order_by("id")
                        if ids_tentados_no_ciclo:
                            queryset_pendentes = queryset_pendentes.exclude(
                                id__in=ids_tentados_no_ciclo
                            )
                        reservados_ids = reservar_lotes_para_envio(queryset_pendentes)

                    if not reservados_ids:
                        print("[LiberacaoLote] Nenhum registro reservado para processar.")
                        break

                    ids_tentados_no_ciclo.update(reservados_ids)
                    registros = (
                        LiberacaoLote.objects.filter(
                            id__in=reservados_ids,
                            status=LiberacaoLote.Status.PROCESSANDO,
                        )
                        .select_related(
                            "usuario",
                            "reuniao",
                        )
                        .order_by("id")
                    )
                    print(
                        f"[LiberacaoLote] Registros em Processando localizados: {list(registros.values_list('id', flat=True))}"
                    )

                    for registro in registros:
                        try:
                            marcar_atividade_service(SERVICE_CODIGO, WEBSERVICE_TIMEOUT_SEGUNDOS)
                            print(f"[LiberacaoLote] Processando registro {registro.id}.")
                            sucesso, log = chamar_webservice_liberacao_lote(registro)
                            _registrar_resultado_liberacao_lote(registro.id, sucesso, log)
                            if sucesso:
                                sucessos += 1
                            else:
                                falhas += 1
                        except Exception as exc:
                            print(
                                f"[LiberacaoLote] Erro no registro {registro.id}: {safe_str(exc)}"
                            )
                            _registrar_resultado_liberacao_lote(registro.id, False, safe_str(exc))
                            falhas += 1

                    if ids is not None:
                        break
            finally:
                PROCESSAMENTO_LOTES_LOCK.release()
                print(f"[LiberacaoLote] Thread finalizada. Sucessos={sucessos} Falhas={falhas}")

            return sucessos, falhas
    finally:
        connections.close_all()


# Dispara uma thread daemon para envio dos lotes ao ERP.
def disparar_envio_lotes(ids=None):
    print(f"[LiberacaoLote] Disparando thread para IDs: {ids}")
    threading.Thread(target=processar_lotes_pendentes, args=(ids,), daemon=True).start()


# Libera registros que ficaram presos após timeout da thread da fila.
def liberar_lotes_processando_antigos(idade_segundos=None):
    queryset = LiberacaoLote.objects.filter(
        status=LiberacaoLote.Status.PROCESSANDO,
    )
    if idade_segundos is not None:
        queryset = queryset.filter(data_hora__lt=timezone.now() - timedelta(seconds=idade_segundos))

    return queryset.update(
        status=LiberacaoLote.Status.NAO_INTEGRADO,
        log="Processamento anterior interrompido. Disponível para novo envio.",
        data_hora=timezone.now(),
    )


# Consulta no ERP a descrição do produto e derivação usada na etiqueta.
def _descricao_produto_etiqueta(codemp, codpro, codder):
    if not codemp or not codpro:
        return "-"

    try:
        with cursor_oracle_erp() as cursor:
            cursor.execute(
                """
                    SELECT descricao
                    FROM (
                        SELECT
                            p.codpro,
                            NVL(d.codder, '') AS codder,
                            p.despro || CASE
                                WHEN d.codder IS NOT NULL THEN ' - ' || d.desder
                                ELSE ''
                            END AS descricao
                        FROM e075pro p
                        LEFT JOIN e075der d
                          ON d.codemp = p.codemp
                         AND d.codpro = p.codpro
                        WHERE p.codemp = :codemp
                          AND UPPER(p.codpro) = :codpro
                          AND NVL(d.codder, '') = :codder
                        ORDER BY p.codpro, d.codder
                    )
                    WHERE ROWNUM <= 1
                """,
                {
                    "codemp": int(codemp),
                    "codpro": str(codpro).upper(),
                    "codder": "" if codder in (None, "-") else str(codder),
                },
            )
            row = cursor.fetchone()
            if row:
                row = dict(
                    zip((coluna[0].lower() for coluna in cursor.description), row, strict=False)
                )
            return row["descricao"] if row and row["descricao"] else "-"
    except Exception:
        return "-"


def _lote_barcode_8_digitos(lote):
    return str(lote or "").strip().zfill(8)


# Gera o código de barras Code128 do lote em SVG embutível no HTML.
def _barcode_svg_lote(lote):
    barcode = createBarcodeDrawing(
        "Code128",
        value=_lote_barcode_8_digitos(lote),
        barHeight=56,
        barWidth=1.35,
        humanReadable=False,
    )
    svg = renderSVG.drawToString(barcode)
    svg = svg.replace('preserveAspectRatio="xMinYMin meet"', 'preserveAspectRatio="none"')
    inicio_svg = svg.find("<svg")
    return svg[inicio_svg:] if inicio_svg >= 0 else svg


def _qrcode_svg_url(url):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=1,
        image_factory=SvgPathImage,
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image().to_string(encoding="unicode")


# Valida no ERP se o lote ainda possui saldo no depósito transferido.
def _validar_saldo_para_etiqueta(registro):
    lote = str(registro.lottrf or registro.codlot or "").strip()
    deposito = str(registro.deptrf or "").strip()
    if not registro.codemp or not lote or not deposito:
        return False, "Registro sem empresa, lote ou depósito transferido para validar a impressão."

    quantidade_linha = float(registro.qtdlibe or registro.qtdrecl or registro.qtdrefu or 0)
    if quantidade_linha <= 0:
        return False, f"Registro do lote {lote} sem quantidade para validar a impressão."

    try:
        with cursor_oracle_erp() as cursor:
            cursor.execute(
                """
                    SELECT NVL(SUM(DLS.QTDEST), 0) saldo
                    FROM E210DLS DLS
                    WHERE DLS.CODEMP = :codemp
                      AND DLS.CODLOT = :codlot
                      AND DLS.CODDEP = :coddep
                """,
                {
                    "codemp": int(registro.codemp),
                    "codlot": lote,
                    "coddep": deposito,
                },
            )
            row = cursor.fetchone()
            if row:
                row = dict(
                    zip((coluna[0].lower() for coluna in cursor.description), row, strict=False)
                )
            saldo = float(row["saldo"] or 0) if row else 0
    except Exception as exc:
        return False, f"Erro ao consultar saldo do lote no ERP: {safe_str(exc)}"

    if saldo < quantidade_linha:
        quantidade_texto = (
            f"{quantidade_linha:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        saldo_texto = f"{saldo:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return False, (
            f"Lote {lote} com saldo insuficiente no depósito {deposito}. "
            f"Saldo atual: {saldo_texto} KG. Quantidade da linha: {quantidade_texto} KG."
        )

    return True, ""


# Consolida todos os dados necessários para renderizar uma etiqueta.
def _contexto_etiqueta(request, registro):
    data_avaliacao = registro.datger
    data_fechamento = (
        timezone.localtime(data_avaliacao).strftime("%d/%m/%Y %H:%M") if data_avaliacao else "-"
    )
    if (registro.qtdlibe or 0) > 0:
        destino = "LIBERADA"
    elif (registro.qtdrecl or 0) > 0:
        destino = "RECLASSIFICADA"
    elif (registro.qtdrefu or 0) > 0:
        destino = "REFUGADA"
    else:
        destino = "-"

    if (registro.qtdrefu or 0) > 0 or (registro.qtdrecl or 0) > 0:
        produto = str(registro.codpro_recl or "-")
        derivacao = str(registro.codder_recl or "-")
    else:
        produto = str(registro.codpro or "-")
        derivacao = str(registro.codder or "-")

    quantidade = registro.qtdlibe or registro.qtdrefu or registro.qtdrecl or 0
    quantidade_formatada = (
        f"{float(quantidade):,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    lote = str(registro.lottrf or registro.codlot or "-")
    tem_bobina = registro.numbob not in (None, 0)
    descricao_produto = _descricao_produto_etiqueta(registro.codemp, produto, derivacao)
    recurso = buscar_recurso_por_codigo(registro.codemp, registro.codigo_integrador)
    codigo_recurso = (
        str(recurso.codigo or registro.codigo_integrador or "-")
        if recurso
        else str(registro.codigo_integrador or "-")
    )
    url_rastreamento = request.build_absolute_uri(
        reverse("qualidade:rastreamento_lote")
        + "?"
        + urlencode({"codemp": registro.codemp, "codlot": lote})
    )
    return {
        "registro": registro,
        "origem": registro.codori or "-",
        "op": registro.numorp or "-",
        "data_fechamento": data_fechamento,
        "recurso": codigo_recurso,
        "tem_bobina": tem_bobina,
        "quantidade": quantidade_formatada,
        "produto": produto,
        "derivacao": derivacao,
        "descricao": descricao_produto,
        "observacao_etiqueta": registro.etiqueta.descricao if registro.etiqueta else "-",
        "destino": destino,
        "lote": lote,
        "barcode_svg": _barcode_svg_lote(lote),
        "rastreamento_url": url_rastreamento,
        "rastreamento_qr_svg": _qrcode_svg_url(url_rastreamento),
    }


# Abre a etiqueta individual de uma linha integrada, validando saldo antes da impressão.
@permissao_requerida("qualidade.pode_acessar_area_vermelha")
def imprimir_etiqueta_lote(request, registro_id):
    registro = (
        LiberacaoLote.objects.select_related("reuniao", "etiqueta")
        .filter(pk=registro_id, status=LiberacaoLote.Status.INTEGRADO)
        .first()
    )
    if not registro:
        return HttpResponse("Registro não encontrado ou ainda não integrado.", status=404)

    filial_logada = getattr(request.user, "filial", None)
    empresa_logada = getattr(filial_logada, "empresa", None)
    codemp_usuario = getattr(empresa_logada, "codemp", None)
    if not request.user.is_staff and registro.codemp != codemp_usuario:
        return HttpResponse("Acesso negado.", status=403)

    saldo_ok, mensagem_saldo = _validar_saldo_para_etiqueta(registro)
    if request.GET.get("validar") == "1":
        return JsonResponse({"ok": saldo_ok, "message": mensagem_saldo})
    if not saldo_ok:
        return HttpResponse(mensagem_saldo, status=409)

    context = {
        "titulo": f"Etiqueta {registro.lottrf or registro.codlot}",
        "etiquetas": [_contexto_etiqueta(request, registro)],
    }
    return render(request, "setores/qualidade/etiqueta_lote.html", context)


# Abre um único arquivo com todas as etiquetas integradas do grupo selecionado.
@permissao_requerida("qualidade.pode_acessar_area_vermelha")
def imprimir_etiquetas_grupo(request):
    try:
        codemp = int(request.GET.get("codemp"))
    except TypeError, ValueError:
        return HttpResponse("Empresa inválida.", status=400)

    filial_logada = getattr(request.user, "filial", None)
    empresa_logada = getattr(filial_logada, "empresa", None)
    codemp_usuario = getattr(empresa_logada, "codemp", None)
    if not request.user.is_staff and codemp != codemp_usuario:
        return HttpResponse("Acesso negado.", status=403)

    registros = (
        LiberacaoLote.objects.select_related("reuniao", "etiqueta")
        .filter(
            codemp=codemp,
            codlot=request.GET.get("codlot", ""),
            codpro=request.GET.get("codpro", ""),
            codder=request.GET.get("codder", ""),
            status=LiberacaoLote.Status.INTEGRADO,
        )
        .order_by("id")
    )
    registros = list(registros)
    if not registros:
        return HttpResponse("Nenhuma etiqueta integrada encontrada para este lote.", status=404)

    sem_saldo = []
    for registro in registros:
        saldo_ok, mensagem_saldo = _validar_saldo_para_etiqueta(registro)
        if not saldo_ok:
            sem_saldo.append(mensagem_saldo)

    if request.GET.get("validar") == "1":
        return JsonResponse(
            {
                "ok": not sem_saldo,
                "message": "\n".join(sem_saldo),
            }
        )

    if sem_saldo:
        return HttpResponse(
            "Etiqueta não liberada para impressão:\n" + "\n".join(sem_saldo), status=409
        )

    etiquetas = [_contexto_etiqueta(request, registro) for registro in registros]

    return render(
        request,
        "setores/qualidade/etiqueta_lote.html",
        {
            "titulo": f"Etiquetas {request.GET.get('codlot', '')}",
            "etiquetas": etiquetas,
        },
    )


# Lista e controla os registros locais de destinação de lotes para integração e impressão.
@permissao_requerida(
    ("qualidade.pode_acessar_area_vermelha", "qualidade.pode_acessar_liberacao_lotes")
)
def consulta_lote(request):
    search_query = (request.GET.get("search") or "").strip()
    status = request.GET.get("status", "")
    page_number = request.GET.get("page", "")
    filial_logada = getattr(request.user, "filial", None)
    empresa_logada = getattr(filial_logada, "empresa", None)
    codemp_usuario = getattr(empresa_logada, "codemp", None)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "enviar_todos":
            if PROCESSAMENTO_LOTES_LOCK.locked():
                messages.warning(
                    request, "Já existe um processamento de lotes em background em andamento."
                )
                return redirect("qualidade:consulta_lote")

            pendentes = LiberacaoLote.objects.filter(
                status=LiberacaoLote.Status.NAO_INTEGRADO,
            ).order_by("id")
            pendentes = pendentes.filter(
                Q(reuniao__isnull=True) | Q(reuniao__data_hora_fim__isnull=False)
            )
            if not request.user.is_staff and codemp_usuario:
                pendentes = pendentes.filter(codemp=codemp_usuario)
            elif not request.user.is_staff:
                pendentes = pendentes.none()
            if not pendentes.exists():
                messages.info(request, "Não há lotes pendentes para enviar.")
                return redirect("qualidade:consulta_lote")

            reservados_ids = reservar_lotes_para_envio(pendentes)
            if not reservados_ids:
                messages.warning(request, "Nenhum lote está disponível para envio.")
                return redirect("qualidade:consulta_lote")

            disparar_envio_lotes(reservados_ids)
            messages.info(
                request, "Processamento em background iniciado para envio dos lotes pendentes."
            )
        elif action == "enviar_grupo":
            if PROCESSAMENTO_LOTES_LOCK.locked():
                messages.warning(request, "Já existe um processamento de lotes em andamento.")
                return redirect("qualidade:consulta_lote")

            try:
                codemp = int(request.POST.get("codemp"))
            except TypeError, ValueError:
                messages.error(request, "Dados inválidos para enviar o lote.")
            else:
                lotes_para_enviar = LiberacaoLote.objects.filter(
                    codemp=codemp,
                    codlot=request.POST.get("codlot", ""),
                    codpro=request.POST.get("codpro", ""),
                    codder=request.POST.get("codder", ""),
                    status=LiberacaoLote.Status.NAO_INTEGRADO,
                )
                lotes_para_enviar = lotes_para_enviar.filter(
                    Q(reuniao__isnull=True) | Q(reuniao__data_hora_fim__isnull=False)
                )
                if not request.user.is_staff and codemp_usuario:
                    lotes_para_enviar = lotes_para_enviar.filter(codemp=codemp_usuario)
                elif not request.user.is_staff:
                    lotes_para_enviar = lotes_para_enviar.none()

                reservados_ids = reservar_lotes_para_envio(lotes_para_enviar)
                if not reservados_ids:
                    messages.warning(
                        request, "Lote não encontrado, já integrado ou em processamento."
                    )
                    return redirect("qualidade:consulta_lote")

                disparar_envio_lotes(reservados_ids)
                messages.info(
                    request, "Processamento em background iniciado para o lote selecionado."
                )
        elif action == "enviar_registro":
            if PROCESSAMENTO_LOTES_LOCK.locked():
                messages.warning(request, "Já existe um processamento de lotes em andamento.")
                return redirect("qualidade:consulta_lote")

            try:
                registro_id = int(request.POST.get("registro_id"))
            except TypeError, ValueError:
                messages.error(request, "Registro inválido para envio.")
                return redirect("qualidade:consulta_lote")

            lote_para_enviar = LiberacaoLote.objects.filter(
                pk=registro_id,
                status=LiberacaoLote.Status.NAO_INTEGRADO,
            )
            lote_para_enviar = lote_para_enviar.filter(
                Q(reuniao__isnull=True) | Q(reuniao__data_hora_fim__isnull=False)
            )
            if not request.user.is_staff and codemp_usuario:
                lote_para_enviar = lote_para_enviar.filter(codemp=codemp_usuario)
            elif not request.user.is_staff:
                lote_para_enviar = lote_para_enviar.none()

            reservados_ids = reservar_lotes_para_envio(lote_para_enviar)
            if not reservados_ids:
                messages.warning(
                    request, "Registro não encontrado, já integrado ou em processamento."
                )
                return redirect("qualidade:consulta_lote")

            disparar_envio_lotes(reservados_ids)
            messages.info(
                request, f"Processamento em background iniciado para o registro {registro_id}."
            )
        elif action == "excluir_grupo":
            if not request.user.is_superuser:
                messages.error(request, "Você não possui permissão para excluir registros.")
                return redirect("qualidade:consulta_lote")

            try:
                codemp = int(request.POST.get("codemp"))
            except TypeError, ValueError:
                messages.error(request, "Dados inválidos para excluir o lote.")
            else:
                total_grupo = LiberacaoLote.objects.filter(
                    codemp=codemp,
                    codlot=request.POST.get("codlot", ""),
                    codpro=request.POST.get("codpro", ""),
                    codder=request.POST.get("codder", ""),
                ).count()
                excluidos, _ = LiberacaoLote.objects.filter(
                    codemp=codemp,
                    codlot=request.POST.get("codlot", ""),
                    codpro=request.POST.get("codpro", ""),
                    codder=request.POST.get("codder", ""),
                    status__in=[LiberacaoLote.Status.NAO_INTEGRADO, LiberacaoLote.Status.LOCAL],
                ).delete()
                if excluidos and excluidos == total_grupo:
                    messages.success(request, "Lote excluído.")
                elif excluidos:
                    messages.warning(request, "Somente registros não integrados foram excluídos.")
                else:
                    messages.warning(request, "Lote não encontrado ou já integrado.")
        return redirect("qualidade:consulta_lote")

    registros = LiberacaoLote.objects.all()
    if not request.user.is_staff:
        registros = registros.filter(codemp=codemp_usuario)

    if search_query:
        filtro_busca = (
            Q(codlot__icontains=search_query)
            | Q(lottrf__icontains=search_query)
            | Q(codpro__icontains=search_query)
            | Q(codder__icontains=search_query)
            | Q(coddep__icontains=search_query)
            | Q(codpro_recl__icontains=search_query)
            | Q(codder_recl__icontains=search_query)
            | Q(coddft__icontains=search_query)
            | Q(etiqueta__descricao__icontains=search_query)
            | Q(observacao_geral__icontains=search_query)
            | Q(codori__icontains=search_query)
            | Q(deptrf__icontains=search_query)
            | Q(log__icontains=search_query)
            | Q(usuario__username__icontains=search_query)
            | Q(usuario__first_name__icontains=search_query)
            | Q(usuario__last_name__icontains=search_query)
        )
        if search_query.isdigit():
            filtro_busca |= (
                Q(codemp=int(search_query))
                | Q(numbob=int(search_query))
                | Q(numorp=int(search_query))
                | Q(codigo_integrador__icontains=search_query)
            )
        registros = registros.filter(filtro_busca)

    if status in {"0", "1", "2"}:
        registros = registros.filter(status=int(status))

    def formatar_participantes(reuniao):
        if not reuniao:
            return ""
        participantes = []
        for participante in reuniao.participantes.all():
            setor = participante.get_setor_display()
            participantes.append(f"{participante.nome} - {setor}" if setor else participante.nome)
        return "||".join(participantes)

    # Pagina os grupos no banco. Carregar todos os registros para agrupá-los em
    # Python fazia a tela crescer linearmente com o histórico inteiro.
    campos_grupo = ("codemp", "numbob", "codlot", "codpro", "codder")
    grupos_base = (
        registros.values(*campos_grupo).annotate(ultimo_id=Max("id")).order_by("-ultimo_id")
    )
    paginator = Paginator(grupos_base, 20)
    grupos_page = paginator.get_page(page_number)

    filtro_grupos_pagina = Q()
    for chave in grupos_page.object_list:
        filtro_chave = Q(codemp=chave["codemp"], codlot=chave["codlot"], codpro=chave["codpro"])
        for campo in ("numbob", "codder"):
            valor = chave[campo]
            filtro_chave &= (
                Q(**{f"{campo}__isnull": True}) if valor is None else Q(**{campo: valor})
            )
        filtro_grupos_pagina |= filtro_chave

    registros_pagina = (
        (
            registros.filter(filtro_grupos_pagina)
            .select_related("usuario", "reuniao", "etiqueta")
            .prefetch_related("reuniao__participantes")
            .order_by("-id")
        )
        if filtro_grupos_pagina
        else registros.none()
    )

    grupos_por_chave = {}
    for chave in grupos_page.object_list:
        chave_grupo = tuple(chave[campo] for campo in campos_grupo)
        grupos_por_chave[chave_grupo] = {"registros": []}

    for registro in registros_pagina:
        chave = (
            registro.codemp,
            registro.numbob,
            registro.codlot,
            registro.codpro,
            registro.codder,
        )
        if len(grupos_por_chave[chave]) == 1:
            participantes_reuniao = formatar_participantes(registro.reuniao)
            grupo = {
                "codemp": registro.codemp,
                "numbob": registro.numbob,
                "codlot": registro.codlot,
                "codpro": registro.codpro,
                "codder": registro.codder,
                "codori": registro.codori,
                "numorp": registro.numorp,
                "coddep": registro.coddep,
                "deptrf": registro.deptrf,
                "qtdtot": registro.qtdtot,
                "total_libe": 0,
                "total_refu": 0,
                "total_recl": 0,
                "total_prensa": 0,
                "status": registro.get_status_display(),
                "data_hora": registro.data_hora,
                "data_hora_inicio_reuniao": registro.reuniao.data_hora_inicio
                if registro.reuniao
                else None,
                "data_hora_fim_reuniao": registro.reuniao.data_hora_fim
                if registro.reuniao
                else None,
                "participantes_reuniao": participantes_reuniao,
                "codigo_integrador": registro.codigo_integrador,
                "usuario": registro.usuario,
                "pode_excluir": True,
                "tem_pendente": False,
                "tem_pendente_enviavel": False,
                "tem_processando": False,
                "tem_integrado": False,
                "tem_local": False,
                "logs": [],
                "motivos": [],
                "observacoes_etiqueta": [],
                "observacoes_gerais": [],
                "observacoes_texto": "",
                "registros": [],
            }
            grupos_por_chave[chave] = grupo

        grupo = grupos_por_chave[chave]
        registro.participantes_reuniao = formatar_participantes(registro.reuniao)
        grupo["total_libe"] += registro.qtdlibe or 0
        grupo["total_refu"] += registro.qtdrefu or 0
        grupo["total_recl"] += registro.qtdrecl or 0
        grupo["total_prensa"] += registro.qtdprensa or 0
        if registro.log and registro.log not in grupo["logs"]:
            grupo["logs"].append(registro.log)
        if registro.coddft and registro.coddft not in grupo["motivos"]:
            grupo["motivos"].append(registro.coddft)
        observacao_etiqueta = registro.etiqueta.descricao if registro.etiqueta else ""
        registro.observacao_etiqueta_texto = observacao_etiqueta
        if observacao_etiqueta and observacao_etiqueta not in grupo["observacoes_etiqueta"]:
            grupo["observacoes_etiqueta"].append(observacao_etiqueta)
        if (
            registro.observacao_geral
            and registro.observacao_geral not in grupo["observacoes_gerais"]
        ):
            grupo["observacoes_gerais"].append(registro.observacao_geral)
        if registro.status not in (LiberacaoLote.Status.NAO_INTEGRADO, LiberacaoLote.Status.LOCAL):
            grupo["pode_excluir"] = False
        if registro.status == LiberacaoLote.Status.NAO_INTEGRADO:
            grupo["tem_pendente"] = True
            if not registro.reuniao or registro.reuniao.data_hora_fim:
                grupo["tem_pendente_enviavel"] = True
        elif registro.status == LiberacaoLote.Status.PROCESSANDO:
            grupo["tem_processando"] = True
        elif registro.status == LiberacaoLote.Status.INTEGRADO:
            grupo["tem_integrado"] = True
        elif registro.status == LiberacaoLote.Status.LOCAL:
            grupo["tem_local"] = True
        grupo["registros"].append(registro)

    grupos = [
        grupos_por_chave[tuple(chave[campo] for campo in campos_grupo)]
        for chave in grupos_page.object_list
    ]
    for grupo in grupos:
        observacoes = []
        if grupo["observacoes_etiqueta"]:
            observacoes.append(
                "Obs. etiqueta:\n" + "\n".join(f"- {obs}" for obs in grupo["observacoes_etiqueta"])
            )
        if grupo["observacoes_gerais"]:
            observacoes.append(
                "Obs. geral:\n" + "\n".join(f"- {obs}" for obs in grupo["observacoes_gerais"])
            )
        grupo["observacoes_texto"] = "\n\n".join(observacoes) or "Nenhuma observação registrada."
        if grupo["tem_processando"]:
            grupo["status"] = dict(LiberacaoLote.Status.choices)[LiberacaoLote.Status.PROCESSANDO]
        elif grupo["tem_pendente"]:
            grupo["status"] = dict(LiberacaoLote.Status.choices)[LiberacaoLote.Status.NAO_INTEGRADO]
        elif grupo["tem_integrado"]:
            grupo["status"] = dict(LiberacaoLote.Status.choices)[LiberacaoLote.Status.INTEGRADO]
        elif grupo["tem_local"]:
            grupo["status"] = dict(LiberacaoLote.Status.choices)[LiberacaoLote.Status.LOCAL]

    grupos_page.object_list = grupos

    context = {
        "titulo": "Consulta de Lotes",
        "grupos_lotes": grupos_page,
        "search_query": search_query,
        "status": status,
        "status_choices": LiberacaoLote.Status.choices,
        "pode_enviar": True,
        "pode_excluir": request.user.is_superuser,
    }
    return render(request, "setores/qualidade/consulta_lotes.html", context)
