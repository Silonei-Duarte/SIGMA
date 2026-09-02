from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("producao", "0003_apontamento_usuario_apontamentocomponente_usuario"),
    ]

    operations = [
        migrations.RenameField(
            model_name="sequenciamento",
            old_name="seqroteiro",
            new_name="seqrot",
        ),
    ]
