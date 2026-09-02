import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_mover_logtrocaopativa_para_producao"),
        ("producao", "0010_rename_paradamaquina_hora_log_data_hora"),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE IF EXISTS public.logs_troca_op_ativa SET SCHEMA producao",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="LogTrocaOPAtiva",
                    fields=[
                        ("id", models.BigAutoField(primary_key=True, serialize=False)),
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
                        ("horario_troca", models.DateTimeField(verbose_name="Horário da Troca")),
                        (
                            "horario_saida",
                            models.DateTimeField(
                                blank=True, null=True, verbose_name="Horário de Saída"
                            ),
                        ),
                        (
                            "id_operador",
                            models.IntegerField(blank=True, null=True, verbose_name="ID Operador"),
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
                                on_delete=django.db.models.deletion.PROTECT,
                                related_name="logs_troca_op_ativa",
                                to="accounts.recurso",
                                verbose_name="Recurso",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Log de Troca de OP Ativa",
                        "verbose_name_plural": "Logs de Troca de OP Ativa",
                        "db_table": 'producao"."logs_troca_op_ativa',
                        "ordering": ["-horario_troca"],
                        "default_permissions": (),
                    },
                ),
            ],
        ),
    ]
