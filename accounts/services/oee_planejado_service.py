import logging
import threading
import time
from datetime import datetime, timedelta

from django.db import close_old_connections, connections

from producao.services.status import (
    marcar_ciclo_fim,
    marcar_ciclo_inicio,
    marcar_service_iniciado,
    marcar_service_parado,
    registrar_service,
)

from ..utils.planejado import consolidar_planejado_dia

logger = logging.getLogger(__name__)
SERVICE_CODIGO = "oee_planejado"
SERVICE_NOME = "Recalcula Planejado OEE"


class OEEPlanejadoScheduler(threading.Thread):
    _running = False
    _last_ontem_run_date = None
    intervalo_segundos = 600
    tempo_limite_ciclo_segundos = 180

    def __init__(self):
        super().__init__(name="OEEPlanejadoScheduler", daemon=True)
        registrar_service(
            SERVICE_CODIGO,
            SERVICE_NOME,
            self.intervalo_segundos,
            "Recalcula o planejado OEE do dia a cada 10 minutos e o dia anterior às 04:00.",
            self.tempo_limite_ciclo_segundos,
        )

    def run(self):
        if OEEPlanejadoScheduler._running:
            logger.warning("Scheduler já está rodando.")
            return

        OEEPlanejadoScheduler._running = True
        marcar_service_iniciado(SERVICE_CODIGO)
        logger.info("Iniciando scheduler interno do Recalcula Planejado OEE.")

        try:
            while OEEPlanejadoScheduler._running:
                inicio_ciclo = time.time()
                close_old_connections()
                with connections["default"].cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('application_name', 'sigma-oee-planejado', false)"
                    )
                marcar_ciclo_inicio(SERVICE_CODIGO)
                erro_ciclo = ""
                try:
                    now = datetime.now()
                    current_date = now.date()
                    current_hour = now.hour

                    logger.info(f"Executando consolidação automática: HOJE ({current_date})")
                    consolidar_planejado_dia(current_date)

                    if (
                        current_hour >= 4
                        and OEEPlanejadoScheduler._last_ontem_run_date != current_date
                    ):
                        ontem = current_date - timedelta(days=1)
                        logger.info(f"Executando consolidação automática: ONTEM ({ontem})")
                        consolidar_planejado_dia(ontem)
                        OEEPlanejadoScheduler._last_ontem_run_date = current_date

                except Exception as e:
                    erro_ciclo = e
                    logger.error(f"Erro no scheduler do planejado: {e}")
                finally:
                    marcar_ciclo_fim(
                        SERVICE_CODIGO,
                        time.time() - inicio_ciclo,
                        self.intervalo_segundos,
                        erro_ciclo,
                    )
                    connections.close_all()

                time.sleep(self.intervalo_segundos)
        finally:
            OEEPlanejadoScheduler._running = False
            marcar_service_parado(SERVICE_CODIGO)


def start_oee_planejado_scheduler():
    if not OEEPlanejadoScheduler._running:
        scheduler = OEEPlanejadoScheduler()
        scheduler.start()
