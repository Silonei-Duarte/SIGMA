"""Regressão visual do card de Status de Recursos.

Mudança visual crítica (CLAUDE.md): trocou `shadow-sm` por `shadow-sutil`
(token do projeto) e o cabeçalho do card ganhou `bg-superficie-afundada` +
`border-b` num container com `overflow-hidden`, para bater com o padrão do
projeto irmão SIGT. Screenshot determinístico desktop e mobile, sempre
gravado (não só na falha), igual à regra do CLAUDE.md para esta categoria.
"""

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Page, expect

from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor
from e2e_helpers import pixels_iguais

pytestmark = pytest.mark.e2e

CODEMP = 920
CODIGO = "E2E-STATUS-RECURSOS"
ARTEFATOS = Path("test-results") / "status-recursos"
BASELINES = Path(__file__).parent / "snapshots" / "status-recursos"


@contextmanager
def _cursor_oracle_vazio():
    """Cursor Oracle de mentira: nenhuma produção lançada para o recurso."""
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    yield cursor


def _limpar_dados():
    Recurso.objects.filter(
        centro_recurso__setor__departamento__filial__empresa__codemp=CODEMP
    ).delete()
    CentroRecurso.objects.filter(setor__departamento__filial__empresa__codemp=CODEMP).delete()
    Setor.objects.filter(departamento__filial__empresa__codemp=CODEMP).delete()
    Departamento.objects.filter(filial__empresa__codemp=CODEMP).delete()
    Filial.objects.filter(empresa__codemp=CODEMP).delete()
    Empresa.objects.filter(codemp=CODEMP).delete()


def _criar_dados(django_db_blocker):
    with django_db_blocker.unblock():
        _limpar_dados()
        empresa = Empresa.objects.create(codemp=CODEMP, nome="E2E Status Recursos", fantasia="E2E")
        filial = Filial.objects.create(
            empresa=empresa, codfil=1, nome="E2E", fantasia="E2E", cnpj="92.000.000/0001-00"
        )
        departamento = Departamento.objects.create(filial=filial, descricao="E2E")
        setor = Setor.objects.create(departamento=departamento, descricao="Setor E2E Status")
        centro = CentroRecurso.objects.create(
            setor=setor, codigo="E2ESR", descricao="Centro E2E Status"
        )
        Recurso.objects.create(
            centro_recurso=centro,
            codigo=CODIGO,
            descricao="Recurso E2E Status",
            ativo=True,
            ordenacao=1,
        )
        return empresa.pk


@pytest.mark.parametrize(
    ("viewport", "nome"),
    [
        ({"width": 1440, "height": 900}, "desktop.png"),
        ({"width": 390, "height": 844}, "mobile.png"),
    ],
)
def test_card_de_status_recursos_mantem_layout_com_tokens_do_projeto(
    pagina_autenticada: Page,
    servidor_e2e: str,
    django_db_blocker,
    monkeypatch,
    viewport,
    nome,
):
    """Card renderizado com pelo menos um recurso mantém o layout visual
    (shadow-sutil, cabeçalho bg-superficie-afundada/border-b, overflow-hidden)
    em desktop e mobile."""
    monkeypatch.setattr("producao.views.status_recursos.cursor_oracle_erp", _cursor_oracle_vazio)
    empresa_id = _criar_dados(django_db_blocker)
    try:
        pagina_autenticada.set_viewport_size(viewport)
        pagina_autenticada.goto(f"{servidor_e2e}/producao/status-recursos/?empresa={empresa_id}")

        card = pagina_autenticada.locator("article").filter(has_text=CODIGO)
        expect(card).to_be_visible()
        expect(card).to_contain_text("Recurso E2E Status")
        expect(card).to_contain_text("Sem atividade")

        # Sem essa espera, o screenshot pode capturar a troca de fonte/ícone
        # do lucide e gerar falso "regressão visual" (render transitório).
        pagina_autenticada.wait_for_load_state("networkidle")
        pagina_autenticada.evaluate("() => document.fonts.ready")

        ARTEFATOS.mkdir(parents=True, exist_ok=True)
        atual = ARTEFATOS / nome
        baseline = BASELINES / nome
        imagem = pagina_autenticada.screenshot(animations="disabled", caret="hide", full_page=True)
        # Mudança visual crítica: screenshot sempre gravado, não só na falha.
        atual.write_bytes(imagem)
        if not baseline.exists():
            baseline.parent.mkdir(parents=True, exist_ok=True)
            baseline.write_bytes(imagem)
            pytest.fail(f"Baseline visual criado, revise antes de aceitar: {baseline}")
        if not pixels_iguais(imagem, baseline):
            pytest.fail(f"Regressão visual: {atual}")
    finally:
        with django_db_blocker.unblock():
            _limpar_dados()
