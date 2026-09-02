import asyncio
import logging
import threading
import time
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import close_old_connections, connections, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import CentroRecurso, Empresa, Recurso, Tara
from producao.models import Apontamento, LogTrocaOPAtiva, ParadaMaquina, Sequenciamento
from producao.services.altera_apontamento import (
    corrigir_quantidade_lote,
    incrementar_lote,
    normalizar_lote_numerico,
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
from producao.views.logs_apontamentos import processar_logs_pendentes
from SIGMA.integracoes.oracle import cursor_oracle_erp

logger = logging.getLogger(__name__)


def disparar_coleta_peso(recurso_id_apont, ids_apont_log):
    # Coleta peso da balança e atualiza log de apontamento (Auditoria)
    close_old_connections()
    try:
        peso_balanca = 0
        tempo_coleta = 15
        try:
            recurso = Recurso.objects.select_related(
                "parametros_recurso",
                "centro_recurso__parametros_centro_recurso",
                "centro_recurso__setor__departamento__filial__parametros_filial",
            ).get(id=recurso_id_apont)
            tempo_coleta = recurso.get_parametros_efetivos()["tempo_sem_comunicacao_manual"]
        except Exception:
            pass

        try:
            camada_canal = get_channel_layer()
            canal_temp = async_to_sync(camada_canal.new_channel)()
            grupo = f"balanca_{recurso_id_apont}"
            async_to_sync(camada_canal.group_add)(grupo, canal_temp)

            inicio_tempo = time.time()
            while time.time() - inicio_tempo < tempo_coleta:
                try:
                    msg = async_to_sync(asyncio.wait_for)(
                        camada_canal.receive(canal_temp), timeout=1.0
                    )
                    if msg.get("type") == "balanca_update" and msg.get("balanca", 0) > 0:
                        peso_balanca = msg["balanca"]
                        break
                except TimeoutError, Exception:
                    continue

            async_to_sync(camada_canal.group_discard)(grupo, canal_temp)
        except Exception:
            pass

        # Atualiza os logs de apontamento com o peso da balança (apenas para auditoria)
        if ids_apont_log:
            try:
                Apontamento.objects.filter(id__in=ids_apont_log).update(balanca=peso_balanca)
            except Exception as e:
                print(f"Erro ao atualizar peso nos logs de apontamento: {e}")
    finally:
        connections.close_all()


def format_data_hora(data, minutos):
    # Formata data e hora vinda do Oracle
    if not data or (hasattr(data, "year") and data.year == 1900):
        return ""
    if minutos in (None, 0):
        return data.strftime("%d/%m/%Y")
    h, mi = divmod(int(minutos), 60)
    return f"{data.strftime('%d/%m/%Y')} {h:02d}:{mi:02d}"


def valida_operador(cursor, cod_emp, num_cad):
    # Busca operador ativo no Oracle
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
    # Extrai dados do código de barras
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


def salvar_log_apontamento(
    cod_emp,
    origem,
    num_op,
    cod_etg,
    seq_rot,
    num_cad,
    qtd_prod,
    qtd_ref,
    lote,
    c_integrador,
    dat_mov,
    hor_mov,
    data_hora,
    bobina=None,
    origem_peso=None,
    recurso=None,
    usuario=None,
):
    # Salva registro na tabela de apontamento local
    if (qtd_prod or 0) <= 0 and (qtd_ref or 0) <= 0:
        return None

    try:
        kwargs = {
            "codemp": int(cod_emp),
            "origem": origem,
            "numorp": int(num_op),
            "codetg": int(cod_etg),
            "seqrot": int(seq_rot),
            "numcad": int(num_cad),
            "qtdre1": float(qtd_prod),
            "qtdrfg": float(qtd_ref),
            "lote": lote,
            "log": "Registro salvo",
            "status": 0,
            "recurso": recurso,
            "usuario": usuario,
            "codigo_integrador": c_integrador,
            "datmov": dat_mov,
            "hormov": hor_mov,
            "data_hora": data_hora.replace(microsecond=0),
            "datger": data_hora.replace(microsecond=0),
            "bobina": bobina,
            # origem_peso é NOT NULL no banco; None explícito no create não
            # aciona o default do model e violaria a coluna, descartando o
            # registro de refugo puro no except logo abaixo.
            "origem_peso": origem_peso or "",
        }

        apont = Apontamento.objects.create(**kwargs)
        return apont
    except Exception:
        # O apontamento não pode sumir em silêncio: sem o traceback no log,
        # a fila perde registro sem deixar pista para reprocessamento.
        logger.exception("Falha ao salvar registro de apontamento local")
        return None


def notifica_atualizacao(codbar):
    # Atualiza as telas abertas na mesma OP, mesmo que estejam em recursos distintos.
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(f"op_{codbar}", {"type": "refresh_page"})
    except Exception:
        pass


def notifica_atualizacao_atrasada(codbar, atraso_segundos=10):
    # Usada após apontamento normal, para respeitar a espera antes de atualizar outras telas.
    try:
        time.sleep(max(int(atraso_segundos), 0))
        notifica_atualizacao(codbar)
    except Exception:
        pass


def buscar_log_op_ativa(recurso_id):
    # Busca a OP ativa atual do recurso a partir do log aberto, sem depender de campo no cadastro.
    if not recurso_id:
        return None
    return (
        LogTrocaOPAtiva.objects.filter(recurso_id=recurso_id, horario_saida__isnull=True)
        .order_by("-horario_troca")
        .first()
    )


def buscar_ultima_bobina_apontada_erp(codemp, codcre):
    # Recupera no ERP a última bobina já apontada para o recurso, usada na validação e no select de bobinas.
    try:
        with cursor_oracle_erp() as cur_bob:
            cur_bob.execute(
                """
                    SELECT MAX(usu_numbob)
                    FROM E900EOQ
                    WHERE codemp = :codemp
                      AND codcre = :codcre
                      AND NVL(usu_numbob, 0) > 0
                """,
                {
                    "codemp": int(codemp or 1),
                    "codcre": int(codcre),
                },
            )
            row_bob = cur_bob.fetchone()
            if row_bob and row_bob[0]:
                return int(row_bob[0])
    except Exception as e:
        print(f"Erro ao buscar bobina ERP: {e}")
    return 0


def calcular_bobinas_disponiveis(bobina_atual_rec, ultima_bobina_apontada):
    # Lista vazia quando a bobina atual está atrás da última já apontada
    # (sensor/contador com erro: reset, estouro fora de sincronia etc.).
    # É proposital: o template oferece "Sem número de bobina" em vez de
    # repetir um valor que a validação de duplicidade rejeitaria.
    if bobina_atual_rec <= 0:
        return []
    limite_inferior = ultima_bobina_apontada + 1 if ultima_bobina_apontada > 0 else bobina_atual_rec
    # Evita carregar milhares de opções quando o último apontamento
    # registrado é antigo. A lista sempre inclui a bobina atual.
    limite_inferior = max(limite_inferior, bobina_atual_rec - 99)
    if bobina_atual_rec < limite_inferior:
        return []
    return list(range(bobina_atual_rec, limite_inferior - 1, -1))


def resolver_bobina_apontamento(
    bobina_post, historico_erp_bruto, cod_etg, seq_rot, num_cad, bobina_recurso
):
    # bobina_post vem de request.POST.get("bobina_selecionada"): None quando o
    # campo não foi enviado (mantém a busca antiga no histórico ERP/recurso);
    # "" quando o operador escolheu "Sem número de bobina" (sensor com erro,
    # não trava o apontamento); dígitos quando uma bobina real foi escolhida.
    if bobina_post is None:
        hist_atual_erp = next(
            (
                x
                for x in historico_erp_bruto
                if x["codetg"] == int(cod_etg)
                and x["seqrot"] == int(seq_rot)
                and int(x.get("numcad", 0) or 0) == int(num_cad or 0)
            ),
            None,
        )
        return (
            (
                int(hist_atual_erp["numbob"])
                if hist_atual_erp and hist_atual_erp.get("numbob")
                else 0
            )
            or bobina_recurso
            or 0
        )
    if bobina_post == "":
        return None
    return int(bobina_post)


@login_required
def apontamentos_view(request):
    # Orquestra toda a tela de apontamento: filtros, leitura da OP, troca de OP ativa, apontamento e correção.
    dados_op, componentes, operacoes, historico = None, [], [], []
    erro, codetg, seqrot, status_seq = None, "", "", ""
    apontamento_concluido = False

    codbar = (request.POST.get("codbar") or request.GET.get("codbar", "")).strip()
    empresa_id = request.POST.get("empresa", request.GET.get("empresa", ""))
    centro_id = request.POST.get("centro", request.GET.get("centro", ""))
    recurso_id = request.POST.get("recurso", request.GET.get("recurso", ""))
    pode_apontar = request.user.is_staff or request.user.has_perm("producao.pode_apontar")
    pode_corrigir_lote = request.user.is_staff or request.user.has_perm(
        "producao.pode_corrigir_lote"
    )

    acoes_restritas = {
        "validar_operador",
        "trocar_operador",
        "trocar_op_ativa",
        "enviar_apontamento",
    }
    if request.method == "POST" and acoes_restritas.intersection(request.POST) and not pode_apontar:
        messages.error(request, "Você não possui permissão para apontar.")
        return redirect(
            f"{request.path}?empresa={empresa_id}&centro={centro_id}&recurso={recurso_id}&codbar={codbar}"
        )

    # Recupera última resposta da sessão
    resposta_data = request.session.pop("ultima_resposta", None)
    resposta, acao = (
        (resposta_data.get("mensagem"), resposta_data.get("acao"))
        if resposta_data
        else (None, None)
    )
    erro = resposta_data.get("erro") if resposta_data else erro

    # Busca empresas acessíveis
    empresas = empresas_visiveis_apontamento(request.user)

    # Seleção automática de empresa no primeiro acesso
    if not empresa_id and empresas.exists():
        empresa_id = str(empresas.first().id)

    # Se houver codbar, os filtros já foram resolvidos pelo apontamento_base.py
    # No entanto, mantemos uma resolução local mínima para compatibilidade e POSTs
    if codbar:
        try:
            _, cod_ori_bar, num_op_bar, cod_etg_bar, seq_rot_bar = decode_cod_barras(codbar)
            codetg, seqrot = cod_etg_bar, seq_rot_bar
        except Exception:
            pass

    # Dado para select (Sincronizado com apontamento_base.py)
    # Recalcula ou usa valor recebido para manter independência da view

    # Busca empresa acessível (Sincronizado com base)
    empresas = empresas_visiveis_apontamento(request.user)

    # Se a view foi chamada pelo base, as variáveis já devem estar no GET/POST
    # Filtros e listas para renderização da barra lateral no template
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

    # Busca dados do recurso selecionado
    taras_vinculadas, aponta_refugo, recurso_selecionado = [], True, None
    parametros_apontamento = {
        "tempo_sem_comunicacao_manual": 15,
        "limite_apontamento_minimo": 0,
        "limite_apontamento_maximo": 4000,
    }
    if recurso_id:
        try:
            recurso_selecionado = (
                recursos_visiveis_apontamento(request.user)
                .select_related(
                    "parametros_recurso",
                    "centro_recurso__parametros_centro_recurso",
                    "centro_recurso__setor__departamento__filial__parametros_filial",
                )
                .get(id=recurso_id, centro_recurso_id=centro_id)
            )
            parametros_apontamento = recurso_selecionado.get_parametros_efetivos()
            aponta_refugo = parametros_apontamento["aponta_refugo"]
            taras_vinculadas = Tara.objects.filter(tara_recursos__recurso_id=recurso_id).order_by(
                "tara"
            )
        except Exception:
            pass

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
            "Este recurso possui mais de uma OP ativa. As ações da Apontamentos V1 exigem uma única OP ativa.",
        )
        return redirect(
            f"{request.path}?empresa={empresa_id}&centro={centro_id}&recurso={recurso_id}&codbar={codbar}"
        )

    # Resolve dados da OP no ERP
    # Lógica de correção de lote se for POST do modal de correção
    if (
        request.method == "POST"
        and "lote" in request.POST
        and "qtdre1" in request.POST
        and "enviar_apontamento" not in request.POST
    ):
        if not (request.user.has_perm("producao.pode_corrigir_lote") or request.user.is_staff):
            erro = "Você não tem permissão para corrigir lotes."
        else:
            lote_id = request.POST.get("lote")
            qtdre1_corrigir = request.POST.get("qtdre1")

            try:
                qtdre1_corrigir = (
                    float(qtdre1_corrigir.replace(",", ".")) if qtdre1_corrigir else 0.0
                )
                erp_params = {
                    "codemp": request.POST.get("codemp_erp"),
                    "codori": request.POST.get("codori_erp"),
                    "numorp": request.POST.get("numorp_erp"),
                    "codetg": request.POST.get("codetg_erp"),
                    "seqeoq": request.POST.get("seqeoq_erp"),
                    "qtd_original_linha": request.POST.get("qtd_original_linha"),
                    "qtd_total_lote": request.POST.get("qtd_total_lote"),
                    "tipo_ajuste": request.POST.get("tipo_ajuste"),
                    "acao_correcao": request.POST.get("acao_correcao"),
                }

                success, logs_list = corrigir_quantidade_lote(
                    lote_id,
                    qtdre1_corrigir,
                    request.user,
                    erp_params=erp_params,
                )
                if success:
                    for msg in logs_list:
                        messages.success(request, msg)
                else:
                    for msg in logs_list:
                        if any(palavra in msg for palavra in ["Falha", "Erro", "Aviso"]):
                            messages.error(request, msg)
                        else:
                            messages.success(request, msg)

                # Após corrigir, recarrega a página para refletir mudanças se necessário
                return redirect(
                    f"{request.path}?empresa={empresa_id}&centro={centro_id}&recurso={recurso_id}&codbar={codbar}"
                )
            except ValueError:
                erro = erro or "Quantidade inválida para correção."

    chave_numcad = f"numcad_operador_{recurso_id}" if recurso_id else None
    chave_nome = f"nome_operador_{recurso_id}" if recurso_id else None
    numcad_sessao = request.session.get(chave_numcad) if chave_numcad else None
    nome_operador_sessao = request.session.get(chave_nome) if chave_nome else None

    def limpar_operador_validado():
        nonlocal numcad_sessao, nome_operador_sessao
        if chave_numcad and chave_nome:
            request.session.pop(chave_numcad, None)
            request.session.pop(chave_nome, None)
            request.session.modified = True
            request.session.save()
        numcad_sessao = None
        nome_operador_sessao = None

    try:
        if codbar:
            cod_emp, cod_ori, num_op, cod_etg, seq_rot = decode_cod_barras(codbar)
            with cursor_oracle_erp() as cursor:
                # Dados principais da OP
                cursor.execute(
                    """
                    SELECT cop.codori, cop.numorp, cop.sitorp, cop.qtdprv, cop.qtdre1,
                           TO_CHAR(cop.dtrini, 'DD/MM/YYYY') dtrini, TO_CHAR(cop.dtrfim, 'DD/MM/YYYY') dtrfim,
                           qdo.codpro, pro.despro, qdo.codder, qdo.unimed, cop.usu_qtdbob
                    FROM e900cop cop
                    JOIN e900qdo qdo ON cop.codemp=qdo.codemp AND cop.codori=qdo.codori AND cop.numorp=qdo.numorp AND cop.codpro=qdo.codpro
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
                        "usu_qtdbob": linha_op["usu_qtdbob"],
                    }
                else:
                    erro, codbar = f"OP {cod_ori}/{num_op} não encontrada.", ""

                # Componentes da OP
                cursor.execute(
                    """
                    SELECT cmo.codcmp, pro.despro, cmo.codder, cmo.unimed, cmo.qtdprv, cmo.qtduti, cmo.bxaorp
                    FROM e900cmo cmo
                    JOIN e075pro pro ON cmo.codemp=pro.codemp AND cmo.codcmp=pro.codpro
                    WHERE cmo.codemp=:codemp AND cmo.codori=:codori AND cmo.numorp=:numorp
                    ORDER BY cmo.codcmp
                """,
                    {"codemp": cod_emp, "codori": cod_ori, "numorp": num_op},
                )
                colunas = [coluna[0].lower() for coluna in cursor.description]
                componentes = [
                    {
                        "codcmp": comp["codcmp"],
                        "descmp": comp["despro"],
                        "codder": comp["codder"],
                        "unimed": comp["unimed"],
                        "qtdprv": comp["qtdprv"],
                        "qtduti": comp["qtduti"],
                        "bxaorp": comp["bxaorp"],
                    }
                    for comp in (dict(zip(colunas, linha, strict=False)) for linha in cursor)
                ]

                # Operações da OP
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

                # Histórico do ERP
                historico_erp_bruto = []
                cursor.execute(
                    """
                    SELECT eoq.seqeoq, eoq.codetg, eoq.seqrot, eoq.codopr, opr.desopr, ope.nomope,
                           eoq.qtdre1, eoq.qtdrfg, eoq.codlot, eoq.USU_Numbob,
                           eoq.datini, eoq.horini, eoq.datrea, eoq.horrea, eoq.numcad
                    FROM e900eoq eoq
                    JOIN e720opr opr ON eoq.codemp = opr.codemp AND eoq.codopr = opr.codopr
                    JOIN e906ope ope ON eoq.codemp = ope.codemp AND eoq.numcad = ope.numcad
                    WHERE eoq.codemp = :codemp AND eoq.codori = :codori AND eoq.numorp = :numorp AND eoq.codetg = :codetg
                    ORDER BY eoq.seqeoq desc
                """,
                    {"codemp": cod_emp, "codori": cod_ori, "numorp": num_op, "codetg": cod_etg},
                )
                colunas = [coluna[0].lower() for coluna in cursor.description]
                for hist in (dict(zip(colunas, linha, strict=False)) for linha in cursor):
                    historico_erp_bruto.append(
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
                            "numbob": hist["usu_numbob"],
                            "datini": hist["datini"],
                            "datrea": hist["datrea"],
                            "dtinicio": format_data_hora(hist["datini"], hist["horini"]),
                            "dtfim": format_data_hora(hist["datrea"], hist["horrea"]),
                            "numcad": hist["numcad"],
                        }
                    )
                historico = historico_erp_bruto

                # Identifica estado atual da sequência (Sempre baseado na Situação da OP)
                if not linha_op:
                    status_seq = "Sequência inexistente"
                    operacoes = []
                else:
                    status_seq = dados_op.get("sitorp", "Parada")

                # Remove sequência do painel lateral
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

                # Valida operador na empresa atual
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
                            request.session.pop(chave_numcad, None)
                            request.session.pop(chave_nome, None)
                            numcad_sessao, nome_operador_sessao = None, None
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

                # Processa troca de OP ativa no recurso
                if "trocar_op_ativa" in request.POST and recurso_selecionado:
                    if recurso_tem_parada_bloqueante(recurso_selecionado):
                        erro = "Não é possível trocar a OP enquanto houver parada bloqueante."
                    else:
                        numcad_troca = request.POST.get("numcad") or numcad_sessao
                        try:
                            id_operador_troca = int(numcad_troca) if numcad_troca else None
                        except TypeError, ValueError:
                            id_operador_troca = None
                        nome_operador_troca = (
                            valida_operador(cursor, cod_emp, numcad_troca) if numcad_troca else None
                        )
                        if not id_operador_troca or not nome_operador_troca:
                            erro = "Operador não validado."

                    if not erro:
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

                codigo_integrador_centro = (
                    recurso_selecionado.centro_recurso.codigo_integrador
                    if recurso_selecionado and recurso_selecionado.centro_recurso
                    else ""
                )

                ultima_bobina_apontada_recurso = 0
                if recurso_selecionado and codigo_integrador_centro:
                    ult_apont_local = (
                        Apontamento.objects.filter(
                            codigo_integrador=codigo_integrador_centro,
                            status=Apontamento.Status.NAO_INTEGRADO,
                            bobina__isnull=False,
                        )
                        .order_by("-bobina")
                        .first()
                    )

                    if ult_apont_local and ult_apont_local.bobina:
                        ultima_bobina_apontada_recurso = int(ult_apont_local.bobina)
                    else:
                        ultima_bobina_apontada_recurso = buscar_ultima_bobina_apontada_erp(
                            recurso_selecionado.centro_recurso.setor.departamento.filial.empresa.codemp,
                            codigo_integrador_centro,
                        )

                # Processa apontamento de produção via formulário (Nova lógica: Apenas Fim)
                if "enviar_apontamento" in request.POST:
                    if recurso_tem_parada_bloqueante(recurso_selecionado):
                        erro = "Existe parada em aberto para este recurso. Justifique a parada antes de apontar."
                    elif not recurso_selecionado or not codigo_integrador_centro:
                        erro = "Centro de recurso sem código integrador."
                    elif op_ativa_recurso != codbar:
                        erro = "Esta OP não é a ativa no recurso. Por favor, clique em 'Trocar OP Ativa' primeiro."

                    if not erro:
                        num_cad = request.POST.get("numcad")
                        nome_valido = valida_operador(cursor, cod_emp, num_cad) if num_cad else None
                        if not num_cad or not nome_valido:
                            erro = "Operador não validado."
                        else:
                            numcad_sessao, nome_operador_sessao = num_cad, nome_valido
                            try:
                                # Obtém quantidades produzidas e de refugo
                                qtd_prod = float(request.POST.get("qtdre1") or 0)
                                qtd_ref = (
                                    float(request.POST.get("qtdrfg") or 0) if aponta_refugo else 0.0
                                )
                                # Valida se o peso foi autorizado pelo modal (apenas se houver produção)
                                autorizado = request.POST.get("autorizado_modal") == "1"
                                if qtd_prod > 0 and not autorizado:
                                    erro = "A quantidade deve ser capturada via modal de peso."
                            except TypeError, ValueError:
                                erro, qtd_prod, qtd_ref = "Quantidade inválida.", 0, 0

                            if not erro:
                                origem_peso_post = request.POST.get("origem_peso", "")
                                # Valida limites de quantidade permitidos
                                limite_min = parametros_apontamento["limite_apontamento_minimo"]
                                limite_max = parametros_apontamento["limite_apontamento_maximo"]
                                qtd_total = qtd_prod + qtd_ref
                                if qtd_total < limite_min or qtd_total > limite_max:
                                    erro = f"Quantidade total deve ficar entre {limite_min:g} e {limite_max:g}."
                                else:
                                    # Valida existência da operação no ERP
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
                                    elif not valida_operador(cursor, cod_emp, num_cad):
                                        erro = "Operador inválido."
                                    else:
                                        agora, cod_rec_int = (
                                            timezone.now().replace(microsecond=0),
                                            codigo_integrador_centro or "",
                                        )
                                        # datmov/hormov são CharField enviados ao ERP: precisam do
                                        # horário local (America/Sao_Paulo), não do UTC que
                                        # timezone.now() retorna com USE_TZ=True.
                                        agora_local = timezone.localtime(agora)
                                        bobina_apont = resolver_bobina_apontamento(
                                            request.POST.get("bobina_selecionada"),
                                            historico_erp_bruto,
                                            cod_etg,
                                            seq_rot,
                                            num_cad,
                                            recurso_selecionado.bobina,
                                        )
                                        if bobina_apont is not None and int(bobina_apont) <= int(
                                            ultima_bobina_apontada_recurso or 0
                                        ):
                                            erro = f"A bobina {bobina_apont} já foi apontada para este recurso."
                                        else:
                                            # Regra de bobinas múltiplas mantida
                                            u_q_bob = (
                                                int(dados_op.get("usu_qtdbob", 0) or 0)
                                                if dados_op
                                                else 0
                                            )
                                            ids_apont_criados = []

                                            if u_q_bob > 1 and (qtd_prod > 0 or qtd_ref > 0):
                                                # Distribui peso entre bobinas da OP
                                                q_tot = int(round(qtd_prod * 100))
                                                f_tot = int(round(qtd_ref * 100))
                                                q_rat, r_rat = divmod(q_tot, u_q_bob)
                                                f_rat, rf_rat = divmod(f_tot, u_q_bob)
                                                try:
                                                    with transaction.atomic():
                                                        emp_obj = (
                                                            Empresa.objects.select_for_update().get(
                                                                codemp=int(cod_emp)
                                                            )
                                                        )
                                                        tempo_ciclo = agora
                                                        tempo_ciclo_local = agora_local
                                                        for i in range(u_q_bob):
                                                            eh_ultimo = i == u_q_bob - 1
                                                            qtd_at = (
                                                                q_rat + (r_rat if eh_ultimo else 0)
                                                            ) / 100.0
                                                            ref_at = (
                                                                f_rat + (rf_rat if eh_ultimo else 0)
                                                            ) / 100.0
                                                            lote_at = normalizar_lote_numerico(
                                                                emp_obj.loteatual
                                                            )
                                                            emp_obj.loteatual = incrementar_lote(
                                                                lote_at
                                                            )
                                                            emp_obj.save()
                                                            if i > 0:
                                                                tempo_ciclo += timedelta(seconds=1)
                                                                tempo_ciclo_local += timedelta(
                                                                    seconds=1
                                                                )
                                                            ap_f = salvar_log_apontamento(
                                                                cod_emp,
                                                                cod_ori,
                                                                num_op,
                                                                cod_etg,
                                                                seq_rot,
                                                                num_cad,
                                                                qtd_at,
                                                                ref_at,
                                                                lote_at,
                                                                cod_rec_int,
                                                                tempo_ciclo_local.strftime(
                                                                    "%d/%m/%Y"
                                                                ),
                                                                tempo_ciclo_local.strftime(
                                                                    "%H:%M:%S"
                                                                ),
                                                                tempo_ciclo,
                                                                bobina_apont,
                                                                origem_peso_post
                                                                if qtd_at > 0
                                                                else None,
                                                                recurso_selecionado,
                                                                request.user,
                                                            )
                                                            if ap_f:
                                                                ids_apont_criados.append(ap_f.id)
                                                                apontamento_concluido = True
                                                                limpar_operador_validado()
                                                except Exception:
                                                    logger.exception(
                                                        "Falha ao registrar apontamento por bobina"
                                                    )
                                                    erro = (
                                                        "Não foi possível registrar o apontamento."
                                                    )
                                            else:
                                                # Apontamento de bobina única
                                                lote_envio = None
                                                if qtd_prod > 0 or qtd_ref > 0:
                                                    try:
                                                        with transaction.atomic():
                                                            emp_obj = Empresa.objects.select_for_update().get(
                                                                codemp=int(cod_emp)
                                                            )
                                                            lote_envio = normalizar_lote_numerico(
                                                                emp_obj.loteatual
                                                            )
                                                            emp_obj.loteatual = incrementar_lote(
                                                                lote_envio
                                                            )
                                                            emp_obj.save()
                                                    except Exception:
                                                        logger.exception(
                                                            "Falha ao reservar lote para apontamento"
                                                        )
                                                        erro = "Não foi possível registrar o apontamento."
                                                if not erro:
                                                    apont_fim = salvar_log_apontamento(
                                                        cod_emp,
                                                        cod_ori,
                                                        num_op,
                                                        cod_etg,
                                                        seq_rot,
                                                        num_cad,
                                                        qtd_prod,
                                                        qtd_ref,
                                                        lote_envio,
                                                        cod_rec_int,
                                                        agora_local.strftime("%d/%m/%Y"),
                                                        agora_local.strftime("%H:%M:%S"),
                                                        agora,
                                                        bobina_apont,
                                                        origem_peso_post if qtd_prod > 0 else None,
                                                        recurso_selecionado,
                                                        request.user,
                                                    )
                                                    if apont_fim:
                                                        ids_apont_criados.append(apont_fim.id)
                                                        apontamento_concluido = True
                                                        limpar_operador_validado()

                                            # Processamento pós-apontamento unificado
                                            if ids_apont_criados:
                                                threading.Thread(
                                                    target=notifica_atualizacao_atrasada,
                                                    args=(codbar, 10),
                                                    daemon=True,
                                                ).start()
                                                # Coleta de peso para auditoria (Thread independente)
                                                threading.Thread(
                                                    target=disparar_coleta_peso,
                                                    args=(recurso_id, ids_apont_criados),
                                                ).start()
                                                # Disparo independente: Envio imediato para o ERP
                                                threading.Thread(
                                                    target=processar_logs_pendentes, daemon=True
                                                ).start()

    except Exception:
        logger.exception("Falha ao processar apontamento V1")
        erro, dados_op, componentes, operacoes, historico, codbar = (
            "Não foi possível consultar os dados no ERP.",
            None,
            [],
            [],
            [],
            "",
        )

    # Ajustes finais de exibição e redirecionamento
    if request.method == "POST" and "enviar_apontamento" in request.POST:
        request.session["ultima_resposta"] = {"mensagem": resposta, "erro": erro, "acao": acao}
        if apontamento_concluido:
            request.session.save()
        redirect_url = f"{request.path}?empresa={empresa_id}&centro={centro_id}&recurso={recurso_id}&codbar={codbar}"
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "redirect_url": redirect_url,
                    "redirect_immediate": bool(erro),
                    "operador_limpo": bool(apontamento_concluido),
                }
            )
        return redirect(redirect_url)

    # Dados de contexto para o template
    sequencias = (
        Sequenciamento.objects.filter(recurso_id=recurso_id).order_by("ordenacao")
        if recurso_id
        else []
    )
    seq_atual_id = next((s.id for s in sequencias if s.codigo_barra == codbar), None)

    # Define bobina disponível para o operador
    bobinas_disp = []
    codigo_integrador_centro = (
        recurso_selecionado.centro_recurso.codigo_integrador
        if recurso_selecionado and recurso_selecionado.centro_recurso
        else ""
    )
    if recurso_selecionado and codigo_integrador_centro:
        bobina_atual_rec = int(recurso_selecionado.bobina or 0)
        ult_apont_local = (
            Apontamento.objects.filter(
                codigo_integrador=codigo_integrador_centro,
                status=Apontamento.Status.NAO_INTEGRADO,
                bobina__isnull=False,
            )
            .order_by("-bobina")
            .first()
        )

        if ult_apont_local and ult_apont_local.bobina:
            ultima_bobina_apontada = int(ult_apont_local.bobina)
        else:
            ultima_bobina_apontada = buscar_ultima_bobina_apontada_erp(
                recurso_selecionado.centro_recurso.setor.departamento.filial.empresa.codemp,
                codigo_integrador_centro,
            )

        bobinas_disp = calcular_bobinas_disponiveis(bobina_atual_rec, ultima_bobina_apontada)

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
        "producao/apontamentos_v1.html",
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
            "acao": acao,
            "codbar": codbar,
            "numcad": numcad_sessao,
            "nome_operador": nome_operador_sessao,
            "habilitar_apontamento": bool(nome_operador_sessao and recurso_id),
            "pode_apontar": pode_apontar,
            "pode_corrigir_lote": pode_corrigir_lote,
            "codetg": codetg,
            "seqrot": seqrot,
            "status_seq": status_seq,
            "sequencias": sequencias,
            "sequencia_atual_id": seq_atual_id,
            "taras_vinculadas": taras_vinculadas,
            "aponta_refugo": aponta_refugo,
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
            "parametros_apontamento": parametros_apontamento,
            "bobinas_disponiveis": bobinas_disp,
            "bobina_selecionada_post": request.POST.get("bobina_selecionada"),
            **contexto_paradas,
        },
    )
