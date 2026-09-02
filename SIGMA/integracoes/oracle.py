"""Acesso padronizado às conexões Oracle configuradas pelo Django."""

from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connections

ORACLE_ERP = "oracle_erp"
ORACLE_ALCHEMY = "oracle_alchemy"
_ALIASES_VALIDOS = frozenset({ORACLE_ERP, ORACLE_ALCHEMY})


@contextmanager
def cursor_oracle(alias: str) -> Iterator[object]:
    """Entrega cursor gerenciado de um alias Oracle conhecido do Django."""
    if alias not in _ALIASES_VALIDOS:
        raise ValueError(f"Alias Oracle não permitido: {alias}")

    with connections[alias].cursor() as cursor:
        yield cursor


@contextmanager
def cursor_oracle_erp() -> Iterator[object]:
    """Entrega cursor gerenciado para consultas do ERP Senior."""
    with cursor_oracle(ORACLE_ERP) as cursor:
        yield cursor


@contextmanager
def cursor_oracle_alchemy() -> Iterator[object]:
    """Entrega cursor gerenciado para consultas do Oracle Alchemy."""
    with cursor_oracle(ORACLE_ALCHEMY) as cursor:
        yield cursor
