from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from SIGMA.autorizacao import permissao_requerida

from ..forms import CentroRecursoForm, ParametrosCentroRecursoForm
from ..models import CentroRecurso


def _parametros_centro_vazios(form):
    for campo in form.Meta.fields:
        valor = form.cleaned_data.get(campo)
        if valor not in (None, ""):
            return False
    return True


def _salvar_parametros_centro(form, centro):
    if _parametros_centro_vazios(form):
        if form.instance and form.instance.pk:
            form.instance.delete()
        return

    parametros = form.save(commit=False)
    parametros.centro_recurso = centro
    parametros.save()


@permissao_requerida("accounts.manipular_cadastros")
def centros_recursos_view(request, centro_id=None):

    # limpa mensagens antigas
    storage = messages.get_messages(request)
    storage.used = True

    # edição ou novo
    if centro_id:
        centro = get_object_or_404(CentroRecurso, id=centro_id)
    else:
        centro = None

    # sempre cria form base
    form = CentroRecursoForm(instance=centro)
    parametros = getattr(centro, "parametros_centro_recurso", None) if centro else None
    param_form = ParametrosCentroRecursoForm(instance=parametros)

    if request.method == "POST":
        form = CentroRecursoForm(request.POST, instance=centro)
        param_form = ParametrosCentroRecursoForm(request.POST, instance=parametros)

        if form.is_valid() and param_form.is_valid():
            # bloqueio ID = 1
            if centro and centro.id == 1:
                if form.cleaned_data.get("descricao") != centro.descricao:
                    messages.warning(
                        request, "Este Centro de Recurso não pode ter a descrição alterada."
                    )
                    return redirect("centros_recursos")

            centro_salvo = form.save()
            _salvar_parametros_centro(param_form, centro_salvo)
            if centro:
                messages.success(request, "Centro de Recurso atualizado com sucesso!")
            else:
                messages.success(request, "Centro de Recurso cadastrado com sucesso!")
            return redirect("centros_recursos")

    # listagem
    centros = CentroRecurso.objects.select_related(
        "setor",
        "setor__departamento",
        "setor__departamento__filial",
    ).order_by(
        "setor__departamento__filial__empresa_id",
        "setor__departamento__filial__nome",
        "setor__departamento__descricao",
        "setor__descricao",
        "descricao",
    )

    paginator = Paginator(centros, 30)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "accounts/centros_recursos.html",
        {
            "form": form,
            "param_form": param_form,
            "page_obj": page_obj,
            "centro_editando": centro,
        },
    )


@require_POST
@permissao_requerida("accounts.manipular_cadastros")
def deletar_centro_recurso(request, pk):

    centro = get_object_or_404(CentroRecurso, pk=pk)
    try:
        centro.delete()
        messages.success(request, "Centro de Recurso excluído com sucesso.")
    except ProtectedError:
        messages.warning(
            request,
            "Não é possível excluir: Existem registros vinculados a este Centro de Recurso.",
        )
    return redirect("centros_recursos")
