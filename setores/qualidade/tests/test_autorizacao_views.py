"""Testes de autorização das rotas privadas do app `qualidade`.

Fatia Autorizações: as rotas passaram de `user_passes_test`/checagens manuais
para o decorator comum `SIGMA.autorizacao.permissao_requerida()`. Este arquivo
cobre o que as regressões existentes não cobriam: o deny 403 por view, o
bypass de staff e o caminho feliz leve (sem rede real, Oracle sempre mockado).
As regressões de escopo por empresa e de ações internas continuam nos arquivos
de teste originais do app.
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import Empresa, Filial, ParametrosFilial

User = get_user_model()


def _criar_empresa_filial(codemp):
    empresa = Empresa.objects.create(codemp=codemp, nome=f"Empresa {codemp}", fantasia=f"E{codemp}")
    filial = Filial.objects.create(
        empresa=empresa,
        codfil=1,
        nome=f"Filial {codemp}",
        fantasia=f"F{codemp}",
        cnpj="22.222.222/0001-22",
    )
    return empresa, filial


def _usuario(username, filial, *codenames_qualidade, is_staff=False):
    usuario = User.objects.create_user(
        username=username, password="Senha@2026", filial=filial, is_staff=is_staff
    )
    if codenames_qualidade:
        permissoes = Permission.objects.filter(
            content_type__app_label="qualidade", codename__in=codenames_qualidade
        )
        usuario.user_permissions.add(*permissoes)
    return usuario


def _cursor_fake():
    cursor = MagicMock()
    cursor.description = []
    cursor.fetchall.return_value = []
    return cursor


class LiberarLotesAutorizacaoTests(TestCase):
    def setUp(self):
        empresa, filial = _criar_empresa_filial(301)
        self.empresa = empresa
        self.filial = filial
        ParametrosFilial.objects.create(
            filial=filial, deposito_apontamento_erp="01", origens_area_vermelha="A"
        )
        self.usuario_com_permissao = _usuario(
            "liberar_lotes_com", filial, "pode_acessar_liberacao_lotes"
        )
        self.usuario_sem_permissao = _usuario("liberar_lotes_sem", filial)
        self.usuario_staff = _usuario("liberar_lotes_staff", filial, is_staff=True)

    def test_anonimo_redireciona_para_login(self):
        resposta = self.client.get(reverse("qualidade:liberar_lotes"))

        self.assertEqual(resposta.status_code, 302)

    def test_autenticado_sem_permissao_recebe_403(self):
        self.client.force_login(self.usuario_sem_permissao)

        resposta = self.client.get(reverse("qualidade:liberar_lotes"))

        self.assertEqual(resposta.status_code, 403)

    def test_usuario_com_permissao_acessa_a_tela(self):
        self.client.force_login(self.usuario_com_permissao)
        with (
            patch(
                "setores.qualidade.views.liberar_lotes.cursor_oracle_erp",
                return_value=MagicMock(__enter__=lambda self: _cursor_fake()),
            ),
            patch(
                "setores.qualidade.views.liberar_lotes.carregar_analises_alchemy", return_value={}
            ),
            patch(
                "setores.qualidade.views.liberar_lotes.carregar_locais_armazenamento_wms",
                return_value=({}, ""),
            ),
        ):
            resposta = self.client.get(reverse("qualidade:liberar_lotes"))

        self.assertEqual(resposta.status_code, 200)

    def test_staff_sem_permissao_acessa_a_tela(self):
        self.client.force_login(self.usuario_staff)
        with (
            patch(
                "setores.qualidade.views.liberar_lotes.cursor_oracle_erp",
                return_value=MagicMock(__enter__=lambda self: _cursor_fake()),
            ),
            patch(
                "setores.qualidade.views.liberar_lotes.carregar_analises_alchemy", return_value={}
            ),
            patch(
                "setores.qualidade.views.liberar_lotes.carregar_locais_armazenamento_wms",
                return_value=({}, ""),
            ),
        ):
            resposta = self.client.get(reverse("qualidade:liberar_lotes"))

        self.assertEqual(resposta.status_code, 200)


class LiberarAreaVermelhaAutorizacaoTests(TestCase):
    def setUp(self):
        _, filial = _criar_empresa_filial(302)
        self.filial = filial
        ParametrosFilial.objects.create(filial=filial)
        self.usuario_com_acesso = _usuario(
            "area_vermelha_acesso", filial, "pode_acessar_area_vermelha"
        )
        self.usuario_sem_permissao = _usuario("area_vermelha_sem", filial)
        self.usuario_staff = _usuario("area_vermelha_staff", filial, is_staff=True)

    def test_autenticado_sem_permissao_recebe_403(self):
        self.client.force_login(self.usuario_sem_permissao)

        resposta = self.client.get(reverse("qualidade:area_vermelha"))

        self.assertEqual(resposta.status_code, 403)

    def test_usuario_com_permissao_entra_na_tela(self):
        # POST com action desconhecida devolve redirect sem tocar em Oracle;
        # prova que o decorator deixou o usuário com a permissão de acesso passar.
        self.client.force_login(self.usuario_com_acesso)

        resposta = self.client.post(
            reverse("qualidade:area_vermelha"), {"reuniao_action": "", "action": "invalida"}
        )

        self.assertEqual(resposta.status_code, 302)

    def test_staff_sem_permissao_entra_na_tela(self):
        self.client.force_login(self.usuario_staff)

        resposta = self.client.post(
            reverse("qualidade:area_vermelha"), {"reuniao_action": "", "action": "invalida"}
        )

        self.assertEqual(resposta.status_code, 302)


class BuscarDescricaoTransformacaoAutorizacaoTests(TestCase):
    def setUp(self):
        _, filial = _criar_empresa_filial(303)
        self.filial = filial
        self.usuario_com_acesso = _usuario("descricao_com", filial, "pode_acessar_area_vermelha")
        self.usuario_sem_permissao = _usuario("descricao_sem", filial)
        self.usuario_staff = _usuario("descricao_staff", filial, is_staff=True)

    def test_autenticado_sem_permissao_recebe_403(self):
        self.client.force_login(self.usuario_sem_permissao)

        resposta = self.client.get(reverse("qualidade:buscar_descricao_transformacao"))

        self.assertEqual(resposta.status_code, 403)

    def test_usuario_com_permissao_recebe_lista_vazia_sem_produto(self):
        self.client.force_login(self.usuario_com_acesso)

        resposta = self.client.get(reverse("qualidade:buscar_descricao_transformacao"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["resultados"], [])

    def test_staff_recebe_lista_vazia_sem_produto(self):
        self.client.force_login(self.usuario_staff)

        resposta = self.client.get(reverse("qualidade:buscar_descricao_transformacao"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["resultados"], [])


class BuscarUsuariosErpAutorizacaoTests(TestCase):
    def setUp(self):
        _, filial = _criar_empresa_filial(304)
        self.filial = filial
        self.usuario_so_acesso = _usuario(
            "usuarios_erp_acesso", filial, "pode_acessar_area_vermelha"
        )
        self.usuario_com_destinar = _usuario(
            "usuarios_erp_destinar", filial, "pode_destinar_area_vermelha"
        )
        self.usuario_staff = _usuario("usuarios_erp_staff", filial, is_staff=True)

    def test_usuario_sem_a_permissao_de_destinar_recebe_403(self):
        self.client.force_login(self.usuario_so_acesso)

        resposta = self.client.get(reverse("qualidade:buscar_usuarios_erp"))

        self.assertEqual(resposta.status_code, 403)

    def test_usuario_com_permissao_de_destinar_recebe_lista_vazia_para_termo_curto(self):
        self.client.force_login(self.usuario_com_destinar)

        resposta = self.client.get(reverse("qualidade:buscar_usuarios_erp"), {"q": "ab"})

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["resultados"], [])

    def test_staff_recebe_lista_vazia_para_termo_curto(self):
        self.client.force_login(self.usuario_staff)

        resposta = self.client.get(reverse("qualidade:buscar_usuarios_erp"), {"q": "ab"})

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["resultados"], [])


class ObservacoesEtiquetaAutorizacaoTests(TestCase):
    def setUp(self):
        _, filial = _criar_empresa_filial(305)
        self.filial = filial
        self.usuario_com_permissao = _usuario(
            "observacoes_com", filial, "pode_cadastrar_observacoes_etiqueta"
        )
        self.usuario_sem_permissao = _usuario("observacoes_sem", filial)
        self.usuario_staff = _usuario("observacoes_staff", filial, is_staff=True)

    def test_anonimo_redireciona_para_login(self):
        resposta = self.client.get(reverse("qualidade:observacoes_etiqueta"))

        self.assertEqual(resposta.status_code, 302)

    def test_autenticado_sem_permissao_recebe_403(self):
        self.client.force_login(self.usuario_sem_permissao)

        resposta = self.client.get(reverse("qualidade:observacoes_etiqueta"))

        self.assertEqual(resposta.status_code, 403)

    def test_usuario_com_permissao_acessa_a_tela(self):
        self.client.force_login(self.usuario_com_permissao)

        resposta = self.client.get(reverse("qualidade:observacoes_etiqueta"))

        self.assertEqual(resposta.status_code, 200)

    def test_staff_sem_permissao_acessa_a_tela(self):
        self.client.force_login(self.usuario_staff)

        resposta = self.client.get(reverse("qualidade:observacoes_etiqueta"))

        self.assertEqual(resposta.status_code, 200)


class ConsultaLoteAutorizacaoTests(TestCase):
    def setUp(self):
        _, filial = _criar_empresa_filial(306)
        self.filial = filial
        self.usuario_sem_permissao = _usuario("consulta_lote_sem", filial)
        self.usuario_area_vermelha = _usuario(
            "consulta_lote_av", filial, "pode_acessar_area_vermelha"
        )
        self.usuario_liberacao_lotes = _usuario(
            "consulta_lote_ll", filial, "pode_acessar_liberacao_lotes"
        )

    def test_autenticado_sem_nenhuma_permissao_recebe_403(self):
        self.client.force_login(self.usuario_sem_permissao)

        resposta = self.client.get(reverse("qualidade:consulta_lote"))

        self.assertEqual(resposta.status_code, 403)

    def test_permissao_de_area_vermelha_sozinha_acessa_a_tela(self):
        self.client.force_login(self.usuario_area_vermelha)

        resposta = self.client.get(reverse("qualidade:consulta_lote"))

        self.assertEqual(resposta.status_code, 200)

    def test_permissao_de_liberacao_de_lotes_sozinha_acessa_a_tela(self):
        self.client.force_login(self.usuario_liberacao_lotes)

        resposta = self.client.get(reverse("qualidade:consulta_lote"))

        self.assertEqual(resposta.status_code, 200)


class ImprimirEtiquetasAutorizacaoTests(TestCase):
    def setUp(self):
        _, filial = _criar_empresa_filial(307)
        self.filial = filial
        self.usuario_com_acesso = _usuario("etiquetas_com", filial, "pode_acessar_area_vermelha")
        self.usuario_sem_permissao = _usuario("etiquetas_sem", filial)
        self.usuario_staff = _usuario("etiquetas_staff", filial, is_staff=True)

    def test_etiqueta_individual_sem_permissao_recebe_403(self):
        self.client.force_login(self.usuario_sem_permissao)

        resposta = self.client.get(reverse("qualidade:imprimir_etiqueta_lote", args=[9999]))

        self.assertEqual(resposta.status_code, 403)

    def test_etiqueta_individual_com_permissao_registro_inexistente_404(self):
        self.client.force_login(self.usuario_com_acesso)

        resposta = self.client.get(reverse("qualidade:imprimir_etiqueta_lote", args=[9999]))

        self.assertEqual(resposta.status_code, 404)

    def test_etiqueta_individual_staff_registro_inexistente_404(self):
        self.client.force_login(self.usuario_staff)

        resposta = self.client.get(reverse("qualidade:imprimir_etiqueta_lote", args=[9999]))

        self.assertEqual(resposta.status_code, 404)

    def test_etiquetas_grupo_sem_permissao_recebe_403(self):
        self.client.force_login(self.usuario_sem_permissao)

        resposta = self.client.get(reverse("qualidade:imprimir_etiquetas_grupo"), {"codemp": "abc"})

        self.assertEqual(resposta.status_code, 403)

    def test_etiquetas_grupo_com_permissao_codemp_invalido_400(self):
        self.client.force_login(self.usuario_com_acesso)

        resposta = self.client.get(reverse("qualidade:imprimir_etiquetas_grupo"), {"codemp": "abc"})

        self.assertEqual(resposta.status_code, 400)

    def test_etiquetas_grupo_staff_codemp_invalido_400(self):
        self.client.force_login(self.usuario_staff)

        resposta = self.client.get(reverse("qualidade:imprimir_etiquetas_grupo"), {"codemp": "abc"})

        self.assertEqual(resposta.status_code, 400)
