"""Teste de setores/qualidade/views/liberar_area_vermelha.py.

Achado de segurança: as ações "excluir_destinacao_lote" e
"registrar_liberacao_lote" da Reunião de Área Vermelha usavam o `codemp`
recebido cru no POST sem nenhuma comparação com a empresa do usuário
autenticado — mesma classe de vulnerabilidade já fechada em `producao`
(ver `producao/tests/test_altera_apontamento.py::
test_codemp_forjado_em_erp_params_e_ignorado`): um usuário com permissão de
destinar lotes na área vermelha conseguia agir (excluir destinação, registrar
avaliação e gerar pendência ERP/WMS) em nome de uma empresa que não era a sua
só forjando o campo `codemp` do formulário.

Os testes usam o client de teste completo (a view decide tudo a partir de
POST) porque as duas ações vivem dentro do corpo de `liberar_area_vermelha`,
sem função própria para chamar isoladamente. `resolver_local_wms_area_vermelha`
é mockado em `registrar_liberacao_lote` para não bater no DBLINK Oracle real
do WMS — o resto do fluxo (validação, gravação local, pendência WMS) roda de
verdade contra o banco de teste.
"""

import re
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.template.loader import render_to_string
from django.test import TestCase
from django.test.client import RequestFactory
from django.urls import reverse
from django.utils import timezone

from accounts.models import Empresa, Filial, ParametrosFilial
from setores.qualidade.models import (
    LiberacaoLote,
    ObservacaoEtiqueta,
    Reuniao,
    WMS_IntegraçãoOP,
)


def _criar_empresa_filial(codemp, codfil=1, **parametros_extra):
    empresa = Empresa.objects.create(codemp=codemp, nome=f"Empresa {codemp}", fantasia=f"E{codemp}")
    filial = Filial.objects.create(
        empresa=empresa,
        codfil=codfil,
        nome=f"Filial {codemp}",
        fantasia=f"F{codemp}",
        cnpj="22.222.222/0001-22",
    )
    ParametrosFilial.objects.create(filial=filial, **parametros_extra)
    return empresa, filial


def _usuario(filial, *codenames_qualidade, is_staff=False):
    usuario = get_user_model().objects.create_user(
        username=f"user_{filial.empresa.codemp if filial else 'staff'}_{is_staff}",
        password="x",
        filial=filial,
        is_staff=is_staff,
    )
    if codenames_qualidade:
        permissoes = Permission.objects.filter(
            content_type__app_label="qualidade", codename__in=codenames_qualidade
        )
        usuario.user_permissions.add(*permissoes)
    return usuario


class ExcluirDestinacaoLoteTests(TestCase):
    """Achado de segurança na ação `excluir_destinacao_lote`."""

    def setUp(self):
        self.empresa_a, self.filial_a = _criar_empresa_filial(101)
        self.empresa_b, self.filial_b = _criar_empresa_filial(102)
        self.reuniao = Reuniao.objects.create(data_hora_inicio=timezone.now())

    def _criar_liberacao(self, empresa, usuario):
        return LiberacaoLote.objects.create(
            codemp=empresa.codemp,
            codpro="P1",
            codder="D1",
            coddep="01",
            codigo_integrador="10",
            codlot="L1",
            qtdtot=10,
            usuario=usuario,
            reuniao=self.reuniao,
            status=LiberacaoLote.Status.NAO_INTEGRADO,
        )

    def _post_excluir(self, usuario, codemp_forjado):
        self.client.force_login(usuario)
        return self.client.post(
            reverse("qualidade:area_vermelha"),
            {
                "reuniao_action": "excluir_destinacao_lote",
                "codemp": codemp_forjado,
                "codlot": "L1",
                "codpro": "P1",
                "codder": "D1",
            },
        )

    def test_nao_staff_nao_exclui_destinacao_de_outra_empresa_com_codemp_forjado(self):
        usuario_a = _usuario(
            self.filial_a, "pode_acessar_area_vermelha", "pode_destinar_area_vermelha"
        )
        registro = self._criar_liberacao(self.empresa_b, usuario_a)

        self._post_excluir(usuario_a, codemp_forjado=self.empresa_b.codemp)

        self.assertTrue(LiberacaoLote.objects.filter(pk=registro.pk).exists())

    def test_staff_pode_excluir_destinacao_de_qualquer_empresa(self):
        """Regra de negócio confirmada: staff continua sem restrição de filial."""
        usuario_staff = _usuario(self.filial_a, is_staff=True)
        registro = self._criar_liberacao(self.empresa_b, usuario_staff)

        self._post_excluir(usuario_staff, codemp_forjado=self.empresa_b.codemp)

        self.assertFalse(LiberacaoLote.objects.filter(pk=registro.pk).exists())


class RegistrarLiberacaoLoteTests(TestCase):
    """Achado de segurança na ação `registrar_liberacao_lote`."""

    def setUp(self):
        self.empresa_a, self.filial_a = _criar_empresa_filial(
            201, origens_area_vermelha="OF", codtns_area_vermelha="9999"
        )
        self.empresa_b, self.filial_b = _criar_empresa_filial(202)
        self.reuniao = Reuniao.objects.create(data_hora_inicio=timezone.now())
        self.etiqueta = ObservacaoEtiqueta.objects.create(descricao="Sem avaria", ativo=True)

    def _dados_post(self, codemp_forjado):
        return {
            "reuniao_action": "registrar_liberacao_lote",
            "qtdtot": "10",
            "codemp": codemp_forjado,
            "numbob": "",
            "codigo_integrador": "",
            "codori": "1",
            "origem_produto": "OF",
            "numorp": "",
            "codlot": "L1",
            "codpro": "P1",
            "codder": "D1",
            "coddep": "01",
            "destino": ["liberar"],
            "quantidade": ["10"],
            "coddft": ["001"],
            "id_etiqueta": [str(self.etiqueta.id)],
            "observacao_geral": [""],
        }

    @patch(
        "setores.qualidade.views.liberar_area_vermelha.resolver_local_wms_area_vermelha",
        return_value=("A1", "padrao"),
    )
    @patch(
        "setores.qualidade.views.liberar_area_vermelha._validar_saldo_lote_erp",
        return_value=(True, ""),
    )
    def test_nao_staff_nao_registra_avaliacao_em_nome_de_outra_empresa(
        self, mock_saldo, mock_local_wms
    ):
        usuario_a = _usuario(
            self.filial_a, "pode_acessar_area_vermelha", "pode_destinar_area_vermelha"
        )
        self.client.force_login(usuario_a)

        self.client.post(
            reverse("qualidade:area_vermelha"), self._dados_post(self.empresa_b.codemp)
        )

        self.assertFalse(
            LiberacaoLote.objects.filter(
                codemp=self.empresa_b.codemp, reuniao=self.reuniao
            ).exists()
        )
        mock_local_wms.assert_not_called()

    @patch(
        "setores.qualidade.views.liberar_area_vermelha.resolver_local_wms_area_vermelha",
        return_value=("A1", "padrao"),
    )
    @patch(
        "setores.qualidade.views.liberar_area_vermelha._validar_saldo_lote_erp",
        return_value=(True, ""),
    )
    def test_staff_pode_registrar_avaliacao_em_nome_de_qualquer_empresa(
        self, mock_saldo, mock_local_wms
    ):
        """Regra de negócio confirmada: staff continua sem restrição de filial."""
        usuario_staff = _usuario(self.filial_a, is_staff=True)
        self.client.force_login(usuario_staff)

        self.client.post(
            reverse("qualidade:area_vermelha"), self._dados_post(self.empresa_b.codemp)
        )

        self.assertTrue(
            LiberacaoLote.objects.filter(
                codemp=self.empresa_b.codemp, reuniao=self.reuniao
            ).exists()
        )

    @patch(
        "setores.qualidade.views.liberar_area_vermelha.resolver_local_wms_area_vermelha",
        return_value=("A1", "padrao"),
    )
    @patch(
        "setores.qualidade.views.liberar_area_vermelha._validar_saldo_lote_erp",
        return_value=(False, "Saldo insuficiente no ERP para destinar 10 KG do lote L1."),
    )
    def test_saldo_insuficiente_no_erp_bloqueia_registro(self, mock_saldo, mock_local_wms):
        """Achado de segurança: quantidade destinada não era conferida contra o saldo real do ERP."""
        usuario_a = _usuario(
            self.filial_a, "pode_acessar_area_vermelha", "pode_destinar_area_vermelha"
        )
        self.client.force_login(usuario_a)

        self.client.post(
            reverse("qualidade:area_vermelha"), self._dados_post(self.empresa_a.codemp)
        )

        self.assertFalse(
            LiberacaoLote.objects.filter(
                codemp=self.empresa_a.codemp, reuniao=self.reuniao
            ).exists()
        )
        mock_local_wms.assert_not_called()

    @patch(
        "setores.qualidade.views.liberar_area_vermelha.cursor_oracle_erp",
        side_effect=RuntimeError("Oracle indisponível no teste"),
    )
    def test_quantidade_destinada_maior_que_o_saldo_real_e_recusada(self, mock_cursor_oracle):
        """Conferência real contra o ERP: sem saldo no banco de teste, qualquer quantidade é recusada."""
        usuario_a = _usuario(
            self.filial_a, "pode_acessar_area_vermelha", "pode_destinar_area_vermelha"
        )
        self.client.force_login(usuario_a)

        self.client.post(
            reverse("qualidade:area_vermelha"), self._dados_post(self.empresa_a.codemp)
        )

        self.assertFalse(
            LiberacaoLote.objects.filter(
                codemp=self.empresa_a.codemp, reuniao=self.reuniao
            ).exists()
        )

    @patch(
        "setores.qualidade.views.liberar_area_vermelha.resolver_local_wms_area_vermelha",
        return_value=("A1", "padrao"),
    )
    @patch(
        "setores.qualidade.views.liberar_area_vermelha._validar_saldo_lote_erp",
        return_value=(True, ""),
    )
    def test_destino_para_prensa_grava_status_local_e_nao_integra(self, mock_saldo, mock_local_wms):
        """`para_prensa` é o único destino que grava LOCAL — registro só de log
        local, sem pendência WMS. O valor mudou de 3 para 4 (o 3 ficou
        reservado ao esquema numérico comum das filas de integração); o teste
        trava a renumeração."""
        ParametrosFilial.objects.filter(filial=self.filial_a).update(produto_refugo="PR1")
        usuario_a = _usuario(
            self.filial_a, "pode_acessar_area_vermelha", "pode_destinar_area_vermelha"
        )
        self.client.force_login(usuario_a)

        dados = self._dados_post(self.empresa_a.codemp)
        dados["destino"] = ["para_prensa"]
        self.client.post(reverse("qualidade:area_vermelha"), dados)

        registro = LiberacaoLote.objects.get(codemp=self.empresa_a.codemp, reuniao=self.reuniao)
        self.assertEqual(registro.status, LiberacaoLote.Status.LOCAL)
        self.assertEqual(registro.status, 4)
        self.assertEqual(registro.qtdprensa, 10.0)
        self.assertFalse(WMS_IntegraçãoOP.objects.exists())


class AreaVermelhaTemplateTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="tester_template_area_vermelha", password="x", is_staff=True
        )

    def test_totais_e_linhas_filhas_so_destacam_numeros_positivos(self):
        registro = SimpleNamespace(
            numbob=None,
            lottrf="L1",
            codlot="L1",
            local_wms="A1",
            codpro="P1",
            codder="D1",
            coddep="01",
            codigo_integrador="1",
            qtdtot=10,
            qtdlibe=1,
            qtdrefu=0,
            qtdrecl=2,
            qtdprensa=0,
            codpro_recl="",
            codder_recl="",
            coddft="",
            etiqueta=SimpleNamespace(descricao=""),
            observacao_geral="",
            usuario=self.usuario,
        )
        grupo = SimpleNamespace(
            numbob=None,
            codlot="L1",
            local="A1",
            codpro="P1",
            codder="D1",
            coddep="01",
            codigo_integrador="1",
            qtdtot=10,
            total_libe=1,
            total_refu=0,
            total_recl=2,
            total_prensa=0,
            registros=[registro],
            pode_excluir=False,
            usuario=self.usuario,
        )
        request = RequestFactory().get(reverse("qualidade:area_vermelha"))
        request.user = self.usuario

        conteudo = render_to_string(
            "setores/qualidade/liberar_area_vermelha.html",
            {
                "grupos_liberacoes": [grupo],
                "reuniao_aberta": True,
                "pode_destinar_area_vermelha": False,
                "bobinas": [],
                "motivos_area_vermelha": [],
                "observacoes_etiqueta": [],
                "setores_participante": [],
            },
            request=request,
        )
        linha_pai = re.search(r'<tr class="cursor-pointer[^>]*>(.*?)</tr>', conteudo, re.DOTALL)
        linha_filha = re.search(
            r'<tr class="grupo-destino-1 hidden[^>]*>(.*?)</tr>', conteudo, re.DOTALL
        )

        self.assertIsNotNone(linha_pai)
        self.assertIsNotNone(linha_filha)
        self.assertEqual(
            re.findall(r'<td class="([^"]*)">([012],0000)</td>', linha_pai.group(1)),
            [
                (
                    "border border-borda-sutil bg-sucesso-sutil text-sucesso-base font-bold p-2",
                    "1,0000",
                ),
                ("border border-borda-sutil p-2", "0,0000"),
                (
                    "border border-borda-sutil bg-atencao-sutil text-atencao-base font-bold p-2",
                    "2,0000",
                ),
                ("border border-borda-sutil p-2", "0,0000"),
            ],
        )
        self.assertEqual(
            re.findall(r'<td class="([^"]*)">([012],0000)</td>', linha_filha.group(1)),
            [
                (
                    "border border-borda-sutil bg-sucesso-sutil text-sucesso-base font-bold p-2",
                    "1,0000",
                ),
                ("border border-borda-sutil bg-superficie-afundada p-2", "0,0000"),
                (
                    "border border-borda-sutil bg-atencao-sutil text-atencao-base font-bold p-2",
                    "2,0000",
                ),
                ("border border-borda-sutil bg-superficie-afundada p-2", "0,0000"),
            ],
        )


class AreaVermelhaBuscaTests(TestCase):
    def setUp(self):
        _, filial = _criar_empresa_filial(
            301,
            deposito_area_vermelha_erp="01.99",
            origens_area_vermelha="OF",
        )
        self.usuario = _usuario(filial, "pode_acessar_area_vermelha")

    @patch("setores.qualidade.views.liberar_area_vermelha.carregar_motivos_area_vermelha")
    @patch("setores.qualidade.views.liberar_area_vermelha.cursor_oracle_erp")
    def test_busca_por_descricao_do_recurso(self, mock_cursor_oracle, mock_motivos):
        mock_motivos.return_value = []
        cursor = mock_cursor_oracle.return_value.__enter__.return_value
        cursor.fetchall.return_value = []
        self.client.force_login(self.usuario)

        resposta = self.client.get(reverse("qualidade:area_vermelha"), {"search": "Prensa"})

        self.assertEqual(resposta.status_code, 200)
        sql, parametros = cursor.execute.call_args.args
        self.assertIn("UPPER(CRE.DESCRE) LIKE :search_text", sql)
        self.assertEqual(parametros["search_text"], "%PRENSA%")
        self.assertContains(resposta, "Recurso ou descrição")


class BuscarUsuariosErpTests(TestCase):
    """Achado baixo de segurança: a busca expunha o quadro inteiro de usuários
    do ERP, de todas as empresas. Decisão do sênior: filtrar por filial — o
    não-staff só recebe usuários da própria empresa; staff mantém a visão
    completa (mesma regra de filial usada nas demais views da app)."""

    def setUp(self):
        self.empresa_a, self.filial_a = _criar_empresa_filial(401)
        self.empresa_b, self.filial_b = _criar_empresa_filial(402)

    @patch("setores.qualidade.views.liberar_area_vermelha.cursor_oracle_erp")
    def test_nao_staff_filtra_por_numemp_da_propria_empresa(self, mock_cursor_oracle):
        cursor = mock_cursor_oracle.return_value.__enter__.return_value
        cursor.description = [["codusu", "NUMBER"], ["nomusu", "VARCHAR2"]]
        cursor.fetchall.return_value = [(1, "Usuario A")]

        usuario_a = _usuario(
            self.filial_a, "pode_acessar_area_vermelha", "pode_destinar_area_vermelha"
        )
        self.client.force_login(usuario_a)

        resposta = self.client.get(reverse("qualidade:buscar_usuarios_erp"), {"q": "usu"})

        self.assertEqual(resposta.status_code, 200)
        params = cursor.execute.call_args.args[1]
        self.assertEqual(params["codemp"], str(self.empresa_a.codemp))

    @patch("setores.qualidade.views.liberar_area_vermelha.cursor_oracle_erp")
    def test_staff_nao_restringe_por_numemp(self, mock_cursor_oracle):
        cursor = mock_cursor_oracle.return_value.__enter__.return_value
        cursor.description = [["codusu", "NUMBER"], ["nomusu", "VARCHAR2"]]
        cursor.fetchall.return_value = [(2, "Usuario B")]

        usuario_staff = _usuario(self.filial_a, is_staff=True)
        self.client.force_login(usuario_staff)

        resposta = self.client.get(reverse("qualidade:buscar_usuarios_erp"), {"q": "usu"})

        self.assertEqual(resposta.status_code, 200)
        sql = cursor.execute.call_args.args[0]
        self.assertNotIn("numemp", sql)


class ConsultaErpFalhaTests(TestCase):
    def setUp(self):
        self.empresa, self.filial = _criar_empresa_filial(501)
        self.usuario = _usuario(
            self.filial, "pode_acessar_area_vermelha", "pode_destinar_area_vermelha"
        )
        self.client.force_login(self.usuario)

    @patch("setores.qualidade.views.liberar_area_vermelha.cursor_oracle_erp")
    def test_busca_de_descricao_nao_expoe_erro_oracle(self, mock_cursor_oracle):
        cursor = mock_cursor_oracle.return_value.__enter__
        cursor.side_effect = RuntimeError("DSN interno")

        resposta = self.client.get(
            reverse("qualidade:buscar_descricao_transformacao"), {"produto": "P1"}
        )

        self.assertEqual(resposta.status_code, 500)
        self.assertEqual(resposta.json()["error"], "Não foi possível concluir a consulta.")
        self.assertNotIn("DSN interno", resposta.content.decode())

    @patch("setores.qualidade.views.liberar_area_vermelha.cursor_oracle_erp")
    def test_busca_de_usuarios_nao_expoe_erro_oracle(self, mock_cursor_oracle):
        cursor = mock_cursor_oracle.return_value.__enter__
        cursor.side_effect = RuntimeError("DSN interno")

        resposta = self.client.get(reverse("qualidade:buscar_usuarios_erp"), {"q": "usu"})

        self.assertEqual(resposta.status_code, 500)
        self.assertEqual(resposta.json()["error"], "Não foi possível concluir a consulta.")
        self.assertNotIn("DSN interno", resposta.content.decode())
