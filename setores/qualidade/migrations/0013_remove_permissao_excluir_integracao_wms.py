from django.db import migrations

CODENAME = "pode_excluir_integracao_wms"
DESCRICAO = "Pode excluir integrações WMS"


def _remover_permissao(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    content_type = ContentType.objects.filter(
        app_label="qualidade", model="permissoesqualidade"
    ).first()
    if content_type:
        Permission.objects.filter(content_type=content_type, codename=CODENAME).delete()


def _restaurar_permissao(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    content_type = ContentType.objects.filter(
        app_label="qualidade", model="permissoesqualidade"
    ).first()
    if content_type:
        Permission.objects.get_or_create(
            content_type=content_type,
            codename=CODENAME,
            defaults={"name": DESCRICAO},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("qualidade", "0012_alter_permissoesqualidade_options"),
    ]

    operations = [
        # A exclusão WMS passou a usar a permissão unificada das filas
        # (producao.pode_excluir_pendencias_integracao); esta aqui saiu do
        # catálogo e é removida do banco junto com concessões pendentes.
        migrations.RunPython(_remover_permissao, _restaurar_permissao),
    ]
