from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0018_dispositivonotificacao"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE public.recursos
                ALTER COLUMN tempo_parada_aut TYPE interval(0)
                USING date_trunc('second', tempo_parada_aut);
            """,
            reverse_sql="""
                ALTER TABLE public.recursos
                ALTER COLUMN tempo_parada_aut TYPE interval(6)
                USING tempo_parada_aut;
            """,
        ),
    ]
