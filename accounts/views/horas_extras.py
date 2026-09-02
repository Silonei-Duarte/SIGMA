from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from SIGMA.autorizacao import permissao_requerida

from ..forms import HoraExtraPlanejadaForm
from ..models import (
    CentroRecurso,
    Departamento,
    Empresa,
    Filial,
    HoraExtraPlanejada,
    Recurso,
    Setor,
    TurnoBase,
)


@permissao_requerida("accounts.manipular_cadastros")
def lista_horas_extras(request):

    # ============================
    # CADASTRO (POST)
    # ============================
    if request.method == "POST":
        dias = request.POST.get("dias", "").strip()
        turnos_ids = request.POST.getlist("id_turnobase")
        recursos_ids = request.POST.getlist("recurso")

        if not dias or not turnos_ids or not recursos_ids:
            messages.error(request, "Selecione ao menos um dia, um turno e um recurso.")
            return redirect("lista_horas_extras")

        data = request.POST.copy()
        data["hora_inicio"] = (
            f"{data.get('hora_inicio_h', '00')}:{data.get('hora_inicio_m', '00')}:{data.get('hora_inicio_s', '00')}"
        )
        data["hora_fim"] = (
            f"{data.get('hora_fim_h', '00')}:{data.get('hora_fim_m', '00')}:{data.get('hora_fim_s', '00')}"
        )

        if data["data_fim"] < data["data_inicio"]:
            messages.error(request, "Data fim não pode ser menor que a data início.")
            return redirect("lista_horas_extras")

        criados = 0
        for t in turnos_ids:
            for r in recursos_ids:
                HoraExtraPlanejada.objects.create(
                    turnobase_id=t,
                    recurso_id=r,
                    dias=[int(d) for d in dias.split(",") if d],
                    data_inicio=data["data_inicio"],
                    data_fim=data["data_fim"],
                    hora_inicio=data["hora_inicio"],
                    hora_fim=data["hora_fim"],
                    considera_feriado="considera_feriado" in data,
                )
                criados += 1

        messages.success(request, f"{criados} hora(s) extra(s) criada(s) com sucesso.")
        return redirect("lista_horas_extras")

    # ============================
    # FILTROS GET
    # ============================
    horas_extras = HoraExtraPlanejada.objects.all()

    empresa_id = request.GET.get("empresa", "")
    filial_id = request.GET.get("filial", "")
    departamento_id = request.GET.get("departamento", "")
    setor_id = request.GET.get("setor", "")
    centro_id = request.GET.get("centro", "")
    recurso_id = request.GET.get("recurso", "")

    # resets corretos
    if departamento_id == "":
        setor_id = ""
        centro_id = ""
        recurso_id = ""

    if setor_id == "":
        centro_id = ""
        recurso_id = ""

    if centro_id == "":
        recurso_id = ""

    if empresa_id:
        horas_extras = horas_extras.filter(
            recurso__centro_recurso__setor__departamento__filial__empresa_id=empresa_id
        )

    if filial_id:
        horas_extras = horas_extras.filter(
            recurso__centro_recurso__setor__departamento__filial_id=filial_id
        )

    if departamento_id:
        horas_extras = horas_extras.filter(
            recurso__centro_recurso__setor__departamento_id=departamento_id
        )

    if setor_id:
        horas_extras = horas_extras.filter(recurso__centro_recurso__setor_id=setor_id)

    if centro_id:
        horas_extras = horas_extras.filter(recurso__centro_recurso_id=centro_id)

    if recurso_id:
        horas_extras = horas_extras.filter(recurso_id=recurso_id)

    horas_extras = horas_extras.order_by("-data_inicio")

    # ============================
    # FILTRAR RECURSOS (dropdown)
    # ============================
    recursos_filtrados = Recurso.objects.all()

    if empresa_id:
        recursos_filtrados = recursos_filtrados.filter(
            centro_recurso__setor__departamento__filial__empresa_id=empresa_id
        )

    if filial_id:
        recursos_filtrados = recursos_filtrados.filter(
            centro_recurso__setor__departamento__filial_id=filial_id
        )

    if departamento_id:
        recursos_filtrados = recursos_filtrados.filter(
            centro_recurso__setor__departamento_id=departamento_id
        )

    if setor_id:
        recursos_filtrados = recursos_filtrados.filter(centro_recurso__setor_id=setor_id)

    if centro_id:
        recursos_filtrados = recursos_filtrados.filter(centro_recurso_id=centro_id)

    recursos_filtrados = recursos_filtrados.order_by("descricao")

    # ============================
    # CONTEXT
    # ============================
    context = {
        "form": HoraExtraPlanejadaForm(),
        "horas_extras": horas_extras,
        "empresas": Empresa.objects.all().order_by("nome"),
        "filiais": Filial.objects.all().order_by("nome"),
        "departamentos": Departamento.objects.all().order_by("descricao"),
        "empresa_sel": empresa_id or "",
        "filial_sel": filial_id or "",
        "departamento_sel": departamento_id or "",
        "setor_sel": setor_id or "",
        "centro_sel": centro_id or "",
        "recurso_sel": recurso_id or "",
        "setores": (
            Setor.objects.filter(departamento_id=departamento_id).order_by("descricao")
            if departamento_id
            else (
                Setor.objects.filter(departamento__filial_id=filial_id).order_by("descricao")
                if filial_id
                else Setor.objects.none()
            )
        ),
        "centros": (
            CentroRecurso.objects.filter(setor_id=setor_id).order_by("descricao")
            if setor_id
            else (
                CentroRecurso.objects.filter(setor__departamento_id=departamento_id).order_by(
                    "descricao"
                )
                if departamento_id
                else CentroRecurso.objects.none()
            )
        ),
        "recursos": recursos_filtrados,  # ← VOLTA PRA CÁ
    }

    return render(request, "accounts/horas_extras_planejadas.html", context)


@permissao_requerida("accounts.manipular_cadastros")
def editar_hora_extra(request, pk):

    he = get_object_or_404(HoraExtraPlanejada, pk=pk)

    # ================================================
    # PEGAR FILTROS DA URL
    # ================================================
    empresa_id = request.GET.get("empresa", "")
    filial_id = request.GET.get("filial", "")
    departamento_id = request.GET.get("departamento", "")
    setor_id = request.GET.get("setor", "")
    centro_id = request.GET.get("centro", "")
    recurso_id = request.GET.get("recurso", "")

    # === resets iguais da listagem ===

    if departamento_id == "":
        setor_id = ""
        centro_id = ""
        recurso_id = ""

    if setor_id == "":
        centro_id = ""
        recurso_id = ""

    if centro_id == "":
        recurso_id = ""

    # ================================================
    # FORM DE EDIÇÃO
    # ================================================
    class EditForm(forms.ModelForm):
        id_turnobase = forms.ModelChoiceField(
            queryset=TurnoBase.objects.all().order_by("descricao"),
            label="Turno Base",
            widget=forms.Select(),
        )

        recurso = forms.ModelChoiceField(
            queryset=Recurso.objects.all().order_by("descricao"),
            label="Recurso",
            widget=forms.Select(),
        )

        hora_inicio_h = forms.ChoiceField(choices=[(f"{h:02d}", f"{h:02d}") for h in range(24)])
        hora_inicio_m = forms.ChoiceField(choices=[(f"{m:02d}", f"{m:02d}") for m in range(60)])
        hora_inicio_s = forms.ChoiceField(choices=[(f"{s:02d}", f"{s:02d}") for s in range(60)])

        hora_fim_h = forms.ChoiceField(choices=[(f"{h:02d}", f"{h:02d}") for h in range(24)])
        hora_fim_m = forms.ChoiceField(choices=[(f"{m:02d}", f"{m:02d}") for m in range(60)])
        hora_fim_s = forms.ChoiceField(choices=[(f"{s:02d}", f"{s:02d}") for s in range(60)])

        class Meta:
            model = HoraExtraPlanejada
            fields = [
                "id_turnobase",
                "recurso",
                "dias",
                "data_inicio",
                "data_fim",
                "hora_inicio",
                "hora_fim",
                "considera_feriado",
            ]

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            # aplicar estilo
            self.fields["id_turnobase"].widget.attrs.update(
                {"class": "border border-black rounded p-1 w-full bg-white"}
            )

            self.fields["recurso"].widget.attrs.update(
                {"class": "border border-black rounded p-1 w-full bg-white"}
            )

    # ================================================
    # POST (SALVAR)
    # ================================================
    if request.method == "POST":
        data = request.POST.copy()

        data["hora_inicio"] = (
            f"{data.get('hora_inicio_h')}:{data.get('hora_inicio_m')}:{data.get('hora_inicio_s')}"
        )
        data["hora_fim"] = (
            f"{data.get('hora_fim_h')}:{data.get('hora_fim_m')}:{data.get('hora_fim_s')}"
        )

        form = EditForm(data, instance=he)

        if form.is_valid():
            di = data.get("data_inicio")
            df = data.get("data_fim")

            if df < di:
                messages.error(request, "Data fim não pode ser menor que a data início.")
                return redirect("editar_hora_extra", pk=pk)

            form.save()
            messages.success(request, "Hora extra atualizada com sucesso.")

            # voltar para a listagem com filtros preservados
            return redirect(
                f"/accounts/horas-extras/?empresa={empresa_id}&filial={filial_id}"
                f"&departamento={departamento_id}&setor={setor_id}"
                f"&centro={centro_id}&recurso={recurso_id}"
            )

        messages.error(request, "Erro ao atualizar.")

    else:
        form = EditForm(instance=he)
        form.initial["id_turnobase"] = he.turnobase.id
        form.initial["recurso"] = he.recurso.id
        form.initial["hora_inicio_h"] = f"{he.hora_inicio.hour:02d}"
        form.initial["hora_inicio_m"] = f"{he.hora_inicio.minute:02d}"
        form.initial["hora_inicio_s"] = f"{he.hora_inicio.second:02d}"
        form.initial["hora_fim_h"] = f"{he.hora_fim.hour:02d}"
        form.initial["hora_fim_m"] = f"{he.hora_fim.minute:02d}"
        form.initial["hora_fim_s"] = f"{he.hora_fim.second:02d}"

    # ================================================
    # LISTAGEM FILTRADA (igual view principal)
    # ================================================
    lista_filtrada = HoraExtraPlanejada.objects.all()

    if empresa_id:
        lista_filtrada = lista_filtrada.filter(
            recurso__centro_recurso__setor__departamento__filial__empresa_id=empresa_id
        )

    if filial_id:
        lista_filtrada = lista_filtrada.filter(
            recurso__centro_recurso__setor__departamento__filial_id=filial_id
        )

    if departamento_id:
        lista_filtrada = lista_filtrada.filter(
            recurso__centro_recurso__setor__departamento_id=departamento_id
        )

    if setor_id:
        lista_filtrada = lista_filtrada.filter(recurso__centro_recurso__setor_id=setor_id)

    if centro_id:
        lista_filtrada = lista_filtrada.filter(recurso__centro_recurso_id=centro_id)

    if recurso_id:
        lista_filtrada = lista_filtrada.filter(recurso_id=recurso_id)

    lista_filtrada = lista_filtrada.order_by("-data_inicio")

    # ================================================
    # FILTRAR SETORES, CENTROS E RECURSOS (dropdowns)
    # ================================================
    setores = (
        Setor.objects.filter(departamento_id=departamento_id).order_by("descricao")
        if departamento_id
        else Setor.objects.none()
    )

    centros = (
        CentroRecurso.objects.filter(setor_id=setor_id).order_by("descricao")
        if setor_id
        else CentroRecurso.objects.none()
    )

    recursos_filtrados = Recurso.objects.all()

    if empresa_id:
        recursos_filtrados = recursos_filtrados.filter(
            centro_recurso__setor__departamento__filial__empresa_id=empresa_id
        )
    if filial_id:
        recursos_filtrados = recursos_filtrados.filter(
            centro_recurso__setor__departamento__filial_id=filial_id
        )
    if departamento_id:
        recursos_filtrados = recursos_filtrados.filter(
            centro_recurso__setor__departamento_id=departamento_id
        )
    if setor_id:
        recursos_filtrados = recursos_filtrados.filter(centro_recurso__setor_id=setor_id)
    if centro_id:
        recursos_filtrados = recursos_filtrados.filter(centro_recurso_id=centro_id)

    recursos_filtrados = recursos_filtrados.order_by("descricao")

    # ================================================
    # CONTEXT FINAL
    # ================================================
    context = {
        "form": form,
        "editar_obj": he,
        "horas_extras": lista_filtrada,
        "empresas": Empresa.objects.all().order_by("nome"),
        "filiais": Filial.objects.all().order_by("nome"),
        "departamentos": Departamento.objects.all().order_by("descricao"),
        "setores": setores,
        "centros": centros,
        "recursos": recursos_filtrados,
        "empresa_sel": empresa_id,
        "filial_sel": filial_id,
        "departamento_sel": departamento_id,
        "setor_sel": setor_id,
        "centro_sel": centro_id,
        "recurso_sel": recurso_id,
    }

    return render(request, "accounts/horas_extras_planejadas.html", context)


@require_POST
@permissao_requerida("accounts.manipular_cadastros")
def deletar_hora_extra(request, pk):

    he = get_object_or_404(HoraExtraPlanejada, pk=pk)
    he.delete()
    messages.success(request, "Hora extra planejada excluída com sucesso.")

    params = request.GET.urlencode()
    return redirect(f"/horas_extras/?{params}")
