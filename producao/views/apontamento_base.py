import importlib
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, transaction
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_duration
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.models import CentroRecurso, Empresa, MotivoAbrangencia, Recurso
from producao.models import JustificativaParada, LogTrocaOPAtiva, ParadaMaquina, Sequenciamento
from producao.utils.paradas import (
    congelar_justificativa_aberta,
    pode_encerrar_parada,
    reconciliar_periodos_da_parada,
)
from producao.utils.paradas_manuais import criar_parada_manual
from SIGMA.autorizacao import permissao_requerida
from SIGMA.integracoes.oracle import cursor_oracle_erp

VIEWS_FLUXO_BASE_OP_UNICA = {0, 1, 2}


def recurso_usa_fluxo_base_op_unica(recurso):
    """Indica se o recurso usa o sequenciamento legado de uma OP por vez."""
    return (
        recurso.view_id if recurso and recurso.view_id is not None else 0
    ) in VIEWS_FLUXO_BASE_OP_UNICA


def _codigo(valor):
    return str(valor or "").strip()


def _codemp_recurso(recurso):
    return recurso.centro_recurso.setor.departamento.filial.empresa.codemp


def motivos_ativos_recurso(recurso, incluir_status=False):
    codemp = _codemp_recurso(recurso)
    vinculos = set(
        MotivoAbrangencia.objects.filter(recurso=recurso, codemp=codemp).values_list(
            "codgpm", "codmtv"
        )
    )
    if not vinculos:
        return ([], False) if incluir_status else []

    try:
        with cursor_oracle_erp() as cursor:
            cursor.execute(
                """
                SELECT g.usu_codgpm, g.usu_desgpm, e.codmtv, e.desmtv
                  FROM usu_t018gpm g
                  INNER JOIN usu_t018mvp m
                    ON m.usu_codemp = g.usu_codemp
                   AND m.usu_codgmp = g.usu_codgpm
                  INNER JOIN e018mtv e
                    ON e.codemp = m.usu_codemp
                   AND e.codmtv = m.usu_codmtv
                 WHERE g.usu_codemp = :codemp
                   AND g.usu_sitgpm = 'A'
                   AND e.sitmtv = 'A'
                 ORDER BY g.usu_codgpm, e.desmtv, e.codmtv
                """,
                {"codemp": codemp},
            )
            registros = cursor.fetchall()
    except DatabaseError:
        return ([], True) if incluir_status else []

    grupos = {}
    for codgpm, desgpm, codmtv, desmtv in registros:
        chave = (int(codgpm), _codigo(codmtv))
        if chave not in vinculos:
            continue
        grupos.setdefault(
            int(codgpm),
            {"codigo": int(codgpm), "descricao": _codigo(desgpm), "motivos": []},
        )["motivos"].append({"codigo": _codigo(codmtv), "descricao": _codigo(desmtv)})
    motivos = list(grupos.values())
    return (motivos, False) if incluir_status else motivos


def _motivo_ativo_e_vinculado(recurso, codgpm, codmtv):
    codemp = _codemp_recurso(recurso)
    if not MotivoAbrangencia.objects.filter(
        recurso=recurso, codemp=codemp, codgpm=codgpm, codmtv=codmtv
    ).exists():
        return False
    try:
        with cursor_oracle_erp() as cursor:
            cursor.execute(
                """
                SELECT 1
                  FROM usu_t018gpm g
                  INNER JOIN usu_t018mvp m ON m.usu_codemp = g.usu_codemp AND m.usu_codgmp = g.usu_codgpm
                  INNER JOIN e018mtv e ON e.codemp = m.usu_codemp AND e.codmtv = m.usu_codmtv
                 WHERE g.usu_codemp = :codemp AND g.usu_codgpm = :codgpm AND e.codmtv = :codmtv
                   AND g.usu_sitgpm = 'A' AND e.sitmtv = 'A'
                """,
                {"codemp": codemp, "codgpm": codgpm, "codmtv": codmtv},
            )
            return cursor.fetchone() is not None
    except DatabaseError:
        return False


def _operador_ativo(recurso, numcad):
    with cursor_oracle_erp() as cursor:
        cursor.execute(
            "SELECT nomope FROM e906ope WHERE codemp=:codemp AND numcad=:numcad AND sitope='A'",
            {"codemp": _codemp_recurso(recurso), "numcad": numcad},
        )
        resultado = cursor.fetchone()
        if resultado:
            resultado = dict(
                zip((coluna[0].lower() for coluna in cursor.description), resultado, strict=False)
            )
    return _codigo(resultado["nomope"]) if resultado else None


def _retorno_apontamento(request):
    destino = request.POST.get("next")
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return destino
    return reverse("apontamento_base")


def empresas_visiveis_apontamento(usuario):
    if usuario.is_staff:
        return Empresa.objects.filter(ativa=True).order_by("nome")
    filial = getattr(usuario, "filial", None)
    if filial and filial.empresa_id:
        return Empresa.objects.filter(pk=filial.empresa_id, ativa=True)
    return Empresa.objects.none()


def recursos_visiveis_apontamento(usuario):
    recursos = Recurso.objects.all()
    if usuario.is_staff:
        return recursos
    filial = getattr(usuario, "filial", None)
    if not filial or not filial.empresa_id:
        return recursos.none()
    return recursos.filter(
        centro_recurso__setor__departamento__filial__empresa_id=filial.empresa_id
    )


def _recurso(usuario, recurso_id):
    return (
        recursos_visiveis_apontamento(usuario)
        .select_related("centro_recurso__setor__departamento__filial__empresa")
        .filter(pk=recurso_id)
        .first()
    )


def _recurso_para_acao(request, recurso_id):
    """Resolve o recurso dentro do escopo do usuário para as rotas de ação.

    A autorização de apontamento é responsabilidade do decorator das rotas;
    aqui resta o escopo de dados (recurso fora da empresa do usuário não é
    alcançável mesmo com permissão).
    """
    recurso = _recurso(request.user, recurso_id)
    if not recurso:
        return None, HttpResponseForbidden("Recurso não disponível para o seu usuário.")
    return recurso, None


def _tempo_parada(parada, referencia=None):
    return (parada.fim or referencia or timezone.now().replace(microsecond=0)) - parada.inicio


def _tempo_justificado(parada, referencia=None):
    limite = parada.fim or referencia or timezone.now().replace(microsecond=0)
    total = timedelta()
    for justificativa in parada.justificativas.all():
        total += (
            justificativa.tempo
            if justificativa.tempo is not None
            else limite - justificativa.parcial
        )
    return total


def _tempo_legivel(tempo):
    segundos = max(0, int(tempo.total_seconds()))
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"


def parada_bloqueia_apontamento(parada, referencia=None):
    if parada.fim is None:
        return True
    return _tempo_justificado(parada, referencia) < _tempo_parada(parada, referencia)


# Ações de apontamento exigem a permissão em rota própria; a tela que as
# chama permanece livre (a versão aberta depende do cadastro do recurso).
@permissao_requerida("producao.pode_apontar")
@require_POST
def justificar_paradas(request, recurso_id):
    try:
        numcad = int(request.POST.get("numcad", ""))
    except TypeError, ValueError:
        return HttpResponseBadRequest("Informe um operador válido.")
    recurso, resposta_erro = _recurso_para_acao(request, recurso_id)
    if resposta_erro:
        return resposta_erro
    if not _operador_ativo(recurso, numcad):
        messages.error(request, "Operador não encontrado ou inativo no ERP.")
        return redirect(_retorno_apontamento(request))

    with transaction.atomic():
        paradas = list(
            ParadaMaquina.objects.select_for_update()
            .filter(
                recurso=recurso,
            )
            .prefetch_related("justificativas")
            .order_by("inicio", "id")
        )
        pendentes = [parada for parada in paradas if parada_bloqueia_apontamento(parada)]
        if not pendentes:
            messages.error(request, "Não há paradas pendentes de justificativa neste recurso.")
            return redirect(_retorno_apontamento(request))

        for parada in pendentes:
            justificativas = list(parada.justificativas.all())
            prefixo = f"novo_motivo_{parada.id}_"
            possui_campos_sequenciais = any(
                chave.startswith(f"motivo_{parada.id}_") or chave.startswith(prefixo)
                for chave in request.POST
            )
            motivo_legado = request.POST.get(f"motivo_{parada.id}", "")
            if justificativas and not possui_campos_sequenciais:
                continue
            ids_remover = request.POST.getlist(f"remover_justificativa_{parada.id}")
            if ids_remover:
                if (
                    not all(item.isdigit() for item in ids_remover)
                    or len(set(ids_remover)) != len(ids_remover)
                    or len(ids_remover) > len(justificativas)
                    or {int(item) for item in ids_remover}
                    != {item.id for item in justificativas[-len(ids_remover) :]}
                ):
                    messages.error(request, "Somente a última justificativa pode ser excluída.")
                    return redirect(_retorno_apontamento(request))
                justificativas = justificativas[: -len(ids_remover)]

            motivos = []
            tempos = []
            for justificativa in justificativas:
                try:
                    codgpm, codmtv = request.POST.get(
                        f"motivo_{parada.id}_{justificativa.id}", ""
                    ).split("|", 1)
                    codgpm = int(codgpm)
                except TypeError, ValueError:
                    messages.error(request, "Informe o motivo de todas as justificativas.")
                    return redirect(_retorno_apontamento(request))
                tempo_texto = (
                    request.POST.get(f"tempo_{parada.id}_{justificativa.id}") or ""
                ).strip()
                tempo = parse_duration(tempo_texto) if tempo_texto else None
                if tempo is not None:
                    tempo -= timedelta(microseconds=tempo.microseconds)
                if tempo_texto and tempo is None:
                    messages.error(request, "Tempo inválido. Use HH:MM:SS.")
                    return redirect(_retorno_apontamento(request))
                if not _motivo_ativo_e_vinculado(recurso, codgpm, _codigo(codmtv)):
                    messages.error(
                        request, "Há motivo inativo no ERP ou não vinculado a este recurso."
                    )
                    return redirect(_retorno_apontamento(request))
                motivos.append(_codigo(codmtv))
                tempos.append(tempo)

            if motivo_legado and not possui_campos_sequenciais:
                try:
                    codgpm, codmtv = motivo_legado.split("|", 1)
                    codgpm = int(codgpm)
                except TypeError, ValueError:
                    messages.error(request, "Informe o motivo de todas as paradas pendentes.")
                    return redirect(_retorno_apontamento(request))
                if not _motivo_ativo_e_vinculado(recurso, codgpm, _codigo(codmtv)):
                    messages.error(
                        request, "Há motivo inativo no ERP ou não vinculado a este recurso."
                    )
                    return redirect(_retorno_apontamento(request))
                motivos.append(_codigo(codmtv))
                tempos.append(None if parada.fim is None else _tempo_parada(parada))

            for indice in sorted(
                (
                    chave.removeprefix(prefixo)
                    for chave in request.POST
                    if chave.startswith(prefixo) and chave.removeprefix(prefixo).isdigit()
                ),
                key=int,
            ):
                try:
                    codgpm, codmtv = request.POST.get(f"{prefixo}{indice}", "").split("|", 1)
                    codgpm = int(codgpm)
                except TypeError, ValueError:
                    messages.error(request, "Informe o motivo de cada nova justificativa.")
                    return redirect(_retorno_apontamento(request))
                tempo_texto = (request.POST.get(f"novo_tempo_{parada.id}_{indice}") or "").strip()
                tempo = parse_duration(tempo_texto) if tempo_texto else None
                if tempo is not None:
                    tempo -= timedelta(microseconds=tempo.microseconds)
                if tempo_texto and tempo is None:
                    messages.error(request, "Tempo inválido. Use HH:MM:SS.")
                    return redirect(_retorno_apontamento(request))
                if not _motivo_ativo_e_vinculado(recurso, codgpm, _codigo(codmtv)):
                    messages.error(
                        request, "Há motivo inativo no ERP ou não vinculado a este recurso."
                    )
                    return redirect(_retorno_apontamento(request))
                motivos.append(_codigo(codmtv))
                tempos.append(tempo)

            if not motivos:
                messages.error(request, "Informe ao menos uma justificativa para cada parada.")
                return redirect(_retorno_apontamento(request))

            if parada.fim is None:
                tempos_anteriores = tempos[:-1]
                if any(tempo is None or tempo <= timedelta() for tempo in tempos_anteriores):
                    messages.error(
                        request,
                        "Preencha o tempo, maior que zero, de todas as justificativas anteriores.",
                    )
                    return redirect(_retorno_apontamento(request))
                if (
                    sum(tempos_anteriores, timedelta())
                    > timezone.now().replace(microsecond=0) - parada.inicio
                ):
                    messages.error(
                        request,
                        "A soma das justificativas não pode ultrapassar o tempo decorrido da parada.",
                    )
                    return redirect(_retorno_apontamento(request))
                tempos = [*tempos_anteriores, None]
            else:
                if (
                    any(tempo is None for tempo in tempos)
                    or any(tempo < timedelta() for tempo in tempos)
                    or any(tempo == timedelta() for tempo in tempos[:-1])
                ):
                    messages.error(
                        request,
                        "Informe tempos válidos; tempo zerado só é permitido na última sequência.",
                    )
                    return redirect(_retorno_apontamento(request))
                if sum(tempos, timedelta()) != parada.fim - parada.inicio:
                    messages.error(
                        request,
                        "A soma das justificativas deve ser igual ao tempo total da parada.",
                    )
                    return redirect(_retorno_apontamento(request))

            agora = timezone.now().replace(microsecond=0)
            parada.justificativas.all().delete()
            parcial = parada.inicio
            for sequencia, (motivo, tempo) in enumerate(
                zip(motivos, tempos, strict=False), start=1
            ):
                JustificativaParada.objects.create(
                    parada=parada,
                    sequencia=sequencia,
                    motivo=motivo,
                    parcial=parcial,
                    tempo=tempo,
                    data_hora=agora,
                )
                if tempo is not None:
                    parcial += tempo

    messages.success(request, "Todas as paradas pendentes foram justificadas.")
    return redirect(_retorno_apontamento(request))


@permissao_requerida("producao.pode_apontar")
@require_POST
def encerrar_paradas(request, recurso_id):
    recurso, resposta_erro = _recurso_para_acao(request, recurso_id)
    if resposta_erro:
        return resposta_erro
    with transaction.atomic():
        recurso, periodos = _bloquear_recurso_e_periodos(recurso)
        paradas = list(
            ParadaMaquina.objects.select_for_update()
            .filter(
                recurso=recurso,
            )
            .prefetch_related("justificativas")
            .order_by("id")
        )
        if any(not parada.justificativas.exists() for parada in paradas):
            messages.error(request, "Justifique todas as paradas antes de marcar o fim.")
            return redirect(_retorno_apontamento(request))
        paradas_abertas = [parada for parada in paradas if parada.fim is None]
        if not paradas_abertas:
            messages.error(request, "Não há parada aberta neste recurso.")
            return redirect(_retorno_apontamento(request))
        agora = timezone.now().replace(microsecond=0)
        if any(not pode_encerrar_parada(parada, agora) for parada in paradas_abertas):
            messages.error(
                request, "Aguarde o tempo mínimo configurado antes de encerrar a parada."
            )
            return redirect(_retorno_apontamento(request))
        for parada in paradas_abertas:
            parada.fim = agora
            parada.data_hora = agora
            parada.usuario = request.user
            parada.save(update_fields=["fim", "data_hora", "usuario"])
            congelar_justificativa_aberta(parada, agora=agora)
            reconciliar_periodos_da_parada(parada, periodos=periodos, agora=agora)

    messages.success(request, "Fim registrado para todas as paradas abertas.")
    return redirect(_retorno_apontamento(request))


def contexto_parada_recurso(recurso):
    if not recurso or not recurso.aponta_parada or not recurso.exibir_jus:
        return {
            "exibir_justificativas": False,
            "parada_aberta": False,
            "parada_aberta_id": None,
        }

    paradas_pendentes = list(
        ParadaMaquina.objects.filter(recurso=recurso)
        .prefetch_related("justificativas")
        .order_by("-inicio", "-id")
    )
    paradas_pendentes = [
        parada for parada in paradas_pendentes if parada_bloqueia_apontamento(parada)
    ]
    agora = timezone.now().replace(microsecond=0)
    for parada in paradas_pendentes:
        parada.tempo_total_legivel = _tempo_legivel(_tempo_parada(parada, agora))
        parada.justificativas_ordenadas = list(parada.justificativas.all())
        for justificativa in parada.justificativas_ordenadas:
            justificativa.tempo_legivel = (
                _tempo_legivel(justificativa.tempo) if justificativa.tempo is not None else ""
            )
            justificativa.tempo_exibicao = _tempo_legivel(
                justificativa.tempo
                if justificativa.tempo is not None
                else agora - justificativa.parcial
            )
            justificativa.tempo_em_andamento = justificativa.tempo is None
        parada.tem_justificativa = bool(parada.justificativas_ordenadas)
        parada.ultima_justificativa = (
            parada.justificativas_ordenadas[-1] if parada.tem_justificativa else None
        )
    parada_aberta = next((parada for parada in paradas_pendentes if parada.fim is None), None)
    motivos_parada, erro_motivos_parada = (
        motivos_ativos_recurso(recurso, incluir_status=True) if paradas_pendentes else ([], False)
    )
    return {
        "exibir_justificativas": True,
        "parada_aberta": bool(parada_aberta),
        "parada_bloqueante": bool(paradas_pendentes),
        "parada_aberta_id": parada_aberta.id if parada_aberta else None,
        "paradas_pendentes": paradas_pendentes,
        "tem_parada_sem_justificativa": any(
            not parada.tem_justificativa for parada in paradas_pendentes
        ),
        "motivos_parada": motivos_parada,
        "erro_motivos_parada": erro_motivos_parada,
    }


def recurso_tem_parada_bloqueante(recurso):
    if not recurso or not recurso.aponta_parada or not recurso.exibir_jus:
        return False
    paradas = ParadaMaquina.objects.filter(recurso=recurso).prefetch_related("justificativas")
    return any(parada_bloqueia_apontamento(parada) for parada in paradas)


def _bloquear_recurso_e_periodos(recurso, apenas_abertos=False):
    """Trava recurso e períodos antes de qualquer parada relacionada.

    Os fluxos que alteram paradas seguem sempre Recurso ->
    LogTrocaOPAtiva -> ParadaMaquina. O chamador deve estar em transação.
    """
    recurso = Recurso.objects.select_for_update().get(pk=recurso.pk)
    periodos = LogTrocaOPAtiva.objects.select_for_update().filter(recurso=recurso)
    if apenas_abertos:
        periodos = periodos.filter(horario_saida__isnull=True)
    return recurso, list(periodos.order_by("id"))


def trocar_periodo_produtivo_fluxo_unico(
    *, recurso, usuario, origem, op, estagio, seqrot, horario_troca, id_operador
):
    """Troca a OP legada preservando uma parada física eventualmente aberta.

    A trava do recurso precisa ocorrer antes de qualquer período para manter a
    mesma ordem da telemetria e evitar uma parada aberta sem vínculo com a OP
    recém-criada.
    """
    horario_troca = horario_troca.replace(microsecond=0)
    with transaction.atomic():
        recurso, periodos_abertos = _bloquear_recurso_e_periodos(recurso, apenas_abertos=True)
        if recurso_tem_parada_bloqueante(recurso):
            raise ValueError("Não é possível trocar a OP enquanto houver parada bloqueante.")
        if len(periodos_abertos) > 1:
            raise ValueError(
                "Este recurso possui mais de uma OP ativa. A troca deve ser tratada pelo fluxo de alocação de OPs."
            )
        if periodos_abertos:
            LogTrocaOPAtiva.objects.filter(pk=periodos_abertos[0].pk).update(
                horario_saida=horario_troca
            )
        return LogTrocaOPAtiva.objects.create(
            recurso=recurso,
            usuario=usuario,
            origem=origem,
            op=op,
            estagio=estagio,
            seqrot=seqrot,
            horario_troca=horario_troca,
            id_operador=id_operador,
        )


@permissao_requerida("producao.pode_apontar")
@require_POST
def desacoplar_op_ativa(request, recurso_id):
    recurso, resposta_erro = _recurso_para_acao(request, recurso_id)
    if resposta_erro:
        return resposta_erro
    if not recurso_usa_fluxo_base_op_unica(recurso):
        messages.error(
            request,
            "O desacoplamento deste recurso deve ser realizado pela sua tela de apontamento.",
        )
        return redirect(_retorno_apontamento(request))
    if not (
        request.session.get(f"numcad_operador_{recurso_id}")
        and request.session.get(f"nome_operador_{recurso_id}")
    ):
        messages.error(request, "Valide o operador antes de desacoplar a OP.")
        return redirect(_retorno_apontamento(request))

    with transaction.atomic():
        recurso, periodos = _bloquear_recurso_e_periodos(recurso)
        paradas = list(
            ParadaMaquina.objects.select_for_update()
            .filter(recurso=recurso)
            .prefetch_related("justificativas")
            .order_by("id")
        )
        if any(parada_bloqueia_apontamento(parada) for parada in paradas):
            messages.error(
                request,
                "Não é possível desacoplar a OP enquanto houver parada aberta ou pendente de justificativa.",
            )
            return redirect(_retorno_apontamento(request))

        periodos_abertos = [periodo for periodo in periodos if periodo.horario_saida is None]
        if not periodos_abertos:
            messages.error(request, "Não há OP ativa para desacoplar neste recurso.")
            return redirect(_retorno_apontamento(request))
        if len(periodos_abertos) > 1:
            messages.error(
                request,
                "Este recurso possui mais de uma OP ativa. O desacoplamento deve ser tratado pelo fluxo de alocação de OPs.",
            )
            return redirect(_retorno_apontamento(request))

        LogTrocaOPAtiva.objects.filter(pk__in=[periodo.id for periodo in periodos_abertos]).update(
            horario_saida=timezone.now().replace(microsecond=0)
        )

    messages.success(request, "OP desacoplada e período produtivo encerrado.")
    return redirect(_retorno_apontamento(request))


@permissao_requerida("producao.pode_apontar")
@require_POST
def abrir_parada_manual_apontamento(request, recurso_id):
    recurso, resposta_erro = _recurso_para_acao(request, recurso_id)
    if resposta_erro:
        return resposta_erro

    # V1/V2 exigem o operador digitado no próprio form da parada. A V3 não
    # tem esse campo: o gate de operador já é o de produção validado na
    # sessão (mesmo usado para liberar peso/Apontar), então o numcad vem daí.
    if recurso_usa_fluxo_base_op_unica(recurso):
        try:
            numcad = int(request.POST.get("numcad", ""))
        except TypeError, ValueError:
            messages.error(request, "Valide um operador antes de abrir a parada.")
            return redirect(_retorno_apontamento(request))
    else:
        numcad = request.session.get(f"numcad_operador_producao_{recurso_id}")
        if not numcad:
            messages.error(request, "Valide o operador de produção antes de abrir a parada.")
            return redirect(_retorno_apontamento(request))

    try:
        with transaction.atomic():
            criar_parada_manual(usuario=request.user, recurso=recurso, numcad=numcad)
    except ValueError as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, "Parada manual aberta.")
    return redirect(_retorno_apontamento(request))


@login_required
def apontamento_base_view(request):
    """View para seleção de filtros e listagem de sequenciamento ou detalhamento via versão."""
    # As ações internas das telas versionadas enviam estes filtros em campos
    # ocultos do POST. Usá-los como fallback mantém o recurso selecionado
    # mesmo quando o navegador não preserva a query string no submit.
    empresa_id = request.POST.get("empresa") or request.GET.get("empresa", "")
    centro_id = request.POST.get("centro") or request.GET.get("centro", "")
    recurso_id = request.POST.get("recurso") or request.GET.get("recurso", "")
    codbar = request.POST.get("codbar") or request.GET.get("codbar", "")

    empresas = empresas_visiveis_apontamento(request.user)

    # Se houver codbar, identifica o recurso e redireciona ou processa a versão
    if codbar:
        try:
            from .apontamentos_v1 import decode_cod_barras

            _, cod_ori_bar, num_op_bar, cod_etg_bar, seq_rot_bar = decode_cod_barras(codbar)
            sequenciamento = (
                Sequenciamento.objects.filter(
                    op=num_op_bar,
                    origem=str(cod_ori_bar),
                    estagio=int(cod_etg_bar),
                    seqrot=int(seq_rot_bar),
                )
                .filter(recurso__in=recursos_visiveis_apontamento(request.user))
                .select_related("recurso__centro_recurso__setor__departamento__filial__empresa")
                .first()
            )
            if sequenciamento:
                recurso_id = str(sequenciamento.recurso.id)
                centro_id = str(sequenciamento.recurso.centro_recurso_id)
                empresa_id = str(
                    sequenciamento.recurso.centro_recurso.setor.departamento.filial.empresa_id
                )
        except Exception:
            pass

    # Seleção automática de empresa no primeiro acesso
    if not empresa_id and empresas.exists():
        empresa_id = str(empresas.first().id)

    # Limpeza em cascata de filtros (SÓ se não for via codbar)
    if not codbar:
        if not empresa_id:
            centro_id = recurso_id = ""
        elif not centro_id:
            recurso_id = ""

    if empresa_id and not empresas.filter(pk=empresa_id).exists():
        empresa_id = centro_id = recurso_id = ""

    # Dados para os selects
    centros = (
        CentroRecurso.objects.filter(
            setor__departamento__filial__empresa_id=empresa_id, recursos__ativo=True
        )
        .exclude(descricao__icontains="Geral")
        .distinct()
        .order_by("descricao")
        if empresa_id
        else []
    )

    if centro_id and not centros.filter(pk=centro_id).exists():
        centro_id = recurso_id = ""

    # Valida se o recurso pertence ao centro e ao escopo do usuário.
    if recurso_id and (
        not centro_id
        or not recursos_visiveis_apontamento(request.user)
        .filter(pk=recurso_id, centro_recurso_id=centro_id)
        .exists()
    ):
        recurso_id = ""

    recursos = (
        recursos_visiveis_apontamento(request.user)
        .filter(centro_recurso_id=centro_id, ativo=True)
        .exclude(descricao__icontains="Geral")
        .order_by("descricao")
        if centro_id
        else []
    )

    recurso_id_atual_sessao = request.session.get("recurso_apontamento_atual", "")
    if recurso_id != recurso_id_atual_sessao:
        for chave in list(request.session.keys()):
            if chave.startswith("numcad_operador_") or chave.startswith("nome_operador_"):
                request.session.pop(chave, None)
        request.session["recurso_apontamento_atual"] = recurso_id or ""

    # Lista de sequenciamento
    sequencias = (
        Sequenciamento.objects.filter(recurso_id=recurso_id).order_by("ordenacao")
        if recurso_id
        else []
    )

    recurso_selecionado = None
    op_ativa_recurso = ""
    if recurso_id:
        try:
            recurso_selecionado = recursos_visiveis_apontamento(request.user).get(id=recurso_id)
            log_op_ativa = (
                LogTrocaOPAtiva.objects.filter(recurso_id=recurso_id, horario_saida__isnull=True)
                .order_by("-horario_troca")
                .first()
            )
            op_ativa_recurso = log_op_ativa.codigo_barra if log_op_ativa else ""
        except Recurso.DoesNotExist:
            recurso_selecionado = None

    # Determina qual versão de apontamento chamar se um recurso estiver selecionado.
    # V1/V2 trabalham com uma OP por vez e exigem codbar; a V3 (Multi-OP) gerencia
    # várias OPs dentro da própria tela e não depende de um codbar para abrir.
    # No FINAL para garantir que IDs e listas já estejam resolvidos no request.GET
    view_id = (
        recurso_selecionado.view_id
        if recurso_selecionado and recurso_selecionado.view_id is not None
        else 0
    )
    if recurso_id and (codbar or view_id == 3) and view_id != 0:
        # Sincroniza os IDs resolvidos de volta para o request.GET se necessário
        # (Algumas views internas dependem de request.GET.get para filtros)
        mutable_get = request.GET.copy()
        mutable_get["empresa"] = empresa_id
        mutable_get["centro"] = centro_id
        mutable_get["recurso"] = recurso_id
        request.GET = mutable_get

        module_name = f"producao.views.apontamentos_v{view_id}"
        try:
            module = importlib.import_module(module_name)
            apontamentos_view_func = module.apontamentos_view
        except ImportError, AttributeError:
            # Só cai no fallback abaixo quando a versão de tela configurada
            # não existe de fato — qualquer exceção levantada DENTRO da view
            # (apontamentos_view_func) deve propagar e aparecer como erro 500,
            # nunca ser escondida atrás da tela "Aguardando código de barras".
            pass
        else:
            return apontamentos_view_func(request)

    pode_apontar = request.user.is_staff or request.user.has_perm("producao.pode_apontar")

    return render(
        request,
        "producao/apontamento_base.html",
        {
            "empresas": empresas,
            "empresa_id": empresa_id,
            "centros": centros,
            "centro_id": centro_id,
            "recursos": recursos,
            "recurso_id": recurso_id,
            "sequencias": sequencias,
            "recurso_selecionado": recurso_selecionado,
            "op_ativa_recurso": op_ativa_recurso,
            "fluxo_base_op_unica": recurso_usa_fluxo_base_op_unica(recurso_selecionado),
            "codbar": codbar,
            "pode_apontar": pode_apontar,
            "operador_validado": bool(
                recurso_id
                and request.session.get(f"numcad_operador_{recurso_id}")
                and request.session.get(f"nome_operador_{recurso_id}")
            ),
            **contexto_parada_recurso(recurso_selecionado),
        },
    )
