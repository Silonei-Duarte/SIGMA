from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("telemetria", "0004_sensor_chave_unica")]

    operations = [
        migrations.AlterField(
            model_name="fontecoletahttp",
            name="ultima_coleta_em",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Data/hora da última coleta"
            ),
        ),
        migrations.AlterField(
            model_name="sensor",
            name="chave_origem",
            field=models.CharField(max_length=200, verbose_name="Chave na resposta JSON"),
        ),
        migrations.RunSQL(
            sql=(
                'ALTER TABLE "telemetria"."sensores" '
                'DROP CONSTRAINT IF EXISTS "sensores_chave_origem_76c1d023_uniq"'
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddConstraint(
            model_name="sensor",
            constraint=models.UniqueConstraint(
                fields=("fonte", "chave_origem"), name="uq_tlm_sensor_fonte_chave"
            ),
        ),
    ]
