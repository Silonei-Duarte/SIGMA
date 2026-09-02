"""Testes de producao/views/logs_apontamentos.py, função enviar_movimentar_op.

Cobrem o achado crítico desta rodada de auditoria: a mesma classe de
vulnerabilidade já corrigida em producao/services/envia_tempos_erp.py
(credencial do Sapiens em log de produção, CDATA sem escape) ainda estava
ativa aqui — e esta função roda em praticamente todo apontamento lançado no
SIGMA (thread disparada a cada apontamento criado).
"""

import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Empresa, Filial
from producao.models.estrutura import Apontamento
from producao.views import logs_apontamentos as views

User = get_user_model()


def _resposta_soap(
    texto='<waRetorno>{"status": "OK", "message": "OK"}</waRetorno>', status_code=200
):
    resposta = Mock()
    resposta.status_code = status_code
    resposta.text = texto
    return resposta


class EnviarMovimentarOpTests(TestCase):
    """Achado crítico: credencial em log e CDATA sem escape na função de apontamento ao ERP."""

    @patch("producao.services.sapiens.requests.post")
    def test_senha_nunca_aparece_em_log_algum(self, mock_post):
        mock_post.return_value = _resposta_soap()

        with self.assertLogs("producao.views.logs_apontamentos", level="DEBUG") as captura:
            views.enviar_movimentar_op(
                usuario="usuario_sapiens",
                senha="segredo_super_secreto",
                codemp=1,
                codori="1",
                numorp=100,
                codetg=1,
                seqrot=1,
                numcad=1,
                qtdre1=10,
                qtdrfg=0,
            )

        saida = "\n".join(captura.output)
        self.assertNotIn("segredo_super_secreto", saida)
        # a máscara precisa de fato ter substituído o conteúdo da tag, não só omitido o log
        self.assertIn("<password>***</password>", saida)

    @patch("producao.services.sapiens.requests.post")
    def test_usuario_tambem_nao_aparece_em_log(self, mock_post):
        mock_post.return_value = _resposta_soap()

        with self.assertLogs("producao.views.logs_apontamentos", level="DEBUG") as captura:
            views.enviar_movimentar_op(
                usuario="usuario_sapiens",
                senha="segredo_super_secreto",
                codemp=1,
                codori="1",
                numorp=100,
                codetg=1,
                seqrot=1,
                numcad=1,
                qtdre1=10,
                qtdrfg=0,
            )

        saida = "\n".join(captura.output)
        self.assertNotIn("usuario_sapiens", saida)
        self.assertIn("<user>***</user>", saida)

    @patch("producao.services.sapiens.requests.post")
    def test_sequencia_fecha_cdata_nao_quebra_nem_injeta_xml(self, mock_post):
        """Achado alto: ']]>' num campo do apontamento não pode fechar o CDATA antes da hora."""
        mock_post.return_value = _resposta_soap()

        views.enviar_movimentar_op(
            usuario="u",
            senha="s",
            codemp=1,
            codori="1]]><forjado>1</forjado>",
            numorp=100,
            codetg=1,
            seqrot=1,
            numcad=1,
            qtdre1=10,
            qtdrfg=0,
        )

        self.assertEqual(mock_post.call_args.kwargs["timeout"], 180)
        envelope = mock_post.call_args.kwargs["data"].decode("ISO-8859-1")
        # o XML resultante precisa continuar bem formado...
        raiz = ET.fromstring(envelope)
        # ...e o valor malicioso deve permanecer como dado inerte, nunca como elemento novo
        self.assertIsNone(raiz.find(".//forjado"))
        self.assertIn("forjado", envelope)

    @patch("producao.services.sapiens.requests.post")
    def test_retorna_texto_da_resposta_do_sapiens(self, mock_post):
        mock_post.return_value = _resposta_soap(texto="<waRetorno>{}</waRetorno>")

        retorno = views.enviar_movimentar_op(
            usuario="u",
            senha="s",
            codemp=1,
            codori="1",
            numorp=100,
            codetg=1,
            seqrot=1,
            numcad=1,
            qtdre1=10,
            qtdrfg=0,
        )

        self.assertEqual(retorno, "<waRetorno>{}</waRetorno>")


class RegistrarResultadoApontamentoTests(TestCase):
    """Achado seguranca (rodada 4): política mudou — o campo `log` persistido
    tambem precisa estar mascarado, não só o que aparece em log/tela."""

    def _criar_apontamento(self):
        return Apontamento.objects.create(
            codemp=1,
            origem="1",
            numorp=100,
            codetg=1,
            seqrot=1,
            numcad=1,
            qtdre1=10,
            lote="L1",
        )

    def test_falha_persiste_log_mascarado(self):
        apontamento = self._criar_apontamento()
        log_cru = "<user>user_teste</user><password>senha_teste_123</password>"

        views._registrar_resultado_apontamento(apontamento.id, 0, log_cru)

        salvo = Apontamento.objects.get(pk=apontamento.id).log
        self.assertNotIn("senha_teste_123", salvo)
        self.assertNotIn("user_teste", salvo)
        self.assertIn("<password>***</password>", salvo)
        self.assertIn("<user>***</user>", salvo)

    def test_sucesso_tambem_persiste_log_mascarado(self):
        apontamento = self._criar_apontamento()
        log_cru = "<user>user_teste</user><password>senha_teste_123</password>"

        views._registrar_resultado_apontamento(apontamento.id, 1, log_cru)

        salvo = Apontamento.objects.get(pk=apontamento.id).log
        self.assertNotIn("senha_teste_123", salvo)
        self.assertIn("<password>***</password>", salvo)

    @override_settings(SAPIENS_PASSWORD="senha-sapiens-sintetica-7h4")
    def test_segredo_de_configuracao_tambem_sai_mascarado(self):
        """Máscara única (SIGMA.segredos): além da credencial do envelope SOAP,
        senha de configuração e token de URL no texto de erro saem mascarados."""
        apontamento = self._criar_apontamento()

        views._registrar_resultado_apontamento(
            apontamento.id,
            0,
            "HTTP 401 com senha-sapiens-sintetica-7h4 em "
            "https://balanca.local/coleta?token=token-sintetico-abc123",
        )

        salvo = Apontamento.objects.get(pk=apontamento.id).log
        self.assertNotIn("senha-sapiens-sintetica-7h4", salvo)
        self.assertNotIn("token-sintetico-abc123", salvo)


class ExecutarEnvioLogsMascaraErroTests(TestCase):
    """Achado seguranca (fechamento desta serie): o print() do bloco de exceção
    de executar_envio_logs saía para o stdout/log de serviço ANTES de qualquer
    máscara — só a persistência em banco era mascarada. Se a exceção um dia
    carregar texto de um envelope/resposta SOAP ecoado pelo Sapiens, a
    credencial vazaria pelo print antes de chegar em _registrar_resultado_apontamento."""

    def _criar_apontamento(self):
        return Apontamento.objects.create(
            codemp=1,
            origem="1",
            numorp=100,
            codetg=1,
            seqrot=1,
            numcad=1,
            qtdre1=10,
            lote="L1",
        )

    @patch("producao.views.logs_apontamentos.enviar_movimentar_op")
    @patch("builtins.print")
    def test_print_de_erro_nunca_expoe_credencial_crua(self, mock_print, mock_enviar):
        apontamento = self._criar_apontamento()
        credencial_crua = "<user>user_teste</user><password>senha_teste_123</password>"
        mock_enviar.side_effect = RuntimeError(f"Falha ao chamar Sapiens: {credencial_crua}")

        views.executar_envio_logs([apontamento])

        # o print aconteceu (fluxo de erro seguiu normalmente)
        mock_print.assert_called_once()
        mensagem_impressa = mock_print.call_args.args[0]
        self.assertNotIn("senha_teste_123", mensagem_impressa)
        self.assertNotIn("user_teste", mensagem_impressa)
        self.assertIn("<password>***</password>", mensagem_impressa)
        self.assertIn("<user>***</user>", mensagem_impressa)

        # e o que foi persistido também continua mascarado
        salvo = Apontamento.objects.get(pk=apontamento.id).log
        self.assertNotIn("senha_teste_123", salvo)
        self.assertIn("<password>***</password>", salvo)


class LogsApontamentosViewFiltroEmpresaTests(TestCase):
    """GET de logs_apontamentos já filtra por filial (staff vê tudo, regra de
    negócio vigente); faltava teste cobrindo o fallback `.none()` de quem não
    tem filial associada."""

    def _criar_apontamento(self, codemp, numorp, status=0):
        return Apontamento.objects.create(
            codemp=codemp,
            origem="1",
            numorp=numorp,
            codetg=1,
            seqrot=1,
            numcad=1,
            qtdre1=10,
            lote="L1",
            status=status,
        )

    def setUp(self):
        empresa_a = Empresa.objects.create(codemp=30, nome="Empresa A", fantasia="EA")
        empresa_b = Empresa.objects.create(codemp=40, nome="Empresa B", fantasia="EB")
        self.filial_a = Filial.objects.create(
            empresa=empresa_a,
            codfil=1,
            nome="Filial A",
            fantasia="FA",
            cnpj="22.222.222/0001-22",
        )
        self.apontamento_empresa_a = self._criar_apontamento(codemp=empresa_a.codemp, numorp=100)
        self.apontamento_empresa_b = self._criar_apontamento(codemp=empresa_b.codemp, numorp=200)

    def test_usuario_sem_filial_ve_lista_vazia(self):
        usuario_sem_filial = User.objects.create_user(
            username="usuario.sem.filial.logs.apont",
            password="Senha@2026",
            is_staff=False,
        )
        self.client.force_login(usuario_sem_filial)

        resposta = self.client.get(reverse("logs_apontamentos"))

        self.assertEqual(len(resposta.context["apontamentos"]), 0)


class BuscarDadosLoteErpPermissaoTests(TestCase):
    def test_usuario_sem_permissao_nao_consulta_dados_do_lote(self):
        usuario = User.objects.create_user(username="sem.permissao.lote", password="Senha@2026")
        self.client.force_login(usuario)

        with patch("producao.views.logs_apontamentos.buscar_dados_lote_erp_logic") as busca:
            resposta = self.client.get(reverse("buscar_dados_lote_erp"), {"lote": "L1"})

        self.assertEqual(resposta.status_code, 403)
        busca.assert_not_called()


class LogsApontamentosPostFiltroEmpresaTests(TestCase):
    """Achado de autorização: as ações de POST (enviar/reenviar, excluir, excluir
    em massa) não checavam se o apontamento pertencia à filial do usuário — um
    não-staff que soubesse o pk conseguia reenviar ao Sapiens ou excluir um
    apontamento de outra empresa. Staff continua sem restrição."""

    def _criar_apontamento(self, codemp, numorp, status=0):
        return Apontamento.objects.create(
            codemp=codemp,
            origem="1",
            numorp=numorp,
            codetg=1,
            seqrot=1,
            numcad=1,
            qtdre1=10,
            lote="L1",
            status=status,
        )

    def setUp(self):
        empresa_a = Empresa.objects.create(codemp=30, nome="Empresa A", fantasia="EA")
        empresa_b = Empresa.objects.create(codemp=40, nome="Empresa B", fantasia="EB")
        filial_a = Filial.objects.create(
            empresa=empresa_a,
            codfil=1,
            nome="Filial A",
            fantasia="FA",
            cnpj="22.222.222/0001-22",
        )

        self.usuario_filial_a = User.objects.create_user(
            username="usuario.filial.a.logs.apont",
            password="Senha@2026",
            is_staff=False,
            filial=filial_a,
        )
        self.usuario_staff = User.objects.create_user(
            username="staff.geral.logs.apont",
            password="Senha@2026",
            is_staff=True,
        )
        self.superusuario_filial_a = User.objects.create_user(
            username="superuser.filial.a.logs.apont",
            password="Senha@2026",
            is_staff=False,
            is_superuser=True,
            filial=filial_a,
        )

        self.apontamento_empresa_a = self._criar_apontamento(codemp=empresa_a.codemp, numorp=100)
        self.apontamento_empresa_b = self._criar_apontamento(codemp=empresa_b.codemp, numorp=200)

    @patch("producao.views.logs_apontamentos.disparar_envio_apontamentos")
    def test_enviar_de_outra_filial_nao_encontra_registro(self, mock_disparar):
        self.client.force_login(self.usuario_filial_a)

        resposta = self.client.post(
            reverse("enviar_apontamento_log", args=[self.apontamento_empresa_b.pk])
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertNotEqual(resposta.url, reverse("logs_apontamentos"))
        mock_disparar.assert_not_called()
        self.assertEqual(Apontamento.objects.get(pk=self.apontamento_empresa_b.pk).status, 0)

    @patch("producao.views.logs_apontamentos.disparar_envio_apontamentos")
    def test_enviar_da_propria_filial_funciona(self, mock_disparar):
        self.client.force_login(self.usuario_filial_a)

        self.client.post(reverse("enviar_apontamento_log", args=[self.apontamento_empresa_a.pk]))

        mock_disparar.assert_called_once_with([self.apontamento_empresa_a.pk])

    @patch("producao.views.logs_apontamentos.disparar_envio_apontamentos")
    def test_staff_enviar_de_qualquer_filial_funciona(self, mock_disparar):
        self.client.force_login(self.usuario_staff)

        self.client.post(reverse("enviar_apontamento_log", args=[self.apontamento_empresa_b.pk]))

        mock_disparar.assert_called_once_with([self.apontamento_empresa_b.pk])

    @patch("producao.views.logs_apontamentos.disparar_envio_apontamentos")
    def test_enviar_todos_nao_staff_so_processa_propria_filial(self, mock_disparar):
        self.client.force_login(self.usuario_filial_a)

        self.client.post(reverse("enviar_todos_apontamentos_log"))

        mock_disparar.assert_called_once()
        (ids_enviados,), _ = mock_disparar.call_args
        self.assertIn(self.apontamento_empresa_a.pk, ids_enviados)
        self.assertNotIn(self.apontamento_empresa_b.pk, ids_enviados)
        self.assertEqual(Apontamento.objects.get(pk=self.apontamento_empresa_b.pk).status, 0)

    @patch("producao.views.logs_apontamentos.disparar_envio_apontamentos")
    def test_enviar_todos_staff_processa_todas_as_filiais(self, mock_disparar):
        self.client.force_login(self.usuario_staff)

        self.client.post(reverse("enviar_todos_apontamentos_log"))

        mock_disparar.assert_called_once_with()

    def test_excluir_de_outra_filial_nao_encontra_registro(self):
        self.client.force_login(self.superusuario_filial_a)

        resposta = self.client.post(
            reverse("excluir_apontamento_erp", args=[self.apontamento_empresa_b.pk])
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertNotEqual(resposta.url, reverse("logs_apontamentos"))
        self.assertTrue(Apontamento.objects.filter(pk=self.apontamento_empresa_b.pk).exists())

    def test_excluir_da_propria_filial_funciona(self):
        self.client.force_login(self.superusuario_filial_a)

        self.client.post(reverse("excluir_apontamento_erp", args=[self.apontamento_empresa_a.pk]))

        self.assertFalse(Apontamento.objects.filter(pk=self.apontamento_empresa_a.pk).exists())

    def test_excluir_todos_nao_staff_so_apaga_propria_filial(self):
        self.client.force_login(self.superusuario_filial_a)

        self.client.post(reverse("excluir_todos_apontamentos_log"))

        self.assertFalse(Apontamento.objects.filter(pk=self.apontamento_empresa_a.pk).exists())
        self.assertTrue(Apontamento.objects.filter(pk=self.apontamento_empresa_b.pk).exists())
