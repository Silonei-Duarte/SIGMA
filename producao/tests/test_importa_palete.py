"""Teste de producao/services/importa_palete.py, método
ImportaPaleteScheduler._importar_paletes_webservice.

O payload enviado hoje é estático (sem dado de usuário), então não há vetor de
injeção real neste momento — mas o CDATA foi corrigido por consistência com o
resto do app (`escapar_cdata_sapiens`). Para provar que a proteção funciona
mesmo assim, o teste força uma sequência ']]>' no valor interpolado, simulando
o dia em que este payload passar a incluir dado dinâmico.
"""

import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from producao.services import importa_palete as svc


def _resposta_soap(
    texto='<waRetorno>{"status": "OK", "total_registros": 3}</waRetorno>',
    status_code=200,
):
    resposta = Mock()
    resposta.ok = status_code == 200
    resposta.status_code = status_code
    resposta.text = texto
    return resposta


@override_settings(SAPIENS_USERNAME="u", SAPIENS_PASSWORD="s")
class ImportarPaletesWebserviceTests(SimpleTestCase):
    @patch("producao.services.sapiens.requests.post")
    @patch.object(svc, "WEBSERVICE_ACAO", "IMPORTAR-PALETES]]><forjado>1</forjado>")
    def test_sequencia_fecha_cdata_nao_quebra_nem_injeta_xml(self, mock_post):
        """Achado (consistência): ']]>' no payload não pode fechar o CDATA antes da hora."""
        mock_post.return_value = _resposta_soap()

        scheduler = svc.ImportaPaleteScheduler.__new__(svc.ImportaPaleteScheduler)
        scheduler._importar_paletes_webservice()

        self.assertEqual(mock_post.call_args.kwargs["timeout"], 180)
        envelope = mock_post.call_args.kwargs["data"].decode("ISO-8859-1")
        raiz = ET.fromstring(envelope)
        self.assertIsNone(raiz.find(".//forjado"))
        self.assertIn("forjado", envelope)

    @patch("producao.services.sapiens.requests.post")
    def test_retorna_total_de_registros_em_caso_de_sucesso(self, mock_post):
        mock_post.return_value = _resposta_soap()

        scheduler = svc.ImportaPaleteScheduler.__new__(svc.ImportaPaleteScheduler)
        total = scheduler._importar_paletes_webservice()

        self.assertEqual(total, 3)

    @patch("producao.services.sapiens.requests.post")
    def test_resposta_sem_status_ok_levanta_excecao(self, mock_post):
        mock_post.return_value = _resposta_soap(
            texto='<waRetorno>{"status": "ERRO", "message": "Falha"}</waRetorno>'
        )

        scheduler = svc.ImportaPaleteScheduler.__new__(svc.ImportaPaleteScheduler)
        with self.assertRaises(RuntimeError):
            scheduler._importar_paletes_webservice()

    @patch("producao.services.sapiens.requests.post")
    def test_falha_http_mascara_credencial_na_excecao(self, mock_post):
        """Achado seguranca: resposta de erro HTTP crua ia direto para RuntimeError/logger.error."""
        mock_post.return_value = _resposta_soap(
            texto="<fault><password>segredo123</password></fault>",
            status_code=500,
        )

        scheduler = svc.ImportaPaleteScheduler.__new__(svc.ImportaPaleteScheduler)
        with self.assertRaises(RuntimeError) as ctx:
            scheduler._importar_paletes_webservice()

        self.assertNotIn("segredo123", str(ctx.exception))
        self.assertIn("<password>***</password>", str(ctx.exception))

    @patch("producao.services.sapiens.requests.post")
    def test_retorno_invalido_mascara_credencial_na_excecao(self, mock_post):
        """Achado seguranca: conteudo cru do waRetorno ia direto para RuntimeError/logger.error."""
        mock_post.return_value = _resposta_soap(
            texto="<waRetorno>nao-e-json <password>segredo123</password></waRetorno>"
        )

        scheduler = svc.ImportaPaleteScheduler.__new__(svc.ImportaPaleteScheduler)
        with self.assertRaises(RuntimeError) as ctx:
            scheduler._importar_paletes_webservice()

        self.assertNotIn("segredo123", str(ctx.exception))
        self.assertIn("<password>***</password>", str(ctx.exception))

    @patch("producao.services.sapiens.requests.post")
    def test_status_diferente_de_ok_sem_message_mascara_credencial(self, mock_post):
        """Achado seguranca (rodada 4): sem 'message', o RuntimeError cai para o
        conteudo cru do waRetorno, que pode ecoar a credencial."""
        mock_post.return_value = _resposta_soap(
            texto=(
                '<waRetorno>{"status": "ERRO", '
                '"detalhe": "<user>user_teste</user><password>senha_teste_123</password>"}'
                "</waRetorno>"
            )
        )

        scheduler = svc.ImportaPaleteScheduler.__new__(svc.ImportaPaleteScheduler)
        with self.assertRaises(RuntimeError) as ctx:
            scheduler._importar_paletes_webservice()

        self.assertNotIn("senha_teste_123", str(ctx.exception))
        self.assertNotIn("user_teste", str(ctx.exception))
        self.assertIn("<password>***</password>", str(ctx.exception))
        self.assertIn("<user>***</user>", str(ctx.exception))

    @patch("producao.services.sapiens.requests.post")
    def test_sem_total_registros_mascara_credencial(self, mock_post):
        """Achado seguranca (rodada 4): 'Retorno sem total de registros' embutia o
        conteudo cru do waRetorno, que pode ecoar a credencial."""
        mock_post.return_value = _resposta_soap(
            texto=(
                '<waRetorno>{"status": "OK", '
                '"detalhe": "<user>user_teste</user><password>senha_teste_123</password>"}'
                "</waRetorno>"
            )
        )

        scheduler = svc.ImportaPaleteScheduler.__new__(svc.ImportaPaleteScheduler)
        with self.assertRaises(RuntimeError) as ctx:
            scheduler._importar_paletes_webservice()

        self.assertNotIn("senha_teste_123", str(ctx.exception))
        self.assertNotIn("user_teste", str(ctx.exception))
        self.assertIn("<password>***</password>", str(ctx.exception))
        self.assertIn("<user>***</user>", str(ctx.exception))
