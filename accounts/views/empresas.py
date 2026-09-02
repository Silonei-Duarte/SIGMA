from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from SIGMA.autorizacao import permissao_requerida

from ..forms import EmpresaForm
from ..models import Empresa


@permissao_requerida("accounts.manipular_cadastros")
def lista_empresas(request):
    empresas = Empresa.objects.all().order_by("nome")
    paginator = Paginator(empresas, 30)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(request, "accounts/lista_empresas.html", {"page_obj": page_obj})


@permissao_requerida("accounts.manipular_cadastros")
def criar_empresa(request):
    if request.method == "POST":
        form = EmpresaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Empresa criada com sucesso!")
            return redirect("lista_empresas")
    else:
        form = EmpresaForm()
    return render(
        request,
        "accounts/form_empresa.html",
        {"form": form, "title": "Nova Empresa", "button_text": "Salvar"},
    )


@permissao_requerida("accounts.manipular_cadastros")
def editar_empresa(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)
    if request.method == "POST":
        form = EmpresaForm(request.POST, instance=empresa)
        if form.is_valid():
            form.save()
            messages.success(request, "Empresa atualizada com sucesso!")
            return redirect("lista_empresas")
    else:
        form = EmpresaForm(instance=empresa)
    return render(
        request,
        "accounts/form_empresa.html",
        {"form": form, "title": "Editar Empresa", "button_text": "Atualizar"},
    )
