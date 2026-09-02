"""Move o status LOCAL de LiberacaoLote do valor 3 para o 4.

Decisão do sênior: o valor 3 volta a ficar livre para o esquema numérico
compartilhado das filas de integração; LOCAL passa a ocupar o 4. A tabela
`qualidade.liberacao_lote` está vazia em produção — a movimentação de dados
existe para qualquer ambiente que ainda tenha registro gravado no valor antigo.
"""

from django.db import migrations, models


def mover_local_para_quatro(apps, schema_editor):
    """Nenhum registro pode sobreviver ao valor 3 depois desta migração."""
    liberacao_lote = apps.get_model("qualidade", "LiberacaoLote")
    liberacao_lote.objects.filter(status=3).update(status=4)


def mover_local_para_tres(apps, schema_editor):
    """Reverso da renumeração: devolve os registros locais ao valor antigo."""
    liberacao_lote = apps.get_model("qualidade", "LiberacaoLote")
    liberacao_lote.objects.filter(status=4).update(status=3)


class Migration(migrations.Migration):
    dependencies = [
        ("qualidade", "0009_alter_wms_integracaoop_status_choices"),
    ]

    operations = [
        # Os dados migram ANTES do AlterField para o novo catálogo encontrar
        # somente valores válidos.
        migrations.RunPython(
            mover_local_para_quatro,
            mover_local_para_tres,
            elidable=False,
        ),
        migrations.AlterField(
            model_name="liberacaolote",
            name="status",
            field=models.IntegerField(
                choices=[
                    (0, "Não integrado"),
                    (1, "Integrado"),
                    (2, "Processando"),
                    (4, "Local (sem integração)"),
                ],
                default=0,
                verbose_name="Status",
            ),
        ),
    ]
