"""Teste de não vazamento da máscara única de segredos (SIGMA/segredos.py).

Critério de aceite da máscara única de segredos: texto contendo credencial
conhecida sai mascarado na saída do helper, para SMTP/Graph, Oracle,
DJANGO_SECRET_KEY, LDAP, Firebase, credencial SOAP Sapiens e token de URL de
telemetria.

TODO valor de segredo aqui é SINTÉTICO — nenhum segredo real entra em
teste; o segredo é citado pelo nome da variável de configuração.
"""

import warnings
from contextlib import contextmanager

from django.test import SimpleTestCase, override_settings

from producao.utils.sapiens_soap import mascarar_credenciais_soap_sapiens
from SIGMA.segredos import MASCARA, mascarar_segredos
from telemetria.validacao_http import mascarar_url_coleta

# DATABASES sintético: o helper lê PASSWORD dos aliases, não abre conexão.
_DATABASES_SINTETICAS = {
    "default": {"PASSWORD": "senha-banco-local-sintetica-81"},
    "oracle_erp": {"PASSWORD": "senha-oracle-erp-sintetica-42"},
    "oracle_alchemy": {"PASSWORD": "senha-oracle-alchemy-sintetica-33"},
}


@contextmanager
def _databases_sinteticas():
    """Override de DATABASES com o aviso do Django suprimido.

    O UserWarning de override de DATABASES não se aplica aqui: a suíte é
    SimpleTestCase e o helper apenas lê o dict de senhas, sem tocar conexão.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with override_settings(DATABASES=_DATABASES_SINTETICAS):
            yield


class MascaraValoresDeConfiguracaoTests(SimpleTestCase):
    """Texto contendo segredo de configuração sai mascarado — um caso por sistema."""

    def test_senha_do_canal_de_e_mail_sai_mascarada(self):
        with override_settings(MICROSOFT_GRAPH_CLIENT_SECRET="segredo-graph-sintetico-9f2"):
            saida = mascarar_segredos(
                "Falha ao autenticar no Microsoft Graph: segredo-graph-sintetico-9f2 rejeitado"
            )

        self.assertNotIn("segredo-graph-sintetico-9f2", saida)
        self.assertIn(MASCARA, saida)

    def test_senha_do_oracle_erp_sai_mascarada(self):
        with _databases_sinteticas():
            saida = mascarar_segredos(
                "ORA-01017 invalid username/password usando senha-oracle-erp-sintetica-42"
            )

        self.assertNotIn("senha-oracle-erp-sintetica-42", saida)
        self.assertIn(MASCARA, saida)

    def test_senha_do_oracle_alchemy_sai_mascarada(self):
        with _databases_sinteticas():
            saida = mascarar_segredos(
                "DPY-3010 conexão recusada para o usuário com senha-oracle-alchemy-sintetica-33"
            )

        self.assertNotIn("senha-oracle-alchemy-sintetica-33", saida)
        self.assertIn(MASCARA, saida)

    def test_senha_do_banco_local_sai_mascarada(self):
        with _databases_sinteticas():
            saida = mascarar_segredos(
                'connection failed password authentication for user "sigma": '
                "senha-banco-local-sintetica-81"
            )

        self.assertNotIn("senha-banco-local-sintetica-81", saida)
        self.assertIn(MASCARA, saida)

    def test_django_secret_key_sai_mascarada(self):
        with override_settings(SECRET_KEY="chave-secreta-django-sintetica-5t1"):
            saida = mascarar_segredos(
                "InvalidKeyBase64 erro assinando sessao com chave-secreta-django-sintetica-5t1"
            )

        self.assertNotIn("chave-secreta-django-sintetica-5t1", saida)
        self.assertIn(MASCARA, saida)

    def test_senha_curta_sai_mascarada(self):
        with override_settings(SAPIENS_PASSWORD="x"):
            saida = mascarar_segredos("Falha com valor x configurado")

        self.assertNotIn("x", saida)
        self.assertIn(MASCARA, saida)

    def test_segredo_curto_nao_altera_palavras_nem_tags(self):
        with override_settings(SAPIENS_PASSWORD="s"):
            saida = mascarar_segredos("valor s; status <status>ativo</status>")

        self.assertEqual(saida, "valor ***; status <status>ativo</status>")

    def test_django_secret_key_curto_sai_mascarado(self):
        with override_settings(SECRET_KEY="k"):
            saida = mascarar_segredos("Falha assinando sessão com chave k")

        self.assertNotIn("k", saida)
        self.assertIn(MASCARA, saida)

    def test_segredos_sobrepostos_sao_mascarados_do_maior_para_o_menor(self):
        with override_settings(
            MICROSOFT_GRAPH_CLIENT_SECRET="segredo-sintetico-completo",
            SAPIENS_PASSWORD="sintetico-completo",
        ):
            saida = mascarar_segredos("Falha com segredo-sintetico-completo")

        self.assertNotIn("segredo-sintetico-completo", saida)
        self.assertNotIn("sintetico-completo", saida)
        self.assertNotIn("segredo-", saida)
        self.assertIn(MASCARA, saida)

    def test_senha_de_bind_do_ldap_sai_mascarada(self):
        with override_settings(AUTH_LDAP_BIND_PASSWORD="senha-ldap-sintetica-x8k2"):
            saida = mascarar_segredos(
                "LDAPInvalidCredentialsResult bind com senha-ldap-sintetica-x8k2 falhou"
            )

        self.assertNotIn("senha-ldap-sintetica-x8k2", saida)
        self.assertIn(MASCARA, saida)

    def test_caminho_do_arquivo_firebase_sai_mascarado(self):
        with override_settings(
            FIREBASE_CREDENTIALS_FILE="/etc/sigma/credencial-firebase-sintetica.json"
        ):
            saida = mascarar_segredos(
                "DefaultCredentialsErro ao carregar /etc/sigma/credencial-firebase-sintetica.json"
            )

        self.assertNotIn("/etc/sigma/credencial-firebase-sintetica.json", saida)
        self.assertIn(MASCARA, saida)

    def test_nome_do_arquivo_firebase_sai_mascarado_sem_o_caminho(self):
        """Erros de SDK costumam citar só o basename do arquivo de conta de serviço."""
        with override_settings(
            FIREBASE_CREDENTIALS_FILE="/etc/sigma/credencial-firebase-sintetica.json"
        ):
            saida = mascarar_segredos("erro ao ler credencial-firebase-sintetica.json do push")

        self.assertNotIn("credencial-firebase-sintetica.json", saida)
        self.assertIn(MASCARA, saida)

    def test_senha_sapiens_sai_mascarada_em_texto_sem_xml(self):
        with override_settings(SAPIENS_PASSWORD="senha-sapiens-sintetica-7h4"):
            saida = mascarar_segredos(
                "HTTP 401 do Sapiens para o usuário com senha-sapiens-sintetica-7h4"
            )

        self.assertNotIn("senha-sapiens-sintetica-7h4", saida)
        self.assertIn(MASCARA, saida)


class MascaraPorTransporteTests(SimpleTestCase):
    """As máscaras por transporte, agregadas, continuam valendo dentro do helper."""

    def test_credencial_do_envelope_soap_sai_mascarada(self):
        envelope = (
            "<envelope><user>usuario_teste</user><password>senha_teste_123</password></envelope>"
        )

        saida = mascarar_segredos(envelope)

        self.assertNotIn("usuario_teste", saida)
        self.assertNotIn("senha_teste_123", saida)
        self.assertIn("<user>***</user>", saida)
        self.assertIn("<password>***</password>", saida)

    def test_url_de_telemetria_com_token_na_query_sai_mascarada(self):
        saida = mascarar_segredos(
            "coleta falhou em https://balanca.local/coleta?token=token-sintetico-abc123"
        )

        self.assertNotIn("token-sintetico-abc123", saida)
        self.assertIn("https://balanca.local/coleta", saida)

    def test_url_de_telemetria_com_credencial_na_autoridade_sai_mascarada(self):
        saida = mascarar_segredos(
            "GET https://operador:senha-sintetica-a9b1@balanca.local/leitura retornou 500"
        )

        self.assertNotIn("senha-sintetica-a9b1", saida)
        self.assertNotIn("operador:", saida)
        self.assertIn("https://balanca.local/leitura", saida)

    def test_segredo_e_url_no_mesmo_texto_sao_mascarados(self):
        with override_settings(SAPIENS_PASSWORD="senha-sapiens-sintetica-7h4"):
            saida = mascarar_segredos(
                "falha em https://balanca.local/coleta?token=token-sintetico-abc123 "
                "com senha-sapiens-sintetica-7h4"
            )

        self.assertNotIn("token-sintetico-abc123", saida)
        self.assertNotIn("senha-sapiens-sintetica-7h4", saida)


class ContratoDoHelperTests(SimpleTestCase):
    """O que o helper garante para qualquer chamador (log, tela, e-mail)."""

    def test_texto_sem_segredo_sai_intocado(self):
        texto = "ORA-01017: invalid username/password; logon denied"

        self.assertEqual(mascarar_segredos(texto), texto)

    def test_helper_e_idempotente(self):
        texto = (
            "<user>usuario_teste</user><password>senha_teste_123</password> "
            "em https://balanca.local/coleta?token=token-sintetico-abc123"
        )

        primeira = mascarar_segredos(texto)
        segunda = mascarar_segredos(primeira)

        self.assertEqual(primeira, segunda)

    def test_none_vira_texto_vazio(self):
        self.assertEqual(mascarar_segredos(None), "")

    def test_bytes_sao_decodificados_e_mascarados(self):
        with override_settings(SAPIENS_PASSWORD="senha-sapiens-sintetica-7h4"):
            saida = mascarar_segredos(b"resposta bruta com senha-sapiens-sintetica-7h4 dentro")

        self.assertNotIn("senha-sapiens-sintetica-7h4", saida)
        self.assertIn(MASCARA, saida)

    def test_excecao_convertida_por_str_e_mascarada(self):
        with override_settings(SAPIENS_PASSWORD="senha-sapiens-sintetica-7h4"):
            saida = mascarar_segredos(RuntimeError("falhou com senha-sapiens-sintetica-7h4"))

        self.assertNotIn("senha-sapiens-sintetica-7h4", saida)


class WrappersPorTransportePreservadosTests(SimpleTestCase):
    """A consolidação não substitui a abordagem: as máscaras por transporte
    continuam existindo e funcionando nos módulos de origem."""

    def test_mascara_soap_sapiens_continua_mascarando(self):
        saida = mascarar_credenciais_soap_sapiens(
            "<user>usuario_teste</user><password>senha_teste_123</password>"
        )

        self.assertNotIn("senha_teste_123", saida)
        self.assertIn("<password>***</password>", saida)

    def test_mascara_url_coleta_continua_removendo_componentes(self):
        saida = mascarar_url_coleta("http://balanca.local:8080/coleta?token=x&senha=y")

        self.assertEqual(saida, "http://balanca.local:8080/coleta")

    def test_mascara_url_coleta_rejeita_url_invalida(self):
        self.assertEqual(mascarar_url_coleta("nao e uma url"), "URL inválida")
