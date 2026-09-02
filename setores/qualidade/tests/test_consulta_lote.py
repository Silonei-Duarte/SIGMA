"""Testes de setores/qualidade/views/consulta_lote.py, função
chamar_webservice_liberacao_lote.

Achado alto desta rodada de auditoria: o payload da liberação/refugo/
reclassificação de lote era embutido no CDATA do envelope SOAP sem
`escapar_cdata_sapiens`. `montar_dados_webservice_lote` é mockado para isolar
o teste da navegação por Recurso/Filial/Empresa que ela faz — o que se testa
aqui é só a montagem e o escape do envelope, não a resolução de dados do lote.
"""

import re
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from setores.qualidade.models import LiberacaoLote
from setores.qualidade.views import consulta_lote as views


def _resposta_soap(
    texto='<waRetorno>{"status": "OK", "message": "OK"}</waRetorno>', status_code=200
):
    resposta = Mock()
    resposta.status_code = status_code
    resposta.text = texto
    return resposta


def _registro(**overrides):
    dados = {"id": 1, "qtdrefu": 0, "qtdrecl": 0}
    dados.update(overrides)
    return SimpleNamespace(**dados)


@override_settings(SAPIENS_USERNAME="usuario_sapiens", SAPIENS_PASSWORD="segredo_super_secreto")
class ChamarWebserviceLiberacaoLoteTests(SimpleTestCase):
    @patch("producao.services.sapiens.requests.post")
    @patch("setores.qualidade.views.consulta_lote.montar_dados_webservice_lote")
    def test_sequencia_fecha_cdata_nao_quebra_nem_injeta_xml(self, mock_montar, mock_post):
        """Achado alto: ']]>' num dado do lote não pode fechar o CDATA antes da hora."""
        mock_montar.return_value = {"codLot": "L1]]><forjado>1</forjado>"}
        mock_post.return_value = _resposta_soap()

        views.chamar_webservice_liberacao_lote(_registro())

        self.assertEqual(mock_post.call_args.kwargs["timeout"], 180)
        envelope = mock_post.call_args.kwargs["data"].decode("ISO-8859-1")
        raiz = ET.fromstring(envelope)
        self.assertIsNone(raiz.find(".//forjado"))
        self.assertIn("forjado", envelope)

    @patch("producao.services.sapiens.requests.post")
    @patch("setores.qualidade.views.consulta_lote.montar_dados_webservice_lote")
    def test_retorna_sucesso_e_log_da_resposta(self, mock_montar, mock_post):
        mock_montar.return_value = {"codLot": "L1"}
        mock_post.return_value = _resposta_soap()

        sucesso, log = views.chamar_webservice_liberacao_lote(_registro())

        self.assertTrue(sucesso)
        self.assertEqual(log, '{"status": "OK", "message": "OK"}')

    @patch("producao.services.sapiens.requests.post")
    @patch("setores.qualidade.views.consulta_lote.montar_dados_webservice_lote")
    def test_print_de_retorno_sem_watagretorno_mascara_credencial(self, mock_montar, mock_post):
        """Judgment call da auditoria: o fallback (sem <waRetorno>) devolve a resposta
        inteira do Sapiens; se algum dia ela ecoar o envelope enviado (comum em SOAP
        faults), a credencial não pode aparecer no console."""
        mock_montar.return_value = {"codLot": "L1"}
        resposta_com_eco = (
            "<soapenv:Fault><detail><requisicaoOriginal>"
            "<user>usuario_sapiens</user><password>segredo_super_secreto</password>"
            "</requisicaoOriginal></detail></soapenv:Fault>"
        )
        mock_post.return_value = _resposta_soap(texto=resposta_com_eco)

        with patch("builtins.print") as mock_print:
            views.chamar_webservice_liberacao_lote(_registro())

        saida = "\n".join(str(chamada) for chamada in mock_print.call_args_list)
        self.assertNotIn("segredo_super_secreto", saida)
        self.assertIn("<password>***</password>", saida)


class RegistrarResultadoLiberacaoLoteTests(TestCase):
    """Achado seguranca (rodada 4): política mudou — o campo `log` persistido
    tambem precisa estar mascarado, não só o que aparece em tela/print."""

    def _criar_registro(self):
        usuario = get_user_model().objects.create_user(username="tester_lote", password="x")
        return LiberacaoLote.objects.create(
            codemp=1,
            codpro="P1",
            codder="D1",
            coddep="01",
            codigo_integrador="1",
            codlot="L1",
            qtdtot=10,
            usuario=usuario,
        )

    def test_falha_persiste_log_mascarado(self):
        registro = self._criar_registro()
        log_cru = "<user>user_teste</user><password>senha_teste_123</password>"

        views._registrar_resultado_liberacao_lote(registro.id, False, log_cru)

        salvo = LiberacaoLote.objects.get(pk=registro.id).log
        self.assertNotIn("senha_teste_123", salvo)
        self.assertNotIn("user_teste", salvo)
        self.assertIn("<password>***</password>", salvo)
        self.assertIn("<user>***</user>", salvo)

    def test_sucesso_tambem_persiste_log_mascarado(self):
        registro = self._criar_registro()
        log_cru = "<user>user_teste</user><password>senha_teste_123</password>"

        views._registrar_resultado_liberacao_lote(registro.id, True, log_cru)

        salvo = LiberacaoLote.objects.get(pk=registro.id).log
        self.assertNotIn("senha_teste_123", salvo)
        self.assertIn("<password>***</password>", salvo)

    @override_settings(SAPIENS_PASSWORD="senha-sapiens-sintetica-7h4")
    def test_segredo_de_configuracao_tambem_sai_mascarado(self):
        """Máscara única (SIGMA.segredos): senha de configuração no texto de
        erro também sai mascarada, não só credencial de envelope SOAP."""
        registro = self._criar_registro()

        views._registrar_resultado_liberacao_lote(
            registro.id, False, "HTTP 401 com senha-sapiens-sintetica-7h4"
        )

        salvo = LiberacaoLote.objects.get(pk=registro.id).log
        self.assertNotIn("senha-sapiens-sintetica-7h4", salvo)


class EnviarRegistroActionTests(TestCase):
    """Achado baixo de segurança: `registro_id` do POST ia cru para o filter do
    ORM; valor não numérico causava erro de cast no PostgreSQL (500)."""

    def setUp(self):
        from django.contrib.auth.models import Permission

        self.usuario = get_user_model().objects.create_user(
            username="tester_consulta_lote", password="x", is_staff=False
        )
        permissao = Permission.objects.get(
            content_type__app_label="qualidade", codename="pode_acessar_area_vermelha"
        )
        self.usuario.user_permissions.add(permissao)
        self.client.force_login(self.usuario)

    def test_registro_id_nao_numerico_nao_provoca_erro_500(self):
        resposta = self.client.post(
            reverse("qualidade:consulta_lote"),
            {"action": "enviar_registro", "registro_id": "abc"},
        )

        self.assertNotEqual(resposta.status_code, 500)
        self.assertIn(resposta.status_code, (200, 302))

    def test_permissao_de_liberacao_de_lotes_tambem_acessa_consulta(self):
        from django.contrib.auth.models import Permission

        permissao_area_vermelha = Permission.objects.get(
            content_type__app_label="qualidade", codename="pode_acessar_area_vermelha"
        )
        permissao_liberacao_lotes = Permission.objects.get(
            content_type__app_label="qualidade", codename="pode_acessar_liberacao_lotes"
        )
        self.usuario.user_permissions.remove(permissao_area_vermelha)
        self.usuario.user_permissions.add(permissao_liberacao_lotes)

        resposta = self.client.post(reverse("qualidade:consulta_lote"), {"action": "invalida"})

        self.assertEqual(resposta.status_code, 302)

    @patch("setores.qualidade.views.consulta_lote.disparar_envio_lotes")
    def test_usuario_sem_filial_nao_envia_grupo_de_outra_empresa(self, mock_disparar):
        registro = LiberacaoLote.objects.create(
            codemp=99,
            codpro="P1",
            codder="D1",
            coddep="01",
            codigo_integrador="1",
            codlot="L1",
            qtdtot=10,
            usuario=self.usuario,
        )

        resposta = self.client.post(
            reverse("qualidade:consulta_lote"),
            {
                "action": "enviar_grupo",
                "codemp": "99",
                "codlot": "L1",
                "codpro": "P1",
                "codder": "D1",
            },
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(LiberacaoLote.objects.get(pk=registro.pk).status, 0)
        mock_disparar.assert_not_called()


class ConsultaLoteTemplateTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="tester_template_consulta_lote", password="x", is_staff=True
        )
        self.client.force_login(self.usuario)

    def test_pinta_somente_totais_de_grupo_acima_de_zero(self):
        LiberacaoLote.objects.create(
            codemp=1,
            codpro="P1",
            codder="D1",
            coddep="01",
            codigo_integrador="1",
            codlot="L1",
            qtdtot=10,
            qtdlibe=1,
            qtdrecl=2,
            usuario=self.usuario,
        )

        resposta = self.client.get(reverse("qualidade:consulta_lote"))

        self.assertEqual(resposta.status_code, 200)
        linha_grupo = re.search(
            r'<tr class="cursor-pointer[^>]*>(.*?)</tr>', resposta.content.decode(), re.DOTALL
        )

        self.assertIsNotNone(linha_grupo)
        classes_quantidades = re.findall(
            r'<td class="([^"]*)">([012],0000)</td>', linha_grupo.group(1)
        )
        self.assertEqual(
            classes_quantidades,
            [
                (
                    "border border-borda-sutil bg-sucesso-sutil text-sucesso-base font-bold p-2",
                    "1,0000",
                ),
                ("border border-borda-sutil p-2", "0,0000"),
                (
                    "border border-borda-sutil bg-atencao-sutil text-atencao-base font-bold p-2",
                    "2,0000",
                ),
                ("border border-borda-sutil p-2", "0,0000"),
            ],
        )
        linha_filha = re.search(
            r'<tr class="grupo-lote-1 hidden[^>]*>(.*?)</tr>', resposta.content.decode(), re.DOTALL
        )
        self.assertIsNotNone(linha_filha)
        self.assertEqual(
            re.findall(r'<td class="([^"]*)">([012],0000)</td>', linha_filha.group(1)),
            classes_quantidades,
        )
