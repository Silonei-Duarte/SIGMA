from unittest.mock import MagicMock, patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from producao.services.sapiens import enviar_soap_sapiens
from SIGMA.autorizacao import permissao_requerida
from SIGMA.integracoes.oracle import ORACLE_ERP, cursor_oracle


class OracleCompartilhadoTests(SimpleTestCase):
    @patch("SIGMA.integracoes.oracle.connections")
    def test_cursor_usa_alias_django(self, connections):
        cursor = MagicMock()
        connections.__getitem__.return_value.cursor.return_value.__enter__.return_value = cursor

        with cursor_oracle(ORACLE_ERP) as resultado:
            self.assertIs(resultado, cursor)

        connections.__getitem__.assert_called_once_with(ORACLE_ERP)

    def test_rejeita_alias_desconhecido(self):
        with self.assertRaises(ValueError):
            with cursor_oracle("desconhecido"):
                pass


class AutorizacaoCompartilhadaTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @staticmethod
    @permissao_requerida("producao.pode_apontar")
    def _view(request):
        return HttpResponse("ok")

    @staticmethod
    @permissao_requerida(
        ("qualidade.pode_acessar_area_vermelha", "qualidade.pode_acessar_liberacao_lotes")
    )
    def _view_multiplas(request):
        return HttpResponse("ok")

    def test_usuario_sem_permissao_recebe_403(self):
        request = self.factory.get("/")
        request.user = MagicMock(is_staff=False, is_superuser=False)
        request.user.has_perm.return_value = False

        with self.assertRaises(PermissionDenied):
            self._view(request)

    def test_staff_eh_autorizado(self):
        request = self.factory.get("/")
        request.user = MagicMock(is_staff=True, is_superuser=False)

        self.assertEqual(self._view(request).status_code, 200)

    def test_anomimo_eh_redirecionado_para_login(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()

        self.assertEqual(self._view(request).status_code, 302)

    def test_multiplas_permissoes_valem_como_ou(self):
        request = self.factory.get("/")
        request.user = MagicMock(is_staff=False, is_superuser=False)
        request.user.has_perm.side_effect = lambda codename: (
            codename == ("qualidade.pode_acessar_liberacao_lotes")
        )

        self.assertEqual(self._view_multiplas(request).status_code, 200)
        self.assertEqual(
            request.user.has_perm.call_args_list[0].args,
            ("qualidade.pode_acessar_area_vermelha",),
        )

    def test_multiplas_permissoes_sem_nenhuma_recebe_403(self):
        request = self.factory.get("/")
        request.user = MagicMock(is_staff=False, is_superuser=False)
        request.user.has_perm.return_value = False

        with self.assertRaises(PermissionDenied):
            self._view_multiplas(request)
        # Uma chamada por codename — o backend LDAP não aceita lista em has_perm.
        self.assertEqual(request.user.has_perm.call_count, 2)


class SapiensCompartilhadoTests(SimpleTestCase):
    @override_settings(SAPIENS_SOAP_VERSION="1.2", SAPIENS_TIMEOUT_SEGUNDOS=17)
    def test_envio_centraliza_timeout_headers_e_envelope(self):
        resposta = MagicMock()
        post = MagicMock(return_value=resposta)

        self.assertIs(
            enviar_soap_sapiens("https://sapiens.test", "<Envelope/>", post=post), resposta
        )

        self.assertEqual(post.call_args.kwargs["timeout"], 17)
        self.assertEqual(
            post.call_args.kwargs["headers"]["Content-Type"],
            'application/soap+xml; charset=ISO-8859-1; action=""',
        )
        resposta.raise_for_status.assert_called_once()

    @override_settings(SAPIENS_SOAP_VERSION="1.1", SAPIENS_TIMEOUT_SEGUNDOS=17)
    def test_envio_aceita_timeout_explicito_e_cabecalho_soap_11(self):
        resposta = MagicMock()
        post = MagicMock(return_value=resposta)

        enviar_soap_sapiens("https://sapiens.test", "<Envelope/>", timeout=9, post=post)

        self.assertEqual(post.call_args.kwargs["timeout"], 9)
        self.assertEqual(
            post.call_args.kwargs["headers"],
            {"Content-Type": "text/xml; charset=ISO-8859-1", "SOAPAction": ""},
        )
        resposta.raise_for_status.assert_called_once()
