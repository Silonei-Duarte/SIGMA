from django.db import migrations, models


def migrar_referencias_para_chave(apps, _schema_editor):
    Sensor = apps.get_model("telemetria", "Sensor")
    LeituraTelemetria = apps.get_model("telemetria", "LeituraTelemetria")
    RegraParadaRecurso = apps.get_model("producao", "RegraParadaRecurso")
    chaves = dict(Sensor.objects.values_list("codigo", "chave_origem"))

    for leitura in LeituraTelemetria.objects.all().iterator():
        valores = {chaves.get(chave, chave): valor for chave, valor in leitura.valores.items()}
        if valores != leitura.valores:
            leitura.valores = valores
            leitura.save(update_fields=["valores"])

    def substituir_condicoes(no):
        if isinstance(no, list):
            return [substituir_condicoes(item) for item in no]
        if not isinstance(no, dict):
            return no
        novo = {chave: substituir_condicoes(valor) for chave, valor in no.items()}
        if novo.get("tipo") == "condicao":
            novo["sensor"] = chaves.get(novo.get("sensor"), novo.get("sensor"))
        return novo

    for regra in RegraParadaRecurso.objects.all().iterator():
        nova_regra = substituir_condicoes(regra.regra)
        if nova_regra != regra.regra:
            regra.regra = nova_regra
            regra.save(update_fields=["regra"])


class Migration(migrations.Migration):
    dependencies = [
        ("producao", "0045_remove_conciliacao_correcao_lote"),
        ("telemetria", "0003_fonte_options"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sensor",
            name="chave_origem",
            field=models.CharField(
                max_length=200, unique=True, verbose_name="Chave na resposta JSON"
            ),
        ),
        migrations.RunPython(migrar_referencias_para_chave, migrations.RunPython.noop),
        migrations.RemoveField(model_name="sensor", name="codigo"),
        migrations.AlterModelOptions(
            name="sensor",
            options={
                "db_table": 'telemetria"."sensores',
                "default_permissions": (),
                "ordering": ["chave_origem"],
                "verbose_name": "Sensor",
                "verbose_name_plural": "Sensores",
            },
        ),
        migrations.AlterModelOptions(
            name="sensorrecurso",
            options={
                "db_table": 'telemetria"."sensores_recursos',
                "default_permissions": (),
                "ordering": ["recurso", "sensor__chave_origem"],
                "verbose_name": "Sensor do recurso",
                "verbose_name_plural": "Sensores dos recursos",
            },
        ),
    ]
