"""Regressao visual da consulta de lotes."""

import re
from datetime import datetime
from pathlib import Path

import pytest
from django.utils import timezone
from playwright.sync_api import Page, ViewportSize, expect

from e2e_helpers import pixels_iguais
from setores.qualidade.models import LiberacaoLote, Reuniao

pytestmark = pytest.mark.e2e

LOTE_E2E = "E2E-CORES-CONSULTA"
LOTE_AREA_E2E = "E2E-CORES-AREA"
INICIO_REUNIAO_AREA_E2E = timezone.make_aware(datetime(2099, 1, 1, 9, 0))
ARTEFATOS_E2E = Path("test-results") / "consulta-lote"
BASELINES_E2E = Path(__file__).parent / "snapshots" / "consulta-lote"
ARTEFATOS_AREA_E2E = Path("test-results") / "area-vermelha"
BASELINES_AREA_E2E = Path(__file__).parent / "snapshots" / "area-vermelha"


def _criar_lote_para_consulta(django_db_blocker, usuario) -> None:
    with django_db_blocker.unblock():
        LiberacaoLote.objects.filter(codlot=LOTE_E2E).delete()
        lote = LiberacaoLote.objects.create(
            codemp=1,
            codpro="P1",
            codder="D1",
            coddep="01",
            codigo_integrador="1",
            codlot=LOTE_E2E,
            qtdtot=10,
            qtdlibe=1,
            qtdrecl=2,
            usuario=usuario,
        )
        LiberacaoLote.objects.filter(pk=lote.pk).update(
            data_hora=timezone.make_aware(datetime(2026, 1, 1, 10, 0))
        )


def _criar_reuniao_para_area_vermelha(django_db_blocker, usuario) -> None:
    with django_db_blocker.unblock():
        LiberacaoLote.objects.filter(codlot=LOTE_AREA_E2E).delete()
        Reuniao.objects.filter(data_hora_inicio=INICIO_REUNIAO_AREA_E2E).delete()
        reuniao = Reuniao.objects.create(data_hora_inicio=INICIO_REUNIAO_AREA_E2E)
        LiberacaoLote.objects.create(
            codemp=1,
            codpro="P1",
            codder="D1",
            coddep="01",
            codigo_integrador="1",
            codlot=LOTE_AREA_E2E,
            qtdtot=10,
            qtdlibe=1,
            qtdrecl=2,
            reuniao=reuniao,
            usuario=usuario,
            status=LiberacaoLote.Status.NAO_INTEGRADO,
        )


def _selecionar_tema(pagina: Page, tema: str) -> None:
    if tema == "escuro":
        pagina.evaluate("localStorage.setItem('temaSigma', 'escuro')")
    else:
        pagina.evaluate("localStorage.removeItem('temaSigma')")
    pagina.reload()


@pytest.mark.parametrize(
    ("tema", "viewport", "screenshot"),
    [
        ("claro", {"width": 1440, "height": 900}, "consulta-lote-claro-desktop.png"),
        ("claro", {"width": 390, "height": 844}, "consulta-lote-claro-mobile.png"),
        ("escuro", {"width": 1440, "height": 900}, "consulta-lote-escuro-desktop.png"),
        ("escuro", {"width": 390, "height": 844}, "consulta-lote-escuro-mobile.png"),
    ],
)
def test_consulta_lote_colore_somente_numeros_positivos(
    pagina_autenticada: Page,
    servidor_e2e: str,
    usuario_e2e,
    django_db_blocker,
    viewport: ViewportSize,
    tema: str,
    screenshot: str,
):
    _criar_lote_para_consulta(django_db_blocker, usuario_e2e)
    try:
        pagina_autenticada.set_viewport_size(viewport)
        _selecionar_tema(pagina_autenticada, tema)
        pagina_autenticada.goto(
            f"{servidor_e2e}/setores/qualidade/consulta-lote/?search={LOTE_E2E}"
        )

        expect(pagina_autenticada.get_by_role("heading", name="Consulta de Lotes")).to_be_visible()
        linha = pagina_autenticada.locator("tbody > tr.cursor-pointer").filter(has_text=LOTE_E2E)
        expect(linha).to_have_count(1)
        celulas = linha.locator("td")

        expect(celulas.nth(10)).to_have_class(re.compile(r".*text-sucesso-base.*font-bold.*"))
        expect(celulas.nth(12)).to_have_class(re.compile(r".*text-atencao-base.*font-bold.*"))
        expect(celulas.nth(10)).to_have_class(
            re.compile(
                r"^border border-borda-sutil bg-sucesso-sutil text-sucesso-base font-bold p-2$"
            )
        )
        expect(celulas.nth(12)).to_have_class(
            re.compile(
                r"^border border-borda-sutil bg-atencao-sutil text-atencao-base font-bold p-2$"
            )
        )
        expect(celulas.nth(11)).to_have_class(re.compile(r"^border border-borda-sutil p-2$"))
        expect(celulas.nth(13)).to_have_class(re.compile(r"^border border-borda-sutil p-2$"))

        linha.click()
        linha_filha = pagina_autenticada.locator("tbody > tr.grupo-lote-1")
        expect(linha_filha).to_be_visible()
        celulas_filhas = linha_filha.locator("td")
        expect(celulas_filhas.nth(10)).to_have_class(
            re.compile(
                r"^border border-borda-sutil bg-sucesso-sutil text-sucesso-base font-bold p-2$"
            )
        )
        expect(celulas_filhas.nth(12)).to_have_class(
            re.compile(
                r"^border border-borda-sutil bg-atencao-sutil text-atencao-base font-bold p-2$"
            )
        )
        expect(celulas_filhas.nth(11)).to_have_class(re.compile(r"^border border-borda-sutil p-2$"))
        expect(celulas_filhas.nth(13)).to_have_class(re.compile(r"^border border-borda-sutil p-2$"))

        ARTEFATOS_E2E.mkdir(parents=True, exist_ok=True)
        artefato = ARTEFATOS_E2E / screenshot
        pagina_autenticada.screenshot(
            path=str(artefato), animations="disabled", caret="hide", full_page=True
        )
        assert artefato.is_file()
        baseline = BASELINES_E2E / screenshot
        assert baseline.is_file(), f"Baseline visual ausente: {baseline}"
        assert pixels_iguais(artefato.read_bytes(), baseline), (
            f"Regressão visual em {screenshot}; captura atual em {artefato}."
        )
    finally:
        with django_db_blocker.unblock():
            LiberacaoLote.objects.filter(codlot=LOTE_E2E).delete()


@pytest.mark.parametrize(
    ("tema", "viewport", "screenshot"),
    [
        ("claro", {"width": 1440, "height": 900}, "area-vermelha-claro-desktop.png"),
        ("claro", {"width": 390, "height": 844}, "area-vermelha-claro-mobile.png"),
        ("escuro", {"width": 1440, "height": 900}, "area-vermelha-escuro-desktop.png"),
        ("escuro", {"width": 390, "height": 844}, "area-vermelha-escuro-mobile.png"),
    ],
)
def test_area_vermelha_colore_somente_numeros_positivos(
    pagina_autenticada: Page,
    servidor_e2e: str,
    usuario_e2e,
    django_db_blocker,
    viewport: ViewportSize,
    tema: str,
    screenshot: str,
):
    _criar_reuniao_para_area_vermelha(django_db_blocker, usuario_e2e)
    try:
        pagina_autenticada.set_viewport_size(viewport)
        _selecionar_tema(pagina_autenticada, tema)
        pagina_autenticada.goto(f"{servidor_e2e}/setores/qualidade/area-vermelha/")

        expect(
            pagina_autenticada.get_by_role("heading", name="Reunião da Área Vermelha")
        ).to_be_visible()
        linha = pagina_autenticada.locator("tbody > tr.cursor-pointer").filter(
            has_text=LOTE_AREA_E2E
        )
        expect(linha).to_have_count(1)
        celulas = linha.locator("td")
        expect(celulas.nth(8)).to_have_class(
            re.compile(
                r"^border border-borda-sutil bg-sucesso-sutil text-sucesso-base font-bold p-2$"
            )
        )
        expect(celulas.nth(10)).to_have_class(
            re.compile(
                r"^border border-borda-sutil bg-atencao-sutil text-atencao-base font-bold p-2$"
            )
        )
        expect(celulas.nth(9)).to_have_class(re.compile(r"^border border-borda-sutil p-2$"))
        expect(celulas.nth(11)).to_have_class(re.compile(r"^border border-borda-sutil p-2$"))

        ARTEFATOS_AREA_E2E.mkdir(parents=True, exist_ok=True)
        artefato = ARTEFATOS_AREA_E2E / screenshot
        pagina_autenticada.screenshot(
            path=str(artefato), animations="disabled", caret="hide", full_page=True
        )
        assert artefato.is_file()
        baseline = BASELINES_AREA_E2E / screenshot
        assert baseline.is_file(), f"Baseline visual ausente: {baseline}"
        assert pixels_iguais(artefato.read_bytes(), baseline), (
            f"Regressão visual em {screenshot}; captura atual em {artefato}."
        )
    finally:
        with django_db_blocker.unblock():
            LiberacaoLote.objects.filter(codlot=LOTE_AREA_E2E).delete()
            Reuniao.objects.filter(data_hora_inicio=INICIO_REUNIAO_AREA_E2E).delete()
