"""Tela de apontamento Multi-OP (rebobinadeira) — view_id = 3.

Múltiplas OPs ficam acopladas ao mesmo recurso simultaneamente (necessário
para o cálculo de tempo de cada uma), mas a produção nunca é apontada em mais
de uma OP ao mesmo tempo: o operador pesa o lote de uma OP, tira da máquina,
depois pesa o lote da outra. O peso líquido pesado é dividido em partes iguais
pelas "Bobinas planejadas" (E900COP.USU_QTDBOB) da OP escolhida naquele
apontamento, e cada parte gera um novo `Apontamento` com lote próprio
incrementado de `Empresa.loteatual` — mesma regra da v1, mas sem o conceito de
número de bobina (aqui cada bobina cortada é o próprio lote, então
`Apontamento.bobina` fica vazio). O consumo de bobinas de consumo, ao
contrário, é da máquina: todo apontamento de peso debita do rateio entre as
bobinas em EM_CONSUMO, independente de qual OP foi apontada.

Estado atual: acoplar/desacoplar OP, alocar/desalocar bobina de consumo e o
apontamento de produção (rateio de consumo + geração dos registros em
producao.apontamento) já gravam de verdade. Cada bobina de consumo debitada
gera um `BaixaComponente` local, enviado ao ERP pelo webservice `TratarBaixa`
(fila própria em producao/views/logs_baixa_componentes.py).
"""

import logging
import threading
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import CentroRecurso, Empresa, Recurso, Tara
from producao.models import (
    Apontamento,
    BaixaComponente,
    BobinaConsumoRecurso,
    LogTrocaOPAtiva,
    Sequenciamento,
)
from producao.services.altera_apontamento import incrementar_lote, normalizar_lote_numerico
from producao.utils.paradas import vincular_parada_aberta_ao_periodo
from producao.views.apontamento_base import (
    contexto_parada_recurso,
    empresas_visiveis_apontamento,
    recurso_tem_parada_bloqueante,
    recursos_visiveis_apontamento,
)
from producao.views.apontamentos_v1 import (
    decode_cod_barras,
    salvar_log_apontamento,
    valida_operador,
)
from producao.views.logs_apontamentos import processar_logs_pendentes
from producao.views.logs_baixa_componentes import disparar_envio_baixas_componentes
from SIGMA.integracoes.oracle import cursor_oracle_erp

logger = logging.getLogger(__name__)


def _bloquear_recurso_e_periodos_abertos(recurso):
    recurso = Recurso.objects.select_for_update().get(pk=recurso.pk)
    periodos_abertos = list(
        LogTrocaOPAtiva.objects.select_for_update()
        .filter(recurso=recurso, horario_saida__isnull=True)
        .order_by("horario_troca")
    )
    return recurso, periodos_abertos


def _acoplar_op(request, recurso_selecionado, cod_emp, codbar_acoplar):
    """Abre um período para uma OP compatível com as já acopladas.

    A V3 compartilha as bobinas de consumo do recurso. Por isso, quando já
    existem OPs acopladas, a nova OP precisa preservar ao menos um mesmo
    componente (produto e derivação) em todas elas.
    """
    try:
        cod_emp_bar, cod_ori_bar, num_op_bar, cod_etg_bar, seq_rot_bar = decode_cod_barras(
            codbar_acoplar
        )
    except Exception:
        messages.error(request, "Código de barras da OP inválido para acoplamento.")
        return

    sequenciada = Sequenciamento.objects.filter(
        recurso=recurso_selecionado,
        origem=str(cod_ori_bar),
        op=num_op_bar,
        estagio=int(cod_etg_bar),
        seqrot=int(seq_rot_bar),
    ).exists()
    if not sequenciada:
        messages.error(request, "Só é possível acoplar OPs sequenciadas para este recurso.")
        return

    numcad = request.POST.get("numcad_acoplar")
    if not numcad:
        messages.error(request, "Informe o operador para acoplar a OP.")
        return

    try:
        with cursor_oracle_erp() as cursor:
            nome_operador = valida_operador(cursor, cod_emp, numcad)
    except Exception:
        logger.exception("Falha ao validar operador no ERP")
        messages.error(request, "Não foi possível validar o operador no ERP.")
        return
    if not nome_operador:
        messages.error(
            request, f"Operador {numcad} não encontrado ou inativo na empresa {cod_emp}."
        )
        return

    with transaction.atomic():
        recurso_travado, periodos_abertos = _bloquear_recurso_e_periodos_abertos(
            recurso_selecionado
        )

        if any(periodo.codigo_barra == codbar_acoplar for periodo in periodos_abertos):
            messages.error(request, "Esta OP já está acoplada neste recurso.")
            return

        if recurso_tem_parada_bloqueante(recurso_travado):
            messages.error(
                request,
                "Existe parada em aberto para este recurso. Justifique antes de acoplar outra OP.",
            )
            return

        bobinas_ativas = _bobinas_ativas_do_recurso(recurso_travado, bloquear=True)
        if periodos_abertos or bobinas_ativas:
            try:
                componentes_em_comum = _componentes_compartilhados_das_ops_erp(
                    cod_emp,
                    [
                        (periodo_aberto.origem, periodo_aberto.op)
                        for periodo_aberto in periodos_abertos
                    ]
                    + [(str(cod_ori_bar), num_op_bar)],
                )
            except Exception:
                logger.exception("Falha ao validar componentes das OPs no ERP")
                messages.error(request, "Não foi possível validar os componentes das OPs no ERP.")
                return

            if periodos_abertos and not componentes_em_comum:
                messages.error(
                    request,
                    "Não é possível acoplar esta OP: as OPs em conjunto devem ter ao menos um "
                    "componente em comum, considerando produto e derivação.",
                )
                return

            bobinas_incompativeis = _bobinas_incompativeis(bobinas_ativas, componentes_em_comum)
            if bobinas_incompativeis:
                messages.error(
                    request,
                    "Não é possível acoplar esta OP: os lotes já alocados "
                    f"({_formatar_bobinas(bobinas_incompativeis)}) não são componentes das OPs "
                    "que ficarão acopladas. Desaloque-os antes de tentar novamente.",
                )
                return

        agora = timezone.now().replace(microsecond=0)
        novo_periodo = LogTrocaOPAtiva.objects.create(
            recurso=recurso_travado,
            usuario=request.user,
            origem=str(cod_ori_bar),
            op=num_op_bar,
            estagio=int(cod_etg_bar),
            seqrot=int(seq_rot_bar),
            horario_troca=agora,
            id_operador=int(numcad),
        )
        vincular_parada_aberta_ao_periodo(novo_periodo)

    messages.success(
        request, f"OP {num_op_bar} acoplada ao recurso. Operador: {nome_operador} ({numcad})."
    )


def _desacoplar_op(request, recurso_selecionado, periodo_id):
    with transaction.atomic():
        recurso_travado, periodos_abertos = _bloquear_recurso_e_periodos_abertos(
            recurso_selecionado
        )

        periodo = next((p for p in periodos_abertos if p.id == int(periodo_id)), None)
        if not periodo:
            messages.error(request, "Período produtivo não encontrado ou já encerrado.")
            return

        if recurso_tem_parada_bloqueante(recurso_travado):
            messages.error(
                request,
                "Existe parada em aberto para este recurso. Justifique antes de desacoplar.",
            )
            return

        periodos_restantes = [item for item in periodos_abertos if item.id != periodo.id]
        bobinas_ativas = _bobinas_ativas_do_recurso(recurso_travado, bloquear=True)
        if periodos_restantes and bobinas_ativas:
            try:
                componentes_em_comum = _componentes_compartilhados_das_ops_erp(
                    recurso_travado.centro_recurso.setor.departamento.filial.empresa.codemp,
                    [(item.origem, item.op) for item in periodos_restantes],
                )
            except Exception:
                logger.exception("Falha ao validar componentes das OPs no ERP")
                messages.error(request, "Não foi possível validar os componentes das OPs no ERP.")
                return

            bobinas_incompativeis = _bobinas_incompativeis(bobinas_ativas, componentes_em_comum)
            if bobinas_incompativeis:
                messages.error(
                    request,
                    "Não é possível desacoplar esta OP: os lotes alocados "
                    f"({_formatar_bobinas(bobinas_incompativeis)}) não são componentes das OPs "
                    "que permanecerão acopladas. Desaloque-os antes de tentar novamente.",
                )
                return

        LogTrocaOPAtiva.objects.filter(pk=periodo.pk).update(
            horario_saida=timezone.now().replace(microsecond=0)
        )

    messages.success(request, f"OP {periodo.op} desacoplada do recurso.")


def _separar_origens(valor):
    return [parte.strip().upper() for parte in str(valor or "").split(",") if parte.strip()]


def _consultar_saldo_lote_erp(cod_emp, lote, origens_permitidas):
    """Consulta saldo/produto-derivação do lote no ERP para alocação de consumo.

    Um mesmo CODLOT pode existir em E210DLS associado a produtos/derivações
    diferentes (ex.: depósitos distintos). Para não pegar a linha errada
    nesse cenário, restringe aos produtos cuja origem (E075PRO.CODORI) esteja
    entre as "Origens área vermelha" configuradas na filial/centro/recurso —
    mesmo parâmetro já usado para restringir o universo de produtos elegíveis
    em outros fluxos de qualidade.
    """
    if not origens_permitidas:
        return (
            None,
            "Nenhuma origem permitida configurada na filial (parâmetro Origens área vermelha).",
        )

    placeholders = ", ".join(["%s"] * len(origens_permitidas))
    with cursor_oracle_erp() as cursor:
        cursor.execute(
            f"""
                SELECT DLS.CODPRO, DLS.CODDER, NVL(SUM(DLS.QTDEST), 0) saldo
                FROM E210DLS DLS
                JOIN E075PRO PRO ON PRO.CODEMP = DLS.CODEMP AND PRO.CODPRO = DLS.CODPRO
                WHERE DLS.CODEMP = %s AND DLS.CODLOT = %s
                  AND UPPER(PRO.CODORI) IN ({placeholders})
                GROUP BY DLS.CODPRO, DLS.CODDER
            """,
            [cod_emp, str(lote).upper().strip(), *origens_permitidas],
        )
        linhas = cursor.fetchall()
    if not linhas:
        return None, None
    if len(linhas) > 1:
        return (
            None,
            "Lote encontrado em mais de um produto/derivação elegível; não é possível alocar automaticamente.",
        )
    codpro, codder, saldo = linhas[0]
    return {"codpro": codpro, "codder": codder, "saldo": saldo}, None


def _alocar_bobina_consumo(request, recurso_selecionado, cod_emp, lote, destino):
    """Aloca um lote para EM_CONSUMO ou EM_FILA. destino: 'consumo' ou 'fila'."""
    lote = (lote or "").strip()
    if not lote:
        messages.error(request, "Informe o lote a alocar.")
        return

    if BobinaConsumoRecurso.objects.filter(
        recurso=recurso_selecionado,
        lote=lote,
        status__in=[BobinaConsumoRecurso.Status.EM_FILA, BobinaConsumoRecurso.Status.EM_CONSUMO],
    ).exists():
        messages.error(request, f"O lote {lote} já está alocado neste recurso.")
        return

    if BaixaComponente.objects.filter(
        codlot=lote, repesagem="S", status=BaixaComponente.Status.NAO_INTEGRADO
    ).exists():
        messages.error(
            request,
            f"O lote {lote} está pendente de repesagem e não pode ser alocado até isso ser resolvido.",
        )
        return

    origens_permitidas = _separar_origens(
        recurso_selecionado.get_parametros_efetivos().get("origens_area_vermelha")
    )
    dados_lote, erro_consulta = _consultar_saldo_lote_erp(cod_emp, lote, origens_permitidas)
    if erro_consulta:
        messages.error(request, erro_consulta)
        return
    if not dados_lote:
        messages.error(request, f"Lote {lote} não encontrado no ERP ou sem saldo.")
        return
    if 0 < dados_lote["saldo"] <= 1:
        messages.error(
            request, f"Lote {lote} está pendente de repesagem no ERP e não pode ser alocado."
        )
        return
    if dados_lote["saldo"] <= 0:
        messages.error(request, f"Lote {lote} está com saldo zerado no ERP.")
        return

    with transaction.atomic():
        recurso_travado, periodos_abertos = _bloquear_recurso_e_periodos_abertos(
            recurso_selecionado
        )
        if periodos_abertos:
            try:
                componentes_em_comum = _componentes_compartilhados_das_ops_erp(
                    cod_emp, [(periodo.origem, periodo.op) for periodo in periodos_abertos]
                )
            except Exception:
                logger.exception("Falha ao validar componentes das OPs no ERP")
                messages.error(request, "Não foi possível validar os componentes das OPs no ERP.")
                return

            componente_lote = _chave_produto_derivacao(dados_lote["codpro"], dados_lote["codder"])
            if componente_lote not in componentes_em_comum:
                messages.error(
                    request,
                    f"O lote {lote} ({_formatar_chave_componente(componente_lote)}) não é componente "
                    "das OPs atualmente acopladas e não pode ser alocado.",
                )
                return

        if destino == "consumo":
            status = BobinaConsumoRecurso.Status.EM_CONSUMO
            ordem_fila = None
        else:
            status = BobinaConsumoRecurso.Status.EM_FILA
            ultima_ordem = (
                BobinaConsumoRecurso.objects.select_for_update()
                .filter(recurso=recurso_travado, status=BobinaConsumoRecurso.Status.EM_FILA)
                .order_by("-ordem_fila")
                .values_list("ordem_fila", flat=True)
                .first()
            )
            ordem_fila = (ultima_ordem or 0) + 1

        BobinaConsumoRecurso.objects.create(
            recurso=recurso_travado,
            usuario=request.user,
            codemp=cod_emp,
            lote=lote,
            codpro=dados_lote["codpro"],
            codder=dados_lote["codder"],
            quantidade_alocada=dados_lote["saldo"],
            quantidade_restante=dados_lote["saldo"],
            status=status,
            ordem_fila=ordem_fila,
        )

    messages.success(
        request, f"Lote {lote} alocado {'em consumo' if destino == 'consumo' else 'na fila'}."
    )


def _desalocar_bobina_consumo(request, recurso_selecionado, bobina_id):
    ja_teve_consumo = False
    with transaction.atomic():
        bobina = (
            BobinaConsumoRecurso.objects.select_for_update()
            .filter(
                pk=bobina_id,
                recurso=recurso_selecionado,
                status__in=[
                    BobinaConsumoRecurso.Status.EM_FILA,
                    BobinaConsumoRecurso.Status.EM_CONSUMO,
                ],
            )
            .first()
        )
        if not bobina:
            messages.error(request, "Bobina alocada não encontrada.")
            return

        # Já teve consumo se existir algum BaixaComponente real (repesagem='N')
        # gerado para este lote — fonte de verdade, em vez de inferir pelo
        # saldo local. Nesse caso o lote precisa ser repesado no ERP antes de
        # reaproveitar, pois a bobina pode ter consumido em proporção
        # diferente da calculada (gramatura do papel nem sempre é 1:1 com o
        # cálculo teórico). O registro de repesagem é conceitualmente um
        # estorno/ajuste da última baixa real daquele lote, por isso herda a
        # chave de OP dela, não uma OP vazia.
        ultima_baixa = (
            BaixaComponente.objects.filter(
                recurso=recurso_selecionado, codlot=bobina.lote, repesagem="N"
            )
            .order_by("-id")
            .first()
        )
        ja_teve_consumo = ultima_baixa is not None
        if ja_teve_consumo:
            agora = timezone.now().replace(microsecond=0)
            # datmov/hormov são CharField enviados ao ERP: precisam do horário
            # local (America/Sao_Paulo), não do UTC que timezone.now() retorna
            # com USE_TZ=True. data_hora continua em agora (UTC), pois é um
            # DateTimeField — o Django já converte para exibição.
            agora_local = timezone.localtime(agora)
            BaixaComponente.objects.create(
                recurso=recurso_selecionado,
                usuario=request.user,
                codemp=ultima_baixa.codemp,
                origem=ultima_baixa.origem,
                numorp=ultima_baixa.numorp,
                codetg=ultima_baixa.codetg,
                seqrot=ultima_baixa.seqrot,
                lotdes=None,
                codcmp=bobina.codpro,
                dercmp=bobina.codder,
                # Mantém saldo 1 no ERP, que identifica o lote como pendente
                # de repesagem; por isso a baixa consome o restante menos 1.
                qtduti=bobina.quantidade_restante - Decimal("1"),
                codigo_integrador=ultima_baixa.codigo_integrador,
                datmov=agora_local.strftime("%d/%m/%Y"),
                hormov=agora_local.strftime("%H:%M:%S"),
                codlot=bobina.lote,
                repesagem="S",
                consumototal="N",
                status=BaixaComponente.Status.NAO_INTEGRADO,
                data_hora=agora,
                datger=agora,
            )

        bobina.delete()

    if ja_teve_consumo:
        disparar_envio_baixas_componentes()
        messages.success(
            request,
            f"Lote {bobina.lote} removido da alocação. Como já havia consumo registrado, "
            "foi gerada uma solicitação de repesagem.",
        )
    else:
        messages.success(request, f"Lote {bobina.lote} removido da alocação.")


def _calcular_plano_rateio_consumo(recurso_selecionado, peso_total):
    """Calcula (sem persistir) o plano teórico de rateio do peso apontado.

    O peso é dividido em fatias iguais pelo número de bobinas em consumo
    ativo. Quando uma fatia não cabe inteira na bobina correspondente (saldo
    insuficiente), o restante da MESMA fatia é emendado com bobinas da fila,
    na ordem, encadeando quantas forem necessárias. Uma bobina da fila nunca
    é usada para cobrir mais de uma fatia no mesmo apontamento — cada fatia
    que precisa de emenda reserva bobinas exclusivas da fila para si.

    Retorna (True, fatias) em sucesso, onde fatias é uma lista de listas —
    uma por bobina em consumo original, cada uma com a cadeia ordenada de
    passos {bobina, quantidade_planejada} que o cálculo teórico previu para
    aquela fatia (o primeiro passo é sempre a bobina que já estava em
    consumo; os seguintes, se houver, são bobinas da fila usadas em emenda).
    Retorna (False, mensagem) quando o saldo teórico é insuficiente.

    Não deve alterar nada no banco: usada tanto para decidir se é necessário
    perguntar ao operador sobre bobinas que zerariam, quanto como insumo para
    _aplicar_plano_rateio_consumo depois que ele responder.
    """
    peso_total = Decimal(str(peso_total))
    bobinas_consumo = list(
        BobinaConsumoRecurso.objects.select_for_update()
        .filter(recurso=recurso_selecionado, status=BobinaConsumoRecurso.Status.EM_CONSUMO)
        .order_by("id")
    )
    if not bobinas_consumo:
        return False, "Não há bobinas em consumo ativo para ratear o peso apontado."

    fila_disponivel = list(
        BobinaConsumoRecurso.objects.select_for_update()
        .filter(recurso=recurso_selecionado, status=BobinaConsumoRecurso.Status.EM_FILA)
        .order_by("ordem_fila")
    )

    quantidade_fatia = peso_total / len(bobinas_consumo)
    fatias = []

    for bobina in bobinas_consumo:
        cadeia = [
            {
                "bobina": bobina,
                "quantidade_planejada": min(quantidade_fatia, bobina.quantidade_restante),
            }
        ]
        falta = quantidade_fatia - bobina.quantidade_restante
        while falta > 0:
            if not fila_disponivel:
                return False, (
                    f"Saldo insuficiente para o rateio: falta {falta:.4f} na fatia da bobina "
                    f"{bobina.lote} e não há mais bobinas em fila para emendar."
                )
            candidata = fila_disponivel.pop(0)
            usado = min(candidata.quantidade_restante, falta)
            cadeia.append({"bobina": candidata, "quantidade_planejada": usado})
            falta -= usado
        fatias.append(cadeia)

    return True, fatias


def _bobinas_a_confirmar(fatias):
    """Retorna, de cada fatia, os passos cujo débito planejado zeraria a bobina.

    Usado para decidir se é preciso perguntar ao operador antes de persistir:
    uma bobina teórica zerada pode, na prática, ter rendido mais do que o
    esperado (emenda desnecessária) ou ainda ter sobra real (emenda maior do
    que a real). Cada passo devolvido carrega a posição na cadeia (índice da
    fatia e índice do passo) para a resposta do operador ser aplicada de volta
    ao passo exato depois.
    """
    passos = []
    for indice_fatia, cadeia in enumerate(fatias):
        total_fatia = sum(p["quantidade_planejada"] for p in cadeia)
        for indice_passo, passo in enumerate(cadeia):
            bobina = passo["bobina"]
            zeraria = (bobina.quantidade_restante - passo["quantidade_planejada"]) <= 0
            if zeraria:
                passos.append(
                    {
                        "indice_fatia": indice_fatia,
                        "indice_passo": indice_passo,
                        "bobina": bobina,
                        "quantidade_planejada": passo["quantidade_planejada"],
                        # Só faz sentido oferecer "emenda" (seguir para a próxima
                        # bobina da fila) quando o plano teórico já previu um
                        # próximo passo nesta cadeia — sem isso, não há para onde
                        # emendar (ex: bobina única cobrindo a fatia inteira).
                        "tem_proximo_passo": indice_passo < len(cadeia) - 1,
                        # Contexto para a UI explicar POR QUE uma bobina que
                        # "fecha exato" sozinha ainda pode ter próximo passo: ela
                        # é só uma parte de uma fatia maior, que outras bobinas
                        # (em fila) também estão cobrindo no mesmo apontamento.
                        "total_fatia": total_fatia,
                        "posicao_na_fatia": indice_passo + 1,
                        "bobinas_na_fatia": len(cadeia),
                    }
                )
    return passos


def _aplicar_plano_rateio_consumo(recurso_selecionado, fatias, respostas):
    """Debita as bobinas conforme o plano teórico, ajustado pelas respostas do operador.

    `respostas` é um dict {bobina_id: resposta}, resposta em:
    - "emenda": confirma que zerou de verdade; a cadeia segue para o próximo
      passo planejado (comportamento igual ao plano teórico).
    - "sem_emenda": zerou de verdade, mas SEM emendar — a cadeia para aqui
      mesmo que houvesse mais passos planejados depois dela (os passos
      seguintes daquela fatia são descartados, as bobinas neles permanecem
      intocadas em EM_FILA).
    - "parcial:<valor>": não zerou; resta de verdade <valor> kg. Debita só a
      diferença (quantidade_planejada - saldo_real), nunca negativa — se a
      diferença for <= 0 (rendeu mais do que o previsto), não debita nada
      dessa bobina e nenhuma BaixaComponente é gerada para ela. A cadeia
      também para aqui (os passos seguintes são descartados).
    Bobinas cujo passo não zeraria teoricamente não precisam de resposta e
    são debitadas exatamente como planejado.

    Deve ser chamada dentro da mesma transaction.atomic() que já bloqueou as
    bobinas (select_for_update ocorreu em _calcular_plano_rateio_consumo).
    Retorna a lista de dicts {bobina, quantidade_debitada, consumo_total}
    usada para gerar BaixaComponente — uma linha por bobina efetivamente
    debitada (bobinas com diferença <= 0 na resposta "parcial" não entram).
    """
    extrato = []

    for cadeia in fatias:
        # Só a última bobina de fila efetivamente tocada nesta cadeia assume
        # EM_CONSUMO no lugar da bobina original (é quem sobra fisicamente na
        # máquina); permanece None se a cadeia não precisou de nenhuma fila.
        bobina_a_promover_id = None

        for indice_passo, passo in enumerate(cadeia):
            bobina = passo["bobina"]
            quantidade_planejada = passo["quantidade_planejada"]
            zeraria = (bobina.quantidade_restante - quantidade_planejada) <= 0
            resposta = respostas.get(bobina.id) if zeraria else None

            if resposta and resposta.startswith("parcial:"):
                saldo_real = Decimal(resposta.split(":", 1)[1])
                debito = bobina.quantidade_restante - saldo_real
                if debito > 0:
                    nova_quantidade = bobina.quantidade_restante - debito
                    BobinaConsumoRecurso.objects.filter(pk=bobina.pk).update(
                        quantidade_restante=nova_quantidade
                    )
                    extrato.append(
                        {"bobina": bobina, "quantidade_debitada": debito, "consumo_total": False}
                    )
                # Cadeia para aqui: os passos seguintes (emenda planejada) não eram necessários.
                break

            debito = quantidade_planejada
            nova_quantidade = bobina.quantidade_restante - debito
            consumo_total = nova_quantidade <= 0
            if consumo_total:
                # Bobina zerada não serve mais para nada: o bloqueio contra
                # realocação de um lote já consumido é feito via
                # BaixaComponente (repesagem pendente), tabela separada que
                # não depende deste registro continuar existindo.
                BobinaConsumoRecurso.objects.filter(pk=bobina.pk).delete()
            else:
                BobinaConsumoRecurso.objects.filter(pk=bobina.pk).update(
                    quantidade_restante=nova_quantidade
                )
            extrato.append(
                {"bobina": bobina, "quantidade_debitada": debito, "consumo_total": consumo_total}
            )

            if indice_passo > 0:
                # Só promove se ela própria não zerou: uma bobina zerada foi
                # deletada acima e não sobra fisicamente para assumir nada.
                bobina_a_promover_id = None if consumo_total else bobina.id

            if zeraria and resposta == "sem_emenda":
                # Zerou de verdade, mas sem emendar: a fatia para aqui — os
                # passos seguintes (bobinas de fila reservadas na emenda
                # teórica) não são debitados e permanecem em fila intactos.
                break

        if bobina_a_promover_id is not None:
            BobinaConsumoRecurso.objects.filter(pk=bobina_a_promover_id).update(
                status=BobinaConsumoRecurso.Status.EM_CONSUMO,
                ordem_fila=None,
            )

    return extrato


def _apontar_producao(request, recurso_selecionado, recurso_id, cod_emp, parametros_apontamento):
    """Valida, aplica o rateio de consumo e gera os registros de produção.

    Mesmas consistências da v1: limites min/máx de quantidade, refugo
    opcional conforme `aponta_refugo` do recurso, peso capturado via modal
    (balança ou manual) e um novo lote incrementado de `Empresa.loteatual`
    por bobina planejada da OP. Diferente da v1, aqui não existe número de
    bobina (cada bobina cortada é o próprio lote), então
    `Apontamento.bobina` fica vazio. ApontamentoComponente (baixa de consumo
    no ERP) ainda não é gravado — só o débito local das bobinas de consumo.
    """
    numcad_producao = request.session.get(f"numcad_operador_producao_{recurso_id}")
    if not numcad_producao:
        messages.error(request, "Valide o operador do apontamento antes de apontar.")
        return

    chave_sessao_confirmacao = f"consumo_a_confirmar_{recurso_id}"

    # Ao reenviar o form de confirmação de consumo (só as respostas por
    # bobina, sem repetir peso/OP/etc.), os dados originais do apontamento
    # são recuperados da sessão em vez de exigidos de novo do POST.
    dados_post = request.POST
    pendencia_sessao = request.session.get(chave_sessao_confirmacao)
    if "confirmar_consumo" in request.POST and pendencia_sessao:
        # QueryDict não pode ser mesclado com "**": desempacotar um QueryDict
        # devolve o valor como lista (ex.: {"id": ["35"]}), não o escalar que
        # .get() devolveria — por isso os valores são extraídos um a um.
        dados_post = dict(pendencia_sessao["dados_originais"])
        for chave in request.POST:
            dados_post[chave] = request.POST.get(chave)

    periodo_id = dados_post.get("periodo_id_apontamento")
    if not periodo_id:
        messages.error(request, "Selecione a OP sendo apontada.")
        return

    aponta_refugo = parametros_apontamento.get("aponta_refugo", True)
    try:
        qtd_prod = float(dados_post.get("peso_total") or 0)
        qtd_ref = float(dados_post.get("qtdrfg") or 0) if aponta_refugo else 0.0
    except TypeError, ValueError:
        messages.error(request, "Quantidade inválida.")
        return
    if qtd_prod <= 0 and qtd_ref <= 0:
        messages.error(request, "Informe um peso de produção ou de refugo maior que zero.")
        return

    autorizado_modal = dados_post.get("autorizado_modal") == "1"
    if not autorizado_modal:
        messages.error(request, "A quantidade deve ser capturada via modal de peso.")
        return

    limite_min = parametros_apontamento["limite_apontamento_minimo"]
    limite_max = parametros_apontamento["limite_apontamento_maximo"]
    qtd_total = qtd_prod + qtd_ref
    if qtd_total < limite_min or qtd_total > limite_max:
        messages.error(
            request, f"Quantidade total deve ficar entre {limite_min:g} e {limite_max:g}."
        )
        return

    origem_peso = dados_post.get("origem_peso", "")

    if recurso_tem_parada_bloqueante(recurso_selecionado):
        messages.error(
            request, "Existe parada em aberto para este recurso. Justifique antes de apontar."
        )
        return

    codigo_integrador_centro = (
        recurso_selecionado.centro_recurso.codigo_integrador
        if recurso_selecionado.centro_recurso
        else ""
    )
    if not codigo_integrador_centro:
        messages.error(request, "Centro de recurso sem código integrador.")
        return

    periodo = LogTrocaOPAtiva.objects.filter(
        pk=periodo_id, recurso=recurso_selecionado, horario_saida__isnull=True
    ).first()
    if not periodo:
        messages.error(request, "Esta OP não está mais acoplada a este recurso.")
        return

    # Não há número de bobina para travar pesagem repetida (como na v1), então
    # o alerta de possível duplo apontamento do mesmo ciclo de pesagem é por
    # proximidade: peso muito parecido com o último registro real desta OP ou
    # apontado há poucos segundos. Isso não bloqueia, só exige confirmação
    # explícita do operador (checkbox "confirmar_pesagem_duplicada").
    ultimo_apontamento = (
        Apontamento.objects.filter(
            codemp=cod_emp,
            origem=periodo.origem,
            numorp=periodo.op,
            codetg=periodo.estagio,
            seqrot=periodo.seqrot,
        )
        .order_by("-id")
        .first()
    )
    if ultimo_apontamento and dados_post.get("confirmar_pesagem_duplicada") != "1":
        peso_anterior = float(ultimo_apontamento.qtdre1 or 0) + float(
            ultimo_apontamento.qtdrfg or 0
        )
        variacao_peso = abs(qtd_total - peso_anterior)
        segundos_desde_ultimo = (timezone.now() - ultimo_apontamento.data_hora).total_seconds()
        if variacao_peso < 10 and segundos_desde_ultimo < 300:
            messages.warning(
                request,
                f"Atenção: diferença de apenas {variacao_peso:.2f} kg em relação ao último "
                f"apontamento e este ocorreu há {int(segundos_desde_ultimo)}s (menos de 5 min). "
                "Confirmar vai gerar novos lotes. Confira o histórico em Logs > Apontamentos "
                "antes de confirmar que esta é realmente uma nova pesagem.",
            )
            return

    # Todas as validações que podem falhar (ERP, operador, bobinas planejadas)
    # ocorrem ANTES de debitar o consumo: um "return" dentro de
    # transaction.atomic() faz commit do que já rodou, não rollback — então
    # o débito de consumo só pode ser aplicado depois de garantir que os
    # registros de produção também serão gerados com sucesso.
    try:
        with cursor_oracle_erp() as cursor:
            if not valida_operador(cursor, cod_emp, numcad_producao):
                messages.error(request, "Operador inválido.")
                return
            cursor.execute(
                "SELECT COUNT(*) FROM e900oop WHERE codemp=:codemp AND codori=:codori "
                "AND numorp=:numorp AND codetg=:codetg AND seqrot=:seqrot",
                {
                    "codemp": cod_emp,
                    "codori": periodo.origem,
                    "numorp": periodo.op,
                    "codetg": periodo.estagio,
                    "seqrot": periodo.seqrot,
                },
            )
            if not cursor.fetchone()[0]:
                messages.error(request, "Estágio não encontrado.")
                return
            dados_op, _ = _consultar_dados_op_erp(cursor, cod_emp, periodo.origem, periodo.op)
    except Exception:
        logger.exception("Falha ao validar dados do apontamento no ERP")
        messages.error(request, "Não foi possível validar os dados no ERP.")
        return

    # OPs sem USU_QTDBOB cadastrado no ERP caem no fallback de bobina única,
    # mesmo comportamento tolerante da v1 (não bloqueia o apontamento).
    qtd_bobinas = int(dados_op.get("usu_qtdbob", 0) or 0) if dados_op else 0
    if qtd_bobinas <= 0:
        qtd_bobinas = 1

    ids_apont_criados = []
    erro_transacao = None
    try:
        with transaction.atomic():
            recurso_travado, periodos_abertos = _bloquear_recurso_e_periodos_abertos(
                recurso_selecionado
            )
            if not any(p.id == periodo.id for p in periodos_abertos):
                erro_transacao = "Esta OP não está mais acoplada a este recurso."
                raise ValueError(erro_transacao)

            agora = timezone.now().replace(microsecond=0)
            # datmov/hormov são CharField enviados ao ERP: precisam do horário
            # local (America/Sao_Paulo), não do UTC que timezone.now() retorna
            # com USE_TZ=True. data_hora continua em agora (UTC), pois é um
            # DateTimeField — o Django já converte para exibição.
            agora_local = timezone.localtime(agora)

            sucesso, resultado_rateio = _calcular_plano_rateio_consumo(recurso_travado, qtd_prod)
            if not sucesso:
                erro_transacao = resultado_rateio
                raise ValueError(erro_transacao)
            fatias = resultado_rateio

            # Bobinas que o cálculo teórico zeraria: a bobina pode ter
            # rendido mais (ou menos) do que o previsto na prática, então o
            # operador confirma a situação real antes de debitar de verdade.
            # Toda bobina pendente precisa de resposta explícita — havendo
            # qualquer uma sem resposta, a transação é abortada (sem persistir
            # nada, pois só houve select_for_update) e a lista de pendências
            # volta para a tela via sessão para o operador responder.
            pendentes = _bobinas_a_confirmar(fatias)
            respostas = {}
            algo_faltando = False
            for pendencia in pendentes:
                bobina_id = pendencia["bobina"].id
                resposta = dados_post.get(f"resposta_consumo_{bobina_id}")
                if resposta == "parcial":
                    valor = dados_post.get(f"resposta_consumo_valor_{bobina_id}")
                    try:
                        valor_decimal = Decimal(str(valor))
                        if valor_decimal < 1 or valor_decimal % 1 != 0:
                            raise ValueError("valor deve ser inteiro >= 1")
                    except Exception:
                        algo_faltando = True
                        continue
                    resposta = f"parcial:{valor_decimal}"
                elif resposta not in ("emenda", "sem_emenda"):
                    algo_faltando = True
                    continue
                elif resposta == "emenda" and not pendencia["tem_proximo_passo"]:
                    # Não há próximo passo planejado nesta cadeia para
                    # emendar (ex: bobina única cobrindo a fatia inteira) —
                    # "emenda" e "sem_emenda" são equivalentes nesse caso.
                    resposta = "sem_emenda"
                respostas[bobina_id] = resposta

            if algo_faltando:
                request.session[chave_sessao_confirmacao] = {
                    "periodo_id": periodo.id,
                    "qtd_bobinas_em_consumo": len(fatias),
                    "dados_originais": {
                        "periodo_id_apontamento": str(periodo_id),
                        "peso_total": str(qtd_prod),
                        "qtdrfg": str(qtd_ref),
                        "autorizado_modal": "1" if autorizado_modal else "0",
                        "origem_peso": origem_peso,
                        "confirmar_pesagem_duplicada": dados_post.get(
                            "confirmar_pesagem_duplicada", ""
                        ),
                    },
                    "bobinas": [
                        {
                            "bobina_id": p["bobina"].id,
                            "lote": p["bobina"].lote,
                            "quantidade_restante": str(p["bobina"].quantidade_restante),
                            "quantidade_planejada": str(p["quantidade_planejada"]),
                            "total_fatia": str(p["total_fatia"]),
                            "posicao_na_fatia": p["posicao_na_fatia"],
                            "bobinas_na_fatia": p["bobinas_na_fatia"],
                            "tem_proximo_passo": p["tem_proximo_passo"],
                        }
                        for p in pendentes
                    ],
                }
                erro_transacao = None
                raise ValueError("__PENDENTE_CONFIRMACAO__")

            request.session.pop(chave_sessao_confirmacao, None)
            extrato_consumo = _aplicar_plano_rateio_consumo(recurso_travado, fatias, respostas)

            # Um BaixaComponente por bobina de consumo debitada neste
            # apontamento (em consumo ou promovida da fila). lotdes fica
            # vazio: o consumo é único por apontamento, não por bobina
            # produzida — vincular a um dos N lotes gerados seria arbitrário.
            for item in extrato_consumo:
                bobina_consumida = item["bobina"]
                BaixaComponente.objects.create(
                    recurso=recurso_travado,
                    usuario=request.user,
                    codemp=cod_emp,
                    origem=periodo.origem,
                    numorp=periodo.op,
                    codetg=periodo.estagio,
                    seqrot=periodo.seqrot,
                    lotdes=None,
                    codcmp=bobina_consumida.codpro,
                    dercmp=bobina_consumida.codder,
                    qtduti=item["quantidade_debitada"],
                    codigo_integrador=codigo_integrador_centro,
                    datmov=agora_local.strftime("%d/%m/%Y"),
                    hormov=agora_local.strftime("%H:%M:%S"),
                    codlot=bobina_consumida.lote,
                    repesagem="N",
                    consumototal="S" if item["consumo_total"] else "N",
                    status=BaixaComponente.Status.NAO_INTEGRADO,
                    data_hora=agora,
                    datger=agora,
                )

            # Rateio em centavos inteiros, resto na última bobina — mesma regra da v1.
            q_tot = round(qtd_prod * 100)
            f_tot = round(qtd_ref * 100)
            q_rat, r_rat = divmod(q_tot, qtd_bobinas)
            f_rat, rf_rat = divmod(f_tot, qtd_bobinas)

            tempo_ciclo = agora
            tempo_ciclo_local = agora_local
            emp_obj = Empresa.objects.select_for_update().get(codemp=int(cod_emp))
            for indice in range(qtd_bobinas):
                eh_ultimo = indice == qtd_bobinas - 1
                qtd_at = (q_rat + (r_rat if eh_ultimo else 0)) / 100.0
                ref_at = (f_rat + (rf_rat if eh_ultimo else 0)) / 100.0
                lote_at = normalizar_lote_numerico(emp_obj.loteatual)
                emp_obj.loteatual = incrementar_lote(lote_at)
                emp_obj.save()
                if indice > 0:
                    tempo_ciclo += timedelta(seconds=1)
                    tempo_ciclo_local += timedelta(seconds=1)
                apontamento = salvar_log_apontamento(
                    cod_emp,
                    periodo.origem,
                    periodo.op,
                    periodo.estagio,
                    periodo.seqrot,
                    numcad_producao,
                    qtd_at,
                    ref_at,
                    lote_at,
                    codigo_integrador_centro,
                    tempo_ciclo_local.strftime("%d/%m/%Y"),
                    tempo_ciclo_local.strftime("%H:%M:%S"),
                    tempo_ciclo,
                    None,
                    origem_peso if qtd_at > 0 else None,
                    recurso_travado,
                    request.user,
                )
                if apontamento:
                    ids_apont_criados.append(apontamento.id)

            if not ids_apont_criados:
                erro_transacao = "Nenhum registro de apontamento foi gerado."
                raise ValueError(erro_transacao)
    except ValueError as erro:
        # A exceção força o rollback de todo o bloco atomic (débito de
        # consumo incluído) — nunca deve sobrar consumo debitado sem os
        # registros de produção correspondentes. O rateio nem chegou a ser
        # debitado neste caso: só houve select_for_update (leitura), então
        # não há nada de fato a desfazer além de encerrar a transação.
        if str(erro) == "__PENDENTE_CONFIRMACAO__":
            messages.warning(
                request,
                "Confirme a situação real de cada bobina que zeraria neste apontamento antes de continuar.",
            )
        else:
            messages.error(request, erro_transacao or "Falha ao gerar o apontamento.")
        return

    request.session.pop(f"numcad_operador_producao_{recurso_id}", None)
    request.session.pop(f"nome_operador_producao_{recurso_id}", None)
    threading.Thread(target=processar_logs_pendentes, daemon=True).start()
    disparar_envio_baixas_componentes()
    messages.success(
        request,
        f"{len(ids_apont_criados)} lote(s) apontado(s) para a OP {periodo.op}, "
        f"{qtd_prod:g} de produção{f' e {qtd_ref:g} de refugo' if qtd_ref > 0 else ''} rateados entre eles.",
    )


def _validar_operador_producao(request, recurso_id, cod_emp):
    """Valida no ERP o operador que vai apontar produção agora.

    Mesmo padrão da v1: fica salvo na sessão do recurso até ser trocado ou
    até um apontamento de produção ser concluído (quando a gravação existir),
    momento em que a sessão deve ser limpa para forçar nova validação. Este
    operador é distinto do informado ao acoplar a OP, que representa quem
    iniciou aquele período de tempo (LogTrocaOPAtiva.id_operador).
    """
    numcad = request.POST.get("numcad_producao")
    if not numcad:
        messages.error(request, "Informe o ID do operador.")
        return
    try:
        with cursor_oracle_erp() as cursor:
            nome_operador = valida_operador(cursor, cod_emp, numcad)
    except Exception:
        logger.exception("Falha ao validar operador de produção no ERP")
        messages.error(request, "Não foi possível validar o operador no ERP.")
        return
    if not nome_operador:
        messages.error(
            request, f"Operador {numcad} não encontrado ou inativo na empresa {cod_emp}."
        )
        return

    request.session[f"numcad_operador_producao_{recurso_id}"] = numcad
    request.session[f"nome_operador_producao_{recurso_id}"] = nome_operador


def _trocar_operador_producao(request, recurso_id):
    request.session.pop(f"numcad_operador_producao_{recurso_id}", None)
    request.session.pop(f"nome_operador_producao_{recurso_id}", None)


def _consultar_dados_op_erp(cursor, cod_emp, cod_ori, num_op):
    """Consulta cabeçalho, produto e componentes de uma OP acoplada no ERP.

    Estrutura equivalente à consulta usada na v1, mas isolada por OP porque
    aqui várias OPs são consultadas na mesma passada (uma por período aberto).
    """
    cursor.execute(
        """
            SELECT cop.sitorp, qdo.codpro, qdo.codder, qdo.qtdprv, qdo.qtdre1 qtd_produzida,
                   pro.despro, cop.usu_qtdbob
            FROM e900cop cop
            JOIN e900qdo qdo ON qdo.codemp = cop.codemp AND qdo.codori = cop.codori AND qdo.numorp = cop.numorp
            LEFT JOIN e075pro pro ON pro.codemp = qdo.codemp AND pro.codpro = qdo.codpro
            WHERE cop.codemp = :codemp AND cop.codori = :codori AND cop.numorp = :numorp
              AND qdo.proori = 'S'
        """,
        {"codemp": cod_emp, "codori": cod_ori, "numorp": num_op},
    )
    colunas = [c[0].lower() for c in cursor.description]
    linha = cursor.fetchone()
    dados_op = dict(zip(colunas, linha, strict=False)) if linha else None
    if dados_op:
        sit_map = {
            "E": "Explodida",
            "L": "Liberada",
            "S": "Suspensa",
            "F": "Finalizada",
            "A": "Em andamento",
            "C": "Cancelada",
            "R": "Reabilitada",
        }
        dados_op["sitorp_display"] = sit_map.get(dados_op["sitorp"], dados_op["sitorp"])

    cursor.execute(
        """
            SELECT cmo.codcmp, cmo.codder, pro.despro
            FROM e900cmo cmo
            LEFT JOIN e075pro pro ON pro.codemp = cmo.codemp AND pro.codpro = cmo.codcmp
            WHERE cmo.codemp = :codemp AND cmo.codori = :codori AND cmo.numorp = :numorp
            ORDER BY cmo.codcmp
        """,
        {"codemp": cod_emp, "codori": cod_ori, "numorp": num_op},
    )
    colunas_comp = [c[0].lower() for c in cursor.description]
    componentes = [dict(zip(colunas_comp, linha, strict=False)) for linha in cursor.fetchall()]

    return dados_op, componentes


def _chaves_componentes(componentes):
    """Retorna os componentes comparáveis da estrutura: produto + derivação."""
    return {
        _chave_produto_derivacao(componente["codcmp"], componente.get("codder"))
        for componente in componentes
        if componente.get("codcmp")
    }


def _chave_produto_derivacao(produto, derivacao):
    return str(produto or "").strip(), str(derivacao or "").strip()


def _componentes_compartilhados_das_ops_erp(cod_emp, ops):
    """Busca a interseção de produto+derivação das OPs informadas no ERP."""
    if not ops:
        return set()

    with cursor_oracle_erp() as cursor:
        componentes_em_comum = None
        for origem, op in ops:
            _, componentes = _consultar_dados_op_erp(cursor, cod_emp, origem, op)
            chaves_op = _chaves_componentes(componentes)
            componentes_em_comum = (
                chaves_op if componentes_em_comum is None else componentes_em_comum & chaves_op
            )

    return componentes_em_comum or set()


def _bobinas_ativas_do_recurso(recurso, bloquear=False):
    consulta = BobinaConsumoRecurso.objects.filter(
        recurso=recurso,
        status__in=[
            BobinaConsumoRecurso.Status.EM_FILA,
            BobinaConsumoRecurso.Status.EM_CONSUMO,
        ],
    ).order_by("id")
    if bloquear:
        consulta = consulta.select_for_update()
    return list(consulta)


def _bobinas_incompativeis(bobinas, componentes_permitidos):
    return [
        bobina
        for bobina in bobinas
        if _chave_produto_derivacao(bobina.codpro, bobina.codder) not in componentes_permitidos
    ]


def _formatar_chave_componente(chave):
    produto, derivacao = chave
    return f"{produto}-{derivacao}" if derivacao else produto


def _formatar_bobinas(bobinas):
    itens = [
        f"{bobina.lote} ({_formatar_chave_componente(_chave_produto_derivacao(bobina.codpro, bobina.codder))})"
        for bobina in bobinas[:5]
    ]
    if len(bobinas) > 5:
        itens.append(f"e mais {len(bobinas) - 5}")
    return ", ".join(itens)


@login_required
def apontamentos_view(request):
    """Tela Multi-OP (rebobinadeira): múltiplas OPs acopladas simultaneamente
    no mesmo recurso, painel de Produção (uma OP por apontamento) e painel de
    Consumo (bobinas de consumo rateadas + fila). O rateio/débito de consumo
    já é gravado de verdade; Apontamento/ApontamentoComponente ainda não.
    """
    empresa_id = request.POST.get("empresa", request.GET.get("empresa", ""))
    centro_id = request.POST.get("centro", request.GET.get("centro", ""))
    recurso_id = request.POST.get("recurso", request.GET.get("recurso", ""))
    codbar = (request.POST.get("codbar") or request.GET.get("codbar", "")).strip()

    pode_apontar = request.user.is_staff or request.user.has_perm("producao.pode_apontar")

    empresas = empresas_visiveis_apontamento(request.user)

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
                .select_related(
                    "parametros_recurso",
                    "centro_recurso__parametros_centro_recurso",
                    "centro_recurso__setor__departamento__filial__parametros_filial",
                )
                .get(id=recurso_id, centro_recurso_id=centro_id)
            )
        except Recurso.DoesNotExist:
            recurso_selecionado = None

    if not recurso_selecionado:
        return render(
            request,
            "producao/apontamentos_v3.html",
            {
                "empresas": empresas,
                "empresa_id": empresa_id,
                "centros": centros,
                "centro_id": centro_id,
                "recursos": recursos,
                "recurso_id": recurso_id,
                "recurso_selecionado": None,
                "codbar": codbar,
            },
        )

    cod_emp = recurso_selecionado.centro_recurso.setor.departamento.filial.empresa.codemp
    parametros_apontamento = recurso_selecionado.get_parametros_efetivos()

    if request.method == "POST":
        if not pode_apontar:
            messages.error(request, "Você não possui permissão para apontar.")
        elif "acoplar_op" in request.POST:
            _acoplar_op(
                request,
                recurso_selecionado,
                cod_emp,
                request.POST.get("codbar_acoplar", "").strip(),
            )
        elif "desacoplar_op" in request.POST:
            _desacoplar_op(request, recurso_selecionado, request.POST.get("periodo_id"))
        elif "alocar_bobina" in request.POST:
            _alocar_bobina_consumo(
                request,
                recurso_selecionado,
                cod_emp,
                request.POST.get("lote_alocar", ""),
                request.POST.get("destino_alocar", "fila"),
            )
        elif "desalocar_bobina" in request.POST:
            _desalocar_bobina_consumo(request, recurso_selecionado, request.POST.get("bobina_id"))
        elif "validar_operador_producao" in request.POST:
            _validar_operador_producao(request, recurso_id, cod_emp)
        elif "trocar_operador_producao" in request.POST:
            _trocar_operador_producao(request, recurso_id)
        elif "cancelar_confirmacao_consumo" in request.POST:
            # Nada foi debitado ainda nesse ponto (a transação que calculou o
            # plano teórico sempre dá rollback antes de pedir confirmação) —
            # só a sessão precisa ser limpa.
            request.session.pop(f"consumo_a_confirmar_{recurso_id}", None)
            messages.info(request, "Apontamento cancelado.")
        elif "apontar_producao" in request.POST:
            _apontar_producao(
                request, recurso_selecionado, recurso_id, cod_emp, parametros_apontamento
            )
        return redirect(
            f"{request.path}?empresa={empresa_id}&centro={centro_id}&recurso={recurso_id}&codbar={codbar}"
        )

    periodos_abertos = list(
        LogTrocaOPAtiva.objects.filter(
            recurso=recurso_selecionado, horario_saida__isnull=True
        ).order_by("horario_troca")
    )

    sequencias = Sequenciamento.objects.filter(recurso=recurso_selecionado).order_by("ordenacao")
    codigos_ja_acoplados = {periodo.codigo_barra for periodo in periodos_abertos}
    sequencias_disponiveis_para_acoplar = [
        s for s in sequencias if s.codigo_barra not in codigos_ja_acoplados
    ]

    ops_acopladas = []
    componentes_ja_acoplados = None
    if periodos_abertos or sequencias_disponiveis_para_acoplar:
        try:
            with cursor_oracle_erp() as cursor:
                dados_por_periodo = {
                    periodo.id: _consultar_dados_op_erp(cursor, cod_emp, periodo.origem, periodo.op)
                    for periodo in periodos_abertos
                }
                if periodos_abertos:
                    componentes_ja_acoplados = set()
                    for _, comp_periodo in dados_por_periodo.values():
                        componentes_ja_acoplados |= _chaves_componentes(comp_periodo)

                for sequencia in sequencias_disponiveis_para_acoplar:
                    if componentes_ja_acoplados is None:
                        sequencia.tem_componente_em_comum = None
                        continue
                    _, comp_sequencia = _consultar_dados_op_erp(
                        cursor, cod_emp, sequencia.origem, sequencia.op
                    )
                    sequencia.tem_componente_em_comum = bool(
                        componentes_ja_acoplados & _chaves_componentes(comp_sequencia)
                    )

                for periodo in periodos_abertos:
                    dados_op, componentes = dados_por_periodo[periodo.id]
                    percentual_produzido = None
                    if dados_op and dados_op.get("qtdprv"):
                        percentual_produzido = round(
                            float(dados_op["qtd_produzida"] or 0) / float(dados_op["qtdprv"]) * 100,
                            1,
                        )
                    ultimo_apontamento = (
                        Apontamento.objects.filter(
                            codemp=cod_emp,
                            origem=periodo.origem,
                            numorp=periodo.op,
                            codetg=periodo.estagio,
                            seqrot=periodo.seqrot,
                        )
                        .order_by("-id")
                        .first()
                    )
                    ultimo_peso_apontado = None
                    ultimo_apontamento_segundos = None
                    if ultimo_apontamento:
                        ultimo_peso_apontado = float(ultimo_apontamento.qtdre1 or 0) + float(
                            ultimo_apontamento.qtdrfg or 0
                        )
                        ultimo_apontamento_segundos = int(
                            (timezone.now() - ultimo_apontamento.data_hora).total_seconds()
                        )
                    ops_acopladas.append(
                        {
                            "periodo": periodo,
                            "codigo_barra": periodo.codigo_barra,
                            "dados_op": dados_op,
                            "componentes": componentes,
                            "percentual_produzido": percentual_produzido,
                            "ultimo_peso_apontado": ultimo_peso_apontado,
                            "ultimo_apontamento_segundos": ultimo_apontamento_segundos,
                            # Produção desta OP no ciclo atual: lista de lotes gerados
                            # (tamanho, quantidade, peso) — vazio até definirmos a
                            # gravação de Apontamento/consumo.
                            "producao_ciclo": [],
                        }
                    )
        except Exception:
            logger.exception("Falha ao consultar OPs no ERP")
            messages.error(request, "Não foi possível consultar as OPs no ERP.")

    bobinas_recurso = BobinaConsumoRecurso.objects.filter(recurso=recurso_selecionado)
    bobinas_em_consumo = list(
        bobinas_recurso.filter(status=BobinaConsumoRecurso.Status.EM_CONSUMO).order_by("id")
    )
    fila_bobinas_consumo = list(
        bobinas_recurso.filter(status=BobinaConsumoRecurso.Status.EM_FILA).order_by("ordem_fila")
    )

    lotes_com_consumo_real = set(
        BaixaComponente.objects.filter(
            codlot__in=[b.lote for b in [*bobinas_em_consumo, *fila_bobinas_consumo]],
            repesagem="N",
        )
        .values_list("codlot", flat=True)
        .distinct()
    )
    for bobina in [*bobinas_em_consumo, *fila_bobinas_consumo]:
        bobina.ja_teve_consumo = bobina.lote in lotes_com_consumo_real
        if bobina.quantidade_alocada:
            percentual_restante = float(
                bobina.quantidade_restante / bobina.quantidade_alocada * 100
            )
        else:
            percentual_restante = 0
        bobina.percentual_restante = round(percentual_restante, 1)
        if percentual_restante <= 15:
            bobina.nivel_saldo = "critical"
        elif percentual_restante <= 40:
            bobina.nivel_saldo = "warning"
        else:
            bobina.nivel_saldo = "good"

    taras_vinculadas = Tara.objects.filter(tara_recursos__recurso_id=recurso_id).order_by("tara")

    numcad_operador_producao = request.session.get(f"numcad_operador_producao_{recurso_id}")
    nome_operador_producao = request.session.get(f"nome_operador_producao_{recurso_id}")
    consumo_a_confirmar = request.session.get(f"consumo_a_confirmar_{recurso_id}")

    contexto = {
        "empresas": empresas,
        "empresa_id": empresa_id,
        "centros": centros,
        "centro_id": centro_id,
        "recursos": recursos,
        "recurso_id": recurso_id,
        "recurso_selecionado": recurso_selecionado,
        "codbar": codbar,
        "pode_apontar": pode_apontar,
        "sequencias": sequencias,
        "sequencias_disponiveis_para_acoplar": sequencias_disponiveis_para_acoplar,
        "ops_acopladas": ops_acopladas,
        # Consumo de bobinas é da máquina (BobinaConsumoRecurso.recurso),
        # compartilhado entre todas as OPs acopladas — rateio e baixa via
        # apontamento ainda não implementados.
        "bobinas_em_consumo": bobinas_em_consumo,
        "fila_bobinas_consumo": fila_bobinas_consumo,
        "parametros_apontamento": parametros_apontamento,
        "taras_vinculadas": taras_vinculadas,
        "numcad_operador_producao": numcad_operador_producao,
        "nome_operador_producao": nome_operador_producao,
        "consumo_a_confirmar": consumo_a_confirmar,
        **contexto_parada_recurso(recurso_selecionado),
    }
    return render(request, "producao/apontamentos_v3.html", contexto)
