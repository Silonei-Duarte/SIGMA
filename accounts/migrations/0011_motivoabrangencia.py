import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_mover_logtrocaopativa_para_producao"),
    ]

    operations = [
        migrations.CreateModel(
            name="MotivoAbrangencia",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "recurso",
                    models.ForeignKey(
                        db_column="id_recurso",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="motivos_abrangencia",
                        to="accounts.recurso",
                        verbose_name="Recurso",
                    ),
                ),
                ("codemp", models.IntegerField(verbose_name="Código da Empresa")),
                ("codmtv", models.CharField(max_length=20, verbose_name="Código do Motivo")),
                (
                    "grupo",
                    models.CharField(
                        choices=[
                            ("SETUP", "SETUP"),
                            ("OPERACIONAL", "OPERACIONAL"),
                            ("PROGRAMADO", "PROGRAMADO"),
                            ("MANUTENÇÃO", "MANUTENÇÃO"),
                        ],
                        max_length=20,
                        verbose_name="Grupo",
                    ),
                ),
            ],
            options={
                "verbose_name": "Motivo de Abrangência",
                "verbose_name_plural": "Motivos de Abrangência",
                "ordering": ["codemp", "codmtv"],
                "db_table": "motivos_abrangencia",
                "default_permissions": (),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("recurso", "codemp", "codmtv"), name="uq_mot_abr_recurso_emp_mtv"
                    )
                ],
            },
        ),
    ]
