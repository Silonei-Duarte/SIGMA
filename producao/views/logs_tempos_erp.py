from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from producao.models import ItemPacoteTempoERP, PacoteTempoERP
from producao.views.apontamento_base import recursos_visiveis_apontamento
from SIGMA.autorizacao import permissao_requerida


def _pacotes_visiveis(usuario):
    return PacoteTempoERP.objects.filter(
        troca_op_ativa__recurso__in=recursos_visiveis_apontamento(usuario)
    )


@login_required
@require_POST
def enviar_tempos_erp(request):
    from producao.services.envia_tempos_erp import disparar_envio_tempos_erp

    ids_pacotes = list(
        _pacotes_visiveis(request.user)
        .filter(status=PacoteTempoERP.Status.PENDENTE)
        .values_list("id", flat=True)
    )
    if not ids_pacotes:
        messages.info(request, "Não há pacotes pendentes para envio.")
    else:
        disparar_envio_tempos_erp(ids_pacotes)
        messages.info(
            request,
            "Processamento em background iniciado para envio dos pacotes de tempo ERP pendentes.",
        )
    return redirect("logs_tempos_erp")


@login_required
@require_POST
def enviar_pacote_tempo_erp(request, pk):
    from producao.services.envia_tempos_erp import (
        PROCESSAMENTO_TEMPOS_ERP_LOCK,
        disparar_envio_tempos_erp,
        reservar_pacote_tempo_erp_para_envio,
    )

    if PROCESSAMENTO_TEMPOS_ERP_LOCK.locked():
        messages.error(request, "Envio de tempos ERP já está em processamento.")
    else:
        if not _pacotes_visiveis(request.user).filter(pk=pk).exists():
            messages.error(request, "Pacote não disponível para o seu usuário.")
            return redirect("logs_tempos_erp")
        reservado, mensagem = reservar_pacote_tempo_erp_para_envio(pk)
        if not reservado:
            messages.error(request, mensagem)
        else:
            disparar_envio_tempos_erp([pk])
            messages.info(
                request, f"Processamento em background iniciado para o pacote de tempo ERP {pk}."
            )
    return redirect("logs_tempos_erp")


# Exclusões unificadas das filas: quem recebe pode_excluir_pendencias_integracao
# exclui (staff e superusuário passam pelo bypass do decorator); sem guard
# interno adicional.
@permissao_requerida("producao.pode_excluir_pendencias_integracao")
@require_POST
def excluir_pacote_tempo_erp(request, pk):
    # Mesmo padrão das filas irmãs: quem tem a permissão exclui dentro do
    # próprio escopo — pacote fora dos recursos visíveis do usuário não é
    # alcançável mesmo sabendo o pk.
    if not _pacotes_visiveis(request.user).filter(pk=pk).exists():
        messages.error(request, "Pacote não disponível para o seu usuário.")
        return redirect("logs_tempos_erp")

    pacote = get_object_or_404(PacoteTempoERP, pk=pk)
    if pacote.status != PacoteTempoERP.Status.PENDENTE:
        messages.error(
            request, f"Pacote {pk} já está integrado ou em processamento e não pode ser excluído."
        )
    else:
        pacote.delete()
        messages.success(request, f"Pacote de tempo ERP {pk} excluído com sucesso.")
    return redirect("logs_tempos_erp")


@permissao_requerida("producao.pode_excluir_pendencias_integracao")
@require_POST
def excluir_parada_pacote_tempo_erp(request, pk):
    pertence = ItemPacoteTempoERP.objects.filter(
        pk=pk,
        pacote_tempo_erp__troca_op_ativa__recurso__in=recursos_visiveis_apontamento(request.user),
    ).exists()
    if not pertence:
        messages.error(request, "Parada não disponível para o seu usuário.")
        return redirect("logs_tempos_erp")

    item = get_object_or_404(ItemPacoteTempoERP.objects.select_related("pacote_tempo_erp"), pk=pk)
    if item.tipo_registro != ItemPacoteTempoERP.TipoRegistro.PARADA:
        messages.error(request, "Apenas itens de parada podem ser excluídos individualmente.")
    elif item.pacote_tempo_erp.status != PacoteTempoERP.Status.PENDENTE:
        messages.error(
            request,
            "A parada pertence a um pacote já integrado ou em processamento e não pode ser excluída.",
        )
    else:
        item.delete()
        messages.success(request, f"Parada {pk} excluída do pacote de tempo ERP.")
    return redirect("logs_tempos_erp")


@permissao_requerida("producao.pode_excluir_pendencias_integracao")
@require_POST
def excluir_tempos_erp_nao_integrados(request):
    # Exclusão em massa limitada ao escopo do usuário; staff apaga global.
    total, _ = (
        _pacotes_visiveis(request.user).filter(status=PacoteTempoERP.Status.PENDENTE).delete()
    )
    if total:
        messages.success(request, "Pacotes de tempo ERP não integrados foram excluídos.")
    else:
        messages.info(request, "Não há pacotes de tempo ERP não integrados para excluir.")
    return redirect("logs_tempos_erp")


@login_required
def logs_tempos_erp(request):
    search_query = (request.GET.get("search") or "").strip()
    pacotes_anteriores = PacoteTempoERP.objects.filter(
        troca_op_ativa__recurso_id=OuterRef("troca_op_ativa__recurso_id"),
        troca_op_ativa__origem=OuterRef("troca_op_ativa__origem"),
        troca_op_ativa__op=OuterRef("troca_op_ativa__op"),
        troca_op_ativa__estagio=OuterRef("troca_op_ativa__estagio"),
        troca_op_ativa__seqrot=OuterRef("troca_op_ativa__seqrot"),
        status__in=[
            PacoteTempoERP.Status.PENDENTE,
            PacoteTempoERP.Status.PROCESSANDO,
        ],
        corte_fim_real__lt=OuterRef("corte_fim_real"),
    )
    pacotes = (
        _pacotes_visiveis(request.user)
        .annotate(tem_pendente_anterior=Exists(pacotes_anteriores))
        .select_related(
            "troca_op_ativa__recurso__centro_recurso__setor__departamento__filial__empresa"
        )
        .prefetch_related("itens")
        .order_by("-corte_fim_real", "-id")
    )

    if search_query:
        filtros = (
            Q(troca_op_ativa__origem__icontains=search_query)
            | Q(troca_op_ativa__recurso__codigo__icontains=search_query)
            | Q(troca_op_ativa__recurso__descricao__icontains=search_query)
        )
        if search_query.isdigit():
            numero = int(search_query)
            filtros |= (
                Q(id=numero) | Q(troca_op_ativa__op=numero) | Q(troca_op_ativa__id_operador=numero)
            )
        pacotes = pacotes.filter(filtros)

    page_obj = Paginator(pacotes, 20).get_page(request.GET.get("page"))
    from producao.services.envia_tempos_erp import PROCESSAMENTO_TEMPOS_ERP_LOCK

    bloqueados_ids = [
        pacote.id
        for pacote in page_obj
        if pacote.status == PacoteTempoERP.Status.PENDENTE
        and (PROCESSAMENTO_TEMPOS_ERP_LOCK.locked() or pacote.tem_pendente_anterior)
    ]
    # Botões de exclusão visíveis a quem a rota autoriza (staff/superusuário
    # pelo bypass ou portador da permissão unificada).
    pode_excluir_pendencias = (
        request.user.is_staff
        or request.user.is_superuser
        or request.user.has_perm("producao.pode_excluir_pendencias_integracao")
    )
    return render(
        request,
        "producao/logs_tempos_erp.html",
        {
            "pacotes": page_obj,
            "search_query": search_query,
            "bloqueados_ids": bloqueados_ids,
            "pode_excluir_pendencias": pode_excluir_pendencias,
        },
    )
