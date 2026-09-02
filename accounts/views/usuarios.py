import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from SIGMA.autorizacao import PERMISSAO_ADMINISTRAR_ACESSOS, permissao_requerida

from ..forms import CustomUserForm

User = get_user_model()

logger = logging.getLogger(__name__)


@permissao_requerida(PERMISSAO_ADMINISTRAR_ACESSOS)
def lista_usuarios(request):
    filtro_status = request.GET.get("status", "ativos")
    usuarios = User.objects.all().order_by("username")

    if filtro_status == "inativos":
        usuarios = usuarios.filter(is_active=False)
    elif filtro_status == "todos":
        pass
    else:
        filtro_status = "ativos"
        usuarios = usuarios.filter(is_active=True)

    paginator = Paginator(usuarios, 16)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    qtd_admins = User.objects.filter(is_superuser=True).count()

    return render(
        request,
        "accounts/lista_usuarios.html",
        {
            "page_obj": page_obj,
            "qtd_admins": qtd_admins,
            "filtro_status": filtro_status,
        },
    )


@permissao_requerida(PERMISSAO_ADMINISTRAR_ACESSOS)
def cadastrar_usuario(request):
    if request.method == "POST":
        _registrar_escalada_staff(request)
        form = CustomUserForm(request.POST, pode_definir_staff=request.user.is_superuser)
        if form.is_valid():
            form.save()
            messages.success(request, "Usuário criado com sucesso!")
            return redirect("lista_usuarios")
    else:
        form = CustomUserForm(pode_definir_staff=request.user.is_superuser)

    return render(
        request,
        "accounts/form_usuario.html",
        {"form": form, "title": "Cadastrar Usuário", "button_text": "Salvar"},
    )


@permissao_requerida(PERMISSAO_ADMINISTRAR_ACESSOS)
def editar_usuario(request, user_id):
    usuario = get_object_or_404(User, id=user_id)

    # Sem edição da própria conta pela tela de gestão: quem tem o poder não
    # escala privilégio editando a si mesmo (staff/senha/permissões).
    if usuario.pk == request.user.pk:
        logger.warning(
            "Usuário %s tentou editar a própria conta pela tela de gestão de usuários.",
            request.user.username,
        )
        messages.error(request, "Não é possível editar sua própria conta por esta tela.")
        return redirect("lista_usuarios")

    # Só outro superusuário pode editar/resetar senha de uma conta superusuário —
    # mesma proteção que deletar_usuario já aplica contra exclusão de superusuário.
    # A permissao delegada tambem nao altera contas staff.
    if (usuario.is_staff or usuario.is_superuser) and not request.user.is_superuser:
        raise PermissionDenied

    if request.method == "POST":
        _registrar_escalada_staff(request)
        form = CustomUserForm(
            request.POST, instance=usuario, pode_definir_staff=request.user.is_superuser
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Usuário atualizado com sucesso!")
            return redirect("lista_usuarios")
    else:
        form = CustomUserForm(instance=usuario, pode_definir_staff=request.user.is_superuser)

    return render(
        request,
        "accounts/form_usuario.html",
        {"form": form, "title": "Editar Usuário", "button_text": "Atualizar"},
    )


@permissao_requerida(PERMISSAO_ADMINISTRAR_ACESSOS)
def deletar_usuario(request, user_id):
    usuario = get_object_or_404(User, id=user_id)

    if request.method != "POST":
        messages.error(request, "A exclusão só pode ser feita por POST.")
        return redirect("lista_usuarios")

    # A permissão delegada não permite remover uma conta com poder
    # administrativo; isso preserva a separação entre gestão e superusuário.
    if (usuario.is_staff or usuario.is_superuser) and not request.user.is_superuser:
        raise PermissionDenied

    # bloqueia exclusão se houver relações FK
    related = []
    for rel in usuario._meta.related_objects:
        model = rel.related_model
        nome = model._meta.verbose_name_plural.title()
        if model.objects.filter(**{rel.field.name: usuario}).exists():
            related.append(nome)

    if related:
        lista = ", ".join(related)
        messages.error(
            request,
            f"Não é possível excluir este usuário pois ele possui registros relacionados: {lista}.",
        )
        return redirect("lista_usuarios")

    # Protege superusuários de serem excluídos
    if usuario.is_superuser:
        messages.error(request, "Não é possível excluir um administrador superusuário.")
        return redirect("lista_usuarios")

    usuario.delete()
    messages.success(request, "Usuário removido com sucesso!")
    return redirect("lista_usuarios")


def _registrar_escalada_staff(request) -> None:
    """Log operacional de tentativa de escala a staff sem poder de superusuário."""
    if not request.user.is_superuser and "is_staff" in request.POST:
        logger.warning(
            "Usuário %s enviou is_staff em POST da tela de usuários sem ser "
            "superusuário; valor ignorado pelo form.",
            request.user.username,
        )
