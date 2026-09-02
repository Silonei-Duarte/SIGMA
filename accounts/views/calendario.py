import json

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from accounts.forms import CalendarioEventoForm, CalendarioForm
from accounts.models import Calendario, CalendarioEvento
from SIGMA.autorizacao import permissao_requerida


# --------- Calendário ---------
@permissao_requerida("accounts.manipular_cadastros")
def calendarios(request):
    if request.method == "POST":
        form = CalendarioForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Calendário cadastrado com sucesso!")
            return redirect("calendarios")
    else:
        form = CalendarioForm()

    calendarios_qs = Calendario.objects.select_related("filial", "filial__empresa").order_by(
        "filial__empresa__nome", "filial__nome", "descricao"
    )
    paginator = Paginator(calendarios_qs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "accounts/calendarios.html",
        {"form": form, "page_obj": page_obj, "modo_eventos": False},
    )


@permissao_requerida("accounts.manipular_cadastros")
def editar_calendario(request, pk):
    calendario = get_object_or_404(Calendario, pk=pk)
    if request.method == "POST":
        form = CalendarioForm(request.POST, instance=calendario)
        if form.is_valid():
            form.save()
            messages.success(request, "Calendário atualizado com sucesso!")
            return redirect("calendarios")
    else:
        form = CalendarioForm(instance=calendario)

    calendarios_qs = Calendario.objects.all().order_by("descricao")
    paginator = Paginator(calendarios_qs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "accounts/calendarios.html",
        {
            "form": form,
            "page_obj": page_obj,
            "editing": True,  # 🔹 habilita modo edição
            "calendario_editando": calendario,  # 🔹 passa objeto editando
            "modo_eventos": False,
        },
    )


@require_POST
@permissao_requerida("accounts.manipular_cadastros")
def deletar_calendario(request, pk):

    calendario = get_object_or_404(Calendario, pk=pk)

    if calendario.eventos.exists():
        messages.warning(
            request, "Não é possível excluir um calendário que possui eventos cadastrados."
        )
        return redirect("calendarios")

    try:
        calendario.delete()
        messages.success(request, "Calendário excluído com sucesso!")
    except ProtectedError:
        messages.warning(
            request, "Não é possível excluir este calendário, pois está vinculado a um turno base."
        )
    return redirect("calendarios")


# --------- Eventos de Calendário ---------
@permissao_requerida("accounts.manipular_cadastros")
def eventos_calendario(request, calendario_id):

    calendario = get_object_or_404(Calendario, pk=calendario_id)

    if request.method == "POST":
        form = CalendarioEventoForm(request.POST)
        if form.is_valid():
            evento = form.save(commit=False)
            evento.calendario = calendario
            evento.save()
            messages.success(request, "Evento cadastrado com sucesso!")
            return redirect("eventos_calendario", calendario_id=calendario.id)
    else:
        form = CalendarioEventoForm()

    # pega ano da URL (?ano=2026), se não vier usa ano atual
    from datetime import date

    ano = request.GET.get("ano")
    if ano is None:
        ano = date.today().year

    eventos_qs = calendario.eventos.filter(data__year=ano).order_by("data")

    return render(
        request,
        "accounts/calendarios.html",
        {
            "form": form,
            "eventos_ano": eventos_qs,
            "calendario": calendario,
            "ano": ano,
            "modo_eventos": True,
        },
    )


@permissao_requerida("accounts.manipular_cadastros")
def editar_evento(request, pk):

    evento = get_object_or_404(CalendarioEvento, pk=pk)

    if request.method == "POST":
        form = CalendarioEventoForm(request.POST, instance=evento)
        if form.is_valid():
            form.save()
            messages.success(request, "Evento atualizado com sucesso!")
            return redirect("eventos_calendario", calendario_id=evento.calendario.id)
    else:
        form = CalendarioEventoForm(instance=evento)

    eventos_qs = evento.calendario.eventos.all().order_by("data")
    paginator = Paginator(eventos_qs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "accounts/calendarios.html",
        {
            "form": form,
            "page_obj": page_obj,
            "calendario": evento.calendario,
            "editing": True,
            "evento_editando": evento,
            "modo_eventos": True,
        },
    )


@require_POST
@permissao_requerida("accounts.manipular_cadastros")
def deletar_evento(request, pk):

    evento = get_object_or_404(CalendarioEvento, pk=pk)
    evento.delete()

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"status": "ok"})
    else:
        messages.success(request, "Evento excluído com sucesso!")
        return redirect("eventos_calendario", calendario_id=evento.calendario.id)


@permissao_requerida("accounts.manipular_cadastros")
def api_eventos(request, calendario_id):

    calendario = get_object_or_404(Calendario, pk=calendario_id)

    start = request.GET.get("start")
    end = request.GET.get("end")

    # se não vier range, retorna vazio
    if not start or not end:
        return JsonResponse([], safe=False)

    # converte 2025-10-26T00:00:00-03:00 → 2025-10-26
    from datetime import datetime

    start = datetime.strptime(start.split("T")[0], "%Y-%m-%d").date()
    end = datetime.strptime(end.split("T")[0], "%Y-%m-%d").date()

    qs = calendario.eventos.filter(data__gte=start, data__lte=end)

    cor_fundo_map = {
        1: "var(--color-erro-sutil)",
        2: "var(--color-atencao-sutil)",
        3: "var(--color-informacao-sutil)",
    }
    cor_conteudo_map = {
        1: "var(--color-erro-base)",
        2: "var(--color-atencao-base)",
        3: "var(--color-informacao-base)",
    }

    data = [
        {
            "id": e.id,
            "title": e.get_motivo_display()
            if not e.observacao
            else f"{e.get_motivo_display()} - {e.observacao}",
            "start": e.data.strftime("%Y-%m-%d"),
            "backgroundColor": cor_fundo_map.get(e.motivo, "var(--color-informacao-sutil)"),
            "borderColor": cor_conteudo_map.get(e.motivo, "var(--color-informacao-base)"),
            "textColor": cor_conteudo_map.get(e.motivo, "var(--color-informacao-base)"),
        }
        for e in qs
    ]

    return JsonResponse(data, safe=False)


@require_POST
@permissao_requerida("accounts.manipular_cadastros")
def api_evento_update(request):

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    evento = get_object_or_404(CalendarioEvento, pk=payload.get("id"))

    # A data chega como string ISO (YYYY-MM-DD) do drag-and-drop do FullCalendar;
    # parse_date valida o formato em vez de deixar o model estourar na gravação.
    data_evento = parse_date(str(payload.get("data") or ""))
    if data_evento is None:
        return JsonResponse({"erro": "Data inválida."}, status=400)

    evento.data = data_evento
    evento.save()
    return JsonResponse({"status": "ok"})


@require_POST
@permissao_requerida("accounts.manipular_cadastros")
def api_evento_create(request):

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    calendario = get_object_or_404(Calendario, pk=payload.get("calendario_id"))

    data_evento = parse_date(str(payload.get("data") or ""))
    if data_evento is None:
        return JsonResponse({"erro": "Data inválida."}, status=400)

    # Reaproveita o form já usado em eventos_calendario/editar_evento para validar
    # o motivo (choices do model) em vez de atribuir payload.get("motivo") cru.
    form = CalendarioEventoForm({"motivo": payload.get("motivo")})
    if not form.is_valid():
        return JsonResponse({"erro": "Motivo inválido.", "detalhes": form.errors}, status=400)

    evento = form.save(commit=False)
    evento.calendario = calendario
    evento.data = data_evento
    evento.save()
    return JsonResponse({"status": "ok", "id": evento.id})
