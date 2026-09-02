from django.test import SimpleTestCase

from producao.views.apontamentos_v1 import (
    calcular_bobinas_disponiveis,
    resolver_bobina_apontamento,
)


class CalcularBobinasDisponiveisTests(SimpleTestCase):
    def test_sem_leitura_do_recurso_nao_oferece_opcao(self):
        self.assertEqual(calcular_bobinas_disponiveis(0, 0), [])

    def test_intervalo_normal_entre_ultima_apontada_e_atual(self):
        self.assertEqual(
            calcular_bobinas_disponiveis(150, 140),
            [150, 149, 148, 147, 146, 145, 144, 143, 142, 141],
        )

    def test_sem_historico_oferece_apenas_a_bobina_atual(self):
        self.assertEqual(calcular_bobinas_disponiveis(150, 0), [150])

    def test_limita_a_cem_opcoes_quando_ultima_apontada_e_muito_antiga(self):
        bobinas = calcular_bobinas_disponiveis(1000, 1)
        self.assertEqual(len(bobinas), 100)
        self.assertEqual(bobinas[0], 1000)
        self.assertEqual(bobinas[-1], 901)

    def test_bobina_atual_atras_da_ultima_apontada_nao_oferece_nenhuma_opcao(self):
        # Sensor/contador com erro (reset, estouro fora de sincronia etc.):
        # nao deve devolver bobina_atual_rec, pois esse valor sempre seria
        # rejeitado pela validacao de duplicidade no POST.
        self.assertEqual(calcular_bobinas_disponiveis(100, 150), [])

    def test_bobina_atual_igual_a_ultima_apontada_nao_oferece_nenhuma_opcao(self):
        self.assertEqual(calcular_bobinas_disponiveis(150, 150), [])


class ResolverBobinaApontamentoTests(SimpleTestCase):
    def test_campo_ausente_usa_historico_erp_quando_disponivel(self):
        historico = [{"codetg": 10, "seqrot": 20, "numcad": 5, "numbob": 777}]

        resultado = resolver_bobina_apontamento(
            None, historico, "10", "20", "5", bobina_recurso=999
        )

        self.assertEqual(resultado, 777)

    def test_campo_ausente_sem_historico_usa_bobina_do_recurso(self):
        resultado = resolver_bobina_apontamento(None, [], "10", "20", "5", bobina_recurso=321)

        self.assertEqual(resultado, 321)

    def test_campo_ausente_sem_historico_nem_recurso_devolve_zero(self):
        resultado = resolver_bobina_apontamento(None, [], "10", "20", "5", bobina_recurso=None)

        self.assertEqual(resultado, 0)

    def test_selecao_explicita_de_sem_numero_devolve_none(self):
        # Operador escolheu "Sem número de bobina": não deve cair no
        # fallback do histórico/recurso, e o apontamento não pode travar.
        resultado = resolver_bobina_apontamento(
            "", [{"codetg": 10, "seqrot": 20, "numcad": 5, "numbob": 777}], "10", "20", "5", 999
        )

        self.assertIsNone(resultado)

    def test_numero_informado_e_convertido_para_inteiro(self):
        resultado = resolver_bobina_apontamento("456", [], "10", "20", "5", 999)

        self.assertEqual(resultado, 456)
