"""Regressão visual do botão de exclusão no modal de correção."""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_modal_correcao_mantem_icone_exclusao_apos_recriacao(pagina_autenticada: Page):
    """O SVG não pode desaparecer quando o contador atualiza o botão."""
    pagina_autenticada.goto(f"{pagina_autenticada.url.rstrip('/')}/producao/logs-apontamentos/")
    pagina_autenticada.get_by_role("button", name="Corrigir Apontamento").click()

    botao_excluir = pagina_autenticada.locator("#btnExcluirApontamento")
    expect(botao_excluir).to_be_visible()
    expect(botao_excluir.locator("svg")).to_have_count(1)

    pagina_autenticada.evaluate("() => resetarBotaoExcluirApontamento()")

    expect(botao_excluir).to_be_visible()
    expect(botao_excluir.locator("svg")).to_have_count(1)
