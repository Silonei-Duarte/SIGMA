import json
import logging
import re
import threading
import time
from xml.sax.saxutils import escape

from django.conf import settings
from django.db import close_old_connections, connections

from producao.services.sapiens import enviar_soap_sapiens
from producao.services.status import (
    marcar_atividade_service,
    marcar_ciclo_fim,
    marcar_ciclo_inicio,
    marcar_service_iniciado,
    marcar_service_parado,
    registrar_service,
)
from producao.utils.codificacao import get_response_text, safe_str
from producao.utils.sapiens_soap import escapar_cdata_sapiens
from SIGMA.segredos import mascarar_segredos

logger = logging.getLogger(__name__)
SERVICE_CODIGO = "importa_palete"
SERVICE_NOME = "Importação de paletes WMS"
WEBSERVICE_NOME = "ImportaWMS"
WEBSERVICE_ACAO = "IMPORTAR-PALETES"
WEBSERVICE_TIMEOUT_SEGUNDOS = 180
IMPORTA_PALETE_LOCK = threading.Lock()


class ImportaPaleteScheduler(threading.Thread):
    _running = False
    intervalo_segundos = 3600
    tempo_limite_ciclo_segundos = WEBSERVICE_TIMEOUT_SEGUNDOS

    def __init__(self):
        super().__init__(name="ImportaPaleteScheduler", daemon=True)
        registrar_service(
            SERVICE_CODIGO,
            SERVICE_NOME,
            self.intervalo_segundos,
            "Solicita ao WebService ImportaWMS a sincronização de paletes WMS no ERP.",
            self.tempo_limite_ciclo_segundos,
        )

    def run(self):
        if ImportaPaleteScheduler._running:
            print("[IMPORTA_PALETE] Scheduler já está rodando")
            return

        ImportaPaleteScheduler._running = True
        marcar_service_iniciado(SERVICE_CODIGO)
        print("[IMPORTA_PALETE] Scheduler iniciado")
        try:
            while ImportaPaleteScheduler._running:
                inicio_ciclo = time.time()
                close_old_connections()
                with connections["default"].cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('application_name', 'sigma-importa-palete', false)"
                    )
                marcar_ciclo_inicio(SERVICE_CODIGO)
                print("[IMPORTA_PALETE] Ciclo iniciado")
                erro_ciclo = ""
                try:
                    self.importar_paletes()
                except Exception as e:
                    erro_ciclo = e
                    logger.error(f"Erro no scheduler de importação de paletes WMS: {e}")
                finally:
                    duracao = time.time() - inicio_ciclo
                    marcar_ciclo_fim(SERVICE_CODIGO, duracao, self.intervalo_segundos, erro_ciclo)
                    connections.close_all()
                    print(f"[IMPORTA_PALETE] Ciclo finalizado em {duracao:.2f}s")

                time.sleep(self.intervalo_segundos)
        finally:
            ImportaPaleteScheduler._running = False
            marcar_service_parado(SERVICE_CODIGO)

    def importar_paletes(self):
        if not IMPORTA_PALETE_LOCK.acquire(blocking=False):
            print("[IMPORTA_PALETE] Importação já está em andamento")
            return None
        try:
            return self._importar_paletes_webservice()
        finally:
            IMPORTA_PALETE_LOCK.release()

    def _importar_paletes_webservice(self):
        payload = json.dumps(
            {"wacao": WEBSERVICE_ACAO, "chave": "", "valor": ""},
            ensure_ascii=False,
        )
        envelope = f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<soapenv:Envelope xmlns:soapenv="http://www.w3.org/2003/05/soap-envelope" xmlns:ser="http://services.senior.com.br">
  <soapenv:Header/>
  <soapenv:Body>
    <ser:{WEBSERVICE_NOME}>
      <user>{escape(str(settings.SAPIENS_USERNAME))}</user>
      <password>{escape(str(settings.SAPIENS_PASSWORD))}</password>
      <encryption>0</encryption>
      <parameters><flowInstanceID></flowInstanceID><flowName></flowName><tabelaEntradas><chave>wdados</chave><valor><![CDATA[{escapar_cdata_sapiens(payload)}]]></valor></tabelaEntradas></parameters>
    </ser:{WEBSERVICE_NOME}>
  </soapenv:Body>
</soapenv:Envelope>"""
        url = (
            f"{settings.SAPIENS_URL_BASE}/g5-senior-services/sapiens_Synccustom.senior.man.producao"
        )
        marcar_atividade_service(SERVICE_CODIGO, WEBSERVICE_TIMEOUT_SEGUNDOS)
        # validar_status=False: HTTP != 200 é interpretado aqui (RuntimeError com
        # corpo mascarado), não pelo transporte — igual ao envia_tempos_erp.
        resposta = enviar_soap_sapiens(
            url,
            envelope,
            timeout=WEBSERVICE_TIMEOUT_SEGUNDOS,
            validar_status=False,
        )
        retorno = get_response_text(resposta)
        if not resposta.ok:
            raise RuntimeError(f"HTTP {resposta.status_code}: {mascarar_segredos(retorno)}")

        encontrado = re.search(r"<waRetorno>(.*?)</waRetorno>", retorno, re.DOTALL | re.IGNORECASE)
        conteudo = (encontrado.group(1) if encontrado else retorno).strip()
        try:
            dados = json.loads(conteudo)
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Retorno inválido do ImportaWMS: {mascarar_segredos(conteudo)}"
            ) from exc

        if dados.get("status") != "OK":
            raise RuntimeError(safe_str(dados.get("message") or mascarar_segredos(conteudo)))

        total_registros = dados.get("total_registros")
        if not isinstance(total_registros, int):
            raise RuntimeError(f"Retorno sem total de registros: {mascarar_segredos(conteudo)}")

        print(f"[IMPORTA_PALETE] ImportaWMS concluído. Registros na USU_TPALWMS: {total_registros}")
        return total_registros


def start_importa_palete_scheduler():
    if not ImportaPaleteScheduler._running:
        scheduler = ImportaPaleteScheduler()
        scheduler.start()
