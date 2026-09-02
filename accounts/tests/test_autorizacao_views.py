from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import Empresa, Filial
from accounts.models.permissoes import (
    criar_permissao_administrar_acessos,
    criar_permissao_manipular_cadastros,
)

User = get_user_model()

# Rotas de usuários/grupos: gestão de acessos (poder de concessão) —
# permissão própria separada dos cadastros.
ROTAS_ACESSOS = [
    ("lista_usuarios", {}, "GET"),
    ("cadastrar_usuario", {}, "GET"),
    ("editar_usuario", {"user_id": 1}, "GET"),
    ("grupos_view", {}, "GET"),
    # POSTs destrutivos por último.
    ("deletar_usuario", {"user_id": 1}, "POST"),
]

# (rota, kwargs, metodo) — o deny acontece no decorator, antes do corpo:
# nenhum dado precisa existir para provar a negação.
ROTAS_TELAS = [
    ("lista_empresas", {}, "GET"),
    ("criar_empresa", {}, "GET"),
    ("editar_empresa", {"pk": 1}, "GET"),
    ("lista_filiais", {}, "GET"),
    ("lista_departamentos", {}, "GET"),
    ("cadastrar_departamento", {}, "GET"),
    ("editar_departamento", {"departamento_id": 1}, "GET"),
    ("turnos_base", {}, "GET"),
    ("editar_turno_base", {"pk": 1}, "GET"),
    ("calendarios", {}, "GET"),
    ("editar_calendario", {"pk": 1}, "GET"),
    ("eventos_calendario", {"calendario_id": 1}, "GET"),
    ("editar_evento", {"pk": 1}, "GET"),
    ("api_eventos", {"calendario_id": 1}, "GET"),
    ("api_evento_create", {}, "POST"),
    ("api_evento_update", {}, "POST"),
    ("setores", {}, "GET"),
    ("centros_recursos", {}, "GET"),
    ("lista_recursos", {}, "GET"),
    ("lista_taras", {}, "GET"),
    ("lista_turnos", {}, "GET"),
    ("editar_turno", {"pk": 1}, "GET"),
    ("lista_horas_extras", {}, "GET"),
    ("editar_hora_extra", {"pk": 1}, "GET"),
    ("reprocessar_planejado", {}, "GET"),
    # AJAX de apoio às telas de cadastro: mesma permissão que os guards
    # manuais anteriores exigiam (staff | manipular_cadastros). Os
    # filtrar_* de recursos.py são codigo morto (sem rota), fora daqui.
    ("motivos_por_grupo_parada", {}, "GET"),
    ("recursos_ativos_por_empresa", {}, "GET"),
    # POSTs destrutivos por último: o teste de permissão concede e navega
    # em sequência, e aqui nenhum registro precisa existir (deny é do gate).
    ("deletar_departamento", {"pk": 1}, "POST"),
    ("excluir_filial", {"pk": 1}, "POST"),
    ("deletar_turno_base", {"pk": 1}, "POST"),
    ("deletar_calendario", {"pk": 1}, "POST"),
    ("deletar_evento", {"pk": 1}, "POST"),
    ("deletar_setor", {"pk": 1}, "POST"),
    ("deletar_centro_recurso", {"pk": 1}, "POST"),
    ("deletar_recurso", {"pk": 1}, "POST"),
    ("deletar_tara", {"pk": 1}, "POST"),
    ("deletar_turno", {"pk": 1}, "POST"),
    ("replicar_turnos", {"recurso_id": 1}, "POST"),
    ("deletar_hora_extra", {"pk": 1}, "POST"),
]


class AutorizacaoCadastrosTests(TestCase):
    """Rotas de cadastro/administração do portal exigem
    `accounts.manipular_cadastros` (staff/superusuário pelo bypass)."""

    @classmethod
    def setUpTestData(cls):
        empresa = Empresa.objects.create(codemp=1, nome="E", fantasia="E")
        cls.filial = Filial.objects.create(
            empresa=empresa,
            codfil=1,
            nome="F",
            fantasia="F",
            cnpj=f"{1_00001:014d}",
        )
        # As duas permissões são criadas por função pós-migrate; no banco de
        # teste elas precisam existir antes de serem concedidas.
        criar_permissao_manipular_cadastros()
        criar_permissao_administrar_acessos()

    def setUp(self):
        self.usuario = User.objects.create_user(
            username="cadastro_a", password="senha", filial=self.filial
        )
        self.client.force_login(self.usuario)

    def _conceder(self, codename="manipular_cadastros"):
        self.usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="accounts", codename=codename)
        )

    # --- deny ---

    def test_anonimo_e_redirecionado_para_o_login(self):
        self.client.logout()

        for nome, kwargs, metodo in ROTAS_TELAS:
            with self.subTest(rota=nome):
                resposta = getattr(self.client, metodo.lower())(reverse(nome, kwargs=kwargs))
                self.assertEqual(resposta.status_code, 302)

    def test_autenticado_sem_permissao_recebe_403(self):
        for nome, kwargs, metodo in ROTAS_TELAS:
            with self.subTest(rota=nome):
                resposta = getattr(self.client, metodo.lower())(reverse(nome, kwargs=kwargs))
                self.assertEqual(resposta.status_code, 403)

    # --- autorizadas: não pode ser 403 (negócio resolve depois) ---

    def test_com_permissao_passa_do_gate_de_rota(self):
        self._conceder()

        for nome, kwargs, metodo in ROTAS_TELAS:
            with self.subTest(rota=nome):
                resposta = getattr(self.client, metodo.lower())(reverse(nome, kwargs=kwargs))
                self.assertNotEqual(resposta.status_code, 403)

    def test_staff_passa_sem_permissao(self):
        self.usuario.is_staff = True
        self.usuario.save()
        # força nova sessão já que staff não tem senha validada por backend
        self.client.force_login(self.usuario)

        for nome, kwargs, metodo in ROTAS_TELAS:
            with self.subTest(rota=nome):
                resposta = getattr(self.client, metodo.lower())(reverse(nome, kwargs=kwargs))
                self.assertNotEqual(resposta.status_code, 403)

    def test_superusuario_passa_sem_permissao(self):
        self.usuario.is_superuser = True
        self.usuario.save()
        self.client.force_login(self.usuario)

        for nome, kwargs, metodo in ROTAS_TELAS:
            with self.subTest(rota=nome):
                resposta = getattr(self.client, metodo.lower())(reverse(nome, kwargs=kwargs))
                self.assertNotEqual(resposta.status_code, 403)

    # --- rota livre — home continua só exigindo login ---

    def test_home_logada_sem_permissao_acessa_o_portal(self):
        resposta = self.client.get(reverse("home"))

        self.assertEqual(resposta.status_code, 200)


class AutorizacaoAcessosTests(TestCase):
    """Usuários e grupos são poder de concessão: exigem
    `accounts.administrar_acessos`, separada de manipular_cadastros — quem só
    cadastra não escala privilégio pelo formulário de usuário/grupo."""

    @classmethod
    def setUpTestData(cls):
        empresa = Empresa.objects.create(codemp=1, nome="E", fantasia="E")
        cls.filial = Filial.objects.create(
            empresa=empresa,
            codfil=1,
            nome="F",
            fantasia="F",
            cnpj=f"{1_00001:014d}",
        )
        criar_permissao_manipular_cadastros()
        criar_permissao_administrar_acessos()

    def setUp(self):
        self.usuario = User.objects.create_user(
            username="acessos_a", password="senha", filial=self.filial
        )
        self.client.force_login(self.usuario)

    def _conceder(self, codename):
        self.usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="accounts", codename=codename)
        )

    def test_manipular_cadastros_nao_libera_gestao_de_usuarios(self):
        # A separação é o ponto central da decisão do sênior.
        self._conceder("manipular_cadastros")

        for nome, kwargs, metodo in ROTAS_ACESSOS:
            with self.subTest(rota=nome):
                resposta = getattr(self.client, metodo.lower())(reverse(nome, kwargs=kwargs))
                self.assertEqual(resposta.status_code, 403)

    def test_administrar_acessos_passa_do_gate(self):
        self._conceder("administrar_acessos")

        for nome, kwargs, metodo in ROTAS_ACESSOS:
            with self.subTest(rota=nome):
                resposta = getattr(self.client, metodo.lower())(reverse(nome, kwargs=kwargs))
                self.assertNotEqual(resposta.status_code, 403)

    def test_sem_qualquer_permissao_recebe_403(self):
        for nome, kwargs, metodo in ROTAS_ACESSOS:
            with self.subTest(rota=nome):
                resposta = getattr(self.client, metodo.lower())(reverse(nome, kwargs=kwargs))
                self.assertEqual(resposta.status_code, 403)

    def test_anonimo_e_redirecionado_para_o_login(self):
        self.client.logout()

        resposta = self.client.get(reverse("lista_usuarios"))

        self.assertEqual(resposta.status_code, 302)


class StatusServicesStaffOnlyTests(TestCase):
    """O painel de serviços fica staff-only (exposição de infraestrutura):
    nem mesmo portadores de permissões de accounts abrem a página."""

    @classmethod
    def setUpTestData(cls):
        empresa = Empresa.objects.create(codemp=1, nome="E", fantasia="E")
        cls.filial = Filial.objects.create(
            empresa=empresa,
            codfil=1,
            nome="F",
            fantasia="F",
            cnpj=f"{1_00001:014d}",
        )
        criar_permissao_manipular_cadastros()
        criar_permissao_administrar_acessos()

    def setUp(self):
        self.usuario = User.objects.create_user(
            username="svc_a", password="senha", filial=self.filial
        )

    def _conceder(self, codename):
        self.usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="accounts", codename=codename)
        )

    def test_portador_de_permissoes_de_accounts_recebe_negacao(self):
        self._conceder("manipular_cadastros")
        self._conceder("administrar_acessos")
        self.client.force_login(self.usuario)

        # O guard staff-only usa user_passes_test sem raise: negação via
        # redirect ao login, como sempre foi nesta rota.
        resposta = self.client.get(reverse("status_services"))

        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/login/", resposta.url)

    def test_staff_abre_o_painel(self):
        self.usuario.is_staff = True
        self.usuario.save()
        self.client.force_login(self.usuario)

        resposta = self.client.get(reverse("status_services"))

        self.assertEqual(resposta.status_code, 200)
