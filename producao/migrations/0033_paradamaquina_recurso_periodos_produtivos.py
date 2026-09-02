from django.db import migrations, models


def migrar_paradas_para_recurso_e_periodos(apps, schema_editor):
    ParadaMaquina = apps.get_model("producao", "ParadaMaquina")

    for parada in (
        ParadaMaquina.objects.select_related("troca_op_ativa__recurso").order_by("id").iterator()
    ):
        if parada.troca_op_ativa_id is None:
            raise RuntimeError(f"Parada {parada.pk} não possui período produtivo para migrar.")
        ParadaMaquina.objects.filter(pk=parada.pk).update(
            recurso_id=parada.troca_op_ativa.recurso_id,
        )
        parada.periodos_produtivos.add(parada.troca_op_ativa_id)

    sem_recurso = ParadaMaquina.objects.filter(recurso__isnull=True).values_list("id", flat=True)
    if sem_recurso.exists():
        raise RuntimeError(f"Paradas sem recurso após migração: {list(sem_recurso[:10])}")

    sem_periodo = ParadaMaquina.objects.filter(periodos_produtivos__isnull=True).values_list(
        "id", flat=True
    )
    if sem_periodo.exists():
        raise RuntimeError(f"Paradas sem período produtivo após migração: {list(sem_periodo[:10])}")

    abertas_duplicadas = (
        ParadaMaquina.objects.filter(fim__isnull=True)
        .values("recurso_id")
        .annotate(total=models.Count("id"))
        .filter(total__gt=1)
    )
    if abertas_duplicadas.exists():
        raise RuntimeError(
            "Há mais de uma parada aberta no mesmo recurso: "
            f"{list(abertas_duplicadas.values_list('recurso_id', flat=True))}"
        )


def restaurar_periodo_referencia(apps, schema_editor):
    ParadaMaquina = apps.get_model("producao", "ParadaMaquina")

    for parada in ParadaMaquina.objects.order_by("id").iterator():
        periodos_ids = list(parada.periodos_produtivos.values_list("id", flat=True))
        if len(periodos_ids) != 1:
            raise RuntimeError(
                f"Não é possível restaurar o FK da parada {parada.pk}: "
                f"ela possui {len(periodos_ids)} períodos produtivos vinculados."
            )
        ParadaMaquina.objects.filter(pk=parada.pk).update(
            troca_op_ativa_id=periodos_ids[0],
        )


class Migration(migrations.Migration):
    dependencies = [
        ("producao", "0032_normalizar_tempos_em_segundos"),
    ]

    operations = [
        migrations.AddField(
            model_name="paradamaquina",
            name="recurso",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="paradas_maquina",
                to="accounts.recurso",
                verbose_name="Recurso",
            ),
        ),
        migrations.AddField(
            model_name="paradamaquina",
            name="periodos_produtivos",
            field=models.ManyToManyField(
                related_name="paradas_periodos_produtivos_migracao",
                to="producao.logtrocaopativa",
                verbose_name="Períodos produtivos afetados",
            ),
        ),
        migrations.RunPython(migrar_paradas_para_recurso_e_periodos, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="paradamaquina",
            name="recurso",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="paradas_maquina",
                to="accounts.recurso",
                verbose_name="Recurso",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="paradamaquina",
            name="uniq_parada_aberta_troca",
        ),
        migrations.RemoveIndex(
            model_name="paradamaquina",
            name="idx_parada_troca_fim",
        ),
        migrations.AlterField(
            model_name="paradamaquina",
            name="troca_op_ativa",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="paradas",
                to="producao.logtrocaopativa",
                verbose_name="Troca de OP Ativa",
            ),
        ),
        migrations.RunPython(migrations.RunPython.noop, restaurar_periodo_referencia),
        migrations.RemoveField(
            model_name="paradamaquina",
            name="troca_op_ativa",
        ),
        migrations.AlterField(
            model_name="paradamaquina",
            name="periodos_produtivos",
            field=models.ManyToManyField(
                related_name="paradas",
                to="producao.logtrocaopativa",
                verbose_name="Períodos produtivos afetados",
            ),
        ),
        migrations.AddIndex(
            model_name="paradamaquina",
            index=models.Index(fields=["recurso", "fim"], name="idx_parada_recurso_fim"),
        ),
        migrations.AddConstraint(
            model_name="paradamaquina",
            constraint=models.UniqueConstraint(
                condition=models.Q(("fim__isnull", True)),
                fields=("recurso",),
                name="uniq_parada_aberta_recurso",
            ),
        ),
    ]
