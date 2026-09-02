"""Testes do relatório de falhas das filas por e-mail
(producao/services/relatorio_falhas_email.py).

Cobrem os critérios de aceite do relatório de falhas: (a) envia quando há
pendência envelhecida; (b) silencia sem pendência; (c) não vaza
segredo/credencial na mensagem (máscara única de segredos);
(d) diz "não foi possível apurar" quando o agendador está mudo; além do
corte honesto por teto e da cadência por horários configurados em banco:
estado persistido (retry do mesmo horário, não-reenvio de horário
cumprido, reinício seguro), configuração alterada valendo sem reinício e
defaults da chave sem linha no banco.
"""

from contextlib import contextmanager
from datetime import time as dt_time
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import (
    CentroRecurso,
    ConfiguracaoAplicacao,
    CustomUser,
    Departamento,
    Empresa,
    Filial,
    Recurso,
    Setor,
)
from accounts.services import configuracoes as configuracoes_svc
from accounts.services.configuracoes import definir
from producao.models import (
    Apontamento,
    ApontamentoComponente,
    BaixaComponente,
    EstadoRelatorioFalhas,
    LogTrocaOPAtiva,
    PacoteTempoERP,
)
from producao.services import envia_pendencias as scheduler_mod
from producao.services import relatorio_falhas_email as svc
from producao.services import status
from producao.services.envia_pendencias import (
    SERVICES_MONITORADOS_TIMEOUT,
    EnviaPendenciasScheduler,
)
from setores.qualidade.models import LiberacaoLote
from setores.qualidade.models.estrutura import WMS_IntegraçãoOP
from telemetria.models import FonteColetaHTTP
from telemetria.services.coleta import LOG_COLETA_SUCESSO

# Valor de exemplo (domínio reservado para documentação); nenhum e-mail real.
DESTINATARIOS = "operacao@dominio.com"
DESTINATARIOS_VARIOS = "operacao@dominio.com\nsupervisor@dominio.com"
LISTA_DESTINATARIOS_VARIOS = ["operacao@dominio.com", "supervisor@dominio.com"]

CHAVE_HORARIOS = svc.CHAVE_HORARIOS
CHAVE_DESTINATARIOS = svc.CHAVE_DESTINATARIOS
CHAVE_LIMIAR = svc.CHAVE_LIMIAR


def _configurar(
    horarios: str | None = "00:00",
    destinatarios: str | None = DESTINATARIOS,
    limiar: str | None = "5",
):
    """Configuração pelo contrato de escrita (definir), como a tela faz.

    Parâmetro None deixa a chave sem linha no banco: a chave conhecida
    responde o padrão declarado (horários 07:00,16:00; destinatários
    ti@empresa.com.br; limiar 5).
    """
    if horarios is not None:
        definir(CHAVE_HORARIOS, horarios, None)
    if destinatarios is not None:
        definir(CHAVE_DESTINATARIOS, destinatarios, None)
    if limiar is not None:
        definir(CHAVE_LIMIAR, limiar, None)


def _registrar_agendador_fresco():
    """Registry com ciclo do agendador concluído agora (dado fresco)."""
    status.registrar_service(
        "envia_pendencias", "Envio automático de pendências", intervalo_segundos=300
    )
    status.marcar_ciclo_fim("envia_pendencias", 1.0, 300)


@contextmanager
def _congelar_agora(quando):
    """Congela timezone.now() durante o ciclo do worker.

    A cadência por horários compara `horario <= agora` e o estado persistido
    contra "hoje": congelar o relógio torna os horários determinísticos sem
    depender da hora em que a suíte roda. O registry do agendador é
    (re)registrado dentro do congelamento para a guarda de frescor passar.
    """
    with patch.object(svc.timezone, "now", return_value=quando):
        yield


def _hoje(hora, minuto):
    """Datetime aware no fuso local, hoje, no horário dado."""
    return timezone.localtime().replace(hour=hora, minute=minuto, second=0, microsecond=0)


class RelatorioFalhasEmailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        empresa = Empresa.objects.create(codemp=91, nome="Empresa Falhas", fantasia="EF")
        filial = Filial.objects.create(
            empresa=empresa,
            codfil=1,
            nome="Filial Falhas",
            fantasia="FF",
            cnpj="91.222.222/0001-91",
        )
        departamento = Departamento.objects.create(filial=filial, descricao="Depto Falhas")
        setor = Setor.objects.create(departamento=departamento, descricao="Setor Falhas")
        centro = CentroRecurso.objects.create(
            setor=setor,
            codigo="CR-FAIL",
            descricao="Centro Falhas",
            codigo_integrador="CR-FAIL",
        )
        cls.recurso = Recurso.objects.create(
            codigo="R-FAIL", descricao="Recurso Falhas", centro_recurso=centro
        )
        cls.usuario = CustomUser.objects.create_user("operador_fila")

    def setUp(self):
        # Registry do painel e cache de configuração são estado em memória
        # do processo; limpar simula um processo novo a cada teste.
        self.addCleanup(status._SERVICES.clear)
        status._SERVICES.clear()
        self.addCleanup(configuracoes_svc.limpar_cache)
        configuracoes_svc.limpar_cache()
        _registrar_agendador_fresco()

    def _criar_pendencias_de_todas_as_filas(self, datger):
        troca = LogTrocaOPAtiva.objects.create(
            recurso=self.recurso,
            origem="1",
            op=100,
            estagio=1,
            seqrot=1,
            horario_troca=datger - timedelta(hours=8),
        )
        PacoteTempoERP.objects.create(
            troca_op_ativa=troca,
            corte_inicio_real=datger - timedelta(hours=4),
            corte_fim_real=datger,
            datger=datger,
            log="Falha de envio do pacote.",
        )
        Apontamento.objects.create(
            codemp=91,
            origem="1",
            numorp=100123,
            codetg=100,
            seqrot=1,
            numcad=10,
            qtdre1="10",
            datger=datger,
            log="Falha no webservice.",
        )
        ApontamentoComponente.objects.create(
            codemp=91,
            origem="1",
            numorp=100123,
            codetg=100,
            seqrot=1,
            numcad=10,
            lote="L123",
            datger=datger,
            log="Falha no webservice.",
        )
        BaixaComponente.objects.create(
            recurso=self.recurso,
            codemp=91,
            origem="1",
            numorp=100123,
            codetg=100,
            seqrot=1,
            codcmp="CMP1",
            qtduti="2",
            codlot="L456",
            datger=datger,
            data_hora=datger,
            log="Falha no webservice.",
        )
        WMS_IntegraçãoOP.objects.create(
            codemp=91,
            origem="1",
            op=100123,
            quantidade="10",
            codigo_integrador="INT1",
            datger=datger,
            log="Falha WMS.",
        )
        LiberacaoLote.objects.create(
            codemp=91,
            codpro="PROD1",
            codder="DER",
            coddep="01",
            codigo_integrador="INT2",
            codlot="L789",
            numbob=42,
            qtdtot="10",
            usuario=self.usuario,
            datger=datger,
            log="Falha no webservice.",
        )

    def _criar_fonte_telemetria_em_falha(self, ultima_tentativa):
        FonteColetaHTTP.objects.create(
            url="http://192.0.2.99/coleta",
            coleta_ativa=True,
            log="Falha na coleta de telemetria.",
            ultima_coleta_em=ultima_tentativa,
        )

    def _executar(self):
        svc.RelatorioFalhasEmailWorker.executar()

    def test_envia_quando_ha_pendencia_envelhecida(self):
        # Horário 00:00: já vencido em qualquer hora do dia em que a suíte rode.
        _configurar(horarios="00:00")
        self._criar_pendencias_de_todas_as_filas(timezone.now() - timedelta(minutes=10))
        self._criar_fonte_telemetria_em_falha(timezone.now() - timedelta(minutes=10))

        with patch.object(svc, "send_mail") as mock_send:
            self._executar()

        self.assertEqual(mock_send.call_count, 1)
        _, kwargs = mock_send.call_args
        self.assertEqual(kwargs["recipient_list"], ["operacao@dominio.com"])
        self.assertIn("Relatório diário de falhas", kwargs["subject"])
        corpo = kwargs["message"]
        # Filas com pendência envelhecida aparecem com contagem e exemplos.
        self.assertIn("Fila Log Apontamentos: 1 pendência(s) envelhecida(s).", corpo)
        self.assertIn("OP 100123 (estágio 100)", corpo)
        self.assertIn("pendente há ", corpo)
        # A fonte de telemetria ativa em falha também entra.
        self.assertIn("Fontes de telemetria ativas em falha", corpo)
        # Estado persistido: o horário ficou marcado como cumprido.
        estado = EstadoRelatorioFalhas.objects.get(pk=1)
        self.assertIsNotNone(estado.ultimo_envio_em)

    def test_silencia_sem_pendencia(self):
        _configurar(horarios="00:00")

        with patch.object(svc, "send_mail") as mock_send:
            self._executar()

        mock_send.assert_not_called()
        # Sem envio não há marca de horário cumprido.
        self.assertFalse(EstadoRelatorioFalhas.objects.exists())

    def test_pendencia_fresca_nao_e_relatada(self):
        # O gatilho é a pendência envelhecida: registro recém-gerado não conta.
        _configurar(horarios="00:00")
        self._criar_pendencias_de_todas_as_filas(timezone.now())

        with patch.object(svc, "send_mail") as mock_send:
            self._executar()

        mock_send.assert_not_called()

    @override_settings(SAPIENS_PASSWORD="senha_sapiens_123", SECRET_KEY="chave-django-teste")
    def test_texto_de_erro_nao_vaza_segredo_na_mensagem(self):
        _configurar(horarios="00:00")
        agora = timezone.now()
        Apontamento.objects.create(
            codemp=91,
            origem="1",
            numorp=100123,
            codetg=100,
            seqrot=1,
            numcad=10,
            qtdre1="10",
            datger=agora - timedelta(minutes=10),
            log=(
                "Falha ao enviar. senha_sapiens_123 chave-django-teste "
                "url http://coletor:segredo_na_url@192.0.2.99/coleta "
                "<user>usuario_sapiens</user><password>senha_sapiens_123</password>"
            ),
        )

        with patch.object(svc, "send_mail") as mock_send:
            self._executar()

        corpo = mock_send.call_args.kwargs["message"]
        self.assertNotIn("senha_sapiens_123", corpo)
        self.assertNotIn("chave-django-teste", corpo)
        self.assertNotIn("segredo_na_url", corpo)
        self.assertNotIn("usuario_sapiens", corpo)
        # A máscara substituiu de fato, não só omitiu o trecho.
        self.assertIn("<password>***</password>", corpo)
        self.assertIn("<user>***</user>", corpo)

    def test_diz_nao_foi_possivel_apurar_quando_agendador_mudo(self):
        _configurar(horarios="00:00")
        self._criar_pendencias_de_todas_as_filas(timezone.now() - timedelta(minutes=10))
        # Registry sem nenhum ciclo do agendador (processo recém-iniciado).
        status._SERVICES.clear()

        with patch.object(svc, "send_mail") as mock_send:
            self._executar()

        corpo = mock_send.call_args.kwargs["message"]
        self.assertIn("NÃO FOI POSSÍVEL APURAR", corpo)
        # Dado não apurado não vira relato: nenhuma pendência é listada.
        self.assertNotIn("OP 100123", corpo)
        self.assertNotIn("Fila Log Apontamentos", corpo)
        # Envio de "não foi possível apurar" também cumpre o horário.
        estado = EstadoRelatorioFalhas.objects.get(pk=1)
        self.assertIsNotNone(estado.ultimo_envio_em)

    def test_agendador_com_ciclo_antigo_tambem_nao_apura(self):
        _configurar(horarios="00:00")
        self._criar_pendencias_de_todas_as_filas(timezone.now() - timedelta(minutes=10))
        # Último ciclo concluído há 20 min; tolerância = 2 ciclos x 300s = 10 min.
        status._SERVICES["envia_pendencias"]["ultimo_ciclo_fim"] = timezone.now() - timedelta(
            minutes=20
        )

        with patch.object(svc, "send_mail") as mock_send:
            self._executar()

        corpo = mock_send.call_args.kwargs["message"]
        self.assertIn("NÃO FOI POSSÍVEL APURAR", corpo)

    def test_registrado_no_agendador_e_monitorado_por_timeout(self):
        self.assertIn(svc.SERVICE_CODIGO, SERVICES_MONITORADOS_TIMEOUT)
        svc.RelatorioFalhasEmailWorker.registrar()
        registrado = status._SERVICES[svc.SERVICE_CODIGO]
        # Executar() roda a cada ciclo do agendador (300s); a cadência
        # efetiva é a dos horários configurados, descrita no painel.
        self.assertEqual(registrado["intervalo_segundos"], 300)
        self.assertEqual(registrado["tempo_limite_ciclo_segundos"], 60)
        self.assertIn("RELATORIO_FALHAS_HORARIOS", registrado["descricao"])

    def test_corte_honesto_quando_ha_muitos_registros(self):
        _configurar(horarios="00:00")
        agora = timezone.now()
        for ordem in range(7):
            Apontamento.objects.create(
                codemp=91,
                origem="1",
                numorp=200000 + ordem,
                codetg=100,
                seqrot=1,
                numcad=10,
                qtdre1="1",
                datger=agora - timedelta(minutes=10 + ordem),
                log="Falha no webservice.",
            )

        with patch.object(svc, "send_mail") as mock_send:
            self._executar()

        corpo = mock_send.call_args.kwargs["message"]
        self.assertIn("Fila Log Apontamentos: 7 pendência(s) envelhecida(s).", corpo)
        self.assertIn("e mais 2 registro(s)…", corpo)
        self.assertEqual(corpo.count("id "), 5)

    def test_nao_reenvia_horario_ja_cumprido(self):
        _configurar(horarios="00:00")
        self._criar_pendencias_de_todas_as_filas(timezone.now() - timedelta(minutes=10))

        with patch.object(svc, "send_mail") as mock_send:
            self._executar()
            self._executar()

        self.assertEqual(mock_send.call_count, 1)
        estado = EstadoRelatorioFalhas.objects.get(pk=1)
        self.assertIsNotNone(estado.ultimo_envio_em)

    def test_horario_ja_cumprido_proximo_horario_configurado_dispara(self):
        # Horários 07:00 e 16:00; 07:00 já cumpriu (envio 07:01) e agora é
        # 16:02: o 16:00 está vencido e por cumprir, então dispara; o ciclo
        # seguinte não reenvia.
        _configurar(horarios="07:00,16:00")
        EstadoRelatorioFalhas.objects.create(pk=1, ultimo_envio_em=_hoje(7, 1))
        agora = _hoje(16, 2)
        self._criar_pendencias_de_todas_as_filas(agora - timedelta(minutes=10))

        with _congelar_agora(agora):
            status._SERVICES.clear()
            _registrar_agendador_fresco()
            with patch.object(svc, "send_mail") as mock_send:
                self._executar()
                self.assertEqual(mock_send.call_count, 1)
                # 16:00 cumprido: o mesmo horário não gera segundo envio.
                self._executar()
                self.assertEqual(mock_send.call_count, 1)

        estado = EstadoRelatorioFalhas.objects.get(pk=1)
        self.assertEqual(timezone.localtime(estado.ultimo_envio_em).time(), dt_time(16, 2))

    def test_falha_de_envio_re_tenta_o_mesmo_horario_no_ciclo_seguinte(self):
        _configurar(horarios="00:00")
        self._criar_pendencias_de_todas_as_filas(timezone.now() - timedelta(minutes=10))

        with patch.object(svc, "send_mail", side_effect=Exception("SMTP indisponível")):
            with self.assertLogs("producao.services.relatorio_falhas_email", level="ERROR"):
                # Falha do canal de e-mail não é falha do sistema: o ciclo segue.
                self._executar()

        # Falha não grava estado: o horário permanece por cumprir.
        self.assertFalse(EstadoRelatorioFalhas.objects.exists())
        with patch.object(svc, "send_mail") as mock_send:
            self._executar()
        self.assertEqual(mock_send.call_count, 1)

    def test_padroes_da_chave_respondem_sem_linha_no_banco(self):
        # Defaults declarados em código: horários 07:00,16:00, destinatários
        # ti@empresa.com.br e limiar 5 — o relatório já nasce ativo no deploy,
        # sem nenhuma configuração pela tela.
        _configurar(horarios=None, destinatarios=None, limiar=None)
        agora = _hoje(7, 1)
        self._criar_pendencias_de_todas_as_filas(agora - timedelta(minutes=10))

        with _congelar_agora(agora):
            status._SERVICES.clear()
            _registrar_agendador_fresco()
            with patch.object(svc, "send_mail") as mock_send:
                self._executar()

        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(mock_send.call_args.kwargs["recipient_list"], ["ti@empresa.com.br"])

    def test_horarios_vazios_plantados_mantem_o_relatorio_desativado(self):
        # Defesa: linha gravada vazia por fora do validador (shell/migração)
        # desativa o relatório — pela tela o padrão agora é preenchido.
        ConfiguracaoAplicacao.objects.create(chave=CHAVE_HORARIOS, valor="", descricao="d")
        _configurar(horarios=None, destinatarios=None)
        self._criar_pendencias_de_todas_as_filas(timezone.now() - timedelta(minutes=10))

        with patch.object(svc, "send_mail") as mock_send:
            with self.assertLogs("producao.services.relatorio_falhas_email", level="WARNING"):
                self._executar()

        mock_send.assert_not_called()
        self.assertFalse(EstadoRelatorioFalhas.objects.exists())

    def test_destinatarios_vazios_plantados_logam_aviso_e_nao_enviam(self):
        # Mesma defesa para destinatários: vazio plantado fora do validador
        # desativa o envio com aviso em log.
        ConfiguracaoAplicacao.objects.create(chave=CHAVE_DESTINATARIOS, valor="", descricao="d")
        _configurar(destinatarios=None)
        self._criar_pendencias_de_todas_as_filas(timezone.now() - timedelta(minutes=10))

        with patch.object(svc, "send_mail") as mock_send:
            with self.assertLogs("producao.services.relatorio_falhas_email", level="WARNING"):
                self._executar()

        mock_send.assert_not_called()
        self.assertFalse(EstadoRelatorioFalhas.objects.exists())

    def test_configuracao_alterada_no_banco_vale_na_proxima_apuracao(self):
        # Limiar 1440: pendência de 10 min ainda não envelhece → não envia.
        _configurar(horarios="00:00", limiar="1440")
        self._criar_pendencias_de_todas_as_filas(timezone.now() - timedelta(minutes=10))

        with patch.object(svc, "send_mail") as mock_send:
            self._executar()
        mock_send.assert_not_called()

        # Alteração pela tela (definir → cache invalidado por signal): sem
        # reinício, a próxima apuração já usa limiar e destinatários novos.
        definir(CHAVE_LIMIAR, "5", None)
        definir(CHAVE_DESTINATARIOS, DESTINATARIOS_VARIOS, None)
        with patch.object(svc, "send_mail") as mock_send:
            self._executar()

        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(mock_send.call_args.kwargs["recipient_list"], LISTA_DESTINATARIOS_VARIOS)
        estado = EstadoRelatorioFalhas.objects.get(pk=1)
        self.assertIsNotNone(estado.ultimo_envio_em)

    def test_limiar_padrao_funciona_sem_linha_no_banco(self):
        # Chave do limiar sem linha: o default declarado (5) responde.
        _configurar(horarios="00:00", limiar=None)
        self._criar_pendencias_de_todas_as_filas(timezone.now() - timedelta(minutes=10))

        with patch.object(svc, "send_mail") as mock_send:
            self._executar()

        self.assertEqual(mock_send.call_count, 1)

    def test_pendencia_apos_horario_cumprido_sai_no_horario_seguinte(self):
        # 07:00 já cumpriu; a pendência que surge depois espera o 16:00.
        _configurar(horarios="07:00,16:00")
        EstadoRelatorioFalhas.objects.create(pk=1, ultimo_envio_em=_hoje(7, 1))
        agora = _hoje(10, 0)
        self._criar_pendencias_de_todas_as_filas(agora - timedelta(minutes=10))

        with _congelar_agora(agora):
            status._SERVICES.clear()
            _registrar_agendador_fresco()
            with patch.object(svc, "send_mail") as mock_send:
                self._executar()

        mock_send.assert_not_called()
        # O estado não mudou: nenhum envio foi gerado fora de horário.
        estado = EstadoRelatorioFalhas.objects.get(pk=1)
        self.assertEqual(timezone.localtime(estado.ultimo_envio_em).time(), dt_time(7, 1))

    def test_reinicio_do_processo_nao_reenvia_horario_cumprido(self):
        _configurar(horarios="00:00")
        self._criar_pendencias_de_todas_as_filas(timezone.now() - timedelta(minutes=10))

        with patch.object(svc, "send_mail") as mock_send:
            self._executar()
        self.assertEqual(mock_send.call_count, 1)

        # Reinício: cache de configuração e registry do painel recomeçam;
        # a marca de horário cumprido está no banco e impede o reenvio.
        configuracoes_svc.limpar_cache()
        status._SERVICES.clear()
        _registrar_agendador_fresco()
        with patch.object(svc, "send_mail") as mock_send:
            self._executar()
        mock_send.assert_not_called()

    def test_registrar_envio_mantem_singleton(self):
        svc.RelatorioFalhasEmailWorker.registrar_envio(_hoje(7, 0))
        svc.RelatorioFalhasEmailWorker.registrar_envio(_hoje(16, 0))

        self.assertEqual(EstadoRelatorioFalhas.objects.count(), 1)
        estado = EstadoRelatorioFalhas.objects.get(pk=1)
        self.assertEqual(timezone.localtime(estado.ultimo_envio_em).hour, 16)

    def test_todas_as_filas_aparecem_com_sua_chave(self):
        _configurar(horarios="00:00")
        self._criar_pendencias_de_todas_as_filas(timezone.now() - timedelta(minutes=10))

        with patch.object(svc, "send_mail") as mock_send:
            self._executar()

        corpo = mock_send.call_args.kwargs["message"]
        self.assertIn("Fila Log Tempos ERP", corpo)
        self.assertIn("Fila Log Apontamento Componentes: 1 pendência(s)", corpo)
        self.assertIn("OP 100123 (lote L123)", corpo)
        self.assertIn("Fila Baixa Componentes: 1 pendência(s)", corpo)
        self.assertIn("OP 100123 (lote bobina L456)", corpo)
        self.assertIn("Fila WMS Integrações: 1 pendência(s)", corpo)
        self.assertIn("OP 100123 (lote 0)", corpo)
        self.assertIn("Fila Consulta de Lotes: 1 pendência(s)", corpo)
        self.assertIn("lote L789 (bobina 42)", corpo)

    def test_fonte_telemetria_saudavel_ou_inativa_nao_aparece(self):
        _configurar(horarios="00:00")
        agora = timezone.now()
        FonteColetaHTTP.objects.create(
            url="http://192.0.2.10/coleta",
            coleta_ativa=True,
            log=LOG_COLETA_SUCESSO,
            ultima_coleta_em=agora - timedelta(minutes=10),
        )
        FonteColetaHTTP.objects.create(
            url="http://192.0.2.11/coleta",
            coleta_ativa=False,
            log="Falha na coleta de telemetria.",
            ultima_coleta_em=agora - timedelta(minutes=10),
        )
        # Ativa em falha: é a única que deve aparecer.
        FonteColetaHTTP.objects.create(
            url="http://192.0.2.12/coleta",
            coleta_ativa=True,
            log="Falha na coleta de telemetria.",
            ultima_coleta_em=agora - timedelta(minutes=10),
        )

        with patch.object(svc, "send_mail") as mock_send:
            self._executar()

        corpo = mock_send.call_args.kwargs["message"]
        self.assertIn("192.0.2.12", corpo)
        self.assertNotIn("192.0.2.10", corpo)
        self.assertNotIn("192.0.2.11", corpo)

    def test_executar_registra_ciclo_no_painel(self):
        _configurar(horarios="00:00")
        self._criar_pendencias_de_todas_as_filas(timezone.now() - timedelta(minutes=10))

        with patch.object(svc, "send_mail"):
            self._executar()

        registrado = status._SERVICES[svc.SERVICE_CODIGO]
        self.assertIsNotNone(registrado["ultimo_ciclo_fim"])
        self.assertFalse(registrado["ciclo_em_andamento"])

    def test_erro_do_ciclo_do_agendador_sai_mascarado_no_registry(self):
        # O registry não mascara: a origem do texto é que aplica a máscara.
        # Um segredo que escape numa exceção do ciclo não pode virar
        # ultimo_erro cru no painel Status (Services).
        self.addCleanup(setattr, EnviaPendenciasScheduler, "_running", False)

        def parar(_segundos):
            EnviaPendenciasScheduler._running = False

        with override_settings(SAPIENS_PASSWORD="senha_sapiens_123"):
            with patch.object(
                EnviaPendenciasScheduler,
                "enviar_pendencias",
                side_effect=Exception("Falha no banco senha_sapiens_123"),
            ):
                # DB mockado: o run() fecha conexões no fim do ciclo e a
                # conexão compartilhada do TestCase não pode ser vítima.
                with patch.object(scheduler_mod, "close_old_connections"):
                    with patch.object(scheduler_mod, "connections"):
                        with patch.object(
                            scheduler_mod,
                            "time",
                            SimpleNamespace(time=scheduler_mod.time.time, sleep=parar),
                        ):
                            # O shutdown limpa ultimo_erro; em produção o
                            # processo encerra com ele — aqui só o ciclo conta.
                            with patch.object(scheduler_mod, "marcar_service_parado"):
                                EnviaPendenciasScheduler().run()

        ultimo_erro = status._SERVICES["envia_pendencias"]["ultimo_erro"]
        self.assertIn("Falha no banco", ultimo_erro)
        self.assertNotIn("senha_sapiens_123", ultimo_erro)


class PlantioConfigInvalidoTests(TestCase):
    """Config plantada fora do validador (shell, ORM, migração).

    O validador da chave conhecida só vale na gravação pelo `definir()`;
    linha plantada por outra via pode trazer lixo — item inválido é
    ignorado com aviso, limiar cai no default declarado e destinatário
    malformado nunca chega ao envio (revalidado na leitura).
    """

    def setUp(self):
        self.addCleanup(status._SERVICES.clear)
        status._SERVICES.clear()
        self.addCleanup(configuracoes_svc.limpar_cache)
        configuracoes_svc.limpar_cache()
        _registrar_agendador_fresco()

    def _plantar(self, chave, valor):
        ConfiguracaoAplicacao.objects.create(
            chave=chave, valor=valor, descricao="plantio fora do validador"
        )

    def _criar_pendencia(self, idade_minutos=10):
        Apontamento.objects.create(
            codemp=91,
            origem="1",
            numorp=100123,
            codetg=100,
            seqrot=1,
            numcad=10,
            qtdre1="10",
            datger=timezone.now() - timedelta(minutes=idade_minutos),
            log="Falha no webservice.",
        )

    def test_destinatario_malformado_plantado_nao_chega_ao_envio(self):
        self._plantar(CHAVE_HORARIOS, "00:00")
        self._plantar(CHAVE_DESTINATARIOS, "operacao@dominio.com\r\nBcc: intruso@dominio.com")
        self._criar_pendencia()

        with patch.object(svc, "send_mail") as mock_send:
            svc.RelatorioFalhasEmailWorker.executar()

        recipient_list = mock_send.call_args.kwargs["recipient_list"]
        self.assertEqual(recipient_list, ["operacao@dominio.com"])
        self.assertNotIn("Bcc: intruso@dominio.com", recipient_list)

    def test_horario_invalido_plantado_e_ignorado_usa_os_validos(self):
        self._plantar(CHAVE_HORARIOS, "99:99,00:00")
        self._plantar(CHAVE_DESTINATARIOS, "operacao@dominio.com")
        self._criar_pendencia()

        with patch.object(svc, "send_mail") as mock_send:
            with self.assertLogs("producao.services.relatorio_falhas_email", level="WARNING"):
                svc.RelatorioFalhasEmailWorker.executar()

        self.assertEqual(mock_send.call_count, 1)

    def test_limiar_invalido_plantado_cai_no_padrao_declarado(self):
        # Limiar plantado "abc" → default declarado (5): pendência de 10 min
        # envelhece e o relatório sai; se o valor ruim fosse usado, não sairia.
        self._plantar(CHAVE_HORARIOS, "00:00")
        self._plantar(CHAVE_DESTINATARIOS, "operacao@dominio.com")
        self._plantar(CHAVE_LIMIAR, "abc")
        self._criar_pendencia(idade_minutos=10)

        with patch.object(svc, "send_mail") as mock_send:
            svc.RelatorioFalhasEmailWorker.executar()

        self.assertEqual(mock_send.call_count, 1)
        self.assertIn("Fila Log Apontamentos", mock_send.call_args.kwargs["message"])
