"""Contrato estático da regra Senior que reduz apontamentos por lote."""

from pathlib import Path

from django.test import SimpleTestCase


class DiminuirApontamentoLspContratoTests(SimpleTestCase):
    """Protege o contrato que o SIGMA envia para o ERP, sem chamar Oracle."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "erp-senior"
            / "Dependencias Externas"
            / "WebService Apontamento"
            / "DiminuirApontamento.lsp"
        ).read_text(encoding="utf-8")

    def test_recebe_quantidade_final_sem_sequencia_do_sigma(self):
        self.assertIn('"QtdRe1", aQtdRe1', self.source)
        self.assertIn('"CodDep", aCodDep', self.source)
        self.assertNotIn('"SeqEoq", aSeqEoq', self.source)
        self.assertIn("ORDER BY SEQEOQ DESC", self.source)

    def test_rateio_acerta_e_grava_pendencia_em_transacao_unica(self):
        inicio = self.source.index("IniciarTransacao();")
        acertar = self.source.index("WSAcertar.Executar();")
        inserir = self.source.index("INSERT INTO USU_TESTCMP")
        excluir = self.source.index("UPDATE E210DLS")
        finalizar = self.source.index("FinalizarTransacao();", inicio)

        self.assertLess(inicio, acertar)
        self.assertLess(acertar, inserir)
        self.assertLess(inserir, excluir)
        self.assertLess(excluir, finalizar)
        self.assertIn("DesfazerTransacao();", self.source)

    def test_pendencia_contem_todo_contrato_confirmado(self):
        for field in (
            "USU_IDEUNI",
            "USU_CODEMP",
            "USU_CODORI",
            "USU_NUMORP",
            "USU_CODETG",
            "USU_CODCMP",
            "USU_QTDEST",
            "USU_CODPRO",
            "USU_CODDER",
            "USU_DERCMP",
            "USU_DATFIM",
            "USU_CODTNS",
            "USU_LOGINC",
            "USU_USUPRC",
            "USU_DATPRC",
            "USU_HORPRC",
            "USU_SITPEN",
        ):
            self.assertIn(field, self.source)

        self.assertIn("ObterGuid(aIdeUni);", self.source)
        self.assertIn("nQtdReduzir = nQtdTotal - nQtdRe1;", self.source)
        self.assertIn("Se (nQtdNova = 0)", self.source)
        self.assertIn("nQtdEst = nQtdUti;", self.source)
