"""Busca das telas de log: consulta e instrução da tela vêm da mesma fonte.

Regra do padrão (skill backend-sigma, "Fonte única dos campos de busca"):
a lista de campos que uma busca varre é constante única no módulo da view
(`CAMPOS_BUSCA`), consumida pela consulta (`consulta_de_busca`) e pela
instrução exibida na tela (rótulos no placeholder). Estes testes comparam
as duas pontas contra a constante: a consulta não pode varrer um conjunto
diferente do prometido, e a instrução não pode ser escrita à mão fora da
constante — o defeito que motivou a regra ("a tela prometia seis, a busca
varria sete").
"""

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.test import TestCase
from django.urls import reverse

from producao.views import (
    logs_apontamento_componentes,
    logs_apontamentos,
    logs_baixa_componentes,
    logs_tempo_producao,
)


def _caminhos_do_q(consulta: Q) -> set[str]:
    """Lookups (campo__operador) de um Q combinado — percorre os níveis OR."""
    caminhos: set[str] = set()
    for filho in consulta.children:
        if isinstance(filho, Q):
            caminhos |= _caminhos_do_q(filho)
        elif isinstance(filho, tuple):
            caminhos.add(str(filho[0]))
    return caminhos


class FonteUnicaBuscasFilaTests(TestCase):
    """Filas com busca totalmente icontains: consulta == constante."""

    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="busca_logs", password="x")
        cls.casos = (
            (logs_apontamentos, "logs_apontamentos"),
            (logs_baixa_componentes, "logs_baixa_componentes"),
            (logs_apontamento_componentes, "logs_apontamento_componentes"),
        )

    def setUp(self):
        self.client.force_login(self.usuario)

    def test_rotulos_da_constante_sao_exibiveis_e_unicos(self):
        for modulo, _rota in self.casos:
            with self.subTest(modulo=modulo.__name__):
                for campo, rotulo in modulo.CAMPOS_BUSCA:
                    self.assertTrue(campo, f"campo vazio em {modulo.__name__}")
                    self.assertTrue(rotulo, f"rótulo vazio para {campo}")
                # Constante e instrução derivam do mesmo lugar.
                self.assertEqual(
                    modulo.ROTULOS_BUSCA,
                    ", ".join(rotulo for _campo, rotulo in modulo.CAMPOS_BUSCA),
                )

    def test_consulta_varre_exatamente_os_campos_da_constante(self):
        for modulo, _rota in self.casos:
            with self.subTest(modulo=modulo.__name__):
                caminhos = _caminhos_do_q(modulo.consulta_de_busca("termo"))
                esperado = {f"{campo}__icontains" for campo, _rotulo in modulo.CAMPOS_BUSCA}
                self.assertEqual(caminhos, esperado)

    def test_instrucao_da_tela_lista_os_rotulos_da_constante(self):
        for modulo, rota in self.casos:
            with self.subTest(rota=rota):
                resposta = self.client.get(reverse(rota), {"search": "termo"})
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, f"Buscar por {modulo.ROTULOS_BUSCA}...")

    def test_telas_nao_exibem_acao_de_ditado_na_busca(self):
        for _modulo, rota in self.casos:
            with self.subTest(rota=rota):
                resposta = self.client.get(reverse(rota))
                self.assertNotContains(resposta, "data-ditado-busca")
                self.assertNotContains(resposta, "ditado-busca.js")


class FonteUnicaBuscaLogTempoProducaoTests(TestCase):
    """Busca do log de tempo de produção: icontains textual + exatos numéricos."""

    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="busca_log_tempo", password="x")

    def setUp(self):
        self.client.force_login(self.usuario)

    def test_consulta_textual_varre_os_campos_nao_exatos(self):
        caminhos = _caminhos_do_q(logs_tempo_producao.consulta_de_busca("termo"))
        esperado = {
            f"{campo}__icontains"
            for campo, _rotulo in logs_tempo_producao.CAMPOS_BUSCA
            if campo not in logs_tempo_producao.CAMPOS_BUSCA_EXATOS
        }
        self.assertEqual(caminhos, esperado)

    def test_consulta_numerica_varre_tambem_os_campos_exatos(self):
        caminhos = _caminhos_do_q(logs_tempo_producao.consulta_de_busca("123"))
        esperado = {
            f"{campo}__icontains"
            for campo, _rotulo in logs_tempo_producao.CAMPOS_BUSCA
            if campo not in logs_tempo_producao.CAMPOS_BUSCA_EXATOS
        } | set(logs_tempo_producao.CAMPOS_BUSCA_EXATOS)
        self.assertEqual(caminhos, esperado)

    def test_digito_unicode_nao_estoura_a_conversao_numerica(self):
        # "²".isdigit() é True e int("²") levanta ValueError — a conversão
        # só aceita decimal ASCII.
        caminhos = _caminhos_do_q(logs_tempo_producao.consulta_de_busca("²"))
        esperado = {
            f"{campo}__icontains"
            for campo, _rotulo in logs_tempo_producao.CAMPOS_BUSCA
            if campo not in logs_tempo_producao.CAMPOS_BUSCA_EXATOS
        }
        self.assertEqual(caminhos, esperado)

    def test_instrucao_da_tela_lista_os_rotulos_da_constante(self):
        resposta = self.client.get(reverse("log_tempo_producao"), {"search": "termo"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, f"Buscar por {logs_tempo_producao.ROTULOS_BUSCA}...")

    def test_tela_nao_exibe_acao_de_ditado_na_busca(self):
        resposta = self.client.get(reverse("log_tempo_producao"))
        self.assertNotContains(resposta, "data-ditado-busca")
