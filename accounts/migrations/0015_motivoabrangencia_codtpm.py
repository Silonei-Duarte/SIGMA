from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0014_remove_motivoabrangencia_grupo"),
    ]

    operations = [
        migrations.AddField(
            model_name="motivoabrangencia",
            name="codtpm",
            field=models.IntegerField(default=0, verbose_name="Código do Tipo de Parada"),
            preserve_default=False,
        ),
        migrations.RemoveConstraint(
            model_name="motivoabrangencia",
            name="uq_mot_abr_rec_emp_mtv_mpm",
        ),
        migrations.RemoveField(
            model_name="motivoabrangencia",
            name="codmpm",
        ),
        migrations.AddConstraint(
            model_name="motivoabrangencia",
            constraint=models.UniqueConstraint(
                fields=("recurso", "codemp", "codtpm", "codmtv"),
                name="uq_mot_abr_rec_emp_tpm_mtv",
            ),
        ),
        migrations.AlterModelOptions(
            name="motivoabrangencia",
            options={
                "default_permissions": (),
                "ordering": ["codemp", "codtpm", "codmtv"],
                "verbose_name": "Motivo de Abrangência",
                "verbose_name_plural": "Motivos de Abrangência",
            },
        ),
    ]
