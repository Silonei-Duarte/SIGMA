from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("producao", "0016_justificativaparada"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="paradamaquina",
            options={
                "ordering": ["-inicio"],
                "verbose_name": "Parada de Máquina",
                "verbose_name_plural": "Paradas de Máquina",
                "default_permissions": (),
                "permissions": [("pode_alterar_paradas", "Pode Alterar Paradas")],
            },
        ),
    ]
