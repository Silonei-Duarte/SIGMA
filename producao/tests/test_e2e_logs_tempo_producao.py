"""Regressão visual das ações de parada no log de tempo."""

from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from django.utils import timezone
from playwright.sync_api import Page, expect

from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor
from e2e_helpers import pixels_iguais
from producao.models.estrutura import LogTrocaOPAtiva, ParadaMaquina

pytestmark = pytest.mark.e2e

CODIGO = "E2E-SLOTS-PARADA"
ARTEFATOS = Path("test-results") / "logs-tempo-producao"
BASELINES = Path(__file__).parent / "snapshots" / "logs-tempo-producao"


def _limpar_dados():
    recursos = Recurso.objects.filter(
        centro_recurso__setor__departamento__filial__empresa__codemp=901
    )
    ParadaMaquina.objects.filter(recurso__in=recursos).delete()
    LogTrocaOPAtiva.objects.filter(recurso__in=recursos).delete()
    recursos.delete()
    CentroRecurso.objects.filter(setor__departamento__filial__empresa__codemp=901).delete()
    Setor.objects.filter(departamento__filial__empresa__codemp=901).delete()
    Departamento.objects.filter(filial__empresa__codemp=901).delete()
    Filial.objects.filter(empresa__codemp=901).delete()
    Empresa.objects.filter(codemp=901).delete()


def _criar_dados(django_db_blocker, usuario):
    with django_db_blocker.unblock():
        _limpar_dados()
        empresa = Empresa.objects.create(codemp=901, nome="E2E", fantasia="E2E")
        filial = Filial.objects.create(
            empresa=empresa, codfil=1, nome="E2E", fantasia="E2E", cnpj="90.000.000/0001-00"
        )
        departamento = Departamento.objects.create(filial=filial, descricao="E2E")
        setor = Setor.objects.create(departamento=departamento, descricao="E2E")
        centro = CentroRecurso.objects.create(setor=setor, codigo="E2E", descricao="E2E")
        recurso = Recurso.objects.create(centro_recurso=centro, codigo=CODIGO, descricao="E2E")
        agora = timezone.make_aware(datetime(2026, 1, 1, 10, 0))
        periodo = LogTrocaOPAtiva.objects.create(
            recurso=recurso, horario_troca=agora - timedelta(hours=1), horario_saida=agora
        )
        parada = ParadaMaquina.objects.create(
            recurso=recurso,
            inicio=agora - timedelta(minutes=30),
            fim=agora,
            tipo=ParadaMaquina.Tipo.MANUAL,
            usuario=usuario,
        )
        parada.periodos_produtivos.add(periodo)
        # data_hora é auto_now no período e na parada: sem congelar, o
        # timestamp da execução entra no screenshot e a comparação
        # determinística quebra a cada minuto.
        LogTrocaOPAtiva.objects.filter(pk=periodo.pk).update(data_hora=agora)
        ParadaMaquina.objects.filter(pk=parada.pk).update(data_hora=agora)


@pytest.mark.parametrize(
    ("viewport", "nome"),
    [
        ({"width": 1440, "height": 900}, "desktop.png"),
        ({"width": 390, "height": 844}, "mobile.png"),
    ],
)
def test_parada_encerrada_reserva_slots_de_acoes(
    pagina_autenticada: Page,
    servidor_e2e: str,
    usuario_e2e,
    django_db_blocker,
    monkeypatch,
    viewport,
    nome,
):
    monkeypatch.setattr(
        "producao.views.logs_tempo_producao.cursor_oracle_erp", lambda: nullcontext()
    )
    monkeypatch.setattr("producao.signals.notificar_parada_recurso", lambda recurso_id: None)
    _criar_dados(django_db_blocker, usuario_e2e)
    try:
        pagina_autenticada.set_viewport_size(viewport)
        pagina_autenticada.goto(f"{servidor_e2e}/producao/log-tempo-producao/?search={CODIGO}")
        periodo = pagina_autenticada.locator("tr.cursor-pointer").filter(has_text=CODIGO).first
        expect(periodo).to_be_visible()
        periodo.click()
        detalhes = pagina_autenticada.locator('tr[id^="paradas-periodo-"]')
        expect(detalhes).to_be_visible()
        parada = detalhes.locator("tbody > tr").filter(has_text="Manual")
        expect(parada).to_be_visible()
        expect(parada.get_by_title("Excluir parada")).to_be_visible()
        # Ator da fixture é staff+superusuário: as três ações (horários,
        # justificativas e excluir) renderizam como botão — nenhum slot
        # vazio. Slots reservados são o caminho do usuário sem privilégio.
        expect(parada.get_by_title("Alterar horários da parada")).to_be_visible()
        expect(parada.get_by_title("Alterar justificativas")).to_be_visible()
        expect(parada.locator('span.inline-flex.h-9.w-9[aria-hidden="true"]')).to_have_count(0)
        # Sem essa espera, o screenshot pode capturar a troca de fonte/ícone
        # do lucide e gerar falso "regressão visual" (render transitório).
        pagina_autenticada.wait_for_load_state("networkidle")
        pagina_autenticada.evaluate("() => document.fonts.ready")
        ARTEFATOS.mkdir(parents=True, exist_ok=True)
        atual = ARTEFATOS / nome
        baseline = BASELINES / nome
        if not baseline.exists():
            pagina_autenticada.screenshot(
                path=str(baseline), animations="disabled", caret="hide", full_page=True
            )
            pytest.fail(f"Baseline visual criado, revise antes de aceitar: {baseline}")
        imagem = pagina_autenticada.screenshot(animations="disabled", caret="hide", full_page=True)
        if not pixels_iguais(imagem, baseline):
            atual.write_bytes(imagem)
            pytest.fail(f"Regressão visual: {atual}")
    finally:
        with django_db_blocker.unblock():
            _limpar_dados()
