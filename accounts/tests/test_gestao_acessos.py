"""
Blindagens da tela de gestão de acessos (usuários, grupos, e-mail de teste):

1. Auto-escala: quem tem ``accounts.administrar_acessos`` sem ser superusuário
   não marca staff nem edita a própria conta pela tela; a flag ``is_staff``
   só muda por superusuário.
2. Whitelist server-side das permissões concedidas pela tela de grupos.
3. E-mail de teste não ecoa o detalhe da exceção SMTP na resposta.
"""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class GestaoAcessosBaseTests(TestCase):
    def criar_ator_permissionado(self, username):
        """Portador de administrar_acessos SEM staff nem superusuário."""
        ator = User.objects.create_user(
            username=username,
            password="Senha@2026",
            is_staff=False,
            is_superuser=False,
        )
        ator.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="accounts", codename="administrar_acessos"
            )
        )
        return ator

    def payload_usuario(self, **extras):
        dados = {
            "first_name": "",
            "last_name": "",
            "email": "",
            "is_active": "on",
            "idintegracao": "",
            "idoperador": "",
            "paginicial": "",
        }
        dados.update(extras)
        return dados


class AutoEscalaFormUsuarioTests(GestaoAcessosBaseTests):
    def setUp(self):
        self.ator = self.criar_ator_permissionado("gestor.acessos")
        self.superusuario = User.objects.create_user(
            username="admin.total",
            password="Senha@2026",
            is_staff=True,
            is_superuser=True,
        )

    def test_ator_nao_edita_a_propria_conta(self):
        """Edição da própria conta é bloqueada mesmo com o poder de acessar a tela."""
        self.client.force_login(self.ator)
        hash_original = self.ator.password

        resposta = self.client.post(
            reverse("editar_usuario", args=[self.ator.pk]),
            self.payload_usuario(
                is_staff="on", password1="OutraSenha@2026", password2="OutraSenha@2026"
            ),
        )

        self.assertRedirects(resposta, reverse("lista_usuarios"))
        self.ator.refresh_from_db()
        self.assertFalse(self.ator.is_staff)
        self.assertEqual(self.ator.password, hash_original)

    def test_superusuario_tambem_nao_edita_a_propria_conta_pela_tela(self):
        self.client.force_login(self.superusuario)

        resposta = self.client.get(reverse("editar_usuario", args=[self.superusuario.pk]))

        self.assertRedirects(resposta, reverse("lista_usuarios"))

    def test_is_staff_forjado_no_post_de_edicao_e_ignorado(self):
        alvo = User.objects.create_user(username="alvo.comum", password="Senha@2026")
        self.client.force_login(self.ator)

        resposta = self.client.post(
            reverse("editar_usuario", args=[alvo.pk]),
            self.payload_usuario(is_staff="on"),
        )

        self.assertEqual(resposta.status_code, 302)
        alvo.refresh_from_db()
        self.assertFalse(alvo.is_staff)

    def test_form_sem_poder_nao_renderiza_campo_staff(self):
        alvo = User.objects.create_user(username="alvo.form", password="Senha@2026")
        self.client.force_login(self.ator)

        resposta = self.client.get(reverse("editar_usuario", args=[alvo.pk]))

        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, 'name="is_staff"')

    def test_is_staff_forjado_no_post_de_criacao_e_ignorado(self):
        self.client.force_login(self.ator)

        resposta = self.client.post(
            reverse("cadastrar_usuario"),
            {
                "username": "novo.forjado",
                "password1": "Senha@2026",
                "password2": "Senha@2026",
                **self.payload_usuario(is_staff="on"),
            },
        )

        self.assertEqual(resposta.status_code, 302)
        criado = User.objects.get(username="novo.forjado")
        self.assertFalse(criado.is_staff)

    def test_superusuario_mantem_o_poder_de_definir_staff(self):
        """Regressão: com o poder, o campo continua e a atribuição funciona."""
        alvo = User.objects.create_user(username="alvo.staff.ok", password="Senha@2026")
        self.client.force_login(self.superusuario)

        resposta = self.client.post(
            reverse("editar_usuario", args=[alvo.pk]),
            self.payload_usuario(is_staff="on"),
        )

        self.assertEqual(resposta.status_code, 302)
        alvo.refresh_from_db()
        self.assertTrue(alvo.is_staff)

    def test_tentativa_de_escala_fica_registrada_em_log(self):
        alvo = User.objects.create_user(username="alvo.log", password="Senha@2026")
        self.client.force_login(self.ator)

        with self.assertLogs("accounts.views.usuarios", level="WARNING") as capturado:
            self.client.post(
                reverse("editar_usuario", args=[alvo.pk]), self.payload_usuario(is_staff="on")
            )

        self.assertTrue(any("is_staff" in linha for linha in capturado.output))

    def _criar_alvo_administrativo(self, username, *, superusuario=False):
        alvo = User.objects.create_user(
            username=username,
            password="SenhaOriginal@2026",
            is_staff=True,
            is_superuser=superusuario,
        )
        alvo.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="producao", codename="pode_alterar_paradas"
            )
        )
        return alvo

    def _assert_alvo_administrativo_intacto(
        self, alvo, hash_original, permissoes_originais, estado_original
    ):
        alvo.refresh_from_db()
        self.assertTrue(User.objects.filter(pk=alvo.pk).exists())
        self.assertEqual(
            (alvo.username, alvo.is_active, alvo.is_staff, alvo.is_superuser), estado_original
        )
        self.assertEqual(alvo.password, hash_original)
        self.assertEqual(
            set(alvo.user_permissions.values_list("pk", flat=True)), permissoes_originais
        )

    def test_ator_delegado_nao_edita_ou_reseta_senha_de_staff(self):
        alvo = self._criar_alvo_administrativo("alvo.staff")
        hash_original = alvo.password
        permissoes_originais = set(alvo.user_permissions.values_list("pk", flat=True))
        estado_original = (alvo.username, alvo.is_active, alvo.is_staff, alvo.is_superuser)
        self.client.force_login(self.ator)

        resposta = self.client.post(
            reverse("editar_usuario", args=[alvo.pk]),
            self.payload_usuario(password1="SenhaForjada@2026", password2="SenhaForjada@2026"),
        )

        self.assertEqual(resposta.status_code, 403)
        self._assert_alvo_administrativo_intacto(
            alvo, hash_original, permissoes_originais, estado_original
        )

    def test_ator_delegado_nao_edita_ou_reseta_senha_de_superusuario(self):
        alvo = self._criar_alvo_administrativo("alvo.superusuario", superusuario=True)
        hash_original = alvo.password
        permissoes_originais = set(alvo.user_permissions.values_list("pk", flat=True))
        estado_original = (alvo.username, alvo.is_active, alvo.is_staff, alvo.is_superuser)
        self.client.force_login(self.ator)

        resposta = self.client.post(
            reverse("editar_usuario", args=[alvo.pk]),
            self.payload_usuario(password1="SenhaForjada@2026", password2="SenhaForjada@2026"),
        )

        self.assertEqual(resposta.status_code, 403)
        self._assert_alvo_administrativo_intacto(
            alvo, hash_original, permissoes_originais, estado_original
        )

    def test_ator_delegado_nao_exclui_staff(self):
        alvo = self._criar_alvo_administrativo("alvo.staff.excluir")
        hash_original = alvo.password
        permissoes_originais = set(alvo.user_permissions.values_list("pk", flat=True))
        estado_original = (alvo.username, alvo.is_active, alvo.is_staff, alvo.is_superuser)
        self.client.force_login(self.ator)

        resposta = self.client.post(reverse("deletar_usuario", args=[alvo.pk]))

        self.assertEqual(resposta.status_code, 403)
        self._assert_alvo_administrativo_intacto(
            alvo, hash_original, permissoes_originais, estado_original
        )

    def test_ator_delegado_nao_exclui_superusuario(self):
        alvo = self._criar_alvo_administrativo("alvo.superusuario.excluir", superusuario=True)
        hash_original = alvo.password
        permissoes_originais = set(alvo.user_permissions.values_list("pk", flat=True))
        estado_original = (alvo.username, alvo.is_active, alvo.is_staff, alvo.is_superuser)
        self.client.force_login(self.ator)

        resposta = self.client.post(reverse("deletar_usuario", args=[alvo.pk]))

        self.assertEqual(resposta.status_code, 403)
        self._assert_alvo_administrativo_intacto(
            alvo, hash_original, permissoes_originais, estado_original
        )


class WhitelistPermissoesGruposTests(GestaoAcessosBaseTests):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin.grupos",
            password="Senha@2026",
            is_staff=True,
        )
        self.permissao_interna = Permission.objects.get(
            content_type__app_label="producao", codename="pode_excluir_pendencias_integracao"
        )
        self.permissao_telemetria = Permission.objects.get(
            content_type__app_label="telemetria", codename="pode_gerenciar_sensores"
        )
        self.permissao_core_auth = Permission.objects.filter(content_type__app_label="auth").first()

    def test_post_forjado_com_permissoes_fora_da_whitelist_e_ignorado(self):
        self.client.force_login(self.admin)

        resposta = self.client.post(
            reverse("grupos_view"),
            {
                "salvar": "",
                "nome": "Grupo Forjado",
                "permissoes": [
                    str(self.permissao_interna.pk),
                    str(self.permissao_telemetria.pk),
                    str(self.permissao_core_auth.pk),
                ],
            },
        )

        self.assertRedirects(resposta, reverse("grupos_view"))
        grupo = Group.objects.get(name="Grupo Forjado")
        self.assertEqual(
            set(grupo.permissions.values_list("pk", flat=True)), {self.permissao_interna.pk}
        )

    def test_get_continua_listando_apenas_apps_da_whitelist(self):
        self.client.force_login(self.admin)

        resposta = self.client.get(reverse("grupos_view"))

        self.assertEqual(resposta.status_code, 200)


class EmailTesteErroMascaradoTests(GestaoAcessosBaseTests):
    def setUp(self):
        self.usuario = self.criar_ator_permissionado("mail.tester")
        self.client.force_login(self.usuario)
        self.url = reverse("enviar_email_teste")

    def post_email(self, email="destino@ipel.com.br"):
        return self.client.post(
            self.url,
            data=json.dumps({"email": email}),
            content_type="application/json",
        )

    def test_falha_smtp_responde_mensagem_generica(self):
        detalhe_interno = "SMTPServerDisconnected('connection lost')"

        with patch("accounts.views.utilitarios.send_mail", side_effect=Exception(detalhe_interno)):
            resposta = self.post_email()

        corpo = resposta.json()
        self.assertFalse(corpo["enviado"])
        self.assertEqual(resposta.status_code, 502)
        self.assertNotIn(detalhe_interno, corpo["erro"])
        self.assertIn("registros do servidor", corpo["erro"])

    def test_envio_bem_sucedido_continua_funcionando(self):
        with patch("accounts.views.utilitarios.send_mail") as mock_send:
            mock_send.return_value = 1
            resposta = self.post_email()

        self.assertTrue(resposta.json()["enviado"])
        self.assertEqual(mock_send.call_count, 1)

    def test_zero_enviados_responde_erro(self):
        with patch("accounts.views.utilitarios.send_mail") as mock_send:
            mock_send.return_value = 0
            resposta = self.post_email()

        self.assertEqual(resposta.status_code, 502)
        self.assertEqual(resposta.json()["erro"], "Nenhum e-mail foi enviado.")

    def test_usuario_autenticado_sem_permissao_nao_envia_email(self):
        usuario_sem_permissao = User.objects.create_user(
            username="mail.sem.permissao", password="Senha@2026"
        )
        self.client.force_login(usuario_sem_permissao)

        with patch("accounts.views.utilitarios.send_mail") as mock_send:
            resposta = self.post_email()

        self.assertEqual(resposta.status_code, 403)
        mock_send.assert_not_called()

    def test_utilitarios_oculta_controle_de_email_sem_permissao(self):
        usuario_sem_permissao = User.objects.create_user(
            username="utilitarios.sem.permissao", password="Senha@2026"
        )
        self.client.force_login(usuario_sem_permissao)

        resposta = self.client.get(reverse("utilitarios"))

        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, 'id="formEmailTeste"')

    def test_utilitarios_exibe_controle_de_email_para_permissionado(self):
        resposta = self.client.get(reverse("utilitarios"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'id="formEmailTeste"')
