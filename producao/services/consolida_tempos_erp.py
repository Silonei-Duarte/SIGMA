import logging
import threading
import time
from datetime import datetime, timedelta

from django.db import IntegrityError, close_old_connections, connections, transaction
from django.db.models import F, OuterRef, Q, Subquery
from django.utils import timezone

from producao.models import (
    ItemPacoteTempoERP,
    LogTrocaOPAtiva,
    PacoteTempoERP,
    ParadaMaquina,
)
from producao.services.status import (
    marcar_ciclo_fim,
    marcar_ciclo_inicio,
    marcar_service_iniciado,
    marcar_service_parado,
    registrar_service,
)

logger = logging.getLogger(__name__)
SERVICE_CODIGO = "consolida_tempos_erp"
SERVICE_NOME = "Consolidação de tempos ERP"


def _proximo_horario_agendado(agora):
    horario_local = timezone.localtime(agora)
    for hora in (0, 6, 12, 18):
        proximo = horario_local.replace(
            hour=hora,
            minute=15,
            second=0,
            microsecond=0,
        )
        if proximo > horario_local:
            return proximo
    return (horario_local + timedelta(days=1)).replace(
        hour=0,
        minute=15,
        second=0,
        microsecond=0,
    )


def _maior_motivo_no_intervalo(parada, inicio, fim):
    maior_tempo = timedelta()
    maior_motivo = ""
    justificativas = list(parada.justificativas.all())
    for indice, justificativa in enumerate(justificativas):
        inicio_justificativa = justificativa.parcial
        if justificativa.tempo is not None:
            fim_justificativa = inicio_justificativa + justificativa.tempo
        elif indice + 1 < len(justificativas):
            fim_justificativa = justificativas[indice + 1].parcial
        else:
            fim_justificativa = parada.fim or fim

        inicio_sobreposto = max(inicio, inicio_justificativa)
        fim_sobreposto = min(fim, fim_justificativa)
        tempo_sobreposto = fim_sobreposto - inicio_sobreposto
        if tempo_sobreposto > maior_tempo:
            maior_tempo = tempo_sobreposto
            maior_motivo = justificativa.motivo
    return maior_motivo


def _data_hora_item(data, hora):
    data_hora = datetime.combine(data, hora)
    return timezone.make_aware(data_hora, timezone.get_current_timezone())


def _proximo_inicio_disponivel(pacote, tipo_registro):
    ultimo_item = (
        ItemPacoteTempoERP.objects.filter(
            pacote_tempo_erp__troca_op_ativa=pacote.troca_op_ativa,
            pacote_tempo_erp__corte_fim_real__lte=pacote.corte_inicio_real,
            tipo_registro=tipo_registro,
        )
        .select_related("pacote_tempo_erp")
        .order_by("-pacote_tempo_erp__corte_fim_real", "-id")
        .first()
    )
    if not ultimo_item:
        return None
    return _data_hora_item(
        ultimo_item.data_fim,
        ultimo_item.hora_fim,
    ) + timedelta(minutes=1)


def _criar_item(pacote, tipo_registro, operador, inicio, fim, motivo="", inicio_minimo=None):
    # O ERP recebe somente minutos; os limites do pacote já são consolidados no minuto.
    inicio = timezone.localtime(inicio)
    fim = timezone.localtime(fim)
    inicio = inicio.replace(second=0, microsecond=0)
    fim = fim.replace(second=0, microsecond=0)

    # O ERP não aceita horário exatamente à meia-noite.
    if inicio.hour == 0 and inicio.minute == 0:
        inicio += timedelta(minutes=1)
    if fim.hour == 0 and fim.minute == 0:
        fim += timedelta(minutes=1)
    if inicio_minimo and inicio < inicio_minimo:
        inicio = inicio_minimo
    if inicio >= fim:
        logger.warning(
            "Item ERP ignorado por não haver minuto disponível: pacote=%s tipo=%s",
            pacote.id,
            tipo_registro,
        )
        return None

    ItemPacoteTempoERP.objects.create(
        pacote_tempo_erp=pacote,
        tipo_registro=tipo_registro,
        operador=operador,
        # motivo é NOT NULL sem default no banco; None estouraria IntegrityError
        # e o scheduler descartaria o pacote inteiro no except.
        motivo=motivo or "",
        data_inicio=inicio.date(),
        hora_inicio=inicio.time().replace(microsecond=0),
        data_fim=fim.date(),
        hora_fim=fim.time().replace(microsecond=0),
    )
    return inicio, fim


def preencher_itens_pacote_tempo_erp(pacote):
    """Monta novamente os itens de um corte já definido de produção/paro."""
    periodo = pacote.troca_op_ativa
    inicio_real = pacote.corte_inicio_real
    fim_real = pacote.corte_fim_real
    if inicio_real >= fim_real or not periodo.id_operador:
        return False

    tem_parada_nao_justificada = (
        ParadaMaquina.objects.filter(periodos_produtivos=periodo, inicio__lt=fim_real)
        .filter(Q(fim__isnull=True) | Q(fim__gt=inicio_real))
        .filter(
            Q(justificativas__isnull=True)
            | Q(justificativas__motivo__isnull=True)
            | Q(justificativas__motivo="")
        )
        .exists()
    )
    if tem_parada_nao_justificada:
        return False

    pacote.itens.all().delete()
    inicio_minimo_producao = _proximo_inicio_disponivel(
        pacote,
        ItemPacoteTempoERP.TipoRegistro.PRODUCAO,
    )
    producao = _criar_item(
        pacote,
        ItemPacoteTempoERP.TipoRegistro.PRODUCAO,
        periodo.id_operador,
        inicio_real,
        fim_real,
        inicio_minimo=inicio_minimo_producao,
    )
    if not producao:
        pacote.itens.all().delete()
        return False

    inicio_producao, _ = producao
    inicio_minimo_parada = _proximo_inicio_disponivel(
        pacote,
        ItemPacoteTempoERP.TipoRegistro.PARADA,
    )
    inicio_minimo_parada = max(
        inicio_minimo_parada or inicio_producao,
        inicio_producao + timedelta(minutes=1),
    )
    paradas = list(
        ParadaMaquina.objects.filter(periodos_produtivos=periodo, inicio__lt=fim_real)
        .filter(Q(fim__isnull=True) | Q(fim__gt=inicio_real))
        .prefetch_related("justificativas")
        .order_by("inicio", "id")
    )
    fim_maximo_parada = fim_real - timedelta(minutes=1)
    paradas_encaixadas = []
    for parada in reversed(paradas):
        inicio_parada = max(parada.inicio, inicio_real, inicio_minimo_parada)
        fim_parada = min(parada.fim or fim_real, fim_real)
        inicio_parada = inicio_parada.replace(second=0, microsecond=0)
        fim_parada = min(
            fim_parada.replace(second=0, microsecond=0),
            fim_maximo_parada,
        )
        if inicio_parada >= fim_parada:
            continue
        paradas_encaixadas.append((parada, inicio_parada, fim_parada))
        fim_maximo_parada = inicio_parada - timedelta(minutes=1)

    for parada, inicio_parada, fim_parada in reversed(paradas_encaixadas):
        _criar_item(
            pacote,
            ItemPacoteTempoERP.TipoRegistro.PARADA,
            int(parada.operador) if str(parada.operador).isdigit() else periodo.id_operador,
            inicio_parada,
            fim_parada,
            _maior_motivo_no_intervalo(parada, inicio_parada, fim_parada),
        )
    return True


def reconsolidar_pacotes_tempo_erp(pacotes):
    """Atualiza somente cortes ainda locais, sem tocar pacotes já integrados
    ou em processamento."""
    pacotes = sorted(
        (
            pacote
            for pacote in pacotes
            # Falha de envio não tem estado próprio: erro É pendente.
            if pacote.status == PacoteTempoERP.Status.PENDENTE
        ),
        key=lambda pacote: (
            pacote.troca_op_ativa_id,
            pacote.corte_inicio_real,
            pacote.corte_fim_real,
            pacote.pk,
        ),
    )
    agora = timezone.now()
    for pacote in pacotes:
        if not preencher_itens_pacote_tempo_erp(pacote):
            raise ValueError(
                "Não foi possível regenerar um pacote local porque há período inválido "
                "ou parada sem justificativa."
            )
        pacote.status = PacoteTempoERP.Status.PENDENTE
        pacote.log = "Regenerado após correção de parada."
        pacote.data_hora_log = agora
        pacote.save(update_fields=["status", "log", "data_hora_log"])
    return len(pacotes)


def gerar_cortes_tempos_erp(corte_fim=None):
    corte_fim = (corte_fim or timezone.now()).replace(second=0, microsecond=0)
    ultimo_pacote = (
        PacoteTempoERP.objects.filter(troca_op_ativa_id=OuterRef("pk"))
        .order_by("-corte_fim_real", "-id")
        .values("corte_fim_real")[:1]
    )
    periodos = (
        LogTrocaOPAtiva.objects.annotate(ultimo_corte_gerado=Subquery(ultimo_pacote))
        .filter(horario_troca__lt=corte_fim)
        .filter(
            Q(horario_saida__isnull=True)
            | Q(ultimo_corte_gerado__isnull=True)
            | Q(horario_saida__gt=F("ultimo_corte_gerado"))
        )
        .select_related("recurso")
        .order_by("id")
    )
    criados = 0

    for periodo in periodos:
        inicio_real = (periodo.ultimo_corte_gerado or periodo.horario_troca).replace(
            second=0, microsecond=0
        )
        fim_real = min(periodo.horario_saida or corte_fim, corte_fim).replace(
            second=0, microsecond=0
        )
        if inicio_real >= fim_real or not periodo.id_operador:
            continue

        try:
            with transaction.atomic():
                pacote, criado = PacoteTempoERP.objects.get_or_create(
                    troca_op_ativa=periodo,
                    corte_inicio_real=inicio_real,
                    corte_fim_real=fim_real,
                    defaults={"status": PacoteTempoERP.Status.PENDENTE, "datger": timezone.now()},
                )
                if not criado:
                    continue
                if not preencher_itens_pacote_tempo_erp(pacote):
                    logger.info(
                        "Pacote de tempos não criado: há período inválido ou parada não justificada. troca=%s início=%s fim=%s",
                        periodo.id,
                        inicio_real,
                        fim_real,
                    )
                    pacote.delete()
                    continue
                criados += 1
        except IntegrityError:
            # Corrida entre schedulers derruba o get_or_create por chave única:
            # o pacote só volta a nascer no próximo corte, mas o descarte
            # precisa ficar visível para não parecer fila vazia por acaso.
            logger.warning(
                "Pacote de tempos descartado por violação de integridade: troca=%s início=%s fim=%s",
                periodo.id,
                inicio_real,
                fim_real,
            )
            continue
    return criados


class ConsolidaTemposERPScheduler(threading.Thread):
    _running = False
    intervalo_segundos = 21600
    tempo_limite_ciclo_segundos = 60

    def __init__(self):
        super().__init__(name="ConsolidaTemposERPScheduler", daemon=True)
        registrar_service(
            SERVICE_CODIGO,
            SERVICE_NOME,
            self.intervalo_segundos,
            "Gera pacotes locais de produção e paradas às 00h15, 06h15, 12h15 e 18h15, desde o último corte gerado.",
            self.tempo_limite_ciclo_segundos,
        )

    def run(self):
        if ConsolidaTemposERPScheduler._running:
            return
        ConsolidaTemposERPScheduler._running = True
        marcar_service_iniciado(SERVICE_CODIGO)
        proxima_execucao = _proximo_horario_agendado(timezone.now())
        marcar_ciclo_fim(
            SERVICE_CODIGO,
            0,
            max((proxima_execucao - timezone.now()).total_seconds(), 0),
        )
        try:
            while ConsolidaTemposERPScheduler._running:
                espera = (proxima_execucao - timezone.now()).total_seconds()
                if espera > 0:
                    time.sleep(min(espera, 60))
                    continue

                inicio_ciclo = time.time()
                close_old_connections()
                with connections["default"].cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('application_name', 'sigma-consolida-tempos', false)"
                    )
                marcar_ciclo_inicio(SERVICE_CODIGO)
                erro_ciclo = ""
                try:
                    criados = gerar_cortes_tempos_erp()
                    if criados:
                        print(f"[CONSOLIDA_TEMPOS_ERP] Pacotes criados: {criados}")
                except Exception as erro:
                    erro_ciclo = str(erro)
                    logger.exception("Erro na consolidação de tempos ERP")
                finally:
                    proxima_execucao = _proximo_horario_agendado(timezone.now())
                    marcar_ciclo_fim(
                        SERVICE_CODIGO,
                        time.time() - inicio_ciclo,
                        max((proxima_execucao - timezone.now()).total_seconds(), 0),
                        erro_ciclo,
                    )
                    connections.close_all()
        finally:
            ConsolidaTemposERPScheduler._running = False
            marcar_service_parado(SERVICE_CODIGO)


def start_consolida_tempos_erp_scheduler():
    if not ConsolidaTemposERPScheduler._running:
        ConsolidaTemposERPScheduler().start()
