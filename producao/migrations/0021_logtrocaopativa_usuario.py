import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("producao", "0020_adicionar_permissao_pode_apontar"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="logtrocaopativa",
            name="usuario",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="trocas_op_ativas_registradas",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Usuário",
            ),
        ),
    ]
