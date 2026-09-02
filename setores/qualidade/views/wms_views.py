import json
import threading
from datetime import timedelta

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import close_old_connections, connections, transaction
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from producao.services.status import ciclo_service, marcar_atividade_service, registrar_service
from producao.utils.codificacao import get_response_text, safe_str
from setores.qualidade.models.estrutura import WMS_IntegraçãoOP
from SIGMA.autorizacao import permissao_requerida

PROCESSAMENTO_WMS_LOCK = threading.Lock()
TEMPO_LIMITE_CICLO_SEGUNDOS = 1800
WEBSERVICE_TIMEOUT_SEGUNDOS = 180
SERVICE_CODIGO = "fila_wms_integracoes"
SERVICE_NOME = "Fila WMS Integrações"

registrar_service(
    SERVICE_CODIGO,
    SERVICE_NOME,
    None,
    "Processa a fila assíncrona de integrações WMS.",
    TEMPO_LIMITE_CICLO_SEGUNDOS,
)


# Só libera envio de registros sem reunião ou de reuniões já fechadas.
def integracoes_wms_enviaveis(queryset):
    return queryset.filter(Q(reuniao__isnull=True) | Q(reuniao__data_hora_fim__isnull=False))


# Reserva pendências com lock no banco para evitar dois processos enviando o mesmo registro.
def reservar_integracoes_wms_para_envio(queryset):
    with transaction.atomic():
        candidatos = list(
            integracoes_wms_enviaveis(queryset)
            .filter(status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO)
            .order_by("id")
            .values_list("id", "codemp", "lote")
        )
        if not candidatos:
            print("[WMS] Reserva solicitada. Nenhum ID elegível encontrado.")
            return []

        # Preserva ordem por lote: um ajuste mais recente do mesmo lote
        # (ex.: baixas sucessivas do mesmo lote na V3, cada uma com um novo
        # saldo) só pode ser enviado depois que o anterior for integrado —
        # senão um reprocessamento fora de ordem pode regredir o saldo no WMS.
        vistos_nesta_reserva = set()
        ids_elegiveis = []
        for id_, codemp, lote in candidatos:
            chave = (codemp, lote)
            if chave in vistos_nesta_reserva:
                continue
            anterior_pendente = WMS_IntegraçãoOP.objects.filter(
                codemp=codemp,
                lote=lote,
                status__in=[
                    WMS_IntegraçãoOP.Status.NAO_INTEGRADO,
                    WMS_IntegraçãoOP.Status.PROCESSANDO,
                ],
                id__lt=id_,
            ).exists()
            if anterior_pendente:
                vistos_nesta_reserva.add(chave)
                continue
            ids_elegiveis.append(id_)
            vistos_nesta_reserva.add(chave)

        if not ids_elegiveis:
            print("[WMS] Reserva solicitada. Nenhum ID elegível após respeitar ordem por lote.")
            return []

        ids = list(
            WMS_IntegraçãoOP.objects.filter(
                id__in=ids_elegiveis, status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO
            )
            .select_for_update(skip_locked=True)
            .order_by("id")
            .values_list("id", flat=True)
        )
        print(f"[WMS] Reserva solicitada. IDs encontrados: {ids}")
        if not ids:
            return []

        WMS_IntegraçãoOP.objects.filter(
            id__in=ids, status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO
        ).update(
            status=WMS_IntegraçãoOP.Status.PROCESSANDO,
            log="Aguardando processamento background",
            data_hora=timezone.now(),
        )
        print(f"[WMS] IDs reservados como Processando: {ids}")
        return ids


# Devolve para pendente registros que ficaram presos após timeout da thread da fila.
def liberar_integracoes_wms_processando_antigas(idade_segundos=None):
    queryset = WMS_IntegraçãoOP.objects.filter(status=WMS_IntegraçãoOP.Status.PROCESSANDO)
    if idade_segundos is not None:
        queryset = queryset.filter(data_hora__lt=timezone.now() - timedelta(seconds=idade_segundos))

    return queryset.update(
        status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO,
        log="Processamento anterior interrompido. Disponível para novo envio.",
        data_hora=timezone.now(),
    )


# Remove registros já integrados há mais de 30 dias, fora do ciclo de
# carregamento da tela (o GET da listagem não pode ter efeito colateral).
def limpar_integracoes_wms_antigas():
    trinta_dias_atras = timezone.now() - timedelta(days=30)
    return WMS_IntegraçãoOP.objects.filter(
        status=WMS_IntegraçãoOP.Status.INTEGRADO, data_hora__lt=trinta_dias_atras
    ).delete()[0]


# Processa em background os IDs recebidos; se IDs vierem vazios, busca lotes até zerar a fila.
def processar_integracoes_wms_background(ids=None):
    close_old_connections()
    print(f"[WMS] Thread iniciada. IDs recebidos: {ids}")
    try:
        if ids is not None and not ids:
            print("[WMS] Thread encerrada: lista de IDs vazia.")
            return 0, 0

        if not PROCESSAMENTO_WMS_LOCK.acquire(blocking=False):
            print("[WMS] Thread bloqueada: já existe processamento em andamento.")
            if ids is not None:
                WMS_IntegraçãoOP.objects.filter(
                    id__in=ids, status=WMS_IntegraçãoOP.Status.PROCESSANDO
                ).update(
                    status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO,
                    log="Aguardando processamento background",
                    data_hora=timezone.now(),
                )
            return 0, 0

        with ciclo_service(SERVICE_CODIGO):
            sucesso = 0
            falha = 0
            ids_tentados_no_ciclo = set()
            try:
                while True:
                    reservados_ids = ids
                    if ids is None:
                        queryset_pendentes = WMS_IntegraçãoOP.objects.order_by("id")
                        if ids_tentados_no_ciclo:
                            queryset_pendentes = queryset_pendentes.exclude(
                                id__in=ids_tentados_no_ciclo
                            )
                        reservados_ids = reservar_integracoes_wms_para_envio(queryset_pendentes)

                    if not reservados_ids:
                        print("[WMS] Nenhuma integração reservada para processar.")
                        break

                    ids_tentados_no_ciclo.update(reservados_ids)
                    pendencias = WMS_IntegraçãoOP.objects.filter(
                        id__in=reservados_ids, status=WMS_IntegraçãoOP.Status.PROCESSANDO
                    ).order_by("id")
                    print(
                        f"[WMS] Integrações em Processando localizadas: {list(pendencias.values_list('id', flat=True))}"
                    )
                    for pendencia in pendencias:
                        marcar_atividade_service(SERVICE_CODIGO, WEBSERVICE_TIMEOUT_SEGUNDOS)
                        print(f"[WMS] Processando integração {pendencia.id}.")
                        ok, _ = _processar_envio_wms(pendencia, reservar=False)
                        if ok:
                            sucesso += 1
                        else:
                            falha += 1

                    if ids is not None:
                        break
            finally:
                PROCESSAMENTO_WMS_LOCK.release()

            print(f"[WMS] Thread finalizada. Sucessos={sucesso} Falhas={falha}")
            return sucesso, falha
    finally:
        connections.close_all()


# Apenas inicia a thread; quem chamou já decidiu quais IDs serão processados.
def disparar_envio_wms(ids=None):
    print(f"[WMS] Disparando thread para IDs: {ids}")
    threading.Thread(target=processar_integracoes_wms_background, args=(ids,), daemon=True).start()


# Fluxo alto nível: reserva pendentes elegíveis e dispara a thread.
def disparar_integracoes_wms_pendentes():
    if PROCESSAMENTO_WMS_LOCK.locked():
        return

    ids = reservar_integracoes_wms_para_envio(WMS_IntegraçãoOP.objects.order_by("id"))
    if ids:
        disparar_envio_wms(ids)


# Monta o SKU esperado pela API WMS: produto-derivação quando houver derivação.
def _sku_wms(pendencia):
    codpro = str(pendencia.codpro or "").strip()
    codder = "" if pendencia.codder is None else str(pendencia.codder).strip()
    return f"{codpro}-{codder}" if codder else codpro


# Define o endpoint WMS pelo tipo de envio gravado na pendência.
def _endpoint_wms(pendencia):
    endpoints = {
        WMS_IntegraçãoOP.TIPO_NOVO_LOTE: "rec_ska",
        WMS_IntegraçãoOP.TIPO_AJUSTE: "ajuste_estoque",
    }
    return endpoints.get(pendencia.tipo_envio, "rec_ska")


# Payload do endpoint rec_ska, usado quando o WMS precisa criar/receber um novo lote.
def _payload_novo_lote_wms(pendencia):
    return {
        "WHSEID": "WMWHSE1",
        "STORERKEY": "00001",
        "RECEIPTKEY": f"{pendencia.origem}-{pendencia.op}",
        "TOLOC": pendencia.local,
        "SKU": _sku_wms(pendencia),
        "QTYRECEIVED": float(pendencia.quantidade),
        "TOID": str(pendencia.palete),
        "LOTTABLE01": str(pendencia.lote),
        "USER": settings.WMS_XC_API_USER,
    }


# Payload do endpoint ajuste_estoque, usado para acertar saldo de lote já existente no WMS.
# MOTBLOQ/FLAGBLOQ fazem parte do contrato de bloqueio de qualidade do WMS
# (área vermelha): FLAGBLOQ "0" desbloqueia a quantidade ajustada e MOTBLOQ
# é o motivo do bloqueio. Por enquanto o SIGMA não decide bloqueio nem
# expõe motivo configurável, por isso os dois vão sempre com o mesmo valor
# fixo em todo ajuste de estoque.
def _payload_ajuste_wms(pendencia):
    return {
        "ARMAZEM": "WMWHSE1",
        "LOTE": str(pendencia.lote),
        "PALETE": str(pendencia.palete),
        "QTD_AJUSTADA": float(pendencia.quantidade),
        "SKU": _sku_wms(pendencia),
        "USUARIO": settings.WMS_XC_API_USER,
        "MOTBLOQ": "",
        "FLAGBLOQ": "0",
    }


# Escolhe o formato do JSON conforme o tipo de envio da pendência.
def _payload_wms(pendencia):
    if pendencia.tipo_envio == WMS_IntegraçãoOP.TIPO_AJUSTE:
        return _payload_ajuste_wms(pendencia)
    return _payload_novo_lote_wms(pendencia)


# Tela de consulta/manutenção manual das pendências WMS.
@login_required
def integracao_wms_view(request):
    filial_logada = getattr(request.user, "filial", None)
    empresa_logada = getattr(filial_logada, "empresa", None)
    codemp_usuario = getattr(empresa_logada, "codemp", None)

    # Filtro de busca
    search_query = request.GET.get("search", "")
    if search_query:
        # Se a busca contiver "/", tentamos converter para formato de data do banco (YYYY-MM-DD)
        search_date = None
        if "/" in search_query:
            try:
                from datetime import datetime

                search_date = datetime.strptime(search_query, "%d/%m/%Y").strftime("%Y-%m-%d")
            except ValueError:
                pass

        query = (
            Q(codemp__icontains=search_query)
            | Q(origem__icontains=search_query)
            | Q(op__icontains=search_query)
            | Q(codpro__icontains=search_query)
            | Q(codder__icontains=search_query)
            | Q(lote__icontains=search_query)
            | Q(palete__icontains=search_query)
            | Q(quantidade__icontains=search_query)
            | Q(codigo_integrador__icontains=search_query)
            | Q(local__icontains=search_query)
            | Q(tipo_envio__icontains=search_query)
            | Q(log__icontains=search_query)
            | Q(data_hora__icontains=search_query)
        )

        if search_date:
            query |= Q(data_hora__icontains=search_date)

        pendencias_list = (
            WMS_IntegraçãoOP.objects.select_related("reuniao").filter(query).order_by("-id")
        )
    else:
        pendencias_list = WMS_IntegraçãoOP.objects.select_related("reuniao").all().order_by("-id")

    # Não-staff só vê pendências da própria empresa; staff vê todas (mesma
    # regra usada em consulta_lote/liberar_area_vermelha desta app).
    if not request.user.is_staff:
        if codemp_usuario:
            pendencias_list = pendencias_list.filter(codemp=codemp_usuario)
        else:
            pendencias_list = pendencias_list.none()

    # Mesma trava de ordem por lote usada em reservar_integracoes_wms_para_envio:
    # uma pendência de status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO não é enviável ainda se existir outra mais
    # antiga do mesmo (codemp, lote) também pendente ou em processamento.
    anterior_do_mesmo_lote = WMS_IntegraçãoOP.objects.filter(
        codemp=OuterRef("codemp"),
        lote=OuterRef("lote"),
        status__in=[WMS_IntegraçãoOP.Status.NAO_INTEGRADO, WMS_IntegraçãoOP.Status.PROCESSANDO],
        id__lt=OuterRef("id"),
    )
    pendencias_list = pendencias_list.annotate(bloqueado_por_lote=Exists(anterior_do_mesmo_lote))

    paginator = Paginator(pendencias_list, 30)
    page_number = request.GET.get("page")
    pendencias = paginator.get_page(page_number)
    # Botões de exclusão visíveis a quem a rota autoriza (staff/superusuário
    # pelo bypass ou portador da permissão unificada das filas).
    pode_excluir_pendencias = (
        request.user.is_staff
        or request.user.is_superuser
        or request.user.has_perm("producao.pode_excluir_pendencias_integracao")
    )
    return render(
        request,
        "setores/qualidade/integracao_wms.html",
        {
            "pendencias": pendencias,
            "search_query": search_query,
            "pode_excluir_pendencias": pode_excluir_pendencias,
        },
    )


# Exclusões seguem o padrão unificado de filas: a permissão declarativa é
# producao.pode_excluir_pendencias_integracao (fila WMS é uma integração);
# quem recebe a permissão exclui — não há mais guard interno adicional.
@permissao_requerida("producao.pode_excluir_pendencias_integracao")
@require_POST
def excluir_integracao_wms(request, pk):
    # Mesmo padrão dos envios: não-staff só exclui pendência da própria
    # empresa, mesmo sabendo o pk de outra.
    filial_logada = getattr(request.user, "filial", None)
    empresa_logada = getattr(filial_logada, "empresa", None)
    codemp_usuario = getattr(empresa_logada, "codemp", None)
    queryset = WMS_IntegraçãoOP.objects.all()
    if not request.user.is_staff:
        queryset = queryset.filter(codemp=codemp_usuario) if codemp_usuario else queryset.none()
    pendencia = get_object_or_404(queryset, pk=pk)
    if pendencia.status == WMS_IntegraçãoOP.Status.PROCESSANDO:
        messages.error(request, f"Integração {pk} está em processamento e não pode ser excluída.")
        return redirect("qualidade:integracao_wms")
    if pendencia.status != WMS_IntegraçãoOP.Status.NAO_INTEGRADO:
        messages.error(request, f"Integração {pk} já foi integrada.")
        return redirect("qualidade:integracao_wms")

    pendencia.delete()
    messages.success(request, f"Integração {pk} excluída com sucesso.")
    return redirect("qualidade:integracao_wms")


@permissao_requerida("producao.pode_excluir_pendencias_integracao")
@require_POST
def excluir_todas_integracoes_wms(request):
    filial_logada = getattr(request.user, "filial", None)
    empresa_logada = getattr(filial_logada, "empresa", None)
    codemp_usuario = getattr(empresa_logada, "codemp", None)

    pendentes_do_escopo = WMS_IntegraçãoOP.objects.filter(
        status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO
    )
    if not request.user.is_staff:
        pendentes_do_escopo = (
            pendentes_do_escopo.filter(codemp=codemp_usuario)
            if codemp_usuario
            else pendentes_do_escopo.none()
        )

    total = pendentes_do_escopo.count()
    if total == 0:
        messages.info(request, "Não há integrações WMS locais para excluir.")
        return redirect("qualidade:integracao_wms")

    pendentes_do_escopo.delete()

    messages.success(request, f"Todas as {total} integrações foram excluídas com sucesso.")
    return redirect("qualidade:integracao_wms")


# Dispara manualmente uma única pendência WMS selecionada na tela.
@login_required
@require_POST
def enviar_integracao_wms(request, pk):
    if PROCESSAMENTO_WMS_LOCK.locked():
        messages.warning(request, "Já existe um processamento WMS em andamento.")
        return redirect("qualidade:integracao_wms")

    pendencia = get_object_or_404(WMS_IntegraçãoOP, pk=pk)

    filial_logada = getattr(request.user, "filial", None)
    empresa_logada = getattr(filial_logada, "empresa", None)
    codemp_usuario = getattr(empresa_logada, "codemp", None)
    if not request.user.is_staff and pendencia.codemp != codemp_usuario:
        messages.error(request, "Você não tem permissão para enviar integração de outra empresa.")
        return redirect("qualidade:integracao_wms")

    if pendencia.status == WMS_IntegraçãoOP.Status.INTEGRADO:
        messages.warning(request, f"Integração {pk} já foi integrada anteriormente.")
        return redirect("qualidade:integracao_wms")
    if pendencia.status == WMS_IntegraçãoOP.Status.PROCESSANDO:
        messages.warning(request, f"Integração {pk} já está em processamento.")
        return redirect("qualidade:integracao_wms")
    ids = reservar_integracoes_wms_para_envio(WMS_IntegraçãoOP.objects.filter(pk=pk))
    if not ids:
        messages.warning(request, f"Integração {pk} não está disponível para envio.")
        return redirect("qualidade:integracao_wms")

    disparar_envio_wms(ids)
    messages.info(request, f"Processamento WMS iniciado para a integração {pk}.")

    return redirect("qualidade:integracao_wms")


# Dispara manualmente todas as pendências WMS disponíveis.
@login_required
@require_POST
def enviar_todas_integracoes_wms(request):
    if PROCESSAMENTO_WMS_LOCK.locked():
        messages.warning(request, "Já existe um processamento WMS em andamento.")
        return redirect("qualidade:integracao_wms")

    filial_logada = getattr(request.user, "filial", None)
    empresa_logada = getattr(filial_logada, "empresa", None)
    codemp_usuario = getattr(empresa_logada, "codemp", None)

    pendentes = WMS_IntegraçãoOP.objects.order_by("id")
    if not request.user.is_staff:
        if codemp_usuario:
            pendentes = pendentes.filter(codemp=codemp_usuario)
        else:
            pendentes = pendentes.none()

    ids = reservar_integracoes_wms_para_envio(pendentes)
    if not ids:
        messages.info(request, "Nenhuma integração pendente.")
    else:
        disparar_envio_wms(ids)
        messages.info(request, "Processamento WMS em background iniciado.")

    return redirect("qualidade:integracao_wms")


# Processamento síncrono de uma lista específica, usado por chamadas internas/serviços.
def processar_envio_integracoes_ids(ids):
    reservados_ids = reservar_integracoes_wms_para_envio(
        WMS_IntegraçãoOP.objects.filter(id__in=ids, status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO)
    )
    sucesso, falha = processar_integracoes_wms_background(reservados_ids)
    return sucesso, falha, len(reservados_ids)


# Processamento síncrono de todas as pendências, usado por chamadas internas/serviços.
def processar_envio_todas_integracoes():
    reservados_ids = reservar_integracoes_wms_para_envio(
        WMS_IntegraçãoOP.objects.filter(status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO)
    )
    sucesso, falha = processar_integracoes_wms_background(reservados_ids)
    return sucesso, falha, len(reservados_ids)


# Atualiza o status final sem reabrir registro que outro processo já marcou como sucesso.
def _registrar_resultado_wms(pendencia_id, sucesso, log):
    agora = timezone.now()
    if sucesso:
        WMS_IntegraçãoOP.objects.filter(pk=pendencia_id).update(
            status=WMS_IntegraçãoOP.Status.INTEGRADO,
            log=log,
            data_hora=agora,
        )
        return True

    atualizados = (
        WMS_IntegraçãoOP.objects.filter(pk=pendencia_id)
        .exclude(status=WMS_IntegraçãoOP.Status.INTEGRADO)
        .update(
            status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO,
            log=log,
            data_hora=agora,
        )
    )
    return bool(atualizados)


# Monta o payload, envia para a API WMS e registra sucesso/falha da pendência.
def _processar_envio_wms(pendencia, reservar=True):
    if reservar:
        # Quando chamado direto, reserva o registro antes de enviar.
        reservado = WMS_IntegraçãoOP.objects.filter(
            pk=pendencia.pk, status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO
        ).update(
            status=WMS_IntegraçãoOP.Status.PROCESSANDO,
            log="Processando integração WMS",
            data_hora=timezone.now(),
        )
        if not reservado:
            return False, f"Integração {pendencia.pk} não está disponível para processamento."
    elif pendencia.status != WMS_IntegraçãoOP.Status.PROCESSANDO:
        return False, f"Integração {pendencia.pk} não está reservada para processamento."

    try:
        # Este JSON é o corpo real enviado para a API, por isso o print usa payload_json.
        payload = _payload_wms(pendencia)

        url_api = f"{settings.WMS_XC_API_URL}{_endpoint_wms(pendencia)}"
        payload_json = json.dumps(payload, ensure_ascii=False)
        print(f"[WMS] Enviando integração {pendencia.pk}: {payload_json}")
        print(f"[WMS] POST integração {pendencia.pk}: {url_api}")

        response = requests.post(
            url_api,
            data=payload_json.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=WEBSERVICE_TIMEOUT_SEGUNDOS,
        )
        # O WMS pode retornar HTTP 200/201 com erro no corpo, então o texto também é validado.
        response_text = get_response_text(response)
        print(
            f"[WMS] Retorno integração {pendencia.pk}: status_http={response.status_code} body={response_text}"
        )

        if response.status_code in (200, 201) and "Erro" not in response_text:
            _registrar_resultado_wms(pendencia.pk, True, f"Sucesso: {response_text}")
            return True, f"Sucesso: {response_text}"
        else:
            if response.status_code in (200, 201):
                log = f"Erro no retorno da API: {response_text}"
            else:
                log = f"Erro API ({response.status_code}): {response_text}"

            _registrar_resultado_wms(pendencia.pk, False, log)
            return False, f"Falha na integração da integração {pendencia.pk}: {response_text}"
    except Exception as e:
        print(f"[WMS] Exceção integração {pendencia.pk}: {safe_str(e)}")
        _registrar_resultado_wms(pendencia.pk, False, f"Erro na requisição: {safe_str(e)}")
        return (
            False,
            f"Falha na comunicação com a API para a integração {pendencia.pk}: {safe_str(e)}",
        )
