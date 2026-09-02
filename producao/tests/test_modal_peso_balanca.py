from pathlib import Path

from django.test import SimpleTestCase

TEMPLATES_BALANCA = (
    "apontamentos_v1.html",
    "apontamentos_v3.html",
)
PASTA_TEMPLATES = Path(__file__).parents[2] / "templates" / "producao"


class ModalPesoBalancaTests(SimpleTestCase):
    def test_modal_abre_zerado_sem_timeout_local_apos_leitura_da_balanca(self):
        for nome_template in TEMPLATES_BALANCA:
            with self.subTest(template=nome_template):
                conteudo = (PASTA_TEMPLATES / nome_template).read_text(encoding="utf-8")

                self.assertIn('pesoModal.value = "0.00";', conteudo)
                self.assertIn("function iniciarTimerManual()", conteudo)
                self.assertIn('containerPesoManual.classList.remove("hidden")', conteudo)
                self.assertIn("Math.trunc(parseFloat(event.detail.balanca) * 100)", conteudo)
                self.assertNotIn("timeoutInatividade", conteudo)
                self.assertNotIn('setTimeout(() => { pesoModal.value = "0.00"; }, 5000)', conteudo)

    def test_atualizacao_da_balanca_trunca_para_duas_casas_decimais(self):
        for nome_template in TEMPLATES_BALANCA:
            with self.subTest(template=nome_template):
                conteudo = (PASTA_TEMPLATES / nome_template).read_text(encoding="utf-8")

                self.assertIn("Math.trunc(parseFloat(event.detail.balanca) * 100) / 100", conteudo)
                self.assertIn(".toFixed(2)", conteudo)
