# Reenumeração do status de PacoteTempoERP para alinhar a fila às demais filas
# de integração: ERRO (2) deixa de existir como estado — falha de envio passa a
# voltar a PENDENTE (0), e a informação de erro vive só no campo `log`;
# PROCESSANDO muda de 3 para 2; ENVIADO (1) é renomeado INTEGRADO, sem mudar
# de valor.

from django.db import migrations, models


def renumerar_para_novo_esquema(apps, schema_editor):
    """Move dado antes do AlterField: ERRO antigo (2) vira PENDENTE (0) e só
    então PROCESSANDO antigo (3) ocupa o valor 2.

    A ordem importa: inverter os passes faria o 2->0 reclassificar como
    pendente um pacote que estava em processamento real.
    Update em batch: uma única instrução UPDATE por passe, sem carregar
    linhas em memória.
    """
    PacoteTempoERP = apps.get_model("producao", "PacoteTempoERP")
    PacoteTempoERP.objects.filter(status=2).update(status=0)
    PacoteTempoERP.objects.filter(status=3).update(status=2)


def renumerar_para_esquema_antigo(apps, schema_editor):
    """Reverso aproximado: devolve PROCESSANDO (2) para o valor antigo (3).

    Limitação conhecida: quem veio de ERRO antigo agora está em PENDENTE e não
    é distinguível de um pendente legítimo — a informação de "era erro" vive só
    no campo `log`. Esses registros permanecem em 0, que no esquema antigo
    também significa pendente/reenviável: nenhuma linha é apagada ou perdida.
    """
    PacoteTempoERP = apps.get_model("producao", "PacoteTempoERP")
    PacoteTempoERP.objects.filter(status=2).update(status=3)


class Migration(migrations.Migration):
    dependencies = [
        ("producao", "0045_remove_conciliacao_correcao_lote"),
    ]

    operations = [
        # Dado antes do esquema: evita janela em que a aplicação já migrada
        # interpretaria os números antigos com o significado novo.
        migrations.RunPython(
            renumerar_para_novo_esquema,
            renumerar_para_esquema_antigo,
            elidable=False,
        ),
        migrations.AlterField(
            model_name="pacotetempoerp",
            name="status",
            field=models.SmallIntegerField(
                choices=[(0, "Pendente"), (1, "Integrado"), (2, "Processando")],
                default=0,
                verbose_name="Status",
            ),
        ),
    ]
