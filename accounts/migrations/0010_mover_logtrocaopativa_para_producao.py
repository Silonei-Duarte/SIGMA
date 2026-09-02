from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_mover_paradamaquina_para_producao"),
        ("producao", "0010_rename_paradamaquina_hora_log_data_hora"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[migrations.DeleteModel(name="LogTrocaOPAtiva")],
        ),
    ]
