import django.db.models.deletion
from django.db import migrations, models


def vincular_paradas(apps, schema_editor):
    ParadaMaquina = apps.get_model("producao", "ParadaMaquina")
    LogTrocaOPAtiva = apps.get_model("producao", "LogTrocaOPAtiva")

    for parada in ParadaMaquina.objects.all().iterator():
        troca = (
            LogTrocaOPAtiva.objects.filter(
                recurso_id=parada.recurso_id,
                origem=parada.origem,
                op=parada.op,
                estagio=parada.estagio,
                seqrot=parada.seqrot,
                horario_troca__lte=parada.inicio,
            )
            .order_by("-horario_troca", "-id")
            .first()
        )
        if troca is None:
            troca = (
                LogTrocaOPAtiva.objects.filter(
                    models.Q(horario_saida__isnull=True)
                    | models.Q(horario_saida__gte=parada.inicio),
                    recurso_id=parada.recurso_id,
                    horario_troca__lte=parada.inicio,
                )
                .order_by("-horario_troca", "-id")
                .first()
            )
        if troca is None:
            raise RuntimeError(f"Parada {parada.id} não pôde ser vinculada a uma troca de OP.")
        parada.troca_op_ativa_id = troca.id
        parada.save(update_fields=["troca_op_ativa"])


class Migration(migrations.Migration):
    dependencies = [("producao", "0012_reordenar_logtrocaopativa")]

    operations = [
        migrations.AddField(
            model_name="paradamaquina",
            name="troca_op_ativa",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="paradas",
                to="producao.logtrocaopativa",
                verbose_name="Troca de OP Ativa",
            ),
        ),
        migrations.RunPython(vincular_paradas, migrations.RunPython.noop),
        migrations.RemoveField(model_name="paradamaquina", name="origem"),
        migrations.RemoveField(model_name="paradamaquina", name="op"),
        migrations.RemoveField(model_name="paradamaquina", name="estagio"),
        migrations.RemoveField(model_name="paradamaquina", name="seqrot"),
        migrations.AlterField(
            model_name="paradamaquina",
            name="troca_op_ativa",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="paradas",
                to="producao.logtrocaopativa",
                verbose_name="Troca de OP Ativa",
            ),
        ),
    ]
