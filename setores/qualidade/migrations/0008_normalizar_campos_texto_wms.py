from django.db import migrations, models


def normalizar_campos_texto_wms(apps, schema_editor):
    WMSIntegracaoOP = apps.get_model("qualidade", "WMS_IntegraçãoOP")
    WMSIntegracaoOP.objects.filter(palete__isnull=True).update(palete="")
    WMSIntegracaoOP.objects.filter(local__isnull=True).update(local="")
    WMSIntegracaoOP.objects.filter(codpro__isnull=True).update(codpro="")
    WMSIntegracaoOP.objects.filter(log__isnull=True).update(log="")


def reverter_normalizacao_campos_texto_wms(apps, schema_editor):
    # Os valores NULL anteriores não podem ser reconstruídos com segurança.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("qualidade", "0007_renomear_permissao_area_vermelha"),
    ]

    operations = [
        migrations.RunPython(
            normalizar_campos_texto_wms,
            reverter_normalizacao_campos_texto_wms,
        ),
        migrations.AlterField(
            model_name="wms_integraçãoop",
            name="codpro",
            field=models.CharField(
                blank=True, default="", max_length=50, verbose_name="Código do Produto"
            ),
        ),
        migrations.AlterField(
            model_name="wms_integraçãoop",
            name="local",
            field=models.CharField(blank=True, default="", max_length=50, verbose_name="Local WMS"),
        ),
        migrations.AlterField(
            model_name="wms_integraçãoop",
            name="log",
            field=models.TextField(blank=True, default="", verbose_name="Log"),
        ),
        migrations.AlterField(
            model_name="wms_integraçãoop",
            name="palete",
            field=models.CharField(blank=True, default="", max_length=50, verbose_name="Palete"),
        ),
    ]
