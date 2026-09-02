import logging
import time

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import CentroRecurso, Recurso
from producao.models import (
    Apontamento,
    ApontamentoComponente,
    LogTrocaOPAtiva,
    ParadaMaquina,
    Sequenciamento,
)
from producao.utils.paradas_manuais import usuario_pode_abrir_parada_manual
from producao.views.apontamento_base import (
    contexto_parada_recurso,
    empresas_visiveis_apontamento,
    recurso_tem_parada_bloqueante,
    recurso_usa_fluxo_base_op_unica,
    recursos_visiveis_apontamento,
    trocar_periodo_produtivo_fluxo_unico,
)
from producao.views.logs_apontamento_componentes import (
    PROCESSAMENTO_APONTAMENTO_COMPONENTES_LOCK,
    disparar_envio_componentes,
    reservar_componentes_para_envio,
)
from SIGMA.integracoes.oracle import cursor_oracle_erp

logger = logging.getLogger(__name__)


def format_data_hora(data, minutos):
    # Formata data e hora vinda do Oracle.
    if not data or (hasattr(data, "year") and data.year == 1900):
        return ""
    if minutos in (None, 0):
        return data.strftime("%d/%m/%Y")
    h, mi = divmod(int(minutos), 60)
    return f"{data.strftime('%d/%m/%Y')} {h:02d}:{mi:02d}"


def classe_comparativo_percentual(receita, atual):
    try:
        receita = float(receita or 0)
        atual = float(atual or 0)
    except (TypeError, ValueError):
        return ""

    # Tolerancia operacional de 1 ponto percentual, com folga para valores exibidos em 3 casas.
    # Mesmos tokens semanticos das colunas de quantidade da consulta de lotes da qualidade.
    tolerancia = 1.01
    if abs(atual - receita) <= tolerancia:
        return "bg-sucesso-sutil text-sucesso-base font-bold"
    if atual > receita:
        return "bg-atencao-sutil text-atencao-base font-bold"
    return "bg-erro-sutil text-erro-base font-bold"


def valida_operador(cursor, cod_emp, num_cad):
    cursor.execute(
        "SELECT nomope FROM e906ope WHERE codemp=:codemp AND numcad=:numcad AND sitope='A'",
        {"codemp": cod_emp, "numcad": num_cad},
    )
    resultado = cursor.fetchone()
    if resultado:
        resultado = dict(
            zip((coluna[0].lower() for coluna in cursor.description), resultado, strict=False)
        )
    return resultado["nomope"] if resultado else None


def decode_cod_barras(codbar: str):
    if len(codbar) == 23:
        cod_emp = codbar[0:4]
        cod_ori = codbar[4:6]
        num_op = int(codbar[6:15])
        cod_etg = codbar[15:19]
        seq_rot = codbar[19:23]
    else:
        cod_emp = codbar[0:4]
        cod_ori = codbar[4:7]
        num_op = int(codbar[7:16])
        cod_etg = codbar[16:20]
        seq_rot = codbar[20:24]
    return cod_emp, cod_ori, num_op, cod_etg, seq_rot


def salvar_log_componente(
    cod_emp,
    origem,
    num_op,
    cod_etg,
    seq_rot,
    num_cad,
    codigo_integrador,
    lote,
    dat_mov,
    hor_mov,
    data_hora,
    recurso=None,
    usuario=None,
):
    lote = str(lote or "").strip().upper()
    if not lote:
        return None, False

    componente_existente = ApontamentoComponente.objects.filter(
        codemp=int(cod_emp),
        lote=lote,
    ).first()
    if componente_existente:
        return componente_existente, False

    return ApontamentoComponente.objects.create(
        recurso=recurso,
        codemp=int(cod_emp),
        origem=origem,
        numorp=int(num_op),
        codetg=int(cod_etg),
        seqrot=int(seq_rot),
        numcad=int(num_cad),
        codigo_integrador=codigo_integrador,
        datmov=dat_mov,
        hormov=hor_mov,
        lote=lote,
        log="Registro salvo",
        status=Apontamento.Status.NAO_INTEGRADO,
        data_hora=data_hora.replace(microsecond=0),
        datger=data_hora.replace(microsecond=0),
        usuario=usuario,
    ), True


def notifica_atualizacao(codbar):
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(f"op_{codbar}", {"type": "refresh_page"})
    except Exception:
        pass


def notifica_atualizacao_atrasada(codbar, atraso_segundos=2):
    try:
        time.sleep(max(int(atraso_segundos), 0))
        notifica_atualizacao(codbar)
    except Exception:
        pass


def buscar_log_op_ativa(recurso_id):
    if not recurso_id:
        return None
    return (
        LogTrocaOPAtiva.objects.filter(recurso_id=recurso_id, horario_saida__isnull=True)
        .order_by("-horario_troca")
        .first()
    )


@login_required
def apontamentos_view(request):
    dados_op, componentes, operacoes, historico, integracoes_pendentes = None, [], [], [], []
    erro, codetg, seqrot, status_seq = None, "", "", ""

    codbar = (request.POST.get("codbar") or request.GET.get("codbar", "")).strip()
    empresa_id = request.POST.get("empresa", request.GET.get("empresa", ""))
    centro_id = request.POST.get("centro", request.GET.get("centro", ""))
    recurso_id = request.POST.get("recurso", request.GET.get("recurso", ""))
    pode_apontar = request.user.is_staff or request.user.has_perm("producao.pode_apontar")

    acoes_restritas = {
        "validar_operador",
        "trocar_operador",
        "trocar_op_ativa",
        "apontar_componente",
    }
    if request.method == "POST" and acoes_restritas.intersection(request.POST) and not pode_apontar:
        messages.error(request, "Você não possui permissão para apontar.")
        return redirect(
            f"{request.path}?empresa={empresa_id}&centro={centro_id}&recurso={recurso_id}&codbar={codbar}"
        )

    resposta_data = request.session.pop("ultima_resposta_componente", None)
    resposta = resposta_data.get("mensagem") if resposta_data else None
    erro = resposta_data.get("erro") if resposta_data else erro

    empresas = empresas_visiveis_apontamento(request.user)

    if not empresa_id and empresas.exists():
        empresa_id = str(empresas.first().id)

    if codbar:
        try:
            _, cod_ori_bar, _, cod_etg_bar, seq_rot_bar = decode_cod_barras(codbar)
            codetg, seqrot = cod_etg_bar, seq_rot_bar
        except Exception:
            pass

    if empresa_id and not empresas.filter(pk=empresa_id).exists():
        empresa_id = centro_id = recurso_id = ""
    centros = (
        CentroRecurso.objects.filter(
            setor__departamento__filial__empresa_id=empresa_id, recursos__ativo=True
        )
        .exclude(descricao__icontains="Geral")
        .distinct()
        .order_by("descricao")
        if empresa_id
        else []
    )
    if centro_id and not centros.filter(pk=centro_id).exists():
        centro_id = recurso_id = ""
    recursos = (
        recursos_visiveis_apontamento(request.user)
        .filter(centro_recurso_id=centro_id, ativo=True)
        .exclude(descricao__icontains="Geral")
        .order_by("descricao")
        if centro_id
        else []
    )

    recurso_selecionado = None
    if recurso_id:
        try:
            recurso_selecionado = (
                recursos_visiveis_apontamento(request.user)
                .select_related("centro_recurso__setor__departamento__filial__empresa")
                .get(id=recurso_id, centro_recurso_id=centro_id)
            )
        except Recurso.DoesNotExist:
            recurso_selecionado = None

    if recurso_id and not recurso_selecionado:
        recurso_id = codbar = ""

    log_op_ativa = buscar_log_op_ativa(recurso_id)
    op_ativa_recurso = log_op_ativa.codigo_barra if log_op_ativa else ""
    tem_multiplas_ops_ativas = bool(
        recurso_selecionado
        and LogTrocaOPAtiva.objects.filter(
            recurso=recurso_selecionado,
            horario_saida__isnull=True,
        )
        .values("pk")[1:2]
        .exists()
    )
    if request.method == "POST" and tem_multiplas_ops_ativas:
        messages.error(
            request,
            "Este recurso possui mais de uma OP ativa. As ações da Apontamentos V2 exigem uma única OP ativa.",
        )
        return redirect(
            f"{request.path}?empresa={empresa_id}&centro={centro_id}&recurso={recurso_id}&codbar={codbar}"
        )

    chave_numcad = f"numcad_operador_{recurso_id}" if recurso_id else None
    chave_nome = f"nome_operador_{recurso_id}" if recurso_id else None
    numcad_sessao = request.session.get(chave_numcad) if chave_numcad else None
    nome_operador_sessao = request.session.get(chave_nome) if chave_nome else None

    try:
        if codbar:
            cod_emp, cod_ori, num_op, cod_etg, seq_rot = decode_cod_barras(codbar)
            with cursor_oracle_erp() as cursor:
                cursor.execute(
                    """
                    SELECT cop.codori, cop.numorp, cop.sitorp, cop.qtdprv, cop.qtdre1,
                           TO_CHAR(cop.dtrini, 'DD/MM/YYYY') dtrini, TO_CHAR(cop.dtrfim, 'DD/MM/YYYY') dtrfim,
                           qdo.codpro, pro.despro, qdo.codder, qdo.unimed
                    FROM e900cop cop
                    JOIN e900qdo qdo ON cop.codemp=qdo.codemp AND cop.codori=qdo.codori
                                   AND cop.numorp=qdo.numorp AND cop.codpro=qdo.codpro
                    JOIN e075pro pro ON qdo.codemp=pro.codemp AND qdo.codpro=pro.codpro
                    WHERE cop.codemp=:codemp AND cop.codori=:codori AND cop.numorp=:numorp
                    """,
                    {"codemp": cod_emp, "codori": cod_ori, "numorp": num_op},
                )
                linha_op = cursor.fetchone()
                if linha_op:
                    linha_op = dict(
                        zip(
                            (coluna[0].lower() for coluna in cursor.description),
                            linha_op,
                            strict=False,
                        )
                    )
                if linha_op:
                    sit_map = {
                        "E": "Explodida",
                        "L": "Liberada",
                        "S": "Suspensa",
                        "F": "Finalizada",
                        "A": "Em andamento",
                        "C": "Cancelada",
                        "R": "Reabilitada",
                    }
                    dados_op = {
                        "codori": linha_op["codori"],
                        "numorp": linha_op["numorp"],
                        "sitorp": sit_map.get(linha_op["sitorp"], linha_op["sitorp"]),
                        "qtdprv": linha_op["qtdprv"],
                        "qtdre1": linha_op["qtdre1"],
                        "dtrini": ""
                        if not linha_op["dtrini"] or linha_op["dtrini"] == "31/12/1900"
                        else linha_op["dtrini"],
                        "dtrfim": ""
                        if not linha_op["dtrfim"] or linha_op["dtrfim"] == "31/12/1900"
                        else linha_op["dtrfim"],
                        "codpro": linha_op["codpro"],
                        "despro": linha_op["despro"],
                        "codder": linha_op["codder"],
                        "unimed": linha_op["unimed"],
                    }
                    status_seq = dados_op.get("sitorp", "Parada")
                else:
                    erro = f"OP {cod_ori}/{num_op} não encontrada."

                cursor.execute(
                    """
                    SELECT cmo.codcmp,
                           pro.despro,
                           pro.codfam,
                           cmo.codder,
                           cmo.unimed,
                           cmo.qtdprv,
                           cmo.qtduti,
                           CASE
                             WHEN pro.codfam IN ('621', '622', '623', '624', '626', '627', '628')
                                  AND NVL(ctm_receita.qtduti, 0) >= 10
                             THEN ROUND(NVL(ctm_receita.qtduti, 0) / 10, 3)
                             ELSE 0
                           END receita,
                           CASE
                             WHEN pro.codfam NOT IN ('621', '622', '623', '624', '626', '627', '628') THEN 0
                             WHEN SUM(CASE WHEN pro.codfam IN ('621', '622', '623', '624', '626', '627', '628') THEN cmo.qtduti ELSE 0 END) OVER (PARTITION BY cmo.codemp, cmo.codori, cmo.numorp) = 0 THEN 0
                             ELSE ROUND((NVL(cmo.qtduti, 0) / SUM(CASE WHEN pro.codfam IN ('621', '622', '623', '624', '626', '627', '628') THEN cmo.qtduti ELSE 0 END) OVER (PARTITION BY cmo.codemp, cmo.codori, cmo.numorp)) * 100, 3)
                           END atual,
                           cmo.bxaorp
                      FROM e900cmo cmo
                      JOIN e075pro pro
                        ON cmo.codemp = pro.codemp
                       AND cmo.codcmp = pro.codpro
                      JOIN e900qdo qdo
                        ON qdo.codemp = cmo.codemp
                       AND qdo.codori = cmo.codori
                       AND qdo.numorp = cmo.numorp
                       AND qdo.proori = 'S'
                      LEFT JOIN e700ctm ctm_receita
                        ON ctm_receita.codemp = qdo.codemp
                       AND ctm_receita.codmod = qdo.codmod
                       AND ctm_receita.codcmp = cmo.codcmp
                       AND ctm_receita.dercmp = cmo.codder
                    WHERE cmo.codemp = :codemp
                       AND cmo.codori = :codori
                       AND cmo.numorp = :numorp
                     ORDER BY cmo.codcmp
                    """,
                    {"codemp": cod_emp, "codori": cod_ori, "numorp": num_op},
                )
                colunas = [coluna[0].lower() for coluna in cursor.description]
                componentes = [
                    {
                        "codcmp": comp["codcmp"],
                        "descmp": comp["despro"],
                        "codfam": comp["codfam"],
                        "codder": comp["codder"],
                        "unimed": comp["unimed"],
                        "qtdprv": comp["qtdprv"],
                        "qtduti": comp["qtduti"],
                        "receita": comp["receita"],
                        "atual": comp["atual"],
                        "classe_atual": classe_comparativo_percentual(
                            comp["receita"], comp["atual"]
                        ),
                        "bxaorp": comp["bxaorp"],
                    }
                    for comp in (dict(zip(colunas, linha, strict=False)) for linha in cursor)
                ]

                cursor.execute(
                    """
                    SELECT oop.seqrot, oop.codetg, oop.codopr, opr.desopr, cre.codcre, cre.descre,
                           oop.qtdprv, oop.qtdre1, oop.qtdrfg, oop.dtrini, oop.dtrfim, oop.horini, oop.horfim, oop.movorp
                    FROM e900oop oop
                    JOIN e720opr opr ON oop.codemp=opr.codemp AND oop.codopr=opr.codopr
                    JOIN e725cre cre ON oop.codemp=cre.codemp AND oop.codcre=cre.codcre
                    WHERE oop.codemp=:codemp AND oop.codori=:codori AND oop.numorp=:numorp
                    ORDER BY oop.codetg, oop.seqrot
                    """,
                    {"codemp": cod_emp, "codori": cod_ori, "numorp": num_op},
                )
                colunas = [coluna[0].lower() for coluna in cursor.description]
                for oper in (dict(zip(colunas, linha, strict=False)) for linha in cursor):
                    operacoes.append(
                        {
                            "seqrot": oper["seqrot"],
                            "codetg": oper["codetg"],
                            "codopr": oper["codopr"],
                            "desopr": oper["desopr"],
                            "codcre": oper["codcre"],
                            "descre": oper["descre"],
                            "qtdprv": oper["qtdprv"],
                            "qtdre1": oper["qtdre1"],
                            "qtdrfg": oper["qtdrfg"],
                            "dtinicio": "NÃO MOVIMENTA"
                            if oper["movorp"] == "N"
                            else format_data_hora(oper["dtrini"], oper["horini"]),
                            "dtfim": "NÃO MOVIMENTA"
                            if oper["movorp"] == "N"
                            else format_data_hora(oper["dtrfim"], oper["horfim"]),
                        }
                    )

                cursor.execute(
                    """
                    SELECT eoq.seqeoq, eoq.codetg, eoq.seqrot, eoq.codopr, opr.desopr, ope.nomope,
                           eoq.qtdre1, eoq.qtdrfg, eoq.codlot, eoq.datini, eoq.horini, eoq.datrea, eoq.horrea, eoq.numcad
                    FROM e900eoq eoq
                    JOIN e720opr opr ON eoq.codemp=opr.codemp AND eoq.codopr=opr.codopr
                    JOIN e906ope ope ON eoq.codemp=ope.codemp AND eoq.numcad=ope.numcad
                    WHERE eoq.codemp=:codemp AND eoq.codori=:codori AND eoq.numorp=:numorp AND eoq.codetg=:codetg
                    ORDER BY eoq.seqeoq DESC
                    """,
                    {"codemp": cod_emp, "codori": cod_ori, "numorp": num_op, "codetg": cod_etg},
                )
                colunas = [coluna[0].lower() for coluna in cursor.description]
                historico = [
                    {
                        "seqeoq": hist["seqeoq"],
                        "codetg": hist["codetg"],
                        "seqrot": hist["seqrot"],
                        "codopr": hist["codopr"],
                        "desopr": hist["desopr"],
                        "nomope": hist["nomope"],
                        "qtdre1": hist["qtdre1"],
                        "qtdrfg": hist["qtdrfg"],
                        "codelote": hist["codlot"],
                        "dtinicio": format_data_hora(hist["datini"], hist["horini"]),
                        "dtfim": format_data_hora(hist["datrea"], hist["horrea"]),
                        "numcad": hist["numcad"],
                    }
                    for hist in (dict(zip(colunas, linha, strict=False)) for linha in cursor)
                ]

                if "remover_sequencia" in request.POST:
                    seq_id = request.POST.get("sequencia_id")
                    if status_seq == "Finalizada" and seq_id:
                        with transaction.atomic():
                            recurso_bloqueado = (
                                Recurso.objects.select_for_update().filter(pk=recurso_id).first()
                            )
                            if not recurso_bloqueado:
                                erro = "Recurso inválido para remover a sequência."
                            else:
                                periodos_abertos = list(
                                    LogTrocaOPAtiva.objects.select_for_update()
                                    .filter(recurso=recurso_bloqueado, horario_saida__isnull=True)
                                    .select_related(
                                        "recurso__centro_recurso__setor__departamento__filial__empresa"
                                    )
                                    .order_by("id")
                                )
                                if len(periodos_abertos) > 1:
                                    erro = (
                                        "Este recurso possui mais de uma OP ativa. A remoção deve ser tratada "
                                        "pelo fluxo de alocação de OPs."
                                    )
                                elif (
                                    periodos_abertos
                                    and periodos_abertos[0].codigo_barra == codbar
                                    and (
                                        ParadaMaquina.objects.select_for_update()
                                        .filter(recurso=recurso_bloqueado, fim__isnull=True)
                                        .exists()
                                        or recurso_tem_parada_bloqueante(recurso_bloqueado)
                                    )
                                ):
                                    erro = (
                                        "Não é possível remover a sequência da OP ativa enquanto houver parada "
                                        "aberta ou pendente de justificativa."
                                    )
                                else:
                                    Sequenciamento.objects.filter(
                                        id=seq_id,
                                        recurso=recurso_bloqueado,
                                    ).delete()
                                    if (
                                        periodos_abertos
                                        and periodos_abertos[0].codigo_barra == codbar
                                    ):
                                        LogTrocaOPAtiva.objects.filter(
                                            pk=periodos_abertos[0].pk
                                        ).update(
                                            horario_saida=timezone.now().replace(microsecond=0)
                                        )
                                    return redirect(
                                        f"{request.path}?empresa={empresa_id}&centro={centro_id}&recurso={recurso_id}"
                                    )

                if "validar_operador" in request.POST:
                    numcad_post = request.POST.get("numcad")
                    if numcad_post and chave_numcad and chave_nome:
                        nome_valido = valida_operador(cursor, cod_emp, numcad_post)
                        if nome_valido:
                            numcad_sessao, nome_operador_sessao = numcad_post, nome_valido
                            request.session[chave_numcad] = numcad_post
                            request.session[chave_nome] = nome_valido
                            if recurso_selecionado:
                                ParadaMaquina.objects.filter(
                                    recurso=recurso_selecionado,
                                    fim__isnull=True,
                                ).update(operador=str(numcad_post).strip())
                        else:
                            erro = f"Operador {numcad_post} não encontrado na empresa {cod_emp}."
                    elif not numcad_post:
                        erro = "Informe o ID do Operador."
                    else:
                        erro = (
                            "Recurso ou identificador de aba não encontrado para validar operador."
                        )

                if "trocar_operador" in request.POST and chave_numcad and chave_nome:
                    if recurso_tem_parada_bloqueante(recurso_selecionado):
                        erro = "Não é possível trocar o operador enquanto houver parada aberta."
                    else:
                        request.session.pop(chave_numcad, None)
                        request.session.pop(chave_nome, None)
                        numcad_sessao, nome_operador_sessao = None, None

                if "trocar_op_ativa" in request.POST and recurso_selecionado:
                    if recurso_tem_parada_bloqueante(recurso_selecionado):
                        erro = "Não é possível trocar a OP enquanto houver parada bloqueante."
                    else:
                        numcad_troca = request.POST.get("numcad") or numcad_sessao
                        try:
                            id_operador_troca = int(numcad_troca) if numcad_troca else None
                        except (TypeError, ValueError):
                            id_operador_troca = None
                        nome_operador_troca = (
                            valida_operador(cursor, cod_emp, numcad_troca) if numcad_troca else None
                        )
                        if not id_operador_troca or not nome_operador_troca:
                            erro = "Operador não validado."

                if "trocar_op_ativa" in request.POST and recurso_selecionado and not erro:
                    op_anterior_codbar = op_ativa_recurso
                    horario_troca = timezone.now().replace(microsecond=0)
                    _, ori_troca, op_troca, etg_troca, seq_troca = decode_cod_barras(codbar)
                    try:
                        trocar_periodo_produtivo_fluxo_unico(
                            recurso=recurso_selecionado,
                            usuario=request.user,
                            origem=ori_troca,
                            op=op_troca,
                            estagio=int(etg_troca),
                            seqrot=int(seq_troca),
                            horario_troca=horario_troca,
                            id_operador=id_operador_troca,
                        )
                    except ValueError as excecao:
                        erro = str(excecao)
                    else:
                        if op_anterior_codbar:
                            notifica_atualizacao(op_anterior_codbar)
                        notifica_atualizacao(codbar)
                        return redirect(
                            f"{request.path}?empresa={empresa_id}&centro={centro_id}&recurso={recurso_id}&codbar={codbar}"
                        )

                if "apontar_componente" in request.POST:
                    codigo_integrador_centro = (
                        recurso_selecionado.centro_recurso.codigo_integrador
                        if recurso_selecionado and recurso_selecionado.centro_recurso
                        else ""
                    )
                    if recurso_tem_parada_bloqueante(recurso_selecionado):
                        erro = "Existe parada em aberto para este recurso. Justifique a parada antes de apontar."
                    elif not recurso_selecionado or not codigo_integrador_centro:
                        erro = "Centro de recurso sem código integrador."
                    elif op_ativa_recurso != codbar:
                        erro = "Esta OP não é a ativa no recurso. Clique em 'Trocar OP Ativa' primeiro."

                    num_cad = request.POST.get("numcad")
                    lote_componente = (request.POST.get("lote_componente") or "").strip().upper()
                    if not erro:
                        nome_valido = valida_operador(cursor, cod_emp, num_cad) if num_cad else None
                        if not num_cad or not nome_valido:
                            erro = "Operador não validado."
                        elif len(lote_componente) < 4:
                            erro = "Informe um lote do componente com pelo menos 4 caracteres."

                    if not erro:
                        cursor.execute(
                            "SELECT COUNT(*) FROM e900oop WHERE codemp=:codemp AND codori=:codori AND numorp=:numorp AND codetg=:codetg AND seqrot=:seqrot",
                            {
                                "codemp": cod_emp,
                                "codori": cod_ori,
                                "numorp": num_op,
                                "codetg": cod_etg,
                                "seqrot": seq_rot,
                            },
                        )
                        if not cursor.fetchone()[0]:
                            erro = "Estágio não encontrado."

                    if not erro:
                        agora = timezone.now().replace(microsecond=0)
                        # dat_mov/hor_mov são CharField enviados ao ERP: precisam do
                        # horário local (America/Sao_Paulo), não do UTC que
                        # timezone.now() retorna com USE_TZ=True.
                        agora_local = timezone.localtime(agora)
                        apont_comp, componente_criado = salvar_log_componente(
                            cod_emp=cod_emp,
                            origem=cod_ori,
                            num_op=num_op,
                            cod_etg=cod_etg,
                            seq_rot=seq_rot,
                            num_cad=num_cad,
                            codigo_integrador=codigo_integrador_centro or "",
                            lote=lote_componente,
                            dat_mov=agora_local.strftime("%d/%m/%Y"),
                            hor_mov=agora_local.strftime("%H:%M:%S"),
                            data_hora=agora,
                            recurso=recurso_selecionado,
                            usuario=request.user,
                        )
                        if apont_comp and componente_criado:
                            if not PROCESSAMENTO_APONTAMENTO_COMPONENTES_LOCK.locked():
                                reservados = reservar_componentes_para_envio(
                                    ApontamentoComponente.objects.filter(pk=apont_comp.pk)
                                )
                                if reservados.exists():
                                    disparar_envio_componentes([apont_comp.pk])
                                    apont_comp.log = "Aguardando processamento background"
                            messages.success(
                                request,
                                f"Lote {lote_componente} registrado para apontamento proporcional.",
                            )
                            notifica_atualizacao_atrasada(codbar, 1)
                        elif apont_comp:
                            erro = f"Lote {lote_componente} já registrado na empresa {cod_emp}."
                        else:
                            erro = "Não foi possível registrar o lote do componente."

                if centro_id:
                    status_integracao = {
                        0: "Pendente",
                        2: "Processando",
                    }
                    integracoes_pendentes = [
                        {
                            "numcad": item.numcad,
                            "lote": item.lote,
                            "datmov": item.datmov,
                            "hormov": item.hormov,
                            "log": item.log,
                            "data_hora": item.data_hora,
                            "status": status_integracao.get(item.status, item.status),
                        }
                        for item in ApontamentoComponente.objects.filter(
                            recurso__centro_recurso_id=centro_id,
                            codemp=int(cod_emp),
                            origem=cod_ori,
                            numorp=int(num_op),
                            codetg=int(cod_etg),
                            seqrot=int(seq_rot),
                            status__in=[0, 2],
                        ).order_by("-data_hora", "-id")
                    ]

    except Exception:
        logger.exception("Falha ao processar apontamento V2")
        erro, dados_op, componentes, operacoes, historico, integracoes_pendentes = (
            "Não foi possível consultar os dados no ERP.",
            None,
            [],
            [],
            [],
            [],
        )

    if request.method == "POST" and "apontar_componente" in request.POST:
        request.session["ultima_resposta_componente"] = {"mensagem": resposta, "erro": erro}
        redirect_url = f"{request.path}?empresa={empresa_id}&centro={centro_id}&recurso={recurso_id}&codbar={codbar}"
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"redirect_url": redirect_url, "redirect_immediate": bool(erro)})
        return redirect(redirect_url)

    sequencias = (
        Sequenciamento.objects.filter(recurso_id=recurso_id).order_by("ordenacao")
        if recurso_id
        else []
    )
    seq_atual_id = next((s.id for s in sequencias if s.codigo_barra == codbar), None)
    contexto_paradas = contexto_parada_recurso(recurso_selecionado)
    pode_abrir_parada_manual = bool(
        recurso_selecionado
        and op_ativa_recurso
        and nome_operador_sessao
        and not tem_multiplas_ops_ativas
        and not ParadaMaquina.objects.filter(recurso=recurso_selecionado, fim__isnull=True).exists()
        and usuario_pode_abrir_parada_manual(request.user, recurso_selecionado)
    )

    return render(
        request,
        "producao/apontamentos_v2.html",
        {
            "empresas": empresas,
            "empresa_id": empresa_id,
            "centros": centros,
            "centro_id": centro_id,
            "recursos": recursos,
            "recurso_id": recurso_id,
            "dados_op": dados_op,
            "componentes": componentes,
            "operacoes": operacoes,
            "historico": historico,
            "erro": erro,
            "resposta": resposta,
            "codbar": codbar,
            "numcad": numcad_sessao,
            "nome_operador": nome_operador_sessao,
            "habilitar_apontamento": bool(nome_operador_sessao and recurso_id),
            "pode_apontar": pode_apontar,
            "codetg": codetg,
            "seqrot": seqrot,
            "status_seq": status_seq,
            "sequencias": sequencias,
            "sequencia_atual_id": seq_atual_id,
            "recurso_selecionado": recurso_selecionado,
            "op_ativa_recurso": op_ativa_recurso,
            "tem_multiplas_ops_ativas": tem_multiplas_ops_ativas,
            "fluxo_base_op_unica": recurso_usa_fluxo_base_op_unica(recurso_selecionado),
            "operador_validado": bool(
                recurso_id
                and request.session.get(f"numcad_operador_{recurso_id}")
                and request.session.get(f"nome_operador_{recurso_id}")
            ),
            "pode_abrir_parada_manual": pode_abrir_parada_manual,
            "integracoes_pendentes": integracoes_pendentes,
            **contexto_paradas,
        },
    )
