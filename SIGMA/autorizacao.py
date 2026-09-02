"""Convenções de autorização das views privadas do SIGMA."""

from collections.abc import Callable, Iterable
from functools import wraps
from typing import Concatenate, ParamSpec, TypeVar

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse

P = ParamSpec("P")
R = TypeVar("R", bound=HttpResponse)

_View = Callable[Concatenate[HttpRequest, P], R]

# Permissão do poder de concessão, compartilhada pelas rotas administrativas.
PERMISSAO_ADMINISTRAR_ACESSOS = "accounts.administrar_acessos"

# Única fonte dos app_labels cujas permissões podem ser concedidas pelas
# telas de gestão de acessos (form de usuário e tela de grupos). Server-side,
# tanto na renderização quanto na gravação — a tela nunca concede permissão
# de app fora desta lista, mesmo em POST forjado.
APPS_PERMISSOES_GESTAO_ACESSOS = (
    "accounts",
    "producao",
    "manutencao",
    "qualidade",
    "pcp",
    "logistica",
    "suprimentos",
)


def permissao_requerida(permissao: str | Iterable[str]) -> Callable[[_View[P, R]], _View[P, R]]:
    """Exige permissão Django e mantém acesso administrativo explícito.

    Aceita um codename ou uma sequência de codenames: a sequência vale como
    OU (qualquer uma libera), preservando o padrão de telas acessíveis por
    mais de um papel.
    """

    codenames = [permissao] if isinstance(permissao, str) else list(permissao)

    def decorator(view: _View[P, R]) -> _View[P, R]:
        @wraps(view)
        def wrapped(request: HttpRequest, *args: P.args, **kwargs: P.kwargs) -> R:
            usuario = request.user
            # Uma chamada por codename: o backend LDAP (django_auth_ldap) não
            # aceita lista em has_perm (faz `perm in set` e explode com
            # TypeError em elemento não hashável).
            autorizado = (
                usuario.is_staff
                or usuario.is_superuser
                or any(usuario.has_perm(codename) for codename in codenames)
            )
            if autorizado:
                return view(request, *args, **kwargs)
            raise PermissionDenied

        return login_required(wrapped)

    return decorator
