"""Testes de setores/qualidade/views/wms_views.py.

Listagem e reenvio manual seguem o mesmo acesso dos logs de integração:
qualquer usuário autenticado opera apenas as pendências da própria empresa.
Staff continua sem a restrição de empresa. Exclusões permanecem protegidas
por `producao.pode_excluir_pendencias_integracao`.

`disparar_envio_wms` é mockado em todos os testes de envio: o que se testa
aqui é a autorização e o filtro por empresa, não o envio real HTTP para o
WMS (isso já é feito em segundo plano, fora do ciclo de request/response).
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import Empresa, Filial
from setores.qualidade.models import WMS_IntegraçãoOP
from setores.qualidade.views.wms_views import _payload_ajuste_wms, _payload_novo_lote_wms

User = get_user_model()


def _criar_empresa_filial(codemp, codfil=1):
    empresa = Empresa.objects.create(codemp=codemp, nome=f"Empresa {codemp}", fantasia=f"E{codemp}")
    filial = Filial.objects.create(
        empresa=empresa,
        codfil=codfil,
        nome=f"Filial {codemp}",
        fantasia=f"F{codemp}",
        cnpj="22.222.222/0001-22",
    )
    return empresa, filial


def _usuario(username, filial=None, is_staff=False, com_permissao=False):
    usuario = User.objects.create_user(
        username=username, password="Senha@2026", filial=filial, is_staff=is_staff
    )
    if com_permissao:
        permissao = Permission.objects.get(
            content_type__app_label="qualidade", codename="pode_destinar_lotes_liberacao"
        )
        usuario.user_permissions.add(permissao)
    return usuario


def _criar_pendencia(codemp, status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO):
    return WMS_IntegraçãoOP.objects.create(
        codemp=codemp,
        origem="OF",
        op=1,
        lote="L1",
        quantidade=10,
        codigo_integrador="10",
        codpro="P1",
        status=status,
    )


class PayloadAjusteWmsTests(TestCase):
    """MOTBLOQ/FLAGBLOQ fazem parte do contrato de bloqueio de qualidade do
    WMS: toda pendência de ajuste de estoque, seja de qual fluxo vier
    (componente, baixa de bobina, área vermelha), passa por este mesmo
    ponto de montagem — por isso um teste aqui cobre todos os fluxos.
    """

    def test_payload_ajuste_inclui_motbloq_e_flagbloq_fixos(self):
        pendencia = _criar_pendencia(codemp=301)

        payload = _payload_ajuste_wms(pendencia)

        self.assertEqual(payload["MOTBLOQ"], "")
        self.assertEqual(payload["FLAGBLOQ"], "0")

    def test_payload_novo_lote_nao_inclui_campos_de_bloqueio(self):
        # rec_ska não é ajuste de estoque; o contrato de bloqueio não se aplica.
        pendencia = _criar_pendencia(codemp=301)

        payload = _payload_novo_lote_wms(pendencia)

        self.assertNotIn("MOTBLOQ", payload)
        self.assertNotIn("FLAGBLOQ", payload)


class WmsViewsAutorizacaoTests(TestCase):
    def setUp(self):
        self.empresa_a, self.filial_a = _criar_empresa_filial(301)
        self.empresa_b, self.filial_b = _criar_empresa_filial(302)

        self.usuario_sem_permissao = _usuario("sem_permissao_wms", filial=self.filial_a)
        self.usuario_filial_a = _usuario("filial_a_wms", filial=self.filial_a, com_permissao=True)
        self.usuario_staff = _usuario("staff_wms", is_staff=True)

        self.pendencia_a = _criar_pendencia(self.empresa_a.codemp)
        self.pendencia_b = _criar_pendencia(self.empresa_b.codemp)

    def test_usuario_anonimo_redirecionado_login_na_listagem(self):
        url = reverse("qualidade:integracao_wms")

        resposta = self.client.get(url)

        self.assertRedirects(resposta, f"/login/?next={url}")

    def test_usuario_anonimo_redirecionado_login_no_enviar_individual(self):
        url = reverse("qualidade:enviar_integracao_wms", args=[self.pendencia_a.pk])

        resposta = self.client.post(url)

        self.assertRedirects(resposta, f"/login/?next={url}")

    def test_usuario_anonimo_redirecionado_login_no_enviar_todas(self):
        url = reverse("qualidade:enviar_todas_integracoes_wms")

        resposta = self.client.post(url)

        self.assertRedirects(resposta, f"/login/?next={url}")

    # --- Acesso de logs: autenticado opera apenas a própria empresa ---

    def test_usuario_autenticado_sem_permissao_lista_apenas_propria_empresa(self):
        self.client.force_login(self.usuario_sem_permissao)

        resposta = self.client.get(reverse("qualidade:integracao_wms"))

        self.assertEqual(resposta.status_code, 200)
        pendencias_exibidas = {p.pk for p in resposta.context["pendencias"]}
        self.assertIn(self.pendencia_a.pk, pendencias_exibidas)
        self.assertNotIn(self.pendencia_b.pk, pendencias_exibidas)

    @patch("setores.qualidade.views.wms_views.disparar_envio_wms")
    def test_usuario_autenticado_sem_permissao_envia_pendencia_da_propria_empresa(
        self, mock_disparar
    ):
        self.client.force_login(self.usuario_sem_permissao)

        resposta = self.client.post(
            reverse("qualidade:enviar_integracao_wms", args=[self.pendencia_a.pk])
        )

        self.assertRedirects(resposta, reverse("qualidade:integracao_wms"))
        mock_disparar.assert_called_once_with([self.pendencia_a.pk])
        self.assertEqual(
            WMS_IntegraçãoOP.objects.get(pk=self.pendencia_a.pk).status,
            WMS_IntegraçãoOP.Status.PROCESSANDO,
        )

    @patch("setores.qualidade.views.wms_views.disparar_envio_wms")
    def test_usuario_autenticado_sem_permissao_envia_todas_da_propria_empresa(self, mock_disparar):
        self.client.force_login(self.usuario_sem_permissao)

        resposta = self.client.post(reverse("qualidade:enviar_todas_integracoes_wms"))

        self.assertRedirects(resposta, reverse("qualidade:integracao_wms"))
        mock_disparar.assert_called_once_with([self.pendencia_a.pk])
        self.assertEqual(
            WMS_IntegraçãoOP.objects.get(pk=self.pendencia_a.pk).status,
            WMS_IntegraçãoOP.Status.PROCESSANDO,
        )
        self.assertEqual(
            WMS_IntegraçãoOP.objects.get(pk=self.pendencia_b.pk).status,
            WMS_IntegraçãoOP.Status.NAO_INTEGRADO,
        )

    # --- Achado CSRF/GET: ações de estado exigem POST, GET vira 405 ---

    def test_enviar_integracao_por_get_retorna_405(self):
        self.client.force_login(self.usuario_filial_a)

        resposta = self.client.get(
            reverse("qualidade:enviar_integracao_wms", args=[self.pendencia_a.pk])
        )

        self.assertEqual(resposta.status_code, 405)

    def test_enviar_todas_por_get_retorna_405(self):
        self.client.force_login(self.usuario_filial_a)

        resposta = self.client.get(reverse("qualidade:enviar_todas_integracoes_wms"))

        self.assertEqual(resposta.status_code, 405)

    def test_excluir_integracao_por_get_retorna_405(self):
        self.client.force_login(self.usuario_staff)

        resposta = self.client.get(
            reverse("qualidade:excluir_integracao_wms", args=[self.pendencia_a.pk])
        )

        self.assertEqual(resposta.status_code, 405)

    def test_excluir_todas_por_get_retorna_405(self):
        self.client.force_login(self.usuario_staff)

        resposta = self.client.get(reverse("qualidade:excluir_todas_integracoes_wms"))

        self.assertEqual(resposta.status_code, 405)

    # --- Listagem: não-staff só vê a própria empresa; staff vê todas ---

    def test_nao_staff_ve_apenas_pendencias_da_propria_empresa(self):
        self.client.force_login(self.usuario_filial_a)

        resposta = self.client.get(reverse("qualidade:integracao_wms"))

        pendencias_exibidas = {p.pk for p in resposta.context["pendencias"]}
        self.assertIn(self.pendencia_a.pk, pendencias_exibidas)
        self.assertNotIn(self.pendencia_b.pk, pendencias_exibidas)

    def test_staff_ve_pendencias_de_todas_as_empresas(self):
        self.client.force_login(self.usuario_staff)

        resposta = self.client.get(reverse("qualidade:integracao_wms"))

        pendencias_exibidas = {p.pk for p in resposta.context["pendencias"]}
        self.assertIn(self.pendencia_a.pk, pendencias_exibidas)
        self.assertIn(self.pendencia_b.pk, pendencias_exibidas)

    # --- Envio individual: não-staff só age sobre a própria empresa ---

    @patch("setores.qualidade.views.wms_views.disparar_envio_wms")
    def test_nao_staff_nao_envia_pendencia_de_outra_empresa(self, mock_disparar):
        self.client.force_login(self.usuario_sem_permissao)

        self.client.post(reverse("qualidade:enviar_integracao_wms", args=[self.pendencia_b.pk]))

        mock_disparar.assert_not_called()
        self.assertEqual(
            WMS_IntegraçãoOP.objects.get(pk=self.pendencia_b.pk).status,
            WMS_IntegraçãoOP.Status.NAO_INTEGRADO,
        )

    @patch("setores.qualidade.views.wms_views.disparar_envio_wms")
    def test_nao_staff_envia_pendencia_da_propria_empresa(self, mock_disparar):
        self.client.force_login(self.usuario_filial_a)

        self.client.post(reverse("qualidade:enviar_integracao_wms", args=[self.pendencia_a.pk]))

        mock_disparar.assert_called_once_with([self.pendencia_a.pk])

    @patch("setores.qualidade.views.wms_views.disparar_envio_wms")
    def test_staff_envia_pendencia_de_qualquer_empresa(self, mock_disparar):
        self.client.force_login(self.usuario_staff)

        self.client.post(reverse("qualidade:enviar_integracao_wms", args=[self.pendencia_b.pk]))

        mock_disparar.assert_called_once_with([self.pendencia_b.pk])

    # --- Envio em lote: não-staff só processa a própria empresa ---

    @patch("setores.qualidade.views.wms_views.disparar_envio_wms")
    def test_enviar_todas_nao_staff_so_processa_propria_empresa(self, mock_disparar):
        self.client.force_login(self.usuario_filial_a)

        self.client.post(reverse("qualidade:enviar_todas_integracoes_wms"))

        mock_disparar.assert_called_once()
        (ids_enviados,), _ = mock_disparar.call_args
        self.assertIn(self.pendencia_a.pk, ids_enviados)
        self.assertNotIn(self.pendencia_b.pk, ids_enviados)
        self.assertEqual(
            WMS_IntegraçãoOP.objects.get(pk=self.pendencia_b.pk).status,
            WMS_IntegraçãoOP.Status.NAO_INTEGRADO,
        )

    @patch("setores.qualidade.views.wms_views.disparar_envio_wms")
    def test_enviar_todas_staff_processa_todas_as_empresas(self, mock_disparar):
        self.client.force_login(self.usuario_staff)

        self.client.post(reverse("qualidade:enviar_todas_integracoes_wms"))

        mock_disparar.assert_called_once()
        (ids_enviados,), _ = mock_disparar.call_args
        self.assertIn(self.pendencia_a.pk, ids_enviados)
        self.assertIn(self.pendencia_b.pk, ids_enviados)

    # --- Exclusão: exige a permissão unificada das filas, via POST ---

    def test_usuario_sem_permissao_bloqueado_no_excluir(self):
        self.client.force_login(self.usuario_sem_permissao)

        resposta = self.client.post(
            reverse("qualidade:excluir_integracao_wms", args=[self.pendencia_a.pk])
        )

        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(WMS_IntegraçãoOP.objects.filter(pk=self.pendencia_a.pk).exists())

    def test_usuario_sem_permissao_bloqueado_no_excluir_todas(self):
        self.client.force_login(self.usuario_sem_permissao)

        resposta = self.client.post(reverse("qualidade:excluir_todas_integracoes_wms"))

        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(WMS_IntegraçãoOP.objects.filter(pk=self.pendencia_a.pk).exists())

    def test_usuario_com_permissao_exclui_pendencia(self):
        # Decisão do sênior: a permissão unificada autoriza a exclusão; não
        # há mais guard interno de superusuário.
        permissao = Permission.objects.get(
            content_type__app_label="producao", codename="pode_excluir_pendencias_integracao"
        )
        usuario = _usuario("excluir_com_permissao", filial=self.filial_a)
        usuario.user_permissions.add(permissao)
        self.client.force_login(usuario)

        resposta = self.client.post(
            reverse("qualidade:excluir_integracao_wms", args=[self.pendencia_a.pk])
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(WMS_IntegraçãoOP.objects.filter(pk=self.pendencia_a.pk).exists())

    def test_com_permissao_nao_exclui_pendencia_de_outra_empresa(self):
        permissao = Permission.objects.get(
            content_type__app_label="producao", codename="pode_excluir_pendencias_integracao"
        )
        usuario = _usuario("excluir_escopo_wms", filial=self.filial_a)
        usuario.user_permissions.add(permissao)
        self.client.force_login(usuario)

        resposta = self.client.post(
            reverse("qualidade:excluir_integracao_wms", args=[self.pendencia_b.pk])
        )

        # get_object_or_404 com DEBUG=False cai no redirect do handler404;
        # o essencial é o registro de outra empresa permanecer.
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(WMS_IntegraçãoOP.objects.filter(pk=self.pendencia_b.pk).exists())

    def test_excluir_todas_com_permissao_limita_ao_proprio_codemp(self):
        permissao = Permission.objects.get(
            content_type__app_label="producao", codename="pode_excluir_pendencias_integracao"
        )
        usuario = _usuario("excluir_todas_escopo_wms", filial=self.filial_a)
        usuario.user_permissions.add(permissao)
        self.client.force_login(usuario)

        resposta = self.client.post(reverse("qualidade:excluir_todas_integracoes_wms"))

        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(WMS_IntegraçãoOP.objects.filter(pk=self.pendencia_a.pk).exists())
        self.assertTrue(WMS_IntegraçãoOP.objects.filter(pk=self.pendencia_b.pk).exists())

    def test_staff_exclui_integracao_por_bypass_do_decorator(self):
        self.client.force_login(self.usuario_staff)

        resposta = self.client.post(
            reverse("qualidade:excluir_integracao_wms", args=[self.pendencia_a.pk])
        )

        self.assertRedirects(resposta, reverse("qualidade:integracao_wms"))
        self.assertFalse(WMS_IntegraçãoOP.objects.filter(pk=self.pendencia_a.pk).exists())

    def test_superusuario_exclui_integracao_pendente_por_post(self):
        usuario_super = _usuario("super_wms", is_staff=True)
        usuario_super.is_superuser = True
        usuario_super.save()
        self.client.force_login(usuario_super)

        self.client.post(reverse("qualidade:excluir_integracao_wms", args=[self.pendencia_a.pk]))

        self.assertFalse(WMS_IntegraçãoOP.objects.filter(pk=self.pendencia_a.pk).exists())

    def test_superusuario_exclui_todas_pendencias_por_post(self):
        usuario_super = _usuario("super_wms_todas", is_staff=True)
        usuario_super.is_superuser = True
        usuario_super.save()
        self.client.force_login(usuario_super)

        self.client.post(reverse("qualidade:excluir_todas_integracoes_wms"))

        self.assertFalse(
            WMS_IntegraçãoOP.objects.filter(status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO).exists()
        )
