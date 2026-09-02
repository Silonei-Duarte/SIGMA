from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("telemetria", "0002_fontes_json")]

    operations = [
        migrations.AlterModelOptions(
            name="fontecoletahttp",
            options={
                "db_table": 'telemetria"."fontes_coleta_http',
                "default_permissions": (),
                "verbose_name": "Fonte HTTP de telemetria",
                "verbose_name_plural": "Fontes HTTP de telemetria",
            },
        ),
    ]
