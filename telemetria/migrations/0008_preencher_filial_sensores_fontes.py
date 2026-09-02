from django.db import migrations


def preencher_filial(apps, schema_editor):
    """Deriva a filial de sensores e fontes a partir dos vínculos existentes.

    Sensor → primeiro vínculo SensorRecurso (ordem por id) → Recurso →
    centro → setor → departamento → filial. Fonte → primeiro sensor já
    resolvido (ordem por id). Sem vínculo ou sem filial derivável, fica NULL:
    staff continua vendo, não-staff não (política de escopo).

    Limitação conhecida: um sensor vinculado a recursos de filiais diferentes
    recebe a filial do primeiro vínculo — o schema atual não registra filial
    no vínculo e não há critério objetivo para escolher outra.
    """
    Sensor = apps.get_model("telemetria", "Sensor")
    FonteColetaHTTP = apps.get_model("telemetria", "FonteColetaHTTP")
    SensorRecurso = apps.get_model("telemetria", "SensorRecurso")

    filial_por_sensor = {}
    vinculos = (
        SensorRecurso.objects.exclude(
            recurso__centro_recurso__setor__departamento__filial__isnull=True
        )
        .order_by("id")
        .values("sensor_id", "recurso__centro_recurso__setor__departamento__filial_id")
    )
    for vinculo in vinculos:
        filial_por_sensor.setdefault(
            vinculo["sensor_id"],
            vinculo["recurso__centro_recurso__setor__departamento__filial_id"],
        )

    for sensor_id, filial_id in filial_por_sensor.items():
        Sensor.objects.filter(pk=sensor_id).update(filial_id=filial_id)

    filial_por_fonte = {}
    for sensor in (
        Sensor.objects.exclude(filial__isnull=True).order_by("id").values("fonte_id", "filial_id")
    ):
        filial_por_fonte.setdefault(sensor["fonte_id"], sensor["filial_id"])

    for fonte_id, filial_id in filial_por_fonte.items():
        FonteColetaHTTP.objects.filter(pk=fonte_id).update(filial_id=filial_id)


def reverter_preenchimento(apps, schema_editor):
    """Limpa as filiais derivadas (inclusive as atribuídas depois da
    migration — reversão de migration não preserva dados posteriores)."""
    Sensor = apps.get_model("telemetria", "Sensor")
    FonteColetaHTTP = apps.get_model("telemetria", "FonteColetaHTTP")
    Sensor.objects.update(filial=None)
    FonteColetaHTTP.objects.update(filial=None)


class Migration(migrations.Migration):
    dependencies = [
        ("telemetria", "0007_permissoestelemetria_fontecoletahttp_filial_and_more"),
    ]

    operations = [
        migrations.RunPython(preencher_filial, reverter_preenchimento),
    ]
