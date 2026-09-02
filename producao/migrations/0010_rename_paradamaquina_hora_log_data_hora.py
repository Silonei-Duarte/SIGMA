from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("producao", "0009_remover_paradamaquina_data_hora")]

    operations = [
        migrations.RenameField(
            model_name="paradamaquina",
            old_name="hora_log",
            new_name="data_hora",
        ),
        migrations.AlterField(
            model_name="paradamaquina",
            name="data_hora",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Data/Hora"),
        ),
    ]
