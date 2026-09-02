"""Fixtures e controle de execucao dos testes E2E do SIGMA."""

import asyncio
import os
import sys

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test.testcases import LiveServerThread, _StaticFilesHandler
from playwright.sync_api import Page, expect

USUARIO_E2E = "e2e.administrador"
SENHA_E2E = "SigmaE2E@2026"


def pytest_addoption(parser):
    group = parser.getgroup("e2e", "Testes de navegador")
    group.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="Executa os testes marcados com e2e.",
    )


def pytest_configure(config):
    if not config.getoption("--run-e2e"):
        return

    # O driver síncrono mantém um loop durante as operações no banco de teste.
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
    if sys.platform == "win32":
        # Daphne escolhe Selector, mas o processo Node do Playwright exige Proactor.
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-e2e"):
        # O pytest-django só monta o banco de teste para testes com a marca
        # django_db (ou que usem db/live_server). Os testes e2e usam fixtures
        # próprias (servidor_e2e), então sem a marca o alias default nunca
        # entra no django_db_setup e TODA a suíte e2e roda contra o banco de
        # desenvolvimento — a troca de nome em servidor_e2e virava no-op.
        # transaction=True: sem atomic em volta do teste, as gravações do
        # fixture precisam estar visíveis para a thread do servidor.
        #
        # available_apps com TODOS os apps é o que liga allow_cascade no
        # flush do teardown (TRUNCATE ... CASCADE): as tabelas de schema
        # qualificado (convenção db_table "schema"."tabela" do projeto) não
        # casam com o nome visível no django_table_names, e sem CASCADE o
        # truncar de tabela referenciada por FK quebra. Com todos os apps
        # listados, o registro Django segue irrestrito durante o teste.
        from django.apps import apps

        marca_db = pytest.mark.django_db(
            transaction=True,
            available_apps=[app_config.name for app_config in apps.get_app_configs()],
        )
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(marca_db)
        return

    pular_e2e = pytest.mark.skip(reason="Use --run-e2e para executar testes de navegador.")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(pular_e2e)


@pytest.fixture
def servidor_e2e(django_db_setup, django_db_blocker, settings):
    """Serve o banco de testes sem acionar o flush incompatível entre schemas."""
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "localhost"]
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    with django_db_blocker.unblock():
        # O pytest-django troca o banco só no settings_dict da conexão da
        # thread principal; o LiveServerThread cria conexão própria por thread
        # a partir de settings.DATABASES e atenderia o banco real enquanto os
        # fixtures gravam no banco de teste. O nome é restaurado ao sair.
        nome_original = settings.DATABASES["default"]["NAME"]
        settings.DATABASES["default"]["NAME"] = connections["default"].settings_dict["NAME"]
        server = LiveServerThread("localhost", _StaticFilesHandler)
        server.daemon = True
        server.start()
        server.is_ready.wait()
        if server.error:
            settings.DATABASES["default"]["NAME"] = nome_original
            raise server.error
        yield f"http://{server.host}:{server.port}"
        server.terminate()
        settings.DATABASES["default"]["NAME"] = nome_original


@pytest.fixture
def usuario_e2e(servidor_e2e, django_db_blocker, settings):
    """Cria uma conta local para que o navegador nunca consulte o LDAP."""
    settings.AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
    user_model = get_user_model()
    with django_db_blocker.unblock():
        user, _ = user_model.objects.get_or_create(username=USUARIO_E2E)
        user.set_password(SENHA_E2E)
        user.is_staff = True
        user.is_superuser = True
        user.save()
    yield user
    with django_db_blocker.unblock():
        user_model.objects.filter(pk=user.pk).delete()


@pytest.fixture
def pagina_e2e(servidor_e2e, page: Page) -> tuple[Page, str]:
    """Inicia o servidor antes do processo do navegador."""
    return page, servidor_e2e


@pytest.fixture
def pagina_autenticada(pagina_e2e: tuple[Page, str], usuario_e2e):
    """Abre uma sessao real via formulario de login no servidor de teste."""
    page, server_url = pagina_e2e
    page.goto(f"{server_url}/login/")
    page.get_by_label("Usuário").fill(usuario_e2e.username)
    page.get_by_label("Senha").fill(SENHA_E2E)
    page.get_by_role("button", name="Entrar").click()
    expect(page).to_have_url(f"{server_url}/")
    return page
