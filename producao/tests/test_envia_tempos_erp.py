"""Testes da fila de envio de tempos ao ERP (producao/services/envia_tempos_erp.py).

Cobrem:
- a senha do Sapiens não pode aparecer em nenhuma saída de log, inclusive no
  campo `log` persistido;
- o payload embutido no CDATA do envelope SOAP não pode quebrar o XML nem
  injetar estrutura quando contém a sequência ']]>';
- o ciclo de vida sem estado ERRO próprio: falha de envio volta a PENDENTE
  (reenviável, motivo só no log), sucesso grava INTEGRADO e PROCESSANDO é o
  valor 2 — alinhamento da fila às demais filas de integração.
"""

import xml.etree.ElementTree as ET
from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor
from producao.models import LogTrocaOPAtiva, PacoteTempoERP
from producao.services import envia_tempos_erp as svc


def _resposta_soap(texto='<waRetorno>{"status": "OK"}</waRetorno>', status_code=200):
    resposta = Mock()
    resposta.ok = status_code == 200
    resposta.status_code = status_code
    resposta.text = texto
    return resposta


@override_settings(SAPIENS_USERNAME="usuario_sapiens", SAPIENS_PASSWORD="segredo_super_secreto")
class ChamarApontamentoTemposErpTests(TestCase):
    """Achado crítico: credencial do Sapiens vazando em log de produção."""

    @patch("producao.services.sapiens.requests.post")
    def test_senha_nunca_aparece_em_log_algum(self, mock_post):
        mock_post.return_value = _resposta_soap()

        with self.assertLogs("producao.services.envia_tempos_erp", level="DEBUG") as captura:
            svc.chamar_apontamento_tempos_erp({"wacao": "APONTAMENTO-TEMPOS"})

        saida = "\n".join(captura.output)
        self.assertNotIn("segredo_super_secreto", saida)
        # a máscara precisa de fato ter substituído o conteúdo da tag, não só omitido o log
        self.assertIn("<password>***</password>", saida)

    @patch("producao.services.sapiens.requests.post")
    def test_usuario_tambem_nao_aparece_em_log(self, mock_post):
        mock_post.return_value = _resposta_soap()

        with self.assertLogs("producao.services.envia_tempos_erp", level="DEBUG") as captura:
            svc.chamar_apontamento_tempos_erp({"wacao": "APONTAMENTO-TEMPOS"})

        saida = "\n".join(captura.output)
        self.assertNotIn("usuario_sapiens", saida)
        self.assertIn("<user>***</user>", saida)

    @patch("producao.services.sapiens.requests.post")
    def test_sequencia_fecha_cdata_nao_quebra_nem_injeta_xml(self, mock_post):
        """Achado alto: ']]>' no payload não pode fechar o CDATA antes da hora."""
        mock_post.return_value = _resposta_soap()

        payload = {
            "wacao": "APONTAMENTO-TEMPOS",
            "producoes": [{"operador": "1]]><forjado>1</forjado>"}],
        }
        svc.chamar_apontamento_tempos_erp(payload)

        envelope = mock_post.call_args.kwargs["data"].decode("ISO-8859-1")
        # o XML resultante precisa continuar bem formado...
        raiz = ET.fromstring(envelope)
        # ...e o valor malicioso deve permanecer como dado inerte, nunca como elemento novo
        self.assertIsNone(raiz.find(".//forjado"))
        self.assertIn("forjado", envelope)

    @patch("producao.services.sapiens.requests.post")
    def test_resposta_http_com_erro_levanta_excecao(self, mock_post):
        mock_post.return_value = _resposta_soap(texto="erro interno", status_code=500)

        with self.assertRaises(RuntimeError):
            svc.chamar_apontamento_tempos_erp({"wacao": "APONTAMENTO-TEMPOS"})


class ProcessarPacoteRegistraLogMascaradoTests(TestCase):
    """Achado seguranca (rodada 4): política mudou — o campo `log` persistido
    tambem precisa estar mascarado. `PacoteTempoERP.objects` é mockado para
    isolar do encadeamento real de troca_op_ativa/recurso/centro/setor/etc.,
    que este teste não precisa montar para provar a máscara na gravação."""

    @patch("producao.services.envia_tempos_erp._chave_op")
    @patch("producao.services.envia_tempos_erp.montar_payload_apontamento_tempos")
    @patch("producao.services.envia_tempos_erp.chamar_apontamento_tempos_erp")
    def test_resposta_sem_sucesso_persiste_log_mascarado(
        self, mock_chamar, mock_montar, mock_chave
    ):
        mock_chave.return_value = ("chave",)
        mock_montar.return_value = {}
        # Sem tag <waRetorno> nem "processado com sucesso": _retorno_sucesso cai
        # no fallback e devolve o texto cru, que aqui carrega a credencial.
        mock_chamar.return_value = "<user>user_teste</user><password>senha_teste_123</password>"

        fake_pacote = Mock(id=1)
        mock_manager = Mock()
        mock_manager.select_related.return_value.prefetch_related.return_value.get.return_value = (
            fake_pacote
        )
        mock_filtro = Mock()
        mock_manager.filter.return_value = mock_filtro

        with patch.object(svc.PacoteTempoERP, "objects", mock_manager):
            svc._processar_pacote(1)

        _, kwargs = mock_filtro.update.call_args
        self.assertNotIn("senha_teste_123", kwargs["log"])
        self.assertNotIn("user_teste", kwargs["log"])
        self.assertIn("<password>***</password>", kwargs["log"])
        self.assertIn("<user>***</user>", kwargs["log"])
        # Falha de negócio não tem estado próprio: volta a PENDENTE, reenviável.
        self.assertEqual(kwargs["status"], PacoteTempoERP.Status.PENDENTE)

    @patch("producao.services.envia_tempos_erp._chave_op")
    @patch("producao.services.envia_tempos_erp.montar_payload_apontamento_tempos")
    @patch("producao.services.envia_tempos_erp.chamar_apontamento_tempos_erp")
    def test_excecao_persiste_log_mascarado(self, mock_chamar, mock_montar, mock_chave):
        mock_chave.return_value = ("chave",)
        mock_montar.return_value = {}
        mock_chamar.side_effect = RuntimeError(
            "<user>user_teste</user><password>senha_teste_123</password>"
        )

        fake_pacote = Mock(id=1)
        mock_manager = Mock()
        mock_manager.select_related.return_value.prefetch_related.return_value.get.return_value = (
            fake_pacote
        )
        mock_filtro = Mock()
        mock_manager.filter.return_value = mock_filtro

        with patch.object(svc.PacoteTempoERP, "objects", mock_manager):
            svc._processar_pacote(1)

        _, kwargs = mock_filtro.update.call_args
        self.assertNotIn("senha_teste_123", kwargs["log"])
        self.assertIn("<password>***</password>", kwargs["log"])
        # Exceção de transporte tem o mesmo desfecho da falha de negócio.
        self.assertEqual(kwargs["status"], PacoteTempoERP.Status.PENDENTE)

    @patch("producao.services.envia_tempos_erp._chave_op")
    @patch("producao.services.envia_tempos_erp.montar_payload_apontamento_tempos")
    @patch("producao.services.envia_tempos_erp.chamar_apontamento_tempos_erp")
    def test_sucesso_persiste_integrado(self, mock_chamar, mock_montar, mock_chave):
        mock_chave.return_value = ("chave",)
        mock_montar.return_value = {}
        mock_chamar.return_value = '<waRetorno>{"status": "OK"}</waRetorno>'

        fake_pacote = Mock(id=1)
        mock_manager = Mock()
        mock_manager.select_related.return_value.prefetch_related.return_value.get.return_value = (
            fake_pacote
        )
        mock_filtro = Mock()
        mock_manager.filter.return_value = mock_filtro

        with patch.object(svc.PacoteTempoERP, "objects", mock_manager):
            svc._processar_pacote(1)

        _, kwargs = mock_filtro.update.call_args
        self.assertEqual(kwargs["status"], PacoteTempoERP.Status.INTEGRADO)


class FilaTemposErpCicloDeVidaTests(TestCase):
    """Ciclo de vida da fila contra o banco, sem estado ERRO próprio: falha de
    envio volta a PENDENTE com o motivo mascarado no log e é reenviável;
    sucesso grava INTEGRADO e trava o pacote; PROCESSANDO ocupa o valor 2."""

    @classmethod
    def setUpTestData(cls):
        empresa = Empresa.objects.create(codemp=91, nome="Empresa Tempo", fantasia="ET")
        filial = Filial.objects.create(
            empresa=empresa,
            codfil=1,
            nome="Filial Tempo",
            fantasia="FT",
            cnpj="91.111.111/0001-91",
        )
        departamento = Departamento.objects.create(filial=filial, descricao="Depto Tempo")
        setor = Setor.objects.create(departamento=departamento, descricao="Setor Tempo")
        centro = CentroRecurso.objects.create(
            setor=setor,
            codigo="CR-TMPO",
            descricao="Centro Tempo",
            codigo_integrador="CR-TMPO",
        )
        cls.recurso = Recurso.objects.create(
            codigo="R-TMPO", descricao="Recurso Tempo", centro_recurso=centro
        )

    def _criar_pacote(self):
        agora = timezone.now()
        troca = LogTrocaOPAtiva.objects.create(
            recurso=self.recurso,
            origem="1",
            op=100,
            estagio=1,
            seqrot=1,
            horario_troca=agora - timedelta(hours=8),
        )
        return PacoteTempoERP.objects.create(
            troca_op_ativa=troca,
            corte_inicio_real=agora - timedelta(hours=4),
            corte_fim_real=agora,
        )

    def test_reserva_grava_processando_valor_2_e_liberacao_devolve_pendente(self):
        pacote = self._criar_pacote()

        ids = svc.reservar_pacotes_tempo_erp_para_envio()

        self.assertEqual(ids, [pacote.id])
        pacote.refresh_from_db()
        self.assertEqual(pacote.status, PacoteTempoERP.Status.PROCESSANDO)
        # Fixa a numeração nova: PROCESSANDO é 2 após a reenumeração.
        self.assertEqual(pacote.status, 2)

        liberados = svc.liberar_pacotes_tempo_erp_processando_antigos()
        self.assertEqual(liberados, 1)
        pacote.refresh_from_db()
        self.assertEqual(pacote.status, PacoteTempoERP.Status.PENDENTE)

    def test_falha_de_envio_volta_a_pendente_com_log_e_reenviavel(self):
        pacote = self._criar_pacote()
        # O worker só grava resultado sobre reserva própria (guarda por
        # PROCESSANDO): reservar antes, como a fila real faz.
        reservado, _mensagem = svc.reservar_pacote_tempo_erp_para_envio(pacote.id)
        self.assertTrue(reservado)

        with patch.object(svc, "chamar_apontamento_tempos_erp") as mock_chamar:
            mock_chamar.side_effect = RuntimeError(
                "<user>user_teste</user><password>senha_teste_123</password>"
            )
            sucesso, _ = svc._processar_pacote(pacote.id)

        self.assertFalse(sucesso)
        pacote.refresh_from_db()
        self.assertEqual(pacote.status, PacoteTempoERP.Status.PENDENTE)
        self.assertNotIn("senha_teste_123", pacote.log)
        self.assertIn("Erro ao enviar pacote", pacote.log)
        # Reenviável: a reserva aceita novamente um registro que falhou,
        # porque falha É pendência nesta fila.
        reservado, _mensagem = svc.reservar_pacote_tempo_erp_para_envio(pacote.id)
        self.assertTrue(reservado)

    def test_sucesso_grava_integrado_e_trava_reenvio(self):
        pacote = self._criar_pacote()
        reservado, _mensagem = svc.reservar_pacote_tempo_erp_para_envio(pacote.id)
        self.assertTrue(reservado)

        with patch.object(svc, "chamar_apontamento_tempos_erp") as mock_chamar:
            mock_chamar.return_value = '<waRetorno>{"status": "OK"}</waRetorno>'
            sucesso, _ = svc._processar_pacote(pacote.id)

        self.assertTrue(sucesso)
        pacote.refresh_from_db()
        self.assertEqual(pacote.status, PacoteTempoERP.Status.INTEGRADO)
        # Integrado não é mais elegível para envio.
        reservado, _mensagem = svc.reservar_pacote_tempo_erp_para_envio(pacote.id)
        self.assertFalse(reservado)
