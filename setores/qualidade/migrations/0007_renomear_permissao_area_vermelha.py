from django.db import migrations


def renomear_permissao_area_vermelha(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    content_type = ContentType.objects.filter(
        app_label="qualidade",
        model="permissoesqualidade",
    ).first()
    if content_type is None:
        return

    # Renomeia o codename mantendo o mesmo registro: atribuições de grupo e
    # de usuário apontam para o id da permissão e continuam valendo.
    Permission.objects.filter(
        content_type=content_type,
        codename="pode_liberar_area_vermelha",
    ).update(codename="pode_acessar_area_vermelha")


class Migration(migrations.Migration):
    dependencies = [
        ("qualidade", "0006_liberacaolote_qtdprensa_alter_liberacaolote_status"),
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
                        "pode_acessar_area_vermelha",
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
        migrations.RunPython(renomear_permissao_area_vermelha, migrations.RunPython.noop),
    ]
