import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor
from producao.models import Sequenciamento


class AcoesMutaveisProducaoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="operador", password="senha")
        self.client.force_login(self.usuario)

    def test_rotas_mutaveis_rejeitam_get(self):
        # Rotas com @permissao_requerida (sequenciamento e exclusões de fila)
        # negam o ator antes da checagem de método: GET sem permissão é 403.
        # Os envios de fila seguem livres (decisão do sênior): GET logado é 405.
        rotas_403 = [
            ("consolidar_sequenciamento", []),
            ("sequenciar_automatico", []),
            ("excluir_apontamento_erp", [1]),
            ("excluir_todos_apontamentos_log", []),
            ("excluir_componente_log", [1]),
            ("excluir_todos_componentes_log", []),
            ("excluir_baixa_componente", [1]),
            ("excluir_todas_baixas_componentes", []),
            ("excluir_pacote_tempo_erp", [1]),
            ("excluir_parada_pacote_tempo_erp", [1]),
            ("excluir_tempos_erp_nao_integrados", []),
        ]
        rotas_405 = [
            ("enviar_apontamento_log", [1]),
            ("enviar_todos_apontamentos_log", []),
            ("enviar_componente_log", [1]),
            ("enviar_todos_componentes_log", []),
            ("enviar_baixa_componente_log", [1]),
            ("enviar_todas_baixas_componentes", []),
        ]

        for nome, argumentos in rotas_403:
            with self.subTest(rota=nome):
                self.assertEqual(self.client.get(reverse(nome, args=argumentos)).status_code, 403)
        for nome, argumentos in rotas_405:
            with self.subTest(rota=nome):
                self.assertEqual(self.client.get(reverse(nome, args=argumentos)).status_code, 405)


class SequenciamentoEscopoTests(TestCase):
    def setUp(self):
        self.empresa_a, self.recurso_a = self._criar_recurso(1, "A")
        self.empresa_b, self.recurso_b = self._criar_recurso(2, "B")
        filial_a = self.recurso_a.centro_recurso.setor.departamento.filial
        self.usuario = get_user_model().objects.create_user(
            username="sequenciador", password="senha", filial=filial_a
        )
        self.usuario.user_permissions.add(
            Permission.objects.get(codename="pode_consolidar_sequenciamento_erp")
        )
        self.client.force_login(self.usuario)

    @staticmethod
    def _criar_recurso(codemp, sufixo):
        empresa = Empresa.objects.create(codemp=codemp, nome=f"Empresa {sufixo}", fantasia=sufixo)
        filial = Filial.objects.create(
            empresa=empresa,
            codfil=1,
            nome=f"Filial {sufixo}",
            fantasia=sufixo,
            cnpj=f"{codemp}" * 14,
        )
        departamento = Departamento.objects.create(filial=filial, descricao=f"Depto {sufixo}")
        setor = Setor.objects.create(departamento=departamento, descricao=f"Setor {sufixo}")
        centro = CentroRecurso.objects.create(
            setor=setor,
            codigo=f"CR{sufixo}",
            descricao=f"Centro {sufixo}",
            codigo_integrador=f"CR{sufixo}",
        )
        return empresa, Recurso.objects.create(
            codigo=f"R{sufixo}", descricao=f"Recurso {sufixo}", centro_recurso=centro
        )

    def test_consolidacao_recusa_centro_ou_recurso_de_outra_empresa(self):
        resposta = self.client.post(
            reverse("consolidar_sequenciamento"),
            {
                "centro_id": self.recurso_b.centro_recurso_id,
                "sequenciamento_json": "[]",
            },
        )
        self.assertEqual(resposta.status_code, 403)

        resposta = self.client.post(
            reverse("consolidar_sequenciamento"),
            {
                "centro_id": self.recurso_a.centro_recurso_id,
                "sequenciamento_json": json.dumps(
                    [
                        {
                            "recurso": self.recurso_b.id,
                            "ordenacao": 1,
                            "op": 1,
                            "origem": "1",
                            "codproduto": "P",
                            "estagio": 1,
                            "seqrot": 1,
                            "tempo": 1,
                            "operacao": "OP",
                        }
                    ]
                ),
            },
        )
        self.assertEqual(resposta.status_code, 400)

    def test_consolidacao_invalida_preserva_sequenciamento_existente(self):
        existente = Sequenciamento.objects.create(
            recurso=self.recurso_a,
            ordenacao=1,
            op=10,
            origem="1",
            codproduto="P",
            estagio=1,
            seqrot=1,
            tempo=1,
            operacao="OP",
        )
        resposta = self.client.post(
            reverse("consolidar_sequenciamento"),
            {"centro_id": self.recurso_a.centro_recurso_id, "sequenciamento_json": "[{]"},
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertTrue(Sequenciamento.objects.filter(pk=existente.pk).exists())

    def test_next_externo_nao_redireciona(self):
        # A rota exige pode_alterar_paradas (fatia Autorizações); o foco
        # aqui é o next externo ser descartado pelo _redirect_retorno.
        self.usuario.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="producao", codename="pode_alterar_paradas"
            )
        )
        resposta = self.client.post(
            reverse("criar_parada_manual_log"),
            {"recurso": self.recurso_a.id, "numcad": "invalido", "next": "https://externo.test/"},
        )
        self.assertRedirects(resposta, reverse("log_tempo_producao"), fetch_redirect_response=False)
