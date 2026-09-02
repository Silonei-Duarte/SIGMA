"""Prova o comportamento de fallback controlado de `accounts/auth_backends.py`.

`docs/pendencias-producao.md` item 3 é o precedente que motivou esta
mudança — um achado real de segurança/observabilidade no projeto irmão
SIGT, num backend com o mesmo desenho (AD como fonte primária, senha local
como fallback). É checklist reaproveitável, não prova de que o sigma tinha
o mesmo bug; a prova de que o comportamento existe *aqui* e foi corrigido
é este arquivo de teste.

No encadeamento padrão do Django, um backend que devolve `None` deixa o
próximo backend (`ModelBackend`) ser tentado. `django_auth_ldap.backend.
LDAPBackend` puro devolvia `None` tanto para "AD confirmou credencial
errada" quanto para "AD fora do ar" quanto para "usuário não existe no AD"
— os três casos acabavam testando a senha local, inclusive quando o AD já
tinha negado a credencial de forma definitiva.

Cada teste abaixo não confere só o resultado do login: testar só o
resultado não pega esse tipo de regressão, porque o comportamento de
fallback fica idêntico nos dois casos — só o log muda. Por isso os dois
casos de fallback usam `assertLogs` para provar nível e conteúdo, e os
dois casos de bloqueio provam, via mock, que `ModelBackend.authenticate`
nunca chega a ser chamado.

O caso de AD indisponível mocka `_LDAPUser._get_connection` (não a
property `.dn`): no modo `AUTH_LDAP_USER_SEARCH` usado por este projeto,
`_search_for_user_dn()` captura `ldap.LDAPError` internamente antes de
`.dn` conseguir devolver qualquer coisa — mockar a property com
`side_effect` de exceção simula um caminho que a biblioteca real nunca
percorre nesse modo (ver docstring de `accounts/auth_backends.py`).
"""

import sys
from unittest.mock import PropertyMock, patch

import ldap
from django.contrib.auth import authenticate, get_user_model
from django.test import TestCase, override_settings
from django.views.debug import get_exception_reporter_filter

_BACKENDS = [
    "accounts.auth_backends.LDAPBackendComFallbackControlado",
    "django.contrib.auth.backends.ModelBackend",
]


@override_settings(AUTHENTICATION_BACKENDS=_BACKENDS)
class LDAPBackendComFallbackControladoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="joao.silva", password="SenhaLocalValida1!"
        )

    @patch("django.contrib.auth.backends.ModelBackend.authenticate")
    @patch("django_auth_ldap.backend._LDAPUser._bind_as")
    @patch("django_auth_ldap.backend._LDAPUser.dn", new_callable=PropertyMock)
    def test_ad_confirma_senha_errada_bloqueia_sem_tentar_senha_local(
        self, dn_mock, bind_mock, model_backend_mock
    ):
        dn_mock.return_value = "CN=joao.silva,DC=ipel,DC=local"
        bind_mock.side_effect = ldap.INVALID_CREDENTIALS(
            {"desc": "Invalid credentials", "info": "80090308: LdapErr: ... data 52e"}
        )

        usuario = authenticate(username="joao.silva", password="SenhaLocalValida1!")

        self.assertIsNone(usuario)
        model_backend_mock.assert_not_called()

    @patch("django.contrib.auth.backends.ModelBackend.authenticate")
    @patch("django_auth_ldap.backend._LDAPUser._bind_as")
    @patch("django_auth_ldap.backend._LDAPUser.dn", new_callable=PropertyMock)
    def test_ad_confirma_conta_bloqueada_bloqueia_sem_tentar_senha_local(
        self, dn_mock, bind_mock, model_backend_mock
    ):
        # AD usa o mesmo código LDAP 49/invalidCredentials para conta
        # desativada/bloqueada/expirada, só variando o sub-código "data" no
        # campo de diagnóstico (aqui, 533 = conta desativada).
        dn_mock.return_value = "CN=joao.silva,DC=ipel,DC=local"
        bind_mock.side_effect = ldap.INVALID_CREDENTIALS(
            {"desc": "Invalid credentials", "info": "80090308: LdapErr: ... data 533, v893"}
        )

        usuario = authenticate(username="joao.silva", password="SenhaLocalValida1!")

        self.assertIsNone(usuario)
        model_backend_mock.assert_not_called()

    @patch("django_auth_ldap.backend._LDAPUser._get_connection")
    def test_ad_indisponivel_durante_busca_do_dn_cai_para_senha_local_com_log_warning(
        self, get_connection_mock
    ):
        # `search.execute(self.connection, ...)`, dentro de
        # `_search_for_user_dn()`, avalia `self.connection` como parte da
        # própria expressão — isso inclui o bind da conta de serviço
        # (`_bind()`). Fazer `_get_connection` levantar aqui reproduz uma
        # queda real do AD durante a busca do DN, capturada pela lib
        # internamente (não pela property `.dn`, que nunca vê a exceção).
        get_connection_mock.side_effect = ldap.SERVER_DOWN({"desc": "Can't contact LDAP server"})

        with self.assertLogs("accounts.ldap", level="WARNING") as captura:
            usuario = authenticate(username="joao.silva", password="SenhaLocalValida1!")

        self.assertEqual(usuario, self.usuario)
        self.assertEqual(len(captura.records), 1)
        self.assertEqual(captura.records[0].levelno, 30)  # logging.WARNING
        self.assertIn("indisponível", captura.records[0].getMessage())

    @patch("django_auth_ldap.backend._LDAPUser.dn", new_callable=PropertyMock)
    def test_usuario_nao_existe_no_ad_cai_para_senha_local_com_log_info(self, dn_mock):
        dn_mock.return_value = None

        with self.assertLogs("accounts.ldap", level="INFO") as captura:
            usuario = authenticate(username="joao.silva", password="SenhaLocalValida1!")

        self.assertEqual(usuario, self.usuario)
        self.assertEqual(len(captura.records), 1)
        self.assertEqual(captura.records[0].levelno, 20)  # logging.INFO
        self.assertIn("não encontrado", captura.records[0].getMessage())

    @patch("django_auth_ldap.backend._LDAPUser._get_or_create_user")
    @patch("django_auth_ldap.backend._LDAPUser._check_requirements")
    @patch("django_auth_ldap.backend._LDAPUser._bind_as")
    @patch("django_auth_ldap.backend._LDAPUser.dn", new_callable=PropertyMock)
    def test_ad_confirma_senha_certa_autentica_sem_cair_para_senha_local(
        self, dn_mock, bind_mock, check_mock, get_or_create_mock
    ):
        # Regressão: a distinção de fallback não pode quebrar o login normal
        # quando o AD confirma a credencial.
        dn_mock.return_value = "CN=joao.silva,DC=ipel,DC=local"

        get_or_create_mock.side_effect = lambda *a, **kw: None
        check_mock.side_effect = lambda *a, **kw: None

        with patch("django_auth_ldap.backend._LDAPUser._user", self.usuario, create=True):
            usuario = authenticate(username="joao.silva", password="SenhaCorretaNoAD1!")

        self.assertEqual(usuario, self.usuario)
        bind_mock.assert_called_once()


@override_settings(AUTHENTICATION_BACKENDS=_BACKENDS, DEBUG=False)
class LDAPBackendNaoVazaSenhaNoFrameDeErroTests(TestCase):
    """Achado Alto de `seguranca` sobre o achado 5 (mail_admins): sem
    `@sensitive_variables("password")` em `authenticate_ldap_user`, uma
    exceção não tratada nesse frame (ex.: erro de banco em
    `_get_or_create_user()`) deixaria a senha em texto puro nas variáveis
    locais desse frame — é isso que `AdminEmailHandler` usaria para montar
    o e-mail de admin no dia em que `ADMINS` for configurado.
    `django.contrib.auth.authenticate()` só mascara a variável chamada
    literalmente `credentials`, não `password` num frame mais interno.

    Por que este teste chama `get_exception_reporter_filter(...)
    .get_traceback_frame_variables(...)` diretamente em vez de checar uma
    página ou e-mail renderizado: o `seguranca` mostrou, por execução real,
    que um teste checando o corpo do e-mail (`AdminEmailHandler`,
    `include_html=False`) não é sensível à correção — o template de texto
    do e-mail nunca lista variáveis locais, então o teste passava com ou
    sem o decorator. A verificação correta é no mecanismo em si: a
    mascaração de `sensitive_variables` só é aplicada quando
    `settings.DEBUG is False`
    (`django.views.debug.SafeExceptionReporterFilter.is_active`) —
    confirmado por execução real neste projeto, inclusive que a página
    técnica de depuração com `DEBUG=True` mostra a senha em texto puro
    nas variáveis locais independente deste decorator (a mascaração ali
    é deliberadamente desligada, porque com `DEBUG=True` a página já expõe
    tudo mais). Por isso o teste fixa `DEBUG=False` — é a única condição em
    que este decorator produz efeito algum — e prova o mecanismo (o
    dicionário de variáveis do frame) em vez de um template específico."""

    def setUp(self):
        get_user_model().objects.create_user(username="joao.silva", password="SenhaLocalValida1!")

    @patch("django_auth_ldap.backend._LDAPUser._get_or_create_user")
    @patch("django_auth_ldap.backend._LDAPUser._check_requirements")
    @patch("django_auth_ldap.backend._LDAPUser._bind_as")
    @patch("django_auth_ldap.backend._LDAPUser.dn", new_callable=PropertyMock)
    def test_senha_e_mascarada_no_frame_de_authenticate_ldap_user(
        self, dn_mock, bind_mock, check_mock, get_or_create_mock
    ):
        dn_mock.return_value = "CN=joao.silva,DC=ipel,DC=local"
        bind_mock.side_effect = lambda *a, **kw: None
        check_mock.side_effect = lambda *a, **kw: None
        senha_usada = "SenhaSecretaDoAD9!"
        get_or_create_mock.side_effect = RuntimeError("erro inesperado de banco")

        try:
            authenticate(username="joao.silva", password=senha_usada)
        except RuntimeError:
            traceback_capturado = sys.exc_info()[2]
        else:
            self.fail("esperava RuntimeError propagando de authenticate_ldap_user")

        frame = None
        atual = traceback_capturado
        while atual is not None:
            if atual.tb_frame.f_code.co_name == "authenticate_ldap_user":
                frame = atual.tb_frame
                break
            atual = atual.tb_next
        self.assertIsNotNone(frame, "não encontrou o frame de authenticate_ldap_user na pilha")

        filtro = get_exception_reporter_filter(None)
        variaveis = dict(filtro.get_traceback_frame_variables(None, frame))

        self.assertIn("password", variaveis)
        self.assertEqual(variaveis["password"], filtro.cleansed_substitute)
        self.assertNotIn(senha_usada, repr(variaveis))
