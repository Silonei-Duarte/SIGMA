"""E2E: editor da regra de parada automática mostra conectores E/OU/NÃO
entre os itens e traduz a regra para uma fórmula em português ao vivo.

Relato do usuário: "não consigo entender onde o E/OU se aplica" — o teste
garante que o chip de conector aparece entre os itens irmãos e que o
parágrafo da fórmula acompanha a montagem da regra.
"""

import pytest
from django.db import connections
from django.urls import reverse
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

USUARIO = "e2e.editor.regra"
SENHA = "SigmaEditorRegra@2026"

SEARCH_PATH_TESTE = "-c search_path=public,producao,manutencao,qualidade,telemetria"


@pytest.fixture
def cenario_editor_regra(pagina_e2e, django_db_blocker):
    """Usuário e cadastros gravados com commit real no banco de teste.

    Mesmo rito do test_e2e_cascadas_seguras: alias espelho em autocommit
    grava dados visíveis ao thread do servidor, e a limpeza no teardown
    dispensa o flush global, que o TimescaleDB não suporta.
    """
    from django.contrib.auth import get_user_model

    from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor
    from producao.models import RegraParadaRecurso
    from telemetria.models import FonteColetaHTTP, Sensor, SensorRecurso

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
                defaults={"first_name": "E2E", "last_name": "EditorRegra"},
            )
        )
        usuario.set_password(SENHA)
        usuario.is_staff = True
        usuario.is_superuser = True
        usuario.save(using="e2e_dados")

        empresa, _ = Empresa.objects.using("e2e_dados").get_or_create(
            codemp=910,
            defaults={"nome": "Empresa Editor Regra", "fantasia": "EER"},
        )
        filial, _ = Filial.objects.using("e2e_dados").get_or_create(
            empresa=empresa,
            codfil=10,
            defaults={
                "nome": "Filial Editor Regra",
                "fantasia": "FER",
                "cnpj": "00.000.000/0000-10",
            },
        )
        departamento, _ = Departamento.objects.using("e2e_dados").get_or_create(
            filial=filial, descricao="Departamento Editor Regra"
        )
        setor, _ = Setor.objects.using("e2e_dados").get_or_create(
            departamento=departamento, descricao="Setor Editor Regra"
        )
        centro, _ = CentroRecurso.objects.using("e2e_dados").get_or_create(
            setor=setor, codigo="CER", defaults={"descricao": "Centro Editor Regra"}
        )
        recurso, _ = Recurso.objects.using("e2e_dados").get_or_create(
            centro_recurso=centro,
            codigo="RER",
            defaults={"descricao": "Recurso Editor Regra"},
        )
        # Sensor vinculado: a aba só oferece sensores ativos ligados ao
        # próprio recurso, e a condição nova já nasce com o primeiro deles
        # selecionado — é ele que deve aparecer na fórmula.
        fonte, _ = FonteColetaHTTP.objects.using("e2e_dados").get_or_create(
            url="http://e2e-editor-regra.local/status",
            defaults={"filial": filial},
        )
        sensor, _ = Sensor.objects.using("e2e_dados").get_or_create(
            fonte=fonte,
            chave_origem="tempZona1",
            defaults={
                "nome": "Temperatura Zona 1",
                "tipo_valor": Sensor.TipoValor.DECIMAL,
                "filial": filial,
            },
        )
        SensorRecurso.objects.using("e2e_dados").get_or_create(recurso=recurso, sensor=sensor)
        ids = {
            "usuario": usuario.pk,
            "empresa": empresa.pk,
            "filial": filial.pk,
            "departamento": departamento.pk,
            "setor": setor.pk,
            "centro": centro.pk,
            "recurso": recurso.pk,
            "fonte": fonte.pk,
            "sensor": sensor.pk,
        }

    yield ids

    with django_db_blocker.unblock():
        # Ordem de FK: vínculo → regra → sensor → fonte → cascata de cadastro.
        SensorRecurso.objects.using("e2e_dados").filter(recurso_id=ids["recurso"]).delete()
        RegraParadaRecurso.objects.using("e2e_dados").filter(recurso_id=ids["recurso"]).delete()
        Sensor.objects.using("e2e_dados").filter(pk=ids["sensor"]).delete()
        FonteColetaHTTP.objects.using("e2e_dados").filter(pk=ids["fonte"]).delete()
        Recurso.objects.using("e2e_dados").filter(pk=ids["recurso"]).delete()
        CentroRecurso.objects.using("e2e_dados").filter(pk=ids["centro"]).delete()
        Setor.objects.using("e2e_dados").filter(pk=ids["setor"]).delete()
        Departamento.objects.using("e2e_dados").filter(pk=ids["departamento"]).delete()
        Filial.objects.using("e2e_dados").filter(pk=ids["filial"]).delete()
        Empresa.objects.using("e2e_dados").filter(pk=ids["empresa"]).delete()
        get_user_model().objects.using("e2e_dados").filter(pk=ids["usuario"]).delete()
    del connections.databases["e2e_dados"]


def test_editor_regra_parada_mostra_conectores_e_formula(
    pagina_e2e: tuple[Page, str],
    cenario_editor_regra,
):
    """Monta condição + subgrupo na aba Parada Automática e prova o chip de
    conector E entre os itens e a fórmula em português ao vivo."""
    page, server_url = pagina_e2e

    page.goto(f"{server_url}/login/")
    page.get_by_label("Usuário").fill(USUARIO)
    page.get_by_label("Senha").fill(SENHA)
    page.get_by_role("button", name="Entrar").click()
    expect(page).to_have_url(f"{server_url}/")

    editor = page.locator("#editor-regra-parada-automatica")
    formula = page.locator("#formula-regra-parada-automatica")

    # Hash abre a aba direto (openTab no carregamento da página).
    page.goto(
        f"{server_url}{reverse('lista_recursos')}?editar={cenario_editor_regra['recurso']}"
        "#tab-parada-automatica"
    )
    expect(editor).to_be_visible()
    expect(formula).to_contain_text("PARADO SE")
    expect(formula).to_contain_text("Regra vazia: adicione uma condição ou grupo para começar.")

    # Primeira condição: o botão diz aonde o item cai.
    expect(page.get_by_title("Adiciona uma condição dentro DESTE grupo")).to_have_count(1)
    editor.get_by_role("button", name="+ Condição").click()
    page.get_by_label("Valor esperado").fill("80")

    # A fórmula acompanha a edição: sensor pré-selecionado + comparação
    # padrão "igual a" + valor digitado, na ordem da frase. Só o nome
    # amigável aparece — a chave entre parênteses confundia o usuário.
    expect(formula).to_contain_text("Temperatura Zona 1 igual a 80")
    expect(formula).not_to_contain_text("(tempZona1)")

    # Subgrupo dentro da raiz: com dois itens, o conector E aparece entre
    # eles — o pedido central ("onde o E se aplica"). A legenda do operador
    # aparece no quadro da raiz e no do subgrupo novo (ambos em E).
    editor.get_by_role("button", name="+ Grupo").click()
    expect(page.get_by_text("E · todas precisam ocorrer")).to_have_count(1)
    expect(page.get_by_text("todos os itens deste quadro juntos")).to_have_count(2)
    expect(
        page.get_by_text(
            "Este grupo está vazio. Use os botões acima para adicionar uma condição ou um subgrupo dentro dele."
        )
    ).to_be_visible()

    # Regra encadeada lida como frase: condição E NÃO (condição).
    editor.get_by_role("button", name="+ Condição").nth(1).click()
    # Os selects com a opção OU são os dois seletores de operador
    # (raiz e subgrupo); o segundo, em ordem de DOM, é o do subgrupo.
    subgrupo_operador = editor.locator("select:has(option[value='OU'])").nth(1)
    subgrupo_operador.select_option("NAO")
    expect(page.get_by_text("NÃO · inverte o resultado")).to_have_count(1)
    expect(formula).to_contain_text(" NÃO (")
    expect(formula).to_contain_text("igual a 80 E NÃO (")

    page.get_by_role("button", name="Salvar regra automática").click()
    expect(page).to_have_url(
        f"{server_url}{reverse('lista_recursos')}?editar={cenario_editor_regra['recurso']}"
        "#tab-parada-automatica"
    )
    expect(editor).to_be_visible()
