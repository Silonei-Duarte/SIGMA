from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0011_motivoabrangencia"),
    ]

    operations = [
        migrations.AlterField(
            model_name="motivoabrangencia",
            name="codmtv",
            field=models.CharField(max_length=4, verbose_name="Código do Motivo"),
        ),
    ]
