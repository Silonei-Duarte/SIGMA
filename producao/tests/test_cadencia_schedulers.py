"""Trava as cadências (`intervalo_segundos`) declaradas pelos schedulers do SIGMA.

Complementa a regra 21 da skill `integracoes` ("Cadência é catálogo com a conta
de carga"): mudar a cadência de um worker que fala com sistema de fora exige
escrever a conta de carga nova — quantas chamadas por hora/dia o novo intervalo
representa ao sistema externo e por que o volume é aceitável — **antes** de
mexer no valor. Este teste falha quando o valor muda, e a mensagem aponta para
a conta de carga que precisa ser revisada.

Catálogo travado (toda classe que declara `intervalo_segundos` hoje):

- `EnviaPendenciasScheduler` (producao/services/envia_pendencias.py): 300s
- `SincronizaOpsEncerradasScheduler` (producao/services/sincroniza_ops_encerradas.py): 300s
- `ImportaPaleteScheduler` (producao/services/importa_palete.py): 3600s
- `ConsolidaTemposERPScheduler` (producao/services/consolida_tempos_erp.py): 21600s
- `OEEPlanejadoScheduler` (accounts/services/oee_planejado_service.py): 600s

Fora do catálogo, de propósito:

- `RelatorioFalhasEmailWorker` não tem cadência própria: roda dentro do ciclo
  do `EnviaPendenciasScheduler` e mantém `INTERVALO_SEGUNDOS` como espelho
  (comentário no próprio arquivo). O teste prova que o espelho não divergiu —
  regra 19 ("nenhum número duplicado em config") ainda não é atendida no
  código, então a igualdade é a guarda enquanto a duplicação existir.
- `CoordenadorColetaTelemetria` (telemetria) registra intervalo `None`: a
  cadência da coleta é por fonte, vinda do banco, não de atributo de classe.
- Workers de fila (`producao/views/logs_*.py`, `wms_views`, `consulta_lote`,
  `envia_tempos_erp`) rodam dentro do ciclo do `EnviaPendenciasScheduler` e não
  declaram cadência própria.
"""

from django.test import SimpleTestCase

from accounts.services.oee_planejado_service import OEEPlanejadoScheduler
from producao.services.consolida_tempos_erp import ConsolidaTemposERPScheduler
from producao.services.envia_pendencias import EnviaPendenciasScheduler
from producao.services.importa_palete import ImportaPaleteScheduler
from producao.services.relatorio_falhas_email import RelatorioFalhasEmailWorker
from producao.services.sincroniza_ops_encerradas import SincronizaOpsEncerradasScheduler

REGRA_21_CADENCIA = (
    "Regra 21 da skill 'integracoes' (.claude/skills/integracoes/SKILL.md): "
    "'Cadência é catálogo com a conta de carga'. Antes de trocar o valor, "
    "escreva no próprio arquivo do worker a conta de carga nova — quantas "
    "chamadas por hora/dia o novo intervalo representa para o sistema externo "
    "(Sapiens, Oracle, WMS) e por que o volume é aceitável. Só então atualize "
    "o valor travado neste teste."
)


def mensagem_mudanca_cadencia(nome_classe: str, valor_travado: int, valor_atual: int) -> str:
    """Mensagem de falha: valor antigo → novo, apontando para a conta de carga."""
    return (
        f"{nome_classe}.intervalo_segundos: valor travado {valor_travado} → "
        f"valor no código {valor_atual}. {REGRA_21_CADENCIA}"
    )


class CadenciaSchedulersTests(SimpleTestCase):
    """Valores travados; falhar aqui significa conta de carga pendente de revisão."""

    def test_agendador_de_pendencias_mantem_ciclo_de_300_segundos(self):
        """Envia as filas de integração e dispara o relatório diário de falhas."""
        valor_esperado = 300
        valor_atual = EnviaPendenciasScheduler.intervalo_segundos
        self.assertEqual(
            valor_atual,
            valor_esperado,
            msg=mensagem_mudanca_cadencia("EnviaPendenciasScheduler", valor_esperado, valor_atual),
        )

    def test_agendador_de_ops_encerradas_mantem_ciclo_de_300_segundos(self):
        """Fecha paradas, remove OPs encerradas e importa sequenciamento do ERP."""
        valor_esperado = 300
        valor_atual = SincronizaOpsEncerradasScheduler.intervalo_segundos
        self.assertEqual(
            valor_atual,
            valor_esperado,
            msg=mensagem_mudanca_cadencia(
                "SincronizaOpsEncerradasScheduler", valor_esperado, valor_atual
            ),
        )

    def test_agendador_de_importacao_de_paletes_mantem_ciclo_de_uma_hora(self):
        """Solicita ao webservice ImportaWMS a sincronização de paletes no ERP."""
        valor_esperado = 3600
        valor_atual = ImportaPaleteScheduler.intervalo_segundos
        self.assertEqual(
            valor_atual,
            valor_esperado,
            msg=mensagem_mudanca_cadencia("ImportaPaleteScheduler", valor_esperado, valor_atual),
        )

    def test_agendador_de_consolidacao_de_tempos_mantem_ciclo_de_seis_horas(self):
        """Gera pacotes de produção/paradas nos cortes 00h15/06h15/12h15/18h15."""
        valor_esperado = 21600
        valor_atual = ConsolidaTemposERPScheduler.intervalo_segundos
        self.assertEqual(
            valor_atual,
            valor_esperado,
            msg=mensagem_mudanca_cadencia(
                "ConsolidaTemposERPScheduler", valor_esperado, valor_atual
            ),
        )

    def test_agendador_de_planejado_oee_mantem_ciclo_de_600_segundos(self):
        """Recalcula o planejado OEE do dia (e o dia anterior às 04:00)."""
        valor_esperado = 600
        valor_atual = OEEPlanejadoScheduler.intervalo_segundos
        self.assertEqual(
            valor_atual,
            valor_esperado,
            msg=mensagem_mudanca_cadencia("OEEPlanejadoScheduler", valor_esperado, valor_atual),
        )

    def test_intervalo_do_relatorio_de_falhas_espelha_o_ciclo_do_agendador(self):
        """O espelho declarado no worker não pode divergir do ciclo real do agendador.

        `RelatorioFalhasEmailWorker` roda dentro do ciclo do
        `EnviaPendenciasScheduler`; o valor próprio é duplicação reconhecida no
        comentário da constante. Quando a duplicação for eliminada (o valor
        passando a ser derivado do agendador), este teste pode ser removido.
        """
        espelho = RelatorioFalhasEmailWorker.INTERVALO_SEGUNDOS
        cadencia = EnviaPendenciasScheduler.intervalo_segundos
        self.assertEqual(
            espelho,
            cadencia,
            msg=(
                "RelatorioFalhasEmailWorker.INTERVALO_SEGUNDOS é espelho do ciclo de "
                f"EnviaPendenciasScheduler e os dois divergiram ({espelho} ≠ {cadencia}). "
                "O worker roda dentro do ciclo do agendador — atualize os dois juntos, "
                "passando antes pela " + REGRA_21_CADENCIA
            ),
        )
