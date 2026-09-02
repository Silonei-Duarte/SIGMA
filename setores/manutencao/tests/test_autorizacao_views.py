from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor
from setores.manutencao.models import Chamado, OrdemServico
from setores.manutencao.views.chamados import _chamados_visiveis
from setores.manutencao.views.ordens_servico import _ordens_visiveis

User = get_user_model()

ACESSO_CHAMADOS = "pode_acessar_chamados"
LISTAR_TODOS_CHAMADOS = "pode_listar_todos_chamados"
MANIPULAR_CHAMADOS = "pode_manipular_chamados"
ACESSO_OS = "pode_acessar_os"
LISTAR_TODAS_OS = "pode_listar_todas_os"
MANIPULAR_OS = "pode_manipular_os"


def create_resource(codemp):
    empresa = Empresa.objects.create(codemp=codemp, nome=f"Empresa {codemp}", fantasia=f"E{codemp}")
    filial = Filial.objects.create(
        empresa=empresa,
        codfil=1,
        nome=f"Filial {codemp}",
        fantasia=f"F{codemp}",
        cnpj=f"{codemp:014d}",
    )
    departamento = Departamento.objects.create(filial=filial, descricao="Manutenção")
    setor = Setor.objects.create(departamento=departamento, descricao="Setor")
    centro = CentroRecurso.objects.create(setor=setor, codigo=f"C{codemp}", descricao="Centro")
    return filial, Recurso.objects.create(
        centro_recurso=centro, codigo=f"R{codemp}", descricao="Recurso"
    )


class ManutencaoAutorizacaoTests(TestCase):
    def setUp(self):
        self.filial_a, self.recurso_a = create_resource(901)
        _, self.recurso_b = create_resource(902)
        self.usuario = User.objects.create_user(
            username="manutencao_a", password="senha", filial=self.filial_a
        )
        self.chamado_a = Chamado.objects.create(
            nome="A", categoria="MECANICA", recurso=self.recurso_a
        )
        self.chamado_b = Chamado.objects.create(
            nome="B", categoria="MECANICA", recurso=self.recurso_b
        )
        self.os_a = OrdemServico.objects.create(
            descricao="OS A", recurso=self.recurso_a, status="ABERTA"
        )
        self.os_b = OrdemServico.objects.create(
            descricao="OS B", recurso=self.recurso_b, status="ABERTA"
        )
        self.client.force_login(self.usuario)

    def _grant(self, *codenames):
        for codename in codenames:
            self.usuario.user_permissions.add(
                Permission.objects.get(content_type__app_label="manutencao", codename=codename)
            )
        # O ModelBackend cacheia as permissões no objeto do usuário; um objeto
        # recém-carregado evita assert com cache da primeira chamada a has_perm.
        self.usuario = User.objects.get(pk=self.usuario.pk)

    # --- Chamados: acesso à rota ---

    def test_listar_chamados_anomimo_e_redirecionado_para_o_login(self):
        self.client.logout()

        resposta = self.client.get(reverse("listar_chamados"))

        self.assertEqual(resposta.status_code, 302)

    def test_listar_chamados_sem_permissao_recebe_403(self):
        resposta = self.client.get(reverse("listar_chamados"))

        self.assertEqual(resposta.status_code, 403)

    def test_listar_chamados_com_permissao_acessa(self):
        self._grant(ACESSO_CHAMADOS)

        resposta = self.client.get(reverse("listar_chamados"))

        self.assertEqual(resposta.status_code, 200)

    def test_listar_chamados_staff_acessa_sem_permissao(self):
        self.usuario.is_staff = True
        self.usuario.save()

        resposta = self.client.get(reverse("listar_chamados"))

        self.assertEqual(resposta.status_code, 200)

    def test_listar_chamados_superusuario_acessa(self):
        self.usuario.is_superuser = True
        self.usuario.save()

        resposta = self.client.get(reverse("listar_chamados"))

        self.assertEqual(resposta.status_code, 200)

    def test_abrir_chamado_sem_permissao_recebe_403(self):
        resposta = self.client.get(reverse("abrir_chamado"))

        self.assertEqual(resposta.status_code, 403)

    def test_abrir_chamado_com_permissao_acessa(self):
        self._grant(ACESSO_CHAMADOS)

        resposta = self.client.get(reverse("abrir_chamado"))

        self.assertEqual(resposta.status_code, 200)

    def test_detalhar_chamado_sem_permissao_recebe_403(self):
        resposta = self.client.get(reverse("detalhar_chamado", args=[self.chamado_a.pk]))

        self.assertEqual(resposta.status_code, 403)

    def test_detalhar_chamado_com_listar_todos_acessa(self):
        # Sem "listar todos", o usuário sem vínculo com o chamado não o enxerga
        # no detalhe; a permissão de listagem amplia o escopo dentro da filial.
        self._grant(ACESSO_CHAMADOS, LISTAR_TODOS_CHAMADOS)

        resposta = self.client.get(reverse("detalhar_chamado", args=[self.chamado_a.pk]))

        self.assertEqual(resposta.status_code, 200)

    def test_detalhar_chamado_de_outra_filial_nao_e_servido(self):
        self._grant(ACESSO_CHAMADOS, LISTAR_TODOS_CHAMADOS)

        resposta = self.client.get(reverse("detalhar_chamado", args=[self.chamado_b.pk]))

        # O chamado de outra filial não entra no queryset visível: a view
        # levanta Http404 e o handler404 do SIGMA (DEBUG=False) devolve
        # redirect para a raiz do portal. O que não pode acontecer é 200.
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, settings.PORTAL_BASE_URL)

    def test_excluir_chamado_sem_permissao_recebe_403(self):
        resposta = self.client.get(reverse("excluir_chamado", args=[self.chamado_a.pk]))

        self.assertEqual(resposta.status_code, 403)

    def test_excluir_chamado_sem_manipular_redireciona_para_a_listagem(self):
        # A exclusão é ação sensível: quem acessa mas não manipula recebe a
        # mensagem e volta para a listagem — deny com redirecionamento, preservado.
        self._grant(ACESSO_CHAMADOS, LISTAR_TODOS_CHAMADOS)

        resposta = self.client.get(reverse("excluir_chamado", args=[self.chamado_a.pk]))

        self.assertRedirects(resposta, reverse("listar_chamados"), fetch_redirect_response=False)
        self.assertTrue(Chamado.objects.filter(pk=self.chamado_a.pk).exists())

    def test_excluir_chamado_com_manipular_exclui(self):
        self._grant(ACESSO_CHAMADOS, LISTAR_TODOS_CHAMADOS, MANIPULAR_CHAMADOS)

        resposta = self.client.post(reverse("excluir_chamado", args=[self.chamado_a.pk]))

        self.assertRedirects(resposta, reverse("listar_chamados"), fetch_redirect_response=False)
        self.assertFalse(Chamado.objects.filter(pk=self.chamado_a.pk).exists())

    def test_listar_chamados_confirmacao_sem_manipular_redireciona(self):
        # O GET ?excluir=<pk> renderiza a página de confirmação de exclusão;
        # quem acessa mas não manipula não pode vê-la — mesmo deny de
        # excluir_chamado: mensagem + volta à listagem.
        self._grant(ACESSO_CHAMADOS, LISTAR_TODOS_CHAMADOS)

        resposta = self.client.get(reverse("listar_chamados"), {"excluir": self.chamado_a.pk})

        self.assertRedirects(resposta, reverse("listar_chamados"), fetch_redirect_response=False)

    def test_listar_chamados_post_exclusao_sem_manipular_continua_negado(self):
        # O POST inline de exclusão segue exigindo manipulação, com o mesmo
        # deny 403 de antes — a checagem nova do GET não o enfraqueceu.
        self._grant(ACESSO_CHAMADOS, LISTAR_TODOS_CHAMADOS)

        resposta = self.client.post(
            reverse("listar_chamados"), {"confirmar_exclusao": self.chamado_a.pk}
        )

        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(Chamado.objects.filter(pk=self.chamado_a.pk).exists())

    def test_qrcode_sem_permissao_recebe_403(self):
        resposta = self.client.get(reverse("qrcode_recurso_pdf", args=[self.recurso_a.pk]))

        self.assertEqual(resposta.status_code, 403)

    def test_qrcode_com_permissao_gera_pdf(self):
        self._grant(ACESSO_CHAMADOS)

        resposta = self.client.get(reverse("qrcode_recurso_pdf", args=[self.recurso_a.pk]))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "application/pdf")

    def test_qrcode_recurso_de_outra_filial_nao_e_servido(self):
        self._grant(ACESSO_CHAMADOS)

        resposta = self.client.get(reverse("qrcode_recurso_pdf", args=[self.recurso_b.pk]))

        # Recurso fora da filial do usuário → Http404 → redirect para a raiz
        # do portal (handler404 do SIGMA); o PDF não pode ser gerado.
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, settings.PORTAL_BASE_URL)

    def test_ajax_sem_permissao_recebe_403(self):
        resposta = self.client.get(reverse("ajax_recursos_por_centro"))

        self.assertEqual(resposta.status_code, 403)

    def test_ajax_com_permissao_lista_recursos_da_filial(self):
        self._grant(ACESSO_CHAMADOS)

        resposta = self.client.get(
            reverse("ajax_recursos_por_centro"),
            {"centro_id": self.recurso_a.centro_recurso_id},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertJSONEqual(
            resposta.content,
            [{"id": self.recurso_a.pk, "descricao": self.recurso_a.descricao}],
        )

    def test_ajax_centro_de_outra_filial_retorna_vazio(self):
        self._grant(ACESSO_CHAMADOS)

        resposta = self.client.get(
            reverse("ajax_recursos_por_centro"),
            {"centro_id": self.recurso_b.centro_recurso_id},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertJSONEqual(resposta.content, [])

    # --- Ordens de serviço: acesso à rota ---

    def test_listar_os_sem_permissao_recebe_403(self):
        resposta = self.client.get(reverse("listar_os"))

        self.assertEqual(resposta.status_code, 403)

    def test_listar_os_com_permissao_acessa(self):
        self._grant(ACESSO_OS)

        resposta = self.client.get(reverse("listar_os"))

        self.assertEqual(resposta.status_code, 200)

    def test_listar_os_staff_acessa_sem_permissao(self):
        self.usuario.is_staff = True
        self.usuario.save()

        resposta = self.client.get(reverse("listar_os"))

        self.assertEqual(resposta.status_code, 200)

    def test_abrir_os_sem_acesso_recebe_403(self):
        resposta = self.client.get(reverse("abrir_os"))

        self.assertEqual(resposta.status_code, 403)

    def test_abrir_os_com_acesso_sem_manipular_redireciona(self):
        # Abrir OS é ação sensível; o deny atual é mensagem + volta à listagem.
        self._grant(ACESSO_OS)

        resposta = self.client.get(reverse("abrir_os"))

        self.assertRedirects(resposta, reverse("listar_os"), fetch_redirect_response=False)

    def test_abrir_os_com_manipular_acessa(self):
        self._grant(ACESSO_OS, MANIPULAR_OS)

        resposta = self.client.get(reverse("abrir_os"))

        self.assertEqual(resposta.status_code, 200)

    def test_detalhar_os_sem_permissao_recebe_403(self):
        resposta = self.client.get(reverse("detalhar_os", args=[self.os_a.pk]))

        self.assertEqual(resposta.status_code, 403)

    def test_detalhar_os_com_listar_todas_acessa(self):
        # Sem "listar todas", o usuário não responsável não enxerga a OS no
        # detalhe; a permissão de listagem amplia o escopo dentro da filial.
        self._grant(ACESSO_OS, LISTAR_TODAS_OS)

        resposta = self.client.get(reverse("detalhar_os", args=[self.os_a.pk]))

        self.assertEqual(resposta.status_code, 200)

    def test_detalhar_os_de_outra_filial_nao_e_servido(self):
        self._grant(ACESSO_OS, LISTAR_TODAS_OS)

        resposta = self.client.get(reverse("detalhar_os", args=[self.os_b.pk]))

        # A OS de outra filial não entra no queryset visível: Http404 →
        # redirect para a raiz do portal (handler404 do SIGMA), nunca 200.
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, settings.PORTAL_BASE_URL)

    def test_excluir_os_sem_permissao_recebe_403(self):
        resposta = self.client.get(reverse("excluir_os", args=[self.os_a.pk]))

        self.assertEqual(resposta.status_code, 403)

    def test_excluir_os_sem_manipular_redireciona_para_a_listagem(self):
        self._grant(ACESSO_OS, LISTAR_TODAS_OS)

        resposta = self.client.get(reverse("excluir_os", args=[self.os_a.pk]))

        self.assertRedirects(resposta, reverse("listar_os"), fetch_redirect_response=False)
        self.assertTrue(OrdemServico.objects.filter(pk=self.os_a.pk).exists())

    def test_excluir_os_com_manipular_exclui(self):
        self._grant(ACESSO_OS, LISTAR_TODAS_OS, MANIPULAR_OS)

        resposta = self.client.post(reverse("excluir_os", args=[self.os_a.pk]))

        self.assertRedirects(resposta, reverse("listar_os"), fetch_redirect_response=False)
        self.assertFalse(OrdemServico.objects.filter(pk=self.os_a.pk).exists())

    # --- Permissões de listagem seguem ampliando o que é renderizado ---

    def test_listar_todos_chamados_amplia_listagem_dentro_da_filial(self):
        # Sem vínculo com o chamado, o usuário não o enxerga; com a permissão
        # de listagem, vê todos os chamados da própria filial — nunca os de outra.
        self.assertNotIn(self.chamado_a, _chamados_visiveis(self.usuario))

        self._grant(LISTAR_TODOS_CHAMADOS)

        visiveis = _chamados_visiveis(self.usuario)
        self.assertIn(self.chamado_a, visiveis)
        self.assertNotIn(self.chamado_b, visiveis)

    def test_listar_todas_os_amplia_listagem_dentro_da_filial(self):
        # Sem ser responsável, o usuário não enxerga a OS; com a permissão de
        # listagem, vê todas as OS da própria filial — nunca as de outra.
        self.assertNotIn(self.os_a, _ordens_visiveis(self.usuario))

        self._grant(LISTAR_TODAS_OS)

        visiveis = _ordens_visiveis(self.usuario)
        self.assertIn(self.os_a, visiveis)
        self.assertNotIn(self.os_b, visiveis)
