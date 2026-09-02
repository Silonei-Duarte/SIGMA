import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [("accounts", "0022_recurso_tempo_minimo_parada")]

    operations = [
        migrations.RunSQL(
            sql="CREATE SCHEMA IF NOT EXISTS telemetria",
            reverse_sql="DROP SCHEMA IF EXISTS telemetria CASCADE",
        ),
        migrations.CreateModel(
            name="ConfiguracaoColetaHTTP",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("url", models.URLField(max_length=500, verbose_name="URL HTTP")),
                ("coleta_ativa", models.BooleanField(default=True, verbose_name="Coleta ativa")),
                (
                    "timeout_segundos",
                    models.PositiveIntegerField(
                        default=10,
                        validators=[django.core.validators.MinValueValidator(1)],
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
                        validators=[django.core.validators.MinValueValidator(1)],
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
                (
                    "recurso",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="configuracao_coleta_http",
                        to="accounts.recurso",
                        verbose_name="Recurso",
                    ),
                ),
            ],
            options={
                "verbose_name": "Configuração HTTP de telemetria",
                "verbose_name_plural": "Configurações HTTP de telemetria",
                "db_table": 'telemetria"."configuracoes_http_recursos',
                "default_permissions": (),
            },
        ),
        migrations.CreateModel(
            name="Sensor",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "codigo",
                    models.SlugField(max_length=100, unique=True, verbose_name="Código fixo"),
                ),
                ("nome", models.CharField(max_length=200, verbose_name="Nome amigável")),
                (
                    "tipo_valor",
                    models.CharField(
                        choices=[
                            ("decimal", "Decimal"),
                            ("inteiro", "Inteiro"),
                            ("booleano", "Booleano"),
                            ("texto", "Texto"),
                        ],
                        max_length=10,
                        verbose_name="Tipo do valor",
                    ),
                ),
                ("unidade", models.CharField(blank=True, max_length=30, verbose_name="Unidade")),
                ("ativo", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Sensor",
                "verbose_name_plural": "Sensores",
                "db_table": 'telemetria"."sensores',
                "default_permissions": (),
                "ordering": ["codigo"],
            },
        ),
        migrations.CreateModel(
            name="SensorRecurso",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "posicao",
                    models.PositiveIntegerField(
                        validators=[django.core.validators.MinValueValidator(1)],
                        verbose_name="Posição na resposta HTTP",
                    ),
                ),
                (
                    "monitorar_variacao",
                    models.BooleanField(default=False, verbose_name="Monitorar variação"),
                ),
                (
                    "tipo_tolerancia",
                    models.CharField(
                        choices=[("absoluta", "Absoluta"), ("percentual", "Percentual")],
                        default="absoluta",
                        max_length=10,
                        verbose_name="Tipo de tolerância",
                    ),
                ),
                ("tolerancia", models.FloatField(default=0.0, verbose_name="Variação mínima")),
                (
                    "recurso",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sensores_telemetria",
                        to="accounts.recurso",
                        verbose_name="Recurso",
                    ),
                ),
                (
                    "sensor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="recursos",
                        to="telemetria.sensor",
                        verbose_name="Sensor",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sensor do recurso",
                "verbose_name_plural": "Sensores dos recursos",
                "db_table": 'telemetria"."sensores_recursos',
                "default_permissions": (),
                "ordering": ["recurso", "posicao"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("recurso", "sensor"), name="uq_tlm_sensor_recurso"
                    ),
                    models.UniqueConstraint(
                        fields=("recurso", "posicao"), name="uq_tlm_recurso_posicao"
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="LeituraTelemetria",
            fields=[
                (
                    "pk",
                    models.CompositePrimaryKey(
                        "recurso",
                        "coletado_em",
                        blank=True,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "coletado_em",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="Data/hora da coleta"
                    ),
                ),
                ("valores", models.JSONField(default=dict, verbose_name="Valores interpretados")),
                (
                    "recurso",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="leituras_telemetria",
                        to="accounts.recurso",
                        verbose_name="Recurso",
                    ),
                ),
            ],
            options={
                "verbose_name": "Leitura de telemetria",
                "verbose_name_plural": "Leituras de telemetria",
                "db_table": 'telemetria"."leituras',
                "default_permissions": (),
                "ordering": ["-coletado_em"],
                "indexes": [
                    models.Index(
                        fields=["recurso", "-coletado_em"], name="idx_tlm_leitura_rec_data"
                    )
                ],
            },
        ),
        migrations.RunSQL(
            sql="""
                CREATE EXTENSION IF NOT EXISTS timescaledb;
                SELECT create_hypertable(
                    'telemetria.leituras',
                    by_range('coletado_em'),
                    if_not_exists => TRUE,
                    create_default_indexes => FALSE
                );
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
