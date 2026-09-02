import django.db.models.deletion
from django.core.validators import MinValueValidator
from django.db import migrations, models


def limpar_telemetria_legada(apps, schema_editor):
    Configuracao = apps.get_model("telemetria", "ConfiguracaoColetaHTTP")
    Sensor = apps.get_model("telemetria", "Sensor")
    SensorRecurso = apps.get_model("telemetria", "SensorRecurso")
    Leitura = apps.get_model("telemetria", "LeituraTelemetria")
    RegraParada = apps.get_model("producao", "RegraParadaRecurso")

    # A mudança de contrato foi aprovada como reinicialização: dados posicionais
    # não podem ser interpretados com segurança no payload JSON por fonte.
    RegraParada.objects.all().delete()
    Leitura.objects.all().delete()
    SensorRecurso.objects.all().delete()
    Sensor.objects.all().delete()
    Configuracao.objects.all().delete()


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("telemetria", "0001_initial"),
        ("producao", "0031_regraparadarecurso"),
    ]
    operations = [
        migrations.CreateModel(
            name="FonteColetaHTTP",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("url", models.URLField(max_length=500, unique=True, verbose_name="URL HTTP")),
                ("coleta_ativa", models.BooleanField(default=True, verbose_name="Coleta ativa")),
                (
                    "timeout_segundos",
                    models.PositiveIntegerField(
                        default=10,
                        validators=[MinValueValidator(1)],
                        verbose_name="Timeout (segundos)",
                    ),
                ),
                (
                    "pausa_sucesso_segundos",
                    models.PositiveIntegerField(
                        default=2, verbose_name="Pausa após sucesso (segundos)"
                    ),
                ),
                (
                    "backoff_erro_segundos",
                    models.PositiveIntegerField(
                        default=10,
                        validators=[MinValueValidator(1)],
                        verbose_name="Espera após erro (segundos)",
                    ),
                ),
                ("log", models.TextField(blank=True, verbose_name="Log da última coleta")),
                (
                    "ultima_coleta_em",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Data/hora do último erro"
                    ),
                ),
            ],
            options={
                "db_table": 'telemetria"."fontes_coleta_http',
                "default_permissions": (),
                "verbose_name": "Fonte HTTP de telemetria",
                "verbose_name_plural": "Fontes HTTP de telemetria",
            },
        ),
        migrations.AddField(
            model_name="sensor",
            name="fonte",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sensores",
                to="telemetria.fontecoletahttp",
            ),
        ),
        migrations.AddField(
            model_name="sensor",
            name="chave_origem",
            field=models.CharField(default="", max_length=200),
        ),
        migrations.RunPython(limpar_telemetria_legada, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="sensorrecurso", name="uq_tlm_recurso_posicao"),
        migrations.RemoveField(model_name="sensorrecurso", name="posicao"),
        migrations.RemoveField(model_name="configuracaocoletahttp", name="recurso"),
        migrations.DeleteModel(name="ConfiguracaoColetaHTTP"),
        migrations.AlterField(
            model_name="sensor",
            name="fonte",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sensores",
                to="telemetria.fontecoletahttp",
                verbose_name="Fonte de coleta",
            ),
        ),
        migrations.AlterField(
            model_name="sensor",
            name="chave_origem",
            field=models.CharField(max_length=200, verbose_name="Chave na resposta JSON"),
        ),
        migrations.AlterModelOptions(
            name="sensorrecurso",
            options={
                "default_permissions": (),
                "ordering": ["recurso", "sensor__codigo"],
                "verbose_name": "Sensor do recurso",
                "verbose_name_plural": "Sensores dos recursos",
            },
        ),
    ]
