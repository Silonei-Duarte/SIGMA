from django.utils import timezone

from producao.utils.codificacao import safe_str
from setores.qualidade.models.estrutura import WMS_IntegraçãoOP
from SIGMA.segredos import mascarar_segredos


def codder_wms(valor):
    texto = "" if valor is None else str(valor).strip()
    if not texto:
        return None
    try:
        return int(texto)
    except ValueError:
        return None


def montar_sku_wms(codpro, codder):
    produto = str(codpro or "").strip()
    derivacao = str(codder or "").strip()
    return f"{produto}-{derivacao}" if produto and derivacao else produto


def chave_wms_liberacao(registro):
    if (registro.qtdrefu or 0) > 0 or (registro.qtdrecl or 0) > 0:
        codpro = str(registro.codpro_recl or "").strip()
        codder = codder_wms(registro.codder_recl)
    else:
        codpro = str(registro.codpro or "").strip()
        codder = codder_wms(registro.codder)

    return (
        registro.codemp,
        str(registro.codori or ""),
        registro.numorp or 0,
        str(registro.lottrf or registro.codlot or ""),
        codpro,
        codder,
        str(registro.codigo_integrador or ""),
    )


def dados_wms_liberacao_lote(
    registro,
    local="",
    tipo_envio=None,
    quantidade=None,
    codpro=None,
    codder=None,
    lote=None,
    palete=None,
    permitir_quantidade_zero=False,
):
    quantidade = float(
        quantidade
        if quantidade is not None
        else (registro.qtdlibe or registro.qtdrefu or registro.qtdrecl or 0)
    )
    if quantidade <= 0 and not permitir_quantidade_zero:
        raise ValueError("Registro sem quantidade para gerar integração WMS.")

    if codpro is not None:
        codpro = str(codpro or "").strip()
        codder = codder_wms(codder)
    elif (registro.qtdrefu or 0) > 0 or (registro.qtdrecl or 0) > 0:
        codpro = str(registro.codpro_recl or "").strip()
        codder = codder_wms(registro.codder_recl)
    else:
        codpro = str(registro.codpro or "").strip()
        codder = codder_wms(registro.codder)

    if not codpro:
        raise ValueError("Registro sem produto para gerar integração WMS.")

    lote_wms = str(lote if lote is not None else (registro.lottrf or registro.codlot or ""))
    if palete is not None:
        palete_wms = str(palete or "")
    else:
        palete_wms = lote_wms

    return {
        "codemp": registro.codemp,
        "origem": str(registro.codori or ""),
        "op": registro.numorp or 0,
        "lote": lote_wms,
        "palete": palete_wms,
        "quantidade": quantidade,
        "codigo_integrador": str(registro.codigo_integrador or ""),
        "local": str(local or ""),
        "codpro": codpro,
        "codder": codder,
        "tipo_envio": tipo_envio or WMS_IntegraçãoOP.TIPO_NOVO_LOTE,
    }


def criar_integracao_wms_liberacao_lote(registro, local="", tipo_envio=None, **overrides):
    dados = dados_wms_liberacao_lote(registro, local=local, tipo_envio=tipo_envio, **overrides)
    integracao_existente = WMS_IntegraçãoOP.objects.filter(**dados).order_by("-id").first()
    if integracao_existente:
        return integracao_existente, False

    integracao = WMS_IntegraçãoOP.objects.create(
        **dados,
        status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO,
        reuniao=registro.reuniao,
        log=f"Gerado pela integração do lote qualidade #{registro.id}",
        datger=timezone.now(),
    )
    return integracao, True


def criar_pendencia_wms_liberacao_lote(registro, local="", tipo_envio=None, **overrides):
    try:
        criar_integracao_wms_liberacao_lote(
            registro, local=local, tipo_envio=tipo_envio, **overrides
        )
    except Exception as exc:
        # O log vai para tela de consulta: texto de exceção passa pela máscara
        # antes de ser gravado, para não vazar credencial de webservice.
        registro.log = f"{registro.log}\nWMS: {mascarar_segredos(safe_str(exc))}".strip()
        registro.data_hora = timezone.now()
        registro.save(update_fields=["log", "data_hora"])


def criar_pendencia_wms_ajuste_lote_original(registro, local=""):
    return criar_pendencia_wms_liberacao_lote(
        registro,
        local=local,
        tipo_envio=WMS_IntegraçãoOP.TIPO_AJUSTE,
        quantidade=0,
        codpro=registro.codpro,
        codder=registro.codder,
        lote=registro.codlot,
        permitir_quantidade_zero=True,
    )


def remover_pendencia_wms_liberacao_lote(registro):
    try:
        dados = dados_wms_liberacao_lote(registro)
    except Exception:
        return 0
    dados.pop("local", None)
    dados.pop("tipo_envio", None)
    dados.pop("palete", None)

    removidos = WMS_IntegraçãoOP.objects.filter(
        **dados, status=0, reuniao=registro.reuniao
    ).delete()[0]
    removidos += WMS_IntegraçãoOP.objects.filter(
        codemp=registro.codemp,
        origem=str(registro.codori or ""),
        op=registro.numorp or 0,
        lote=str(registro.codlot or ""),
        quantidade=0,
        codigo_integrador=str(registro.codigo_integrador or ""),
        codpro=str(registro.codpro or "").strip(),
        codder=codder_wms(registro.codder),
        tipo_envio=WMS_IntegraçãoOP.TIPO_AJUSTE,
        status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO,
        reuniao=registro.reuniao,
    ).delete()[0]
    return removidos
