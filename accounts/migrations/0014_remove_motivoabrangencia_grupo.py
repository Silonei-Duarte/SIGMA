from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0013_motivoabrangencia_codmpm_grupo_erp"),
    ]

    operations = [
        migrations.AlterField(
            model_name="motivoabrangencia",
            name="codmpm",
            field=models.CharField(max_length=4, verbose_name="Código do Subnível do Motivo"),
        ),
        migrations.RemoveField(
            model_name="motivoabrangencia",
            name="grupo",
        ),
        migrations.AlterModelOptions(
            name="motivoabrangencia",
            options={
                "default_permissions": (),
                "ordering": ["codemp", "codmtv", "codmpm"],
                "verbose_name": "Motivo de Abrangência",
                "verbose_name_plural": "Motivos de Abrangência",
            },
        ),
    ]
