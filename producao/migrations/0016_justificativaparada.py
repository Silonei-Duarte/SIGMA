import django.db.models.deletion
from django.db import migrations, models


def migrar_motivos_para_justificativas(apps, schema_editor):
    ParadaMaquina = apps.get_model("producao", "ParadaMaquina")
    JustificativaParada = apps.get_model("producao", "JustificativaParada")

    for parada in ParadaMaquina.objects.exclude(motivo="").iterator():
        tempo = parada.fim - parada.inicio if parada.fim else None
        JustificativaParada.objects.get_or_create(
            parada_id=parada.id,
            sequencia=1,
            defaults={
                "motivo": parada.motivo,
                "parcial": parada.inicio,
                "tempo": tempo,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("producao", "0015_remover_paradamaquina_recurso"),
    ]

    operations = [
        migrations.CreateModel(
            name="JustificativaParada",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("sequencia", models.PositiveIntegerField(verbose_name="Sequência")),
                ("motivo", models.CharField(max_length=4, verbose_name="Motivo ERP")),
                ("parcial", models.DateTimeField(verbose_name="Início Parcial")),
                ("tempo", models.DurationField(blank=True, null=True, verbose_name="Tempo")),
                (
                    "parada",
                    models.ForeignKey(
                        db_column="id_parada",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="justificativas",
                        to="producao.paradamaquina",
                        verbose_name="Parada",
                    ),
                ),
            ],
            options={
                "verbose_name": "Justificativa de Parada",
                "verbose_name_plural": "Justificativas de Paradas",
                "db_table": 'producao"."justificativas_paradas',
                "ordering": ["sequencia"],
                "default_permissions": (),
            },
        ),
        migrations.AddConstraint(
            model_name="justificativaparada",
            constraint=models.UniqueConstraint(
                fields=("parada", "sequencia"), name="uq_just_parada_sequencia"
            ),
        ),
        migrations.AddConstraint(
            model_name="justificativaparada",
            constraint=models.UniqueConstraint(
                condition=models.Q(("tempo__isnull", True)),
                fields=("parada",),
                name="uq_just_parada_aberta",
            ),
        ),
        migrations.RunPython(migrar_motivos_para_justificativas, migrations.RunPython.noop),
        migrations.RemoveField(model_name="paradamaquina", name="motivo"),
    ]
