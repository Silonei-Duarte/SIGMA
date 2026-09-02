from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor

User = get_user_model()


class AutorizacaoApontamentosTests(TestCase):
    """Telas de apontamento livres a autenticados (a versão aberta depende
    do cadastro do recurso); as rotas de ação exigem `producao.pode_apontar`
    e mantêm escopo por empresa dentro do corpo.
    """

    def setUp(self):
        self.empresa_a, self.recurso_a = self._criar_recurso(1, "A")
        _, self.recurso_b = self._criar_recurso(2, "B")
        filial_a = self.recurso_a.centro_recurso.setor.departamento.filial
        self.usuario = User.objects.create_user(
            username="operador", password="senha", filial=filial_a
        )
        self.client.force_login(self.usuario)

    @staticmethod
    def _criar_recurso(codemp, sufixo):
        empresa = Empresa.objects.create(
            codemp=codemp, nome=f"Empresa {sufixo}", fantasia=f"E{sufixo}"
        )
        filial = Filial.objects.create(
            empresa=empresa,
            codfil=1,
            nome=f"Filial {sufixo}",
            fantasia=f"F{sufixo}",
            cnpj=f"{codemp:04d}0000000001",
        )
        departamento = Departamento.objects.create(filial=filial, descricao=f"Depto {sufixo}")
        setor = Setor.objects.create(departamento=departamento, descricao=f"Setor {sufixo}")
        centro = CentroRecurso.objects.create(
            setor=setor, codigo=f"CR{sufixo}", descricao=f"Centro {sufixo}"
        )
        return empresa, Recurso.objects.create(
            centro_recurso=centro, codigo=f"R{sufixo}", descricao=f"Recurso {sufixo}"
        )

    def _conceder_apontamento(self):
        self.usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="producao", codename="pode_apontar")
        )

    # --- telas livres ---

    def test_tela_base_anonima_e_redirecionada_para_o_login(self):
        self.client.logout()

        resposta = self.client.get(reverse("apontamento_base"))

        self.assertEqual(resposta.status_code, 302)

    def test_tela_base_logada_sem_permissao_acessa_com_filtros_vazios(self):
        resposta = self.client.get(reverse("apontamento_base"))

        # Tela livre: usuário autenticado sem pode_apontar visualiza a tela;
        # as empresas visíveis ficam restritas à própria filial.
        self.assertEqual(resposta.status_code, 200)

    # --- ações exigem pode_apontar ---

    def test_acoes_sem_permissao_recebem_403_do_decorator(self):
        rotas = [
            ("justificar_paradas", [self.recurso_a.pk]),
            ("encerrar_paradas", [self.recurso_a.pk]),
            ("desacoplar_op_ativa", [self.recurso_a.pk]),
            ("abrir_parada_manual_apontamento", [self.recurso_a.pk]),
        ]
        for nome, argumentos in rotas:
            with self.subTest(rota=nome):
                resposta = self.client.post(reverse(nome, args=argumentos))
                self.assertEqual(resposta.status_code, 403)

    def test_acoes_anonimas_vao_para_o_login(self):
        self.client.logout()

        resposta = self.client.post(reverse("encerrar_paradas", args=[self.recurso_a.pk]))

        self.assertEqual(resposta.status_code, 302)

    def test_acao_com_permissao_alcanca_o_escopo_no_corpo(self):
        # Operador inválido: a view nega pela validação de ERP, não pelo
        # 403 do decorator — prova que o gate de permissão passou.
        self._conceder_apontamento()

        resposta = self.client.post(
            reverse("abrir_parada_manual_apontamento", args=[self.recurso_a.pk]),
            {"numcad": "invalido"},
        )

        self.assertRedirects(resposta, reverse("apontamento_base"), fetch_redirect_response=False)

    def test_acao_staff_passa_sem_permissao(self):
        self.usuario.is_staff = True
        self.usuario.save()

        resposta = self.client.post(
            reverse("abrir_parada_manual_apontamento", args=[self.recurso_a.pk]),
            {"numcad": "invalido"},
        )

        self.assertRedirects(resposta, reverse("apontamento_base"), fetch_redirect_response=False)

    def test_superusuario_sem_staff_passa_pela_rota_de_acao(self):
        # O ModelBackend libera has_perm para superusuário independente de
        # staff; o decorator formaliza o mesmo conjunto com is_superuser.
        self.usuario.is_superuser = True
        self.usuario.save()

        resposta = self.client.post(reverse("desacoplar_op_ativa", args=[self.recurso_a.pk]))

        # Sem operador validado em sessão o corpo nega por fluxo (302),
        # nunca pelo 403 do decorator.
        self.assertRedirects(resposta, reverse("apontamento_base"), fetch_redirect_response=False)

    def test_acoes_rejeitam_recurso_de_outra_empresa(self):
        self._conceder_apontamento()
        rotas = [
            ("justificar_paradas", [self.recurso_b.pk]),
            ("encerrar_paradas", [self.recurso_b.pk]),
            ("desacoplar_op_ativa", [self.recurso_b.pk]),
            ("abrir_parada_manual_apontamento", [self.recurso_b.pk]),
        ]
        for nome, argumentos in rotas:
            with self.subTest(rota=nome):
                resposta = self.client.post(reverse(nome, args=argumentos), {"numcad": "1"})
                self.assertEqual(resposta.status_code, 403)
