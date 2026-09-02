from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import Empresa, Filial

User = get_user_model()

PERMISSAO = "pode_visualizar_componentes_movimentar"


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


class ComponentesMovimentarAutorizacaoTests(TestCase):
    def setUp(self):
        self.empresa_a, self.filial_a = criar_empresa_filial(901)
        self.empresa_b, _ = criar_empresa_filial(902)
        self.usuario = User.objects.create_user(
            username="logistica_a", password="senha", filial=self.filial_a
        )
        self.client.force_login(self.usuario)

    def _conceder_permissao(self):
        self.usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="logistica", codename=PERMISSAO)
        )

    def test_anomimo_e_redirecionado_para_o_login(self):
        self.client.logout()

        resposta = self.client.get(reverse("logistica:componentes_movimentar"))

        self.assertEqual(resposta.status_code, 302)

    def test_usuario_sem_permissao_recebe_403(self):
        resposta = self.client.get(reverse("logistica:componentes_movimentar"))

        self.assertEqual(resposta.status_code, 403)

    def test_usuario_com_permissao_acessa_o_painel(self):
        self._conceder_permissao()
        with patch(
            "setores.logistica.views.componentes_movimentar._listar_recursos_erp", return_value=[]
        ):
            resposta = self.client.get(reverse("logistica:componentes_movimentar"))

        self.assertEqual(resposta.status_code, 200)

    def test_staff_sem_permissao_acessa_o_painel(self):
        self.usuario.is_staff = True
        self.usuario.save()
        with patch(
            "setores.logistica.views.componentes_movimentar._listar_recursos_erp", return_value=[]
        ):
            resposta = self.client.get(reverse("logistica:componentes_movimentar"))

        self.assertEqual(resposta.status_code, 200)

    def test_superusuario_acessa_o_painel(self):
        self.usuario.is_superuser = True
        self.usuario.save()
        with patch(
            "setores.logistica.views.componentes_movimentar._listar_recursos_erp", return_value=[]
        ):
            resposta = self.client.get(reverse("logistica:componentes_movimentar"))

        self.assertEqual(resposta.status_code, 200)

    def test_empresa_forjada_nao_amplia_o_escopo_do_usuario(self):
        self._conceder_permissao()
        with patch(
            "setores.logistica.views.componentes_movimentar._listar_recursos_erp", return_value=[]
        ) as mock_recursos:
            resposta = self.client.get(
                reverse("logistica:componentes_movimentar"), {"empresa": self.empresa_b.id}
            )

        self.assertEqual(resposta.status_code, 200)
        # Usuário não-staff permanece preso à empresa da própria filial,
        # mesmo informando outra empresa na requisição.
        self.assertEqual(resposta.context["empresa_id"], str(self.empresa_a.id))
        mock_recursos.assert_called_once_with(self.empresa_a.codemp)

    def test_historico_lote_sem_permissao_recebe_403(self):
        resposta = self.client.get(
            reverse("logistica:historico_lote_componente"),
            {"empresa": self.empresa_a.id, "codori": "110", "numorp": "1", "codcmp": "C1"},
        )

        self.assertEqual(resposta.status_code, 403)

    def test_historico_lote_de_outra_empresa_e_bloqueado(self):
        self._conceder_permissao()
        with patch(
            "setores.logistica.views.componentes_movimentar._buscar_historico_lote", return_value=[]
        ) as mock_busca:
            resposta = self.client.get(
                reverse("logistica:historico_lote_componente"),
                {"empresa": self.empresa_b.id, "codori": "110", "numorp": "1", "codcmp": "C1"},
            )

        self.assertEqual(resposta.status_code, 403)
        self.assertJSONEqual(resposta.content, {"erro": "Empresa inválida ou sem acesso."})
        mock_busca.assert_not_called()

    def test_historico_lote_da_propria_empresa_retorna_linhas(self):
        self._conceder_permissao()
        with patch(
            "setores.logistica.views.componentes_movimentar._buscar_historico_lote",
            return_value=[{"LOTE": "L1"}],
        ) as mock_busca:
            resposta = self.client.get(
                reverse("logistica:historico_lote_componente"),
                {"empresa": self.empresa_a.id, "codori": "110", "numorp": "1", "codcmp": "C1"},
            )

        self.assertEqual(resposta.status_code, 200)
        self.assertJSONEqual(resposta.content, {"linhas": [{"LOTE": "L1"}]})
        mock_busca.assert_called_once_with(self.empresa_a.codemp, "110", "1", "C1", "")

    def test_historico_lote_sem_filial_e_bloqueado(self):
        self.usuario.filial = None
        self.usuario.save()
        self._conceder_permissao()
        with patch(
            "setores.logistica.views.componentes_movimentar._buscar_historico_lote"
        ) as mock_busca:
            resposta = self.client.get(
                reverse("logistica:historico_lote_componente"),
                {"empresa": self.empresa_a.id, "codori": "110", "numorp": "1", "codcmp": "C1"},
            )

        self.assertEqual(resposta.status_code, 403)
        mock_busca.assert_not_called()

    def test_bobinas_sem_permissao_recebe_403(self):
        resposta = self.client.get(
            reverse("logistica:bobinas_disponiveis"),
            {"empresa": self.empresa_a.id, "codori": "110", "numorp": "1", "codcmp": "C1"},
        )

        self.assertEqual(resposta.status_code, 403)

    def test_bobinas_de_outra_empresa_e_bloqueado(self):
        self._conceder_permissao()
        with patch(
            "setores.logistica.views.componentes_movimentar._buscar_componentes_op"
        ) as mock_componentes:
            resposta = self.client.get(
                reverse("logistica:bobinas_disponiveis"),
                {"empresa": self.empresa_b.id, "codori": "110", "numorp": "1", "codcmp": "C1"},
            )

        self.assertEqual(resposta.status_code, 403)
        self.assertJSONEqual(resposta.content, {"erro": "Empresa inválida ou sem acesso."})
        mock_componentes.assert_not_called()

    def test_bobinas_da_propria_empresa_retorna_linhas(self):
        self._conceder_permissao()
        componente = {"CODCMP": "C1", "CODDER": None, "QTDPRV": 10, "QTDUTI": 0}
        with (
            patch(
                "setores.logistica.views.componentes_movimentar._buscar_componentes_op",
                return_value=[componente],
            ),
            patch(
                "setores.logistica.views.componentes_movimentar._buscar_bobinas_wms",
                return_value=([], 0),
            ),
        ):
            resposta = self.client.get(
                reverse("logistica:bobinas_disponiveis"),
                {"empresa": self.empresa_a.id, "codori": "110", "numorp": "1", "codcmp": "C1"},
            )

        self.assertEqual(resposta.status_code, 200)
        self.assertJSONEqual(resposta.content, {"linhas": [], "total_linhas": 0})
