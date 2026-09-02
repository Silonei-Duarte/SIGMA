from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_remove_logtrocaopativa_codigo_barra_op_and_more"),
        ("producao", "0007_remover_logparada"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="ParadaMaquina"),
            ],
        ),
    ]
