"""Prova que o `LOGGING` de `SIGMA/settings.py` captura erro 500 real.

Contexto (docs/pendencias-producao.md item 2): sem `LOGGING` customizado, o
Django usa `DEFAULT_LOGGING`, que em produção (`DEBUG=False`) só ativa o
handler `mail_admins` para o logger "django" — e sem `ADMINS` configurado
(item separado, não implementado aqui), `mail_admins()` é um no-op
silencioso. Resultado: uma exceção 500 real não deixa rastro nenhum.

Este teste prova a emissão de ponta a ponta: uma requisição real, por uma
rota sintética que só existe para este teste
(`SIGMA/tests/urls_logging_teste.py`), levanta uma exceção não tratada e o
teste confirma que o logger "django.request" recebe o traceback com o tipo
e a mensagem da exceção — com e sem DEBUG, porque o Django loga o 500
nesse logger independente do valor de DEBUG.
"""

from django.test import Client, SimpleTestCase, override_settings

_ROTA_SINTETICA = "/erro-sintetico-teste-logging/"


@override_settings(ROOT_URLCONF="SIGMA.tests.urls_logging_teste")
class LoggingDeErro500Tests(SimpleTestCase):
    def setUp(self):
        # raise_request_exception=False: por padrão o test Client relança a
        # exceção da view depois da resposta — isso mascararia justamente o
        # que este teste prova (que o handler de exceção do Django já
        # capturou e logou o traceback antes de qualquer coisa chegar aqui).
        self.client = Client(raise_request_exception=False)

    @override_settings(DEBUG=False)
    def test_excecao_nao_tratada_chega_ao_logger_com_debug_desligado(self):
        with self.assertLogs("django.request", level="ERROR") as captura:
            resposta = self.client.get(_ROTA_SINTETICA)

        self.assertEqual(resposta.status_code, 500)
        saida = "\n".join(captura.output)
        self.assertIn("RuntimeError", saida)
        self.assertIn("erro sintético do teste de logging", saida)

    @override_settings(DEBUG=True)
    def test_excecao_nao_tratada_chega_ao_logger_com_debug_ligado(self):
        """DEBUG=True muda a página de resposta, não a emissão do log.

        Cobre a hipótese descartada na investigação registrada em
        docs/pendencias-producao.md item 2: o comportamento em produção não
        é um efeito colateral de DEBUG.
        """
        with self.assertLogs("django.request", level="ERROR") as captura:
            resposta = self.client.get(_ROTA_SINTETICA)

        self.assertEqual(resposta.status_code, 500)
        self.assertIn("RuntimeError", "\n".join(captura.output))
