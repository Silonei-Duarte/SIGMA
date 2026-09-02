"""Transporte SOAP único para o ERP Senior/Sapiens."""

import logging
from collections.abc import Callable

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from producao.utils.sapiens_soap import ajustar_envelope_soap_sapiens, headers_soap_sapiens

logger = logging.getLogger(__name__)

_FAULT_DIALETO_SOAP = "Unable to internalize message"


def _registrar_diagnostico_dialeto_soap(resposta: requests.Response) -> None:
    """Registra causa acionavel sem expor corpo da resposta SOAP."""
    if _FAULT_DIALETO_SOAP not in resposta.text:
        return

    logger.error(
        "Sapiens recusou mensagem SOAP; confira SAPIENS_SOAP_VERSION contra o binding "
        "WSDL do endpoint (1.1 usa text/xml e SOAPAction; 1.2 usa application/soap+xml)."
    )


def enviar_soap_sapiens(
    url: str,
    envelope: str,
    *,
    timeout: int | None = None,
    validar_status: bool = True,
    post: Callable[..., requests.Response] | None = None,
) -> requests.Response:
    """Envia envelope SOAP com versão, cabeçalhos e timeout centralizados."""
    if not url:
        raise ImproperlyConfigured("A URL do serviço Sapiens não foi configurada.")

    resposta = (post or requests.post)(
        url,
        data=ajustar_envelope_soap_sapiens(envelope).encode("iso-8859-1"),
        headers=headers_soap_sapiens(),
        timeout=timeout if timeout is not None else settings.SAPIENS_TIMEOUT_SEGUNDOS,
    )
    _registrar_diagnostico_dialeto_soap(resposta)
    if validar_status:
        resposta.raise_for_status()
    return resposta
