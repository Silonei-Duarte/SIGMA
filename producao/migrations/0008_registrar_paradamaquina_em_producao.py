import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_mover_paradamaquina_para_producao"),
        ("producao", "0007_remover_logparada"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="ParadaMaquina",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        ("inicio", models.DateTimeField(verbose_name="Data/Hora Início")),
                        (
                            "fim",
                            models.DateTimeField(
                                blank=True, null=True, verbose_name="Data/Hora Fim"
                            ),
                        ),
                        (
                            "origem",
                            models.CharField(
                                blank=True, max_length=10, null=True, verbose_name="Origem"
                            ),
                        ),
                        (
                            "op",
                            models.IntegerField(
                                blank=True, null=True, verbose_name="Ordem de Produção"
                            ),
                        ),
                        (
                            "estagio",
                            models.IntegerField(blank=True, null=True, verbose_name="Estágio"),
                        ),
                        (
                            "seqrot",
                            models.IntegerField(blank=True, null=True, verbose_name="Seq. Roteiro"),
                        ),
                        (
                            "operador",
                            models.CharField(blank=True, max_length=100, verbose_name="Operador"),
                        ),
                        (
                            "motivo",
                            models.CharField(blank=True, max_length=255, verbose_name="Motivo"),
                        ),
                        (
                            "hora_log",
                            models.DateTimeField(
                                blank=True, null=True, verbose_name="Data/Hora Log"
                            ),
                        ),
                        (
                            "tipo",
                            models.SmallIntegerField(
                                choices=[(1, "Manual"), (2, "Sinal")], verbose_name="Tipo"
                            ),
                        ),
                        ("status", models.IntegerField(default=0, verbose_name="Status")),
                        ("log", models.TextField(blank=True, null=True, verbose_name="Log")),
                        (
                            "data_hora",
                            models.DateTimeField(auto_now=True, verbose_name="Data/Hora"),
                        ),
                        (
                            "recurso",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="paradas_maquina",
                                to="accounts.recurso",
                            ),
                        ),
                        (
                            "usuario",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="paradas_maquina_registradas",
                                to=settings.AUTH_USER_MODEL,
                                verbose_name="Usuário",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Parada de Máquina",
                        "verbose_name_plural": "Paradas de Máquina",
                        "db_table": 'producao"."paradas_maquina',
                        "ordering": ["-inicio"],
                        "default_permissions": (),
                        "indexes": [
                            models.Index(fields=["recurso", "fim"], name="idx_parada_recurso_fim"),
                            models.Index(fields=["tipo", "fim"], name="idx_parada_tipo_fim"),
                        ],
                        "constraints": [
                            models.UniqueConstraint(
                                condition=models.Q(("fim__isnull", True)),
                                fields=("recurso",),
                                name="uniq_parada_aberta_recurso",
                            ),
                        ],
                    },
                ),
            ],
        ),
    ]
