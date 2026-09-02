"""
Testes das APIs JSON do calendário de eventos.

Cobrem o achado alto da auditoria: `api_evento_update` e `api_evento_create`
tinham `@csrf_exempt` sem justificativa e atribuíam o payload cru aos campos
do model, sem validação. Depois da correção, as duas exigem o token CSRF
(como qualquer POST autenticado do projeto) e validam `motivo`/`data` antes
de gravar.
"""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Calendario, CalendarioEvento, Empresa, Filial

User = get_user_model()


class ApiEventoCalendarioTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(
            username="staff.calendario", password="Senha@2026", is_staff=True
        )
        empresa = Empresa.objects.create(codemp=100, nome="Empresa Calendário", fantasia="EC")
        filial = Filial.objects.create(
            empresa=empresa,
            codfil=1,
            nome="Filial Calendário",
            fantasia="FC",
            cnpj="33.333.333/0001-33",
        )
        self.calendario = Calendario.objects.create(filial=filial, descricao="Calendário Teste")
        self.evento = CalendarioEvento.objects.create(
            calendario=self.calendario, motivo=1, data="2026-01-05"
        )

    def _client_com_csrf(self):
        """Cliente que aplica a checagem real de CSRF, para provar que o
        @csrf_exempt removido realmente passou a proteger a rota."""
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.usuario)
        return client

    def test_api_eventos_retorna_tokens_semanticos_por_motivo(self):
        CalendarioEvento.objects.bulk_create(
            [
                CalendarioEvento(calendario=self.calendario, motivo=2, data="2026-01-06"),
                CalendarioEvento(calendario=self.calendario, motivo=3, data="2026-01-07"),
            ]
        )
        client = Client()
        client.force_login(self.usuario)

        resposta = client.get(
            reverse("api_eventos", args=[self.calendario.id]),
            {"start": "2026-01-01", "end": "2026-12-31"},
        )

        self.assertEqual(resposta.status_code, 200)
        eventos_por_motivo = {evento["title"]: evento for evento in resposta.json()}
        self.assertEqual(
            eventos_por_motivo["Dia Não Produtivo"]["backgroundColor"],
            "var(--color-erro-sutil)",
        )
        self.assertEqual(
            eventos_por_motivo["Feriado"]["backgroundColor"],
            "var(--color-atencao-sutil)",
        )
        self.assertEqual(
            eventos_por_motivo["Manutenção"]["backgroundColor"],
            "var(--color-informacao-sutil)",
        )
        for evento in eventos_por_motivo.values():
            self.assertNotIn(evento["backgroundColor"], {"var(--color-info-sutil)"})
            self.assertNotIn(evento["borderColor"], {"var(--color-info)"})

    def _token_csrf(self, client):
        # a página de calendários renderiza {% csrf_token %} e seta o cookie;
        # é o mesmo mecanismo que o JS de calendarios.html já usa em produção.
        client.get(reverse("calendarios"))
        return client.cookies["csrftoken"].value

    # --- api_evento_create ---

    def test_create_sem_token_csrf_e_bloqueado(self):
        client = self._client_com_csrf()
        resposta = client.post(
            reverse("api_evento_create"),
            data=json.dumps(
                {"calendario_id": self.calendario.id, "motivo": 1, "data": "2026-02-10"}
            ),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 403)

    def test_create_com_token_csrf_funciona(self):
        client = self._client_com_csrf()
        token = self._token_csrf(client)

        resposta = client.post(
            reverse("api_evento_create"),
            data=json.dumps(
                {"calendario_id": self.calendario.id, "motivo": 2, "data": "2026-02-10"}
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(
            CalendarioEvento.objects.filter(
                calendario=self.calendario, data="2026-02-10", motivo=2
            ).exists()
        )

    def test_create_payload_json_invalido_retorna_erro_tratado(self):
        client = self._client_com_csrf()
        token = self._token_csrf(client)

        resposta = client.post(
            reverse("api_evento_create"),
            data="isto nao e json",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(resposta.status_code, 400)

    def test_create_motivo_fora_das_choices_retorna_erro_tratado(self):
        client = self._client_com_csrf()
        token = self._token_csrf(client)

        resposta = client.post(
            reverse("api_evento_create"),
            data=json.dumps(
                {"calendario_id": self.calendario.id, "motivo": 99, "data": "2026-02-10"}
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(resposta.status_code, 400)

    def test_create_data_invalida_retorna_erro_tratado(self):
        client = self._client_com_csrf()
        token = self._token_csrf(client)

        resposta = client.post(
            reverse("api_evento_create"),
            data=json.dumps(
                {"calendario_id": self.calendario.id, "motivo": 1, "data": "nao-e-uma-data"}
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(resposta.status_code, 400)

    # --- api_evento_update ---

    def test_update_sem_token_csrf_e_bloqueado(self):
        client = self._client_com_csrf()
        resposta = client.post(
            reverse("api_evento_update"),
            data=json.dumps({"id": self.evento.id, "data": "2026-03-01"}),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 403)

    def test_update_com_token_csrf_funciona(self):
        client = self._client_com_csrf()
        token = self._token_csrf(client)

        resposta = client.post(
            reverse("api_evento_update"),
            data=json.dumps({"id": self.evento.id, "data": "2026-03-01"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(resposta.status_code, 200)
        self.evento.refresh_from_db()
        self.assertEqual(str(self.evento.data), "2026-03-01")

    def test_update_payload_json_invalido_retorna_erro_tratado(self):
        client = self._client_com_csrf()
        token = self._token_csrf(client)

        resposta = client.post(
            reverse("api_evento_update"),
            data="isto nao e json",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(resposta.status_code, 400)
