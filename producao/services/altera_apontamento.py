import json
import logging
import re
from datetime import datetime
from decimal import Decimal
from xml.sax.saxutils import escape

from django.conf import settings
from django.db import transaction

from accounts.models import Recurso
from producao.models.estrutura import Apontamento, CorrecaoLote
from producao.services.sapiens import enviar_soap_sapiens
from producao.utils.codificacao import get_response_text, safe_str
from producao.utils.sapiens_soap import escapar_cdata_sapiens
from SIGMA.integracoes.oracle import cursor_oracle_erp
from SIGMA.segredos import mascarar_segredos

logger = logging.getLogger(__name__)

# Timeout herdado do comportamento anterior ao transporte compartilhado; declarado
# aqui porque correção de lote pode estornar várias linhas em sequência (rateio).
WEBSERVICE_TIMEOUT_SEGUNDOS = 180


def normalizar_lote_numerico(lote_str):
    """Retorna o contador numerico cadastrado na empresa; vazio/invalido deve bloquear."""
    texto = str(lote_str or "").strip()
    if not texto:
        raise ValueError("Lote atual da empresa não informado.")
    if not texto.isdigit():
        raise ValueError("Lote atual da empresa deve conter somente números.")
    return texto


def incrementar_lote(lote_str):
    """Incrementa o contador de lote, mantendo a nova nomenclatura somente numerica."""
    return str(int(normalizar_lote_numerico(lote_str)) + 1)


def get_codemp_usuario(user):
    """Retorna o codemp da filial do usuário logado."""
    if user.is_authenticated and hasattr(user, "filial") and user.filial:
        return user.filial.empresa.codemp
    return None


def extrair_mensagem_soap(response_text):
    """Extrai mensagem de erro ou sucesso de uma resposta SOAP do Sapiens."""
    for tag in ["mensagemErro", "erroExecucao", "erroAviso", "mensagemRetorno"]:
        match = re.search(f"<{tag}>(.*?)</{tag}>", response_text, re.DOTALL)
        if match:
            msg = match.group(1).strip()
            if msg:
                return msg
    # Nenhuma tag conhecida bateu: cai para a resposta inteira, que pode ecoar o
    # envelope da requisição (comum em SOAP faults) — mascara por precaução.
    return mascarar_segredos(response_text)


def post_soap_sapiens(url_suffix, envelope):
    """Executa uma requisição POST SOAP para o Sapiens."""
    sapiens_base = settings.SAPIENS_URL_BASE
    if not sapiens_base:
        logger.error("SAPIENS_URL_BASE não configurada para chamada SOAP.")
        return False, "Integração ERP não configurada."
    url = f"{sapiens_base}/g5-senior-services/{url_suffix}"
    try:
        # validar_status=False: HTTP != 200 é interpretado como regra de negócio
        # daqui (mensagem genérica, sem ecoar o corpo), não exceção do transporte.
        r = enviar_soap_sapiens(
            url, envelope, timeout=WEBSERVICE_TIMEOUT_SEGUNDOS, validar_status=False
        )
    except Exception as exc:
        # Falha de rede/requisição não costuma ecoar o corpo enviado, mas o invariante
        # do módulo é mascarar toda exceção que passou perto do Sapiens antes de sair.
        logger.error(
            "Falha na chamada SOAP do Sapiens: %s",
            mascarar_segredos(safe_str(exc)),
        )
        return False, "Falha ao comunicar com o ERP."

    # Lógica de validação baseada em logs_apontamentos
    m_status = re.search(
        r"<waRetorno>(.*?)</waRetorno>", get_response_text(r), re.DOTALL | re.IGNORECASE
    )
    if m_status:
        json_str_status = m_status.group(1)
        try:
            data_status = json.loads(json_str_status)
            if data_status.get("message") == "OK" or data_status.get("status") == "OK":
                return True, "OK"
            logger.warning(
                "ERP recusou correção de lote: %s",
                mascarar_segredos(json_str_status),
            )
            return False, "ERP recusou a operação."
        except json.JSONDecodeError, TypeError:
            if "Processado com sucesso" in get_response_text(r):
                return True, "OK"

    msg = extrair_mensagem_soap(get_response_text(r))
    if r.status_code == 200:
        if (
            "<codigoResultado>0</codigoResultado>" in get_response_text(r)
            or msg in ["OK", "Sucesso", "Processado com Sucesso.", "Processado com sucesso."]
            or "Processado com sucesso" in get_response_text(r)
            or "Processado com Sucesso" in get_response_text(r)
            or "<erroAviso></erroAviso>" in get_response_text(r)
            or "<mensagemRetorno>Processado com Sucesso.</mensagemRetorno>" in get_response_text(r)
            or "<retorno>OK</retorno>" in get_response_text(r)
        ):
            return True, "OK"
        logger.warning("ERP recusou correção de lote: %s", msg)
        return False, "ERP recusou a operação."
    logger.warning("Falha HTTP %s ao chamar ERP: %s", r.status_code, msg)
    return False, "Falha ao comunicar com o ERP."


def buscar_dados_lote_erp_logic(lote, user):
    """Lógica de busca de dados do lote no ERP (E900EOQ) ou logs locais."""
    if not lote:
        return {"error": "Lote não informado"}, 400
    lote = str(lote).upper().strip()
    codemp = get_codemp_usuario(user)
    if not codemp:
        return {"error": "Usuário não vinculado a uma empresa"}, 400

    try:
        apont_local = Apontamento.objects.filter(lote=lote, codemp=codemp).first()
        # Status EXCLUIDO é o histórico/cache local de exclusão já confirmada pelo fluxo de correção.
        # Evita novas consultas e tentativas no ERP para um lote que o sistema já marcou como excluído.
        if Apontamento.objects.filter(
            lote=lote, codemp=codemp, status=Apontamento.Status.EXCLUIDO
        ).exists():
            return {
                "error": f"Lote {lote} já foi excluído localmente.",
                "integrado_erp": False,
                "existe_local": True,
                "excluido_local": True,
            }, 400

        with cursor_oracle_erp() as cursor:
            cursor.execute(
                """SELECT
                    codemp,
                    codpro,
                    codder,
                    codori,
                    numorp,
                    codetg,
                    codcre,
                    seqeoq,
                    qtdre1,

                    MAX(seqeoq) OVER (PARTITION BY codpro, codder, codori, numorp, codetg) AS max_seqeoq,
                    SUM(qtdre1) OVER (PARTITION BY codpro, codder, codori, numorp, codetg) AS total_qtdre1,
                    MAX(seqrot) OVER (PARTITION BY codpro, codder, codori, numorp, codetg) AS seqrot,
                    MAX(usu_numbob) OVER (PARTITION BY codpro, codder, codori, numorp, codetg) AS numbob,
                    MAX(codcre) OVER (PARTITION BY codpro, codder, codori, numorp, codetg) AS codcre_max,
                    MAX(numcad) OVER (PARTITION BY codpro, codder, codori, numorp, codetg) AS numcad_max

                FROM e900eoq
                WHERE codlot = :lote AND codemp = :codemp
                ORDER BY seqeoq DESC""",
                {"lote": str(lote), "codemp": codemp},
            )
            rows = cursor.fetchall()
            colunas = [coluna[0].lower() for coluna in cursor.description]

        if rows:
            erp_data = []
            for r in (dict(zip(colunas, linha, strict=False)) for linha in rows):
                erp_data.append(
                    {
                        "codemp": r["codemp"],
                        "codpro": r["codpro"],
                        "codder": r["codder"],
                        "codori": r["codori"],
                        "numorp": r["numorp"],
                        "codetg": r["codetg"],
                        "codcre": r["codcre"],
                        "seqeoq": r["seqeoq"],
                        "qtdre1": float(r["qtdre1"] or 0),
                        "max_seqeoq": r["max_seqeoq"],
                        "total_qtdre1": float(r["total_qtdre1"] or 0),
                        "seqrot": r["seqrot"],
                        "numbob": r["numbob"],
                        "codcre_max": r["codcre_max"],
                        "numcad_max": r["numcad_max"],
                    }
                )

            # O primeiro registro serve como base para os dados principais
            first = erp_data[0]
            return {
                "codemp": codemp,
                "codpro": first["codpro"],
                "codder": first["codder"],
                "codori": first["codori"],
                "numorp": first["numorp"],
                "codetg": first["codetg"],
                "seqeoq": first["max_seqeoq"],
                "qtdre1": first["total_qtdre1"],
                "seqrot": first["seqrot"],
                "numbob": first["numbob"],
                "codcre": first["codcre_max"],
                "numcad": first["numcad_max"],
                "datmov": datetime.now().strftime("%d/%m/%Y"),
                "integrado_erp": True,
                "existe_local": bool(apont_local),
                "erp_rows": erp_data,  # Lista completa para exibição na tela
            }, 200

        if apont_local:
            return {
                "codemp": apont_local.codemp,
                "codori": apont_local.origem,
                "numorp": apont_local.numorp,
                "codetg": apont_local.codetg,
                "seqeoq": None,
                "qtdre1": float(apont_local.qtdre1 or 0),
                "integrado_erp": False,
                "existe_local": True,
                "codcre": apont_local.codigo_integrador,
            }, 200

        return {"error": "Lote não encontrado.", "integrado_erp": False, "existe_local": False}, 404
    except Exception:
        logger.exception("Falha ao buscar dados do lote no ERP.")
        return {"error": "Não foi possível consultar o lote no ERP."}, 500


def get_operator_name(cursor, codemp, numcad):
    """Busca nome do operador ativo no Oracle."""
    cursor.execute(
        "SELECT nomope FROM e906ope WHERE codemp=:codemp AND numcad=:numcad AND sitope='A'",
        {"codemp": codemp, "numcad": numcad},
    )
    r = cursor.fetchone()
    if r:
        r = dict(zip((coluna[0].lower() for coluna in cursor.description), r, strict=False))
    return r["nomope"] if r else None


def _buscar_recurso_para_correcao(erp_info, codemp):
    codcre = erp_info.get("codcre") if erp_info else None
    if not codcre:
        return None

    return (
        Recurso.objects.select_related(
            "parametros_recurso",
            "centro_recurso__parametros_centro_recurso",
            "centro_recurso__setor__departamento__filial__parametros_filial",
        )
        .filter(
            centro_recurso__codigo_integrador=str(codcre),
            centro_recurso__setor__departamento__filial__empresa__codemp=codemp,
        )
        .first()
    )


def _validar_lote_bobina_deposito_consulta(
    codemp, codlot, numbob, coddep, codori=None, numorp=None, codetg=None, codcre=None
):
    if (
        not codemp
        or not codlot
        or numbob in (None, "", "None")
        or not coddep
        or not codori
        or numorp in (None, "", "None")
        or codetg in (None, "", "None")
        or not codcre
    ):
        return False, "Dados insuficientes para validar lote/bobina no depósito de consulta."

    try:
        numbob = int(numbob)
        numorp = int(numorp)
        codetg = int(codetg)
    except TypeError, ValueError:
        return False, "Dados inválidos para validar lote/bobina no depósito de consulta."

    with cursor_oracle_erp() as cursor:
        cursor.execute(
            """
                SELECT DLS.USU_SITLOT,
                       NVL(DLS.QTDEST, 0) saldo
                FROM E210DLS DLS
                JOIN E900EOQ EOQ
                  ON EOQ.CODEMP = DLS.CODEMP
                 AND EOQ.CODLOT = DLS.CODLOT
                WHERE DLS.CODEMP = :codemp
                  AND DLS.CODLOT = :codlot
                  AND EOQ.USU_NUMBOB = :numbob
                  AND EOQ.CODORI = :codori
                  AND EOQ.NUMORP = :numorp
                  AND EOQ.CODETG = :codetg
                  AND EOQ.CODCRE = :codcre
                  AND DLS.CODDEP = :coddep
                  AND ROWNUM = 1
            """,
            {
                "codemp": codemp,
                "codlot": str(codlot).upper().strip(),
                "numbob": numbob,
                "coddep": str(coddep).strip(),
                "codori": str(codori).strip(),
                "numorp": numorp,
                "codetg": codetg,
                "codcre": str(codcre).strip(),
            },
        )
        row = cursor.fetchone()
        if row:
            row = dict(zip((coluna[0].lower() for coluna in cursor.description), row, strict=False))

    if not row:
        return False, "Lote/bobina não encontrado no depósito de consulta do ERP."

    situacao = str(row["usu_sitlot"] or "").strip().upper()
    # NOTA (auditoria producao/models,services,utils): `saldo` calculado mas não usado abaixo —
    # incerto se é código morto ou validação de saldo faltando. Mantido sem alteração; ver relatório.
    float(row["saldo"] or 0)

    if situacao == "E":
        return False, "já foi excluído no ERP."
    if situacao == "A":
        return False, "já foi avaliado no ERP."
    if situacao == "V":
        return False, "está em Área Vermelha no ERP."
    if situacao != "P":
        return (
            False,
            f"não está mais pendente no ERP, já foi direcionado. Situação atual: {situacao}.",
        )

    return True, ""


def _iniciar_correcao_lote(codemp, lote_id, nova_quantidade, excluir_apontamento):
    """Reserva uma correção por empresa/lote e impede reenvio ERP duplicado."""
    quantidade = Decimal(str(nova_quantidade))
    with transaction.atomic():
        operacao, criada = CorrecaoLote.objects.select_for_update().get_or_create(
            codemp=codemp,
            lote=lote_id,
            defaults={
                "quantidade": quantidade,
                "excluir_apontamento": excluir_apontamento,
                "status": CorrecaoLote.Status.EM_ANDAMENTO,
            },
        )
        if criada:
            return operacao, None

        if operacao.status == CorrecaoLote.Status.EM_ANDAMENTO:
            return None, (False, [f"Ajuste do lote {lote_id} já está em processamento."])
        if (
            operacao.status == CorrecaoLote.Status.CONCLUIDA
            and operacao.quantidade == quantidade
            and operacao.excluir_apontamento == excluir_apontamento
        ):
            return None, (True, [f"Ajuste do lote {lote_id} já foi confirmado anteriormente."])

        operacao.quantidade = quantidade
        operacao.excluir_apontamento = excluir_apontamento
        operacao.status = CorrecaoLote.Status.EM_ANDAMENTO
        operacao.mensagem = ""
        operacao.save(
            update_fields=[
                "quantidade",
                "excluir_apontamento",
                "status",
                "mensagem",
                "atualizado_em",
            ]
        )
        return operacao, None


def _finalizar_correcao_lote(operacao, sucesso, mensagens):
    # AumentarApontamento/DiminuirApontamento são idempotentes na regra
    # personalizada do ERP: reenviar uma correção já aplicada não duplica o
    # efeito, o ERP reconhece que não há mais o que ajustar e responde sucesso
    # A regra reconhece uma correção já aplicada sem duplicar o efeito.
    # Por isso falha após chamada ao ERP cai em FALHA, que já libera nova
    # tentativa em `_iniciar_correcao_lote` — decisão do sênior (2026-08-25):
    # não existe mais conciliação manual para este fluxo.
    status = CorrecaoLote.Status.CONCLUIDA if sucesso else CorrecaoLote.Status.FALHA
    operacao.status = status
    operacao.mensagem = "\n".join(str(mensagem) for mensagem in mensagens)
    operacao.save(update_fields=["status", "mensagem", "atualizado_em"])
    return sucesso, mensagens


def _corrigir_lote_sem_erp(lote_id, codemp, nova_quantidade, usuario_obj, excluir_apontamento):
    """Fluxo quando o lote não está integrado no ERP: ajusta só o registro local."""
    logs = []
    apontamentos = Apontamento.objects.filter(lote=lote_id, codemp=codemp)

    if not apontamentos.exists():
        logs.append("ERP: Lote inexistente (local e ERP).")
        return True, logs

    if excluir_apontamento:
        for apont in apontamentos:
            apont.qtdre1 = 0
            apont.log = "Apontamento local excluído."
            apont.status = Apontamento.Status.EXCLUIDO
            apont.usuario = usuario_obj
            apont.save()
        logs.append("Apontamento local excluído.")
        return True, logs

    qtd_local_atual = sum(float(apont.qtdre1 or 0) for apont in apontamentos)
    if qtd_local_atual <= 0:
        return False, ["Erro: Não é permitido corrigir lote com quantidade atual zero."]

    for apont in apontamentos:
        apont.qtdre1 = nova_quantidade
        apont.usuario = usuario_obj
        apont.save()
        logs.append("Apontamento local atualizado.")
    return True, logs


def _corrigir_lote_incremento(
    *,
    codemp,
    codori,
    numorp,
    codetg,
    seqrot_erp,
    numcad_final,
    nome_ope,
    qtd_total_db,
    nova_quantidade,
    lote_id,
    numbob_erp,
    codcre_erp,
    codpro,
    codder,
    usuario_obj,
):
    """Fluxo de ajuste PARA MAIS: incremento no ERP via webservice AumentarApontamento."""
    logs = []
    sucesso_geral = True
    qtd_incremento = float(nova_quantidade) - float(qtd_total_db)
    logs.append(
        f"Dados do lote recuperados do ERP ({codpro}-{codder}). "
        f"Incremento solicitado: {qtd_incremento:.2f} pelo operador {numcad_final} ({nome_ope})."
    )

    ws_args = {
        "usuario": settings.SAPIENS_USERNAME,
        "senha": settings.SAPIENS_PASSWORD,
        "codemp": codemp,
        "codori": codori,
        "numorp": numorp,
        "codetg": codetg,
        "seqrot": seqrot_erp,
        "numcad": numcad_final,
        "qtdrfg": 0,
        "codlot": lote_id,
        "numbob": numbob_erp or "",
        "nummaq": codcre_erp,
        "datmov": datetime.now().strftime("%d/%m/%Y"),
        "hormov": datetime.now().strftime("%H:%M:%S"),
    }

    success, msg = False, ""
    try:
        success, msg = _chamar_webservice_aumentar_apontamento(
            **{**ws_args, "qtdre1": qtd_incremento}
        )
        if success:
            logs.append(f"ERP: Lote incrementado: {msg}")
        else:
            logs.append(f"ERP: Falha ao incrementar: {msg}")
    except Exception as e_ws:
        logs.append(f"Erro ao chamar webservice de incremento: {mascarar_segredos(safe_str(e_ws))}")
        sucesso_geral = False

    if success:
        apont = Apontamento.objects.filter(lote=lote_id, codemp=codemp).first()
        if apont:
            apont.qtdre1 = nova_quantidade
            apont.log = f"Incremento ERP: {msg}"
            apont.usuario = usuario_obj
            apont.save()
    else:
        sucesso_geral = False

    return sucesso_geral, logs


def _corrigir_lote_reducao_rateio(
    *,
    codemp,
    lote_id,
    nova_quantidade,
    qtd_orig_para_comparar,
    erp_info,
    numbob_erp,
    codcre_erp,
    deposito_consulta,
    excluir_apontamento,
    usuario_obj,
):
    """Fluxo de ajuste PARA MENOS: uma chamada deixa o rateio inteiramente no ERP."""
    logs = []
    qtd_diferenca_total = float(qtd_orig_para_comparar) - float(nova_quantidade)

    # O contrato novo recebe o total desejado uma vez. A regra ERP localiza e
    # rateia as sequências, grava a pendência de componentes em USU_TESTCMP
    # e confirma tudo na mesma transação. O SIGMA não possui fila ou
    # retentativa separada para esse efeito.
    success, msg = _chamar_webservice_diminuir_apontamento(
        codemp=codemp,
        codori=erp_info.get("codori"),
        numorp=erp_info.get("numorp"),
        codetg=erp_info.get("codetg"),
        qtdre1=nova_quantidade,
        codlot=lote_id,
        numbob=numbob_erp,
        codcre=codcre_erp,
        coddep=deposito_consulta,
        excluir_lote=excluir_apontamento,
    )
    if not success:
        return False, [f"ERP: Falha ao diminuir quantidade: {msg}"]

    if excluir_apontamento:
        logs.append("ERP: Situação de exclusão atualizada no depósito de consulta.")

    apontamentos_lote = Apontamento.objects.filter(lote=lote_id, codemp=codemp)
    for apont in apontamentos_lote:
        apont.qtdre1 = float(nova_quantidade)
        apont.log = f"Ajuste ERP (Redução total de {qtd_diferenca_total:.2f})."
        apont.usuario = usuario_obj
        if excluir_apontamento:
            apont.status = Apontamento.Status.EXCLUIDO
        apont.save()

    logs.append("ERP: Redução confirmada em uma única solicitação.")
    return True, logs


def _corrigir_lote_igual(lote_id, codemp, nova_quantidade, usuario_obj):
    """Fluxo de quantidade IGUAL: nada a integrar no ERP, só atualiza o registro local."""
    logs = []
    apont = Apontamento.objects.filter(lote=lote_id, codemp=codemp).first()
    if apont:
        apont.qtdre1 = nova_quantidade
        apont.log = "Ajuste ERP: Quantidade igual, acerto ignorado."
        apont.usuario = usuario_obj
        apont.save()
    logs.append("ERP: Quantidade igual, webservice de acerto ignorado.")
    return True, logs


def corrigir_quantidade_lote(lote_id, nova_quantidade, usuario_obj, erp_params=None):
    """Corrige a quantidade de um lote no modelo Apontamento.

    Função orquestradora fina: prepara/valida os dados comuns e despacha para
    o fluxo de negócio correto (sem ERP, incremento, redução com rateio ou
    quantidade igual) — ver `_corrigir_lote_*` acima.
    """
    lote_id = str(lote_id).upper().strip()
    logs, sucesso_geral = [], True
    # codemp vem sempre do usuário autenticado (nunca de erp_params/POST): o modal de
    # correção envia "codemp_erp" só para exibição, e um valor forjado ali bastaria para
    # validar limites e montar o envelope SOAP contra a filial errada (achado de segurança).
    codemp = get_codemp_usuario(usuario_obj)
    acao_correcao = (erp_params or {}).get("acao_correcao") if erp_params else None
    excluir_apontamento = acao_correcao == "excluir"

    try:
        nova_quantidade = float(nova_quantidade)
    except TypeError, ValueError:
        return False, ["Erro: Quantidade inválida."]

    if excluir_apontamento:
        nova_quantidade = 0.0

    if not codemp:
        return sucesso_geral, logs

    # Status EXCLUIDO é usado como cache/histórico local de exclusão confirmada pelo próprio fluxo.
    # A exclusão no ERP é validada por E210DLS.USU_SITLOT; esta trava evita rebuscar no erp ao listar.
    if (
        codemp
        and Apontamento.objects.filter(
            lote=lote_id, codemp=codemp, status=Apontamento.Status.EXCLUIDO
        ).exists()
    ):
        return (
            False,
            [f"Erro: Lote {lote_id} já foi excluído localmente e não pode ser atualizado."],
        )

    operacao, resultado_existente = _iniciar_correcao_lote(
        codemp, lote_id, nova_quantidade, excluir_apontamento
    )
    if resultado_existente:
        return resultado_existente

    def finalizar(success, mensagens):
        return _finalizar_correcao_lote(operacao, success, mensagens)

    try:
        # Reutiliza a lógica de busca de dados do lote que já faz o SELECT necessário no E900EOQ
        erp_info, status_code = buscar_dados_lote_erp_logic(lote_id, usuario_obj)

        if status_code != 200:
            return finalizar(False, [f"Erro: {erp_info.get('error', 'Lote não encontrado.')}"])

        recurso_correcao = _buscar_recurso_para_correcao(erp_info, codemp)
        if recurso_correcao is None:
            return finalizar(
                False, ["Erro: Recurso não identificado para validar os limites de correção."]
            )

        parametros_recurso = recurso_correcao.get_parametros_efetivos()
        limite_min = parametros_recurso["limite_apontamento_minimo"]
        limite_max = parametros_recurso["limite_apontamento_maximo"]

        if not excluir_apontamento and (
            nova_quantidade < limite_min or nova_quantidade > limite_max
        ):
            return finalizar(
                False,
                [f"Erro: Quantidade de correção deve ficar entre {limite_min:g} e {limite_max:g}."],
            )

        if not (status_code == 200 and erp_info.get("integrado_erp")):
            # --- Lote não encontrado no ERP, verifica localmente ---
            sucesso_geral, logs = _corrigir_lote_sem_erp(
                lote_id, codemp, nova_quantidade, usuario_obj, excluir_apontamento
            )
            return finalizar(sucesso_geral, logs)

        deposito_consulta = (parametros_recurso.get("deposito_apontamento_erp") or "").strip()
        codori = erp_info.get("codori")
        numorp = erp_info.get("numorp")
        codetg = erp_info.get("codetg")
        codcre_erp = erp_info.get("codcre")
        numbob_erp = (erp_params or {}).get("numbob_erp") or erp_info.get("numbob")

        if not deposito_consulta:
            return finalizar(
                False,
                [
                    "Erro: Depósito de consulta apontamento ERP não configurado para o recurso/filial."
                ],
            )

        lote_disponivel, motivo_bloqueio = _validar_lote_bobina_deposito_consulta(
            codemp,
            lote_id,
            numbob_erp,
            deposito_consulta,
            codori=codori,
            numorp=numorp,
            codetg=codetg,
            codcre=codcre_erp,
        )
        if not lote_disponivel:
            return finalizar(
                False, [f"Erro: Lote {lote_id} bobina {numbob_erp or '-'} {motivo_bloqueio}"]
            )

        codpro = erp_info.get("codpro")
        codder = erp_info.get("codder")
        qtd_total_db = erp_info.get("qtdre1")
        seqrot_erp = erp_info.get("seqrot")
        numcad_final = erp_info.get("numcad")

        # A quantidade original para fins de comparação é o TOTAL do lote no banco
        qtd_orig_para_comparar = float(qtd_total_db)

        # Usa o operador do próprio apontamento ERP, não o usuário local logado.
        if not numcad_final:
            return finalizar(
                False, ["Erro: Não foi possível identificar o operador do lote no ERP."]
            )

        # Validação no ERP
        with cursor_oracle_erp() as cursor:
            nome_ope = get_operator_name(cursor, codemp, numcad_final)

        if not nome_ope:
            return finalizar(
                False,
                [
                    f"Erro: Operador {numcad_final} do lote não foi localizado ou está inativo no ERP."
                ],
            )

        if float(nova_quantidade) > float(qtd_orig_para_comparar):
            sucesso_geral, logs = _corrigir_lote_incremento(
                codemp=codemp,
                codori=codori,
                numorp=numorp,
                codetg=codetg,
                seqrot_erp=seqrot_erp,
                numcad_final=numcad_final,
                nome_ope=nome_ope,
                qtd_total_db=qtd_total_db,
                nova_quantidade=nova_quantidade,
                lote_id=lote_id,
                numbob_erp=numbob_erp,
                codcre_erp=codcre_erp,
                codpro=codpro,
                codder=codder,
                usuario_obj=usuario_obj,
            )
        elif float(nova_quantidade) < float(qtd_orig_para_comparar):
            sucesso_geral, logs = _corrigir_lote_reducao_rateio(
                codemp=codemp,
                lote_id=lote_id,
                nova_quantidade=nova_quantidade,
                qtd_orig_para_comparar=qtd_orig_para_comparar,
                erp_info=erp_info,
                numbob_erp=numbob_erp,
                codcre_erp=codcre_erp,
                deposito_consulta=deposito_consulta,
                excluir_apontamento=excluir_apontamento,
                usuario_obj=usuario_obj,
            )
        else:
            sucesso_geral, logs = _corrigir_lote_igual(
                lote_id, codemp, nova_quantidade, usuario_obj
            )

    except Exception:
        logger.exception("Falha ao corrigir lote %s da empresa %s.", lote_id, codemp)
        logs.append("Erro ao processar a correção no ERP.")
        sucesso_geral = False

    return finalizar(sucesso_geral, logs)


def _chamar_webservice_diminuir_apontamento(
    *,
    codemp,
    codori,
    numorp,
    codetg,
    codlot,
    numbob,
    codcre,
    qtdre1,
    coddep=None,
    excluir_lote=False,
):
    """Executa a redução ou a conclusão da exclusão pela regra personalizada do ERP."""
    dados = {
        "wacao": "DIMINUIR-OP",
        "empresa": str(codemp),
        "CodOri": str(codori),
        "NumOrp": str(numorp),
        "CodEtg": str(codetg),
        "CodLot": str(codlot),
        "NumBob": str(numbob),
        "NumMaq": str(codcre),
    }
    dados["QtdRe1"] = str(qtdre1)
    dados["QtdRfg"] = "0.0"
    if coddep:
        dados["CodDep"] = str(coddep)
    if excluir_lote:
        dados["ExcluirLote"] = "S"

    json_dados = json.dumps(dados, ensure_ascii=False)
    envelope = f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<soapenv:Envelope xmlns:soapenv="http://www.w3.org/2003/05/soap-envelope"
                  xmlns:ser="http://services.senior.com.br">
  <soapenv:Header/>
  <soapenv:Body>
    <ser:DiminuirApontamento>
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
    </ser:DiminuirApontamento>
  </soapenv:Body>
</soapenv:Envelope>"""
    return post_soap_sapiens("sapiens_Synccustom.senior.man.producao", envelope)


def _chamar_webservice_aumentar_apontamento(**kwargs):
    """Chama o webservice AumentarApontamento do Sapiens."""
    dados = {
        "wacao": "INCREMENTAR-OP",
        "empresa": str(kwargs.get("codemp")),
        "CodOri": str(kwargs.get("codori")),
        "NumOrp": str(kwargs.get("numorp")),
        "NumCad": str(kwargs.get("numcad")),
        "CodEtg": str(kwargs.get("codetg")),
        "SeqRot": str(kwargs.get("seqrot")),
        "QtdRe1": str(kwargs.get("qtdre1")),
        "QtdRfg": str(kwargs.get("qtdrfg")),
        "Numbob": str(kwargs.get("numbob")),
        "NumMaq": str(kwargs.get("nummaq")),
        "DatMov": str(kwargs.get("datmov")),
        "HorMov": str(kwargs.get("hormov")),
    }

    if kwargs.get("codlot"):
        dados["CodLot"] = str(kwargs.get("codlot"))

    json_dados = json.dumps(dados, ensure_ascii=False)

    envelope = f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<soapenv:Envelope xmlns:soapenv="http://www.w3.org/2003/05/soap-envelope"
                  xmlns:ser="http://services.senior.com.br">
  <soapenv:Header/>
  <soapenv:Body>
    <ser:AumentarApontamento>
      <user>{escape(str(kwargs.get("usuario")))}</user>
      <password>{escape(str(kwargs.get("senha")))}</password>
      <encryption>0</encryption>
      <parameters>
        <flowInstanceID></flowInstanceID>
        <flowName></flowName>
        <tabelaEntradas>
            <chave>wdados</chave>
            <valor><![CDATA[{escapar_cdata_sapiens(json_dados)}]]></valor>
        </tabelaEntradas>
      </parameters>
    </ser:AumentarApontamento>
  </soapenv:Body>
</soapenv:Envelope>"""
    return post_soap_sapiens("sapiens_Synccustom.senior.man.producao", envelope)
