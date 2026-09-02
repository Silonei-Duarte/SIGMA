"""E2E: cadastro malicioso não é interpretado como HTML nas cascatas AJAX."""

import pytest
from django.db import connections
from django.urls import reverse
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

PAYLOAD_XSS = '<img src=x onerror="window.__xss_explorado = true">'
USUARIO = "e2e.cascata"
SENHA = "SigmaCascata@2026"

SEARCH_PATH_TESTE = "-c search_path=public,producao,manutencao,qualidade,telemetria"


@pytest.fixture
def cenario_cascata(pagina_e2e, django_db_blocker):
    """Usuário e cadastros gravados com commit real no banco de teste.

    O TestCase do pytest-django mantém a transação da conexão padrão aberta
    até o rollback, invisível ao thread do servidor. Um alias espelho em
    autocommit grava os dados do cenário commitados; a limpeza no teardown
    dispensa o flush global, que o TimescaleDB não suporta.
    """
    from django.contrib.auth import get_user_model

    from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor

    config = dict(connections.databases["default"])
    config["NAME"] = connections["default"].settings_dict["NAME"]
    config["OPTIONS"] = {**dict(config.get("OPTIONS") or {}), "options": SEARCH_PATH_TESTE}
    config["CONN_MAX_AGE"] = 0
    connections.databases["e2e_dados"] = config

    with django_db_blocker.unblock():
        usuario, _ = (
            get_user_model()
            .objects.using("e2e_dados")
            .get_or_create(
                username=USUARIO,
                defaults={"first_name": "E2E", "last_name": "Cascata"},
            )
        )
        usuario.set_password(SENHA)
        usuario.is_staff = True
        usuario.is_superuser = True
        usuario.save(using="e2e_dados")

        empresa, _ = Empresa.objects.using("e2e_dados").get_or_create(
            codemp=909,
            defaults={"nome": "Empresa XSS", "fantasia": "EXSS"},
        )
        filial, _ = Filial.objects.using("e2e_dados").get_or_create(
            empresa=empresa,
            codfil=9,
            defaults={
                "nome": "Filial XSS",
                "fantasia": "FXSS",
                "cnpj": "00.000.000/0000-09",
            },
        )
        departamento, _ = Departamento.objects.using("e2e_dados").get_or_create(
            filial=filial, descricao=PAYLOAD_XSS
        )
        setor, _ = Setor.objects.using("e2e_dados").get_or_create(
            departamento=departamento, descricao="Setor XSS"
        )
        centro, _ = CentroRecurso.objects.using("e2e_dados").get_or_create(
            setor=setor, codigo="CXSS", defaults={"descricao": "Centro XSS"}
        )
        recurso, _ = Recurso.objects.using("e2e_dados").get_or_create(
            centro_recurso=centro,
            codigo="RXSS",
            defaults={"descricao": PAYLOAD_XSS},
        )
        empresa_id, filial_id, departamento_id = empresa.pk, filial.pk, departamento.pk
        setor_id, centro_id, recurso_id = setor.pk, centro.pk, recurso.pk

    yield usuario, empresa_id, filial_id, departamento_id, setor_id, centro_id, recurso_id

    with django_db_blocker.unblock():
        for modelo, filtros in (
            (Recurso, {"pk": recurso_id}),
            (CentroRecurso, {"pk": centro_id}),
            (Setor, {"pk": setor_id}),
            (Departamento, {"filial_id": filial_id}),
            (Filial, {"pk": filial_id}),
            (Empresa, {"pk": empresa_id}),
            (get_user_model(), {"pk": usuario.pk}),
        ):
            modelo.objects.using("e2e_dados").filter(**filtros).delete()
    del connections.databases["e2e_dados"]


def _assert_payload_e_texto(page: Page, seletor: str):
    alvo = page.locator(f"{seletor} option").filter(has_text=PAYLOAD_XSS)
    expect(alvo).to_have_count(1)
    assert alvo.text_content() == PAYLOAD_XSS
    assert page.locator(f"{seletor} img").count() == 0
    assert page.evaluate("window.__xss_explorado === undefined")


def _assert_recurso_e_texto(page: Page):
    alvo = page.locator("#id_recursos span").filter(has_text=PAYLOAD_XSS)
    expect(alvo).to_have_count(1)
    assert alvo.text_content() == PAYLOAD_XSS
    assert page.locator("#id_recursos img").count() == 0
    assert page.evaluate("window.__xss_explorado === undefined")


def test_descricao_maliciosa_vira_texto_nas_tres_cascatas(
    pagina_e2e: tuple[Page, str],
    cenario_cascata,
):
    """A descrição do departamento chega ao <select> como texto, nunca como HTML."""
    page, server_url = pagina_e2e
    usuario, empresa_id, filial_id, departamento_id, setor_id, centro_id, _ = cenario_cascata

    page.goto(f"{server_url}/login/")
    page.get_by_label("Usuário").fill(usuario.username)
    page.get_by_label("Senha").fill(SENHA)
    page.get_by_role("button", name="Entrar").click()
    expect(page).to_have_url(f"{server_url}/")

    # Recursos: a filial carrega departamentos dinamicamente.
    page.goto(f"{server_url}{reverse('lista_recursos')}?editar=novo")
    page.select_option("#id_filial", str(filial_id))
    _assert_payload_e_texto(page, "#id_departamento")

    # Turnos: cascata completa empresa -> filial -> departamento.
    page.goto(f"{server_url}{reverse('lista_turnos')}")
    page.select_option("#id_empresa", str(empresa_id))
    expect(page.locator(f"#id_filial option[value='{filial_id}']")).to_have_count(1)
    page.select_option("#id_filial", str(filial_id))
    _assert_payload_e_texto(page, "#id_departamento")

    # Horas extras: neutraliza apenas o submit automático para deixar a
    # atualização AJAX concluir e validar o option criado por textContent.
    page.goto(f"{server_url}{reverse('lista_horas_extras')}")
    page.evaluate("document.getElementById('filtroForm').submit = () => {}")
    page.select_option("#id_empresa", str(empresa_id))
    expect(page.locator(f"#id_filial option[value='{filial_id}']")).to_have_count(1)
    page.select_option("#id_filial", str(filial_id))
    _assert_payload_e_texto(page, "#id_departamento")
    page.select_option("#id_departamento", str(departamento_id))
    expect(page.locator(f"#id_setor option[value='{setor_id}']")).to_have_count(1)
    page.select_option("#id_setor", str(setor_id))
    expect(page.locator(f"#id_centro option[value='{centro_id}']")).to_have_count(1)
    page.select_option("#id_centro", str(centro_id))
    _assert_recurso_e_texto(page)
