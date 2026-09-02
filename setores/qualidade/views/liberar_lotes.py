import json
import logging
from decimal import Decimal, InvalidOperation
from xml.sax.saxutils import escape

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import Recurso
from producao.services.altera_apontamento import post_soap_sapiens
from producao.utils.sapiens_soap import escapar_cdata_sapiens
from setores.qualidade.models import LiberacaoLote
from setores.qualidade.utils.wms_integracao import criar_pendencia_wms_liberacao_lote
from SIGMA.autorizacao import permissao_requerida
from SIGMA.integracoes.oracle import cursor_oracle_alchemy, cursor_oracle_erp

logger = logging.getLogger(__name__)


def separar_origens_area_vermelha(valor):
    return [origem.strip().upper() for origem in str(valor or "").split(",") if origem.strip()]


def carregar_analises_alchemy(bobinas_pagina):
    grupos = {}
    for bobina in bobinas_pagina:
        codbobina = bobina.get("usu_numbob")
        codmaquina = bobina.get("codmaquina_alchemy")
        if codbobina and codmaquina:
            grupos.setdefault(codmaquina, set()).add(int(codbobina))

    if not grupos:
        return {}

    clausulas = []
    params = {}

    for indice_grupo, (codmaquina, codbobinas) in enumerate(grupos.items()):
        placeholders = []
        for indice_bobina, codbobina in enumerate(sorted(codbobinas)):
            nome_param = f"bob_{indice_grupo}_{indice_bobina}"
            params[nome_param] = codbobina
            placeholders.append(f":{nome_param}")

        nome_maquina = f"maq_{indice_grupo}"
        params[nome_maquina] = codmaquina
        clausulas.append(
            f"(b.codmaquina = :{nome_maquina} AND b.codbobina IN ({', '.join(placeholders)}))"
        )

    sql = f"""
        SELECT b.codmaquina, b.codbobina, b.flagproducao
        FROM bobinas b
        WHERE {" OR ".join(clausulas)}
    """

    analises = {}
    with cursor_oracle_alchemy() as cursor:
        cursor.execute(sql, params)
        for codmaquina, codbobina, flagproducao in cursor.fetchall():
            analises[(int(codmaquina), int(codbobina))] = (
                int(flagproducao) if flagproducao is not None else None
            )

    return analises


def carregar_depositos_consulta(filial):
    depositos = set()
    parametros_filial = getattr(filial, "parametros_filial", None)
    deposito_filial = getattr(parametros_filial, "deposito_apontamento_erp", "") or ""
    if deposito_filial:
        depositos.add(deposito_filial.strip())

    depositos_recursos = (
        Recurso.objects.filter(centro_recurso__setor__departamento__filial=filial)
        .exclude(centro_recurso__parametros_centro_recurso__deposito_apontamento_erp__isnull=True)
        .exclude(centro_recurso__parametros_centro_recurso__deposito_apontamento_erp__exact="")
        .values_list(
            "centro_recurso__parametros_centro_recurso__deposito_apontamento_erp", flat=True
        )
    )
    for deposito in depositos_recursos:
        if deposito:
            depositos.add(str(deposito).strip())

    return sorted(depositos)


def buscar_recurso_por_codigo(codemp, codigo_recurso):
    if not codemp or not codigo_recurso:
        return None

    codigo_recurso = str(codigo_recurso).strip()
    return (
        Recurso.objects.select_related(
            "parametros_recurso",
            "centro_recurso__parametros_centro_recurso",
            "centro_recurso__setor__departamento__filial__parametros_filial",
        )
        .filter(
            centro_recurso__codigo_integrador=codigo_recurso,
            centro_recurso__setor__departamento__filial__empresa__codemp=codemp,
        )
        .first()
    )


def validar_lote_pendente_erp(codemp_usuario, selected_row):
    """Valida a situação do lote no ERP sempre pela empresa real do usuário.

    Achado de segurança: antes, `codemp` vinha de `selected_row["codemp"]` (POST
    cru, sem nenhum fallback). Um usuário com permissão de destinar lotes
    conseguia forjar a empresa e validar/mover lote de uma filial que não era a
    sua. `codemp_usuario` é sempre resolvido pela view a partir de
    `request.user.filial.empresa.codemp`, nunca do formulário.
    """
    if not codemp_usuario:
        return False, "Usuário sem empresa vinculada para validar a situação do lote."

    with cursor_oracle_erp() as cursor:
        cursor.execute(
            """
                SELECT USU_SITLOT
                FROM E210DLS
                WHERE CODEMP = :codemp
                  AND CODLOT = :codlot
                  AND CODDEP = :coddep
                  AND CODPRO = :codpro
                  AND CODDER = :codder
                  AND ROWNUM = 1
            """,
            {
                "codemp": codemp_usuario,
                "codlot": selected_row.get("codlot", ""),
                "coddep": selected_row.get("coddep", ""),
                "codpro": selected_row.get("codpro", ""),
                "codder": selected_row.get("codder", ""),
            },
        )
        row = cursor.fetchone()
        if row:
            row = dict(zip((coluna[0].lower() for coluna in cursor.description), row, strict=False))

    if not row:
        return False, "Lote não encontrado no ERP para validar a situação."

    situacao = str(row["usu_sitlot"] or "").strip().upper()
    if situacao not in ("P", ""):
        return False, f"Lote não está pendente no ERP. Situação atual: {situacao or '-'}."

    return True, ""


def obter_parametros_liberacao(request, selected_row):
    filial = getattr(request.user, "filial", None)
    empresa = getattr(filial, "empresa", None)
    parametros_filial = getattr(filial, "parametros_filial", None)
    # Achado de segurança: `codemp` vinha de `selected_row["codemp"]` (POST cru)
    # com prioridade sobre a empresa real do usuário — um `codemp` forjado
    # sobrescrevia a empresa usada para gravar o registro local e montar o
    # envelope enviado ao ERP/WMS. A tela só lista lotes da empresa do próprio
    # usuário (não há seleção de empresa nem bypass de staff na consulta),
    # então a empresa efetiva é sempre a do usuário autenticado.
    codemp = getattr(empresa, "codemp", None)
    codfil = getattr(filial, "codfil", None)
    codtns = getattr(parametros_filial, "codtns", "") if parametros_filial else ""

    if not codemp or not codfil:
        return False, "Usuário sem empresa/filial vinculada.", {}
    if not codtns:
        return (
            False,
            "Parâmetro de filial 'Transação de ERP Saída por Transferência Interna' não configurado.",
            {},
        )

    recurso = buscar_recurso_por_codigo(codemp, selected_row.get("codcre"))
    parametros_recurso = recurso.get_parametros_efetivos() if recurso else None

    deptrf_destino = (parametros_recurso or {}).get("deposito_armazenamento_erp") or getattr(
        parametros_filial, "deposito_armazenamento_erp", ""
    )
    local_wms = (
        (parametros_recurso or {}).get("deposito_armazenamento_wms")
        or getattr(parametros_filial, "deposito_armazenamento_wms", "")
        or ""
    )

    if not deptrf_destino:
        return False, "Depósito de destino não configurado para a ação selecionada.", {}
    if not local_wms:
        return False, "Local WMS não definido. Configure o local no recurso ou na filial.", {}

    return (
        True,
        "",
        {
            "codemp": int(codemp),
            "deptrf": deptrf_destino,
            "codtns": str(codtns),
            "local": str(local_wms),
        },
    )


def carregar_locais_armazenamento_wms(bobinas, filial):
    parametros_filial = getattr(filial, "parametros_filial", None)
    local_filial = str(getattr(parametros_filial, "deposito_armazenamento_wms", "") or "").strip()
    codigos = {
        str(bobina.get("codcre") or "").strip()
        for bobina in bobinas
        if str(bobina.get("codcre") or "").strip()
    }
    locais = {}

    if not filial or not codigos:
        return locais, local_filial

    recursos = Recurso.objects.filter(
        centro_recurso__setor__departamento__filial=filial,
        centro_recurso__codigo_integrador__in=codigos,
    ).select_related(
        "parametros_recurso",
        "centro_recurso__parametros_centro_recurso",
        "centro_recurso__setor__departamento__filial__parametros_filial",
        "centro_recurso__setor__departamento__filial__empresa",
    )
    for recurso in recursos:
        codemp = recurso.centro_recurso.setor.departamento.filial.empresa.codemp
        codigo = str(recurso.centro_recurso.codigo_integrador or "").strip()
        locais[(str(codemp), codigo)] = str(
            recurso.get_parametros_efetivos().get("deposito_armazenamento_wms") or ""
        ).strip()

    return locais, local_filial


def salvar_liberacao_lote_pendente(request, selected_row):
    ok, mensagem, parametros = obter_parametros_liberacao(request, selected_row)
    if not ok:
        return False, mensagem

    try:
        numbob_raw = selected_row.get("usu_numbob")
        numbob = int(numbob_raw) if numbob_raw not in (None, "") else None
        qtdest = float(str(selected_row.get("qtdest") or "0").replace(",", "."))
        numorp = (
            int(selected_row.get("numorp"))
            if selected_row.get("numorp") not in (None, "")
            else None
        )
    except TypeError, ValueError:
        return False, "Dados inválidos para salvar a liberação do lote."

    if qtdest <= 0:
        return False, "Quantidade inválida para salvar a liberação do lote."

    existe = LiberacaoLote.objects.filter(
        codemp=parametros["codemp"],
        codlot=selected_row.get("codlot", ""),
        codpro=selected_row.get("codpro", ""),
        codder=selected_row.get("codder", ""),
    ).exists()
    if existe:
        return False, "Este lote/bobina já possui registro local para integração."

    registro = LiberacaoLote.objects.create(
        codemp=parametros["codemp"],
        numbob=numbob,
        codpro=selected_row.get("codpro", ""),
        codder=selected_row.get("codder", ""),
        coddep=selected_row.get("coddep", ""),
        deptrf=parametros["deptrf"],
        codtns=parametros["codtns"],
        codigo_integrador=selected_row.get("codcre", ""),
        codlot=selected_row.get("codlot", ""),
        lottrf=selected_row.get("codlot", ""),
        codori=selected_row.get("codori", ""),
        numorp=numorp,
        qtdtot=qtdest,
        qtdlibe=qtdest,
        usuario=request.user,
        status=LiberacaoLote.Status.NAO_INTEGRADO,
        datger=timezone.now(),
        log="Inserido Registro",
    )
    from setores.qualidade.views.consulta_lote import (
        disparar_envio_lotes,
        reservar_lotes_para_envio,
    )
    from setores.qualidade.views.wms_views import disparar_integracoes_wms_pendentes

    criar_pendencia_wms_liberacao_lote(registro, local=parametros["local"])
    disparar_integracoes_wms_pendentes()
    ids_envio = reservar_lotes_para_envio(LiberacaoLote.objects.order_by("id"))
    if ids_envio:
        disparar_envio_lotes(ids_envio)
    return True, "Registro local de liberação salvo para integração."


def retorno_area_vermelha_confirmado(resposta):
    try:
        retorno = json.loads(resposta)
        resultado = retorno.get("result") or {}
        retorno_movimento = resultado.get("retornoMovimento") or {}
        return (
            retorno_movimento.get("retorno") == "OK"
            and resultado.get("tipoRetorno") == "1"
            and "processado com sucesso" in str(resultado.get("mensagemRetorno") or "").lower()
            and not resultado.get("erroExecucao")
        )
    except TypeError, ValueError:
        return False


def enviar_lote_para_area_vermelha(request, selected_row):
    """Move o lote pendente para o depósito físico de Área Vermelha."""
    filial = getattr(request.user, "filial", None)
    empresa = getattr(filial, "empresa", None)
    parametros_filial = getattr(filial, "parametros_filial", None)
    # Mesmo achado de segurança de obter_parametros_liberacao: empresa sempre
    # vem do usuário autenticado, nunca do `codemp` recebido no POST.
    codemp = getattr(empresa, "codemp", None)
    codfil = getattr(filial, "codfil", None)
    codtns = getattr(parametros_filial, "codtns", "") if parametros_filial else ""
    usuario_integracao = getattr(request.user, "idintegracao", None)
    if not codemp or not codfil:
        return False, "Usuário sem empresa/filial vinculada."
    if not codtns:
        return (
            False,
            "Parâmetro de filial 'Transação de ERP Saída por Transferência Interna' não configurado.",
        )
    if usuario_integracao in (None, ""):
        return False, "Usuário sem ID de integração configurado."

    recurso = buscar_recurso_por_codigo(codemp, selected_row.get("codcre"))
    parametros_recurso = recurso.get_parametros_efetivos() if recurso else None
    deposito_destino = (parametros_recurso or {}).get("deposito_area_vermelha_erp") or getattr(
        parametros_filial, "deposito_area_vermelha_erp", ""
    )
    if not deposito_destino:
        return False, "Depósito de Área Vermelha não configurado no recurso ou na filial."

    try:
        qtd_mov = float(str(selected_row.get("qtdest") or "").replace(",", "."))
    except TypeError, ValueError:
        return False, "Quantidade inválida para a transferência para a Área Vermelha."

    if qtd_mov <= 0:
        return False, "Quantidade inválida para a transferência para a Área Vermelha."

    dados = {
        "wacao": "MOVIMENTAR-ESTOQUE",
        "acaoBotao": "V",
        "codEmp": int(codemp),
        "codFil": codfil,
        "codPro": selected_row["codpro"],
        "codDer": selected_row.get("codder", " "),
        "codDep": selected_row["coddep"],
        "codTns": str(codtns),
        "codLot": selected_row["codlot"],
        "lotTrf": selected_row["codlot"],
        "numDoc": selected_row.get("numorp", ""),
        "oriOrp": selected_row.get("codori", ""),
        "qtdMov": qtd_mov,
        "usuRes": usuario_integracao,
        "depTrf": str(deposito_destino),
        "proTrf": "",
        "derTrf": "",
        "motMvp": f"MOVIMENTO VIA {getattr(settings, 'APPLICATION_NAME', '')}",
    }
    json_dados = json.dumps(dados, ensure_ascii=False)
    envelope = f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<soapenv:Envelope xmlns:soapenv="http://www.w3.org/2003/05/soap-envelope" xmlns:ser="http://services.senior.com.br">
  <soapenv:Header/>
  <soapenv:Body>
    <ser:MovimentarEstoque>
      <user>{escape(str(settings.SAPIENS_USERNAME))}</user>
      <password>{escape(str(settings.SAPIENS_PASSWORD))}</password>
      <encryption>0</encryption>
      <parameters><flowInstanceID></flowInstanceID><flowName></flowName><tabelaEntradas><chave>wdados</chave><valor><![CDATA[{escapar_cdata_sapiens(json_dados)}]]></valor></tabelaEntradas></parameters>
    </ser:MovimentarEstoque>
  </soapenv:Body>
</soapenv:Envelope>"""
    sucesso, resposta = post_soap_sapiens("sapiens_Synccustom.senior.man.producao", envelope)
    if sucesso:
        return True, resposta

    # O MovimentarEstoque pode devolver status externo ERRO mesmo com o retorno
    # interno de movimento confirmado. Esse formato pertence só a esta ação.
    if retorno_area_vermelha_confirmado(resposta):
        return True, "OK"
    return False, resposta


@permissao_requerida("qualidade.pode_acessar_liberacao_lotes")
def liberar_lotes(request):
    search_query = (request.GET.get("search") or "").strip()
    page_number = request.GET.get("page", "")
    selected_row = {}
    filial_logada = getattr(request.user, "filial", None)
    empresa_logada = getattr(filial_logada, "empresa", None)
    parametros_filial_logada = getattr(filial_logada, "parametros_filial", None)
    codemp_usuario = getattr(empresa_logada, "codemp", None)
    depositos_consulta = carregar_depositos_consulta(filial_logada) if filial_logada else []
    origens_area_vermelha = separar_origens_area_vermelha(
        getattr(parametros_filial_logada, "origens_area_vermelha", "")
    )

    if request.method == "POST":
        selected_row = {
            "codemp": request.POST.get("codemp", ""),
            "usu_numbob": request.POST.get("usu_numbob", ""),
            "codlot": request.POST.get("codlot", ""),
            "coddep": request.POST.get("coddep", ""),
            "codpro": request.POST.get("codpro", ""),
            "codder": request.POST.get("codder", ""),
            "codcre": request.POST.get("codcre", ""),
            "codori": request.POST.get("codori", ""),
            "numorp": request.POST.get("numorp", ""),
            "qtdest": request.POST.get("qtdest", ""),
            "sitlot": request.POST.get("sitlot", ""),
        }
        action = request.POST.get("action")
        pode_destinar_lotes = request.user.is_staff or request.user.has_perm(
            "qualidade.pode_destinar_lotes_liberacao"
        )
        if action in ("liberar", "area_vermelha") and not pode_destinar_lotes:
            messages.error(request, "Você não possui permissão para destinar lotes nesta tela.")
        elif action == "liberar" and selected_row.get("codlot"):
            pendente, motivo = validar_lote_pendente_erp(codemp_usuario, selected_row)
            if not pendente:
                messages.error(request, motivo)
            else:
                success, msg = salvar_liberacao_lote_pendente(request, selected_row)
                if success:
                    messages.success(
                        request, f"Lote {selected_row['codlot']} salvo para integração."
                    )
                else:
                    messages.error(
                        request,
                        f"Falha ao salvar liberação do lote {selected_row['codlot']}: {msg}",
                    )
        elif action == "area_vermelha" and selected_row.get("codlot"):
            if str(selected_row.get("codori") or "").strip().upper() not in origens_area_vermelha:
                messages.error(request, "Origem não permitida para destinação na Área Vermelha.")
            else:
                pendente, motivo = validar_lote_pendente_erp(codemp_usuario, selected_row)
                if not pendente:
                    messages.error(request, motivo)
                else:
                    success, msg = enviar_lote_para_area_vermelha(request, selected_row)
                    if success:
                        messages.success(
                            request,
                            f"Lote {selected_row['codlot']} transferido para Área Vermelha.",
                        )
                    else:
                        messages.error(
                            request,
                            f"Falha ao transferir lote {selected_row['codlot']} para Área Vermelha: {msg}",
                        )
        elif action:
            messages.warning(request, "Selecione uma linha antes de executar a ação.")

        redirect_url = "qualidade:liberar_lotes"
        query_string = []
        if search_query:
            query_string.append(f"search={search_query}")
        if page_number:
            query_string.append(f"page={page_number}")
        if query_string:
            return redirect(f"{redirect(redirect_url).url}?{'&'.join(query_string)}")
        return redirect(redirect_url)

    sql = """
        SELECT
            DLS.CODEMP,
            MAX(EOQ.USU_NUMBOB) AS USU_NUMBOB,
            MAX(EOQ.NUMORP) AS NUMORP,
            MAX(EOQ.CODORI) AS CODORI,
            DLS.CODLOT,
            DLS.USU_SITLOT AS SITLOT,
            DLS.CODDEP,
            DLS.CODPRO,
            DLS.CODDER,
            PRO.DESPRO,
            MAX(EOQ.CODCRE) AS CODCRE,
            MAX(CRE.ABRCRE) AS ABRCRE,
            DLS.QTDEST,
            TO_CHAR(MAX(EOQ.DATREA), 'DD/MM/YYYY') AS DATREA,
            LPAD(TRUNC(MAX(EOQ.HORREA) / 60), 2, '0') || ':' ||
            LPAD(MOD(MAX(EOQ.HORREA), 60), 2, '0') AS HORREA
        FROM E210DLS DLS
        JOIN E900EOQ EOQ
          ON EOQ.CODEMP = DLS.CODEMP
         AND EOQ.CODLOT = DLS.CODLOT
        LEFT JOIN E725CRE CRE
          ON CRE.CODEMP = EOQ.CODEMP
         AND CRE.CODCRE = EOQ.CODCRE
        LEFT JOIN E075PRO PRO
          ON PRO.CODEMP = DLS.CODEMP
         AND PRO.CODPRO = DLS.CODPRO
        WHERE DLS.CODEMP = :codemp
          AND DLS.QTDEST > 0
    """
    params = {"codemp": codemp_usuario}

    if depositos_consulta:
        placeholders = []
        for indice, deposito in enumerate(depositos_consulta):
            nome_param = f"coddep_{indice}"
            params[nome_param] = deposito
            placeholders.append(f":{nome_param}")
        sql += f"""
          AND DLS.CODDEP IN ({", ".join(placeholders)})
        """

    placeholders = []
    for indice, origem in enumerate(origens_area_vermelha):
        nome_param = f"codori_area_{indice}"
        params[nome_param] = origem
        placeholders.append(f":{nome_param}")
    sql += f"""
          AND UPPER(PRO.CODORI) IN ({", ".join(placeholders) if placeholders else "NULL"})
    """

    if search_query:
        sql += """
          AND (
                UPPER(DLS.CODLOT) LIKE :search_text
             OR UPPER(DLS.USU_SITLOT) LIKE :search_text
             OR UPPER(DLS.CODDEP) LIKE :search_text
             OR TO_CHAR(EOQ.USU_NUMBOB) LIKE :search_exact
             OR UPPER(EOQ.CODCRE) LIKE :search_text
             OR UPPER(CRE.ABRCRE) LIKE :search_text
             OR UPPER(DLS.CODPRO) LIKE :search_text
             OR UPPER(DLS.CODDER) LIKE :search_text
             OR UPPER(PRO.DESPRO) LIKE :search_text
             OR TO_CHAR(DLS.QTDEST) LIKE :search_exact
             OR TO_CHAR(EOQ.DATREA, 'DD/MM/YYYY') LIKE :search_exact
             OR (LPAD(TRUNC(EOQ.HORREA / 60), 2, '0') || ':' || LPAD(MOD(EOQ.HORREA, 60), 2, '0')) LIKE :search_exact
          )
        """
        params["search_text"] = f"%{search_query.upper()}%"
        params["search_exact"] = f"%{search_query}%"

    sql += """
        GROUP BY
            EOQ.USU_NUMBOB,
            DLS.CODEMP,
            DLS.CODLOT,
            DLS.USU_SITLOT,
            DLS.CODDEP,
            DLS.CODPRO,
            DLS.CODDER,
            PRO.DESPRO,
            DLS.QTDEST
        ORDER BY MAX(EOQ.DATREA) DESC, MAX(EOQ.HORREA) DESC
    """

    bobinas = []
    erro = None

    if not codemp_usuario:
        erro = "Usuário sem empresa vinculada."
        messages.error(request, erro)
    elif not depositos_consulta:
        erro = "Nenhum depósito de consulta apontamento ERP configurado na filial ou nos recursos da filial."
        messages.error(request, erro)
    elif not origens_area_vermelha:
        erro = "Nenhuma origem permitida para área vermelha configurada na filial."
        messages.error(request, erro)
    else:
        try:
            with cursor_oracle_erp() as cursor:
                cursor.execute(sql, params)
                colunas = [col[0].lower() for col in cursor.description]
                for row in cursor.fetchall():
                    bobinas.append(dict(zip(colunas, row, strict=False)))
        except Exception:
            logger.exception("Falha ao consultar bobinas no Oracle")
            messages.error(request, "Não foi possível consultar bobinas no ERP.")

    paginator = Paginator(bobinas, 30)
    page_number = request.GET.get("page")
    bobinas_page = paginator.get_page(page_number)

    # Mapeamento de cod_alchemy para os recursos da página
    recursos_alchemy = {}
    if filial_logada:
        for recurso in Recurso.objects.filter(
            centro_recurso__setor__departamento__filial=filial_logada
        ).select_related(
            "centro_recurso__setor__departamento__filial__empresa",
            "centro_recurso__parametros_centro_recurso",
        ):
            parametros_centro = getattr(recurso.centro_recurso, "parametros_centro_recurso", None)
            if not parametros_centro or not parametros_centro.cod_alchemy:
                continue
            codemp_recurso = str(recurso.centro_recurso.setor.departamento.filial.empresa.codemp)
            codigo = recurso.centro_recurso.codigo_integrador
            if codigo:
                recursos_alchemy[(codemp_recurso, str(codigo))] = parametros_centro.cod_alchemy

    for bobina in bobinas_page.object_list:
        bobina["codmaquina_alchemy"] = recursos_alchemy.get(
            (str(bobina.get("codemp") or ""), str(bobina.get("codcre") or ""))
        )

    try:
        analises = carregar_analises_alchemy(bobinas_page.object_list)
        for bobina in bobinas_page.object_list:
            codmaquina = bobina.get("codmaquina_alchemy")
            codbobina = bobina.get("usu_numbob")
            chave = (int(codmaquina), int(codbobina)) if codmaquina and codbobina else None
            bobina["analise_flag"] = analises.get(chave)
    except Exception:
        logger.exception("Falha ao consultar análises no Alchemy")
        messages.warning(request, "Não foi possível consultar análises no Alchemy.")
        for bobina in bobinas_page.object_list:
            bobina["analise_flag"] = None

    locais_wms, local_filial_wms = carregar_locais_armazenamento_wms(
        bobinas_page.object_list, filial_logada
    )
    for bobina in bobinas_page.object_list:
        chave_recurso = (
            str(bobina.get("codemp") or ""),
            str(bobina.get("codcre") or "").strip(),
        )
        bobina["local_wms"] = locais_wms.get(chave_recurso) or local_filial_wms or ""

    chaves_pagina = []
    for bobina in bobinas_page.object_list:
        try:
            chaves_pagina.append(
                (
                    int(bobina.get("codemp") or 0),
                    str(bobina.get("codlot") or ""),
                    str(bobina.get("codpro") or ""),
                    str(bobina.get("codder") or ""),
                )
            )
        except TypeError, ValueError:
            bobina["destinado_lote"] = False

    lotes_destinados = set()
    if chaves_pagina:
        filtro_destinados = Q()
        for codemp, codlot, codpro, codder in chaves_pagina:
            filtro_destinados |= Q(
                codemp=codemp,
                codlot=codlot,
                codpro=codpro,
                codder=codder,
            )
        lotes_destinados = set(
            LiberacaoLote.objects.filter(filtro_destinados).values_list(
                "codemp", "codlot", "codpro", "codder"
            )
        )

    for bobina in bobinas_page.object_list:
        try:
            codemp_bobina = int(bobina.get("codemp") or 0)
            codlot_bobina = str(bobina.get("codlot") or "")
            codpro_bobina = str(bobina.get("codpro") or "")
            codder_bobina = str(bobina.get("codder") or "")
            chaves_destinacao = {(codemp_bobina, codlot_bobina, codpro_bobina, codder_bobina)}
        except TypeError, ValueError:
            chaves_destinacao = set()
        sitlot = str(bobina.get("sitlot") or "").strip().upper()
        bobina["situacao_pendente"] = sitlot in ("P", "")
        bobina["avaliado_erp"] = sitlot == "A"
        bobina["situacao_excluida"] = sitlot == "E"
        try:
            bobina["aguardando_repesagem"] = (
                Decimal(str(bobina.get("qtdest") or "0").replace(",", ".")) == 1
            )
        except InvalidOperation, TypeError, ValueError:
            bobina["aguardando_repesagem"] = False

        bobina["destinado_lote"] = bool(chaves_destinacao & lotes_destinados)
        bobina["local_nao_definido"] = not str(bobina.get("local_wms") or "").strip()
        bobina["bloqueado_lote"] = (
            bobina["destinado_lote"]
            or bobina["avaliado_erp"]
            or not bobina["situacao_pendente"]
            or bobina["aguardando_repesagem"]
            or bobina["local_nao_definido"]
        )

    context = {
        "titulo": "Liberação de Lotes",
        "bobinas": bobinas_page,
        "search_query": search_query,
        "selected_row": selected_row,
        "erro_consulta": erro,
        "pode_destinar_lotes": request.user.is_staff
        or request.user.has_perm("qualidade.pode_destinar_lotes_liberacao"),
    }
    return render(request, "setores/qualidade/liberar_lotes.html", context)
