def safe_str(obj):
    """
    Converte um objeto para string de forma segura, tratando falhas de decodificação.
    Útil para converter exceções que podem conter bytes não-UTF8.
    """
    try:
        return str(obj or "")
    except UnicodeDecodeError, UnicodeError:
        try:
            return repr(obj)
        except Exception:
            return "[Erro de decodificação de mensagem]"


def safe_decode(payload, encodings=None):
    """
    Tenta decodificar um payload usando uma lista de encodings em ordem.
    """
    if encodings is None:
        encodings = ["utf-8", "cp1252", "iso-8859-1"]

    if payload is None:
        return ""

    if isinstance(payload, str):
        return payload

    for enc in encodings:
        try:
            return payload.decode(enc)
        except UnicodeDecodeError, AttributeError, LookupError:
            continue

    try:
        return bytes(payload).decode("utf-8", errors="replace")
    except TypeError, ValueError:
        return safe_str(payload)


def get_response_text(response, default_encoding="utf-8"):
    """
    Obtém o texto de uma resposta do requests tratando encoding de forma robusta.
    """
    try:
        return response.text
    except UnicodeDecodeError, UnicodeError:
        try:
            response.encoding = response.apparent_encoding or default_encoding
            return response.text
        except Exception:
            return response.content.decode(default_encoding, errors="replace")
