"""Testes de producao/views/apontamentos_v2.py, funcao
classe_comparativo_percentual — cores da coluna Atual % no quadro
Componentes da OP da tela de apontamento v2.

A referencia visual sao as colunas de quantidade da consulta de lotes da
qualidade (templates/setores/qualidade/consulta_lotes.html): fundo *-sutil
com texto *-base, sem cor para estado neutro.
"""

from django.test import TestCase

from producao.views.apontamentos_v2 import classe_comparativo_percentual


class ClasseComparativoPercentualTests(TestCase):
    def test_dentro_da_tolerancia_usa_sucesso(self):
        self.assertEqual(
            classe_comparativo_percentual(30.0, 30.5),
            "bg-sucesso-sutil text-sucesso-base font-bold",
        )

    def test_acima_da_receita_usa_atencao(self):
        self.assertEqual(
            classe_comparativo_percentual(30.0, 35.0),
            "bg-atencao-sutil text-atencao-base font-bold",
        )

    def test_abaixo_da_receita_usa_erro(self):
        self.assertEqual(
            classe_comparativo_percentual(30.0, 25.0),
            "bg-erro-sutil text-erro-base font-bold",
        )

    def test_zero_com_zero_e_dentro_da_tolerancia(self):
        # None cai para 0: 0% contra 0% e igualdade, nao estado invalido.
        self.assertEqual(
            classe_comparativo_percentual(None, None),
            "bg-sucesso-sutil text-sucesso-base font-bold",
        )

    def test_valores_nao_numericos_ficam_sem_cor(self):
        # Estado neutro, igual ao zero sem cor na consulta de lotes.
        self.assertEqual(classe_comparativo_percentual("abc", "x"), "")
        self.assertEqual(classe_comparativo_percentual(None, "x"), "")
