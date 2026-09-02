from django.contrib.auth import get_user_model
from django.test import TestCase

from setores.qualidade.models.estrutura import LiberacaoLote
from setores.qualidade.utils.wms_integracao import criar_integracao_wms_liberacao_lote

User = get_user_model()


class DatgerIntegracaoWmsTests(TestCase):
    """A fila WMS gerada pela liberação de lote deve registrar o momento da
    geração do registro em datger."""

    def setUp(self):
        self.usuario = User.objects.create_user(username="qualidade", password="senha")
        self.registro = LiberacaoLote.objects.create(
            codemp=1,
            codpro="PROD1",
            codder="1",
            coddep="01",
            codigo_integrador="INT1",
            codlot="LOTE5",
            numorp=100,
            qtdtot=10.0,
            qtdlibe=10.0,
            usuario=self.usuario,
        )

    def test_criar_integracao_wms_preenche_datger(self):
        integracao, criado = criar_integracao_wms_liberacao_lote(self.registro)

        self.assertTrue(criado)
        self.assertIsNotNone(integracao.datger)

    def test_reaproveitar_integracao_existente_nao_altera_datger(self):
        integracao_original, _ = criar_integracao_wms_liberacao_lote(self.registro)

        integracao_reaproveitada, criado = criar_integracao_wms_liberacao_lote(self.registro)

        self.assertFalse(criado)
        self.assertEqual(integracao_reaproveitada.pk, integracao_original.pk)
        self.assertEqual(integracao_reaproveitada.datger, integracao_original.datger)
