from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_paradamaquina_remove_estadorecurso_idx_estado_fim_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="paradamaquina",
            old_name="operador_atual",
            new_name="operador",
        ),
        migrations.RenameField(
            model_name="paradamaquina",
            old_name="motivo_registrado_em",
            new_name="hora_log",
        ),
        migrations.AlterField(
            model_name="paradamaquina",
            name="operador",
            field=models.CharField(blank=True, max_length=100, verbose_name="Operador"),
        ),
        migrations.AlterField(
            model_name="paradamaquina",
            name="hora_log",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Data/Hora Log"),
        ),
    ]
