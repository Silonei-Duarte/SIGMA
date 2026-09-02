# A fila local foi substituída pela pendência transacional criada no ERP.
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("producao", "0046_pacotetempoerp_renumera_status_sem_erro"),
    ]

    operations = [
        migrations.DeleteModel(
            name="EstornoComponente",
        ),
    ]
