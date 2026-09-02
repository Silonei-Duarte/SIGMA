from django.db import migrations, models


def preencher_data_hora_justificativas(apps, schema_editor):
    JustificativaParada = apps.get_model("producao", "JustificativaParada")

    for justificativa in JustificativaParada.objects.select_related("parada").iterator():
        justificativa.data_hora = justificativa.parada.data_hora
        justificativa.save(update_fields=["data_hora"])


class Migration(migrations.Migration):
    dependencies = [
        ("producao", "0017_alter_paradamaquina_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="justificativaparada",
            name="data_hora",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Data/Hora do Log"),
        ),
        migrations.RunPython(preencher_data_hora_justificativas, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="paradamaquina",
            name="log",
        ),
    ]
