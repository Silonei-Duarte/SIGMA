import json
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

from producao.models import BaixaComponente, BobinaConsumoRecurso
from producao.services.sapiens import enviar_soap_sapiens
from producao.services.status import ciclo_service, marcar_atividade_service, registrar_service
from producao.utils.codificacao import get_response_text, safe_str
from producao.utils.sapiens_soap import escapar_cdata_sapiens
from SIGMA.autorizacao import permissao_requerida
from SIGMA.integracoes.oracle import cursor_oracle_erp
from SIGMA.segredos import mascarar_segredos

PROCESSAMENTO_BAIXAS_COMPONENTES_LOCK = threading.Lock()
TEMPO_LIMITE_CICLO_SEGUNDOS = 1800
WEBSERVICE_TIMEOUT_SEGUNDOS = 180
MAX_WORKERS_LOGS_BAIXA_COMPONENTES = max(
    int(os.getenv("LOGS_BAIXA_COMPONENTES_MAX_WORKERS", "10")), 1
)
SERVICE_CODIGO = "fila_baixa_componentes"
SERVICE_NOME = "Fila Baixa Componentes"

registrar_service(
    SERVICE_CODIGO,
    SERVICE_NOME,
    None,
    "Processa a fila assíncrona de baixas de componentes da tela de apontamento V3.",
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
    ("codigo_integrador", "código integrador"),
    ("codlot", "lote"),
    ("codcmp", "componente"),
    ("dercmp", "derivação"),
    ("log", "log"),
    ("usuario__username", "usuário"),
    ("recurso__codigo", "recurso"),
    ("recurso__descricao", "descrição do recurso"),
)

# Rótulos dos campos para a instrução da tela (placeholder do template).
ROTULOS_BUSCA = ", ".join(rotulo for _campo, rotulo in CAMPOS_BUSCA)


def consulta_de_busca(termo: str) -> Q:
    """Q disjunto com um `icontains` por campo de `CAMPOS_BUSCA`."""
    consulta = Q()
    for campo, _rotulo in CAMPOS_BUSCA:
        consulta |= Q(**{f"{campo}__icontains": termo})
    return consulta


def reservar_baixas_componentes_para_envio(queryset, uma_por_codlot=False, codlots_ignorados=None):
    """Reserva pendências sem permitir dois envios simultâneos do mesmo CodLot."""
    codlots_ignorados = codlots_ignorados or set()
    with transaction.atomic():
        pendentes = list(
            queryset.filter(status=BaixaComponente.Status.NAO_INTEGRADO)
            .select_for_update(skip_locked=True)
            .order_by("id")
            .values("id", "codlot")
        )
        if uma_por_codlot:
            codlots_processando = set(
                BaixaComponente.objects.filter(
                    status=BaixaComponente.Status.PROCESSANDO
                ).values_list("codlot", flat=True)
            )
            ids, codlots_reservados = [], set()
            for item in pendentes:
                codlot = item["codlot"]
                if (
                    codlot in codlots_ignorados
                    or codlot in codlots_processando
                    or codlot in codlots_reservados
                ):
                    continue
                ids.append(item["id"])
                codlots_reservados.add(codlot)
        else:
            ids = [item["id"] for item in pendentes]

        if not ids:
            return BaixaComponente.objects.none()
        BaixaComponente.objects.filter(
            id__in=ids, status=BaixaComponente.Status.NAO_INTEGRADO
        ).update(
            status=BaixaComponente.Status.PROCESSANDO,
            log="Aguardando processamento background",
            data_hora=timezone.now(),
        )
    return BaixaComponente.objects.filter(
        id__in=ids, status=BaixaComponente.Status.PROCESSANDO
    ).order_by("id")


def _registrar_resultado(baixa_id, integrado, log):
    # Mascara o mais perto possivel da gravacao: cobre qualquer chamador atual ou futuro.
    log = mascarar_segredos(log)
    filtros = BaixaComponente.objects.filter(pk=baixa_id)
    if integrado:
        filtros.update(status=BaixaComponente.Status.INTEGRADO, log=log, data_hora=timezone.now())
        return True
    return bool(
        filtros.exclude(status=BaixaComponente.Status.INTEGRADO).update(
            status=BaixaComponente.Status.NAO_INTEGRADO, log=log, data_hora=timezone.now()
        )
    )


def _formatar_numero(valor):
    return str(valor if valor is not None else 0).strip().replace(",", ".")


def enviar_baixa_componente(usuario, senha, baixa):
    """Ponto único para configurar futuramente o serviço definitivo de baixa."""
    url = f"{settings.SAPIENS_URL_BASE}/g5-senior-services/sapiens_Synccustom.senior.man.producao"
    dados = {
        "codemp": str(baixa.codemp),
        "origem": str(baixa.origem),
        "numorp": str(baixa.numorp),
        "codetg": str(baixa.codetg),
        "seqrot": str(baixa.seqrot),
        "lotdes": str(baixa.lotdes or ""),
        "codcmp": str(baixa.codcmp),
        "dercmp": str(baixa.dercmp or ""),
        "qtduti": _formatar_numero(baixa.qtduti),
        "codigo_integrador": str(baixa.codigo_integrador or ""),
        "datmov": str(baixa.datmov or ""),
        "hormov": str(baixa.hormov or ""),
        "codlot": str(baixa.codlot),
        "repesagem": str(baixa.repesagem),
        "consumototal": str(baixa.consumototal),
    }
    envelope = f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<soapenv:Envelope xmlns:soapenv="http://www.w3.org/2003/05/soap-envelope" xmlns:ser="http://services.senior.com.br">
  <soapenv:Header/>
  <soapenv:Body>
    <ser:TratarBaixa>
      <user>{escape(str(usuario))}</user>
      <password>{escape(str(senha))}</password>
      <encryption>0</encryption>
      <parameters>
        <flowInstanceID></flowInstanceID><flowName></flowName>
        <tabelaEntradas><chave>wdados</chave><valor><![CDATA[{escapar_cdata_sapiens(json.dumps(dados, ensure_ascii=False))}]]></valor></tabelaEntradas>
      </parameters>
    </ser:TratarBaixa>
  </soapenv:Body>
</soapenv:Envelope>"""
    # validar_status=False: a leitura de waRetorno decide integrado/erro,
    # inclusive para HTTP != 200.
    resposta = enviar_soap_sapiens(
        url, envelope, timeout=WEBSERVICE_TIMEOUT_SEGUNDOS, validar_status=False
    )
    return get_response_text(resposta)


def _resposta_integrada(resposta):
    retorno = re.search(r"<waRetorno>(.*?)</waRetorno>", resposta, re.DOTALL | re.IGNORECASE)
    log = retorno.group(1) if retorno else resposta
    try:
        dados = json.loads(log)
    except json.JSONDecodeError, TypeError:
        return "Processado com sucesso" in resposta, log
    return dados.get("message") == "OK" or dados.get("status") == "OK", log


def _resolver_palete_wms_por_lote(codemp, codlot):
    """Encontra o palete WMS cujo USU_CODLOT bate com o lote consumido.

    O WMS controla saldo por palete, não por lote — mesma resolução usada em
    logs_apontamento_componentes.py, mas aqui partindo do lote (não de um
    valor digitado pelo operador). Sem palete correspondente, o próprio lote
    é usado como identificador no ajuste, igual ao fluxo de área vermelha.
    """
    with cursor_oracle_erp() as cursor:
        cursor.execute(
            "SELECT USU_PALWMS FROM USU_TPALWMS WHERE USU_CODEMP = :codemp AND USU_CODLOT = :codlot",
            {"codemp": codemp, "codlot": codlot},
        )
        row = cursor.fetchone()
    return str(row[0]).strip() if row and row[0] else codlot


def _novo_valor_lote_para_wms(baixa):
    """Calcula o novo saldo do lote a informar ao WMS após esta baixa.

    O WMS precisa saber quanto SOBROU no lote, não quanto foi debitado
    (baixa.qtduti). Repesagem e consumo total já têm o saldo final definido
    pela própria regra de negócio (1 e 0); no caso comum, o saldo restante é
    lido da BobinaConsumoRecurso ainda ativa para aquele lote — se ela já foi
    removida (zerou por completo), o valor correto é 0.
    """
    if baixa.repesagem == "S":
        return 1
    if baixa.consumototal == "S":
        return 0
    bobina = BobinaConsumoRecurso.objects.filter(codemp=baixa.codemp, lote=baixa.codlot).first()
    return bobina.quantidade_restante if bobina else 0


def criar_ajuste_wms_lote_baixado(baixa):
    from setores.qualidade.models.estrutura import WMS_IntegraçãoOP
    from setores.qualidade.utils.wms_integracao import codder_wms
    from setores.qualidade.views.wms_views import (
        disparar_envio_wms,
        reservar_integracoes_wms_para_envio,
    )

    palete = _resolver_palete_wms_por_lote(baixa.codemp, baixa.codlot)
    dados_wms = {
        "codemp": baixa.codemp,
        "origem": str(baixa.origem or ""),
        "op": baixa.numorp or 0,
        "lote": baixa.codlot,
        "palete": palete,
        "quantidade": _novo_valor_lote_para_wms(baixa),
        "codigo_integrador": str(baixa.codigo_integrador or ""),
        "local": "",
        "codpro": baixa.codcmp,
        "codder": codder_wms(baixa.dercmp),
        "tipo_envio": WMS_IntegraçãoOP.TIPO_AJUSTE,
        "reuniao": None,
    }

    # Diferente do ajuste da v1/v2 (sempre quantidade=0, idempotente), aqui a
    # quantidade é o novo saldo do lote a cada baixa — cada baixa integrada
    # gera seu próprio ajuste, sem reaproveitar um pendente anterior do mesmo
    # lote, para não sobrescrever um valor ainda não enviado ao WMS.
    integracao = WMS_IntegraçãoOP.objects.create(
        **dados_wms,
        status=0,
        log=f"Gerado pela baixa de componente #{baixa.id}",
        datger=timezone.now(),
    )

    ids = reservar_integracoes_wms_para_envio(WMS_IntegraçãoOP.objects.filter(pk=integracao.pk))
    if ids:
        disparar_envio_wms(ids)
    return integracao


def executar_envio_baixas_componentes(pendentes):
    sucessos = erros = 0
    codlots_com_erro = set()
    for baixa in pendentes:
        marcar_atividade_service(SERVICE_CODIGO, WEBSERVICE_TIMEOUT_SEGUNDOS)
        codlot = baixa.codlot
        if codlot in codlots_com_erro:
            _registrar_resultado(
                baixa.id, False, "Aguardando integração de baixa anterior do mesmo lote"
            )
            erros += 1
            continue

        # A chave desta fila é o lote consumido: cada baixa só segue quando a
        # anterior do mesmo CodLot já tiver sido integrada.
        anterior_pendente = BaixaComponente.objects.filter(
            codlot=codlot, status=BaixaComponente.Status.NAO_INTEGRADO, id__lt=baixa.id
        ).exists()
        if anterior_pendente:
            _registrar_resultado(
                baixa.id, False, "Aguardando integração de baixa anterior do mesmo lote"
            )
            codlots_com_erro.add(codlot)
            erros += 1
            continue
        try:
            resposta = enviar_baixa_componente(
                settings.SAPIENS_USERNAME, settings.SAPIENS_PASSWORD, baixa
            )
            integrado, log = _resposta_integrada(resposta)
            _registrar_resultado(baixa.id, integrado, log)
            if integrado:
                sucessos += 1
                try:
                    criar_ajuste_wms_lote_baixado(baixa)
                except Exception as exc_wms:
                    # A baixa no ERP já foi efetivada; uma falha aqui não deve
                    # reverter isso — só fica sem o ajuste WMS desta vez, sem
                    # bloquear as próximas baixas do mesmo lote.
                    _registrar_resultado(
                        baixa.id, True, f"{log} | Erro ao gerar ajuste WMS: {safe_str(exc_wms)}"
                    )
            else:
                erros += 1
                codlots_com_erro.add(codlot)
        except Exception as exc:
            _registrar_resultado(
                baixa.id,
                False,
                # Log visível em tela: texto de exceção passa pela máscara.
                f"Erro no processamento da baixa {baixa.id}: {mascarar_segredos(safe_str(exc))}",
            )
            erros += 1
            codlots_com_erro.add(codlot)
    return sucessos, erros, codlots_com_erro


def _executar_envio_com_conexao_limpa(pendentes):
    close_old_connections()
    try:
        return executar_envio_baixas_componentes(pendentes)
    finally:
        connections.close_all()


def processar_baixas_componentes_pendentes(ids=None):
    close_old_connections()
    try:
        if not PROCESSAMENTO_BAIXAS_COMPONENTES_LOCK.acquire(blocking=False):
            if ids:
                BaixaComponente.objects.filter(
                    id__in=ids, status=BaixaComponente.Status.PROCESSANDO
                ).update(
                    status=BaixaComponente.Status.NAO_INTEGRADO,
                    log="Aguardando processamento background",
                    data_hora=timezone.now(),
                )
            return 0, 0
        with ciclo_service(SERVICE_CODIGO):
            sucessos_total = erros_total = 0
            codlots_falhados = set()
            try:
                while True:
                    pendentes = (
                        reservar_baixas_componentes_para_envio(
                            BaixaComponente.objects.order_by("id"), True, codlots_falhados
                        )
                        if ids is None
                        else BaixaComponente.objects.filter(
                            id__in=ids, status=BaixaComponente.Status.PROCESSANDO
                        ).order_by("id")
                    )
                    if not pendentes.exists():
                        break
                    if ids is None:
                        grupos_ids = [[item["id"]] for item in pendentes.values("id", "codlot")]
                        max_workers = min(len(grupos_ids), MAX_WORKERS_LOGS_BAIXA_COMPONENTES)
                        if max_workers <= 1:
                            sucessos, erros, falhados = _executar_envio_com_conexao_limpa(pendentes)
                            sucessos_total += sucessos
                            erros_total += erros
                            codlots_falhados.update(falhados)
                        else:
                            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                                futures = [
                                    executor.submit(
                                        _executar_envio_com_conexao_limpa,
                                        BaixaComponente.objects.filter(
                                            id__in=grupo_ids,
                                            status=BaixaComponente.Status.PROCESSANDO,
                                        ).order_by("id"),
                                    )
                                    for grupo_ids in grupos_ids
                                ]
                                for future in as_completed(futures):
                                    sucessos, erros, falhados = future.result()
                                    sucessos_total += sucessos
                                    erros_total += erros
                                    codlots_falhados.update(falhados)
                    else:
                        sucessos, erros, falhados = _executar_envio_com_conexao_limpa(pendentes)
                        sucessos_total += sucessos
                        erros_total += erros
                        codlots_falhados.update(falhados)
                    if ids is not None:
                        break
            finally:
                PROCESSAMENTO_BAIXAS_COMPONENTES_LOCK.release()
            return sucessos_total, erros_total
    finally:
        connections.close_all()


def disparar_envio_baixas_componentes(ids=None):
    threading.Thread(
        target=processar_baixas_componentes_pendentes, args=(ids,), daemon=True
    ).start()


def _codemp_usuario(request):
    """Deriva o codemp do usuário logado; mesma fonte usada em toda a fila de baixas."""
    empresa_usuario = getattr(getattr(request.user, "filial", None), "empresa", None)
    return getattr(empresa_usuario, "codemp", None)


def liberar_baixas_componentes_processando_antigas(idade_segundos=None):
    queryset = BaixaComponente.objects.filter(status=BaixaComponente.Status.PROCESSANDO)
    if idade_segundos is not None:
        queryset = queryset.filter(data_hora__lt=timezone.now() - timedelta(seconds=idade_segundos))
    return queryset.update(
        status=BaixaComponente.Status.NAO_INTEGRADO,
        log="Processamento anterior interrompido. Disponível para novo envio.",
        data_hora=timezone.now(),
    )


@login_required
def logs_baixa_componentes(request):
    codemp_usuario = _codemp_usuario(request)
    queryset_base = BaixaComponente.objects.select_related(
        "recurso", "recurso__centro_recurso", "usuario"
    )
    if not request.user.is_staff:
        queryset_base = (
            queryset_base.filter(codemp=codemp_usuario) if codemp_usuario else queryset_base.none()
        )

    search_query = request.GET.get("search", "").strip()
    if search_query:
        search_date = None
        if "/" in search_query:
            try:
                search_date = datetime.strptime(search_query, "%d/%m/%Y").strftime("%Y-%m-%d")
            except ValueError:
                pass
        query = consulta_de_busca(search_query)
        if search_date:
            query |= Q(data_hora__icontains=search_date) | Q(datmov__icontains=search_date)
        queryset_base = queryset_base.filter(query)

    mesmo_lote_processando = BaixaComponente.objects.filter(
        status=BaixaComponente.Status.PROCESSANDO, codlot=OuterRef("codlot")
    )
    baixa_anterior_pendente = BaixaComponente.objects.filter(
        codlot=OuterRef("codlot"),
        status=BaixaComponente.Status.NAO_INTEGRADO,
        id__lt=OuterRef("id"),
    )
    baixas_list = queryset_base.annotate(
        tem_processamento_no_lote=Exists(mesmo_lote_processando),
        tem_baixa_anterior_pendente=Exists(baixa_anterior_pendente),
    ).order_by("-id")
    baixas = Paginator(baixas_list, 20).get_page(request.GET.get("page"))
    bloqueados_ids = [
        baixa.id
        for baixa in baixas
        if baixa.status == BaixaComponente.Status.NAO_INTEGRADO
        and (
            PROCESSAMENTO_BAIXAS_COMPONENTES_LOCK.locked()
            or baixa.tem_processamento_no_lote
            or baixa.tem_baixa_anterior_pendente
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
        "producao/logs_baixa_componentes.html",
        {
            "baixas": baixas,
            "bloqueados_ids": bloqueados_ids,
            "search_query": search_query,
            "rotulos_busca": ROTULOS_BUSCA,
            "pode_excluir_pendencias": pode_excluir_pendencias,
        },
    )


@login_required
@require_POST
def enviar_baixa_componente_log(request, pk):
    # Achado de autorização: sem restringir por codemp, um não-staff que soubesse
    # o pk conseguia reenviar ao Sapiens uma baixa de componente de outra filial.
    queryset = BaixaComponente.objects.all()
    if not request.user.is_staff:
        codemp_usuario = _codemp_usuario(request)
        queryset = queryset.filter(codemp=codemp_usuario) if codemp_usuario else queryset.none()
    baixa = get_object_or_404(queryset, pk=pk)
    if (
        baixa.status != BaixaComponente.Status.NAO_INTEGRADO
        or PROCESSAMENTO_BAIXAS_COMPONENTES_LOCK.locked()
    ):
        messages.warning(request, "A baixa não está disponível para envio no momento.")
    elif BaixaComponente.objects.filter(
        codlot=baixa.codlot,
        status__in=[BaixaComponente.Status.NAO_INTEGRADO, BaixaComponente.Status.PROCESSANDO],
        id__lt=baixa.id,
    ).exists():
        messages.warning(request, "A baixa anterior do mesmo lote ainda não foi integrada.")
    else:
        reservadas = reservar_baixas_componentes_para_envio(BaixaComponente.objects.filter(pk=pk))
        if reservadas.exists():
            disparar_envio_baixas_componentes([pk])
            messages.info(request, f"Processamento em background iniciado para a baixa {pk}.")
        else:
            messages.warning(request, "A baixa não está disponível para envio.")
    return redirect("logs_baixa_componentes")


@login_required
@require_POST
def enviar_todas_baixas_componentes(request):
    if PROCESSAMENTO_BAIXAS_COMPONENTES_LOCK.locked():
        messages.warning(
            request, "Já existe um processamento de baixas de componentes em andamento."
        )
        return redirect("logs_baixa_componentes")

    # Achado de autorização: "enviar todas" sem staff não pode disparar o
    # processamento global (todas as filiais) — só as pendentes da própria
    # empresa entram na fila.
    pendentes = BaixaComponente.objects.filter(status=BaixaComponente.Status.NAO_INTEGRADO)
    if not request.user.is_staff:
        codemp_usuario = _codemp_usuario(request)
        pendentes = pendentes.filter(codemp=codemp_usuario) if codemp_usuario else pendentes.none()

    if not pendentes.exists():
        messages.info(request, "Não há baixas de componentes pendentes para enviar.")
        return redirect("logs_baixa_componentes")

    if request.user.is_staff:
        disparar_envio_baixas_componentes()
    else:
        reservadas = reservar_baixas_componentes_para_envio(pendentes, uma_por_codlot=True)
        ids_reservados = list(reservadas.values_list("id", flat=True))
        if not ids_reservados:
            messages.warning(request, "As baixas pendentes já estão em processamento.")
            return redirect("logs_baixa_componentes")
        disparar_envio_baixas_componentes(ids_reservados)

    messages.info(
        request, "Processamento em background iniciado para as baixas de componentes pendentes."
    )
    return redirect("logs_baixa_componentes")


# Exclusão unificada das filas: quem recebe pode_excluir_pendencias_integracao
# exclui (staff e superusuário passam pelo bypass do decorator); sem guard
# interno adicional.
@permissao_requerida("producao.pode_excluir_pendencias_integracao")
@require_POST
def excluir_baixa_componente(request, pk):
    # Restrição de filial: não-staff não exclui baixa de
    # outra empresa mesmo sabendo o pk.
    queryset = BaixaComponente.objects.all()
    if not request.user.is_staff:
        codemp_usuario = _codemp_usuario(request)
        queryset = queryset.filter(codemp=codemp_usuario) if codemp_usuario else queryset.none()
    baixa = get_object_or_404(queryset, pk=pk)

    if baixa.status != BaixaComponente.Status.NAO_INTEGRADO:
        messages.error(request, "Apenas baixas pendentes podem ser excluídas.")
    else:
        baixa.delete()
        messages.success(request, f"Baixa {pk} excluída com sucesso.")
    return redirect("logs_baixa_componentes")


@permissao_requerida("producao.pode_excluir_pendencias_integracao")
@require_POST
def excluir_todas_baixas_componentes(request):

    # Exclusão em massa também precisa respeitar a filial do não-staff.
    queryset = BaixaComponente.objects.filter(status=BaixaComponente.Status.NAO_INTEGRADO)
    if not request.user.is_staff:
        codemp_usuario = _codemp_usuario(request)
        queryset = queryset.filter(codemp=codemp_usuario) if codemp_usuario else queryset.none()

    total, _ = queryset.delete()
    messages.info(
        request,
        "Não há baixas pendentes para excluir."
        if not total
        else f"Todos os {total} logs de baixa pendentes foram excluídos com sucesso.",
    )
    return redirect("logs_baixa_componentes")
