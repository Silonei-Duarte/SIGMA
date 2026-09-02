from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("producao", "0029_add_permissao_componentes_movimentar"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pacotetempoerp",
            name="status",
            field=models.SmallIntegerField(
                choices=[(0, "Pendente"), (1, "Enviado"), (2, "Erro"), (3, "Processando")],
                default=0,
                verbose_name="Status",
            ),
        ),
    ]
