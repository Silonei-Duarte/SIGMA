from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from SIGMA.autorizacao import permissao_requerida

from ..forms import TurnoRecursoForm
from ..models import Departamento, Empresa, Filial, Recurso, Setor, TurnoRecurso


@permissao_requerida("accounts.manipular_cadastros")
def lista_turnos(request):
    empresa_id = request.GET.get("empresa")
    filial_id = request.GET.get("filial")
    departamento_id = request.GET.get("departamento")

    setores = Setor.objects.exclude(id=1).order_by("descricao")
    if empresa_id:
        setores = setores.filter(departamento__filial__empresa_id=empresa_id)
    if filial_id:
        setores = setores.filter(departamento__filial_id=filial_id)
    if departamento_id:
        setores = setores.filter(departamento_id=departamento_id)

    setores = setores.prefetch_related(
        "centrorecurso_set__recursos__turnorecurso_set__turnobase"
    ).order_by("descricao")

    # Reordena manualmente os turnos antes de enviar ao template
    setores_filtrados = []
    for setor in setores:
        centros_filtrados = []
        for centro in setor.centrorecurso_set.all():
            recursos_validos = centro.recursos.filter(
                habilita_oee=True
            )  # Apenas recursos com OEE habilitado
            if not recursos_validos.exists():
                continue

            for recurso in recursos_validos:
                turnos = list(recurso.turnorecurso_set.all())
                turnos.sort(
                    key=lambda t: (
                        t.turnobase.descricao if t.turnobase else "",
                        min(t.dias) if t.dias else 99,
                        t.hora_inicio,
                    )
                )
                recurso.turnos_ordenados = turnos

            centro.recursos_filtrados = recursos_validos
            centros_filtrados.append(centro)

        # ignora setor sem recursos
        if centros_filtrados:
            setor.centros_filtrados = centros_filtrados
            setores_filtrados.append(setor)

    # substitui a lista de setores
    setores = setores_filtrados

    # Criação de turno
    if request.method == "POST":
        dias = request.POST.get("dias", "").strip()
        if not dias:
            messages.error(request, "Selecione ao menos um dia da semana.")
            return redirect("lista_turnos")

        # Monta hora início e fim a partir dos selects separados (agora com segundos)
        hora_inicio_h = request.POST.get("hora_inicio_h", "00")
        hora_inicio_m = request.POST.get("hora_inicio_m", "00")
        hora_inicio_s = request.POST.get("hora_inicio_s", "00")
        hora_fim_h = request.POST.get("hora_fim_h", "00")
        hora_fim_m = request.POST.get("hora_fim_m", "00")
        hora_fim_s = request.POST.get("hora_fim_s", "00")

        data = request.POST.copy()
        data["hora_inicio"] = f"{hora_inicio_h}:{hora_inicio_m}:{hora_inicio_s}"
        data["hora_fim"] = f"{hora_fim_h}:{hora_fim_m}:{hora_fim_s}"

        form = TurnoRecursoForm(data)
        if form.is_valid():
            turno = form.save(commit=False)
            turno.dias = [int(d) for d in dias.split(",") if d]
            recurso_id = request.POST.get("recurso")
            if recurso_id:
                turno.recurso_id = recurso_id
                turno.save()
                messages.success(request, "Turno cadastrado com sucesso.")
            else:
                messages.error(request, "Recurso não informado.")
        else:
            messages.error(request, f"Erro ao cadastrar turno: {form.errors}")
        return redirect("lista_turnos")

    else:
        form = TurnoRecursoForm()

    context = {
        "empresas": Empresa.objects.order_by("nome"),
        "filiais": Filial.objects.filter(empresa_id=empresa_id).order_by("nome")
        if empresa_id
        else [],
        "departamentos": Departamento.objects.filter(filial_id=filial_id).order_by("descricao")
        if filial_id
        else [],
        "setores": setores,
        "form": form,
        "empresa_sel": empresa_id,
        "filial_sel": filial_id,
        "departamento_sel": departamento_id,
    }

    return render(request, "accounts/turnos_recursos.html", context)


@require_POST
@permissao_requerida("accounts.manipular_cadastros")
def deletar_turno(request, pk):

    turno = get_object_or_404(TurnoRecurso, pk=pk)
    turno.delete()
    messages.success(request, "Turno excluído com sucesso.")
    return redirect("lista_turnos")


@permissao_requerida("accounts.manipular_cadastros")
def editar_turno(request, pk):
    turno = get_object_or_404(TurnoRecurso, pk=pk)
    if request.method == "POST":
        dias = request.POST.get("dias", "").strip()
        hora_inicio_h = request.POST.get("hora_inicio_h", "00")
        hora_inicio_m = request.POST.get("hora_inicio_m", "00")
        hora_inicio_s = request.POST.get("hora_inicio_s", "00")
        hora_fim_h = request.POST.get("hora_fim_h", "00")
        hora_fim_m = request.POST.get("hora_fim_m", "00")
        hora_fim_s = request.POST.get("hora_fim_s", "00")

        data = request.POST.copy()
        data["hora_inicio"] = f"{hora_inicio_h}:{hora_inicio_m}:{hora_inicio_s}"
        data["hora_fim"] = f"{hora_fim_h}:{hora_fim_m}:{hora_fim_s}"

        form = TurnoRecursoForm(data, instance=turno)
        if form.is_valid():
            turno = form.save(commit=False)
            turno.dias = [int(d) for d in dias.split(",") if d]
            turno.save()
            messages.success(request, "Turno atualizado com sucesso.")
        else:
            messages.error(request, "Erro ao atualizar turno.")
    return redirect("lista_turnos")


@permissao_requerida("accounts.manipular_cadastros")
def replicar_turnos(request, recurso_id):
    recurso = get_object_or_404(Recurso, id=recurso_id)
    setor = recurso.centro_recurso.setor
    turnos_origem = TurnoRecurso.objects.filter(recurso=recurso)

    if not turnos_origem.exists():
        messages.warning(request, "O recurso selecionado não possui turnos para replicar.")
    else:
        recursos_destino = (
            Recurso.objects.filter(centro_recurso__setor=setor, habilita_oee=True)
            .exclude(id=recurso.id)
            .exclude(centro_recurso__setor_id=1)
        )
        copiados = 0
        for r in recursos_destino:
            if TurnoRecurso.objects.filter(recurso=r).exists():
                continue
            for t in turnos_origem:
                TurnoRecurso.objects.create(
                    turnobase=t.turnobase,
                    recurso=r,
                    dias=t.dias,
                    hora_inicio=t.hora_inicio,
                    hora_fim=t.hora_fim,
                )
                copiados += 1
        if copiados:
            recursos_afetados = (
                Recurso.objects.filter(centro_recurso__setor=setor)
                .exclude(id=recurso.id)
                .filter(turnorecurso__isnull=False)
                .distinct()
                .count()
            )

            messages.success(
                request, f"{copiados} turno(s) replicado(s) para {recursos_afetados} recurso(s)."
            )
        else:
            messages.info(request, "Nenhum recurso elegível para replicação.")

    return redirect("lista_turnos")
