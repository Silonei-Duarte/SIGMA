from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import Empresa, Filial

User = get_user_model()

TITULO_SENSIVEL = "Permissão sensível: permite apagar registros das filas de integração"


class FormUsuarioPermissaoSensivelTests(TestCase):
    """A permissão unificada de exclusão aparece destacada com aviso de
    sensibilidade nos formulários de usuário e de grupos."""

    def setUp(self):
        self.empresa = Empresa.objects.create(codemp=1, nome="E", fantasia="E")
        self.filial = Filial.objects.create(
            empresa=self.empresa, codfil=1, nome="F", fantasia="F", cnpj=f"{1_00001:014d}"
        )
        self.admin = User.objects.create_user(
            username="admin_ui",
            password="senha",
            filial=self.filial,
            is_staff=True,
        )
        self.permissao = Permission.objects.get(
            content_type__app_label="producao", codename="pode_excluir_pendencias_integracao"
        )

    def test_form_usuario_marca_permissao_sensivel(self):
        alvo = User.objects.create_user(username="comum_ui", password="senha", filial=self.filial)
        self.client.force_login(self.admin)

        resposta = self.client.get(reverse("editar_usuario", args=[alvo.pk]))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, TITULO_SENSIVEL)

    def test_form_grupo_marca_permissao_sensivel(self):
        self.client.force_login(self.admin)

        resposta = self.client.get(reverse("grupos_view"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, TITULO_SENSIVEL)
