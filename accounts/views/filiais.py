from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from SIGMA.autorizacao import permissao_requerida

from ..forms import FilialForm, ParametrosFilialForm
from ..models import CentroRecurso, Departamento, Filial, ParametrosFilial, Recurso, Setor


def get_filiais_paginadas(request):
    filiais = Filial.objects.select_related("empresa").all().order_by("empresa__nome", "nome")
    paginator = Paginator(filiais, 30)
    page_number = request.GET.get("page")
    return paginator.get_page(page_number)


@permissao_requerida("accounts.manipular_cadastros")
def lista_filiais(request, pk=None):
    # edição ou criação
    filial = get_object_or_404(Filial, pk=pk) if pk else None
    parametros = getattr(filial, "parametros_filial", None) if filial else None

    if request.method == "POST":
        form = FilialForm(request.POST, instance=filial)
        param_form = ParametrosFilialForm(request.POST, instance=parametros)
        if form.is_valid() and param_form.is_valid():
            filial_salva = form.save()
            parametros_salvos = param_form.save(commit=False)
            parametros_salvos.filial = filial_salva
            parametros_salvos.save()
            if filial:
                messages.success(request, "Filial atualizada com sucesso!")
            else:
                messages.success(request, "Filial criada com sucesso!")
            return redirect("lista_filiais")
    else:
        form = FilialForm(instance=filial) if filial else FilialForm()
        param_form = ParametrosFilialForm(
            instance=parametros, initial=ParametrosFilial.defaults() if not parametros else None
        )

    page_obj = get_filiais_paginadas(request)
    return render(
        request,
        "accounts/filial.html",
        {
            "form": form,
            "param_form": param_form,
            "title": "Editar Filial" if filial else "Nova Filial",
            "button_text": "Atualizar" if filial else "Salvar",
            "page_obj": page_obj,
            "filial_editando": filial,
        },
    )


@require_POST
@permissao_requerida("accounts.manipular_cadastros")
def excluir_filial(request, pk):
    filial = get_object_or_404(Filial, pk=pk)
    try:
        filial.delete()
        messages.success(request, "Filial excluída com sucesso!")
    except ProtectedError:
        messages.error(
            request, "Não é possível excluir: a filial está vinculada a outros registros."
        )
    return redirect("lista_filiais")


@login_required
def ajax_filiais(request):
    empresa_id = request.GET.get("empresa_id")
    qs = Filial.objects.all()
    if empresa_id:
        qs = qs.filter(empresa_id=empresa_id)
    return JsonResponse(list(qs.values("id", "codfil", "nome")), safe=False)


@login_required
def ajax_departamentos(request):
    filial_id = request.GET.get("filial_id")
    empresa_id = request.GET.get("empresa_id")

    qs = Departamento.objects.all()
    if filial_id:
        qs = qs.filter(filial_id=filial_id)
    elif empresa_id:
        qs = qs.filter(filial__empresa_id=empresa_id)

    return JsonResponse(list(qs.values("id", "descricao")), safe=False)


@login_required
def ajax_setores(request):
    departamento_id = request.GET.get("departamento_id")
    filial_id = request.GET.get("filial_id")
    empresa_id = request.GET.get("empresa_id")

    qs = Setor.objects.all()
    if departamento_id:
        qs = qs.filter(departamento_id=departamento_id)
    elif filial_id:
        qs = qs.filter(departamento__filial_id=filial_id)
    elif empresa_id:
        qs = qs.filter(departamento__filial__empresa_id=empresa_id)

    return JsonResponse(list(qs.values("id", "descricao")), safe=False)


@login_required
def ajax_centros(request):
    setor_id = request.GET.get("setor_id")
    departamento_id = request.GET.get("departamento_id")
    filial_id = request.GET.get("filial_id")
    empresa_id = request.GET.get("empresa_id")

    qs = CentroRecurso.objects.all()
    if setor_id:
        qs = qs.filter(setor_id=setor_id)
    elif departamento_id:
        qs = qs.filter(setor__departamento_id=departamento_id)
    elif filial_id:
        qs = qs.filter(setor__departamento__filial_id=filial_id)
    elif empresa_id:
        qs = qs.filter(setor__departamento__filial__empresa_id=empresa_id)

    return JsonResponse(list(qs.values("id", "descricao")), safe=False)


@login_required
def ajax_recursos(request):
    centro_id = request.GET.get("centro_id")
    setor_id = request.GET.get("setor_id")
    departamento_id = request.GET.get("departamento_id")
    filial_id = request.GET.get("filial_id")
    empresa_id = request.GET.get("empresa_id")

    qs = Recurso.objects.all()

    # conversão segura e filtros cumulativos
    if centro_id:
        try:
            qs = qs.filter(centro_recurso_id=int(centro_id))
        except ValueError:
            pass
    if setor_id:
        qs = qs.filter(centro_recurso__setor_id=setor_id)
    if departamento_id:
        qs = qs.filter(centro_recurso__setor__departamento_id=departamento_id)
    if filial_id:
        qs = qs.filter(centro_recurso__setor__departamento__filial_id=filial_id)
    if empresa_id:
        qs = qs.filter(centro_recurso__setor__departamento__filial__empresa_id=empresa_id)

    return JsonResponse(list(qs.values("id", "descricao")), safe=False)
