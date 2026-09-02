"""Testes de producao/views/logs_baixa_componentes.py, função enviar_baixa_componente.

Achado alto desta rodada de auditoria: o payload da baixa era embutido no CDATA
do envelope SOAP sem `escapar_cdata_sapiens`, igual ao padrão já corrigido em
producao/services/envia_tempos_erp.py.
"""

import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor
from producao.models import BaixaComponente
from producao.views import logs_baixa_componentes as views

User = get_user_model()


def _resposta_soap(
    texto='<waRetorno>{"status": "OK", "message": "OK"}</waRetorno>', status_code=200
):
    resposta = Mock()
    resposta.status_code = status_code
    resposta.text = texto
    return resposta


def _baixa(**overrides):
    dados = {
        "codemp": 1,
        "origem": "1",
        "numorp": 100,
        "codetg": 1,
        "seqrot": 1,
        "lotdes": "",
        "codcmp": "62709",
        "dercmp": "",
        "qtduti": 10,
        "codigo_integrador": "1",
        "datmov": "01/01/2026",
        "hormov": "10:00:00",
        "codlot": "L1",
        "repesagem": "N",
        "consumototal": "N",
    }
    dados.update(overrides)
    return SimpleNamespace(**dados)


class EnviarBaixaComponenteTests(SimpleTestCase):
    """Achado alto: CDATA sem escape no envio de baixa de componente ao ERP."""

    @patch("producao.services.sapiens.requests.post")
    def test_sequencia_fecha_cdata_nao_quebra_nem_injeta_xml(self, mock_post):
        mock_post.return_value = _resposta_soap()

        views.enviar_baixa_componente("u", "s", _baixa(codlot="L1]]><forjado>1</forjado>"))

        self.assertEqual(mock_post.call_args.kwargs["timeout"], 180)
        envelope = mock_post.call_args.kwargs["data"].decode("ISO-8859-1")
        raiz = ET.fromstring(envelope)
        self.assertIsNone(raiz.find(".//forjado"))
        self.assertIn("forjado", envelope)

    @patch("producao.services.sapiens.requests.post")
    def test_retorna_texto_da_resposta_do_sapiens(self, mock_post):
        mock_post.return_value = _resposta_soap(texto="<waRetorno>{}</waRetorno>")

        retorno = views.enviar_baixa_componente("u", "s", _baixa())

        self.assertEqual(retorno, "<waRetorno>{}</waRetorno>")


class RegistrarResultadoTests(SimpleTestCase):
    """Achado seguranca (rodada 4): política mudou — o campo `log` persistido
    tambem precisa estar mascarado. `BaixaComponente.objects` é mockado porque
    `recurso` é FK obrigatória (on_delete=PROTECT), sem valor de teste simples."""

    def test_falha_persiste_log_mascarado(self):
        log_cru = "<user>user_teste</user><password>senha_teste_123</password>"
        mock_manager = Mock()
        mock_filtro = Mock()
        mock_manager.filter.return_value = mock_filtro

        with patch.object(views.BaixaComponente, "objects", mock_manager):
            views._registrar_resultado(1, False, log_cru)

        _, kwargs = mock_filtro.exclude.return_value.update.call_args
        self.assertNotIn("senha_teste_123", kwargs["log"])
        self.assertNotIn("user_teste", kwargs["log"])
        self.assertIn("<password>***</password>", kwargs["log"])
        self.assertIn("<user>***</user>", kwargs["log"])

    def test_sucesso_tambem_persiste_log_mascarado(self):
        log_cru = "<user>user_teste</user><password>senha_teste_123</password>"
        mock_manager = Mock()
        mock_filtro = Mock()
        mock_manager.filter.return_value = mock_filtro

        with patch.object(views.BaixaComponente, "objects", mock_manager):
            views._registrar_resultado(1, True, log_cru)

        _, kwargs = mock_filtro.update.call_args
        self.assertNotIn("senha_teste_123", kwargs["log"])
        self.assertIn("<password>***</password>", kwargs["log"])

    @override_settings(SAPIENS_PASSWORD="senha-sapiens-sintetica-7h4")
    def test_segredo_de_configuracao_tambem_sai_mascarado(self):
        """Máscara única (SIGMA.segredos): senha de configuração no texto de
        erro também sai mascarada, não só credencial de envelope SOAP."""
        mock_manager = Mock()
        mock_filtro = Mock()
        mock_manager.filter.return_value = mock_filtro

        with patch.object(views.BaixaComponente, "objects", mock_manager):
            views._registrar_resultado(1, False, "HTTP 401 com senha-sapiens-sintetica-7h4")

        _, kwargs = mock_filtro.exclude.return_value.update.call_args
        self.assertNotIn("senha-sapiens-sintetica-7h4", kwargs["log"])


def _criar_recurso(sufixo, filial):
    """Monta a cadeia obrigatória de FKs (departamento -> setor -> centro -> recurso)
    exigida por BaixaComponente.recurso (PROTECT, sem null=True)."""
    departamento = Departamento.objects.create(filial=filial, descricao=f"Depto {sufixo}")
    setor = Setor.objects.create(departamento=departamento, descricao=f"Setor {sufixo}")
    centro = CentroRecurso.objects.create(
        setor=setor, codigo=f"CR-{sufixo}", descricao=f"Centro {sufixo}"
    )
    return Recurso.objects.create(
        codigo=f"R-{sufixo}", descricao=f"Recurso {sufixo}", centro_recurso=centro
    )


class LogsBaixaComponentesViewFiltroEmpresaTests(TestCase):
    """GET já filtra por filial (staff vê tudo); faltava teste do fallback
    `.none()` de quem não tem filial associada."""

    def _criar_baixa(self, codemp, recurso, numorp, status=0):
        return BaixaComponente.objects.create(
            recurso=recurso,
            codemp=codemp,
            origem="1",
            numorp=numorp,
            codetg=1,
            seqrot=1,
            codcmp="62709",
            qtduti=10,
            codlot="L1",
            data_hora=timezone.now(),
            status=status,
        )

    def setUp(self):
        empresa_a = Empresa.objects.create(codemp=70, nome="Empresa A", fantasia="EA")
        empresa_b = Empresa.objects.create(codemp=80, nome="Empresa B", fantasia="EB")
        filial_a = Filial.objects.create(
            empresa=empresa_a,
            codfil=1,
            nome="Filial A",
            fantasia="FA",
            cnpj="44.444.444/0001-44",
        )
        recurso = _criar_recurso("BAIXA-GET", filial_a)
        self.baixa_empresa_a = self._criar_baixa(
            codemp=empresa_a.codemp, recurso=recurso, numorp=100
        )
        self.baixa_empresa_b = self._criar_baixa(
            codemp=empresa_b.codemp, recurso=recurso, numorp=200
        )

    def test_usuario_sem_filial_ve_lista_vazia(self):
        usuario_sem_filial = User.objects.create_user(
            username="usuario.sem.filial.logs.baixa",
            password="Senha@2026",
            is_staff=False,
        )
        self.client.force_login(usuario_sem_filial)

        resposta = self.client.get(reverse("logs_baixa_componentes"))

        self.assertEqual(len(resposta.context["baixas"]), 0)


class LogsBaixaComponentesPostFiltroEmpresaTests(TestCase):
    """Achado de autorização: as ações de POST (enviar/reenviar, excluir, excluir
    em massa) não checavam se a baixa pertencia à filial do usuário — um
    não-staff que soubesse o pk conseguia reenviar ao Sapiens ou excluir uma
    baixa de outra empresa. Staff continua sem restrição."""

    def _criar_baixa(self, codemp, recurso, numorp, status=0, codlot="L1"):
        return BaixaComponente.objects.create(
            recurso=recurso,
            codemp=codemp,
            origem="1",
            numorp=numorp,
            codetg=1,
            seqrot=1,
            codcmp="62709",
            qtduti=10,
            codlot=codlot,
            data_hora=timezone.now(),
            status=status,
        )

    def setUp(self):
        empresa_a = Empresa.objects.create(codemp=70, nome="Empresa A", fantasia="EA")
        empresa_b = Empresa.objects.create(codemp=80, nome="Empresa B", fantasia="EB")
        filial_a = Filial.objects.create(
            empresa=empresa_a,
            codfil=1,
            nome="Filial A",
            fantasia="FA",
            cnpj="44.444.444/0001-44",
        )
        self.recurso = _criar_recurso("BAIXA-POST", filial_a)

        self.usuario_filial_a = User.objects.create_user(
            username="usuario.filial.a.logs.baixa",
            password="Senha@2026",
            is_staff=False,
            filial=filial_a,
        )
        self.usuario_staff = User.objects.create_user(
            username="staff.geral.logs.baixa",
            password="Senha@2026",
            is_staff=True,
        )
        self.superusuario_filial_a = User.objects.create_user(
            username="superuser.filial.a.logs.baixa",
            password="Senha@2026",
            is_staff=False,
            is_superuser=True,
            filial=filial_a,
        )

        self.baixa_empresa_a = self._criar_baixa(
            codemp=empresa_a.codemp, recurso=self.recurso, numorp=100, codlot="LA"
        )
        self.baixa_empresa_b = self._criar_baixa(
            codemp=empresa_b.codemp, recurso=self.recurso, numorp=200, codlot="LB"
        )

    @patch("producao.views.logs_baixa_componentes.disparar_envio_baixas_componentes")
    def test_enviar_de_outra_filial_nao_encontra_registro(self, mock_disparar):
        self.client.force_login(self.usuario_filial_a)

        resposta = self.client.post(
            reverse("enviar_baixa_componente_log", args=[self.baixa_empresa_b.pk])
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertNotEqual(resposta.url, reverse("logs_baixa_componentes"))
        mock_disparar.assert_not_called()
        self.assertEqual(BaixaComponente.objects.get(pk=self.baixa_empresa_b.pk).status, 0)

    @patch("producao.views.logs_baixa_componentes.disparar_envio_baixas_componentes")
    def test_enviar_da_propria_filial_funciona(self, mock_disparar):
        self.client.force_login(self.usuario_filial_a)

        self.client.post(reverse("enviar_baixa_componente_log", args=[self.baixa_empresa_a.pk]))

        mock_disparar.assert_called_once_with([self.baixa_empresa_a.pk])

    @patch("producao.views.logs_baixa_componentes.disparar_envio_baixas_componentes")
    def test_staff_enviar_de_qualquer_filial_funciona(self, mock_disparar):
        self.client.force_login(self.usuario_staff)

        self.client.post(reverse("enviar_baixa_componente_log", args=[self.baixa_empresa_b.pk]))

        mock_disparar.assert_called_once_with([self.baixa_empresa_b.pk])

    @patch("producao.views.logs_baixa_componentes.disparar_envio_baixas_componentes")
    def test_enviar_todas_nao_staff_so_processa_propria_filial(self, mock_disparar):
        self.client.force_login(self.usuario_filial_a)

        self.client.post(reverse("enviar_todas_baixas_componentes"))

        mock_disparar.assert_called_once()
        (ids_enviados,), _ = mock_disparar.call_args
        self.assertIn(self.baixa_empresa_a.pk, ids_enviados)
        self.assertNotIn(self.baixa_empresa_b.pk, ids_enviados)
        self.assertEqual(BaixaComponente.objects.get(pk=self.baixa_empresa_b.pk).status, 0)

    @patch("producao.views.logs_baixa_componentes.disparar_envio_baixas_componentes")
    def test_enviar_todas_staff_processa_todas_as_filiais(self, mock_disparar):
        self.client.force_login(self.usuario_staff)

        self.client.post(reverse("enviar_todas_baixas_componentes"))

        mock_disparar.assert_called_once_with()

    def test_excluir_de_outra_filial_nao_encontra_registro(self):
        self.client.force_login(self.superusuario_filial_a)

        resposta = self.client.post(
            reverse("excluir_baixa_componente", args=[self.baixa_empresa_b.pk])
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertNotEqual(resposta.url, reverse("logs_baixa_componentes"))
        self.assertTrue(BaixaComponente.objects.filter(pk=self.baixa_empresa_b.pk).exists())

    def test_excluir_da_propria_filial_funciona(self):
        self.client.force_login(self.superusuario_filial_a)

        self.client.post(reverse("excluir_baixa_componente", args=[self.baixa_empresa_a.pk]))

        self.assertFalse(BaixaComponente.objects.filter(pk=self.baixa_empresa_a.pk).exists())

    def test_excluir_todas_nao_staff_so_apaga_propria_filial(self):
        self.client.force_login(self.superusuario_filial_a)

        self.client.post(reverse("excluir_todas_baixas_componentes"))

        self.assertFalse(BaixaComponente.objects.filter(pk=self.baixa_empresa_a.pk).exists())
        self.assertTrue(BaixaComponente.objects.filter(pk=self.baixa_empresa_b.pk).exists())
