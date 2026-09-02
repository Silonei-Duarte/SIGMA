from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from SIGMA.autorizacao import permissao_requerida

from ..forms import DepartamentoForm
from ..models import Departamento


@permissao_requerida("accounts.manipular_cadastros")
def lista_departamentos(request):

    # limpa mensagens antigas
    storage = messages.get_messages(request)
    storage.used = True

    departamentos = Departamento.objects.select_related("filial").all().order_by("descricao")
    paginator = Paginator(departamentos, 30)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "accounts/lista_departamentos.html", {"page_obj": page_obj})


@permissao_requerida("accounts.manipular_cadastros")
def cadastrar_departamento(request):

    if request.method == "POST":
        form = DepartamentoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Departamento cadastrado com sucesso!")
            return redirect("lista_departamentos")
    else:
        form = DepartamentoForm()
    return render(
        request,
        "accounts/form_departamento.html",
        {"form": form, "title": "Cadastrar Departamento", "button_text": "Salvar"},
    )


@permissao_requerida("accounts.manipular_cadastros")
def editar_departamento(request, departamento_id):

    departamento = get_object_or_404(Departamento, id=departamento_id)
    if request.method == "POST":
        form = DepartamentoForm(request.POST, instance=departamento)
        if form.is_valid():
            form.save()
            messages.success(request, "Departamento atualizado com sucesso!")
            return redirect("lista_departamentos")
    else:
        form = DepartamentoForm(instance=departamento)
    return render(
        request,
        "accounts/form_departamento.html",
        {"form": form, "title": "Editar Departamento", "button_text": "Atualizar"},
    )


@require_POST
@permissao_requerida("accounts.manipular_cadastros")
def deletar_departamento(request, pk):

    departamento = get_object_or_404(Departamento, pk=pk)
    try:
        departamento.delete()
        messages.success(request, "Departamento excluído com sucesso!")
    except ProtectedError:
        messages.warning(
            request, "Não é possível excluir: o departamento está vinculado a setores."
        )
    return redirect("lista_departamentos")
