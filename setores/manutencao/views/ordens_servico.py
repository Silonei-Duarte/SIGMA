import logging

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import CustomUser, Recurso
from setores.manutencao.forms import GRUPO_RESPONSAVEIS, InteracaoOSForm, OrdemServicoForm
from setores.manutencao.models import Chamado, Interacao_OS, OrdemServico
from SIGMA.autorizacao import permissao_requerida

logger = logging.getLogger(__name__)


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
        logger.exception("Falha ao enviar e-mail de ordem de serviço")


def _ordens_visiveis(usuario):
    if usuario.is_staff:
        return OrdemServico.objects.all()
    ordens_da_filial = OrdemServico.objects.filter(recurso__in=_recursos_visiveis(usuario))
    if usuario.has_perm("manutencao.pode_listar_todas_os"):
        return ordens_da_filial
    return ordens_da_filial.filter(responsaveis__contains=[usuario.id])


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
    return Chamado.objects.filter(recurso__in=_recursos_visiveis(usuario))


@permissao_requerida("manutencao.pode_acessar_os")
def listar_os(request):
    u = request.user
    if request.GET.get("nova"):
        return redirect("abrir_os")

    # =================== PERMISSÃO DE LISTAGEM ====================
    ordens = _ordens_visiveis(u).select_related("recurso").order_by("-id")

    # =================== FILTROS ====================
    recurso = request.GET.get("recurso")
    status = request.GET.get("status")

    if recurso:
        ordens = ordens.filter(recurso_id=recurso)

    if status:
        ordens = ordens.filter(status=status)

    # =================== PAGINAÇÃO ====================
    paginator = Paginator(ordens, 20)
    page_number = request.GET.get("page")
    ordens = paginator.get_page(page_number)

    recursos = _recursos_visiveis(u).order_by("descricao")

    return render(
        request,
        "setores/manutencao/ordens_servico.html",
        {
            "modo": "lista",
            "ordens": ordens,
            "recursos": recursos,
            "status_list": OrdemServico.Status.choices,
            "recurso_sel": recurso,
            "status_sel": status,
        },
    )


@permissao_requerida("manutencao.pode_acessar_os")
def abrir_os(request):
    # A rota só existe para abrir OS; a checagem de manipulação permanece no
    # corpo porque o deny atual é mensagem + redirecionamento para a listagem,
    # não um 403 puro — comportamento preservado de propósito.
    if not (request.user.has_perm("manutencao.pode_manipular_os") or request.user.is_staff):
        messages.warning(request, "Você não tem permissão para abrir Ordens de Serviço.")
        return redirect("listar_os")

    initial = {}
    chamado_id = request.GET.get("chamado")
    if chamado_id:
        chamado = _chamados_visiveis(request.user).filter(pk=chamado_id).first()
        if chamado:
            initial["chamado"] = chamado
            initial["recurso"] = chamado.recurso

    if request.method == "POST":
        data = request.POST.copy()

        if not data.get("status"):
            data["status"] = "ABERTA"

        form = OrdemServicoForm(
            data,
            recurso_queryset=_recursos_visiveis(request.user),
            chamado_queryset=_chamados_visiveis(request.user),
        )
        form.fields["responsaveis"].queryset = CustomUser.objects.filter(
            groups__name=GRUPO_RESPONSAVEIS
        ).order_by("first_name")
        selecionados = data.getlist("responsaveis")

        if form.is_valid():
            os_obj = form.save(commit=False)
            os_obj.save()
            os_obj.responsaveis = [u.id for u in form.cleaned_data.get("responsaveis", [])]
            os_obj.save()
            messages.success(request, "Ordem de Serviço criada com sucesso.")

            # INTERAÇÃO INICIAL — Quem abriu
            Interacao_OS.objects.create(
                ordem_servico=os_obj,
                usuario=request.user,
                descricao="OS aberta.",
                inicio=None,
                fim=None,
            )

            # ===== EMAIL - ABERTURA DA OS =====
            dest = set()

            # quem abriu
            if request.user.email:
                dest.add(request.user.email)

            # responsáveis
            resp = form.cleaned_data.get("responsaveis") or []
            dest.update(
                _emails_validos(
                    CustomUser.objects.filter(id__in=[u.id for u in resp], is_active=True)
                )
            )

            assunto = f"OS {os_obj.id} — ABERTA"
            corpo = (
                f"Ordem de Serviço {os_obj.id} foi ABERTA.\n\n"
                f"Descrição: {os_obj.descricao or ''}\n"
                f"Recurso: {os_obj.recurso.descricao}\n\n"
                f"Acesse o portal para verificar mais informações:\n"
                f"{settings.PORTAL_BASE_URL}/setores/manutencao/os/{os_obj.id}/\n"
            )

            enviar_email(assunto, corpo, list(dest))

            return redirect("detalhar_os", pk=os_obj.id)
        else:
            for erros in form.errors.values():
                for erro in erros:
                    messages.warning(request, erro)

            return render(
                request,
                "setores/manutencao/ordens_servico.html",
                {"modo": "form", "form": form, "selecionados": selecionados},
            )

    else:
        form = OrdemServicoForm(
            initial=initial,
            recurso_queryset=_recursos_visiveis(request.user),
            chamado_queryset=_chamados_visiveis(request.user),
        )
        form.fields["responsaveis"].queryset = CustomUser.objects.filter(
            groups__name=GRUPO_RESPONSAVEIS
        ).order_by("first_name")
        selecionados = []

    return render(
        request,
        "setores/manutencao/ordens_servico.html",
        {"modo": "form", "form": form, "selecionados": selecionados},
    )


@permissao_requerida("manutencao.pode_acessar_os")
def detalhar_os(request, pk):
    from django.utils import timezone

    u = request.user
    os_obj = get_object_or_404(_ordens_visiveis(u), pk=pk)
    interacoes = os_obj.interacoesos.select_related("usuario").order_by("data_registro")
    bloqueada = os_obj.status == "FINALIZADA"

    # ==================== PERMISSÃO DE ACESSO ====================
    # O escopo de visibilidade já foi garantido pelo get_object_or_404 com
    # _ordens_visiveis(u) acima; a rechecagem local (pode_ver = False seguida
    # de exists()) era código morto — sempre verdadeiro aqui — e foi removida.

    # ==================== QUEM PODE MANIPULAR ====================
    pode_manipular = u.is_staff or u.has_perm("manutencao.pode_manipular_os")

    # ==================== QUEM PODE INTERAGIR ====================
    pode_interagir = (
        u.is_staff
        or u.has_perm("manutencao.pode_manipular_os")
        or (os_obj.responsaveis and u.id in os_obj.responsaveis)
    )

    # instância padrão
    interacao_form = InteracaoOSForm()

    # ========================= POST ============================
    if request.method == "POST":
        # ---------- impedir manipulação ----------
        if bloqueada:
            messages.warning(request, "Esta OS está finalizada e não pode mais ser alterada.")
            return redirect("detalhar_os", pk=os_obj.id)

        # ---------- FINALIZAR ----------
        if "finalizar_os" in request.POST:
            if not pode_interagir:  # <-- AGORA QUEM INTERAGE PODE FINALIZAR
                messages.warning(request, "Você não tem permissão para finalizar esta OS.")
                return redirect("detalhar_os", pk=os_obj.id)

            if os_obj.status != "PARADA":
                messages.warning(request, "Só é possível finalizar uma OS que esteja PARADA.")
                return redirect("detalhar_os", pk=os_obj.id)

            if not os_obj.inicio_real:
                messages.warning(
                    request, "Não é possível finalizar uma OS que ainda não foi iniciada."
                )
                return redirect("detalhar_os", pk=os_obj.id)

            os_obj.status = "FINALIZADA"
            os_obj.final_real = timezone.now()
            os_obj.save()
            messages.success(request, "OS finalizada com sucesso.")
            return redirect("detalhar_os", pk=os_obj.id)

        # ---------- INTERAÇÃO ----------
        elif "salvar_interacao" in request.POST:
            if not pode_interagir:
                messages.warning(request, "Você não pode registrar interações nesta OS.")
                return redirect("detalhar_os", pk=os_obj.id)

            interacao_form = InteracaoOSForm(request.POST)
            if not interacao_form.is_valid():
                for erros in interacao_form.errors.values():
                    for erro in erros:
                        messages.warning(request, erro)
                return redirect("detalhar_os", pk=os_obj.id)

            desc = interacao_form.cleaned_data["descricao"].strip()
            inicio = interacao_form.cleaned_data["inicio"]
            fim = interacao_form.cleaned_data["fim"]
            if not desc:
                messages.warning(
                    request, "Para registrar uma interação é necessário preencher a descrição."
                )
                return redirect("detalhar_os", pk=os_obj.id)
            agora = timezone.now()

            if (inicio and inicio > agora) or (fim and fim > agora):
                messages.warning(
                    request, "A data da interação não pode ser maior que a data atual."
                )
                return redirect("detalhar_os", pk=os_obj.id)

            ultima = os_obj.interacoesos.order_by("-data_registro").first()
            ultima_data = ultima.fim or ultima.inicio if ultima else None

            nova_data = inicio or fim

            if ultima_data and nova_data < ultima_data:
                messages.warning(
                    request, "A data da nova interação não pode ser menor que a anterior."
                )
                return redirect("detalhar_os", pk=os_obj.id)

            # INÍCIO
            if not ultima or ultima.fim or not ultima.inicio:
                # pegar valor anterior do banco ANTES
                inicio_real_anterior = os_obj.inicio_real

                Interacao_OS.objects.create(
                    ordem_servico=os_obj,
                    usuario=u,
                    descricao=desc,
                    inicio=nova_data,
                    fim=None,
                )

                if not os_obj.inicio_real:
                    os_obj.inicio_real = nova_data
                    os_obj.final_real = None

                os_obj.status = "EM_EXECUCAO"
                os_obj.save()

                # enviar email SOMENTE se mudou
                if inicio_real_anterior != os_obj.inicio_real:
                    dest = set()

                    primeira_interacao = os_obj.interacoesos.order_by("data_registro").first()
                    if (
                        primeira_interacao
                        and primeira_interacao.usuario
                        and primeira_interacao.usuario.email
                    ):
                        dest.add(primeira_interacao.usuario.email)

                    if os_obj.responsaveis:
                        dest.update(
                            _emails_validos(
                                CustomUser.objects.filter(
                                    id__in=os_obj.responsaveis, is_active=True
                                )
                            )
                        )

                    assunto = f"OS {os_obj.id} — Início Real"
                    corpo = (
                        f"A OS {os_obj.id} iniciou execução.\n\n"
                        f"Início real: {os_obj.inicio_real}\n"
                        f"Recurso: {os_obj.recurso.descricao}\n\n"
                        f"Acesse o portal para verificar mais informações:\n"
                        f"{settings.PORTAL_BASE_URL}/setores/manutencao/os/{os_obj.id}/\n"
                    )

                    enviar_email(assunto, corpo, list(dest))

            # FIM
            else:
                fim_real_anterior = os_obj.final_real

                Interacao_OS.objects.create(
                    ordem_servico=os_obj,
                    usuario=u,
                    descricao=desc,
                    inicio=None,
                    fim=nova_data,
                )

                os_obj.status = "PARADA"
                os_obj.final_real = nova_data
                os_obj.save()

                if fim_real_anterior != os_obj.final_real:
                    dest = set()

                    primeira_interacao = os_obj.interacoesos.order_by("data_registro").first()
                    if (
                        primeira_interacao
                        and primeira_interacao.usuario
                        and primeira_interacao.usuario.email
                    ):
                        dest.add(primeira_interacao.usuario.email)

                    if os_obj.responsaveis:
                        dest.update(
                            _emails_validos(
                                CustomUser.objects.filter(
                                    id__in=os_obj.responsaveis, is_active=True
                                )
                            )
                        )

                    assunto = f"OS {os_obj.id} — Fim Real"
                    corpo = (
                        f"A OS {os_obj.id} teve FIM REAL registrado.\n\n"
                        f"Fim real: {os_obj.final_real}\n"
                        f"Recurso: {os_obj.recurso.descricao}\n\n"
                        f"Acesse o portal para verificar mais informações:\n"
                        f"{settings.PORTAL_BASE_URL}/setores/manutencao/os/{os_obj.id}/\n"
                    )

                    enviar_email(assunto, corpo, list(dest))

            messages.success(request, "Interação registrada com sucesso.")
            return redirect("detalhar_os", pk=os_obj.id)

        # ---------- SALVAR ALTERAÇÕES ----------
        elif "salvar" in request.POST:
            if not pode_manipular:
                messages.warning(request, "Você não tem permissão para alterar esta OS.")
                return redirect("detalhar_os", pk=os_obj.id)

            inicio_real_atual = os_obj.inicio_real
            final_real_atual = os_obj.final_real

            chamado_atual = os_obj.chamado
            os_form = OrdemServicoForm(
                request.POST,
                instance=os_obj,
                recurso_queryset=_recursos_visiveis(request.user),
                chamado_queryset=_chamados_visiveis(request.user),
            )

            if os_form.is_valid():
                os_edit = os_form.save(commit=False)
                os_edit.inicio_real = inicio_real_atual
                os_edit.final_real = final_real_atual
                os_edit.chamado = chamado_atual
                os_edit.save()

                os_edit.responsaveis = [
                    usuario.id for usuario in os_form.cleaned_data["responsaveis"]
                ]
                os_edit.save()

                messages.success(request, "Alterações da OS salvas com sucesso.")

            else:
                for campo, erros in os_form.errors.items():
                    for erro in erros:
                        messages.warning(request, f"{campo}: {erro}")

            return render(
                request,
                "setores/manutencao/ordens_servico.html",
                {
                    "modo": "detalhe",
                    "os_obj": os_form.instance,
                    "os_form": os_form,
                    "interacoes": interacoes,
                    "form": interacao_form,
                    "bloqueada": bloqueada,
                    "pode_manipular": pode_manipular,
                    "pode_interagir": pode_interagir,
                },
            )

    # SE NÃO FOR POST → CRIA O FORM NORMAL
    if request.method != "POST":
        os_form = OrdemServicoForm(
            instance=os_obj,
            recurso_queryset=_recursos_visiveis(request.user),
            chamado_queryset=_chamados_visiveis(request.user),
        )
        os_form.fields["descricao"].widget.attrs.update(
            {"readonly": True, "style": "background-color:#e9ecef;"}
        )
        os_form.fields["responsaveis"].queryset = CustomUser.objects.filter(
            groups__name=GRUPO_RESPONSAVEIS
        ).order_by("first_name")

    return render(
        request,
        "setores/manutencao/ordens_servico.html",
        {
            "modo": "detalhe",
            "os_obj": os_obj,
            "os_form": os_form,
            "interacoes": interacoes,
            "form": interacao_form,
            "bloqueada": bloqueada,
            "pode_manipular": pode_manipular,
            "pode_interagir": pode_interagir,
        },
    )


@permissao_requerida("manutencao.pode_acessar_os")
def excluir_os(request, pk):
    os_obj = get_object_or_404(_ordens_visiveis(request.user), pk=pk)

    if not (request.user.has_perm("manutencao.pode_manipular_os") or request.user.is_staff):
        messages.warning(request, "Você não tem permissão para excluir ordens de serviço.")
        return redirect("listar_os")

    if request.method == "GET":
        ordens = _ordens_visiveis(request.user).select_related("recurso").order_by("-id")
        return render(
            request,
            "setores/manutencao/ordens_servico.html",
            {"modo": "lista", "ordens": ordens, "os_excluir": os_obj},
        )

    if request.method == "POST":
        os_obj.delete()
        messages.warning(request, f"OS {pk} excluída com sucesso.")
        return redirect("listar_os")
