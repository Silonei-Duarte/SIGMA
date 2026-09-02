from collections import defaultdict

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.shortcuts import get_object_or_404, redirect, render

from SIGMA.autorizacao import (
    APPS_PERMISSOES_GESTAO_ACESSOS,
    PERMISSAO_ADMINISTRAR_ACESSOS,
    permissao_requerida,
)

User = get_user_model()


@permissao_requerida(PERMISSAO_ADMINISTRAR_ACESSOS)
def grupos_view(request):
    grupos = Group.objects.all().order_by("name")
    usuarios = User.objects.filter(is_staff=False, is_superuser=False).order_by("username")
    permissoes = Permission.objects.filter(
        content_type__app_label__in=APPS_PERMISSOES_GESTAO_ACESSOS
    ).select_related("content_type")

    permissoes_por_app = defaultdict(list)
    # Ordenar por nome insensível a maiúsculas
    sorted_perms = sorted(permissoes, key=lambda x: x.name.lower())
    for p in sorted_perms:
        permissoes_por_app[p.content_type.app_label].append(p)

    # 🔹 ordenar e renomear visualmente
    mapping = {
        "accounts": "Geral",
        "producao": "Produção",
        "manutencao": "Manutenção",
        "qualidade": "Qualidade",
        "pcp": "PCP",
        "logistica": "Logística",
        "suprimentos": "Suprimentos",
    }

    ordenado = []
    # Primeiro os mapeados na ordem desejada
    for label in [
        "accounts",
        "producao",
        "manutencao",
        "qualidade",
        "pcp",
        "logistica",
        "suprimentos",
    ]:
        if label in permissoes_por_app:
            ordenado.append((mapping[label], permissoes_por_app[label]))

    # Outros (caso existam)
    for label, perms in list(permissoes_por_app.items()):
        if label not in mapping:
            ordenado.append((label.capitalize(), perms))

    grupo_editando = None

    # 🔹 Exclusão de grupo
    if request.method == "POST" and "deletar" in request.POST:
        grupo_id = request.POST.get("deletar")
        grupo = get_object_or_404(Group, id=grupo_id)

        # 🔒 bloqueia grupos essenciais (por ID)
        GRUPOS_PROTEGIDOS_IDS = [3, 7, 8]  # Adicione os IDs reais aqui
        if grupo.id in GRUPOS_PROTEGIDOS_IDS:
            messages.error(request, f"O grupo '{grupo.name}' é protegido e não pode ser excluído.")
            return redirect("grupos_view")

        # impede exclusão se houver usuários
        if grupo.user_set.exists():
            messages.error(request, "Não é possível excluir um grupo que ainda possui usuários.")
            return redirect("grupos_view")

        # 🔹 bloqueia exclusão se houver qualquer modelo referenciando este grupo
        related = []
        for rel in grupo._meta.related_objects:
            model = rel.related_model
            nome = model._meta.verbose_name_plural.title()
            if model.objects.filter(**{rel.field.name: grupo}).exists():
                related.append(nome)

        if related:
            lista = ", ".join(related)
            messages.warning(
                request,
                f"Não é possível excluir este grupo pois ele está vinculado a registros: {lista}.",
            )
            return redirect("grupos_view")

        grupo.delete()
        messages.success(request, f"Grupo '{grupo.name}' excluído com sucesso.")
        return redirect("grupos_view")

    # 🔹 Criação / Edição
    if request.method == "POST" and "salvar" in request.POST:
        grupo_id = request.POST.get("grupo_id")
        nome = request.POST.get("nome").strip()
        users_ids = request.POST.getlist("usuarios")
        perms_ids = request.POST.getlist("permissoes")

        if not nome:
            messages.error(request, "O nome do grupo é obrigatório.")
            return redirect("grupos_view")

        if grupo_id:
            grupo = get_object_or_404(Group, id=grupo_id)
            grupo.name = nome
            grupo.save()
            messages.success(request, f"Grupo '{nome}' atualizado com sucesso.")
        else:
            grupo = Group.objects.create(name=nome)
            messages.success(request, f"Grupo '{nome}' criado com sucesso.")

        grupo.user_set.set(
            User.objects.filter(id__in=users_ids, is_staff=False, is_superuser=False)
        )
        # Whitelist server-side: mesmo que a UI, o POST forjado não concede
        # permissão de app fora da lista de gestão de acessos. IDs inválidos
        # são ignorados silenciosamente, como já ocorre com usuários.
        grupo.permissions.set(
            Permission.objects.filter(
                id__in=perms_ids,
                content_type__app_label__in=APPS_PERMISSOES_GESTAO_ACESSOS,
            )
        )

        return redirect("grupos_view")

    elif request.method == "GET" and "editar" in request.GET:
        grupo_editando = get_object_or_404(Group, id=request.GET.get("editar"))

    return render(
        request,
        "accounts/grupos.html",
        {
            "grupos": grupos,
            "usuarios": usuarios,
            "permissoes_por_app": ordenado,
            "grupo_editando": grupo_editando,
        },
    )
