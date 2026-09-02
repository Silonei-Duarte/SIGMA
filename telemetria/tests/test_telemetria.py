import time
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import CentroRecurso, Departamento, Empresa, Filial, Recurso, Setor
from producao.services.paradas_automaticas import validar_regra_parada
from telemetria.forms import FonteColetaHTTPForm, SensorForm, SensorRecursoForm
from telemetria.models import FonteColetaHTTP, LeituraTelemetria, Sensor, SensorRecurso
from telemetria.services.coleta import (
    CoordenadorColetaTelemetria,
    coletar_fonte,
    obter_status_coleta,
    processar_snapshot_recurso,
)

User = get_user_model()


def criar_recurso(codigo):
    empresa = Empresa.objects.create(codemp=981, nome=f"Empresa {codigo}", fantasia="Empresa")
    filial = Filial.objects.create(
        empresa=empresa, codfil=1, nome="Filial", fantasia="Filial", cnpj="12345678000199"
    )
    departamento = Departamento.objects.create(filial=filial, descricao="Departamento")
    setor = Setor.objects.create(departamento=departamento, descricao="Setor")
    centro = CentroRecurso.objects.create(setor=setor, codigo=f"C{codigo}", descricao="Centro")
    return Recurso.objects.create(centro_recurso=centro, codigo=codigo, descricao="Recurso")


class RespostaHTTP:
    headers: dict[str, str]
    encoding = "utf-8"

    def __init__(self, corpo):
        self.headers = {}
        self.corpo, self.close = corpo, Mock()

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        return iter([self.corpo.encode()])


@override_settings(
    TELEMETRIA_HOSTS_PERMITIDOS=("equipamento.local",),
    TELEMETRIA_TIMEOUT_MAX_SEGUNDOS=30,
    TELEMETRIA_RESPOSTA_MAX_BYTES=1024,
)
class ColetaPorFonteTests(TestCase):
    def setUp(self):
        self.fonte = FonteColetaHTTP.objects.create(url="http://equipamento.local/status")
        self.recurso = criar_recurso("MP-III")
        self.sensor = Sensor.objects.create(
            fonte=self.fonte,
            chave_origem="statusPrensa",
            nome="Prensa",
            tipo_valor=Sensor.TipoValor.BOOLEANO,
        )
        self.vinculo = SensorRecurso.objects.create(
            recurso=self.recurso, sensor=self.sensor, monitorar_variacao=True
        )

    def test_fonte_json_e_requisitada_uma_vez(self):
        cliente = Mock(return_value=RespostaHTTP('{"MP-III": {"statusPrensa": 1}}'))
        self.assertEqual(coletar_fonte(self.fonte, cliente), {"MP-III": {"statusPrensa": 1}})
        cliente.assert_called_once()

    def test_converte_booleano_e_ignora_sensor_ausente(self):
        valores = processar_snapshot_recurso(self.recurso.id, [self.vinculo], {"statusPrensa": "0"})
        self.assertEqual(valores, {"statusPrensa": False})
        self.assertIsNone(processar_snapshot_recurso(self.recurso.id, [self.vinculo], {}))

    def test_primeira_coleta_sem_monitorar_variacao_nao_grava_leitura(self):
        # Vínculo nasce com monitorar_variacao=False (regra atual do form). Sem
        # nenhuma leitura anterior em cache ou banco, a primeira coleta não deve
        # criar baseline nenhuma, porque nunca haverá comparação futura para ela.
        self.vinculo.monitorar_variacao = False
        self.vinculo.save()

        resultado = processar_snapshot_recurso(
            self.recurso.id, [self.vinculo], {"statusPrensa": "1"}
        )

        self.assertIsNone(resultado)
        self.assertEqual(LeituraTelemetria.objects.filter(recurso_id=self.recurso.id).count(), 0)

    def test_primeira_coleta_com_monitorar_variacao_grava_baseline(self):
        # Continua criando a baseline normalmente quando ao menos um vínculo
        # relevante monitora variação — não pode regredir esse caso.
        resultado = processar_snapshot_recurso(
            self.recurso.id, [self.vinculo], {"statusPrensa": "1"}
        )

        self.assertEqual(resultado, {"statusPrensa": True})
        self.assertEqual(LeituraTelemetria.objects.filter(recurso_id=self.recurso.id).count(), 1)

    def test_recurso_nao_aceita_fontes_misturadas(self):
        outra = FonteColetaHTTP.objects.create(url="http://equipamento.local/outra")
        sensor = Sensor.objects.create(
            fonte=outra, chave_origem="outro", nome="Outro", tipo_valor=Sensor.TipoValor.TEXTO
        )
        vinculo = SensorRecurso(recurso=self.recurso, sensor=sensor)
        with self.assertRaisesMessage(Exception, "mesma fonte"):
            vinculo.full_clean()

    def test_formulario_rejeita_chave_repetida_na_mesma_fonte(self):
        form = SensorForm(
            data={
                "fonte": self.fonte.pk,
                "chave_origem": self.sensor.chave_origem,
                "nome": "Outro sensor",
                "tipo_valor": Sensor.TipoValor.TEXTO,
                "unidade": "",
                "ativo": True,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("chave_origem", form.errors)

    def test_formulario_aceita_chave_repetida_em_outra_fonte(self):
        outra_fonte = FonteColetaHTTP.objects.create(url="http://equipamento.local/outra")
        form = SensorForm(
            data={
                "fonte": outra_fonte.pk,
                "chave_origem": self.sensor.chave_origem,
                "nome": "Outro sensor",
                "tipo_valor": Sensor.TipoValor.TEXTO,
                "unidade": "",
                "ativo": True,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().fonte, outra_fonte)

    def test_vinculo_novo_nasce_sem_monitorar_mesmo_enviando_o_campo(self):
        # "Monitorar variação" só existe na tabela de vínculos já criados; o
        # form de vincular sensor novo não deve mais aceitar esse campo, nem
        # mesmo se algo enviar o POST com ele.
        sensor = Sensor.objects.create(
            fonte=self.fonte,
            chave_origem="contagemBobinas",
            nome="Contagem de bobinas",
            tipo_valor=Sensor.TipoValor.INTEIRO,
        )
        self.assertNotIn("monitorar_variacao", SensorRecursoForm.base_fields)

        form = SensorRecursoForm(
            data={"sensor": sensor.pk, "monitorar_variacao": True}, recurso=self.recurso
        )

        self.assertTrue(form.is_valid(), form.errors)
        vinculo = form.save()
        self.assertFalse(vinculo.monitorar_variacao)

    def test_view_vincular_cria_vinculo_sem_monitorar_ainda_que_o_post_envie_o_campo(self):
        # Reproduz o bug relatado: a tela de vincular não tem mais o
        # checkbox, mas alguém poderia forjar o campo no POST. O vínculo
        # criado deve nascer com o default do model (False) do mesmo jeito.
        sensor = Sensor.objects.create(
            fonte=self.fonte,
            chave_origem="temperaturaForno",
            nome="Temperatura do forno",
            tipo_valor=Sensor.TipoValor.DECIMAL,
        )
        usuario_staff = User.objects.create_user(
            username="staff.telemetria", password="Senha@2026", is_staff=True
        )
        self.client.force_login(usuario_staff)

        resposta = self.client.post(
            reverse("telemetria_configurar_recurso", args=[self.recurso.id]),
            {"acao": "vincular", "sensor": sensor.pk, "monitorar_variacao": "on"},
        )

        self.assertRedirects(
            resposta,
            f"/recursos/?editar={self.recurso.id}#tab-telemetria",
            fetch_redirect_response=False,
        )
        vinculo = SensorRecurso.objects.get(recurso=self.recurso, sensor=sensor)
        self.assertFalse(vinculo.monitorar_variacao)

    def test_sensor_desativado_e_ignorado_na_monitoracao_e_na_parada_automatica(self):
        # Sensor desativado permanece vinculado ao recurso (histórico), mas o
        # worker de coleta deve ignorá-lo por completo: nem entra na leitura
        # gravada, nem é passado para a avaliação de parada automática.
        sensor_inativo = Sensor.objects.create(
            fonte=self.fonte,
            chave_origem="sensorInativo",
            nome="Sensor desativado",
            tipo_valor=Sensor.TipoValor.TEXTO,
            ativo=False,
        )
        SensorRecurso.objects.create(
            recurso=self.recurso, sensor=sensor_inativo, monitorar_variacao=True
        )
        coordenador = CoordenadorColetaTelemetria()

        with (
            patch("telemetria.services.coleta.close_old_connections"),
            patch(
                "telemetria.services.coleta.coletar_fonte",
                return_value={"MP-III": {"statusPrensa": "1", "sensorInativo": "qualquer"}},
            ),
            patch(
                "telemetria.services.coleta.avaliar_e_aplicar_parada_automatica",
                return_value=None,
            ) as avaliar_mock,
        ):
            coordenador._coletar(self.fonte)

        leitura = LeituraTelemetria.objects.get(recurso_id=self.recurso.id)
        self.assertEqual(leitura.valores, {"statusPrensa": True})

        avaliar_mock.assert_called_once()
        valores_avaliados = avaliar_mock.call_args.args[1]
        self.assertNotIn("sensorInativo", valores_avaliados)
        self.assertEqual(valores_avaliados, {"statusPrensa": True})

    def test_fonte_sem_sensor_atualiza_status_da_coleta(self):
        fonte = FonteColetaHTTP.objects.create(url="http://equipamento.local/sem-sensor")
        coordenador = CoordenadorColetaTelemetria()

        with (
            patch("telemetria.services.coleta.close_old_connections"),
            patch("telemetria.services.coleta.coletar_fonte", return_value={}),
        ):
            pausa = coordenador._coletar(fonte)

        fonte.refresh_from_db()
        self.assertEqual(pausa, fonte.pausa_sucesso_segundos)
        self.assertEqual(fonte.log, "Coleta concluída.")
        self.assertIsNotNone(fonte.ultima_coleta_em)

    def test_status_lista_fontes_em_vez_de_recursos(self):
        status = obter_status_coleta()

        self.assertIn("fontes", status)
        self.assertNotIn("recursos", status)

    @override_settings(
        TELEMETRIA_PAUSA_SUCESSO_SEGUNDOS=10,
        TELEMETRIA_BACKOFF_ERRO_SEGUNDOS=10,
    )
    def test_nova_fonte_recebe_intervalos_padrao_de_dez_segundos(self):
        form = FonteColetaHTTPForm()
        fonte = FonteColetaHTTP(url="http://equipamento.local/padrao")

        self.assertEqual(form.initial["pausa_sucesso_segundos"], 10)
        self.assertEqual(form.initial["backoff_erro_segundos"], 10)
        self.assertEqual(fonte.pausa_sucesso_segundos, 10)
        self.assertEqual(fonte.backoff_erro_segundos, 10)

    def test_fonte_ativa_fica_elegivel_imediatamente_ao_iniciar_coordenador(self):
        coordenador = CoordenadorColetaTelemetria()

        coordenador.recarregar()

        self.assertIn(self.fonte.id, coordenador.fontes)
        self.assertNotIn(self.fonte.id, coordenador.proximos)

    def test_edicao_da_fonte_reagenda_coleta_imediatamente(self):
        coordenador = CoordenadorColetaTelemetria()
        coordenador.recarregar()
        coordenador.proximos[self.fonte.id] = time.monotonic() + 60

        coordenador.reagendar_fonte(self.fonte.id)
        coordenador.recarregar()

        self.assertLessEqual(coordenador.proximos[self.fonte.id], time.monotonic())


@override_settings(
    TELEMETRIA_HOSTS_PERMITIDOS=("equipamento.local",),
    TELEMETRIA_TIMEOUT_MAX_SEGUNDOS=30,
    TELEMETRIA_RESPOSTA_MAX_BYTES=1024,
)
class AtualizacaoBobinaTelemetriaTests(TestCase):
    # Substitui o importa_numbobinas.py: o número da bobina passa a ser
    # calculado a partir das mesmas tags JSON da fonte de telemetria do
    # recurso, sem depender de Sensor/SensorRecurso cadastrado.
    def test_atualiza_bobina_a_partir_do_snapshot_sem_sensor_cadastrado(self):
        recurso = criar_recurso("MP-IV")
        coordenador = CoordenadorColetaTelemetria()

        coordenador._atualizar_bobinas({"MP-IV": {"contagemBobinas": 150, "estouroDeContagem": 2}})

        recurso.refresh_from_db()
        self.assertEqual(recurso.bobina, 2 * 32000 + 150)

    def test_sensor_ausente_no_bloco_nao_atualiza_bobina(self):
        recurso = criar_recurso("MP-V")
        coordenador = CoordenadorColetaTelemetria()

        coordenador._atualizar_bobinas({"MP-V": {"contagemBobinas": 10}})

        recurso.refresh_from_db()
        self.assertIsNone(recurso.bobina)

    def test_recurso_ausente_no_snapshot_nao_gera_erro(self):
        coordenador = CoordenadorColetaTelemetria()

        coordenador._atualizar_bobinas({"MP-VI": {"contagemBobinas": 1, "estouroDeContagem": 0}})

    def test_segunda_leitura_igual_nao_consulta_nem_grava_de_novo(self):
        recurso = criar_recurso("MP-III")
        recurso.bobina = 2 * 32000 + 150
        recurso.save(update_fields=["bobina"])
        coordenador = CoordenadorColetaTelemetria()
        bloco = {"MP-III": {"contagemBobinas": 150, "estouroDeContagem": 2}}

        coordenador._atualizar_bobinas(bloco)
        with CaptureQueriesContext(connection) as queries:
            coordenador._atualizar_bobinas(bloco)

        self.assertEqual(len(queries), 0)
        recurso.refresh_from_db()
        self.assertEqual(recurso.bobina, 2 * 32000 + 150)

    def test_coletar_fonte_completa_atualiza_bobina_de_recurso_sem_sensor(self):
        fonte = FonteColetaHTTP.objects.create(url="http://equipamento.local/bobina")
        recurso = criar_recurso("MP-IV")
        coordenador = CoordenadorColetaTelemetria()

        with (
            patch("telemetria.services.coleta.close_old_connections"),
            patch(
                "telemetria.services.coleta.coletar_fonte",
                return_value={"MP-IV": {"contagemBobinas": 300, "estouroDeContagem": 1}},
            ),
        ):
            coordenador._coletar(fonte)

        recurso.refresh_from_db()
        self.assertEqual(recurso.bobina, 1 * 32000 + 300)


@override_settings(
    TELEMETRIA_HOSTS_PERMITIDOS=("equipamento.local",),
    TELEMETRIA_TIMEOUT_MAX_SEGUNDOS=30,
    TELEMETRIA_RESPOSTA_MAX_BYTES=1024,
)
class AtualizacaoPesoBalancaTelemetriaTests(TestCase):
    def test_coletar_fonte_sem_sensor_repassa_peso_da_balanca(self):
        fonte = FonteColetaHTTP.objects.create(url="http://equipamento.local/peso")
        recurso = criar_recurso("MP-III")
        coordenador = CoordenadorColetaTelemetria()
        camada_canal = Mock()

        with (
            patch("telemetria.services.coleta.close_old_connections"),
            patch(
                "telemetria.services.coleta.coletar_fonte",
                return_value={"MP-III": {"pesoBalanca": 12.5}},
            ),
            patch("telemetria.services.coleta.get_channel_layer", return_value=camada_canal),
            patch(
                "telemetria.services.coleta.async_to_sync",
                side_effect=lambda func: func,
            ),
        ):
            coordenador._coletar(fonte)

        camada_canal.group_send.assert_called_once_with(
            f"balanca_{recurso.id}", {"type": "balanca_update", "balanca": 12.5}
        )

    def test_atualiza_balanca_por_recurso_sem_sensor_cadastrado(self):
        recurso = criar_recurso("MP-IV")
        coordenador = CoordenadorColetaTelemetria()
        camada_canal = Mock()

        with (
            patch("telemetria.services.coleta.get_channel_layer", return_value=camada_canal),
            patch(
                "telemetria.services.coleta.async_to_sync",
                side_effect=lambda func: func,
            ),
        ):
            coordenador._atualizar_pesos_balanca(None, {"MP-IV": {"pesoBalanca": "12,50"}})

        self.assertEqual(coordenador.ultimos_pesos_balanca, {recurso.id: 12.5})
        camada_canal.group_send.assert_called_once_with(
            f"balanca_{recurso.id}", {"type": "balanca_update", "balanca": 12.5}
        )

    def test_peso_ausente_ou_invalido_repassa_zero_sem_erro(self):
        recurso = criar_recurso("MP-V")
        coordenador = CoordenadorColetaTelemetria()

        with (
            patch("telemetria.services.coleta.get_channel_layer") as camada_canal,
            patch(
                "telemetria.services.coleta.async_to_sync",
                side_effect=lambda func: func,
            ),
        ):
            coordenador._atualizar_pesos_balanca(
                None,
                {
                    "MP-V": {},
                    "MP-VI": {"pesoBalanca": "invalido"},
                    "MP-VII": {"pesoBalanca": "5000,01"},
                },
            )

        self.assertEqual(coordenador.ultimos_pesos_balanca, {recurso.id: 0})
        camada_canal.return_value.group_send.assert_called_once_with(
            f"balanca_{recurso.id}", {"type": "balanca_update", "balanca": 0}
        )

    def test_falha_da_fonte_repassa_zero_so_para_recursos_ja_lidos_nela(self):
        fonte = FonteColetaHTTP.objects.create(url="http://equipamento.local/peso")
        recurso = criar_recurso("MP-VI")
        outra_fonte = FonteColetaHTTP.objects.create(url="http://equipamento.local/outro-peso")
        outro_recurso = Recurso.objects.create(
            centro_recurso=recurso.centro_recurso,
            codigo="MP-VII",
            descricao="Outro recurso",
        )
        coordenador = CoordenadorColetaTelemetria()
        camada_canal = Mock()

        with (
            patch("telemetria.services.coleta.get_channel_layer", return_value=camada_canal),
            patch(
                "telemetria.services.coleta.async_to_sync",
                side_effect=lambda func: func,
            ),
        ):
            coordenador._atualizar_pesos_balanca(fonte.id, {"MP-VI": {"pesoBalanca": 12}})
            coordenador._atualizar_pesos_balanca(outra_fonte.id, {"MP-VII": {"pesoBalanca": 30}})
            camada_canal.group_send.reset_mock()
            with (
                patch("telemetria.services.coleta.close_old_connections"),
                patch(
                    "telemetria.services.coleta.coletar_fonte",
                    side_effect=Exception("fonte indisponível"),
                ),
                patch("telemetria.services.coleta.logger.exception"),
            ):
                pausa = coordenador._coletar(fonte)

        self.assertEqual(pausa, fonte.backoff_erro_segundos)
        self.assertEqual(coordenador.ultimos_pesos_balanca[recurso.id], 0)
        self.assertEqual(coordenador.ultimos_pesos_balanca[outro_recurso.id], 30)
        camada_canal.group_send.assert_called_once_with(
            f"balanca_{recurso.id}", {"type": "balanca_update", "balanca": 0}
        )


class ValidarRegraParadaTests(TestCase):
    # A regra referencia o sensor pela chave_origem (mesma chave do snapshot
    # de coleta); antes da correção o dicionário de vínculos era montado com
    # um atributo `codigo` que não existe mais no modelo Sensor.
    def setUp(self):
        self.fonte = FonteColetaHTTP.objects.create(url="http://equipamento.local/status")
        self.recurso = criar_recurso("MP-VIII")
        self.sensor = Sensor.objects.create(
            fonte=self.fonte,
            chave_origem="statusPrensa",
            nome="Prensa",
            tipo_valor=Sensor.TipoValor.BOOLEANO,
        )
        SensorRecurso.objects.create(recurso=self.recurso, sensor=self.sensor)

    def test_regra_com_chave_origem_do_sensor_vinculado_valida(self):
        regra = {
            "tipo": "grupo",
            "operador": "E",
            "itens": [
                {"tipo": "condicao", "sensor": "statusPrensa", "comparacao": "igual", "valor": 1}
            ],
        }
        validar_regra_parada(regra, self.recurso)

    def test_regra_com_sensor_desconhecido_e_rejeitada(self):
        regra = {"tipo": "condicao", "sensor": "inexistente", "comparacao": "igual", "valor": 1}
        with self.assertRaisesMessage(ValidationError, "inexistente"):
            validar_regra_parada(regra, self.recurso)
