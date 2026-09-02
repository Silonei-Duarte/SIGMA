import logging
from datetime import timedelta
from io import BytesIO

import qrcode
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import OuterRef, Q, Subquery
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from accounts.models import CentroRecurso, CustomUser, Recurso
from setores.manutencao.forms import (
    GRUPO_OBSERVADORES,
    GRUPO_RESPONSAVEIS,
    ChamadoForm,
    InteracaoChamadoForm,
)
from setores.manutencao.models import Chamado, Interacao_Chamado
from SIGMA.autorizacao import permissao_requerida

logger = logging.getLogger(__name__)


def _recursos_visiveis(usuario):
    if usuario.is_staff:
        return Recurso.objects.all()
    filial = getattr(usuario, "filial", None)
    if not filial:
        return Recurso.objects.none()
    return Recurso.objects.filter(centro_recurso__setor__departamento__filial=filial)


def _chamados_visiveis(usuario):
    if usuario.is_staff:
        return Chamado.objects.all()
    chamados_da_filial = Chamado.objects.filter(recurso__in=_recursos_visiveis(usuario))
    if usuario.has_perm("manutencao.pode_listar_todos_chamados"):
        return chamados_da_filial
    primeiro_usuario = Subquery(
        Interacao_Chamado.objects.filter(chamado=OuterRef("pk"))
        .order_by("data")
        .values("usuario")[:1]
    )
    return (
        chamados_da_filial.annotate(primeiro_usuario=primeiro_usuario)
        .filter(
            Q(primeiro_usuario=usuario.id)
            | Q(responsaveis__contains=[usuario.id])
            | Q(observadores_id__contains=[usuario.id])
        )
        .distinct()
    )


def _pode_ver_chamado(usuario, chamado):
    return _chamados_visiveis(usuario).filter(pk=chamado.pk).exists()


def _emails_validos(qs):
    return list(
        qs.exclude(email__isnull=True)
        .exclude(email__exact="")
        .values_list("email", flat=True)
        .distinct()
    )


def enviar_email(assunto, corpo, destinatarios):
    if not destinatarios:
        return
    try:
        send_mail(assunto, corpo, settings.DEFAULT_FROM_EMAIL, destinatarios, fail_silently=False)
    except Exception:
        logger.exception("Falha ao enviar e-mail de chamado")


@permissao_requerida("manutencao.pode_acessar_chamados")
def qrcode_recurso_pdf(request, pk=None):
    # 1) Se PK → 1 recurso
    if pk:
        recursos = [get_object_or_404(_recursos_visiveis(request.user), pk=pk)]

    # 2) Se não tem PK → precisa vir centro
    else:
        centro_id = request.GET.get("centro")
        if not centro_id:
            return HttpResponse("Centro não informado.", status=400)

        recursos = (
            _recursos_visiveis(request.user)
            .filter(ativo=True, centro_recurso_id=centro_id)
            .order_by("descricao")
        )

    # ----- PDF -----

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    page_w, page_h = A4

    qr_w = 125
    qr_h = 125
    margem_topo = 72
    espacamento = 160
    y = page_h - margem_topo - qr_h

    for recurso in recursos:
        url = f"{settings.PORTAL_BASE_URL}/setores/manutencao/chamados/novo/?recurso={recurso.id}"

        qr_buf = BytesIO()
        qrcode.make(url).save(qr_buf, format="PNG")
        qr_buf.seek(0)
        img = ImageReader(qr_buf)

        x = (page_w - qr_w) / 2
        p.drawImage(img, x, y, width=qr_w, height=qr_h)

        p.setFont("Helvetica", 9)
        p.drawCentredString(page_w / 2, y, recurso.descricao)

        y -= espacamento
        if y < 100:
            p.showPage()
            y = page_h - margem_topo - qr_h

    p.save()
    buffer.seek(0)

    # resposta CLEAN
    resp = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = "inline; filename=qrcode.pdf"
    resp["X-Content-Type-Options"] = "nosniff"

    return resp


@permissao_requerida("manutencao.pode_acessar_chamados")
def listar_chamados(request):
    if request.GET.get("novo"):
        return redirect("abrir_chamado")

    chamado_excluir = None
    if request.method == "POST" and "confirmar_exclusao" in request.POST:
        if not (
            request.user.has_perm("manutencao.pode_manipular_chamados") or request.user.is_staff
        ):
            return HttpResponse("Você não tem permissão para excluir chamados.", status=403)
        pk = request.POST.get("confirmar_exclusao")
        chamado = get_object_or_404(_chamados_visiveis(request.user), pk=pk)
        chamado.delete()
        messages.warning(request, f"Chamado {pk} excluído com sucesso.")
        return redirect("listar_chamados")

    if request.method == "GET" and "excluir" in request.GET:
        # A confirmação de exclusão é ação sensível: quem acessa mas não
        # manipula não chega a vê-la — mesmo deny de excluir_chamado
        # (mensagem + volta à listagem). Sem a checagem, o GET renderizava a
        # confirmação para usuário que o POST inline negaria em seguida.
        if not (
            request.user.has_perm("manutencao.pode_manipular_chamados") or request.user.is_staff
        ):
            messages.warning(request, "Você não tem permissão para excluir chamados.")
            return redirect("listar_chamados")
        chamado_excluir = get_object_or_404(
            _chamados_visiveis(request.user), pk=request.GET["excluir"]
        )

    u = request.user

    chamados = _chamados_visiveis(u).select_related("recurso").order_by("-id")

    # --- filtros ---
    categoria = request.GET.get("categoria")
    status = request.GET.get("status")
    recurso = request.GET.get("recurso")

    if categoria:
        chamados = chamados.filter(categoria=categoria)
    if status:
        chamados = chamados.filter(status=status)
    if recurso:
        chamados = chamados.filter(recurso_id=recurso)

    # --- paginação ---
    paginator = Paginator(chamados, 20)
    page_number = request.GET.get("page")
    chamados = paginator.get_page(page_number)

    recursos = _recursos_visiveis(u).order_by("descricao")
    centros = CentroRecurso.objects.filter(recursos__in=recursos).distinct().order_by("descricao")
    return render(
        request,
        "setores/manutencao/chamados.html",
        {
            "modo": "lista",
            "chamados": chamados,
            "chamado_excluir": chamado_excluir,
            "categorias": Chamado.Categoria.choices,
            "status_list": Chamado.Status.choices,
            "recursos": recursos,
            "categoria_sel": categoria,
            "status_sel": status,
            "recurso_sel": recurso,
            "centros": centros,
        },
    )


@permissao_requerida("manutencao.pode_acessar_chamados")
def abrir_chamado(request):
    class ChamadoSimplesForm(ChamadoForm):
        def __init__(self, *args, recurso_queryset=None, centro_queryset=None, **kwargs):
            super().__init__(*args, **kwargs)
            if recurso_queryset is not None:
                self.fields["recurso"].queryset = recurso_queryset
            if centro_queryset is not None:
                self.fields["centro_recurso"].queryset = centro_queryset

        descricao = forms.CharField(
            label="Descrição",
            required=False,
            widget=forms.Textarea(
                attrs={
                    "class": "form-control form-control-sm",
                    "rows": 3,
                    "placeholder": "Descreva o problema ou situação...",
                }
            ),
        )

        centro_recurso = forms.ModelChoiceField(
            queryset=CentroRecurso.objects.none(),
            required=False,
            widget=forms.Select(
                attrs={
                    "id": "id_centro_recurso",
                    "name": "centro_recurso",
                    "class": "form-select form-select-sm",
                }
            ),
            label="Centro de Recurso",
        )

        recurso = forms.ModelChoiceField(
            queryset=Recurso.objects.none(),
            required=False,
            widget=forms.Select(
                attrs={"id": "id_recurso", "name": "recurso", "class": "form-select form-select-sm"}
            ),
        )

        class Meta(ChamadoForm.Meta):
            fields = ["nome", "categoria", "prioridade", "centro_recurso", "recurso"]

        centro_recurso.label_from_instance = lambda obj: (
            f"{obj.setor.departamento.filial.empresa.codemp}."
            f"{obj.setor.departamento.filial.codfil} - "
            f"{obj.setor.descricao}"
        )

    # --- carrega recurso se veio via QR ---
    recursos_visiveis = _recursos_visiveis(request.user)
    recurso_id = request.GET.get("recurso")
    initial = {}
    if recurso_id:
        recurso = recursos_visiveis.filter(pk=recurso_id).first()
        if recurso:
            initial["recurso"] = recurso
            initial["centro_recurso"] = recurso.centro_recurso

    # --- se não veio recurso via GET, usa o recurso com nome 'Geral' ---
    if not recurso_id:
        recurso_geral = recursos_visiveis.filter(id=1).first()
        if recurso_geral:
            initial["recurso"] = recurso_geral
            initial["centro_recurso"] = recurso_geral.centro_recurso

    if request.method == "POST":
        centro_id = request.POST.get("centro_recurso")

        # cria o form JÁ com o queryset correto
        if centro_id:
            qs_recursos = recursos_visiveis.filter(centro_recurso_id=centro_id, ativo=True)
        else:
            qs_recursos = recursos_visiveis.order_by("descricao")

        # injeta o queryset ANTES da validação
        form = ChamadoSimplesForm(
            request.POST,
            recurso_queryset=qs_recursos,
            centro_queryset=CentroRecurso.objects.filter(recursos__in=recursos_visiveis).distinct(),
        )

        if form.is_valid():
            chamado = form.save(commit=False)

            if not chamado.recurso_id:
                messages.warning(request, "Selecione um recurso antes de salvar.")
                return render(
                    request, "setores/manutencao/chamados.html", {"modo": "form", "form": form}
                )

            chamado.save()

            mensagem_inicial = form.cleaned_data.get("descricao") or "Chamado aberto."
            Interacao_Chamado.objects.create(
                chamado=chamado,
                usuario=request.user,
                mensagem=mensagem_inicial,
            )

            messages.success(request, "Chamado criado com sucesso.")

            # ===== EMAIL — NOVO CHAMADO =====
            criador = request.user
            destinatarios = []

            # criador
            if criador.email:
                destinatarios.append(criador.email)

            # quem tem permissão de listar todos
            users_listar = CustomUser.objects.filter(
                is_active=True, user_permissions__codename="pode_listar_todos_chamados"
            ) | CustomUser.objects.filter(
                is_active=True, groups__permissions__codename="pode_listar_todos_chamados"
            )

            destinatarios += _emails_validos(users_listar)

            assunto = f"CHAMADO MANUTENÇÃO {chamado.id} — {chamado.nome} Criado"
            corpo = (
                f"Novo chamado criado.\n\n"
                f"ID: {chamado.id}\n"
                f"Nome: {chamado.nome}\n"
                f"Categoria: {chamado.get_categoria_display()}\n"
                f"Prioridade: {chamado.get_prioridade_display()}\n"
                f"Recurso: {chamado.recurso.descricao}\n"
                f"Criado por: {criador.get_full_name() or criador.username}\n\n"
                f"Acesse o portal para verificar mais informações:\n"
                f"{settings.PORTAL_BASE_URL}/setores/manutencao/{chamado.id}/\n"
            )

            enviar_email(assunto, corpo, destinatarios)

            return redirect("detalhar_chamado", pk=chamado.id)
        else:
            messages.warning(request, "Verifique os campos antes de salvar.")
    else:
        form = ChamadoSimplesForm(
            initial=initial,
            recurso_queryset=recursos_visiveis,
            centro_queryset=CentroRecurso.objects.filter(recursos__in=recursos_visiveis).distinct(),
        )

    # Ajustar recursos SEMPRE que existir centro selecionado (initial OU POST)
    centro_id = form.data.get("centro_recurso") or (
        initial.get("centro_recurso").id if initial.get("centro_recurso") else None
    )
    if centro_id:
        form.fields["recurso"].queryset = recursos_visiveis.filter(
            centro_recurso_id=centro_id, ativo=True
        )
    form.fields["centro_recurso"].queryset = (
        CentroRecurso.objects.filter(recursos__in=recursos_visiveis)
        .distinct()
        .order_by("descricao")
    )

    return render(
        request,
        "setores/manutencao/chamados.html",
        {"modo": "form", "form": form, "titulo": "Novo Chamado"},
    )


@permissao_requerida("manutencao.pode_acessar_chamados")
def ajax_recursos_por_centro(request):
    centro_id = request.GET.get("centro_id")
    qs = Recurso.objects.none()
    if centro_id:
        qs = _recursos_visiveis(request.user).filter(centro_recurso_id=centro_id, ativo=True)
    return JsonResponse(list(qs.values("id", "descricao")), safe=False)


@permissao_requerida("manutencao.pode_acessar_chamados")
def detalhar_chamado(request, pk):
    chamado = get_object_or_404(_chamados_visiveis(request.user), pk=pk)
    # --- BLOQUEIO DE ACESSO DIRETO ---
    u = request.user
    pode_ver = False
    # staff ou permissão global
    if u.is_staff or u.has_perm("manutencao.pode_listar_todos_chamados"):
        pode_ver = True
    # responsável
    elif chamado.responsaveis and u.id in chamado.responsaveis:
        pode_ver = True
    # observador
    elif chamado.observadores_id and u.id in chamado.observadores_id:
        pode_ver = True
    # primeiro usuário que interagiu no chamado
    else:
        primeira_interacao = chamado.interacoeschamados.order_by("data").first()
        if primeira_interacao and primeira_interacao.usuario_id == u.id:
            pode_ver = True
    if not pode_ver:
        messages.warning(request, "Você não tem permissão para acessar este chamado.")
        return redirect("listar_chamados")

    interacoeschamados = chamado.interacoeschamados.select_related("usuario").order_by("data")
    oss = chamado.ordemservico_set.all()

    eventos = []

    # Interações normais
    for i in interacoeschamados:
        i.tipo = "interacao"
        i.momento = i.data
        eventos.append(i)

    # Eventos das OS com ordenação lógica fixa
    for o in oss:
        ordem_os = []

        def trunc_minuto(dt):
            if not dt:
                return None
            return dt.replace(second=0, microsecond=0)

        if o.data_criacao:
            ordem_os.append(("aberta", o.data_criacao, trunc_minuto(o.data_criacao)))
        if o.inicio_real:
            ordem_os.append(("iniciada", o.inicio_real, trunc_minuto(o.inicio_real)))
        if o.final_real:
            ordem_os.append(("finalizada", o.final_real, trunc_minuto(o.final_real)))

        # ORDEM CORRETA: 1º minuto truncado, 2º ordem fixa
        ordem_os.sort(
            key=lambda x: (
                x[2],  # minuto truncado
                ["aberta", "iniciada", "finalizada"].index(x[0]),  # ordem fixa
            )
        )

        for idx, (tipo, momento_original, momento_truncado) in enumerate(ordem_os):
            eventos.append(
                {
                    "tipo": "os_evento",
                    "descricao": f"Ordem de Serviço {tipo.capitalize()} (OS {o.id})",
                    "momento": momento_truncado + timedelta(microseconds=idx),
                    "momento_real": momento_original,
                }
            )

    # Ordenação global
    eventos.sort(key=lambda e: e["momento"] if isinstance(e, dict) else e.momento)

    # Usuário
    pode_editar = u.has_perm("manutencao.pode_manipular_chamados") or u.is_staff

    initial = {
        "responsaveis": CustomUser.objects.filter(id__in=chamado.responsaveis or []),
        "observadores_id": CustomUser.objects.filter(id__in=chamado.observadores_id or []),
    }

    chamado_form = ChamadoForm(request.POST or None, instance=chamado, initial=initial)
    chamado_form.fields["recurso"].queryset = _recursos_visiveis(u)
    interacao_chamado_form = InteracaoChamadoForm(request.POST or None)

    # Bloqueia edição para quem não pode
    if not pode_editar:
        for campo in ["nome", "categoria", "status", "prioridade", "recurso"]:
            if campo in chamado_form.fields:
                chamado_form.fields[campo].widget.attrs["disabled"] = True

    # Querysets filtrados
    chamado_form.fields["responsaveis"].queryset = CustomUser.objects.filter(
        groups__name=GRUPO_RESPONSAVEIS
    ).order_by("first_name")
    chamado_form.fields["observadores_id"].queryset = CustomUser.objects.filter(
        groups__name=GRUPO_OBSERVADORES
    ).order_by("first_name")

    # POST
    if request.method == "POST":
        msg = interacao_chamado_form.data.get("mensagem", "").strip()
        alterou = False
        interagiu = False

        # Nova interação
        if msg and interacao_chamado_form.is_valid():
            Interacao_Chamado.objects.create(chamado=chamado, usuario=u, mensagem=msg)
            interagiu = True

            # ===== EMAIL — INTERAÇÃO =====
            dest = set()

            # criador do chamado (primeira interação)
            primeira = chamado.interacoeschamados.order_by("data").first()
            if primeira and primeira.usuario and primeira.usuario.email:
                dest.add(primeira.usuario.email)

            # responsáveis
            if chamado.responsaveis:
                resp_users = CustomUser.objects.filter(id__in=chamado.responsaveis, is_active=True)
                dest.update(_emails_validos(resp_users))

            # observadores
            if chamado.observadores_id:
                obs_users = CustomUser.objects.filter(
                    id__in=chamado.observadores_id, is_active=True
                )
                dest.update(_emails_validos(obs_users))

            # autor da interação
            if u.email:
                dest.add(u.email)

            assunto = f"CHAMADO MANUTENÇÃO {chamado.id} — {chamado.nome} - Nova interação"
            corpo = (
                f"Nova interação registrada no chamado {chamado.id}.\n\n"
                f"Mensagem:\n{msg}\n\n"
                f"Por: {u.get_full_name() or u.username}\n"
                f"Recurso: {chamado.recurso.descricao}\n\n"
                f"Acesse o portal para verificar mais informações:\n"
                f"{settings.PORTAL_BASE_URL}/setores/manutencao/{chamado.id}/\n"
            )

            enviar_email(assunto, corpo, list(dest))

        # Alterações no chamado
        if pode_editar and chamado_form.is_valid() and chamado_form.has_changed():
            # STATUS ANTERIOR DIRETO DO BANCO
            status_anterior = Chamado.objects.get(pk=chamado.id).status

            # SALVA A EDIÇÃO
            chamado_edit = chamado_form.save(commit=False)
            chamado_edit.responsaveis = [
                u.id for u in chamado_form.cleaned_data.get("responsaveis", [])
            ]
            chamado_edit.observadores_id = [
                u.id for u in chamado_form.cleaned_data.get("observadores_id", [])
            ]
            chamado_edit.save()
            alterou = True

            # STATUS NOVO DIRETO DO BANCO
            status_atual = Chamado.objects.get(pk=chamado.id).status

            # DISPARA EMAIL
            if status_anterior != "FECHADO" and status_atual == "FECHADO":
                dest = set()

                primeira = chamado_edit.interacoeschamados.order_by("data").first()
                if primeira and primeira.usuario and primeira.usuario.email:
                    dest.add(primeira.usuario.email)

                if chamado_edit.responsaveis:
                    dest.update(
                        _emails_validos(
                            CustomUser.objects.filter(
                                id__in=chamado_edit.responsaveis, is_active=True
                            )
                        )
                    )

                if chamado_edit.observadores_id:
                    dest.update(
                        _emails_validos(
                            CustomUser.objects.filter(
                                id__in=chamado_edit.observadores_id, is_active=True
                            )
                        )
                    )

                assunto = f"CHAMADO MANUTENÇÃO {chamado_edit.id} — {chamado_edit.nome} — Finalizado"
                corpo = (
                    f"O chamado {chamado_edit.id} foi FINALIZADO.\n\n"
                    f"Finalizado por: {u.get_full_name() or u.username}\n"
                    f"Recurso: {chamado_edit.recurso.descricao}\n\n"
                    f"Acesse o portal para verificar mais informações:\n"
                    f"{settings.PORTAL_BASE_URL}/setores/manutencao/{chamado.id}/\n"
                )

                enviar_email(assunto, corpo, list(dest))

        elif not pode_editar and not interagiu:
            messages.warning(request, "Você não tem permissão para alterar os dados do chamado.")

        # Mensagens finais
        if alterou and interagiu:
            messages.success(request, "Alterações e interação salvas com sucesso.")
        elif alterou:
            messages.success(request, "Alterações do chamado salvas com sucesso.")
        elif interagiu:
            messages.success(request, "Interação adicionada com sucesso.")

        return redirect("detalhar_chamado", pk=chamado.id)

    return render(
        request,
        "setores/manutencao/chamados.html",
        {
            "modo": "detalhe",
            "chamado": chamado,
            "chamado_form": chamado_form,
            "eventos": eventos,
            "form": interacao_chamado_form,
            "pode_editar": pode_editar,
        },
    )


@permissao_requerida("manutencao.pode_acessar_chamados")
def excluir_chamado(request, pk):
    chamado = get_object_or_404(_chamados_visiveis(request.user), pk=pk)

    # 🔒 impede exclusão se tiver OS vinculada
    if chamado.ordemservico_set.exists():
        messages.warning(
            request,
            f"Não é possível excluir o chamado {pk} pois existem Ordens de Serviço vinculadas.",
        )
        return redirect("listar_chamados")  # ← volta pra listagem

    # 🔐 permissão
    if not (request.user.has_perm("manutencao.pode_manipular_chamados") or request.user.is_staff):
        messages.warning(request, "Você não tem permissão para excluir chamados.")
        return redirect("listar_chamados")

    if request.method == "GET":
        chamados = _chamados_visiveis(request.user).select_related("recurso").order_by("-id")
        return render(
            request,
            "setores/manutencao/chamados.html",
            {"modo": "lista", "chamados": chamados, "chamado_excluir": chamado},
        )

    if request.method == "POST":
        chamado.delete()
        messages.warning(request, f"Chamado {pk} excluído com sucesso.")
        return redirect("listar_chamados")
