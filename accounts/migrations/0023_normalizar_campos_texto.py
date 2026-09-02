from django.db import migrations, models

TEXT_FIELDS = {
    "CustomUser": ("paginicial",),
    "CalendarioEvento": ("observacao",),
    "CentroRecurso": ("codigo_integrador",),
    "ParametrosCentroRecurso": (
        "deposito_apontamento_erp",
        "deposito_armazenamento_erp",
        "deposito_armazenamento_wms",
        "deposito_area_vermelha_erp",
        "deposito_area_vermelha_wms",
        "produto_refugo",
        "derivacao_refugo",
    ),
}


def preencher_nulos_com_vazio(apps, schema_editor):
    for model_name, field_names in TEXT_FIELDS.items():
        model = apps.get_model("accounts", model_name)
        for field_name in field_names:
            model.objects.filter(**{f"{field_name}__isnull": True}).update(**{field_name: ""})


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0022_recurso_tempo_minimo_parada"),
    ]

    operations = [
        migrations.RunPython(preencher_nulos_com_vazio, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="customuser",
            name="paginicial",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AlterField(
            model_name="calendarioevento",
            name="observacao",
            field=models.CharField(
                blank=True, default="", max_length=200, verbose_name="Observação"
            ),
        ),
        migrations.AlterField(
            model_name="centrorecurso",
            name="codigo_integrador",
            field=models.CharField(
                blank=True, default="", max_length=100, verbose_name="Código Integrador"
            ),
        ),
        migrations.AlterField(
            model_name="parametroscentrorecurso",
            name="deposito_apontamento_erp",
            field=models.CharField(
                blank=True,
                default="",
                max_length=50,
                verbose_name="Depósito de consulta apontamento ERP",
            ),
        ),
        migrations.AlterField(
            model_name="parametroscentrorecurso",
            name="deposito_armazenamento_erp",
            field=models.CharField(
                blank=True,
                default="",
                max_length=50,
                verbose_name="Depósito de armazenamento ERP",
            ),
        ),
        migrations.AlterField(
            model_name="parametroscentrorecurso",
            name="deposito_armazenamento_wms",
            field=models.CharField(
                blank=True, default="", max_length=50, verbose_name="Local de liberação WMS"
            ),
        ),
        migrations.AlterField(
            model_name="parametroscentrorecurso",
            name="deposito_area_vermelha_erp",
            field=models.CharField(
                blank=True,
                default="",
                max_length=50,
                verbose_name="Depósito área vermelha ERP",
            ),
        ),
        migrations.AlterField(
            model_name="parametroscentrorecurso",
            name="deposito_area_vermelha_wms",
            field=models.CharField(
                blank=True, default="", max_length=50, verbose_name="Local área vermelha WMS"
            ),
        ),
        migrations.AlterField(
            model_name="parametroscentrorecurso",
            name="produto_refugo",
            field=models.CharField(
                blank=True, default="", max_length=50, verbose_name="Produto refugo"
            ),
        ),
        migrations.AlterField(
            model_name="parametroscentrorecurso",
            name="derivacao_refugo",
            field=models.CharField(
                blank=True, default="", max_length=50, verbose_name="Derivação refugo"
            ),
        ),
    ]
