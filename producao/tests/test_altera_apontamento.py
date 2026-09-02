"""Testes de producao/services/altera_apontamento.py.

Primeiros testes deste código (movido de producao/utils/ nesta auditoria).
Cobrem os quatro fluxos de negócio de `corrigir_quantidade_lote` (sem ERP,
incremento, redução com rateio no ERP, quantidade igual) e a proteção de CDATA nos
dois webservices que montam envelope SOAP diretamente aqui. Oracle e a
chamada SOAP são sempre mockados — nenhuma rede real, nenhum Oracle real.
O transporte é o client compartilhado `enviar_soap_sapiens()`; por resolver
`requests.post` em tempo de execução, o mock é feito no módulo do client.
"""

import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import Empresa, Filial
from producao.models.estrutura import Apontamento, CorrecaoLote
from producao.services import altera_apontamento as svc


def _criar_apontamento(**kwargs):
    dados = {
        "codemp": 1,
        "origem": "1",
        "numorp": 100,
        "codetg": 1,
        "seqrot": 1,
        "numcad": 1,
        "qtdre1": 10,
        "lote": "LOTE1",
    }
    dados.update(kwargs)
    return Apontamento.objects.create(**dados)


def _usuario(codemp=1):
    """Cria usuário com filial/empresa reais — codemp precisa vir daqui, nunca
    de erp_params (achado de segurança: POST forjava a empresa usada na correção)."""
    empresa = Empresa.objects.create(codemp=codemp, nome=f"Empresa {codemp}", fantasia=f"E{codemp}")
    filial = Filial.objects.create(
        empresa=empresa,
        codfil=1,
        nome=f"Filial {codemp}",
        fantasia=f"F{codemp}",
        cnpj="22.222.222/0001-22",
    )
    return get_user_model().objects.create_user(
        username=f"tester{codemp}", password="x", filial=filial
    )


class ExtrairMensagemSoapTests(TestCase):
    """Achado seguranca (rodada 4): fallback sem tag conhecida devolvia o texto cru,
    que pode ecoar o envelope da requisicao (com credencial) num SOAP fault."""

    def test_fallback_sem_tag_conhecida_mascara_credencial(self):
        resposta = "<fault><user>user_teste</user><password>senha_teste_123</password></fault>"

        mensagem = svc.extrair_mensagem_soap(resposta)

        self.assertNotIn("senha_teste_123", mensagem)
        self.assertNotIn("user_teste", mensagem)
        self.assertIn("<password>***</password>", mensagem)
        self.assertIn("<user>***</user>", mensagem)


class PostSoapSapiensTests(TestCase):
    """Achado seguranca (rodada 4): o conteudo de <waRetorno> num status de falha
    tambem precisa estar mascarado antes de virar mensagem de erro na tela."""

    @patch("producao.services.sapiens.requests.post")
    def test_waretorno_com_falha_mascara_credencial(self, mock_post):
        resposta = Mock(
            status_code=200,
            text=(
                '<waRetorno>{"status": "ERRO", '
                '"user": "<user>user_teste</user>", '
                '"password": "<password>senha_teste_123</password>"}</waRetorno>'
            ),
        )
        mock_post.return_value = resposta

        sucesso, msg = svc.post_soap_sapiens("qualquer", "<envelope/>")

        self.assertFalse(sucesso)
        self.assertNotIn("senha_teste_123", msg)
        self.assertNotIn("user_teste", msg)
        self.assertEqual(msg, "ERP recusou a operação.")

    @patch("producao.services.sapiens.requests.post")
    def test_excecao_de_rede_mascara_credencial(self, mock_post):
        """Rodada extra: o invariante do módulo é mascarar toda exceção que passou
        perto do Sapiens antes de sair da função, mesmo numa falha de rede."""
        mock_post.side_effect = ConnectionError(
            "falha ao conectar <user>user_teste</user><password>senha_teste_123</password>"
        )

        sucesso, msg = svc.post_soap_sapiens("qualquer", "<envelope/>")

        self.assertFalse(sucesso)
        self.assertNotIn("senha_teste_123", msg)
        self.assertNotIn("user_teste", msg)
        self.assertEqual(msg, "Falha ao comunicar com o ERP.")


class CdataWebserviceTests(TestCase):
    """Achado alto: ']]>' no payload não pode fechar o CDATA antes da hora.
    O timeout de 180s do comportamento anterior é contrato deste módulo
    e fica travado aqui."""

    @patch("producao.services.sapiens.requests.post")
    def test_diminuir_apontamento_escapa_sequencia_fecha_cdata(self, mock_post):
        resposta = Mock(status_code=200, text="Processado com sucesso.")
        mock_post.return_value = resposta

        svc._chamar_webservice_diminuir_apontamento(
            codemp=1,
            codori="1]]><forjado>1</forjado>",
            numorp=100,
            codetg=1,
            codlot="LOTE1",
            numbob=1,
            codcre="M1",
            qtdre1=4,
        )

        self.assertEqual(mock_post.call_args.kwargs["timeout"], 180)
        envelope = mock_post.call_args.kwargs["data"].decode("ISO-8859-1")
        raiz = ET.fromstring(envelope)
        self.assertIsNone(raiz.find(".//forjado"))
        self.assertIn("forjado", envelope)
        self.assertIn('"QtdRe1": "4"', envelope)
        self.assertNotIn("SeqEoq", envelope)

    @patch("producao.services.sapiens.requests.post")
    def test_aumentar_apontamento_escapa_sequencia_fecha_cdata(self, mock_post):
        resposta = Mock(status_code=200, text="Processado com sucesso.")
        mock_post.return_value = resposta

        svc._chamar_webservice_aumentar_apontamento(
            usuario="u",
            senha="s",
            codemp=1,
            codori="1]]><forjado>1</forjado>",
            numorp=100,
            numcad=1,
            codetg=1,
            seqrot=1,
            qtdre1=5,
            qtdrfg=0,
            numbob=1,
            nummaq="M1",
            datmov="01/01/2026",
            hormov="00:00:00",
        )

        envelope = mock_post.call_args.kwargs["data"].decode("ISO-8859-1")
        raiz = ET.fromstring(envelope)
        self.assertIsNone(raiz.find(".//forjado"))
        self.assertIn("forjado", envelope)


def _erp_info_integrado(qtd_total=10.0):
    return {
        "integrado_erp": True,
        "codori": "1",
        "numorp": 100,
        "codetg": 1,
        "codcre": "M1",
        "numbob": 1,
        "codpro": "P1",
        "codder": "D1",
        "qtdre1": qtd_total,
        "seqrot": 1,
        "numcad": 1,
        "erp_rows": [
            {"seqeoq": 1, "qtdre1": qtd_total, "codori": "1", "numorp": 100, "codetg": 1},
        ],
    }


def _recurso_mock():
    recurso = Mock()
    recurso.get_parametros_efetivos.return_value = {
        "limite_apontamento_minimo": 0,
        "limite_apontamento_maximo": 999999,
        "deposito_apontamento_erp": "01",
    }
    return recurso


class CorrigirQuantidadeLoteSemErpTests(TestCase):
    """Fluxo quando o lote não está integrado no ERP: só ajusta o registro local."""

    @patch("producao.services.altera_apontamento._buscar_recurso_para_correcao")
    @patch("producao.services.altera_apontamento.buscar_dados_lote_erp_logic")
    def test_atualiza_local_quando_nao_integrado_no_erp(self, mock_busca, mock_recurso):
        mock_busca.return_value = ({"integrado_erp": False}, 200)
        mock_recurso.return_value = _recurso_mock()
        _criar_apontamento(qtdre1=10)
        usuario = _usuario()

        sucesso, logs = svc.corrigir_quantidade_lote(
            "lote1", 15, usuario, erp_params={"codemp": 999}
        )

        self.assertTrue(sucesso, logs)
        self.assertEqual(float(Apontamento.objects.get(lote="LOTE1").qtdre1), 15)

    @patch("producao.services.altera_apontamento._buscar_recurso_para_correcao")
    @patch("producao.services.altera_apontamento.buscar_dados_lote_erp_logic")
    def test_exclui_localmente_quando_acao_excluir(self, mock_busca, mock_recurso):
        mock_busca.return_value = ({"integrado_erp": False}, 200)
        mock_recurso.return_value = _recurso_mock()
        _criar_apontamento(qtdre1=10)
        usuario = _usuario()

        sucesso, logs = svc.corrigir_quantidade_lote(
            "lote1", 0, usuario, erp_params={"codemp": 999, "acao_correcao": "excluir"}
        )

        self.assertTrue(sucesso, logs)
        apont = Apontamento.objects.get(lote="LOTE1")
        self.assertEqual(apont.status, 3)
        self.assertEqual(float(apont.qtdre1), 0)

    @patch("producao.services.altera_apontamento._buscar_recurso_para_correcao")
    @patch("producao.services.altera_apontamento.buscar_dados_lote_erp_logic")
    def test_bloqueia_correcao_com_quantidade_atual_zero(self, mock_busca, mock_recurso):
        mock_busca.return_value = ({"integrado_erp": False}, 200)
        mock_recurso.return_value = _recurso_mock()
        _criar_apontamento(qtdre1=0)
        usuario = _usuario()

        sucesso, logs = svc.corrigir_quantidade_lote(
            "lote1", 5, usuario, erp_params={"codemp": 999}
        )

        self.assertFalse(sucesso)

    @patch("producao.services.altera_apontamento._buscar_recurso_para_correcao")
    @patch("producao.services.altera_apontamento.buscar_dados_lote_erp_logic")
    def test_repeticao_da_mesma_correcao_local_retorna_resultado_persistido(
        self, mock_busca, mock_recurso
    ):
        mock_busca.return_value = ({"integrado_erp": False}, 200)
        mock_recurso.return_value = _recurso_mock()
        _criar_apontamento(qtdre1=10)
        usuario = _usuario()

        self.assertTrue(svc.corrigir_quantidade_lote("lote1", 15, usuario)[0])
        sucesso, logs = svc.corrigir_quantidade_lote("lote1", 15, usuario)

        self.assertTrue(sucesso, logs)
        self.assertEqual(mock_busca.call_count, 1)
        self.assertEqual(
            CorrecaoLote.objects.get(codemp=1, lote="LOTE1").status,
            CorrecaoLote.Status.CONCLUIDA,
        )

    @patch("producao.services.altera_apontamento.buscar_dados_lote_erp_logic")
    def test_operacao_em_andamento_bloqueia_nova_correcao(self, mock_busca):
        usuario = _usuario()
        CorrecaoLote.objects.create(
            codemp=1,
            lote="LOTE1",
            quantidade=10,
            status=CorrecaoLote.Status.EM_ANDAMENTO,
        )

        sucesso, _ = svc.corrigir_quantidade_lote("LOTE1", 15, usuario)

        self.assertFalse(sucesso)
        mock_busca.assert_not_called()


@patch("producao.services.altera_apontamento.cursor_oracle_erp")
@patch("producao.services.altera_apontamento._validar_lote_bobina_deposito_consulta")
@patch("producao.services.altera_apontamento.get_operator_name")
@patch("producao.services.altera_apontamento._buscar_recurso_para_correcao")
@patch("producao.services.altera_apontamento.buscar_dados_lote_erp_logic")
class CorrigirQuantidadeLoteIntegradoErpTests(TestCase):
    """Fluxos com o lote integrado no ERP: incremento, redução com rateio e igual.

    O cursor Oracle compartilhado também é mockado aqui: mesmo com
    `get_operator_name` mockado, a função consulta o ERP antes de chamá-lo e
    isso não pode virar uma conexão Oracle real em teste.
    """

    @patch("producao.services.altera_apontamento._chamar_webservice_aumentar_apontamento")
    def test_incremento_atualiza_local_quando_webservice_confirma(
        self, mock_ws, mock_busca, mock_recurso, mock_operador, mock_valida, mock_connections
    ):
        mock_busca.return_value = (_erp_info_integrado(qtd_total=10.0), 200)
        mock_recurso.return_value = _recurso_mock()
        mock_operador.return_value = "OPERADOR TESTE"
        mock_valida.return_value = (True, "")
        mock_ws.return_value = (True, "OK")
        _criar_apontamento(qtdre1=10)
        usuario = _usuario()

        sucesso, logs = svc.corrigir_quantidade_lote(
            "lote1", 15, usuario, erp_params={"codemp": 999}
        )

        self.assertTrue(sucesso, logs)
        self.assertEqual(float(Apontamento.objects.get(lote="LOTE1").qtdre1), 15)
        # o incremento enviado ao ERP é a diferença sobre o total do lote, não sobre o local
        _, kwargs = mock_ws.call_args
        self.assertEqual(kwargs["qtdre1"], 5.0)

    @patch("producao.services.altera_apontamento._chamar_webservice_aumentar_apontamento")
    def test_codemp_forjado_em_erp_params_e_ignorado(
        self, mock_ws, mock_busca, mock_recurso, mock_operador, mock_valida, mock_connections
    ):
        """Achado de segurança: as views de correção de lote (logs_apontamentos.py e
        apontamentos_v1.py) repassavam `codemp_erp` cru do POST em `erp_params`, e essa
        função sobrescrevia o codemp do usuário autenticado por ele — um usuário com
        `pode_corrigir_lote` conseguia forjar a empresa usada para validar limites do
        recurso e montar o envelope SOAP enviado ao Sapiens. codemp tem que vir sempre
        de `get_codemp_usuario(usuario_obj)`, nunca de erp_params/POST."""
        mock_busca.return_value = (_erp_info_integrado(qtd_total=10.0), 200)
        mock_recurso.return_value = _recurso_mock()
        mock_operador.return_value = "OPERADOR TESTE"
        mock_valida.return_value = (True, "")
        mock_ws.return_value = (True, "OK")
        _criar_apontamento(qtdre1=10, codemp=1)
        usuario = _usuario(codemp=1)

        sucesso, logs = svc.corrigir_quantidade_lote(
            "lote1", 15, usuario, erp_params={"codemp": 999}
        )

        self.assertTrue(sucesso, logs)
        # codemp usado para localizar/validar o recurso é o do usuário (1), não o forjado (999)
        self.assertEqual(mock_recurso.call_args.args[1], 1)
        # codemp usado no envelope SOAP enviado ao Sapiens também é o do usuário
        self.assertEqual(mock_ws.call_args.kwargs["codemp"], 1)

    @patch("producao.services.altera_apontamento._chamar_webservice_aumentar_apontamento")
    def test_incremento_nao_atualiza_local_quando_webservice_falha(
        self, mock_ws, mock_busca, mock_recurso, mock_operador, mock_valida, mock_connections
    ):
        """Guarda de integração: falha no Sapiens não pode marcar como integrado.

        AumentarApontamento/DiminuirApontamento são idempotentes na regra
        personalizada do ERP (reenviar uma correção já aplicada não duplica o
        efeito), então falha após chamada ao ERP cai em FALHA — libera nova
        tentativa sem exigir conciliação manual (ver `_finalizar_correcao_lote`).
        """
        mock_busca.return_value = (_erp_info_integrado(qtd_total=10.0), 200)
        mock_recurso.return_value = _recurso_mock()
        mock_operador.return_value = "OPERADOR TESTE"
        mock_valida.return_value = (True, "")
        mock_ws.return_value = (False, "erroExecucao preenchido")
        _criar_apontamento(qtdre1=10)
        usuario = _usuario()

        sucesso, logs = svc.corrigir_quantidade_lote(
            "lote1", 15, usuario, erp_params={"codemp": 999}
        )

        self.assertFalse(sucesso)
        self.assertEqual(float(Apontamento.objects.get(lote="LOTE1").qtdre1), 10)
        self.assertEqual(
            CorrecaoLote.objects.get(codemp=1, lote="LOTE1").status,
            CorrecaoLote.Status.FALHA,
        )
        sucesso_retry, _ = svc.corrigir_quantidade_lote("LOTE1", 16, usuario)
        self.assertFalse(sucesso_retry)
        self.assertEqual(mock_ws.call_count, 2)

    @patch("producao.services.altera_apontamento._chamar_webservice_aumentar_apontamento")
    def test_incremento_nao_altera_lote_igual_de_outra_empresa(
        self, mock_ws, mock_busca, mock_recurso, mock_operador, mock_valida, mock_connections
    ):
        mock_busca.return_value = (_erp_info_integrado(qtd_total=10.0), 200)
        mock_recurso.return_value = _recurso_mock()
        mock_operador.return_value = "OPERADOR TESTE"
        mock_valida.return_value = (True, "")
        mock_ws.return_value = (True, "OK")
        _criar_apontamento(qtdre1=10, codemp=1)
        outro = _criar_apontamento(qtdre1=99, codemp=2, lote="LOTE1")
        usuario = _usuario(codemp=1)

        sucesso, logs = svc.corrigir_quantidade_lote("lote1", 15, usuario)

        self.assertTrue(sucesso, logs)
        outro.refresh_from_db()
        self.assertEqual(float(outro.qtdre1), 99)

    @patch("producao.services.altera_apontamento._chamar_webservice_aumentar_apontamento")
    def test_incremento_com_excecao_no_webservice_mascara_credencial_no_log(
        self, mock_ws, mock_busca, mock_recurso, mock_operador, mock_valida, mock_connections
    ):
        """Rodada extra: exceção ao chamar o webservice de incremento não pode
        vazar credencial crua no log local (`logs.append`), que é exibido/persistido."""
        mock_busca.return_value = (_erp_info_integrado(qtd_total=10.0), 200)
        mock_recurso.return_value = _recurso_mock()
        mock_operador.return_value = "OPERADOR TESTE"
        mock_valida.return_value = (True, "")
        mock_ws.side_effect = ConnectionError(
            "falha <user>user_teste</user><password>senha_teste_123</password>"
        )
        _criar_apontamento(qtdre1=10)
        usuario = _usuario()

        sucesso, logs = svc.corrigir_quantidade_lote(
            "lote1", 15, usuario, erp_params={"codemp": 999}
        )

        self.assertFalse(sucesso)
        mensagens = " ".join(logs)
        self.assertNotIn("senha_teste_123", mensagens)
        self.assertNotIn("user_teste", mensagens)
        self.assertIn("<password>***</password>", mensagens)
        self.assertIn("<user>***</user>", mensagens)

    @patch("producao.services.altera_apontamento._chamar_webservice_diminuir_apontamento")
    def test_reducao_envia_uma_quantidade_final_e_atualiza_local(
        self,
        mock_ws,
        mock_busca,
        mock_recurso,
        mock_operador,
        mock_valida,
        mock_connections,
    ):
        mock_busca.return_value = (_erp_info_integrado(qtd_total=10.0), 200)
        mock_recurso.return_value = _recurso_mock()
        mock_operador.return_value = "OPERADOR TESTE"
        mock_valida.return_value = (True, "")
        mock_ws.return_value = (True, "OK")
        _criar_apontamento(qtdre1=10)
        usuario = _usuario()

        sucesso, logs = svc.corrigir_quantidade_lote(
            "lote1", 4, usuario, erp_params={"codemp": 999}
        )

        self.assertTrue(sucesso, logs)
        self.assertEqual(float(Apontamento.objects.get(lote="LOTE1").qtdre1), 4)
        mock_ws.assert_called_once()
        kwargs = mock_ws.call_args.kwargs
        self.assertEqual(kwargs["qtdre1"], 4)
        self.assertNotIn("seqeoq", kwargs)

    @patch("producao.services.altera_apontamento._chamar_webservice_diminuir_apontamento")
    def test_reducao_falha_no_webservice_nao_atualiza_local(
        self, mock_ws, mock_busca, mock_recurso, mock_operador, mock_valida, mock_connections
    ):
        mock_busca.return_value = (_erp_info_integrado(qtd_total=10.0), 200)
        mock_recurso.return_value = _recurso_mock()
        mock_operador.return_value = "OPERADOR TESTE"
        mock_valida.return_value = (True, "")
        mock_ws.return_value = (False, "erroExecucao preenchido")
        _criar_apontamento(qtdre1=10)
        usuario = _usuario()

        sucesso, logs = svc.corrigir_quantidade_lote(
            "lote1", 4, usuario, erp_params={"codemp": 999}
        )

        self.assertFalse(sucesso)
        self.assertEqual(float(Apontamento.objects.get(lote="LOTE1").qtdre1), 10)

    def test_quantidade_igual_nao_chama_nenhum_webservice(
        self, mock_busca, mock_recurso, mock_operador, mock_valida, mock_connections
    ):
        mock_busca.return_value = (_erp_info_integrado(qtd_total=10.0), 200)
        mock_recurso.return_value = _recurso_mock()
        mock_operador.return_value = "OPERADOR TESTE"
        mock_valida.return_value = (True, "")
        _criar_apontamento(qtdre1=10)
        usuario = _usuario()

        with (
            patch(
                "producao.services.altera_apontamento._chamar_webservice_aumentar_apontamento"
            ) as mock_aumenta,
            patch(
                "producao.services.altera_apontamento._chamar_webservice_diminuir_apontamento"
            ) as mock_diminui,
        ):
            sucesso, logs = svc.corrigir_quantidade_lote(
                "lote1", 10, usuario, erp_params={"codemp": 999}
            )

        self.assertTrue(sucesso, logs)
        mock_aumenta.assert_not_called()
        mock_diminui.assert_not_called()
        self.assertEqual(float(Apontamento.objects.get(lote="LOTE1").qtdre1), 10)

    def test_quantidade_igual_nao_altera_lote_igual_de_outra_empresa(
        self, mock_busca, mock_recurso, mock_operador, mock_valida, mock_connections
    ):
        mock_busca.return_value = (_erp_info_integrado(qtd_total=10.0), 200)
        mock_recurso.return_value = _recurso_mock()
        mock_operador.return_value = "OPERADOR TESTE"
        mock_valida.return_value = (True, "")
        _criar_apontamento(qtdre1=10, codemp=1)
        outro = _criar_apontamento(qtdre1=99, codemp=2, lote="LOTE1")
        usuario = _usuario(codemp=1)

        sucesso, logs = svc.corrigir_quantidade_lote("lote1", 10, usuario)

        self.assertTrue(sucesso, logs)
        outro.refresh_from_db()
        self.assertEqual(float(outro.qtdre1), 99)
