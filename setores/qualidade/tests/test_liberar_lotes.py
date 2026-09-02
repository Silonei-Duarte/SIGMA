"""Teste de setores/qualidade/views/liberar_lotes.py.

Achado alto desta rodada de auditoria: o payload da movimentação para Área
Vermelha era embutido no CDATA do envelope SOAP sem `escapar_cdata_sapiens`.
`buscar_recurso_por_codigo` e `post_soap_sapiens` são mockados para isolar o
teste da navegação por Recurso/Filial e da chamada HTTP real — o que se testa
aqui é só a montagem e o escape do envelope.

Achado alto de uma rodada seguinte: `codemp` vinha de `selected_row` (POST cru)
com prioridade sobre a empresa real do usuário logado nas três funções que
decidem sob qual empresa o lote é liberado/validado/movido no ERP — mesma
classe de vulnerabilidade já fechada em `producao` (ver
`producao/tests/test_altera_apontamento.py::test_codemp_forjado_em_erp_params_e_ignorado`).
Os testes abaixo forjam um `codemp` diferente do da filial do usuário e
confirmam que o valor efetivo usado é sempre o real.
"""

import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from setores.qualidade.views import liberar_lotes as views


def _request(**overrides_filial):
    parametros_filial = SimpleNamespace(
        codtns="90253",
        deposito_area_vermelha_erp="01.99",
        deposito_armazenamento_erp="01.10",
        deposito_armazenamento_wms="A1",
    )
    filial = SimpleNamespace(
        empresa=SimpleNamespace(codemp=1),
        parametros_filial=parametros_filial,
        codfil=1,
        idintegracao=1186,
    )
    for chave, valor in overrides_filial.items():
        setattr(filial, chave, valor)
    user = SimpleNamespace(filial=filial, idintegracao=1186)
    return SimpleNamespace(user=user)


def _selected_row(**overrides):
    dados = {
        "codemp": 1,
        "codcre": "10",
        "codpro": "62709",
        "codder": " ",
        "coddep": "01.14",
        "codlot": "L1",
        "numorp": "100",
        "codori": "1",
        "qtdest": "10",
    }
    dados.update(overrides)
    return dados


@override_settings(SAPIENS_USERNAME="usuario_sapiens", SAPIENS_PASSWORD="segredo_super_secreto")
class EnviarLoteParaAreaVermelhaTests(SimpleTestCase):
    @patch("setores.qualidade.views.liberar_lotes.post_soap_sapiens")
    @patch("setores.qualidade.views.liberar_lotes.buscar_recurso_por_codigo", return_value=None)
    def test_sequencia_fecha_cdata_nao_quebra_nem_injeta_xml(self, mock_recurso, mock_post_soap):
        """Achado alto: ']]>' num dado do lote não pode fechar o CDATA antes da hora."""
        mock_post_soap.return_value = (True, "OK")

        views.enviar_lote_para_area_vermelha(
            _request(), _selected_row(codlot="L1]]><forjado>1</forjado>")
        )

        envelope = mock_post_soap.call_args.args[1]
        raiz = ET.fromstring(envelope)
        self.assertIsNone(raiz.find(".//forjado"))
        self.assertIn("forjado", envelope)

    @patch("setores.qualidade.views.liberar_lotes.post_soap_sapiens")
    @patch("setores.qualidade.views.liberar_lotes.buscar_recurso_por_codigo", return_value=None)
    def test_sucesso_repassa_resposta_do_post_soap_sapiens(self, mock_recurso, mock_post_soap):
        mock_post_soap.return_value = (True, "OK")

        sucesso, resposta = views.enviar_lote_para_area_vermelha(_request(), _selected_row())

        self.assertTrue(sucesso)
        self.assertEqual(resposta, "OK")

    @patch("setores.qualidade.views.liberar_lotes.post_soap_sapiens")
    @patch("setores.qualidade.views.liberar_lotes.buscar_recurso_por_codigo", return_value=None)
    def test_codemp_forjado_no_selected_row_e_ignorado(self, mock_recurso, mock_post_soap):
        """Achado de segurança: `selected_row["codemp"]` (POST) tinha prioridade
        sobre a empresa da filial do usuário logado (codemp=1) e ia direto para o
        `codEmp` do MovimentarEstoque no Sapiens — um usuário com permissão de
        destinar lotes conseguia mover estoque de outra empresa no ERP."""
        mock_post_soap.return_value = (True, "OK")

        views.enviar_lote_para_area_vermelha(_request(), _selected_row(codemp=999))

        envelope = mock_post_soap.call_args.args[1]
        raiz = ET.fromstring(envelope)
        # O payload JSON vai dentro do CDATA de <valor>; concatenar as partes de
        # texto (o parser separa em torno do trecho escapado) é suficiente para
        # confirmar que a empresa real (1) foi usada, e não a forjada (999).
        json_dados = "".join(raiz.find(".//valor").itertext())
        self.assertIn('"codEmp": 1', json_dados)
        self.assertNotIn('"codEmp": 999', json_dados)


class ObterParametrosLiberacaoTests(SimpleTestCase):
    """`obter_parametros_liberacao` decide sob qual empresa o registro local de
    liberação (e a pendência ERP/WMS gerada a partir dele) é criado."""

    @patch("setores.qualidade.views.liberar_lotes.buscar_recurso_por_codigo", return_value=None)
    def test_codemp_forjado_no_selected_row_e_ignorado(self, mock_recurso):
        """Achado de segurança: `codemp` vinha de `selected_row.get("codemp") or
        <empresa real>` — a prioridade era do POST, não da empresa do usuário."""
        ok, mensagem, parametros = views.obter_parametros_liberacao(
            _request(), _selected_row(codemp=999)
        )

        self.assertTrue(ok, mensagem)
        self.assertEqual(parametros["codemp"], 1)

    def test_usuario_sem_filial_e_recusado(self):
        request = SimpleNamespace(user=SimpleNamespace(filial=None))

        ok, mensagem, parametros = views.obter_parametros_liberacao(request, _selected_row())

        self.assertFalse(ok)
        self.assertEqual(parametros, {})


class ValidarLotePendenteErpTests(SimpleTestCase):
    """`validar_lote_pendente_erp` consulta a situação do lote direto no Oracle;
    o `codemp` do filtro precisa ser sempre o da empresa real do usuário."""

    def _cursor_mock(self, situacao):
        cursor = MagicMock()
        cursor.description = [("USU_SITLOT",)]
        cursor.fetchone.return_value = (situacao,)
        contexto = MagicMock()
        contexto.__enter__.return_value = cursor
        return contexto, cursor

    @patch("setores.qualidade.views.liberar_lotes.cursor_oracle_erp")
    def test_usa_o_codemp_recebido_explicitamente_no_filtro_oracle(self, mock_cursor_oracle):
        """A função não aceita mais `codemp` vindo de `selected_row` (POST); quem
        chama (a view) já resolveu a empresa real antes de invocá-la. Aqui só
        confirmamos que o valor passado é o que vai para o filtro Oracle."""
        contexto, cursor = self._cursor_mock("P")
        mock_cursor_oracle.return_value = contexto

        ok, motivo = views.validar_lote_pendente_erp(1, _selected_row(codemp=999))

        self.assertTrue(ok, motivo)
        params_usados = cursor.execute.call_args.args[1]
        self.assertEqual(params_usados["codemp"], 1)

    def test_sem_empresa_do_usuario_recusa_sem_consultar_oracle(self):
        ok, motivo = views.validar_lote_pendente_erp(None, _selected_row())

        self.assertFalse(ok)
        self.assertIn("empresa", motivo.lower())
