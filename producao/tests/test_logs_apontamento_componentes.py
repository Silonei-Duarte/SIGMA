"""Testes de producao/views/logs_apontamento_componentes.py, função
enviar_integracao_componente.

Achado crítico desta rodada de auditoria: a mesma classe de vulnerabilidade já
corrigida em producao/views/logs_apontamentos.py (credencial do Sapiens em
print() de produção, CDATA sem escape) ainda estava ativa aqui.
"""

import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import Empresa, Filial
from producao.models import ApontamentoComponente
from producao.views import logs_apontamento_componentes as views

User = get_user_model()


def _resposta_soap(
    texto='<waRetorno>{"status": "OK", "message": "OK"}</waRetorno>', status_code=200
):
    resposta = Mock()
    resposta.status_code = status_code
    resposta.text = texto
    return resposta


def _componente(**overrides):
    dados = {
        "codemp": 1,
        "origem": "1",
        "numorp": 100,
        "numcad": 1,
        "codetg": 1,
        "seqrot": 1,
        "hormov": "10:00:00",
        "datmov": "01/01/2026",
        "codigo_integrador": "1",
    }
    dados.update(overrides)
    return SimpleNamespace(**dados)


def _dados_componente():
    return {
        "CodLotCmp": "L1",
        "CodCmpRec": "62709",
        "DerCmpRec": " ",
        "QtdCmp": "10",
    }


class EnviarIntegracaoComponenteTests(SimpleTestCase):
    """Achado crítico: credencial em log e CDATA sem escape no envio de componente."""

    @patch("producao.services.sapiens.requests.post")
    def test_senha_nunca_aparece_em_log_algum(self, mock_post):
        mock_post.return_value = _resposta_soap()

        with self.assertLogs(
            "producao.views.logs_apontamento_componentes", level="DEBUG"
        ) as captura:
            views.enviar_integracao_componente(
                "usuario_sapiens", "segredo_super_secreto", _componente(), _dados_componente()
            )

        saida = "\n".join(captura.output)
        self.assertNotIn("segredo_super_secreto", saida)
        self.assertIn("<password>***</password>", saida)

    @patch("producao.services.sapiens.requests.post")
    def test_usuario_tambem_nao_aparece_em_log(self, mock_post):
        mock_post.return_value = _resposta_soap()

        with self.assertLogs(
            "producao.views.logs_apontamento_componentes", level="DEBUG"
        ) as captura:
            views.enviar_integracao_componente(
                "usuario_sapiens", "segredo_super_secreto", _componente(), _dados_componente()
            )

        saida = "\n".join(captura.output)
        self.assertNotIn("usuario_sapiens", saida)
        self.assertIn("<user>***</user>", saida)

    @patch("producao.services.sapiens.requests.post")
    def test_sequencia_fecha_cdata_nao_quebra_nem_injeta_xml(self, mock_post):
        """Achado alto: ']]>' num dado do componente não pode fechar o CDATA antes da hora."""
        mock_post.return_value = _resposta_soap()

        dados_componente = _dados_componente()
        dados_componente["CodLotCmp"] = "L1]]><forjado>1</forjado>"

        views.enviar_integracao_componente("u", "s", _componente(), dados_componente)

        self.assertEqual(mock_post.call_args.kwargs["timeout"], 180)
        envelope = mock_post.call_args.kwargs["data"].decode("ISO-8859-1")
        raiz = ET.fromstring(envelope)
        self.assertIsNone(raiz.find(".//forjado"))
        self.assertIn("forjado", envelope)

    @patch("producao.services.sapiens.requests.post")
    def test_retorna_texto_da_resposta_do_sapiens(self, mock_post):
        mock_post.return_value = _resposta_soap(texto="<waRetorno>{}</waRetorno>")

        retorno = views.enviar_integracao_componente("u", "s", _componente(), _dados_componente())

        self.assertEqual(retorno, "<waRetorno>{}</waRetorno>")


class RegistrarResultadoComponenteTests(TestCase):
    """Achado seguranca (rodada 4): política mudou — o campo `log` persistido
    tambem precisa estar mascarado, não só o que aparece em log/print."""

    def _criar_componente(self):
        return ApontamentoComponente.objects.create(
            codemp=1,
            origem="1",
            numorp=100,
            codetg=1,
            seqrot=1,
            numcad=1,
            lote="L1",
        )

    def test_falha_persiste_log_mascarado(self):
        componente = self._criar_componente()
        log_cru = "<user>user_teste</user><password>senha_teste_123</password>"

        views._registrar_resultado_componente(componente.id, 0, log_cru)

        salvo = ApontamentoComponente.objects.get(pk=componente.id).log
        self.assertNotIn("senha_teste_123", salvo)
        self.assertNotIn("user_teste", salvo)
        self.assertIn("<password>***</password>", salvo)
        self.assertIn("<user>***</user>", salvo)

    def test_sucesso_tambem_persiste_log_mascarado(self):
        componente = self._criar_componente()
        log_cru = "<user>user_teste</user><password>senha_teste_123</password>"

        views._registrar_resultado_componente(componente.id, 1, log_cru)

        salvo = ApontamentoComponente.objects.get(pk=componente.id).log
        self.assertNotIn("senha_teste_123", salvo)
        self.assertIn("<password>***</password>", salvo)

    @override_settings(SAPIENS_PASSWORD="senha-sapiens-sintetica-7h4")
    def test_segredo_de_configuracao_tambem_sai_mascarado(self):
        """Máscara única (SIGMA.segredos): senha de configuração no texto de
        erro também sai mascarada, não só credencial de envelope SOAP."""
        componente = self._criar_componente()

        views._registrar_resultado_componente(
            componente.id, 0, "HTTP 401 com senha-sapiens-sintetica-7h4"
        )

        salvo = ApontamentoComponente.objects.get(pk=componente.id).log
        self.assertNotIn("senha-sapiens-sintetica-7h4", salvo)


class LogsApontamentoComponentesViewFiltroEmpresaTests(TestCase):
    """GET já filtra por filial (staff vê tudo); faltava teste do fallback
    `.none()` de quem não tem filial associada."""

    def _criar_componente(self, codemp, numorp, status=0):
        return ApontamentoComponente.objects.create(
            codemp=codemp,
            origem="1",
            numorp=numorp,
            codetg=1,
            seqrot=1,
            numcad=1,
            lote="L1",
            status=status,
        )

    def setUp(self):
        empresa_a = Empresa.objects.create(codemp=50, nome="Empresa A", fantasia="EA")
        empresa_b = Empresa.objects.create(codemp=60, nome="Empresa B", fantasia="EB")
        Filial.objects.create(
            empresa=empresa_a,
            codfil=1,
            nome="Filial A",
            fantasia="FA",
            cnpj="33.333.333/0001-33",
        )
        self.componente_empresa_a = self._criar_componente(codemp=empresa_a.codemp, numorp=100)
        self.componente_empresa_b = self._criar_componente(codemp=empresa_b.codemp, numorp=200)

    def test_usuario_sem_filial_ve_lista_vazia(self):
        usuario_sem_filial = User.objects.create_user(
            username="usuario.sem.filial.logs.comp",
            password="Senha@2026",
            is_staff=False,
        )
        self.client.force_login(usuario_sem_filial)

        resposta = self.client.get(reverse("logs_apontamento_componentes"))

        self.assertEqual(len(resposta.context["apontamentos"]), 0)


class LogsApontamentoComponentesPostFiltroEmpresaTests(TestCase):
    """Achado de autorização: as ações de POST (enviar/reenviar, excluir, excluir
    em massa) não checavam se o componente pertencia à filial do usuário — um
    não-staff que soubesse o pk conseguia reenviar ao Sapiens ou excluir um
    componente de outra empresa. Staff continua sem restrição."""

    def _criar_componente(self, codemp, numorp, status=0):
        return ApontamentoComponente.objects.create(
            codemp=codemp,
            origem="1",
            numorp=numorp,
            codetg=1,
            seqrot=1,
            numcad=1,
            lote="L1",
            status=status,
        )

    def setUp(self):
        empresa_a = Empresa.objects.create(codemp=50, nome="Empresa A", fantasia="EA")
        empresa_b = Empresa.objects.create(codemp=60, nome="Empresa B", fantasia="EB")
        filial_a = Filial.objects.create(
            empresa=empresa_a,
            codfil=1,
            nome="Filial A",
            fantasia="FA",
            cnpj="33.333.333/0001-33",
        )

        self.usuario_filial_a = User.objects.create_user(
            username="usuario.filial.a.logs.comp",
            password="Senha@2026",
            is_staff=False,
            filial=filial_a,
        )
        self.usuario_staff = User.objects.create_user(
            username="staff.geral.logs.comp",
            password="Senha@2026",
            is_staff=True,
        )
        self.superusuario_filial_a = User.objects.create_user(
            username="superuser.filial.a.logs.comp",
            password="Senha@2026",
            is_staff=False,
            is_superuser=True,
            filial=filial_a,
        )

        self.componente_empresa_a = self._criar_componente(codemp=empresa_a.codemp, numorp=100)
        self.componente_empresa_b = self._criar_componente(codemp=empresa_b.codemp, numorp=200)

    @patch("producao.views.logs_apontamento_componentes.disparar_envio_componentes")
    def test_enviar_de_outra_filial_nao_encontra_registro(self, mock_disparar):
        self.client.force_login(self.usuario_filial_a)

        resposta = self.client.post(
            reverse("enviar_componente_log", args=[self.componente_empresa_b.pk])
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertNotEqual(resposta.url, reverse("logs_apontamento_componentes"))
        mock_disparar.assert_not_called()
        self.assertEqual(
            ApontamentoComponente.objects.get(pk=self.componente_empresa_b.pk).status, 0
        )

    @patch("producao.views.logs_apontamento_componentes.disparar_envio_componentes")
    def test_enviar_da_propria_filial_funciona(self, mock_disparar):
        self.client.force_login(self.usuario_filial_a)

        self.client.post(reverse("enviar_componente_log", args=[self.componente_empresa_a.pk]))

        mock_disparar.assert_called_once_with([self.componente_empresa_a.pk])

    @patch("producao.views.logs_apontamento_componentes.disparar_envio_componentes")
    def test_staff_enviar_de_qualquer_filial_funciona(self, mock_disparar):
        self.client.force_login(self.usuario_staff)

        self.client.post(reverse("enviar_componente_log", args=[self.componente_empresa_b.pk]))

        mock_disparar.assert_called_once_with([self.componente_empresa_b.pk])

    @patch("producao.views.logs_apontamento_componentes.disparar_envio_componentes")
    def test_enviar_todos_nao_staff_so_processa_propria_filial(self, mock_disparar):
        self.client.force_login(self.usuario_filial_a)

        self.client.post(reverse("enviar_todos_componentes_log"))

        mock_disparar.assert_called_once()
        (ids_enviados,), _ = mock_disparar.call_args
        self.assertIn(self.componente_empresa_a.pk, ids_enviados)
        self.assertNotIn(self.componente_empresa_b.pk, ids_enviados)
        self.assertEqual(
            ApontamentoComponente.objects.get(pk=self.componente_empresa_b.pk).status, 0
        )

    @patch("producao.views.logs_apontamento_componentes.disparar_envio_componentes")
    def test_enviar_todos_staff_processa_todas_as_filiais(self, mock_disparar):
        self.client.force_login(self.usuario_staff)

        self.client.post(reverse("enviar_todos_componentes_log"))

        mock_disparar.assert_called_once_with()

    def test_excluir_de_outra_filial_nao_encontra_registro(self):
        self.client.force_login(self.superusuario_filial_a)

        resposta = self.client.post(
            reverse("excluir_componente_log", args=[self.componente_empresa_b.pk])
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertNotEqual(resposta.url, reverse("logs_apontamento_componentes"))
        self.assertTrue(
            ApontamentoComponente.objects.filter(pk=self.componente_empresa_b.pk).exists()
        )

    def test_excluir_da_propria_filial_funciona(self):
        self.client.force_login(self.superusuario_filial_a)

        self.client.post(reverse("excluir_componente_log", args=[self.componente_empresa_a.pk]))

        self.assertFalse(
            ApontamentoComponente.objects.filter(pk=self.componente_empresa_a.pk).exists()
        )

    def test_excluir_todos_nao_staff_so_apaga_propria_filial(self):
        self.client.force_login(self.superusuario_filial_a)

        self.client.post(reverse("excluir_todos_componentes_log"))

        self.assertFalse(
            ApontamentoComponente.objects.filter(pk=self.componente_empresa_a.pk).exists()
        )
        self.assertTrue(
            ApontamentoComponente.objects.filter(pk=self.componente_empresa_b.pk).exists()
        )
