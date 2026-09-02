import ipaddress
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError


def validar_url_coleta(url):
    """Aceita somente o endpoint HTTP explicitamente autorizado para telemetria."""
    try:
        partes = urlsplit(url)
        porta = partes.port
    except ValueError as exc:
        raise ValidationError("URL HTTP inválida.") from exc

    if partes.scheme not in {"http", "https"} or not partes.hostname:
        raise ValidationError("Informe uma URL HTTP ou HTTPS válida.")
    if partes.username or partes.password or partes.query or partes.fragment:
        raise ValidationError("A URL de telemetria não aceita credenciais, query ou fragmento.")

    host = partes.hostname.lower().rstrip(".")
    porta_padrao = 80 if partes.scheme == "http" else 443
    autoridade = f"{host}:{porta}" if porta is not None else host
    permitidos = set(settings.TELEMETRIA_HOSTS_PERMITIDOS)
    host_na_porta_padrao = porta in {None, porta_padrao}
    em_rede_permitida = False
    try:
        endereco = ipaddress.ip_address(host)
        em_rede_permitida = any(
            "/" in item and endereco in ipaddress.ip_network(item, strict=False)
            for item in permitidos
        )
    except ValueError:
        pass
    if not permitidos or (
        autoridade not in permitidos
        and not (host_na_porta_padrao and host in permitidos)
        and not em_rede_permitida
    ):
        raise ValidationError("O host da URL não está autorizado para telemetria.")

    return url


def mascarar_url_coleta(url):
    """Remove componentes sensíveis de registros legados antes de exibi-los."""
    try:
        partes = urlsplit(url)
        if not partes.scheme or not partes.hostname:
            return "URL inválida"
        autoridade = partes.hostname
        if partes.port is not None:
            autoridade = f"{autoridade}:{partes.port}"
        return f"{partes.scheme}://{autoridade}{partes.path}"
    except ValueError:
        return "URL inválida"
