import json
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Final
from xml.sax.saxutils import escape

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import close_old_connections, connections, transaction
from django.db.models import Exists, OuterRef, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from producao.models.estrutura import Apontamento
from producao.services.altera_apontamento import (
    buscar_dados_lote_erp_logic,
    corrigir_quantidade_lote,
)
from producao.services.sapiens import enviar_soap_sapiens
from producao.services.status import ciclo_service, marcar_atividade_service, registrar_service
from producao.utils.codificacao import get_response_text, safe_str
from producao.utils.sapiens_soap import escapar_cdata_sapiens
from SIGMA.autorizacao import permissao_requerida
from SIGMA.segredos import mascarar_segredos

logger = logging.getLogger(__name__)
PROCESSAMENTO_LOGS_LOCK = threading.Lock()
TEMPO_LIMITE_CICLO_SEGUNDOS = 1800
WEBSERVICE_TIMEOUT_SEGUNDOS = 180
MAX_WORKERS_LOGS_APONTAMENTOS = max(int(os.getenv("LOGS_APONTAMENTOS_MAX_WORKERS", "10")), 1)
SERVICE_CODIGO = "fila_logs_apontamentos"
SERVICE_NOME = "Fila Log Apontamentos"

registrar_service(
    SERVICE_CODIGO,
    SERVICE_NOME,
    None,
    "Processa a fila assíncrona de logs de apontamentos.",
    TEMPO_LIMITE_CICLO_SEGUNDOS,
)

# Fonte única da busca (consulta e instrução da tela): a consulta varre
# exatamente estes campos e a instrução exibida sai dos mesmos rótulos —
# teste anti-divergência em producao/tests/test_busca_logs.py impede que
# as duas pontas voltem a divergir.
CAMPOS_BUSCA: Final[tuple[tuple[str, str], ...]] = (
    ("codemp", "empresa"),
    ("origem", "origem"),
    ("numorp", "OP"),
    ("codetg", "estágio"),
    ("seqrot", "sequência"),
    ("numcad", "operador"),
    ("qtdre1", "quantidade"),
    ("qtdrfg", "quantidade refugada"),
    ("lote", "lote"),
    ("codigo_integrador", "código integrador"),
    ("recurso__codigo", "recurso"),
    ("recurso__descricao", "descrição do recurso"),
    ("recurso__centro_recurso__codigo", "centro de recurso"),
    ("recurso__centro_recurso__descricao", "descrição do centro"),
    ("bobina", "bobina"),
    ("datmov", "data do movimento"),
    ("hormov", "hora do movimento"),
    ("log", "log"),
    ("usuario__username", "usuário"),
    ("data_hora", "data/hora"),
    ("origem_peso", "origem do peso"),
)

# Rótulos dos campos para a instrução da tela (placeholder do template).
ROTULOS_BUSCA = ", ".join(rotulo for _campo, rotulo in CAMPOS_BUSCA)


def consulta_de_busca(termo: str) -> Q:
    """Q disjunto com um `icontains` por campo de `CAMPOS_BUSCA`."""
    consulta = Q()
    for campo, _rotulo in CAMPOS_BUSCA:
        consulta |= Q(**{f"{campo}__icontains": termo})
    return consulta


def reservar_apontamentos_para_envio(queryset, um_por_chave=False, chaves_ignoradas=None):
    # Reserva de forma atômica os pendentes do queryset, marcando status=PROCESSANDO para evitar captura duplicada.
    chaves_ignoradas = chaves_ignoradas or set()
    with transaction.atomic():
        pendentes = list(
            queryset.filter(status=Apontamento.Status.NAO_INTEGRADO)
            .select_for_update(skip_locked=True)
            .order_by("id")
            .values("id", "codemp", "origem", "numorp", "codetg", "seqrot")
        )

        if um_por_chave:
            chaves_em_processamento = {
                (item["codemp"], item["origem"], item["numorp"], item["codetg"], item["seqrot"])
                for item in Apontamento.objects.filter(
                    status=Apontamento.Status.PROCESSANDO
                ).values("codemp", "origem", "numorp", "codetg", "seqrot")
            }
            ids = []
            chaves_reservadas = set()
            for item in pendentes:
                chave = (
                    item["codemp"],
                    item["origem"],
                    item["numorp"],
                    item["codetg"],
                    item["seqrot"],
                )
                if (
                    chave in chaves_ignoradas
                    or chave in chaves_em_processamento
                    or chave in chaves_reservadas
                ):
                    continue
                ids.append(item["id"])
                chaves_reservadas.add(chave)
        else:
            ids = [item["id"] for item in pendentes]

        if not ids:
            return Apontamento.objects.none()

        Apontamento.objects.filter(id__in=ids, status=Apontamento.Status.NAO_INTEGRADO).update(
            status=Apontamento.Status.PROCESSANDO,
            log="Aguardando processamento background",
            data_hora=timezone.now(),
        )

    return Apontamento.objects.filter(id__in=ids, status=Apontamento.Status.PROCESSANDO).order_by(
        "id"
    )


def processar_logs_pendentes(ids=None):
    # Motor único do background: sem ids processa todos os pendentes; com ids processa só os já reservados.
    close_old_connections()
    try:
        if ids is not None and not ids:
            return 0, 0

        if not PROCESSAMENTO_LOGS_LOCK.acquire(blocking=False):
            if ids is not None:
                Apontamento.objects.filter(
                    id__in=ids, status=Apontamento.Status.PROCESSANDO
                ).update(
                    status=Apontamento.Status.NAO_INTEGRADO,
                    log="Aguardando processamento background",
                    data_hora=timezone.now(),
                )
            return 0, 0

        with ciclo_service(SERVICE_CODIGO):
            sucessos_total = 0
            erros_total = 0
            chaves_falhadas_lote = set()

            try:
                while True:
                    if ids is None:
                        apontamentos = reservar_apontamentos_para_envio(
                            Apontamento.objects.order_by("id"),
                            um_por_chave=True,
                            chaves_ignoradas=chaves_falhadas_lote,
                        )
                    else:
                        apontamentos = Apontamento.objects.filter(
                            id__in=ids, status=Apontamento.Status.PROCESSANDO
                        ).order_by("id")

                    if not apontamentos.exists():
                        break

                    if ids is None:
                        grupos_por_chave = {}
                        for item in apontamentos.values(
                            "id", "codemp", "origem", "numorp", "codetg", "seqrot"
                        ):
                            chave = (
                                item["codemp"],
                                item["origem"],
                                item["numorp"],
                                item["codetg"],
                                item["seqrot"],
                            )
                            grupos_por_chave.setdefault(chave, []).append(item["id"])

                        grupos_ids = list(grupos_por_chave.values())
                        max_workers = min(len(grupos_ids), MAX_WORKERS_LOGS_APONTAMENTOS)

                        if max_workers <= 1:
                            sucessos, erros, chaves_falhadas = (
                                executar_envio_logs_com_conexao_limpa(apontamentos)
                            )
                            sucessos_total += sucessos
                            erros_total += erros
                            chaves_falhadas_lote.update(chaves_falhadas)
                        else:
                            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                                futures = []
                                for grupo_ids in grupos_ids:
                                    grupo_qs = Apontamento.objects.filter(
                                        id__in=grupo_ids, status=Apontamento.Status.PROCESSANDO
                                    ).order_by("id")
                                    futures.append(
                                        executor.submit(
                                            executar_envio_logs_com_conexao_limpa, grupo_qs
                                        )
                                    )

                                for future in as_completed(futures):
                                    sucessos, erros, chaves_falhadas = future.result()
                                    sucessos_total += sucessos
                                    erros_total += erros
                                    chaves_falhadas_lote.update(chaves_falhadas)
                    else:
                        sucessos, erros, _ = executar_envio_logs_com_conexao_limpa(apontamentos)
                        sucessos_total += sucessos
                        erros_total += erros

                    if ids is not None:
                        break
            finally:
                PROCESSAMENTO_LOGS_LOCK.release()

            return sucessos_total, erros_total
    finally:
        connections.close_all()


def disparar_envio_apontamentos(ids=None):
    # Disparo único de thread para envio: sem ids envia todos os pendentes, com ids envia só os reservados.
    threading.Thread(target=processar_logs_pendentes, args=(ids,), daemon=True).start()


def _codemp_usuario(request):
    """Deriva o codemp do usuário logado; mesma fonte usada em toda a fila de apontamentos."""
    empresa_usuario = getattr(getattr(request.user, "filial", None), "empresa", None)
    return getattr(empresa_usuario, "codemp", None)


def liberar_apontamentos_processando_antigos(idade_segundos=None):
    queryset = Apontamento.objects.filter(status=Apontamento.Status.PROCESSANDO)
    if idade_segundos is not None:
        queryset = queryset.filter(data_hora__lt=timezone.now() - timedelta(seconds=idade_segundos))

    total = queryset.update(
        status=Apontamento.Status.NAO_INTEGRADO,
        log="Processamento anterior interrompido. Disponível para novo envio.",
        data_hora=timezone.now(),
    )
    return total


def enviar_movimentar_op(
    usuario,
    senha,
    codemp,
    codori,
    numorp,
    codetg,
    seqrot,
    numcad,
    qtdre1,
    qtdrfg,
    codlot=None,
    datmov=None,
    hormov=None,
    num_bobina=None,
    codigo_integrador=None,
):
    # Envia o SOAP de apontamento ao ERP e devolve o XML de resposta bruto.

    sapiens_base = settings.SAPIENS_URL_BASE
    url = f"{sapiens_base}/g5-senior-services/sapiens_Synccustom.senior.man.producao"

    dados = {
        "wacao": "APONTAR-OP",
        "empresa": str(codemp),
        "CodOri": str(codori),
        "NumOrp": str(numorp),
        "NumCad": str(numcad),
        "CodEtg": str(codetg),
        "SeqRot": str(seqrot),
        "QtdRe1": str(qtdre1),
        "QtdRfg": str(qtdrfg),
        "DatMov": str(datmov),
        "HorMov": str(hormov),
        "NumBob": str(num_bobina) if num_bobina not in [None, "", "None"] else "0",
        "NumMaq": str(codigo_integrador),
    }

    if codlot is not None:
        dados["CodLot"] = str(codlot)

    json_dados = json.dumps(dados, ensure_ascii=False)

    envelope = f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<soapenv:Envelope xmlns:soapenv="http://www.w3.org/2003/05/soap-envelope"
                  xmlns:ser="http://services.senior.com.br">
  <soapenv:Header/>
  <soapenv:Body>
    <ser:Apontamentos>
      <user>{escape(str(usuario))}</user>
      <password>{escape(str(senha))}</password>
      <encryption>0</encryption>
      <parameters>
        <flowInstanceID></flowInstanceID>
        <flowName></flowName>

        <tabelaEntradas>
            <chave>wdados</chave>
            <valor><![CDATA[{escapar_cdata_sapiens(json_dados)}]]></valor>
        </tabelaEntradas>

      </parameters>
    </ser:Apontamentos>
  </soapenv:Body>
</soapenv:Envelope>"""
    logger.debug("SOAP enviado (Apontamentos): %s", mascarar_segredos(envelope))

    # validar_status=False: a leitura de waRetorno abaixo decide integrado/erro,
    # inclusive para HTTP != 200 (mesma resposta de negócio do Sapiens).
    r = enviar_soap_sapiens(
        url, envelope, timeout=WEBSERVICE_TIMEOUT_SEGUNDOS, validar_status=False
    )

    retorno = get_response_text(r)
    logger.debug("Resposta SOAP (Apontamentos): %s", mascarar_segredos(retorno))

    return retorno


def _registrar_resultado_apontamento(apontamento_id, status, log):
    # Mascara o mais perto possivel da gravacao: cobre qualquer chamador atual ou futuro.
    log = mascarar_segredos(log)
    agora = timezone.now()
    if status == Apontamento.Status.INTEGRADO:
        Apontamento.objects.filter(pk=apontamento_id).update(
            status=Apontamento.Status.INTEGRADO,
            log=log,
            data_hora=agora,
        )
        return True

    atualizados = (
        Apontamento.objects.filter(pk=apontamento_id)
        .exclude(status=Apontamento.Status.INTEGRADO)
        .update(
            status=Apontamento.Status.NAO_INTEGRADO,
            log=log,
            data_hora=agora,
        )
    )
    return bool(atualizados)


def executar_envio_logs(pendentes):
    """
    Lógica centralizada para processar uma lista de apontamentos pendentes.
    """
    sucessos = 0
    erros = 0

    # Mantém rastreio de chaves que falharam para não tentar as próximas
    chaves_com_erro = set()

    for apontamento in pendentes:
        marcar_atividade_service(SERVICE_CODIGO, WEBSERVICE_TIMEOUT_SEGUNDOS)
        chave = (
            apontamento.codemp,
            apontamento.origem,
            apontamento.numorp,
            apontamento.codetg,
            apontamento.seqrot,
        )

        # Se já houve erro nesta chave anteriormente neste lote, devolve para pendente sem reenviar agora.
        if chave in chaves_com_erro:
            _registrar_resultado_apontamento(
                apontamento.id,
                Apontamento.Status.NAO_INTEGRADO,
                "Aguardando integração log anterior",
            )
            erros += 1
            continue

        # Verifica se existe algum log mais antigo (ID menor) não integrado para esta mesma chave
        # Garante a ordem cronológica mesmo em envios individuais ou disparos manuais
        anterior_pendente = Apontamento.objects.filter(
            codemp=apontamento.codemp,
            origem=apontamento.origem,
            numorp=apontamento.numorp,
            codetg=apontamento.codetg,
            seqrot=apontamento.seqrot,
            status=Apontamento.Status.NAO_INTEGRADO,
            id__lt=apontamento.id,
        ).exists()

        if anterior_pendente:
            _registrar_resultado_apontamento(
                apontamento.id,
                Apontamento.Status.NAO_INTEGRADO,
                "Aguardando integração log anterior",
            )
            chaves_com_erro.add(chave)  # Bloqueia os próximos deste lote também
            erros += 1
            continue

        # Tenta usar a data/hora já registrada no apontamento para manter igualdade em múltiplas bobinas
        # Se não houver, ou se for um reenvio manual que exija atualização, gera agora
        nova_data = apontamento.datmov
        nova_hora = apontamento.hormov
        agora = timezone.localtime(timezone.now())

        if not nova_data or not nova_hora:
            nova_data = agora.strftime("%d/%m/%Y")
            nova_hora = agora.strftime("%H:%M:%S")

        try:
            resposta = enviar_movimentar_op(
                usuario=settings.SAPIENS_USERNAME,
                senha=settings.SAPIENS_PASSWORD,
                codemp=apontamento.codemp,
                codori=apontamento.origem,
                numorp=apontamento.numorp,
                codetg=apontamento.codetg,
                seqrot=apontamento.seqrot,
                numcad=apontamento.numcad,
                qtdre1=apontamento.qtdre1,
                qtdrfg=apontamento.qtdrfg,
                codlot=apontamento.lote,
                datmov=nova_data,
                hormov=nova_hora,
                num_bobina=apontamento.bobina,
                codigo_integrador=apontamento.codigo_integrador,
            )

            status_apont = Apontamento.Status.NAO_INTEGRADO
            log_apont = resposta

            m_status = re.search(
                r"<waRetorno>(.*?)</waRetorno>", resposta, re.DOTALL | re.IGNORECASE
            )
            if m_status:
                json_str_status = m_status.group(1)
                log_apont = json_str_status
                try:
                    data_status = json.loads(json_str_status)
                    if data_status.get("message") == "OK" or (
                        data_status.get("status") == "OK"
                        and data_status.get("message") == "Apontamento ja realizado"
                    ):
                        status_apont = Apontamento.Status.INTEGRADO
                except json.JSONDecodeError, TypeError:
                    if "Processado com sucesso" in resposta:
                        status_apont = Apontamento.Status.INTEGRADO

            _registrar_resultado_apontamento(apontamento.id, status_apont, log_apont)

            if status_apont == Apontamento.Status.INTEGRADO:
                sucessos += 1
            else:
                erros += 1
                chaves_com_erro.add(chave)

        except Exception as e:
            msg_erro = mascarar_segredos(
                f"Erro no processamento do log {apontamento.id}: {safe_str(e)}"
            )
            print(msg_erro)
            _registrar_resultado_apontamento(
                apontamento.id, Apontamento.Status.NAO_INTEGRADO, msg_erro
            )
            erros += 1
            chaves_com_erro.add(chave)

    return sucessos, erros, chaves_com_erro


def executar_envio_logs_com_conexao_limpa(pendentes):
    close_old_connections()
    try:
        return executar_envio_logs(pendentes)
    finally:
        connections.close_all()


@login_required
def buscar_dados_lote_erp(request):
    """
    Busca dados do lote no ERP (E900EOQ) para preencher o modal de correção.
    """
    if not (request.user.has_perm("producao.pode_corrigir_lote") or request.user.is_staff):
        return JsonResponse({"error": "Sem permissão para corrigir lotes."}, status=403)
    lote = request.GET.get("lote")
    data, status = buscar_dados_lote_erp_logic(lote, request.user)
    return JsonResponse(data, status=status)


@login_required
def logs_apontamentos(request):
    # Lógica de correção de lote se for POST
    if request.method == "POST" and "lote" in request.POST:
        if not (request.user.has_perm("producao.pode_corrigir_lote") or request.user.is_staff):
            messages.error(request, "Você não tem permissão para corrigir lotes.")
            return redirect("logs_apontamentos")

        lote_id = request.POST.get("lote")
        qtdre1 = request.POST.get("qtdre1")

        if not lote_id or qtdre1 is None:
            messages.error(request, "Lote e quantidade produzida são obrigatórios.")
        else:
            try:
                qtdre1 = float(qtdre1.replace(",", ".")) if qtdre1 else 0.0

                # Coleta parâmetros específicos do ERP se enviados pelo modal de correção
                erp_params = None
                if request.POST.get("seqeoq_erp"):
                    erp_params = {
                        "codemp": request.POST.get("codemp_erp"),
                        "codori": request.POST.get("codori_erp"),
                        "numorp": request.POST.get("numorp_erp"),
                        "codetg": request.POST.get("codetg_erp"),
                        "seqeoq": request.POST.get("seqeoq_erp"),
                        "numbob_erp": request.POST.get("numbob_erp"),
                        "qtd_original_linha": request.POST.get("qtd_original_linha"),
                        "qtd_total_lote": request.POST.get("qtd_total_lote"),
                        "tipo_ajuste": request.POST.get("tipo_ajuste"),
                        "acao_correcao": request.POST.get("acao_correcao"),
                    }

                success, logs_list = corrigir_quantidade_lote(
                    lote_id,
                    qtdre1,
                    request.user,
                    erp_params=erp_params,
                )
                if success:
                    for msg in logs_list:
                        messages.success(request, msg)
                else:
                    for msg in logs_list:
                        # Identifica se é erro ou apenas informação/sucesso parcial
                        if any(palavra in msg for palavra in ["Falha", "Erro", "Aviso"]):
                            messages.error(request, msg)
                        else:
                            # Mensagens que não são de erro são consideradas sucessos parciais
                            messages.success(request, msg)
            except ValueError:
                messages.error(request, "Quantidade inválida.")

        return redirect("logs_apontamentos")

    codemp_usuario = _codemp_usuario(request)
    queryset_base = Apontamento.objects.select_related(
        "recurso", "recurso__centro_recurso", "usuario"
    )
    if not request.user.is_staff:
        if codemp_usuario:
            queryset_base = queryset_base.filter(codemp=codemp_usuario)
        else:
            queryset_base = queryset_base.none()

    # Filtro de busca
    search_query = request.GET.get("search", "")
    if search_query:
        # Se for busca por lote (começa com L ou é número), converte para maiúsculas para o icontains
        if search_query.lower().startswith("l") or search_query.isdigit():
            search_query = search_query.upper()

        # Se a busca contiver "/", tentamos converter para formato de data do banco (YYYY-MM-DD)
        search_date = None
        if "/" in search_query:
            try:
                search_date = datetime.strptime(search_query, "%d/%m/%Y").strftime("%Y-%m-%d")
            except ValueError:
                pass

        query = consulta_de_busca(search_query)

        if search_date:
            query |= Q(data_hora__icontains=search_date) | Q(datmov__icontains=search_date)

        apontamentos_list = queryset_base.filter(query).order_by("-id")
    else:
        apontamentos_list = queryset_base.order_by(
            "-id"
        )  # Ordenar por ID decrescente para ver os últimos primeiro

    chave_mesmo_processamento = Apontamento.objects.filter(
        status=Apontamento.Status.PROCESSANDO,
        codemp=OuterRef("codemp"),
        origem=OuterRef("origem"),
        numorp=OuterRef("numorp"),
        codetg=OuterRef("codetg"),
        seqrot=OuterRef("seqrot"),
    )
    chave_com_pendente_anterior = Apontamento.objects.filter(
        status=Apontamento.Status.NAO_INTEGRADO,
        codemp=OuterRef("codemp"),
        origem=OuterRef("origem"),
        numorp=OuterRef("numorp"),
        codetg=OuterRef("codetg"),
        seqrot=OuterRef("seqrot"),
        id__lt=OuterRef("id"),
    )
    apontamentos_list = apontamentos_list.annotate(
        tem_processamento_na_chave=Exists(chave_mesmo_processamento),
        tem_pendente_anterior=Exists(chave_com_pendente_anterior),
    )

    paginator = Paginator(apontamentos_list, 20)
    page_number = request.GET.get("page")
    apontamentos = paginator.get_page(page_number)
    bloqueados_ids = [
        apontamento.id
        for apontamento in apontamentos
        if apontamento.status == Apontamento.Status.NAO_INTEGRADO
        and (
            PROCESSAMENTO_LOGS_LOCK.locked()
            or apontamento.tem_processamento_na_chave
            or apontamento.tem_pendente_anterior
        )
    ]

    # Botões de exclusão visíveis a quem a rota autoriza (staff/superusuário
    # pelo bypass ou portador da permissão unificada).
    pode_excluir_pendencias = (
        request.user.is_staff
        or request.user.is_superuser
        or request.user.has_perm("producao.pode_excluir_pendencias_integracao")
    )

    return render(
        request,
        "producao/logs_apontamentos.html",
        {
            "apontamentos": apontamentos,
            "bloqueados_ids": bloqueados_ids,
            "search_query": search_query,
            "rotulos_busca": ROTULOS_BUSCA,
            "pode_excluir_pendencias": pode_excluir_pendencias,
        },
    )


@login_required
@require_POST
def enviar_apontamento_log(request, pk):
    # Reserva e dispara em background o envio de um único apontamento escolhido na grade.
    # Achado de autorização: sem restringir por codemp, um não-staff que soubesse
    # o pk conseguia reenviar ao Sapiens um apontamento de outra filial.
    queryset = Apontamento.objects.all()
    if not request.user.is_staff:
        codemp_usuario = _codemp_usuario(request)
        queryset = queryset.filter(codemp=codemp_usuario) if codemp_usuario else queryset.none()
    apontamento = get_object_or_404(queryset, pk=pk)

    status_bloqueado_msg = {
        Apontamento.Status.INTEGRADO: "já está integrado",
        Apontamento.Status.PROCESSANDO: "já está em processamento",
        Apontamento.Status.EXCLUIDO: "foi excluído",
    }
    if apontamento.status != Apontamento.Status.NAO_INTEGRADO:
        messages.warning(
            request,
            f"Apontamento {pk} {status_bloqueado_msg.get(apontamento.status, 'não está pendente')}.",
        )
        return redirect("logs_apontamentos")

    existe_mesma_chave_processando = (
        Apontamento.objects.filter(
            codemp=apontamento.codemp,
            origem=apontamento.origem,
            numorp=apontamento.numorp,
            codetg=apontamento.codetg,
            seqrot=apontamento.seqrot,
            status=Apontamento.Status.PROCESSANDO,
        )
        .exclude(pk=apontamento.pk)
        .exists()
    )
    if existe_mesma_chave_processando:
        messages.warning(
            request,
            f"Já existe um apontamento em processamento para a mesma chave do registro {pk}.",
        )
        return redirect("logs_apontamentos")

    if PROCESSAMENTO_LOGS_LOCK.locked():
        messages.warning(
            request,
            "Já existe um processamento de apontamentos em andamento. Aguarde o retorno antes de enviar outro individual.",
        )
        return redirect("logs_apontamentos")

    apontamentos_reservados = reservar_apontamentos_para_envio(Apontamento.objects.filter(pk=pk))
    if not apontamentos_reservados.exists():
        messages.warning(request, f"Apontamento {pk} não está disponível para envio.")
        return redirect("logs_apontamentos")

    disparar_envio_apontamentos([pk])
    messages.info(request, f"Processamento em background iniciado para o apontamento {pk}.")

    return redirect("logs_apontamentos")


@login_required
@require_POST
def enviar_todos_apontamentos_log(request):
    # Dispara em background o envio em lote de todos os apontamentos ainda pendentes.
    if PROCESSAMENTO_LOGS_LOCK.locked():
        messages.warning(request, "Já existe um processamento em background em andamento.")
        return redirect("logs_apontamentos")

    # Achado de autorização: "enviar todos" sem staff não pode disparar o
    # processamento global (que abrange todas as filiais) — só os pendentes
    # da própria empresa entram na fila.
    pendentes = Apontamento.objects.filter(status=Apontamento.Status.NAO_INTEGRADO)
    if not request.user.is_staff:
        codemp_usuario = _codemp_usuario(request)
        pendentes = pendentes.filter(codemp=codemp_usuario) if codemp_usuario else pendentes.none()

    if not pendentes.exists():
        messages.info(request, "Não há apontamentos pendentes para enviar.")
        return redirect("logs_apontamentos")

    if request.user.is_staff:
        disparar_envio_apontamentos()
    else:
        reservados = reservar_apontamentos_para_envio(pendentes, um_por_chave=True)
        ids_reservados = list(reservados.values_list("id", flat=True))
        if not ids_reservados:
            messages.warning(request, "Os apontamentos pendentes já estão em processamento.")
            return redirect("logs_apontamentos")
        disparar_envio_apontamentos(ids_reservados)

    messages.info(
        request, "Processamento em background iniciado para envio dos apontamentos pendentes."
    )

    return redirect("logs_apontamentos")


# Exclusão unificada das filas: quem recebe pode_excluir_pendencias_integracao
# exclui (staff e superusuário passam pelo bypass do decorator); sem guard
# interno adicional.
@permissao_requerida("producao.pode_excluir_pendencias_integracao")
@require_POST
def excluir_apontamento_erp(request, pk):
    # Restrição de filial: não-staff não exclui apontamento
    # de outra empresa mesmo sabendo o pk.
    queryset = Apontamento.objects.all()
    if not request.user.is_staff:
        codemp_usuario = _codemp_usuario(request)
        queryset = queryset.filter(codemp=codemp_usuario) if codemp_usuario else queryset.none()
    apontamento = get_object_or_404(queryset, pk=pk)

    if apontamento.status == Apontamento.Status.PROCESSANDO:
        messages.error(request, f"Apontamento {pk} está em processamento e não pode ser excluído.")
        return redirect("logs_apontamentos")
    if apontamento.status != Apontamento.Status.NAO_INTEGRADO:
        messages.error(request, f"Apontamento {pk} já foi integrado e não pode mais ser excluído.")
        return redirect("logs_apontamentos")

    apontamento.delete()
    messages.success(request, f"Apontamento {pk} excluído com sucesso.")
    return redirect("logs_apontamentos")


@permissao_requerida("producao.pode_excluir_pendencias_integracao")
@require_POST
def excluir_todos_apontamentos_log(request):
    # Exclusão em massa também precisa respeitar a filial do não-staff.
    queryset = Apontamento.objects.filter(status=Apontamento.Status.NAO_INTEGRADO)
    if not request.user.is_staff:
        codemp_usuario = _codemp_usuario(request)
        queryset = queryset.filter(codemp=codemp_usuario) if codemp_usuario else queryset.none()

    total = queryset.count()
    if total == 0:
        messages.info(request, "Não há logs locais para excluir.")
        return redirect("logs_apontamentos")

    queryset.delete()
    messages.success(request, f"Todos os {total} logs locais foram excluídos com sucesso.")
    return redirect("logs_apontamentos")
