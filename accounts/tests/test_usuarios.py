"""
Testes de controle de acesso da edição de usuários.

Cobrem o achado crítico da auditoria de segurança: `editar_usuario`
permitia que qualquer conta `is_staff=True` trocasse a senha de um
superusuário, pois não havia a mesma checagem que `deletar_usuario` já
aplica contra exclusão de superusuário.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class EditarUsuarioSuperusuarioTests(TestCase):
    def setUp(self):
        self.staff_comum = User.objects.create_user(
            username="staff.comum",
            password="Senha@2026",
            is_staff=True,
            is_superuser=False,
        )
        self.superusuario_ator = User.objects.create_user(
            username="admin.ator",
            password="Senha@2026",
            is_staff=True,
            is_superuser=True,
        )
        self.superusuario_alvo = User.objects.create_user(
            username="admin.alvo",
            password="SenhaAntiga@2026",
            is_staff=True,
            is_superuser=True,
        )
        self.hash_original = self.superusuario_alvo.password

    def _payload(self, nova_senha=None):
        dados = {
            "first_name": "",
            "last_name": "",
            "email": "",
            "is_staff": "on",
            "is_active": "on",
            "idintegracao": "",
            "idoperador": "",
            "paginicial": "",
        }
        if nova_senha:
            dados["password1"] = nova_senha
            dados["password2"] = nova_senha
        return dados

    def test_staff_comum_nao_pode_editar_senha_de_superusuario(self):
        self.client.force_login(self.staff_comum)
        url = reverse("editar_usuario", args=[self.superusuario_alvo.id])

        resposta = self.client.post(url, self._payload(nova_senha="NovaSenha@2026"))

        self.assertEqual(resposta.status_code, 403)
        self.superusuario_alvo.refresh_from_db()
        self.assertEqual(self.superusuario_alvo.password, self.hash_original)

    def test_staff_comum_nao_pode_nem_abrir_o_formulario_de_um_superusuario(self):
        self.client.force_login(self.staff_comum)
        url = reverse("editar_usuario", args=[self.superusuario_alvo.id])

        resposta = self.client.get(url)

        self.assertEqual(resposta.status_code, 403)

    def test_superusuario_pode_editar_outro_superusuario(self):
        self.client.force_login(self.superusuario_ator)
        url = reverse("editar_usuario", args=[self.superusuario_alvo.id])

        resposta = self.client.post(url, self._payload(nova_senha="NovaSenha@2026"))

        self.assertEqual(resposta.status_code, 302)
        self.superusuario_alvo.refresh_from_db()
        self.assertNotEqual(self.superusuario_alvo.password, self.hash_original)
        self.assertTrue(self.superusuario_alvo.check_password("NovaSenha@2026"))

    def test_staff_comum_continua_editando_usuario_comum_normalmente(self):
        """Guarda contra regressão: a checagem nova não pode travar o caminho feliz."""
        alvo_comum = User.objects.create_user(
            username="usuario.comum", password="Senha@2026", is_staff=False, is_superuser=False
        )
        self.client.force_login(self.staff_comum)
        url = reverse("editar_usuario", args=[alvo_comum.id])

        resposta = self.client.post(url, self._payload())

        self.assertEqual(resposta.status_code, 302)
