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
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from producao.models import ApontamentoComponente
from producao.services.sapiens import enviar_soap_sapiens
from producao.services.status import ciclo_service, marcar_atividade_service, registrar_service
from producao.utils.codificacao import get_response_text, safe_str
from producao.utils.sapiens_soap import escapar_cdata_sapiens
from SIGMA.autorizacao import permissao_requerida
from SIGMA.integracoes.oracle import cursor_oracle_erp
from SIGMA.segredos import mascarar_segredos

logger = logging.getLogger(__name__)
PROCESSAMENTO_APONTAMENTO_COMPONENTES_LOCK = threading.Lock()
TEMPO_LIMITE_CICLO_SEGUNDOS = 1800
WEBSERVICE_TIMEOUT_SEGUNDOS = 180
MAX_WORKERS_LOGS_APONTAMENTO_COMPONENTES = max(
    int(os.getenv("LOGS_APONTAMENTO_COMPONENTES_MAX_WORKERS", "10")), 1
)
COMPONENTES_SERVICE_NAME = "ApontamentoComponente"
COMPONENTES_WACAO = "APONTAR-COMPONENTE"
SERVICE_CODIGO = "fila_log_apontamento_componentes"
SERVICE_NOME = "Fila Log Apontamento Componentes"

registrar_service(
    SERVICE_CODIGO,
    SERVICE_NOME,
    None,
    "Processa a fila assíncrona de apontamentos de componentes.",
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
    ("codigo_integrador", "código integrador"),
    ("lote", "lote"),
    ("log", "log"),
    ("usuario__username", "usuário"),
    ("data_hora", "data/hora"),
    ("recurso__codigo", "recurso"),
    ("recurso__descricao", "descrição do recurso"),
    ("recurso__centro_recurso__codigo", "centro de recurso"),
    ("recurso__centro_recurso__descricao", "descrição do centro"),
)

# Rótulos dos campos para a instrução da tela (placeholder do template).
ROTULOS_BUSCA = ", ".join(rotulo for _campo, rotulo in CAMPOS_BUSCA)


def consulta_de_busca(termo: str) -> Q:
    """Q disjunto com um `icontains` por campo de `CAMPOS_BUSCA`."""
    consulta = Q()
    for campo, _rotulo in CAMPOS_BUSCA:
        consulta |= Q(**{f"{campo}__icontains": termo})
    return consulta


def reservar_componentes_para_envio(queryset, um_por_chave=False):
    # Reserva pendentes de forma atomica para evitar envio duplicado por tela e scheduler.
    with transaction.atomic():
        pendentes = list(
            queryset.filter(status=ApontamentoComponente.Status.NAO_INTEGRADO)
            .select_for_update(skip_locked=True)
            .order_by("id")
            .values("id", "codemp", "origem", "numorp", "codetg", "seqrot")
        )

        if um_por_chave:
            chaves_em_processamento = {
                (item["codemp"], item["origem"], item["numorp"], item["codetg"], item["seqrot"])
                for item in ApontamentoComponente.objects.filter(
                    status=ApontamentoComponente.Status.PROCESSANDO
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
                if chave in chaves_em_processamento or chave in chaves_reservadas:
                    continue
                ids.append(item["id"])
                chaves_reservadas.add(chave)
        else:
            ids = [item["id"] for item in pendentes]

        if not ids:
            return ApontamentoComponente.objects.none()

        ApontamentoComponente.objects.filter(
            id__in=ids, status=ApontamentoComponente.Status.NAO_INTEGRADO
        ).update(
            status=ApontamentoComponente.Status.PROCESSANDO,
            log="Aguardando processamento background",
            data_hora=timezone.now(),
        )

    return ApontamentoComponente.objects.filter(
        id__in=ids, status=ApontamentoComponente.Status.PROCESSANDO
    ).order_by("id")


def processar_componentes_pendentes(ids=None):
    close_old_connections()
    try:
        if ids is not None and not ids:
            return 0, 0

        if not PROCESSAMENTO_APONTAMENTO_COMPONENTES_LOCK.acquire(blocking=False):
            if ids is not None:
                ApontamentoComponente.objects.filter(
                    id__in=ids, status=ApontamentoComponente.Status.PROCESSANDO
                ).update(
                    status=ApontamentoComponente.Status.NAO_INTEGRADO,
                    log="Aguardando processamento background",
                    data_hora=timezone.now(),
                )
            return 0, 0

        with ciclo_service(SERVICE_CODIGO):
            sucessos_total = 0
            erros_total = 0
            ids_tentados_no_ciclo = set()
            try:
                while True:
                    if ids is None:
                        queryset_pendentes = ApontamentoComponente.objects.order_by("id")
                        if ids_tentados_no_ciclo:
                            queryset_pendentes = queryset_pendentes.exclude(
                                id__in=ids_tentados_no_ciclo
                            )
                        componentes = reservar_componentes_para_envio(
                            queryset_pendentes,
                            um_por_chave=True,
                        )
                    else:
                        componentes = ApontamentoComponente.objects.filter(
                            id__in=ids, status=ApontamentoComponente.Status.PROCESSANDO
                        ).order_by("id")

                    if not componentes.exists():
                        break

                    ids_tentados_no_ciclo.update(componentes.values_list("id", flat=True))

                    if ids is None:
                        grupos_por_chave = {}
                        for item in componentes.values(
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
                        max_workers = min(len(grupos_ids), MAX_WORKERS_LOGS_APONTAMENTO_COMPONENTES)

                        if max_workers <= 1:
                            sucessos, erros, _ = executar_envio_componentes_com_conexao_limpa(
                                componentes
                            )
                            sucessos_total += sucessos
                            erros_total += erros
                        else:
                            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                                futures = [
                                    executor.submit(
                                        executar_envio_componentes_com_conexao_limpa,
                                        ApontamentoComponente.objects.filter(
                                            id__in=grupo_ids,
                                            status=ApontamentoComponente.Status.PROCESSANDO,
                                        ).order_by("id"),
                                    )
                                    for grupo_ids in grupos_ids
                                ]
                                for future in as_completed(futures):
                                    sucessos, erros, _ = future.result()
                                    sucessos_total += sucessos
                                    erros_total += erros
                    else:
                        sucessos, erros, _ = executar_envio_componentes_com_conexao_limpa(
                            componentes
                        )
                        sucessos_total += sucessos
                        erros_total += erros

                    if ids is not None:
                        break
            finally:
                PROCESSAMENTO_APONTAMENTO_COMPONENTES_LOCK.release()

            return sucessos_total, erros_total
    finally:
        connections.close_all()


def disparar_envio_componentes(ids=None):
    threading.Thread(target=processar_componentes_pendentes, args=(ids,), daemon=True).start()


def _codemp_usuario(request):
    """Deriva o codemp do usuário logado; mesma fonte usada em toda a fila de componentes."""
    empresa_usuario = getattr(getattr(request.user, "filial", None), "empresa", None)
    return getattr(empresa_usuario, "codemp", None)


def liberar_componentes_processando_antigos(idade_segundos=None):
    queryset = ApontamentoComponente.objects.filter(status=ApontamentoComponente.Status.PROCESSANDO)
    if idade_segundos is not None:
        queryset = queryset.filter(data_hora__lt=timezone.now() - timedelta(seconds=idade_segundos))

    return queryset.update(
        status=ApontamentoComponente.Status.NAO_INTEGRADO,
        log="Processamento anterior interrompido. Disponível para novo envio.",
        data_hora=timezone.now(),
    )


def _formatar_numero_json(valor):
    if valor is None:
        return "0"
    return str(valor).strip().replace(",", ".")


def resolver_dados_componente_para_envio(componente):
    lote_informado = str(componente.lote or "").strip().upper()
    if not lote_informado:
        return None, "Palete/lote do componente não informado."

    with cursor_oracle_erp() as cursor:
        cursor.execute(
            """
            SELECT USU_QTDDIS,
                   USU_CODLOT,
                   USU_CODCMP,
                   USU_DERCMP
              FROM USU_TPALWMS
             WHERE USU_CODEMP = :codemp
               AND USU_PALWMS = :palete
            """,
            {"codemp": componente.codemp, "palete": lote_informado},
        )
        row = cursor.fetchone()
        if row:
            qtd_cmp, codlot, codcmp, dercmp = row
            return {
                "PalWms": lote_informado,
                "CodLotCmp": str(codlot or "").strip(),
                "CodCmpRec": str(codcmp or "").strip(),
                "DerCmpRec": str(dercmp or " ").strip() or " ",
                "QtdCmp": _formatar_numero_json(qtd_cmp),
            }, None

        cursor.execute(
            """
            SELECT CODPRO,
                   CODDER,
                   SUM(QTDEST)
              FROM E210DLS
             WHERE CODEMP = :codemp
               AND CODLOT = :codlot
             GROUP BY CODPRO, CODDER
            """,
            {"codemp": componente.codemp, "codlot": lote_informado},
        )
        row = cursor.fetchone()
        if row:
            codcmp, dercmp, qtd_cmp = row
            return {
                "PalWms": "",
                "CodLotCmp": lote_informado,
                "CodCmpRec": str(codcmp or "").strip(),
                "DerCmpRec": str(dercmp or " ").strip() or " ",
                "QtdCmp": _formatar_numero_json(qtd_cmp),
            }, None

    return None, f"Palete/lote {lote_informado} não encontrado na USU_TPALWMS nem na E210DLS."


def criar_ajuste_wms_palete_integrado(componente, dados_componente):
    if not dados_componente.get("PalWms"):
        return None

    from setores.qualidade.models.estrutura import WMS_IntegraçãoOP
    from setores.qualidade.utils.wms_integracao import codder_wms
    from setores.qualidade.views.wms_views import (
        disparar_envio_wms,
        reservar_integracoes_wms_para_envio,
    )

    dados_wms = {
        "codemp": componente.codemp,
        "origem": str(componente.origem or ""),
        "op": componente.numorp or 0,
        "lote": dados_componente["CodLotCmp"],
        "palete": dados_componente["PalWms"],
        "quantidade": 0,
        "codigo_integrador": str(componente.codigo_integrador or ""),
        "local": "",
        "codpro": dados_componente["CodCmpRec"],
        "codder": codder_wms(dados_componente["DerCmpRec"]),
        "tipo_envio": WMS_IntegraçãoOP.TIPO_AJUSTE,
        "reuniao": None,
    }

    integracao = (
        WMS_IntegraçãoOP.objects.filter(
            **dados_wms,
            status__in=[WMS_IntegraçãoOP.Status.NAO_INTEGRADO, WMS_IntegraçãoOP.Status.PROCESSANDO],
        )
        .order_by("-id")
        .first()
    )
    if not integracao:
        integracao = WMS_IntegraçãoOP.objects.create(
            **dados_wms,
            status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO,
            log=f"Gerado pelo apontamento de componente #{componente.id}",
            datger=timezone.now(),
        )

    ids = reservar_integracoes_wms_para_envio(WMS_IntegraçãoOP.objects.filter(pk=integracao.pk))
    if ids:
        disparar_envio_wms(ids)
    return integracao


def enviar_integracao_componente(usuario, senha, componente, dados_componente):
    # Ponto unico para troca do webservice de componentes.
    sapiens_base = settings.SAPIENS_URL_BASE
    url = f"{sapiens_base}/g5-senior-services/sapiens_Synccustom.senior.man.producao"

    dados = {
        "wacao": COMPONENTES_WACAO,
        "empresa": str(componente.codemp),
        "CodOri": str(componente.origem),
        "NumOrp": str(componente.numorp),
        "NumCad": str(componente.numcad),
        "CodEtg": str(componente.codetg),
        "SeqRot": str(componente.seqrot),
        "HorMov": str(componente.hormov),
        "DatMov": str(componente.datmov),
        "NumMaq": str(componente.codigo_integrador or ""),
        "CodLotCmp": dados_componente["CodLotCmp"],
        "CodCmpRec": dados_componente["CodCmpRec"],
        "DerCmpRec": dados_componente["DerCmpRec"],
        "QtdCmp": dados_componente["QtdCmp"],
    }
    json_dados = json.dumps(dados, ensure_ascii=False)

    envelope = f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<soapenv:Envelope xmlns:soapenv="http://www.w3.org/2003/05/soap-envelope"
                  xmlns:ser="http://services.senior.com.br">
  <soapenv:Header/>
  <soapenv:Body>
    <ser:{COMPONENTES_SERVICE_NAME}>
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
    </ser:{COMPONENTES_SERVICE_NAME}>
  </soapenv:Body>
</soapenv:Envelope>"""
    logger.debug(
        "SOAP enviado (%s): %s",
        COMPONENTES_SERVICE_NAME,
        mascarar_segredos(envelope),
    )

    # validar_status=False: a leitura de waRetorno decide integrado/erro,
    # inclusive para HTTP != 200.
    resposta = enviar_soap_sapiens(
        url, envelope, timeout=WEBSERVICE_TIMEOUT_SEGUNDOS, validar_status=False
    )

    logger.debug(
        "Resposta SOAP (%s): %s",
        COMPONENTES_SERVICE_NAME,
        mascarar_segredos(get_response_text(resposta)),
    )

    return get_response_text(resposta)


def _registrar_resultado_componente(componente_id, status, log):
    # Mascara o mais perto possivel da gravacao: cobre qualquer chamador atual ou futuro.
    log = mascarar_segredos(log)
    agora = timezone.now()
    if status == ApontamentoComponente.Status.INTEGRADO:
        ApontamentoComponente.objects.filter(pk=componente_id).update(
            status=ApontamentoComponente.Status.INTEGRADO,
            log=log,
            data_hora=agora,
        )
        return True

    atualizados = (
        ApontamentoComponente.objects.filter(pk=componente_id)
        .exclude(status=ApontamentoComponente.Status.INTEGRADO)
        .update(status=ApontamentoComponente.Status.NAO_INTEGRADO, log=log, data_hora=agora)
    )
    return bool(atualizados)


def _resposta_integrada(resposta):
    log = resposta
    status = ApontamentoComponente.Status.NAO_INTEGRADO
    match = re.search(r"<waRetorno>(.*?)</waRetorno>", resposta, re.DOTALL | re.IGNORECASE)
    if match:
        log = match.group(1).strip()
        try:
            dados = json.loads(log)
            if dados.get("status") == "OK" or dados.get("message") == "OK":
                status = ApontamentoComponente.Status.INTEGRADO
        except json.JSONDecodeError, TypeError:
            if "Processado com sucesso" in resposta:
                status = ApontamentoComponente.Status.INTEGRADO
    elif "Processado com sucesso" in resposta:
        status = ApontamentoComponente.Status.INTEGRADO
    return status, log


def executar_envio_componentes(pendentes):
    sucessos = 0
    erros = 0

    for componente in pendentes:
        marcar_atividade_service(SERVICE_CODIGO, WEBSERVICE_TIMEOUT_SEGUNDOS)
        if not componente.datmov or not componente.hormov:
            agora = timezone.localtime(timezone.now())
            componente.datmov = agora.strftime("%d/%m/%Y")
            componente.hormov = agora.strftime("%H:%M:%S")

        try:
            dados_componente, erro_resolucao = resolver_dados_componente_para_envio(componente)
            if erro_resolucao:
                _registrar_resultado_componente(
                    componente.id, ApontamentoComponente.Status.NAO_INTEGRADO, erro_resolucao
                )
                erros += 1
                continue

            resposta = enviar_integracao_componente(
                usuario=settings.SAPIENS_USERNAME,
                senha=settings.SAPIENS_PASSWORD,
                componente=componente,
                dados_componente=dados_componente,
            )
            status_comp, log_comp = _resposta_integrada(resposta)

            if status_comp == ApontamentoComponente.Status.INTEGRADO:
                try:
                    integracao_wms = criar_ajuste_wms_palete_integrado(componente, dados_componente)
                except Exception as exc:
                    msg_erro = f"ERP integrado, mas falhou ao gerar ajuste WMS: {exc}"
                    _registrar_resultado_componente(
                        componente.id, ApontamentoComponente.Status.NAO_INTEGRADO, msg_erro
                    )
                    erros += 1
                    continue

                if integracao_wms:
                    log_comp = (
                        f"{log_comp}\nWMS ajuste #{integracao_wms.pk} gerado para zerar palete."
                    )

                _registrar_resultado_componente(componente.id, status_comp, log_comp)
                sucessos += 1
            else:
                _registrar_resultado_componente(componente.id, status_comp, log_comp)
                erros += 1
        except Exception as exc:
            # Log visível em tela: texto de exceção passa pela máscara.
            msg_erro = f"Erro no processamento do componente {componente.id}: {mascarar_segredos(safe_str(exc))}"
            _registrar_resultado_componente(
                componente.id, ApontamentoComponente.Status.NAO_INTEGRADO, msg_erro
            )
            erros += 1

    return sucessos, erros, set()


def executar_envio_componentes_com_conexao_limpa(pendentes):
    close_old_connections()
    try:
        return executar_envio_componentes(pendentes)
    finally:
        connections.close_all()


@login_required
def logs_apontamento_componentes(request):
    codemp_usuario = _codemp_usuario(request)

    queryset_base = ApontamentoComponente.objects.select_related(
        "recurso",
        "recurso__centro_recurso",
        "usuario",
    )
    if not request.user.is_staff:
        if codemp_usuario:
            queryset_base = queryset_base.filter(codemp=codemp_usuario)
        else:
            queryset_base = queryset_base.none()

    search_query = request.GET.get("search", "").strip()
    if search_query:
        if search_query.lower().startswith("l") or search_query.isdigit():
            search_query = search_query.upper()

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
        apontamentos_list = queryset_base.order_by("-id")

    chave_mesmo_processamento = ApontamentoComponente.objects.filter(
        status=ApontamentoComponente.Status.PROCESSANDO,
        codemp=OuterRef("codemp"),
        origem=OuterRef("origem"),
        numorp=OuterRef("numorp"),
        codetg=OuterRef("codetg"),
        seqrot=OuterRef("seqrot"),
    )
    apontamentos_list = apontamentos_list.annotate(
        tem_processamento_na_chave=Exists(chave_mesmo_processamento),
    )
    paginator = Paginator(apontamentos_list, 20)
    page_number = request.GET.get("page")
    apontamentos = paginator.get_page(page_number)
    bloqueados_ids = [
        apontamento.id
        for apontamento in apontamentos
        if apontamento.status == ApontamentoComponente.Status.NAO_INTEGRADO
        and (
            PROCESSAMENTO_APONTAMENTO_COMPONENTES_LOCK.locked()
            or apontamento.tem_processamento_na_chave
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
        "producao/logs_apontamento_componentes.html",
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
def enviar_componente_log(request, pk):
    # Achado de autorização: sem restringir por codemp, um não-staff que soubesse
    # o pk conseguia reenviar ao Sapiens um componente de outra filial.
    queryset = ApontamentoComponente.objects.all()
    if not request.user.is_staff:
        codemp_usuario = _codemp_usuario(request)
        queryset = queryset.filter(codemp=codemp_usuario) if codemp_usuario else queryset.none()
    componente = get_object_or_404(queryset, pk=pk)
    status_bloqueado_msg = {
        ApontamentoComponente.Status.INTEGRADO: "já está integrado",
        ApontamentoComponente.Status.PROCESSANDO: "já está em processamento",
        ApontamentoComponente.Status.EXCLUIDO: "foi excluído",
    }
    if componente.status != ApontamentoComponente.Status.NAO_INTEGRADO:
        messages.warning(
            request,
            f"Componente {pk} {status_bloqueado_msg.get(componente.status, 'não está pendente')}.",
        )
        return redirect("logs_apontamento_componentes")

    existe_mesma_chave_processando = (
        ApontamentoComponente.objects.filter(
            codemp=componente.codemp,
            origem=componente.origem,
            numorp=componente.numorp,
            codetg=componente.codetg,
            seqrot=componente.seqrot,
            status=ApontamentoComponente.Status.PROCESSANDO,
        )
        .exclude(pk=componente.pk)
        .exists()
    )
    if existe_mesma_chave_processando:
        messages.warning(
            request,
            f"Já existe um componente em processamento para a mesma chave do registro {pk}.",
        )
        return redirect("logs_apontamento_componentes")

    if PROCESSAMENTO_APONTAMENTO_COMPONENTES_LOCK.locked():
        messages.warning(
            request,
            "Já existe um processamento de componentes em andamento. Aguarde antes de enviar outro individual.",
        )
        return redirect("logs_apontamento_componentes")

    reservados = reservar_componentes_para_envio(ApontamentoComponente.objects.filter(pk=pk))
    if not reservados.exists():
        messages.warning(request, f"Componente {pk} não está disponível para envio.")
        return redirect("logs_apontamento_componentes")

    disparar_envio_componentes([pk])
    messages.info(request, f"Processamento em background iniciado para o componente {pk}.")
    return redirect("logs_apontamento_componentes")


@login_required
@require_POST
def enviar_todos_componentes_log(request):
    if PROCESSAMENTO_APONTAMENTO_COMPONENTES_LOCK.locked():
        messages.warning(
            request, "Já existe um processamento de componentes em background em andamento."
        )
        return redirect("logs_apontamento_componentes")

    # Achado de autorização: "enviar todos" sem staff não pode disparar o
    # processamento global (todas as filiais) — só os pendentes da própria
    # empresa entram na fila.
    pendentes = ApontamentoComponente.objects.filter(
        status=ApontamentoComponente.Status.NAO_INTEGRADO
    )
    if not request.user.is_staff:
        codemp_usuario = _codemp_usuario(request)
        pendentes = pendentes.filter(codemp=codemp_usuario) if codemp_usuario else pendentes.none()

    if not pendentes.exists():
        messages.info(request, "Não há componentes pendentes para enviar.")
        return redirect("logs_apontamento_componentes")

    if request.user.is_staff:
        disparar_envio_componentes()
    else:
        reservados = reservar_componentes_para_envio(pendentes, um_por_chave=True)
        ids_reservados = list(reservados.values_list("id", flat=True))
        if not ids_reservados:
            messages.warning(request, "Os componentes pendentes já estão em processamento.")
            return redirect("logs_apontamento_componentes")
        disparar_envio_componentes(ids_reservados)

    messages.info(
        request, "Processamento em background iniciado para envio dos componentes pendentes."
    )
    return redirect("logs_apontamento_componentes")


# Exclusão unificada das filas: quem recebe pode_excluir_pendencias_integracao
# exclui (staff e superusuário passam pelo bypass do decorator); sem guard
# interno adicional.
@permissao_requerida("producao.pode_excluir_pendencias_integracao")
@require_POST
def excluir_componente_log(request, pk):
    # Restrição de filial: não-staff não exclui componente
    # de outra empresa mesmo sabendo o pk.
    queryset = ApontamentoComponente.objects.all()
    if not request.user.is_staff:
        codemp_usuario = _codemp_usuario(request)
        queryset = queryset.filter(codemp=codemp_usuario) if codemp_usuario else queryset.none()
    componente = get_object_or_404(queryset, pk=pk)

    if componente.status == ApontamentoComponente.Status.PROCESSANDO:
        messages.error(request, f"Componente {pk} está em processamento e não pode ser excluído.")
        return redirect("logs_apontamento_componentes")
    if componente.status != ApontamentoComponente.Status.NAO_INTEGRADO:
        messages.error(request, f"Componente {pk} já foi integrado e não pode mais ser excluído.")
        return redirect("logs_apontamento_componentes")

    componente.delete()
    messages.success(request, f"Componente {pk} excluído com sucesso.")
    return redirect("logs_apontamento_componentes")


@permissao_requerida("producao.pode_excluir_pendencias_integracao")
@require_POST
def excluir_todos_componentes_log(request):
    # Exclusão em massa também precisa respeitar a filial do não-staff.
    queryset = ApontamentoComponente.objects.filter(
        status=ApontamentoComponente.Status.NAO_INTEGRADO
    )
    if not request.user.is_staff:
        codemp_usuario = _codemp_usuario(request)
        queryset = queryset.filter(codemp=codemp_usuario) if codemp_usuario else queryset.none()

    total = queryset.count()
    if total == 0:
        messages.info(request, "Não há logs locais de componentes para excluir.")
        return redirect("logs_apontamento_componentes")

    queryset.delete()
    messages.success(
        request, f"Todos os {total} logs locais de componentes foram excluídos com sucesso."
    )
    return redirect("logs_apontamento_componentes")
