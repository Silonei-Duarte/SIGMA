import re

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

SOAP_1_1_NAMESPACE = "http://schemas.xmlsoap.org/soap/envelope/"
SOAP_1_2_NAMESPACE = "http://www.w3.org/2003/05/soap-envelope"


def versao_soap_sapiens():
    versao = str(getattr(settings, "SAPIENS_SOAP_VERSION", "1.2")).strip()
    if versao not in {"1.1", "1.2"}:
        raise ImproperlyConfigured("SAPIENS_SOAP_VERSION deve ser 1.1 ou 1.2.")
    return versao


def ajustar_envelope_soap_sapiens(envelope):
    namespace = SOAP_1_1_NAMESPACE if versao_soap_sapiens() == "1.1" else SOAP_1_2_NAMESPACE
    return envelope.replace(SOAP_1_1_NAMESPACE, namespace).replace(SOAP_1_2_NAMESPACE, namespace)


def headers_soap_sapiens():
    if versao_soap_sapiens() == "1.1":
        return {
            "Content-Type": "text/xml; charset=ISO-8859-1",
            "SOAPAction": "",
        }
    return {"Content-Type": 'application/soap+xml; charset=ISO-8859-1; action=""'}


def escapar_cdata_sapiens(valor):
    """Neutraliza a sequência ']]>' antes de embutir um valor num bloco CDATA.

    Sem isso, um dado de entrada (ex.: lote digitado) contendo ']]>' fecharia o
    CDATA antes do esperado e quebraria (ou injetaria estrutura em) o XML
    enviado ao Sapiens. É a forma padrão de escapar ']]>' dentro de um CDATA:
    fecha o bloco, escreve a sequência como texto fora dele e reabre outro.
    """
    return str(valor).replace("]]>", "]]]]><![CDATA[>")


def mascarar_credenciais_soap_sapiens(texto):
    """Substitui o conteúdo de <user>/<password> por '***' para uso em log.

    O envelope SOAP carrega usuário e senha do serviço em texto (só escapado
    para XML, não mascarado) — nunca logar o envelope/retorno cru.
    """
    texto = re.sub(r"(<user>).*?(</user>)", r"\1***\2", texto, flags=re.IGNORECASE | re.DOTALL)
    texto = re.sub(
        r"(<password>).*?(</password>)", r"\1***\2", texto, flags=re.IGNORECASE | re.DOTALL
    )
    return texto
