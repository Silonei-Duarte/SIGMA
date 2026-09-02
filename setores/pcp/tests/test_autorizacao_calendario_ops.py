from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import Empresa, Filial

User = get_user_model()

PERMISSAO = "pode_visualizar_calendario_ops"

OPCOES_VAZIAS: dict[str, list[str]] = {"maquinas": [], "origens": [], "produtos": []}


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


class CalendarioOpsAutorizacaoTests(TestCase):
    def setUp(self):
        self.empresa_a, self.filial_a = criar_empresa_filial(901)
        criar_empresa_filial(902)
        self.usuario = User.objects.create_user(
            username="pcp_a", password="senha", filial=self.filial_a
        )
        self.client.force_login(self.usuario)

    def _conceder_permissao(self):
        self.usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="pcp", codename=PERMISSAO)
        )

    def test_anomimo_e_redirecionado_para_o_login(self):
        self.client.logout()

        resposta = self.client.get(reverse("pcp:calendario_ops"))

        self.assertEqual(resposta.status_code, 302)

    def test_tela_sem_permissao_recebe_403(self):
        resposta = self.client.get(reverse("pcp:calendario_ops"))

        self.assertEqual(resposta.status_code, 403)

    def test_tela_com_permissao_acessa_e_consulta_a_empresa_da_filial(self):
        self._conceder_permissao()
        with patch(
            "setores.pcp.views.calendario_ops._opcoes_filtros", return_value=OPCOES_VAZIAS
        ) as mock_opcoes:
            resposta = self.client.get(reverse("pcp:calendario_ops"))

        self.assertEqual(resposta.status_code, 200)
        mock_opcoes.assert_called_once_with(self.empresa_a.codemp)

    def test_filtros_selecionados_usam_texto_semantico_para_os_dois_temas(self):
        self._conceder_permissao()
        with patch("setores.pcp.views.calendario_ops._opcoes_filtros", return_value=OPCOES_VAZIAS):
            resposta = self.client.get(reverse("pcp:calendario_ops"))

        conteudo = resposta.content.decode()
        self.assertIn("details.tem-filtro>summary]:text-informacao-base", conteudo)
        self.assertNotIn("details.tem-filtro>summary]:bg-informacao-sutil", conteudo)
        self.assertNotIn("details.tem-filtro>summary]:text-texto-sobre-marca", conteudo)

    def test_situacoes_nascem_desmarcadas_sem_selecao_explicita(self):
        self._conceder_permissao()
        with patch("setores.pcp.views.calendario_ops._opcoes_filtros", return_value=OPCOES_VAZIAS):
            resposta = self.client.get(reverse("pcp:calendario_ops"))

        self.assertEqual(resposta.context["filtros"]["situacoes"], [])

    def test_situacoes_marcadas_apenas_com_selecao_explicita(self):
        self._conceder_permissao()
        with patch("setores.pcp.views.calendario_ops._opcoes_filtros", return_value=OPCOES_VAZIAS):
            resposta = self.client.get(reverse("pcp:calendario_ops"), {"situacao": ["A", "L"]})

        self.assertEqual(resposta.context["filtros"]["situacoes"], ["A", "L"])

    def test_staff_sem_permissao_acessa_a_tela(self):
        self.usuario.is_staff = True
        self.usuario.save()
        with patch("setores.pcp.views.calendario_ops._opcoes_filtros", return_value=OPCOES_VAZIAS):
            resposta = self.client.get(reverse("pcp:calendario_ops"))

        self.assertEqual(resposta.status_code, 200)

    def test_superusuario_acessa_a_tela(self):
        self.usuario.is_superuser = True
        self.usuario.save()
        with patch("setores.pcp.views.calendario_ops._opcoes_filtros", return_value=OPCOES_VAZIAS):
            resposta = self.client.get(reverse("pcp:calendario_ops"))

        self.assertEqual(resposta.status_code, 200)

    def test_eventos_sem_permissao_recebe_403(self):
        resposta = self.client.get(reverse("pcp:eventos_calendario_ops"))

        self.assertEqual(resposta.status_code, 403)

    def test_eventos_consultam_apenas_a_empresa_da_filial(self):
        self._conceder_permissao()
        with (
            patch(
                "setores.pcp.views.calendario_ops._consultar_eventos", return_value=[]
            ) as mock_eventos,
            patch(
                "setores.pcp.views.calendario_ops._consultar_comprometimentos_por_produto",
                return_value={},
            ),
        ):
            resposta = self.client.get(reverse("pcp:eventos_calendario_ops"))

        self.assertEqual(resposta.status_code, 200)
        self.assertJSONEqual(resposta.content, [])
        self.assertEqual(mock_eventos.call_args.args[0], self.empresa_a.codemp)

    def test_detalhes_sem_permissao_recebe_403(self):
        resposta = self.client.get(
            reverse("pcp:detalhes_calendario_ops"),
            {"codori": "110", "numorp": 1, "codpro": "P1"},
        )

        self.assertEqual(resposta.status_code, 403)

    def test_detalhes_com_permissao_retorna_calculo(self):
        self._conceder_permissao()
        alvo = {
            "codori": "110",
            "dtpfim": date.today() + timedelta(days=10),
            "dtrfim": None,
            "unimed": "KG",
        }
        # Cinco consultas: alvo, reservas da OP, estoque, produção e consumo.
        with patch(
            "setores.pcp.views.calendario_ops._linhas_oracle", side_effect=[[alvo], [], [], [], []]
        ):
            resposta = self.client.get(
                reverse("pcp:detalhes_calendario_ops"),
                {"codori": "110", "numorp": 1, "codpro": "P1"},
            )

        self.assertEqual(resposta.status_code, 200)

    def test_salvar_cores_sem_permissao_recebe_403(self):
        resposta = self.client.post(
            reverse("pcp:salvar_cores_calendario_ops"), {"colorido": "false"}
        )

        self.assertEqual(resposta.status_code, 403)

    def test_salvar_cores_com_permissao_grava_preferencia(self):
        self._conceder_permissao()

        resposta = self.client.post(
            reverse("pcp:salvar_cores_calendario_ops"), {"colorido": "false"}
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertJSONEqual(resposta.content, {"colorido": False})
        self.assertFalse(self.client.session["calendario_ops_cores_coloridas"])
