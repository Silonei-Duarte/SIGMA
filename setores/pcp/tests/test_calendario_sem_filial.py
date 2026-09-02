from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class CalendarioOpsSemFilialTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username="pcp_sem_filial", password="senha")
        permissao = Permission.objects.get(
            content_type__app_label="pcp", codename="pode_visualizar_calendario_ops"
        )
        self.usuario.user_permissions.add(permissao)
        self.client.force_login(self.usuario)

    @patch("setores.pcp.views.calendario_ops._opcoes_filtros")
    def test_tela_nao_consulta_filtros_sem_filial(self, mock_opcoes):
        resposta = self.client.get(reverse("pcp:calendario_ops"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            resposta.context["opcoes"], {"maquinas": [], "origens": [], "produtos": []}
        )
        mock_opcoes.assert_not_called()

    @patch("setores.pcp.views.calendario_ops._consultar_eventos")
    def test_eventos_retorna_lista_vazia_sem_filial(self, mock_consultar):
        resposta = self.client.get(reverse("pcp:eventos_calendario_ops"))

        self.assertEqual(resposta.status_code, 200)
        self.assertJSONEqual(resposta.content, [])
        mock_consultar.assert_not_called()

    @patch("setores.pcp.views.calendario_ops._linhas_oracle")
    def test_detalhe_nao_consulta_oracle_sem_filial(self, mock_oracle):
        resposta = self.client.get(
            reverse("pcp:detalhes_calendario_ops"),
            {"codori": "S", "numorp": 1, "codpro": "P1"},
        )

        self.assertEqual(resposta.status_code, 404)
        mock_oracle.assert_not_called()

    def test_salvar_cores_e_bloqueado_sem_filial(self):
        resposta = self.client.post(
            reverse("pcp:salvar_cores_calendario_ops"), {"colorido": "false"}
        )

        self.assertEqual(resposta.status_code, 403)
        self.assertNotIn("calendario_ops_cores_coloridas", self.client.session)
