from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0019_recurso_tempo_parada_aut_segundos"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                UPDATE public.recursos
                SET tempo_parada_aut = INTERVAL '1 second'
                WHERE tempo_parada_aut = INTERVAL '0 second';
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
