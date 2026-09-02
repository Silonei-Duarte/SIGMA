from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from setores.qualidade.models import ObservacaoEtiqueta
from SIGMA.autorizacao import permissao_requerida


# Mantém o cadastro de observações pré-definidas usadas nas etiquetas da área vermelha.
@permissao_requerida("qualidade.pode_cadastrar_observacoes_etiqueta")
def observacoes_etiqueta(request):
    observacao_id = request.POST.get("observacao_id") if request.method == "POST" else None
    observacao_edicao = None
    status = request.GET.get("status", "todas")

    if observacao_id:
        observacao_edicao = get_object_or_404(ObservacaoEtiqueta, pk=observacao_id)

    if request.method == "POST":
        action = request.POST.get("action")
        descricao = (request.POST.get("descricao") or "").strip().upper()
        ativo = request.POST.get("ativo") == "on"

        if action in {"salvar", "editar"}:
            if not descricao:
                messages.warning(request, "Informe a descrição da observação.")
            elif (
                ObservacaoEtiqueta.objects.filter(descricao__iexact=descricao)
                .exclude(pk=observacao_id)
                .exists()
            ):
                messages.warning(request, "Já existe uma observação cadastrada com esta descrição.")
            else:
                if observacao_edicao:
                    observacao_edicao.descricao = descricao
                    observacao_edicao.ativo = ativo
                    observacao_edicao.save(update_fields=["descricao", "ativo"])
                    messages.success(request, "Observação atualizada.")
                else:
                    ObservacaoEtiqueta.objects.create(descricao=descricao, ativo=ativo)
                    messages.success(request, "Observação cadastrada.")
                return redirect("qualidade:observacoes_etiqueta")

        elif action == "alternar":
            if observacao_edicao:
                observacao_edicao.ativo = not observacao_edicao.ativo
                observacao_edicao.save(update_fields=["ativo"])
                messages.success(request, "Status da observação atualizado.")
            return redirect("qualidade:observacoes_etiqueta")

        elif action == "excluir":
            if observacao_edicao:
                if observacao_edicao.liberacoes_lote.exists():
                    messages.warning(
                        request,
                        "Não é possível excluir: a observação já está vinculada a registros.",
                    )
                else:
                    observacao_edicao.delete()
                    messages.success(request, "Observação excluída.")
            return redirect("qualidade:observacoes_etiqueta")

    observacoes = ObservacaoEtiqueta.objects.all()
    if status == "inativas":
        observacoes = observacoes.filter(ativo=False)
    elif status != "todas":
        status = "ativas"
        observacoes = observacoes.filter(ativo=True)

    paginator = Paginator(observacoes, 30)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "setores/qualidade/observacoes_etiqueta.html",
        {
            "titulo": "Observações de Etiqueta",
            "page_obj": page_obj,
            "status": status,
        },
    )
