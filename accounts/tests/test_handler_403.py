import json

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from SIGMA.urls import acesso_nao_autorizado

User = get_user_model()


class Handler403Tests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_navegacao_html_exibe_pagina_amigavel_e_retorno_mesma_origem(self):
        request = self.factory.get(
            "/rota-protegida/",
            HTTP_REFERER="http://testserver/origem/",
        )

        resposta = acesso_nao_autorizado(request)

        self.assertEqual(resposta.status_code, 403)
        self.assertContains(resposta, "Acesso não autorizado", status_code=403)
        self.assertContains(resposta, 'href="http://testserver/origem/"', status_code=403)

    def test_referer_de_outra_origem_usa_pagina_inicial_como_fallback(self):
        request = self.factory.get(
            "/rota-protegida/",
            HTTP_REFERER="https://externo.example/rota/",
        )

        resposta = acesso_nao_autorizado(request)

        self.assertContains(resposta, f'href="{reverse("home")}"', status_code=403)

    def test_accept_json_recebe_resposta_generica_sem_html(self):
        request = self.factory.get("/rota-protegida/", HTTP_ACCEPT="application/json")

        resposta = acesso_nao_autorizado(request)

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(json.loads(resposta.content), {"mensagem": "Acesso não autorizado."})
        self.assertEqual(resposta["Content-Type"], "application/json")

    def test_xhr_recebe_resposta_generica_sem_html(self):
        request = self.factory.get(
            "/rota-protegida/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        resposta = acesso_nao_autorizado(request)

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(json.loads(resposta.content), {"mensagem": "Acesso não autorizado."})

    @override_settings(DEBUG=False)
    def test_usuario_autenticado_sem_permissao_recebe_handler_global(self):
        usuario = User.objects.create_user(username="sem_permissao", password="senha")
        self.client.force_login(usuario)

        resposta = self.client.get(reverse("lista_usuarios"))

        self.assertEqual(resposta.status_code, 403)
        self.assertTemplateUsed(resposta, "403.html")

    @override_settings(DEBUG=False)
    def test_rota_negada_com_accept_json_recebe_json_do_handler_global(self):
        usuario = User.objects.create_user(username="sem_permissao_json", password="senha")
        self.client.force_login(usuario)

        resposta = self.client.get(reverse("lista_usuarios"), HTTP_ACCEPT="application/json")

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(json.loads(resposta.content), {"mensagem": "Acesso não autorizado."})

    @override_settings(DEBUG=False)
    def test_rota_negada_com_xhr_recebe_json_do_handler_global(self):
        usuario = User.objects.create_user(username="sem_permissao_xhr", password="senha")
        self.client.force_login(usuario)

        resposta = self.client.get(
            reverse("lista_usuarios"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(json.loads(resposta.content), {"mensagem": "Acesso não autorizado."})

    def test_usuario_anonimo_continua_redirecionado_para_login(self):
        resposta = self.client.get(reverse("lista_usuarios"))

        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("login"), resposta.url)

    @override_settings(DEBUG=False)
    def test_handler_404_continua_redirecionando_para_portal(self):
        resposta = self.client.get("/rota-inexistente/")

        self.assertEqual(resposta.status_code, 302)
