from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from accounts.models import Empresa, Filial
from setores.suprimentos.views.componentes_separar import _montar_necessidade_separacao

User = get_user_model()

PERMISSAO = "pode_visualizar_componentes_separar"


def criar_empresa_filial(codemp):
    empresa = Empresa.objects.create(codemp=codemp, nome=f"Empresa {codemp}", fantasia=f"E{codemp}")
    filial = Filial.objects.create(
        empresa=empresa,
        codfil=1,
        nome=f"Filial {codemp}",
        fantasia=f"F{codemp}",
        cnpj=f"{codemp:014d}",
    )
    return empresa, filial


class ComponentesSepararAutorizacaoTests(TestCase):
    def setUp(self):
        self.empresa_a, self.filial_a = criar_empresa_filial(901)
        self.empresa_b, _ = criar_empresa_filial(902)
        self.usuario = User.objects.create_user(
            username="suprimentos_a", password="senha", filial=self.filial_a
        )
        self.client.force_login(self.usuario)

    def _conceder_permissao(self):
        self.usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="suprimentos", codename=PERMISSAO)
        )

    def _mockar_consultas_oracle(self):
        """Mocks das consultas ERP; devolve os mocks para asserts de escopo."""
        return [
            self.enterContext(
                patch(
                    "setores.suprimentos.views.componentes_separar._buscar_necessidade_ops",
                    return_value=[],
                )
            ),
            self.enterContext(
                patch(
                    "setores.suprimentos.views.componentes_separar._buscar_estoque_componentes",
                    return_value=[],
                )
            ),
            self.enterContext(
                patch(
                    "setores.suprimentos.views.componentes_separar._buscar_nomes_depositos",
                    return_value={},
                )
            ),
        ]

    def test_anomimo_e_redirecionado_para_o_login(self):
        self.client.logout()

        resposta = self.client.get(reverse("suprimentos:componentes_separar"))

        self.assertEqual(resposta.status_code, 302)

    def test_usuario_sem_permissao_recebe_403(self):
        resposta = self.client.get(reverse("suprimentos:componentes_separar"))

        self.assertEqual(resposta.status_code, 403)

    def test_usuario_com_permissao_acessa_a_tela(self):
        self._conceder_permissao()
        self._mockar_consultas_oracle()

        resposta = self.client.get(reverse("suprimentos:componentes_separar"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["empresa_id"], str(self.empresa_a.id))

    def test_filtros_selecionados_usam_texto_semantico_sem_texto_sobre_marca(self):
        self._conceder_permissao()
        self._mockar_consultas_oracle()

        resposta = self.client.get(reverse("suprimentos:componentes_separar"))

        conteudo = resposta.content.decode()
        self.assertIn('"!text-informacao-base"', conteudo)
        self.assertIn('resumo.classList.remove("text-texto-sobre-marca")', conteudo)

    def test_staff_sem_permissao_acessa_a_tela(self):
        self.usuario.is_staff = True
        self.usuario.save()
        self._mockar_consultas_oracle()

        resposta = self.client.get(reverse("suprimentos:componentes_separar"))

        self.assertEqual(resposta.status_code, 200)

    def test_superusuario_acessa_a_tela(self):
        self.usuario.is_superuser = True
        self.usuario.save()
        self._mockar_consultas_oracle()

        resposta = self.client.get(reverse("suprimentos:componentes_separar"))

        self.assertEqual(resposta.status_code, 200)

    def test_usuario_com_permissao_sem_filial_nao_recebe_empresas(self):
        self.usuario.filial = None
        self.usuario.save()
        self._conceder_permissao()
        with patch(
            "setores.suprimentos.views.componentes_separar._buscar_necessidade_ops"
        ) as mock_busca:
            resposta = self.client.get(reverse("suprimentos:componentes_separar"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["empresas"], [])
        self.assertEqual(resposta.context["empresa_id"], "")
        mock_busca.assert_not_called()

    def test_empresa_forjada_nao_amplia_o_escopo_do_usuario(self):
        self._conceder_permissao()
        mocks = self._mockar_consultas_oracle()

        resposta = self.client.get(
            reverse("suprimentos:componentes_separar"), {"empresa": self.empresa_b.id}
        )

        self.assertEqual(resposta.status_code, 200)
        # Usuário não-staff permanece preso à empresa da própria filial,
        # mesmo informando outra empresa na requisição.
        self.assertEqual(resposta.context["empresa_id"], str(self.empresa_a.id))
        mocks[0].assert_called_once_with(self.empresa_a.codemp)

    def test_filtro_de_deposito_de_planta_afeta_a_tela_principal(self):
        self._conceder_permissao()
        self.enterContext(
            patch(
                "setores.suprimentos.views.componentes_separar._buscar_necessidade_ops",
                return_value=[linha_de_op(24195, 3, 500.0)],
            )
        )
        self.enterContext(
            patch(
                "setores.suprimentos.views.componentes_separar._buscar_estoque_componentes",
                return_value=[
                    linha_de_estoque("P01.01", 100.0),
                    linha_de_estoque("P01.02", 400.0),
                ],
            )
        )
        self.enterContext(
            patch(
                "setores.suprimentos.views.componentes_separar._buscar_nomes_depositos",
                return_value={},
            )
        )

        resposta = self.client.get(
            reverse("suprimentos:componentes_separar"), {"deposito_planta": "P01.01"}
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["depositos_planta_selecionados"], ("P01.01",))
        self.assertFalse(resposta.context["depositos_planta_todos"])
        item = resposta.context["necessidades"][0]
        self.assertAlmostEqual(item["necessidade_real"], 400.0)

    def test_consulta_do_erp_exclui_recurso_de_producao_externa(self):
        self._conceder_permissao()
        capturado = []

        class CursorFalso:
            description = []

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql, params):
                capturado.append((sql, params))

            def fetchall(self):
                return []

        with patch(
            "setores.suprimentos.views.componentes_separar.cursor_oracle_erp",
            return_value=CursorFalso(),
        ):
            resposta = self.client.get(reverse("suprimentos:componentes_separar"))

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(
            any(
                "TRIM(oop.CODCRE) <> :recurso_externo" in sql
                and params.get("recurso_externo") == "930"
                for sql, params in capturado
            )
        )

    def test_coluna_em_planta_da_op_mostra_o_rateio_da_planta(self):
        self._conceder_permissao()
        self._mockar_consultas_oracle()

        resposta = self.client.get(reverse("suprimentos:componentes_separar"))

        conteudo = resposta.content.decode()
        self.assertIn("op.em_planta", conteudo)
        # Saldo do depósito específico da OP não aparece mais na coluna
        # "Em Planta" — ele é informativo e não é o estoque da planta.
        self.assertNotIn("estoque_deposito", conteudo)


def linha_de_op(numorp, numpri, qtdprv, qtduti=0.0):
    return {
        "CODCRE": "101",
        "DESCRE": "Recurso 101",
        "CODORI": "110",
        "NUMORP": numorp,
        "NUMPRI": numpri,
        "SITORP": "L",
        "QTD_PREVISTO_OP": 10.0,
        "QTD_REALIZADO_OP": 0.0,
        "UM_PRODUTO": "UN",
        "DESC_PRODUTO_OP": "Produto da OP",
        "DESC_DER_OP": " ",
        "CODCMP": "66314831313026",
        "CODDER": " ",
        "CODDEP": "01.03",
        "DESPRO": "Componente de teste",
        "DESDER": " ",
        "CODFAM": "62",
        "DESFAM": "Materia-prima",
        "UNIMED": "KG",
        "QTDPRV": qtdprv,
        "QTDUTI": qtduti,
    }


def linha_de_estoque(coddep, qtdest):
    return {
        "CODPRO": "66314831313026",
        "CODDER": " ",
        "CODDEP": coddep,
        "QTDEST": qtdest,
    }


class ComponentesSepararRateioPlantaTests(SimpleTestCase):
    def test_saldo_do_pulmao_p0101_abate_e_almoxarifado_e_pulmao_mp_sao_informativos(self):
        linhas = [linha_de_op(24195, 3, 12720.0)]
        estoque = [
            linha_de_estoque("P01.01", 4320.0),
            linha_de_estoque("P01.03", 0.0),
            linha_de_estoque("01.03", 8400.0),
        ]

        resultado = _montar_necessidade_separacao(linhas, estoque)

        self.assertEqual(len(resultado), 1)
        item = resultado[0]
        # P01.01 (Pulmão Planta 1) é planta: os 4320 abatem a necessidade.
        self.assertAlmostEqual(item["estoque_planta"], 4320.0)
        self.assertAlmostEqual(item["necessidade_real"], 8400.0)
        # A OP recebe 4320 da planta rateada para ela.
        self.assertAlmostEqual(item["ops"][0]["em_planta"], 4320.0)
        # Almoxarifado (01.03) e pulmão MP (P01.03) não entram no rateio:
        # o saldo do Alpino é só informativo.
        self.assertAlmostEqual(item["estoque_geral"], 8400.0)
        detalhe_planta = {d["deposito"]: d["saldo"] for d in item["estoque_detalhe"]}
        self.assertAlmostEqual(detalhe_planta["P01.01"], 4320.0)
        self.assertAlmostEqual(detalhe_planta["P01.02"], 0.0)

    def test_saldo_da_planta_rateia_na_ordem_de_prioridade_das_ops(self):
        linhas = [
            linha_de_op(24195, 1, 4320.0),
            linha_de_op(24196, 2, 4000.0),
        ]
        estoque = [linha_de_estoque("P01.01", 4320.0)]

        resultado = _montar_necessidade_separacao(linhas, estoque)

        self.assertEqual(len(resultado), 1)
        item = resultado[0]
        self.assertAlmostEqual(item["necessidade_op"], 8320.0)
        self.assertAlmostEqual(item["estoque_planta"], 4320.0)
        self.assertAlmostEqual(item["necessidade_real"], 4000.0)
        a_separar_por_op = {op["numorp"]: op["a_separar"] for op in item["ops"]}
        em_planta_por_op = {op["numorp"]: op["em_planta"] for op in item["ops"]}
        self.assertAlmostEqual(a_separar_por_op[24195], 0.0)
        self.assertAlmostEqual(a_separar_por_op[24196], 4000.0)
        self.assertAlmostEqual(em_planta_por_op[24195], 4320.0)
        self.assertAlmostEqual(em_planta_por_op[24196], 0.0)

    def test_op_coberta_pela_planta_aparece_junto_das_demais(self):
        linhas = [
            linha_de_op(24112, 4, 7000.0),
            linha_de_op(24243, 0, 5000.0),
        ]
        estoque = [linha_de_estoque("P01.01", 10279.141)]

        resultado = _montar_necessidade_separacao(linhas, estoque, separar_prioridades=True)

        # A OP mais prioritária fica com "A separar" zero, mas continua
        # listada — é ela quem consumiu o rateio da planta.
        self.assertEqual(len(resultado), 2)
        por_prioridade = {item["prioridade"]: item for item in resultado}
        self.assertAlmostEqual(por_prioridade[4]["necessidade_real"], 0.0)
        self.assertAlmostEqual(por_prioridade[0]["necessidade_real"], 1720.859)
        # O modal de qualquer linha lista TODAS as OPs do componente, não só
        # as do grupo da linha.
        for item in resultado:
            ops_do_modal = {op["numorp"]: op for op in item["ops"]}
            self.assertEqual(set(ops_do_modal), {24112, 24243})
            self.assertAlmostEqual(ops_do_modal[24112]["em_planta"], 7000.0)
            self.assertAlmostEqual(ops_do_modal[24112]["a_separar"], 0.0)
            self.assertAlmostEqual(ops_do_modal[24243]["em_planta"], 3279.141)
            self.assertAlmostEqual(ops_do_modal[24243]["a_separar"], 1720.859)
        # Sem saldo no almoxarifado: A separar zero é etiqueta verde, o resto vermelha.
        self.assertIn("bg-sucesso-sutil", por_prioridade[4]["classe_a_separar"])
        self.assertIn("bg-erro-sutil", por_prioridade[0]["classe_a_separar"])

    def test_a_separar_com_saldo_no_almoxarifado_e_exibido_em_azul(self):
        linhas = [linha_de_op(24195, 3, 100.0)]
        estoque = [
            linha_de_estoque("P01.01", 0.0),
            linha_de_estoque("01.03", 500.0),
        ]

        resultado = _montar_necessidade_separacao(linhas, estoque)

        self.assertEqual(len(resultado), 1)
        item = resultado[0]
        self.assertAlmostEqual(item["necessidade_real"], 100.0)
        self.assertIn("informacao", item["classe_a_separar"])
        self.assertIn("informacao", item["ops"][0]["classe_a_separar"])

    def test_componente_totalmente_coberto_pela_planta_nao_e_listado(self):
        linhas = [linha_de_op(24195, 3, 100.0)]
        estoque = [linha_de_estoque("P01.01", 500.0)]

        resultado = _montar_necessidade_separacao(linhas, estoque)

        self.assertEqual(resultado, [])

    def test_filtro_de_deposito_de_planta_restringe_so_o_rateio(self):
        linhas = [linha_de_op(24195, 3, 500.0)]
        estoque = [
            linha_de_estoque("P01.01", 100.0),
            linha_de_estoque("P01.02", 400.0),
            linha_de_estoque("01.03", 900.0),
        ]

        # Considerando só o P01.01 (Planta 1), o rateio usa apenas os 100 dele.
        resultado = _montar_necessidade_separacao(linhas, estoque, depositos_planta=("P01.01",))
        self.assertEqual(len(resultado), 1)
        item = resultado[0]
        self.assertAlmostEqual(item["estoque_planta"], 100.0)
        self.assertAlmostEqual(item["necessidade_real"], 400.0)
        # O detalhe do modal continua completo: mostra os dois depósitos.
        detalhe_planta = {d["deposito"]: d["saldo"] for d in item["estoque_detalhe"]}
        self.assertAlmostEqual(detalhe_planta["P01.01"], 100.0)
        self.assertAlmostEqual(detalhe_planta["P01.02"], 400.0)

        # Sem filtro, os dois depósitos entram no rateio (500 cobre tudo).
        resultado_completo = _montar_necessidade_separacao(linhas, estoque)
        self.assertEqual(resultado_completo, [])
