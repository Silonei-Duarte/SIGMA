from django.db import migrations

PERMISSOES_ANTERIORES = (
    "pode_liberar_bobinas",
    "pode_area_vermelha_bobinas",
)


def atualizar_permissoes(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    content_type = ContentType.objects.filter(
        app_label="qualidade",
        model="permissoesqualidade",
    ).first()
    if content_type is None:
        # Em um banco novo, os ContentTypes só são criados no post_migrate.
        # As permissões finais serão criadas nesse mesmo sinal.
        return

    permissoes_anteriores = Permission.objects.filter(
        content_type=content_type,
        codename__in=PERMISSOES_ANTERIORES,
    )
    permissao_acessar, _ = Permission.objects.get_or_create(
        content_type=content_type,
        codename="pode_acessar_liberacao_lotes",
        defaults={"name": "Pode acessar a tela de liberação de lotes"},
    )
    permissao_destinar, _ = Permission.objects.get_or_create(
        content_type=content_type,
        codename="pode_destinar_lotes_liberacao",
        defaults={"name": "Pode destinar lotes na tela de liberação"},
    )

    permissao_liberar = permissoes_anteriores.filter(codename="pode_liberar_bobinas").first()
    if permissao_liberar:
        for grupo in permissao_liberar.group_set.all():
            grupo.permissions.add(permissao_acessar, permissao_destinar)
        for usuario in permissao_liberar.user_set.all():
            usuario.user_permissions.add(permissao_acessar, permissao_destinar)

    for permissao_anterior in permissoes_anteriores:
        for grupo in permissao_anterior.group_set.all():
            grupo.permissions.add(permissao_destinar)
        for usuario in permissao_anterior.user_set.all():
            usuario.user_permissions.add(permissao_destinar)

    permissoes_anteriores.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("qualidade", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="permissoesqualidade",
            options={
                "default_permissions": (),
                "managed": False,
                "permissions": [
                    ("pode_acessar_liberacao_lotes", "Pode acessar a tela de liberação de lotes"),
                    ("pode_destinar_lotes_liberacao", "Pode destinar lotes na tela de liberação"),
                    (
                        "pode_liberar_area_vermelha",
                        "Pode acessar a tela de liberação da área vermelha",
                    ),
                    ("pode_destinar_area_vermelha", "Pode destinar lotes na área vermelha"),
                    (
                        "pode_cadastrar_observacoes_etiqueta",
                        "Pode cadastrar observações de etiqueta",
                    ),
                ],
            },
        ),
        migrations.RunPython(atualizar_permissoes, migrations.RunPython.noop),
    ]
