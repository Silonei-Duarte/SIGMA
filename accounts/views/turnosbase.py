from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.forms import TurnoBaseForm
from accounts.models import TurnoBase
from SIGMA.autorizacao import permissao_requerida


@permissao_requerida("accounts.manipular_cadastros")
def turnos_base(request):

    if request.method == "POST":
        form = TurnoBaseForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Turno cadastrado com sucesso!")
            return redirect("turnos_base")
    else:
        form = TurnoBaseForm()

    turnos = TurnoBase.objects.all().order_by("ordenacao", "id")
    paginator = Paginator(turnos, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "accounts/turnos_base.html", {"form": form, "page_obj": page_obj})


@permissao_requerida("accounts.manipular_cadastros")
def editar_turno_base(request, pk):

    turno = get_object_or_404(TurnoBase, pk=pk)
    if request.method == "POST":
        form = TurnoBaseForm(request.POST, instance=turno)
        if form.is_valid():
            form.save()
            messages.success(request, "Turno atualizado com sucesso!")
            return redirect("turnos_base")
    else:
        form = TurnoBaseForm(instance=turno)

    turnos = TurnoBase.objects.select_related("calendario").order_by("ordenacao", "id")
    paginator = Paginator(turnos, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "accounts/turnos_base.html",
        {"form": form, "page_obj": page_obj, "editing": True, "turno_editando": turno},
    )


@require_POST
@permissao_requerida("accounts.manipular_cadastros")
def deletar_turno_base(request, pk):

    turno = get_object_or_404(TurnoBase, pk=pk)
    try:
        turno.delete()
        messages.success(request, "Turno excluído com sucesso!")
    except ProtectedError:
        messages.warning(
            request,
            "Não é possível excluir este turno base, pois está vinculado a registros de turno ou horas extras.",
        )
    return redirect("turnos_base")
