from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor
from producao.views import apontamentos_v1, apontamentos_v2, apontamentos_v3
from producao.views.apontamento_base import recursos_visiveis_apontamento


class EscopoApontamentosTests(TestCase):
    def setUp(self):
        self.empresa_a, self.recurso_a = self._criar_recurso(1, "A")
        self.empresa_b, self.recurso_b = self._criar_recurso(2, "B")
        filial_a = self.recurso_a.centro_recurso.setor.departamento.filial
        self.usuario = get_user_model().objects.create_user(
            username="operador-a", password="senha", filial=filial_a
        )
        self.factory = RequestFactory()

    def _criar_recurso(self, codemp, sufixo):
        empresa = Empresa.objects.create(
            codemp=codemp, nome=f"Empresa {sufixo}", fantasia=f"E{sufixo}"
        )
        filial = Filial.objects.create(
            empresa=empresa,
            codfil=1,
            nome=f"Filial {sufixo}",
            fantasia=f"F{sufixo}",
            cnpj=f"00.000.000/000{codemp}-00",
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
        permissao = Permission.objects.get(codename="pode_apontar")
        self.usuario.user_permissions.add(permissao)

    def _request_com_recurso_estrangeiro(self):
        request = self.factory.get(
            "/producao/apontamentos/",
            {
                "empresa": self.empresa_b.pk,
                "centro": self.recurso_b.centro_recurso_id,
                "recurso": self.recurso_b.pk,
            },
        )
        request.user = self.usuario
        SessionMiddleware(lambda _request: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        return request

    def test_recurso_estrangeiro_nao_pertence_ao_escopo_do_usuario(self):
        recursos = recursos_visiveis_apontamento(self.usuario)

        self.assertTrue(recursos.filter(pk=self.recurso_a.pk).exists())
        self.assertFalse(recursos.filter(pk=self.recurso_b.pk).exists())

    def test_filtro_forjado_de_outra_empresa_e_descartado_na_tela_base(self):
        self.client.force_login(self.usuario)

        resposta = self.client.get(
            reverse("apontamento_base"),
            {
                "empresa": self.empresa_b.pk,
                "centro": self.recurso_b.centro_recurso_id,
                "recurso": self.recurso_b.pk,
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["recurso_id"], "")
        self.assertNotContains(resposta, self.recurso_b.descricao)

    def test_telas_versionadas_nao_carregam_recurso_de_outra_empresa(self):
        for view in (
            apontamentos_v1.apontamentos_view,
            apontamentos_v2.apontamentos_view,
            apontamentos_v3.apontamentos_view,
        ):
            with self.subTest(view=view.__module__):
                resposta = view(self._request_com_recurso_estrangeiro())

                self.assertEqual(resposta.status_code, 200)
                self.assertNotIn(self.recurso_b.descricao.encode(), resposta.content)

    def test_acoes_de_parada_exigem_permissao_de_apontamento(self):
        self.client.force_login(self.usuario)

        resposta = self.client.post(
            reverse("encerrar_paradas", args=[self.recurso_a.pk]),
        )

        self.assertEqual(resposta.status_code, 403)

    def test_acoes_de_parada_rejeitam_recurso_de_outra_empresa(self):
        self._conceder_apontamento()
        self.client.force_login(self.usuario)

        resposta = self.client.post(
            reverse("encerrar_paradas", args=[self.recurso_b.pk]),
        )

        self.assertEqual(resposta.status_code, 403)
