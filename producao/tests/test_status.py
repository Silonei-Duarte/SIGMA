from datetime import timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from producao.services import status


class TimeoutServiceTests(SimpleTestCase):
    def setUp(self):
        self.addCleanup(status._SERVICES.clear)
        status._SERVICES.clear()

    def test_timeout_e_sinalizado_sem_interromper_thread(self):
        status.registrar_service("teste", "Teste", tempo_limite_ciclo_segundos=10)
        service = status._SERVICES["teste"]
        service.update(
            {
                "ciclo_em_andamento": True,
                "ultimo_ciclo_inicio": timezone.now() - timedelta(seconds=11),
                "thread_ident": 123,
            }
        )

        self.assertTrue(status.matar_service_travado("teste"))
        self.assertTrue(service["interrompido_por_timeout"])
        self.assertIn("aguardando", service["ultimo_status"].lower())
