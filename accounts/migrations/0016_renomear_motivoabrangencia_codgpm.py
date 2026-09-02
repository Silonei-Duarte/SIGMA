from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0015_motivoabrangencia_codtpm"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="motivoabrangencia",
            name="uq_mot_abr_rec_emp_tpm_mtv",
        ),
        migrations.RenameField(
            model_name="motivoabrangencia",
            old_name="codtpm",
            new_name="codgpm",
        ),
        migrations.AddConstraint(
            model_name="motivoabrangencia",
            constraint=models.UniqueConstraint(
                fields=("recurso", "codemp", "codgpm", "codmtv"),
                name="uq_mot_abr_rec_emp_gpm_mtv",
            ),
        ),
    ]
