"""Backend LDAP com controle explícito de fallback para senha local.

Contexto: `docs/pendencias-producao.md` item 3 registra esse mesmo bug
encontrado (e corrigido) no projeto irmão SIGT, num backend com o mesmo
desenho (AD como fonte primária, senha local como fallback). É o
precedente/checklist que motivou aplicar a correção aqui de forma
preventiva — não é prova de que o sigma tinha o mesmo incidente; a prova
de que o comportamento abaixo é o que o sigma realmente executa está em
`accounts/tests/test_auth_backends.py`.

No encadeamento padrão de `AUTHENTICATION_BACKENDS`, quando um backend
devolve `None`, o Django tenta o próximo backend automaticamente.
`django_auth_ldap.backend.LDAPBackend` puro devolve `None` tanto para "AD
respondeu que a credencial está errada" quanto para "AD está fora do ar"
quanto para "usuário não existe no AD" — os três casos acabavam permitindo
que `ModelBackend` tentasse a senha local em seguida, inclusive quando o AD
já tinha negado a credencial de forma definitiva.

Regra implementada aqui:
- AD responde de forma autoritativa que a credencial é inválida (senha
  errada, ou qualquer motivo de bloqueio que o AD embuta na mesma resposta —
  conta desativada, bloqueada, expirada; o Active Directory usa o mesmo
  código LDAP 49/invalidCredentials para todos esses casos, só variando o
  sub-código no campo de diagnóstico) -> bloqueia o login imediatamente,
  nunca tenta a senha local.
- AD não respondeu (timeout, conexão recusada, erro de servidor) -> cai
  para a senha local.
- Usuário não existe no AD -> cai para a senha local.

Mecanismo: `django.core.exceptions.PermissionDenied` levantado dentro de um
backend de autenticação interrompe a cadeia de `AUTHENTICATION_BACKENDS`
(mecanismo nativo do Django em `django.contrib.auth.authenticate()`); os
backends seguintes nunca chegam a ser chamados.

Ponto de extensão: `LDAPBackend.authenticate_ldap_user()` é o hook
documentado para subclasses (delega, por padrão, para
`_LDAPUser.authenticate()`). Esse método padrão da biblioteca não expõe a
distinção que precisamos: tanto "usuário não encontrado" quanto "credencial
rejeitada" viram a mesma exceção interna (`_LDAPUser.AuthenticationFailed`),
capturada e descartada com `logger.debug` sem sinal nenhum.

Detalhe que já causou um bug aqui e por isso fica documentado: no modo de
configuração deste projeto (`AUTH_LDAP_USER_SEARCH`, sem
`AUTH_LDAP_USER_DN_TEMPLATE`), a property `_LDAPUser.dn` NUNCA levanta
`ldap.LDAPError` — `_search_for_user_dn()` (chamada por trás da property)
já captura qualquer `ldap.LDAPError` internamente (erro ao religar a
conexão de serviço ou ao buscar o usuário), loga um `WARNING` no logger
próprio da lib (`django_auth_ldap`, fora do nosso `LOGGING`) e devolve
`None` — indistinguível de "usuário não encontrado" para quem só olha o
retorno de `.dn`. Um `try/except ldap.LDAPError` em volta do acesso a
`.dn` é código morto nesse modo (não dispara nunca) e foi removido daqui.
A distinção correta vem do signal público `django_auth_ldap.backend.
ldap_error`, que a própria lib dispara nesse mesmo ponto interno
(contexto `"search_for_user_dn"`) — é o mecanismo oficial da biblioteca
para observar esse erro sem reimplementar a busca do DN.

Fora isso, este override chama os mesmos passos internos que
`_LDAPUser.authenticate()` chamaria (`.dn`, `_bind_as`,
`_check_requirements`, `_get_or_create_user()`), na mesma ordem, mas com
captura de exceção própria em cada etapa — não reimplementa a conexão, a
busca nem o `simple_bind_s`, que continuam inteiramente a cargo da
biblioteca. Uma lacuna conhecida e aceita: o passo de
`REFRESH_DN_ON_BIND` (recarregar o DN após bind bem-sucedido em modo
"simple bind", `django_auth_ldap/backend.py::_authenticate_user_dn`) não é
reproduzido — hoje é inofensivo porque este projeto não configura
`AUTH_LDAP_USER_DN_TEMPLATE` (`_using_simple_bind_mode()` sempre `False`,
logo aquele trecho da lib nunca rodaria de qualquer forma), mas se algum
dia esse modo passar a ser usado, este backend precisa ser revisto.
"""

import logging
import threading

import ldap
from django.core.exceptions import PermissionDenied
from django.views.decorators.debug import sensitive_variables
from django_auth_ldap.backend import LDAPBackend, _LDAPUser, ldap_error

logger = logging.getLogger("accounts.ldap")

# Estado por thread: Signal.send() invoca os receivers de forma síncrona na
# mesma thread que emitiu o sinal, então threading.local() garante que cada
# requisição só enxergue o próprio erro de busca, mesmo com o receiver
# conectado uma única vez (nível de módulo) e compartilhado entre threads.
_estado_busca_dn = threading.local()


def _capturar_erro_de_busca_dn(sender, context, user, request, exception, **kwargs):
    """Recebe o signal que `_search_for_user_dn` dispara ao engolir um
    `ldap.LDAPError` internamente (ver docstring do módulo). Sem isso, um
    AD fora do ar durante a busca do DN fica indistinguível de "usuário não
    encontrado" — os dois fazem `.dn` devolver `None`."""
    if context == "search_for_user_dn":
        _estado_busca_dn.exception = exception


ldap_error.connect(
    _capturar_erro_de_busca_dn,
    dispatch_uid="accounts.auth_backends.capturar_erro_busca_dn",
)


class LDAPBackendComFallbackControlado(LDAPBackend):
    """Só permite fallback para senha local quando o AD não respondeu ou
    quando o usuário não existe nele; qualquer resposta autoritativa do AD
    negando a credencial bloqueia o login ali mesmo."""

    # A senha em texto puro fica numa variável local chamada "password"
    # nesta função (usada em `_bind_as`). `django.contrib.auth.authenticate()`
    # já é decorado com `@sensitive_variables("credentials")`, mas isso só
    # mascara a variável chamada literalmente "credentials" NAQUELE frame —
    # cada frame do traceback precisa da própria proteção. Sem isto, uma
    # exceção não tratada aqui dentro (ex.: erro de banco em
    # `_get_or_create_user()`) faria o Django incluir a senha em texto puro
    # no e-mail de admin (`AdminEmailHandler.get_traceback_frame_variables`)
    # no dia em que `ADMINS` for configurado — hoje é inofensivo porque
    # `ADMINS` está vazio (mail_admins() é no-op), mas a proteção não pode
    # depender dessa configuração continuar vazia para sempre.
    @sensitive_variables("password")
    def authenticate_ldap_user(self, ldap_user: _LDAPUser, password):
        username = ldap_user._username

        _estado_busca_dn.exception = None
        dn = ldap_user.dn
        erro_busca = getattr(_estado_busca_dn, "exception", None)
        _estado_busca_dn.exception = None

        if erro_busca is not None:
            logger.warning(
                "AD indisponível ao localizar o usuário %s no diretório (%s); "
                "login pode cair para a senha local.",
                username,
                erro_busca,
            )
            return None

        if dn is None:
            logger.info(
                "Usuário %s não encontrado no AD; login pode cair para a senha local.",
                username,
            )
            return None

        sticky = self.settings.BIND_AS_AUTHENTICATING_USER
        try:
            ldap_user._bind_as(dn, password, sticky=sticky)
        except ldap.INVALID_CREDENTIALS:
            logger.warning(
                "AD rejeitou a credencial de %s (senha incorreta ou conta "
                "desativada/bloqueada/expirada); login bloqueado sem tentar "
                "a senha local.",
                username,
            )
            raise PermissionDenied("Credenciais rejeitadas pelo Active Directory.") from None
        except ldap.LDAPError:
            logger.warning(
                "AD indisponível ao autenticar %s; login pode cair para a senha local.",
                username,
            )
            return None

        try:
            ldap_user._check_requirements()
            ldap_user._get_or_create_user()
        except _LDAPUser.AuthenticationFailed:
            logger.warning(
                "AD autenticou %s mas negou acesso (grupo exigido não satisfeito ou "
                "restrição equivalente); login bloqueado sem tentar a senha local.",
                username,
            )
            raise PermissionDenied("Acesso negado pelo Active Directory.") from None
        except ldap.LDAPError:
            logger.warning(
                "AD indisponível ao concluir a autenticação de %s; "
                "login pode cair para a senha local.",
                username,
            )
            return None

        return ldap_user._user
