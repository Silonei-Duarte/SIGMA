from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_remove_logtrocaopativa_codigo_barra_op_and_more"),
        ("producao", "0006_remove_logparada_op_ativa"),
    ]

    operations = [
        migrations.DeleteModel(name="LogParada"),
    ]
