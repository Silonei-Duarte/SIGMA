from django.db import migrations


def copiar_exibir_jus_para_aponta_parada(apps, schema_editor):
    Recurso = apps.get_model("accounts", "Recurso")
    Recurso.objects.filter(exibir_jus=True).update(aponta_parada=True)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_recurso_aponta_parada"),
    ]

    operations = [
        migrations.RunPython(copiar_exibir_jus_para_aponta_parada, migrations.RunPython.noop),
    ]
