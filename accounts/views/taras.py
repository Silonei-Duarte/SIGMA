from django.contrib import messages
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from SIGMA.autorizacao import permissao_requerida

from ..forms import TaraForm
from ..models import Tara


@permissao_requerida("accounts.manipular_cadastros")
def lista_taras(request):

    taras = Tara.objects.all().order_by("tara")
    tara_editando = None
    form = TaraForm()

    if request.method == "POST":
        if "salvar" in request.POST:
            form = TaraForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Tara cadastrada com sucesso.")
                return redirect("lista_taras")

        elif "atualizar" in request.POST:
            tara_id = request.POST.get("tara_id")
            tara = get_object_or_404(Tara, pk=tara_id)
            form = TaraForm(request.POST, instance=tara)
            if form.is_valid():
                form.save()
                messages.success(request, "Tara atualizada com sucesso.")
                return redirect("lista_taras")

    elif "editar" in request.GET:
        tara_id = request.GET.get("editar")
        if tara_id != "novo":
            tara_editando = get_object_or_404(Tara, pk=tara_id)
            form = TaraForm(instance=tara_editando)
        else:
            form = TaraForm()

    context = {
        "taras": taras,
        "form": form,
        "tara_editando": tara_editando,
        "editar_param": request.GET.get("editar"),
    }
    return render(request, "accounts/taras.html", context)


@require_POST
@permissao_requerida("accounts.manipular_cadastros")
def deletar_tara(request, pk):

    tara = get_object_or_404(Tara, pk=pk)
    try:
        tara.delete()
        messages.success(request, "Tara excluída com sucesso.")
    except ProtectedError:
        messages.warning(
            request, "Não é possível excluir esta tara pois existem recursos vinculados a ela."
        )

    return redirect("lista_taras")
