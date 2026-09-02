import os
import sys
from pathlib import Path

import ldap
from django.core.exceptions import ImproperlyConfigured
from django_auth_ldap.config import ActiveDirectoryGroupType, LDAPSearch
from dotenv import load_dotenv

load_dotenv()
load_dotenv("/etc/sigma/sigma.env")


BASE_DIR = Path(__file__).resolve().parent.parent
APPLICATION_NAME = "SIGMA"

# Segurança
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("Defina DJANGO_SECRET_KEY no ambiente")
# True apenas se DJANGO_DEBUG=True estiver declarado.
DEBUG = os.getenv("DJANGO_DEBUG") == "True"
ALLOWED_HOSTS = [
    host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",") if host.strip()
]


def _env_int_positivo(nome, padrao):
    try:
        valor = int(os.getenv(nome, str(padrao)))
    except ValueError as exc:
        raise ImproperlyConfigured(f"{nome} deve ser um inteiro positivo.") from exc
    if valor <= 0:
        raise ImproperlyConfigured(f"{nome} deve ser um inteiro positivo.")
    return valor


TELEMETRIA_HOSTS_PERMITIDOS = tuple(
    host.strip().lower().rstrip(".")
    for host in os.getenv("TELEMETRIA_HOSTS_PERMITIDOS", "").split(",")
    if host.strip()
)
TELEMETRIA_PAUSA_SUCESSO_SEGUNDOS = _env_int_positivo("TELEMETRIA_PAUSA_SUCESSO_SEGUNDOS", 10)
TELEMETRIA_BACKOFF_ERRO_SEGUNDOS = _env_int_positivo("TELEMETRIA_BACKOFF_ERRO_SEGUNDOS", 10)
TELEMETRIA_TIMEOUT_MAX_SEGUNDOS = _env_int_positivo("TELEMETRIA_TIMEOUT_MAX_SEGUNDOS", 30)
TELEMETRIA_PAUSA_MAX_SEGUNDOS = _env_int_positivo("TELEMETRIA_PAUSA_MAX_SEGUNDOS", 3600)
TELEMETRIA_RESPOSTA_MAX_BYTES = _env_int_positivo("TELEMETRIA_RESPOSTA_MAX_BYTES", 1048576)

# Aplicações
INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "widget_tweaks",
    "accounts.apps.AccountsConfig",
    "django_select2",
    "django.contrib.postgres",
    "producao.apps.ProducaoConfig",
    "telemetria.apps.TelemetriaConfig",
    "setores.apps.SetoresConfig",
    "setores.manutencao.apps.ManutencaoConfig",
    "setores.qualidade.apps.QualidadeConfig",
    "setores.pcp.apps.PcpConfig",
    "setores.logistica.apps.LogisticaConfig",
    "setores.suprimentos.apps.SuprimentosConfig",
    "tailwind",
    "theme",
    "django_browser_reload",
    "channels",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_browser_reload.middleware.BrowserReloadMiddleware",
]

ROOT_URLCONF = "SIGMA.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "SIGMA.context_processors.application_name",
            ],
        },
    }
]

WSGI_APPLICATION = "SIGMA.wsgi.application"
ASGI_APPLICATION = "SIGMA.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

# Banco
_SEARCH_PATH_PADRAO = "producao,manutencao,public"
# A ordem de teste vale tanto para "manage.py test" quanto para a suíte pytest
# (pytest-django carrega este módulo com pytest já importado); checar apenas
# sys.argv quebra os testes E2E, cujos argumentos começam por --run-e2e.
if (len(sys.argv) > 1 and sys.argv[1] == "test") or "pytest" in sys.modules:
    # As migrations históricas de accounts foram criadas quando as tabelas sem
    # schema explícito pertenciam a public. O banco de testes precisa preservar
    # essa ordem para reproduzir corretamente a evolução do schema.
    _SEARCH_PATH_PADRAO = "public,producao,manutencao,qualidade,telemetria"

# Em produção, o PgBouncer não deve receber o parâmetro de inicialização
# "options". O search_path passa a ser definido no papel PostgreSQL do banco
# sigma; o pool passa a reutilizar as conexões reais com segurança.
_USA_PGBOUNCER = os.getenv("POSTGRES_USA_PGBOUNCER", "").strip().lower() in {
    "1",
    "true",
    "sim",
    "yes",
}
_OPCOES_POSTGRES = {"application_name": "sigma-web"}
if not _USA_PGBOUNCER:
    _OPCOES_POSTGRES["options"] = f"-c search_path={_SEARCH_PATH_PADRAO}"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_DEFAULT_NAME"),
        "USER": os.getenv("DB_DEFAULT_USER"),
        "PASSWORD": os.getenv("DB_DEFAULT_PASSWORD"),
        "HOST": os.getenv("DB_DEFAULT_HOST"),
        "PORT": os.getenv("DB_DEFAULT_PORT"),
        "OPTIONS": _OPCOES_POSTGRES,
        "CONN_MAX_AGE": 0 if _USA_PGBOUNCER else 60,
        "CONN_HEALTH_CHECKS": True,
    },
    "oracle_erp": {
        "ENGINE": "django.db.backends.oracle",
        "NAME": os.getenv("ORACLE_ERP_NAME"),
        "USER": os.getenv("ORACLE_ERP_USER"),
        "PASSWORD": os.getenv("ORACLE_ERP_PASSWORD"),
    },
    "oracle_alchemy": {
        "ENGINE": "django.db.backends.oracle",
        "NAME": os.getenv("ORACLE_ALCHEMY_NAME"),
        "USER": os.getenv("ORACLE_ALCHEMY_USER"),
        "PASSWORD": os.getenv("ORACLE_ALCHEMY_PASSWORD"),
    },
}

# Sapiens G5 Services Webservices
SAPIENS_URL_BASE = os.getenv("SAPIENS_URL_BASE")
SAPIENS_USERNAME = os.getenv("SAPIENS_USERNAME")
SAPIENS_PASSWORD = os.getenv("SAPIENS_PASSWORD")
SAPIENS_SOAP_VERSION = os.getenv("SAPIENS_SOAP_VERSION", "1.2")
SAPIENS_TIMEOUT_SEGUNDOS = _env_int_positivo("SAPIENS_TIMEOUT_SEGUNDOS", 30)

# WMS XC API
WMS_XC_API_URL = os.getenv("WMS_XC_API_URL")
WMS_XC_API_USER = os.getenv("WMS_XC_API_USER")


# Internacionalização
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# Arquivos estáticos
STATIC_URL = "/static/"
STATICFILES_DIRS = [
    BASE_DIR / "static",
    BASE_DIR / "theme/static",
]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
    },
}

# Autenticação
AUTH_USER_MODEL = "accounts.CustomUser"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

# Sessões
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365
SESSION_SAVE_EVERY_REQUEST = False

# Segurança (produção)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = os.getenv("DJANGO_HTTPS_ENABLED") == "True"
CSRF_COOKIE_SECURE = os.getenv("DJANGO_HTTPS_ENABLED") == "True"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# ========================
# Logging
# ========================
# Sem este LOGGING, o Django usa o DEFAULT_LOGGING padrão: em produção
# (DEBUG=False) só o handler "mail_admins" fica ativo para o logger
# "django", e sem ADMINS configurado (item separado, não decidido ainda)
# mail_admins() é um no-op silencioso — um 500 real não deixa rastro
# nenhum, nem no journal nem por e-mail. docs/pendencias-producao.md item 2
# registra o mesmo problema encontrado (e corrigido) no projeto irmão SIGT,
# que tem o mesmo desenho de logging Django — é o precedente que motivou
# esta configuração, não prova de que o sigma tinha o mesmo bug. A prova de
# que o sigma emite esse log corretamente é local, por teste de execução
# real (não só inspeção de código): SIGMA/tests/test_logging.py.
#
# "stream" explícito para "ext://sys.stderr" em vez do
# logging.StreamHandler() sem argumento: a forma sem argumento resolve
# sys.stderr uma única vez, no momento em que o handler é instanciado (na
# configuração de logging, durante o import deste módulo). O mesmo padrão
# do handler "error_console" do próprio Gunicorn — referência explícita ao
# stream, não o objeto capturado de antemão.
#
# Logger "django.request" (não "django"): é o logger específico de exceção
# não tratada em view (Django loga 500 nele sempre, incluindo com
# DEBUG=True). Configurar "django" diretamente herdaria o barulho de
# "django.server" (log de acesso do runserver) e "django.security.*"
# (tentativas de acesso suspeitas) no mesmo handler; "propagate": False
# evita duplicar a mesma exceção no logger "django" pai — mas como
# "propagate": False corta o caminho até lá, o handler "mail_admins" do
# Django (só pendurado, por padrão, no logger pai "django") nunca seria
# alcançado. Por isso ele é redeclarado e plugado direto em
# "django.request" abaixo: decisão do sênior de já deixar isso pronto, em
# vez de virar uma armadilha futura (o dia em que alguém configurar ADMINS
# e descobrir, só então, que nenhum e-mail sai porque o logger de 500 não
# alcança o handler). Hoje é inofensivo — sem ADMINS configurado,
# mail_admins() é um no-op silencioso — mas o caminho já fica plugado.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        # Reimplementação do filtro padrão do Django: dictConfig() aplicado
        # sobre este LOGGING roda numa chamada separada da que configura o
        # DEFAULT_LOGGING (django.utils.log.configure_logging faz duas
        # chamadas de dictConfig em sequência) — um logger deste dict só
        # pode referenciar handler/filtro declarado neste MESMO dict,
        # mesmo que o Django já tenha registrado um "mail_admins" e um
        # "require_debug_false" com esse nome antes.
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
    },
    "formatters": {
        "com_timestamp_e_pid": {
            "format": "%(asctime)s [%(process)d] %(levelname)s %(name)s: %(message)s",
        },
    },
    "handlers": {
        "stderr_processo": {
            "level": "ERROR",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "com_timestamp_e_pid",
        },
        # Mesma classe e filtro do handler "mail_admins" padrão do Django
        # (django.utils.log.DEFAULT_LOGGING) — redeclarado aqui pelo motivo
        # explicado acima do bloco.
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
        },
        # Handler próprio para o logger de LDAP (accounts.auth_backends):
        # "stderr_processo" fica em ERROR de propósito (log de exceção 500,
        # alto volume descartado abaixo desse nível). Reutilizá-lo aqui
        # descartaria justamente as mensagens INFO ("usuário não encontrado
        # no AD") e WARNING ("AD indisponível") que essa distinção de nível
        # existe para produzir (docs/pendencias-producao.md item 3.2) — o
        # nível do handler é um teto mínimo, não repassa nada abaixo dele.
        "stderr_ldap": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "com_timestamp_e_pid",
        },
    },
    "loggers": {
        "django.request": {
            "handlers": ["stderr_processo", "mail_admins"],
            "level": "ERROR",
            "propagate": False,
        },
        # accounts.auth_backends.LDAPBackendComFallbackControlado: INFO para
        # "usuário não encontrado no AD" (fallback esperado, sem gravidade),
        # WARNING para "AD indisponível" (precisa aparecer sem se confundir
        # com o INFO acima) e para rejeição autoritativa do AD.
        "accounts.ldap": {
            "handlers": ["stderr_ldap"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# ========================
# Autenticacao AD/LDAP
# ========================
AUTHENTICATION_BACKENDS = [
    "accounts.auth_backends.LDAPBackendComFallbackControlado",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": 8,
        },
    },
    {
        "NAME": "accounts.validators.UppercaseValidator",
    },
    {
        "NAME": "accounts.validators.LowercaseValidator",
    },
    {
        "NAME": "accounts.validators.SymbolValidator",
    },
    {
        "NAME": "accounts.validators.DigitValidator",
    },
]


AUTH_LDAP_SERVER_URI = os.getenv("LDAP_SERVER_URI")
AUTH_LDAP_ENCODING = "utf-8"
AUTH_LDAP_BIND_DN = os.getenv("LDAP_BIND_DN")
AUTH_LDAP_BIND_PASSWORD = os.getenv("LDAP_BIND_PASSWORD")
AUTH_LDAP_USER_DOMAIN = os.getenv("LDAP_USER_DOMAIN", "")
AUTH_LDAP_REQUIRE_GROUP = os.getenv("LDAP_REQUIRE_GROUP") or None
AUTH_LDAP_CA_CERT_FILE = os.getenv("LDAP_CA_CERT_FILE") or None
if AUTH_LDAP_CA_CERT_FILE and not os.path.isabs(AUTH_LDAP_CA_CERT_FILE):
    AUTH_LDAP_CA_CERT_FILE = str(BASE_DIR / AUTH_LDAP_CA_CERT_FILE)

AUTH_LDAP_USER_SEARCH = LDAPSearch(
    os.getenv("LDAP_USER_SEARCH_BASE"),
    ldap.SCOPE_SUBTREE,
    f"(|(sAMAccountName=%(user)s)(userPrincipalName=%(user)s@{AUTH_LDAP_USER_DOMAIN}))",
)

AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
    os.getenv("LDAP_GROUP_SEARCH_BASE", os.getenv("LDAP_USER_SEARCH_BASE")),
    ldap.SCOPE_SUBTREE,
    "(objectClass=group)",
)
AUTH_LDAP_GROUP_TYPE = ActiveDirectoryGroupType()
AUTH_LDAP_USER_ATTR_MAP = {
    "first_name": "givenName",
    "last_name": "sn",
    "email": "mail",
}

AUTH_LDAP_CREATE_USERS = True
AUTH_LDAP_ALWAYS_UPDATE_USER = True
AUTH_LDAP_FIND_GROUP_PERMS = False

AUTH_LDAP_CONNECTION_OPTIONS = {
    ldap.OPT_REFERRALS: 0,
    ldap.OPT_X_TLS_REQUIRE_CERT: ldap.OPT_X_TLS_DEMAND,
}
if AUTH_LDAP_CA_CERT_FILE:
    AUTH_LDAP_CONNECTION_OPTIONS[ldap.OPT_X_TLS_CACERTFILE] = AUTH_LDAP_CA_CERT_FILE
AUTH_LDAP_CONNECTION_OPTIONS[ldap.OPT_X_TLS_NEWCTX] = 0

ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_DEMAND)
ldap.set_option(ldap.OPT_REFERRALS, 0)
ldap.set_option(ldap.OPT_NETWORK_TIMEOUT, 5)
if AUTH_LDAP_CA_CERT_FILE:
    ldap.set_option(ldap.OPT_X_TLS_CACERTFILE, AUTH_LDAP_CA_CERT_FILE)
ldap.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
try:
    ldap.set_option(0x0015, "utf-8")  # OPT_ENCODING (fallback)
except Exception:
    pass


# ========================
# E-mail (notificações)
# ========================
EMAIL_BACKEND = "SIGMA.mail_backends.MicrosoftGraphEmailBackend"
MICROSOFT_GRAPH_TENANT_ID = os.getenv("MICROSOFT_GRAPH_TENANT_ID", "")
MICROSOFT_GRAPH_CLIENT_ID = os.getenv("MICROSOFT_GRAPH_CLIENT_ID", "")
MICROSOFT_GRAPH_CLIENT_SECRET = os.getenv("MICROSOFT_GRAPH_CLIENT_SECRET", "")
MICROSOFT_GRAPH_MAIL_SENDER = os.getenv("MICROSOFT_GRAPH_MAIL_SENDER", "")
MICROSOFT_GRAPH_TIMEOUT = int(os.getenv("MICROSOFT_GRAPH_TIMEOUT", "30"))
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", f"SIGMA <{MICROSOFT_GRAPH_MAIL_SENDER}>")
PORTAL_BASE_URL = os.getenv("PORTAL_BASE_URL", "http://127.0.0.1:8000")

# Firebase Cloud Messaging
FIREBASE_CREDENTIALS_FILE = os.getenv("FIREBASE_CREDENTIALS_FILE", "")
SIGMA_APK_FILE = os.getenv(
    "SIGMA_APK_FILE",
    str(BASE_DIR / "artifacts" / "SIGMA.apk"),
)


# Cache obrigatório para o django_select2
SELECT2_CACHE_BACKEND = "default"

TAILWIND_APP_NAME = "theme"
NPM_BIN_PATH = os.getenv("NPM_BIN_PATH", r"C:\Program Files\nodejs\npm.cmd")
