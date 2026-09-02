from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0012_alter_motivoabrangencia_codmtv"),
    ]

    operations = [
        migrations.AddField(
            model_name="motivoabrangencia",
            name="codmpm",
            field=models.CharField(
                default="", max_length=4, verbose_name="Código do Motivo de Parada"
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="motivoabrangencia",
            name="codmtv",
            field=models.CharField(max_length=4, verbose_name="Código ERP do Motivo"),
        ),
        migrations.AlterField(
            model_name="motivoabrangencia",
            name="grupo",
            field=models.CharField(max_length=20, verbose_name="Código do Tipo de Parada"),
        ),
        migrations.RemoveConstraint(
            model_name="motivoabrangencia",
            name="uq_mot_abr_recurso_emp_mtv",
        ),
        migrations.AddConstraint(
            model_name="motivoabrangencia",
            constraint=models.UniqueConstraint(
                fields=("recurso", "codemp", "codmtv", "codmpm"), name="uq_mot_abr_rec_emp_mtv_mpm"
            ),
        ),
        migrations.AlterModelOptions(
            name="motivoabrangencia",
            options={
                "default_permissions": (),
                "ordering": ["codemp", "grupo", "codmtv", "codmpm"],
                "verbose_name": "Motivo de Abrangência",
                "verbose_name_plural": "Motivos de Abrangência",
            },
        ),
    ]
