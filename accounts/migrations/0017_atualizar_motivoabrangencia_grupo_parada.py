from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0016_renomear_motivoabrangencia_codgpm"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="motivoabrangencia",
            options={
                "default_permissions": (),
                "ordering": ["codemp", "codgpm", "codmtv"],
                "verbose_name": "Motivo de Abrangência",
                "verbose_name_plural": "Motivos de Abrangência",
            },
        ),
        migrations.AlterField(
            model_name="motivoabrangencia",
            name="codgpm",
            field=models.IntegerField(verbose_name="Código do Grupo de Parada"),
        ),
    ]
