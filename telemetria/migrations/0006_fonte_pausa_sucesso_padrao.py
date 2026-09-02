from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("telemetria", "0005_sensor_chave_por_fonte")]

    operations = [
        migrations.AlterField(
            model_name="fontecoletahttp",
            name="pausa_sucesso_segundos",
            field=models.PositiveIntegerField(
                default=10, verbose_name="Pausa após sucesso (segundos)"
            ),
        ),
    ]
