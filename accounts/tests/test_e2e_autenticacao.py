"""Fluxos de navegador da entrada e administracao local."""

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, ViewportSize, expect

pytestmark = pytest.mark.e2e


def test_login_local_redireciona_para_pagina_inicial(pagina_autenticada: Page):
    expect(pagina_autenticada.locator("#sigma-page-main")).to_contain_text("Sistema IPEL de Gestão")


def test_login_alterna_para_tema_escuro_sem_perder_o_controle(
    pagina_e2e: tuple[Page, str],
):
    page, server_url = pagina_e2e
    page.goto(f"{server_url}/login/")

    page.get_by_role("button", name="Usar tema escuro").click()

    expect(page.locator("html")).to_have_class(re.compile(r"tema-escuro"))
    expect(page.get_by_role("button", name="Usar tema claro")).to_be_visible()
    expect(page.locator(".login-efeito-escuro")).to_have_css("opacity", "1")


def test_login_exibe_efeitos_ambientais_sem_mascotes(
    pagina_e2e: tuple[Page, str],
):
    page, server_url = pagina_e2e
    page.goto(f"{server_url}/login/")

    expect(page.locator(".login-efeito-claro")).to_have_count(1)
    expect(page.locator(".login-efeito .login-feixe")).to_have_count(2)
    expect(page.locator(".login-efeito .login-esfera")).to_have_count(2)
    expect(page.locator(".login-efeito .login-particula")).to_have_count(16)
    expect(page.locator(".login-fundo img")).to_have_count(0)
    expect(page.locator("video.login-mascote")).to_have_count(0)


@pytest.mark.parametrize(
    ("viewport", "tema_escuro"),
    [
        ({"width": 1440, "height": 900}, False),
        ({"width": 390, "height": 844}, True),
    ],
)
def test_login_mantem_composicao_em_desktop_e_mobile(
    pagina_e2e: tuple[Page, str],
    viewport: ViewportSize,
    tema_escuro: bool,
):
    page, server_url = pagina_e2e
    page.set_viewport_size(viewport)
    page.goto(f"{server_url}/login/")

    if tema_escuro:
        page.get_by_role("button", name="Usar tema escuro").click()

    expect(page.get_by_role("textbox", name="Usuário")).to_be_visible()
    expect(page.get_by_role("button", name="Entrar")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_grupos_abre_pela_navegacao_autenticada(pagina_autenticada: Page):
    pagina_autenticada.get_by_role("button", name="Administração").hover()
    pagina_autenticada.get_by_role("link", name="Grupos").click()

    expect(
        pagina_autenticada.get_by_role("heading", name="Gerenciar Grupos e Permissões")
    ).to_be_visible()


def test_utilitarios_exibe_email_teste_para_administrador(pagina_autenticada: Page):
    pagina_autenticada.goto(f"{pagina_autenticada.url.rstrip('/')}/utilitarios/")

    expect(pagina_autenticada.locator("#formEmailTeste")).to_be_visible()
    expect(pagina_autenticada.locator("#ativarNotificacao.botao-primario")).to_be_visible()
    expect(pagina_autenticada.locator("#emailTeste.border-borda-padrao")).to_be_visible()


def test_status_services_preserva_painel_e_controles_semanticos(
    pagina_autenticada: Page,
):
    pagina_autenticada.goto(f"{pagina_autenticada.url.rstrip('/')}/services/status/")

    expect(pagina_autenticada.get_by_role("heading", name="Status dos Services")).to_be_visible()
    expect(pagina_autenticada.locator("#autoRefreshSelect.border-borda-padrao")).to_be_visible()
    expect(
        pagina_autenticada.locator('button[title="Manual de operação dos services"]')
    ).to_be_visible()


def test_cadastros_exibem_tooltips_dos_codigos(
    pagina_autenticada: Page,
):
    pagina_autenticada.goto(f"{pagina_autenticada.url.rstrip('/')}/centros-recursos/")

    for dica_id in (
        "dica-codigo-centro",
        "dica-codigo-integrador-centro",
        "dica-codigo-alchemy-centro",
    ):
        ajuda = pagina_autenticada.locator(f'[aria-describedby="{dica_id}"]')
        expect(ajuda).to_be_visible()
        ajuda.hover()
        expect(pagina_autenticada.locator(f"#{dica_id}")).to_have_css("opacity", "1")

    pagina_autenticada.goto(
        f"{pagina_autenticada.url.split('/centros-recursos/')[0]}/recursos/?editar=novo"
    )
    ajuda = pagina_autenticada.locator('[aria-describedby="dica-codigo-recurso"]')
    expect(ajuda).to_be_visible()
    ajuda.hover()
    expect(pagina_autenticada.locator("#dica-codigo-recurso")).to_have_css("opacity", "1")


@pytest.mark.parametrize(
    ("viewport", "nome_snapshot"),
    [
        ({"width": 1440, "height": 900}, "desktop"),
        ({"width": 390, "height": 844}, "mobile"),
    ],
)
def test_usuario_sem_permissao_ve_pagina_403_e_retorna_para_inicio(
    pagina_e2e: tuple[Page, str],
    usuario_e2e,
    django_db_blocker,
    viewport: ViewportSize,
    nome_snapshot: str,
):
    """A negação autenticada usa a página amigável em ambas as larguras suportadas."""
    with django_db_blocker.unblock():
        usuario_e2e.is_staff = False
        usuario_e2e.is_superuser = False
        usuario_e2e.save(update_fields=["is_staff", "is_superuser"])

    page, server_url = pagina_e2e
    page.set_viewport_size(viewport)
    page.goto(f"{server_url}/login/")
    page.get_by_label("Usuário").fill(usuario_e2e.username)
    page.get_by_label("Senha").fill("SigmaE2E@2026")
    page.get_by_role("button", name="Entrar").click()
    expect(page).to_have_url(f"{server_url}/")

    page.goto(f"{server_url}/usuarios/")

    expect(page).to_have_url(f"{server_url}/usuarios/")
    expect(page.get_by_role("heading", name="Acesso não autorizado")).to_be_visible()
    botao_voltar = page.get_by_role("link", name="Voltar")
    expect(botao_voltar).to_be_visible()
    screenshot_atual = page.screenshot(
        animations="disabled",
        full_page=True,
    )
    screenshot_esperado = (
        Path(__file__).parent / "snapshots" / f"acesso-nao-autorizado-{nome_snapshot}.png"
    ).read_bytes()
    assert screenshot_atual == screenshot_esperado

    botao_voltar.click()
    expect(page).to_have_url(f"{server_url}/")
