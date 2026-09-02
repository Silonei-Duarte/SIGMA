from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor
from producao.models import (
    ApontamentoComponente,
    BaixaComponente,
    LogTrocaOPAtiva,
    PacoteTempoERP,
)
from producao.services.consolida_tempos_erp import gerar_cortes_tempos_erp
from producao.views.apontamentos_v1 import salvar_log_apontamento
from producao.views.apontamentos_v2 import salvar_log_componente
from producao.views.logs_apontamento_componentes import criar_ajuste_wms_palete_integrado
from producao.views.logs_baixa_componentes import criar_ajuste_wms_lote_baixado


class DatgerFilasIntegracaoTests(TestCase):
    """O campo datger deve registrar o momento em que o registro da fila foi
    gerado, em todas as filas de integração que ainda não o tinham."""

    @classmethod
    def setUpTestData(cls):
        empresa = Empresa.objects.create(codemp=1, nome="Empresa 1", fantasia="E1")
        filial = Filial.objects.create(
            empresa=empresa, codfil=1, nome="Filial 1", fantasia="F1", cnpj="00000000000001"
        )
        departamento = Departamento.objects.create(filial=filial, descricao="Depto 1")
        setor = Setor.objects.create(departamento=departamento, descricao="Setor 1")
        centro = CentroRecurso.objects.create(setor=setor, codigo="CR1", descricao="Centro 1")
        cls.recurso = Recurso.objects.create(
            centro_recurso=centro, codigo="R1", descricao="Recurso 1"
        )

    def test_salvar_log_apontamento_preenche_datger(self):
        agora = timezone.now().replace(microsecond=0)

        apontamento = salvar_log_apontamento(
            "1",
            "01",
            123,
            10,
            1,
            55,
            10.0,
            0.0,
            "LOTE1",
            "INT1",
            agora.strftime("%d/%m/%Y"),
            agora.strftime("%H:%M:%S"),
            agora,
        )

        self.assertIsNotNone(apontamento, "Falha ao salvar o apontamento de teste.")
        self.assertEqual(apontamento.datger, agora)

    def test_apontamento_refugo_puro_sem_origem_peso_e_salvo(self):
        # Regressão: qtd_prod=0 com qtd_ref>0 chegava com origem_peso=None
        # (None explícito não aciona o default do model) e o registro era
        # descartado por violação de NOT NULL, engolido pelo except.
        agora = timezone.now().replace(microsecond=0)

        apontamento = salvar_log_apontamento(
            "1",
            "01",
            123,
            10,
            1,
            55,
            0.0,
            5.0,
            "LOTE1",
            "INT1",
            agora.strftime("%d/%m/%Y"),
            agora.strftime("%H:%M:%S"),
            agora,
        )

        self.assertIsNotNone(apontamento, "Refugo puro não pode ser descartado.")
        self.assertEqual(apontamento.origem_peso, "")
        self.assertEqual(apontamento.datger, agora)

    def test_salvar_log_componente_preenche_datger(self):
        agora = timezone.now().replace(microsecond=0)

        componente, criado = salvar_log_componente(
            cod_emp="1",
            origem="01",
            num_op=123,
            cod_etg=10,
            seq_rot=1,
            num_cad=55,
            codigo_integrador="INT1",
            lote="LOTE2",
            dat_mov=agora.strftime("%d/%m/%Y"),
            hor_mov=agora.strftime("%H:%M:%S"),
            data_hora=agora,
        )

        self.assertTrue(criado)
        self.assertEqual(componente.datger, agora)

    def test_gerar_cortes_tempos_erp_preenche_datger(self):
        agora = timezone.now()
        troca = LogTrocaOPAtiva.objects.create(
            recurso=self.recurso,
            origem="1",
            op=100,
            estagio=1,
            seqrot=1,
            horario_troca=agora - timedelta(hours=8),
            id_operador=55,
        )

        criados = gerar_cortes_tempos_erp(corte_fim=agora)

        self.assertEqual(criados, 1)
        pacote = PacoteTempoERP.objects.get(troca_op_ativa=troca)
        self.assertIsNotNone(pacote.datger)

    def test_criar_ajuste_wms_lote_baixado_preenche_datger(self):
        agora = timezone.now()
        baixa = BaixaComponente.objects.create(
            recurso=self.recurso,
            codemp=1,
            origem="1",
            numorp=100,
            codetg=1,
            seqrot=1,
            codcmp="COMP1",
            qtduti=Decimal("2.0000"),
            codlot="LOTE3",
            status=BaixaComponente.Status.INTEGRADO,
            data_hora=agora,
        )

        with (
            mock.patch(
                "producao.views.logs_baixa_componentes._resolver_palete_wms_por_lote",
                return_value="PAL3",
            ),
            mock.patch(
                "setores.qualidade.views.wms_views.reservar_integracoes_wms_para_envio",
                return_value=[1],
            ),
            mock.patch("setores.qualidade.views.wms_views.disparar_envio_wms"),
        ):
            integracao = criar_ajuste_wms_lote_baixado(baixa)

        self.assertIsNotNone(integracao.datger)

    def test_criar_ajuste_wms_palete_integrado_preenche_datger(self):
        agora = timezone.now()
        componente = ApontamentoComponente.objects.create(
            codemp=1,
            origem="1",
            numorp=100,
            codetg=1,
            seqrot=1,
            numcad=55,
            lote="LOTE4",
            status=ApontamentoComponente.Status.INTEGRADO,
            data_hora=agora,
        )
        dados_componente = {
            "PalWms": "PAL4",
            "CodLotCmp": "LOTE4",
            "CodCmpRec": "COMP1",
            "DerCmpRec": "1",
        }

        with (
            mock.patch(
                "setores.qualidade.views.wms_views.reservar_integracoes_wms_para_envio",
                return_value=[1],
            ),
            mock.patch("setores.qualidade.views.wms_views.disparar_envio_wms"),
        ):
            integracao = criar_ajuste_wms_palete_integrado(componente, dados_componente)

        self.assertIsNotNone(integracao.datger)
