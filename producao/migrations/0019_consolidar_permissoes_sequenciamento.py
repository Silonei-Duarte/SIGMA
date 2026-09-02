from django.db import migrations

PERMISSOES_LEGADAS = {
    "acesso_sequenciamento": "pode_acessar_sequenciamento",
    "consolidar_sequenciamento": "pode_consolidar_sequenciamento_erp",
}


def consolidar_permissoes_sequenciamento(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")

    for codename_legado, codename_oficial in PERMISSOES_LEGADAS.items():
        permissao_oficial = Permission.objects.filter(
            content_type__app_label="producao",
            content_type__model="permissoesproducao",
            codename=codename_oficial,
        ).first()
        if not permissao_oficial:
            continue

        permissoes_legadas = Permission.objects.filter(
            codename=codename_legado,
            content_type__app_label__in=("accounts", "producao"),
            content_type__model="sequenciamento",
        )
        for permissao_legada in permissoes_legadas:
            grupos = list(permissao_legada.group_set.all())
            usuarios = list(permissao_legada.user_set.all())
            for grupo in grupos:
                grupo.permissions.add(permissao_oficial)
                grupo.permissions.remove(permissao_legada)
            for usuario in usuarios:
                usuario.user_permissions.add(permissao_oficial)
                usuario.user_permissions.remove(permissao_legada)
            permissao_legada.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("producao", "0018_justificativaparada_data_hora_remover_log_parada"),
    ]

    operations = [
        migrations.RunPython(consolidar_permissoes_sequenciamento, migrations.RunPython.noop),
    ]
