from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from SIGMA.autorizacao import permissao_requerida

from ..forms import SetorForm
from ..models import Setor


@permissao_requerida("accounts.manipular_cadastros")
def setores_view(request, setor_id=None):

    # limpa mensagens antigas
    storage = messages.get_messages(request)
    storage.used = True

    # Se veio id, é edição
    if setor_id:
        setor = get_object_or_404(Setor, id=setor_id)
    else:
        setor = None

    if request.method == "POST":
        form = SetorForm(request.POST, instance=setor)
        if form.is_valid():
            # bloqueio ID = 1 (Setor Geral)
            if setor and setor.id == 1:
                if form.cleaned_data.get("descricao") != setor.descricao:
                    messages.warning(request, "O Setor Geral não pode ter a descrição alterada.")
                    return redirect("setores")

            form.save()
            if setor:
                messages.success(request, "Setor atualizado com sucesso!")
            else:
                messages.success(request, "Setor cadastrado com sucesso!")
            return redirect("setores")

    else:
        form = SetorForm(instance=setor)

    # listagem
    setores = Setor.objects.select_related(
        "departamento",
        "departamento__filial",
    ).order_by(
        "departamento__filial__empresa_id",
        "departamento__filial__nome",
        "departamento__descricao",
        "descricao",
    )

    paginator = Paginator(setores, 30)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "accounts/setores.html",
        {
            "form": form,
            "page_obj": page_obj,
            "setor_editando": setor,
        },
    )


@require_POST
@permissao_requerida("accounts.manipular_cadastros")
def deletar_setor(request, pk):

    setor = get_object_or_404(Setor, pk=pk)
    try:
        setor.delete()
        messages.success(request, "Setor excluído com sucesso.")
    except ProtectedError:
        messages.warning(
            request, "Não é possível excluir: existem Centros de Recursos vinculados a este Setor."
        )
    return redirect("setores")
