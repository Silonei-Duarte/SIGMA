import logging
import threading
import time

from django.db import close_old_connections, connections

from producao.services.status import (
    consumir_interrupcao_timeout,
    marcar_ciclo_fim,
    marcar_ciclo_inicio,
    marcar_service_iniciado,
    marcar_service_parado,
    matar_services_travados,
    registrar_service,
)
from producao.utils.codificacao import safe_str
from SIGMA.segredos import mascarar_segredos

logger = logging.getLogger(__name__)
SERVICE_CODIGO = "envia_pendencias"
SERVICE_NOME = "Envio automático de pendências"
SERVICES_MONITORADOS_TIMEOUT = (
    "consolida_tempos_erp",
    "envia_pendencias",
    "fila_consulta_lotes",
    "fila_logs_apontamentos",
    "fila_tempos_erp",
    "fila_log_apontamento_componentes",
    "fila_baixa_componentes",
    "fila_wms_integracoes",
    "relatorio_falhas_email",
    "sincroniza_ops_encerradas",
    "oee_planejado",
    "coleta_telemetria",
)


class EnviaPendenciasScheduler(threading.Thread):
    _running = False
    intervalo_segundos = 300
    tempo_limite_ciclo_segundos = 60

    def __init__(self):
        super().__init__(name="EnviaPendenciasScheduler", daemon=True)
        # Import local: os serviços importam modules de outros apps e o
        # scheduler sobe durante o bootstrap (padrão de import lazy do arquivo).
        from producao.services.relatorio_falhas_email import RelatorioFalhasEmailWorker

        registrar_service(
            SERVICE_CODIGO,
            SERVICE_NOME,
            self.intervalo_segundos,
            "Envia pendências de Log Apontamentos, Log Tempos ERP, Log Apontamento Componentes, Baixa Componentes, WMS Integrações e Consulta de Lotes, e dispara o Relatório diário de falhas por e-mail.",
            self.tempo_limite_ciclo_segundos,
        )
        # O relatório de falhas roda dentro do ciclo deste scheduler;
        # registra a si próprio para aparecer no painel de Status (Services).
        RelatorioFalhasEmailWorker.registrar()

    def run(self):
        if EnviaPendenciasScheduler._running:
            print("[ENVIA_PENDENCIAS] Scheduler já está rodando")
            return

        EnviaPendenciasScheduler._running = True
        marcar_service_iniciado(SERVICE_CODIGO)
        print("[ENVIA_PENDENCIAS] Scheduler iniciado")
        try:
            while EnviaPendenciasScheduler._running:
                inicio_ciclo = time.time()
                close_old_connections()
                with connections["default"].cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('application_name', 'sigma-envia-pendencias', false)"
                    )
                marcar_ciclo_inicio(SERVICE_CODIGO)
                print("[ENVIA_PENDENCIAS] Ciclo iniciado")
                erro_ciclo = ""
                try:
                    self.enviar_pendencias()
                except Exception as e:
                    # A máscara fica na origem do texto: o registry só converte
                    # com safe_str, não mascara — erro de banco/HTTP não sai
                    # cru para o painel nem para o log.
                    erro_ciclo = mascarar_segredos(safe_str(e))
                    logger.error("Erro no scheduler de envio de pendências: %s", erro_ciclo)
                finally:
                    duracao = time.time() - inicio_ciclo
                    marcar_ciclo_fim(SERVICE_CODIGO, duracao, self.intervalo_segundos, erro_ciclo)
                    connections.close_all()
                    print(f"[ENVIA_PENDENCIAS] Ciclo finalizado em {duracao:.2f}s")

                time.sleep(self.intervalo_segundos)
        finally:
            EnviaPendenciasScheduler._running = False
            marcar_service_parado(SERVICE_CODIGO)

    def enviar_pendencias(self):
        interrompidos = matar_services_travados(SERVICES_MONITORADOS_TIMEOUT)
        if interrompidos:
            print(
                f"[ENVIA_PENDENCIAS] Timeouts sinalizados; aguardando término seguro: {', '.join(interrompidos)}"
            )

        self._enviar_logs_apontamentos()
        self._enviar_tempos_erp()
        self._enviar_logs_apontamento_componentes()
        self._enviar_baixas_componentes()
        self._enviar_integracoes_wms()
        self._enviar_consulta_lotes()
        self._enviar_relatorio_falhas_email()

    def _enviar_relatorio_falhas_email(self):
        from producao.services.relatorio_falhas_email import RelatorioFalhasEmailWorker

        # Último do ciclo: relata o estado após o tratamento das filas.
        # Falha do relatório não derruba o ciclo (executar trata as próprias
        # exceções), então as chamadas seguintes de outro ciclo não são afetadas.
        RelatorioFalhasEmailWorker.executar()

    def _enviar_logs_apontamentos(self):
        from producao.models import Apontamento
        from producao.views.logs_apontamentos import (
            PROCESSAMENTO_LOGS_LOCK,
            WEBSERVICE_TIMEOUT_SEGUNDOS,
            disparar_envio_apontamentos,
            liberar_apontamentos_processando_antigos,
        )

        if PROCESSAMENTO_LOGS_LOCK.locked():
            print("[ENVIA_PENDENCIAS] Logs apontamentos: processamento em andamento")
            return

        liberados = 0
        if consumir_interrupcao_timeout("fila_logs_apontamentos"):
            liberados = liberar_apontamentos_processando_antigos()
        else:
            liberados = liberar_apontamentos_processando_antigos(
                idade_segundos=WEBSERVICE_TIMEOUT_SEGUNDOS
            )

        pendentes = Apontamento.objects.filter(status=Apontamento.Status.NAO_INTEGRADO).exists()
        if not pendentes:
            print("[ENVIA_PENDENCIAS] Logs apontamentos: nenhum pendente")
            return

        disparar_envio_apontamentos()
        print(
            f"[ENVIA_PENDENCIAS] Logs apontamentos: envio disparado. Antigos liberados={liberados}"
        )

    def _enviar_tempos_erp(self):
        from producao.models import PacoteTempoERP
        from producao.services.envia_tempos_erp import (
            PROCESSAMENTO_TEMPOS_ERP_LOCK,
            WEBSERVICE_TIMEOUT_SEGUNDOS,
            disparar_envio_tempos_erp,
            liberar_pacotes_tempo_erp_processando_antigos,
        )

        if PROCESSAMENTO_TEMPOS_ERP_LOCK.locked():
            print("[ENVIA_PENDENCIAS] Log Tempos ERP: processamento em andamento")
            return

        liberados = liberar_pacotes_tempo_erp_processando_antigos(WEBSERVICE_TIMEOUT_SEGUNDOS)
        # Erro não existe mais como estado: falha permanece PENDENTE.
        if not PacoteTempoERP.objects.filter(status=PacoteTempoERP.Status.PENDENTE).exists():
            print(
                f"[ENVIA_PENDENCIAS] Log Tempos ERP: nenhum pendente. Antigos liberados={liberados}"
            )
            return

        disparar_envio_tempos_erp()
        print(f"[ENVIA_PENDENCIAS] Log Tempos ERP: envio disparado. Antigos liberados={liberados}")

    def _enviar_logs_apontamento_componentes(self):
        from producao.models import ApontamentoComponente
        from producao.views.logs_apontamento_componentes import (
            PROCESSAMENTO_APONTAMENTO_COMPONENTES_LOCK,
            WEBSERVICE_TIMEOUT_SEGUNDOS,
            disparar_envio_componentes,
            liberar_componentes_processando_antigos,
        )

        if PROCESSAMENTO_APONTAMENTO_COMPONENTES_LOCK.locked():
            print("[ENVIA_PENDENCIAS] Logs apontamento componentes: processamento em andamento")
            return

        liberados = 0
        if consumir_interrupcao_timeout("fila_log_apontamento_componentes"):
            liberados = liberar_componentes_processando_antigos()
        else:
            liberados = liberar_componentes_processando_antigos(
                idade_segundos=WEBSERVICE_TIMEOUT_SEGUNDOS
            )

        pendentes = ApontamentoComponente.objects.filter(
            status=ApontamentoComponente.Status.NAO_INTEGRADO
        ).exists()
        if not pendentes:
            print("[ENVIA_PENDENCIAS] Logs apontamento componentes: nenhum pendente")
            return

        disparar_envio_componentes()
        print(
            f"[ENVIA_PENDENCIAS] Logs apontamento componentes: envio disparado. Antigos liberados={liberados}"
        )

    def _enviar_baixas_componentes(self):
        from producao.models import BaixaComponente
        from producao.views.logs_baixa_componentes import (
            PROCESSAMENTO_BAIXAS_COMPONENTES_LOCK,
            WEBSERVICE_TIMEOUT_SEGUNDOS,
            disparar_envio_baixas_componentes,
            liberar_baixas_componentes_processando_antigas,
        )

        if PROCESSAMENTO_BAIXAS_COMPONENTES_LOCK.locked():
            print("[ENVIA_PENDENCIAS] Baixa componentes: processamento em andamento")
            return

        if consumir_interrupcao_timeout("fila_baixa_componentes"):
            liberados = liberar_baixas_componentes_processando_antigas()
        else:
            liberados = liberar_baixas_componentes_processando_antigas(
                idade_segundos=WEBSERVICE_TIMEOUT_SEGUNDOS
            )

        if not BaixaComponente.objects.filter(status=BaixaComponente.Status.NAO_INTEGRADO).exists():
            print("[ENVIA_PENDENCIAS] Baixa componentes: nenhum pendente")
            return

        disparar_envio_baixas_componentes()
        print(
            f"[ENVIA_PENDENCIAS] Baixa componentes: envio disparado. Antigos liberados={liberados}"
        )

    def _enviar_integracoes_wms(self):
        from setores.qualidade.models.estrutura import WMS_IntegraçãoOP
        from setores.qualidade.views.wms_views import (
            PROCESSAMENTO_WMS_LOCK,
            WEBSERVICE_TIMEOUT_SEGUNDOS,
            disparar_envio_wms,
            liberar_integracoes_wms_processando_antigas,
            limpar_integracoes_wms_antigas,
            reservar_integracoes_wms_para_envio,
        )

        if PROCESSAMENTO_WMS_LOCK.locked():
            print("[ENVIA_PENDENCIAS] WMS: processamento em andamento")
            return

        liberados = 0
        if consumir_interrupcao_timeout("fila_wms_integracoes"):
            liberados = liberar_integracoes_wms_processando_antigas()
        else:
            liberados = liberar_integracoes_wms_processando_antigas(
                idade_segundos=WEBSERVICE_TIMEOUT_SEGUNDOS
            )

        removidos = limpar_integracoes_wms_antigas()

        ids = reservar_integracoes_wms_para_envio(WMS_IntegraçãoOP.objects.order_by("id"))
        if not ids:
            print(
                f"[ENVIA_PENDENCIAS] WMS: nenhum pendente. Antigos liberados={liberados}; removidos={removidos}"
            )
            return

        disparar_envio_wms(ids)
        print(
            f"[ENVIA_PENDENCIAS] WMS: envio disparado para {len(ids)} registro(s). Antigos liberados={liberados}; removidos={removidos}"
        )

    def _enviar_consulta_lotes(self):
        from setores.qualidade.models import LiberacaoLote
        from setores.qualidade.views.consulta_lote import (
            PROCESSAMENTO_LOTES_LOCK,
            WEBSERVICE_TIMEOUT_SEGUNDOS,
            disparar_envio_lotes,
            liberar_lotes_processando_antigos,
            reservar_lotes_para_envio,
        )

        if PROCESSAMENTO_LOTES_LOCK.locked():
            print("[ENVIA_PENDENCIAS] Consulta de Lotes: processamento em andamento")
            return

        liberados = 0
        if consumir_interrupcao_timeout("fila_consulta_lotes"):
            liberados = liberar_lotes_processando_antigos()
        else:
            liberados = liberar_lotes_processando_antigos(
                idade_segundos=WEBSERVICE_TIMEOUT_SEGUNDOS
            )

        ids = reservar_lotes_para_envio(LiberacaoLote.objects.order_by("id"))
        if not ids:
            print(
                f"[ENVIA_PENDENCIAS] Consulta de Lotes: nenhum pendente. Antigos liberados={liberados}"
            )
            return

        disparar_envio_lotes(ids)
        print(
            f"[ENVIA_PENDENCIAS] Consulta de Lotes: envio disparado para {len(ids)} registro(s). Antigos liberados={liberados}"
        )


def start_envia_pendencias_scheduler():
    if not EnviaPendenciasScheduler._running:
        scheduler = EnviaPendenciasScheduler()
        scheduler.start()
