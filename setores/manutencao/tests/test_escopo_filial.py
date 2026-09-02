from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor
from setores.manutencao.models import Chamado
from setores.manutencao.views.chamados import _chamados_visiveis, _recursos_visiveis
from setores.manutencao.views.ordens_servico import _ordens_visiveis

User = get_user_model()


def criar_recurso(codemp):
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


class EscopoFilialManutencaoTests(TestCase):
    def setUp(self):
        self.filial_a, self.recurso_a = criar_recurso(901)
        self.filial_b, self.recurso_b = criar_recurso(902)
        self.usuario = User.objects.create_user(
            username="manutencao_a", password="senha", filial=self.filial_a
        )
        self.chamado_a = Chamado.objects.create(
            nome="A", categoria="MECANICA", recurso=self.recurso_a
        )
        self.chamado_b = Chamado.objects.create(
            nome="B", categoria="MECANICA", recurso=self.recurso_b
        )

    def test_recursos_e_chamados_ficam_limitados_a_filial_do_usuario(self):
        self.assertEqual(list(_recursos_visiveis(self.usuario)), [self.recurso_a])
        self.assertEqual(list(_chamados_visiveis(self.usuario)), [])

    def test_usuario_sem_filial_nao_recebe_recursos(self):
        sem_filial = User.objects.create_user(username="sem_filial", password="senha")
        self.assertFalse(_recursos_visiveis(sem_filial).exists())
        self.assertFalse(_chamados_visiveis(sem_filial).exists())
        self.assertFalse(_ordens_visiveis(sem_filial).exists())

    def test_listar_todos_nao_ultrapassa_a_propria_filial(self):
        permissao = Permission.objects.get(
            content_type__app_label="manutencao", codename="pode_listar_todos_chamados"
        )
        self.usuario.user_permissions.add(permissao)

        chamados = _chamados_visiveis(self.usuario)

        self.assertIn(self.chamado_a, chamados)
        self.assertNotIn(self.chamado_b, chamados)

    def test_edicao_rejeita_recurso_forjado_de_outra_filial(self):
        for codename in ("pode_acessar_chamados", "pode_manipular_chamados"):
            self.usuario.user_permissions.add(
                Permission.objects.get(content_type__app_label="manutencao", codename=codename)
            )
        self.client.force_login(self.usuario)

        resposta = self.client.post(
            reverse("detalhar_chamado", args=[self.chamado_a.pk]),
            {
                "nome": self.chamado_a.nome,
                "categoria": self.chamado_a.categoria,
                "prioridade": self.chamado_a.prioridade,
                "status": self.chamado_a.status,
                "recurso": self.recurso_b.pk,
            },
        )

        self.assertEqual(resposta.status_code, 302)
        self.chamado_a.refresh_from_db()
        self.assertEqual(self.chamado_a.recurso_id, self.recurso_a.pk)
