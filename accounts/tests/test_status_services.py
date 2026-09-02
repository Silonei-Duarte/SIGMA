"""Testes do painel Status dos Services (accounts/views/services.py)."""

import datetime

from django.test import TestCase
from django.utils import timezone

from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor
from accounts.views.services import _status_filas_integracao
from producao.models import LogTrocaOPAtiva, PacoteTempoERP


class StatusFilasIntegracaoTemposErpTests(TestCase):
    """Linha Log Tempos ERP: a fila não tem estado de erro próprio — falha de
    envio permanece PENDENTE (motivo só no log), então pendência conta
    somente PENDENTE; PROCESSANDO é reserva em andamento, não pendência."""

    @classmethod
    def setUpTestData(cls):
        empresa = Empresa.objects.create(codemp=92, nome="Empresa Painel", fantasia="EP")
        filial = Filial.objects.create(
            empresa=empresa,
            codfil=1,
            nome="Filial Painel",
            fantasia="FP",
            cnpj="92.222.222/0001-92",
        )
        departamento = Departamento.objects.create(filial=filial, descricao="Depto Painel")
        setor = Setor.objects.create(departamento=departamento, descricao="Setor Painel")
        centro = CentroRecurso.objects.create(
            setor=setor,
            codigo="CR-PNL",
            descricao="Centro Painel",
            codigo_integrador="CR-PNL",
        )
        cls.recurso = Recurso.objects.create(
            codigo="R-PNL", descricao="Recurso Painel", centro_recurso=centro
        )

    def _criar_pacote(self, op, status):
        agora = timezone.now()
        troca = LogTrocaOPAtiva.objects.create(
            recurso=self.recurso,
            origem="1",
            op=op,
            estagio=1,
            seqrot=1,
            horario_troca=agora - datetime.timedelta(hours=8),
        )
        return PacoteTempoERP.objects.create(
            troca_op_ativa=troca,
            corte_inicio_real=agora - datetime.timedelta(hours=4),
            corte_fim_real=agora,
            status=status,
        )

    @staticmethod
    def _linha_tempos_erp():
        return next(fila for fila in _status_filas_integracao() if fila["nome"] == "Log Tempos ERP")

    def test_dois_registros_reenviaveis_contam_dois_pendentes(self):
        """Pendência é PENDENTE somente: falha já vive em PENDENTE (sem estado
        ERRO), então dois registros reenviáveis contam um por linha de status,
        e INTEGRADO não conta."""
        self._criar_pacote(100, PacoteTempoERP.Status.PENDENTE)
        # Simula registro que veio da falha de envio: pendente com log de erro.
        com_falha = self._criar_pacote(200, PacoteTempoERP.Status.PENDENTE)
        com_falha.log = "Erro ao enviar pacote: HTTP 500"
        com_falha.save(update_fields=["log"])
        self._criar_pacote(300, PacoteTempoERP.Status.INTEGRADO)

        linha = self._linha_tempos_erp()

        self.assertEqual(linha["pendentes"], 2)
        self.assertEqual(linha["processando"], 0)

    def test_processando_conta_como_processando_e_nao_pendente(self):
        self._criar_pacote(400, PacoteTempoERP.Status.PROCESSANDO)

        linha = self._linha_tempos_erp()

        self.assertEqual(linha["pendentes"], 0)
        self.assertEqual(linha["processando"], 1)
