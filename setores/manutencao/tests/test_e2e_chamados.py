"""Regressão do acesso à abertura de OS pelo detalhe do chamado."""

import re

import pytest
from django.contrib.auth.models import Permission
from playwright.sync_api import Page, expect

from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor
from setores.manutencao.models import Chamado, Interacao_Chamado

pytestmark = pytest.mark.e2e

CODIGO_EMPRESA = 9901


def _limpar_dados() -> None:
    recursos = Recurso.objects.filter(
        centro_recurso__setor__departamento__filial__empresa__codemp=CODIGO_EMPRESA
    )
    Chamado.objects.filter(recurso__in=recursos).delete()
    recursos.delete()
    CentroRecurso.objects.filter(
        setor__departamento__filial__empresa__codemp=CODIGO_EMPRESA
    ).delete()
    Setor.objects.filter(departamento__filial__empresa__codemp=CODIGO_EMPRESA).delete()
    Departamento.objects.filter(filial__empresa__codemp=CODIGO_EMPRESA).delete()
    Filial.objects.filter(empresa__codemp=CODIGO_EMPRESA).delete()
    Empresa.objects.filter(codemp=CODIGO_EMPRESA).delete()


def _criar_cenario(django_db_blocker, usuario, *, status: str, pode_manipular_os: bool) -> Chamado:
    with django_db_blocker.unblock():
        _limpar_dados()
        empresa = Empresa.objects.create(codemp=CODIGO_EMPRESA, nome="E2E", fantasia="E2E")
        filial = Filial.objects.create(
            empresa=empresa,
            codfil=1,
            nome="E2E",
            fantasia="E2E",
            cnpj="99.000.000/0001-00",
        )
        departamento = Departamento.objects.create(filial=filial, descricao="E2E")
        setor = Setor.objects.create(departamento=departamento, descricao="E2E")
        centro = CentroRecurso.objects.create(setor=setor, codigo="E2E", descricao="E2E")
        recurso = Recurso.objects.create(centro_recurso=centro, codigo="E2E", descricao="E2E")

        usuario.is_staff = False
        usuario.is_superuser = False
        usuario.filial = filial
        usuario.save()
        usuario.user_permissions.clear()
        permissoes = [
            Permission.objects.get(
                content_type__app_label="manutencao", codename="pode_acessar_chamados"
            )
        ]
        if pode_manipular_os:
            permissoes.extend(
                [
                    Permission.objects.get(
                        content_type__app_label="manutencao", codename="pode_acessar_os"
                    ),
                    Permission.objects.get(
                        content_type__app_label="manutencao", codename="pode_manipular_os"
                    ),
                ]
            )
        usuario.user_permissions.add(*permissoes)

        chamado = Chamado.objects.create(
            nome="Chamado E2E",
            categoria=Chamado.Categoria.MECANICA,
            status=status,
            recurso=recurso,
        )
        Interacao_Chamado.objects.create(
            chamado=chamado, usuario=usuario, mensagem="Chamado aberto."
        )
        return chamado


@pytest.mark.parametrize(
    ("status", "pode_manipular_os", "deve_exibir"),
    [
        (Chamado.Status.ABERTO, True, True),
        (Chamado.Status.ABERTO, False, False),
        (Chamado.Status.FECHADO, True, False),
    ],
)
def test_detalhe_chamado_exibe_abrir_os_somente_quando_permitido(
    pagina_autenticada: Page,
    servidor_e2e: str,
    usuario_e2e,
    django_db_blocker,
    status: str,
    pode_manipular_os: bool,
    deve_exibir: bool,
):
    chamado = _criar_cenario(
        django_db_blocker,
        usuario_e2e,
        status=status,
        pode_manipular_os=pode_manipular_os,
    )
    try:
        pagina_autenticada.goto(f"{servidor_e2e}/setores/manutencao/{chamado.pk}/")
        abrir_os = pagina_autenticada.get_by_role("link", name="Abrir OS")

        if deve_exibir:
            expect(abrir_os).to_be_visible()
            expect(abrir_os).to_have_class(re.compile(r".*\bbotao-primario\b.*"))
            expect(abrir_os).to_have_attribute(
                "href", f"/setores/manutencao/os/abrir/?chamado={chamado.pk}"
            )
            abrir_os.click()
            expect(pagina_autenticada).to_have_url(
                f"{servidor_e2e}/setores/manutencao/os/abrir/?chamado={chamado.pk}"
            )
        else:
            expect(abrir_os).to_have_count(0)
    finally:
        with django_db_blocker.unblock():
            _limpar_dados()
