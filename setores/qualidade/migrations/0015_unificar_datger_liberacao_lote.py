# Rename preserva o histórico de datager: Remove+Add descartaria a data de
# geração já registrada nas liberações de lote, usada pelo rastreamento público.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("qualidade", "0014_datger_filas_integracao"),
    ]

    operations = [
        migrations.RenameField(
            model_name="liberacaolote",
            old_name="datager",
            new_name="datger",
        ),
        migrations.AlterField(
            model_name="liberacaolote",
            name="datger",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Data/Hora Geração"),
        ),
    ]
