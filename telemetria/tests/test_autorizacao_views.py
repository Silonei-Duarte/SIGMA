from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import (
    CentroRecurso,
    Departamento,
    Empresa,
    Filial,
    Recurso,
    Setor,
    criar_permissao_manipular_cadastros,
)
from telemetria.models import FonteColetaHTTP, Sensor, SensorRecurso

User = get_user_model()

PERMISSAO = "pode_gerenciar_sensores"


def create_resource(codemp):
    """Estrutura mínima de empresa/filial para o recurso usado pela aba de telemetria."""
    empresa = Empresa.objects.create(codemp=codemp, nome=f"Empresa {codemp}", fantasia="Empresa")
    filial = Filial.objects.create(
        empresa=empresa,
        codfil=1,
        nome=f"Filial {codemp}",
        fantasia="Filial",
        cnpj=f"{codemp:014d}",
    )
    departamento = Departamento.objects.create(filial=filial, descricao="Departamento")
    setor = Setor.objects.create(departamento=departamento, descricao="Setor")
    centro = CentroRecurso.objects.create(setor=setor, codigo=f"C{codemp}", descricao="Centro")
    return filial, Recurso.objects.create(
        centro_recurso=centro, codigo=f"R{codemp}", descricao="Recurso"
    )


@override_settings(TELEMETRIA_HOSTS_PERMITIDOS=("equipamento.local",))
class SensoresAutorizacaoTests(TestCase):
    def setUp(self):
        self.filial_a, self.recurso_a = create_resource(901)
        self.filial_b, self.recurso_b = create_resource(902)
        self.usuario = User.objects.create_user(
            username="telemetria_a", password="senha", filial=self.filial_a
        )
        self.fonte_a = FonteColetaHTTP.objects.create(
            url="http://equipamento.local/status", filial=self.filial_a
        )
        self.fonte_b = FonteColetaHTTP.objects.create(
            url="http://equipamento.local/filial-b", filial=self.filial_b
        )
        self.fonte_sem_filial = FonteColetaHTTP.objects.create(
            url="http://equipamento.local/sem-filial"
        )
        self.fonte_sem_sensor = FonteColetaHTTP.objects.create(
            url="http://equipamento.local/vazia", filial=self.filial_a
        )
        self.sensor_a = Sensor.objects.create(
            fonte=self.fonte_a,
            chave_origem="statusPrensa",
            nome="Prensa",
            tipo_valor=Sensor.TipoValor.BOOLEANO,
            filial=self.filial_a,
        )
        self.sensor_b = Sensor.objects.create(
            fonte=self.fonte_b,
            chave_origem="statusInjetora",
            nome="Injetora",
            tipo_valor=Sensor.TipoValor.BOOLEANO,
            filial=self.filial_b,
        )
        self.sensor_sem_filial = Sensor.objects.create(
            fonte=self.fonte_sem_filial,
            chave_origem="statusOrfao",
            nome="Órfão",
            tipo_valor=Sensor.TipoValor.BOOLEANO,
        )
        self.client.force_login(self.usuario)

    def _grant_permission(self):
        self.usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="telemetria", codename=PERMISSAO)
        )

    # --- Acesso à rota (permissão própria do módulo) ---

    def test_anomimo_e_redirecionado_para_o_login(self):
        self.client.logout()

        resposta = self.client.get(reverse("telemetria_sensores"))

        self.assertEqual(resposta.status_code, 302)

    def test_cadastro_sensores_sem_permissao_recebe_403(self):
        resposta = self.client.get(reverse("telemetria_sensores"))

        self.assertEqual(resposta.status_code, 403)

    def test_cadastro_sensores_com_permissao_acessa(self):
        self._grant_permission()

        resposta = self.client.get(reverse("telemetria_sensores"))

        self.assertEqual(resposta.status_code, 200)

    def test_cadastro_sensores_staff_acessa_sem_permissao(self):
        self.usuario.is_staff = True
        self.usuario.save()

        resposta = self.client.get(reverse("telemetria_sensores"))

        self.assertEqual(resposta.status_code, 200)

    def test_cadastro_sensores_superusuario_acessa(self):
        self.usuario.is_superuser = True
        self.usuario.save()

        resposta = self.client.get(reverse("telemetria_sensores"))

        self.assertEqual(resposta.status_code, 200)

    def test_manipular_cadastros_nao_libera_mais_a_tela(self):
        # A tela deixou de usar accounts.manipular_cadastros: quem tinha só a
        # permissão antiga passa a receber 403 até ganhar a nova, por grupo.
        # A permissão antiga não nasce de migration no banco de teste — a
        # função pós-migrate de Accounts é idempotente.
        criar_permissao_manipular_cadastros()
        self.usuario.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="accounts", codename="manipular_cadastros"
            )
        )

        resposta = self.client.get(reverse("telemetria_sensores"))

        self.assertEqual(resposta.status_code, 403)

    # --- Exclusão de sensor ---

    def test_excluir_sensor_sem_permissao_recebe_403(self):
        resposta = self.client.post(reverse("telemetria_excluir_sensor", args=[self.sensor_a.pk]))

        self.assertEqual(resposta.status_code, 403)

    def test_excluir_sensor_com_permissao_exclui(self):
        self._grant_permission()

        resposta = self.client.post(reverse("telemetria_excluir_sensor", args=[self.sensor_a.pk]))

        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(Sensor.objects.filter(pk=self.sensor_a.pk).exists())

    # --- Exclusão de fonte ---

    def test_excluir_fonte_sem_permissao_recebe_403(self):
        resposta = self.client.post(
            reverse("telemetria_excluir_fonte", args=[self.fonte_sem_sensor.pk])
        )

        self.assertEqual(resposta.status_code, 403)

    def test_excluir_fonte_com_permissao_exclui(self):
        self._grant_permission()

        resposta = self.client.post(
            reverse("telemetria_excluir_fonte", args=[self.fonte_sem_sensor.pk])
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(FonteColetaHTTP.objects.filter(pk=self.fonte_sem_sensor.pk).exists())

    # --- Configuração de sensores no recurso ---

    def test_configurar_recurso_sem_permissao_recebe_403(self):
        resposta = self.client.get(
            reverse("telemetria_configurar_recurso", args=[self.recurso_a.pk])
        )

        self.assertEqual(resposta.status_code, 403)

    def test_configurar_recurso_com_permissao_redireciona_para_o_cadastro(self):
        self._grant_permission()

        resposta = self.client.get(
            reverse("telemetria_configurar_recurso", args=[self.recurso_a.pk])
        )

        self.assertRedirects(
            resposta,
            f"/recursos/?editar={self.recurso_a.id}#tab-telemetria",
            fetch_redirect_response=False,
        )

    def test_configurar_recurso_staff_passa_sem_permissao(self):
        self.usuario.is_staff = True
        self.usuario.save()

        resposta = self.client.get(
            reverse("telemetria_configurar_recurso", args=[self.recurso_a.pk])
        )

        self.assertRedirects(
            resposta,
            f"/recursos/?editar={self.recurso_a.id}#tab-telemetria",
            fetch_redirect_response=False,
        )

    def test_salvar_regra_parada_mantem_aba_parada_automatica_aberta(self):
        self._grant_permission()

        with patch("telemetria.services.coleta.notificar_alteracao_recurso"):
            resposta = self.client.post(
                reverse("telemetria_configurar_recurso", args=[self.recurso_a.pk]),
                {"acao": "regra_parada", "ativa": "on", "regra": "{}"},
            )

        self.assertRedirects(
            resposta,
            f"/recursos/?editar={self.recurso_a.id}#tab-parada-automatica",
            fetch_redirect_response=False,
        )

    def test_configurar_recurso_vinculo_id_nao_numerico_nao_quebra(self):
        # vinculo_id chega cru do POST; pk não numérico causava ValueError no
        # filter (HTTP 500). Inválido é tratado como vínculo inexistente:
        # mesmo redirect da view, sem excluir nada.
        self._grant_permission()
        vinculo = SensorRecurso.objects.create(recurso=self.recurso_a, sensor=self.sensor_a)

        with patch("telemetria.services.coleta.notificar_alteracao_recurso"):
            resposta = self.client.post(
                reverse("telemetria_configurar_recurso", args=[self.recurso_a.pk]),
                {"acao": "excluir_vinculo", "vinculo_id": "abc"},
            )

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(SensorRecurso.objects.filter(pk=vinculo.pk).exists())

    # --- Escopo por filial (não-staff) ---

    def test_cadastro_sensores_lista_somente_os_da_filial(self):
        self._grant_permission()

        resposta = self.client.get(reverse("telemetria_sensores"))

        self.assertEqual(resposta.status_code, 200)
        sensores = list(resposta.context["sensores"])
        self.assertEqual(sensores, [self.sensor_a])
        self.assertNotIn(self.sensor_b, sensores)
        self.assertNotIn(self.sensor_sem_filial, sensores)
        fontes = list(resposta.context["fontes"])
        self.assertEqual(set(fontes), {self.fonte_a, self.fonte_sem_sensor})

    def test_editar_sensor_da_propria_filial_acessa(self):
        self._grant_permission()

        resposta = self.client.get(reverse("telemetria_editar_sensor", args=[self.sensor_a.pk]))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["sensor_editando"], self.sensor_a)

    def test_editar_sensor_de_outra_filial_nao_e_servido(self):
        self._grant_permission()

        resposta = self.client.get(reverse("telemetria_editar_sensor", args=[self.sensor_b.pk]))

        # Sensor fora do escopo: Http404 → redirect para a raiz do portal
        # (handler404 do SIGMA com DEBUG=False); nunca 200.
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, settings.PORTAL_BASE_URL)

    def test_editar_fonte_de_outra_filial_nao_e_servido(self):
        self._grant_permission()

        resposta = self.client.get(reverse("telemetria_editar_fonte", args=[self.fonte_b.pk]))

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, settings.PORTAL_BASE_URL)

    def test_excluir_sensor_de_outra_filial_nao_exclui(self):
        self._grant_permission()

        resposta = self.client.post(reverse("telemetria_excluir_sensor", args=[self.sensor_b.pk]))

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, settings.PORTAL_BASE_URL)
        self.assertTrue(Sensor.objects.filter(pk=self.sensor_b.pk).exists())

    def test_excluir_fonte_de_outra_filial_nao_exclui(self):
        self._grant_permission()

        resposta = self.client.post(reverse("telemetria_excluir_fonte", args=[self.fonte_b.pk]))

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, settings.PORTAL_BASE_URL)
        self.assertTrue(FonteColetaHTTP.objects.filter(pk=self.fonte_b.pk).exists())

    def test_configurar_recurso_de_outra_filial_nao_e_servido(self):
        self._grant_permission()

        resposta = self.client.get(
            reverse("telemetria_configurar_recurso", args=[self.recurso_b.pk])
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, settings.PORTAL_BASE_URL)

    def test_vincular_sensor_de_outra_filial_negado(self):
        # O queryset do form de vínculo também respeita a filial: um POST
        # forjado com sensor de outra filial não cria vínculo.
        self._grant_permission()

        with patch("telemetria.services.coleta.notificar_alteracao_recurso"):
            resposta = self.client.post(
                reverse("telemetria_configurar_recurso", args=[self.recurso_a.pk]),
                {"acao": "vincular", "sensor": self.sensor_b.pk},
            )

        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(
            SensorRecurso.objects.filter(recurso=self.recurso_a, sensor=self.sensor_b).exists()
        )

    def test_vincular_sensor_inativo_da_propria_filial_negado(self):
        # O vínculo exige sensor ativo: a view passa ao form o queryset de
        # filial já filtrado por ativo=True; sem isso, o fallback do form
        # ficava inalcançável e sensor inativo passava a ser vinculável.
        self._grant_permission()
        self.sensor_a.ativo = False
        self.sensor_a.save()

        with patch("telemetria.services.coleta.notificar_alteracao_recurso"):
            resposta = self.client.post(
                reverse("telemetria_configurar_recurso", args=[self.recurso_a.pk]),
                {"acao": "vincular", "sensor": self.sensor_a.pk},
            )

        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(
            SensorRecurso.objects.filter(recurso=self.recurso_a, sensor=self.sensor_a).exists()
        )

    def test_post_forjado_de_sensor_para_fonte_de_outra_filial_e_negado(self):
        self._grant_permission()

        with (
            patch("telemetria.services.coleta.notificar_alteracao_fonte"),
            patch("telemetria.services.coleta.notificar_alteracao_recurso"),
        ):
            resposta = self.client.post(
                reverse("telemetria_sensores"),
                {
                    "fonte": self.fonte_b.pk,
                    "chave_origem": "forjado",
                    "nome": "Forjado",
                    "tipo_valor": Sensor.TipoValor.TEXTO,
                    "unidade": "",
                    "ativo": True,
                },
            )

        # Form inválido: a fonte de outra filial não está no queryset e o
        # sensor não é criado.
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Sensor.objects.filter(chave_origem="forjado").exists())

    # --- Escopo global (staff) ---

    def test_staff_ve_sensores_de_todas_as_filiais_inclusive_sem_filial(self):
        self.usuario.is_staff = True
        self.usuario.save()

        resposta = self.client.get(reverse("telemetria_sensores"))

        self.assertEqual(resposta.status_code, 200)
        sensores = list(resposta.context["sensores"])
        self.assertIn(self.sensor_a, sensores)
        self.assertIn(self.sensor_b, sensores)
        self.assertIn(self.sensor_sem_filial, sensores)
        fontes = list(resposta.context["fontes"])
        self.assertIn(self.fonte_a, fontes)
        self.assertIn(self.fonte_b, fontes)
        self.assertIn(self.fonte_sem_filial, fontes)

    def test_staff_exclui_sensor_de_outra_filial(self):
        self.usuario.is_staff = True
        self.usuario.save()

        resposta = self.client.post(reverse("telemetria_excluir_sensor", args=[self.sensor_b.pk]))

        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(Sensor.objects.filter(pk=self.sensor_b.pk).exists())

    # --- Usuário sem filial ---

    def test_usuario_sem_filial_recebe_listas_vazias(self):
        self._grant_permission()
        self.usuario.filial = None
        self.usuario.save()

        resposta = self.client.get(reverse("telemetria_sensores"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(list(resposta.context["sensores"]), [])
        self.assertEqual(list(resposta.context["fontes"]), [])

    def test_usuario_sem_filial_nao_exclui_sensor(self):
        self._grant_permission()
        self.usuario.filial = None
        self.usuario.save()

        resposta = self.client.post(reverse("telemetria_excluir_sensor", args=[self.sensor_a.pk]))

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, settings.PORTAL_BASE_URL)
        self.assertTrue(Sensor.objects.filter(pk=self.sensor_a.pk).exists())

    def test_usuario_sem_filial_nao_cria_fonte(self):
        # Sem filial, a escrita é negada — criar com filial NULL faria o
        # próprio usuário perder o registro de vista.
        self._grant_permission()
        self.usuario.filial = None
        self.usuario.save()

        resposta = self.client.post(
            reverse("telemetria_sensores"),
            {
                "acao": "fonte",
                "url": "http://equipamento.local/sem-filial-nova",
                "coleta_ativa": True,
                "timeout_segundos": 10,
                "pausa_sucesso_segundos": 10,
                "backoff_erro_segundos": 10,
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(
            FonteColetaHTTP.objects.filter(url="http://equipamento.local/sem-filial-nova").exists()
        )

    # --- Criação herda a filial do usuário não-staff ---

    def test_criacao_de_fonte_herda_filial_do_usuario(self):
        self._grant_permission()

        with patch("telemetria.services.coleta.notificar_alteracao_fonte"):
            resposta = self.client.post(
                reverse("telemetria_sensores"),
                {
                    "acao": "fonte",
                    "url": "http://equipamento.local/nova-fonte",
                    "coleta_ativa": True,
                    "timeout_segundos": 10,
                    "pausa_sucesso_segundos": 10,
                    "backoff_erro_segundos": 10,
                },
            )

        self.assertEqual(resposta.status_code, 302)
        fonte = FonteColetaHTTP.objects.get(url="http://equipamento.local/nova-fonte")
        self.assertEqual(fonte.filial, self.filial_a)

    def test_criacao_de_sensor_herda_filial_do_usuario(self):
        self._grant_permission()

        with (
            patch("telemetria.services.coleta.notificar_alteracao_fonte"),
            patch("telemetria.services.coleta.notificar_alteracao_recurso"),
        ):
            resposta = self.client.post(
                reverse("telemetria_sensores"),
                {
                    "fonte": self.fonte_a.pk,
                    "chave_origem": "novoSensor",
                    "nome": "Novo",
                    "tipo_valor": Sensor.TipoValor.TEXTO,
                    "unidade": "",
                    "ativo": True,
                },
            )

        self.assertEqual(resposta.status_code, 302)
        sensor = Sensor.objects.get(chave_origem="novoSensor")
        self.assertEqual(sensor.filial, self.filial_a)
