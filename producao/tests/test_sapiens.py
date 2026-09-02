from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from producao.services.sapiens import enviar_soap_sapiens


@override_settings(SAPIENS_SOAP_VERSION="1.2", SAPIENS_TIMEOUT_SEGUNDOS=180)
class EnviarSoapSapiensTests(SimpleTestCase):
    def test_soap_1_1_ajusta_namespace_e_headers(self):
        resposta = Mock(text="<waRetorno>OK</waRetorno>")
        post = Mock(return_value=resposta)

        with override_settings(SAPIENS_SOAP_VERSION="1.1"):
            enviar_soap_sapiens(
                "https://sapiens.exemplo/g5-senior-services",
                '<soapenv:Envelope xmlns:soapenv="http://www.w3.org/2003/05/soap-envelope"/>',
                post=post,
            )

        self.assertEqual(
            post.call_args.kwargs["headers"],
            {"Content-Type": "text/xml; charset=ISO-8859-1", "SOAPAction": ""},
        )
        self.assertIn(
            b"http://schemas.xmlsoap.org/soap/envelope/",
            post.call_args.kwargs["data"],
        )

    def test_soap_1_2_ajusta_namespace_e_headers(self):
        resposta = Mock(text="<waRetorno>OK</waRetorno>")
        post = Mock(return_value=resposta)

        with override_settings(SAPIENS_SOAP_VERSION="1.2"):
            enviar_soap_sapiens(
                "https://sapiens.exemplo/g5-senior-services",
                '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"/>',
                post=post,
            )

        self.assertEqual(
            post.call_args.kwargs["headers"],
            {"Content-Type": 'application/soap+xml; charset=ISO-8859-1; action=""'},
        )
        self.assertIn(
            b"http://www.w3.org/2003/05/soap-envelope",
            post.call_args.kwargs["data"],
        )

    def test_versao_invalida_e_recusada_antes_da_chamada(self):
        with override_settings(SAPIENS_SOAP_VERSION="invalida"):
            with self.assertRaisesMessage(
                ImproperlyConfigured, "SAPIENS_SOAP_VERSION deve ser 1.1 ou 1.2."
            ):
                enviar_soap_sapiens(
                    "https://sapiens.exemplo/g5-senior-services",
                    "<soapenv:Envelope/>",
                )

    def test_registra_diagnostico_para_fault_de_dialeto(self):
        resposta = Mock(text="<fault>Unable to internalize message</fault>")

        with patch("producao.services.sapiens.logger.error") as log_error:
            enviar_soap_sapiens(
                "https://sapiens.exemplo/g5-senior-services",
                "<soapenv:Envelope/>",
                validar_status=False,
                post=Mock(return_value=resposta),
            )

        log_error.assert_called_once_with(
            "Sapiens recusou mensagem SOAP; confira SAPIENS_SOAP_VERSION contra o binding "
            "WSDL do endpoint (1.1 usa text/xml e SOAPAction; 1.2 usa application/soap+xml)."
        )

    def test_nao_registra_diagnostico_para_resposta_sem_fault_de_dialeto(self):
        resposta = Mock(text="<waRetorno>OK</waRetorno>")

        with patch("producao.services.sapiens.logger.error") as log_error:
            enviar_soap_sapiens(
                "https://sapiens.exemplo/g5-senior-services",
                "<soapenv:Envelope/>",
                validar_status=False,
                post=Mock(return_value=resposta),
            )

        log_error.assert_not_called()
