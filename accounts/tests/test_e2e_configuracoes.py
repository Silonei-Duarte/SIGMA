"""Fluxos de navegador da tela de configurações da aplicação.

Desenho do dono do produto (2026-08): a chave é parte do código — a tela
não cria nem remove, só edita descrição e valor de chave declarada.
"""

from pathlib import Path

import pytest
from playwright.sync_api import Page, ViewportSize, expect

from accounts.models import ConfiguracaoAplicacao
from e2e_helpers import pixels_iguais

pytestmark = pytest.mark.e2e

CHAVE_LIMIAR = "RELATORIO_FALHAS_LIMIAR_ATRASO_MINUTOS"
TOPICO_EMAIL = "E-mail — Relatórios"
PASTA_SNAPSHOTS = Path(__file__).parent / "snapshots"


def test_configuracoes_abre_autenticada_e_lista_chaves_agrupadas(
    pagina_autenticada: Page,
):
    pagina_autenticada.goto(f"{pagina_autenticada.url.rstrip('/')}/configuracoes/")

    expect(
        pagina_autenticada.get_by_role("heading", name="Configurações da Aplicação")
    ).to_be_visible()
    # Agrupamento por tópico declarado em código.
    expect(pagina_autenticada.get_by_role("heading", name=TOPICO_EMAIL)).to_be_visible()
    expect(pagina_autenticada.get_by_text(CHAVE_LIMIAR)).to_be_visible()
    # Chave conhecida sem linha no banco mostra o padrão do código na
    # listagem — a etiqueta "Padrão" é só da tela de edição. O texto do
    # e-mail aparece 2x na linha (descrição e valor): pego o primeiro.
    expect(pagina_autenticada.get_by_text("ti@empresa.com.br").first).to_be_visible()
    # Sem criar/remover: a única ação por linha é editar.
    expect(pagina_autenticada.get_by_title("Editar").first).to_be_visible()
    assert pagina_autenticada.get_by_title("Remover").count() == 0


def test_configuracoes_edita_chave_conhecida_e_confirma_vigencia(
    pagina_autenticada: Page,
    django_db_blocker,
):
    page = pagina_autenticada
    page.goto(f"{page.url.rstrip('/')}/configuracoes/")

    linha = page.get_by_role("row").filter(has_text=CHAVE_LIMIAR)
    linha.get_by_title("Editar").click()

    # A chave não é campo: chega no título e como texto fixo, e o formulário
    # não oferece entrada para ela.
    expect(page.get_by_role("heading", name=f"Editar {CHAVE_LIMIAR}")).to_be_visible()
    expect(page.get_by_label("Chave")).to_have_count(0)
    page.get_by_label("Valor").fill("7")
    page.get_by_role("button", name="Salvar").click()

    expect(page.get_by_text("passa a valer")).to_be_visible()
    expect(linha.get_by_text("7")).to_be_visible()

    with django_db_blocker.unblock():
        gravada = ConfiguracaoAplicacao.objects.get(chave=CHAVE_LIMIAR)
        assert gravada.valor == "7"
        assert gravada.atualizado_por is not None


def test_configuracoes_volta_chave_ao_padrao_pelo_formulario(
    pagina_autenticada: Page,
    django_db_blocker,
):
    """Ação "Voltar ao padrão" (POST próprio do form de edição): exclui a
    linha salva e a listagem volta a mostrar o padrão do código."""
    with django_db_blocker.unblock():
        ConfiguracaoAplicacao.objects.create(
            chave=CHAVE_LIMIAR, valor="12", descricao="Ajuste manual"
        )

    page = pagina_autenticada
    page.goto(f"{page.url.rstrip('/')}/configuracoes/")

    linha = page.get_by_role("row").filter(has_text=CHAVE_LIMIAR)
    linha.get_by_title("Editar").click()
    page.get_by_role("button", name="Voltar ao padrão").click()

    # De volta à listagem: mensagem de confirmação e o valor padrão.
    expect(page.get_by_text("voltou ao padrão do código")).to_be_visible()
    expect(linha.get_by_text("12")).to_have_count(0)
    expect(linha.get_by_text("5")).to_be_visible()
    with django_db_blocker.unblock():
        assert not ConfiguracaoAplicacao.objects.filter(chave=CHAVE_LIMIAR).exists()


def test_configuracoes_edita_valor_e_descricao_gravados(
    pagina_autenticada: Page,
    django_db_blocker,
):
    with django_db_blocker.unblock():
        gravada = ConfiguracaoAplicacao.objects.create(
            chave="RELATORIO_FALHAS_EMAIL_DESTINATARIOS",
            valor="ana@ipel.com.br",
            descricao="Lista da produção",
        )

    page = pagina_autenticada
    # Após o login a página está na raiz do servidor; capturar a base uma
    # vez — depois do redirect de salvar, page.url já contém /configuracoes/.
    url_base = page.url.rstrip("/")
    page.goto(f"{url_base}/configuracoes/")

    linha = page.get_by_role("row").filter(has_text="RELATORIO_FALHAS_EMAIL_DESTINATARIOS")
    linha.get_by_title("Editar").click()

    # O form abre com os valores vigentes (os gravados, não os defaults).
    expect(page.get_by_label("Valor")).to_have_value("ana@ipel.com.br")
    expect(page.get_by_label("Descrição")).to_have_value("Lista da produção")

    page.get_by_label("Valor").fill("bob@ipel.com.br")
    page.get_by_label("Descrição").fill("Lista atualizada")
    page.get_by_role("button", name="Salvar").click()

    expect(page.get_by_text("passa a valer")).to_be_visible()
    with django_db_blocker.unblock():
        gravada.refresh_from_db()
        assert gravada.valor == "bob@ipel.com.br"
        assert gravada.descricao == "Lista atualizada"
        assert gravada.atualizado_por is not None


@pytest.mark.parametrize(
    ("viewport", "nome_snapshot"),
    [
        ({"width": 1440, "height": 900}, "desktop"),
        ({"width": 390, "height": 844}, "mobile"),
    ],
)
def test_configuracoes_mantem_composicao_em_desktop_e_mobile(
    pagina_autenticada: Page,
    django_db_blocker,
    viewport: ViewportSize,
    nome_snapshot: str,
):
    """Tela agrupada por tópico é mudança visual crítica: composição fixa nas
    duas larguras, com a lista em estado determinístico (sem linhas no banco
    — só as chaves conhecidas com os padrões do código). Baseline ausente é
    criado na primeira execução e o teste falha uma vez para revisão visual —
    mesmo rito dos baselines de produção."""
    with django_db_blocker.unblock():
        ConfiguracaoAplicacao.objects.all().delete()

    page = pagina_autenticada
    page.set_viewport_size(viewport)
    page.goto(f"{page.url.rstrip('/')}/configuracoes/")

    expect(page.get_by_role("heading", name="Configurações da Aplicação")).to_be_visible()

    # A antialiasing da barra de rolagem oscila um pixel entre execuções;
    # escondê-la é aceitável na comparação de composição da tela.
    page.add_style_tag(
        content="html { scrollbar-width: none; } ::-webkit-scrollbar { display: none; }"
    )
    # Sem essa espera, o screenshot pode capturar a troca de fonte/ícone
    # do lucide e gerar falso "regressão visual" (render transitório).
    page.wait_for_load_state("networkidle")
    page.evaluate("() => document.fonts.ready")

    baseline = PASTA_SNAPSHOTS / f"configuracoes-{nome_snapshot}.png"
    screenshot_atual = page.screenshot(
        animations="disabled",
        full_page=True,
    )
    if not baseline.exists():
        baseline.write_bytes(screenshot_atual)
        pytest.fail(f"Baseline visual criado, revise antes de aceitar: {baseline}")
    # Comparação visual tolerante (antialiasing do Chromium varia entre
    # processos) — byte-exata quebraria a cada execução.
    if not pixels_iguais(screenshot_atual, baseline):
        pytest.fail(f"Regressão visual contra o baseline: {baseline}")
