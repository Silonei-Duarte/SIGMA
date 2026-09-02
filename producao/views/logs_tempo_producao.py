from copy import copy
from datetime import timedelta
from typing import Final

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_duration
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from producao.models import JustificativaParada, LogTrocaOPAtiva, PacoteTempoERP, ParadaMaquina
from producao.utils.paradas import alterar_horarios_parada
from producao.utils.paradas_manuais import (
    criar_parada_manual,
    data_hora_local,
    usuario_pode_abrir_parada_manual,
)
from producao.views.apontamento_base import (
    _motivo_ativo_e_vinculado,
    motivos_ativos_recurso,
    recursos_visiveis_apontamento,
)
from SIGMA.autorizacao import permissao_requerida
from SIGMA.integracoes.oracle import cursor_oracle_erp


def _periodos_visiveis(usuario):
    return LogTrocaOPAtiva.objects.filter(recurso__in=recursos_visiveis_apontamento(usuario))


# Fonte única da busca (consulta e instrução da tela): a consulta varre
# exatamente estes campos e a instrução exibida sai dos mesmos rótulos —
# teste anti-divergência em producao/tests/test_busca_logs.py impede que
# as duas pontas voltem a divergir. Os campos de `CAMPOS_BUSCA_EXATOS`
# recebem igualdade numérica exata; os demais, `icontains`.
CAMPOS_BUSCA: Final[tuple[tuple[str, str], ...]] = (
    ("origem", "origem"),
    ("recurso__codigo", "recurso"),
    ("recurso__descricao", "descrição do recurso"),
    ("id", "nº do período"),
    ("op", "OP"),
    ("id_operador", "operador"),
)
CAMPOS_BUSCA_EXATOS: Final[frozenset[str]] = frozenset({"id", "op", "id_operador"})

# Rótulos dos campos para a instrução da tela (placeholder do template).
ROTULOS_BUSCA = ", ".join(rotulo for _campo, rotulo in CAMPOS_BUSCA)


def consulta_de_busca(termo: str) -> Q:
    """Q com um filtro por campo de `CAMPOS_BUSCA`: `icontains` textual e
    igualdade exata numérica para os campos de `CAMPOS_BUSCA_EXATOS` —
    termo não decimal não filtra por esses.

    `isdecimal()` e não `isdigit()`: dígitos unicode como "²" passam em
    `isdigit()` e `int()` levanta `ValueError` neles.
    """
    filtros = Q()
    termo_exato = int(termo) if termo.isdecimal() else None
    for campo, _rotulo in CAMPOS_BUSCA:
        if campo in CAMPOS_BUSCA_EXATOS:
            if termo_exato is not None:
                filtros |= Q(**{campo: termo_exato})
        else:
            filtros |= Q(**{f"{campo}__icontains": termo})
    return filtros


def _redirect_retorno(request):
    destino = request.POST.get("next")
    if destino and url_has_allowed_host_and_scheme(
        destino, {request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(destino)
    return redirect("log_tempo_producao")


def _usuario_pode_alterar_horarios_parada(usuario):
    """Flag de exibição da tela; a autorização do POST é do decorator."""
    return (
        usuario.is_staff
        or usuario.is_superuser
        or usuario.has_perm("producao.pode_alterar_paradas")
    )


def _descricoes_motivos_erp(periodos):
    motivos_por_empresa = {}
    for periodo in periodos:
        codemp = periodo.recurso.centro_recurso.setor.departamento.filial.empresa.codemp
        for parada in periodo.paradas_periodo:
            for justificativa in parada.justificativas.all():
                motivo = str(justificativa.motivo or "").strip()
                if motivo:
                    motivos_por_empresa.setdefault(codemp, set()).add(motivo)

    descricoes = {}
    # Cursor só quando há motivo a resolver: sem períodos com justificativa
    # a tela não consulta o ERP.
    for codemp, motivos in motivos_por_empresa.items():
        parametros = {"codemp": codemp}
        marcadores = []
        for indice, motivo in enumerate(motivos):
            nome_parametro = f"motivo_{indice}"
            parametros[nome_parametro] = motivo
            marcadores.append(f":{nome_parametro}")
        with cursor_oracle_erp() as cursor:
            cursor.execute(
                f"""
                SELECT codmtv, desmtv
                  FROM e018mtv
                 WHERE codemp = :codemp
                   AND codmtv IN ({", ".join(marcadores)})
                """,
                parametros,
            )
            for codmtv, desmtv in cursor.fetchall():
                descricoes[(codemp, str(codmtv).strip())] = str(desmtv or "").strip()
    return descricoes


@permissao_requerida("producao.pode_excluir_pendencias_integracao")
@require_POST
def excluir_parada_tempo_producao(request, pk):
    # Escopo: parada fora dos recursos visíveis do usuário não é
    # alcançável mesmo sabendo o pk (padrão das filas irmãs).
    if not ParadaMaquina.objects.filter(
        pk=pk, recurso__in=recursos_visiveis_apontamento(request.user)
    ).exists():
        messages.error(request, "Parada não disponível para o seu usuário.")
        return redirect("log_tempo_producao")
    try:
        periodo_id = int(request.POST.get("periodo_id", ""))
    except TypeError, ValueError:
        messages.error(request, "Período produtivo inválido para a exclusão da parada.")
        return redirect("log_tempo_producao")

    try:
        with transaction.atomic():
            parada = get_object_or_404(ParadaMaquina.objects.select_for_update(), pk=pk)
            periodo = get_object_or_404(LogTrocaOPAtiva.objects.select_for_update(), pk=periodo_id)
            if not parada.periodos_produtivos.filter(pk=periodo.pk).exists():
                messages.error(request, "A parada não pertence ao período produtivo informado.")
                return redirect("log_tempo_producao")
            if parada.fim is None:
                messages.error(
                    request,
                    "Não é permitido desvincular uma parada física ainda aberta.",
                )
                return redirect("log_tempo_producao")

            # O corte é preservado e apenas seus itens locais são refeitos
            # depois de remover a parada. INTEGRADO/PROCESSANDO ficam travados.
            inicio_alteracao = max(parada.inicio, periodo.horario_troca)
            pacotes = list(
                PacoteTempoERP.objects.select_for_update().filter(
                    troca_op_ativa=periodo,
                    corte_fim_real__gt=inicio_alteracao,
                )
            )
            if parada.periodos_produtivos.exclude(pk=periodo.pk).exists():
                parada.periodos_produtivos.remove(periodo)
                mensagem = "Vínculo da parada com o período produtivo excluído."
            else:
                parada.delete()
                mensagem = "Parada excluída."

            from producao.services.consolida_tempos_erp import reconsolidar_pacotes_tempo_erp

            pacotes_regenerados = reconsolidar_pacotes_tempo_erp(pacotes)
    except ValueError as erro:
        messages.error(request, str(erro))
        return redirect("log_tempo_producao")
    if pacotes_regenerados:
        mensagem += f" {pacotes_regenerados} pacote(s) ERP pendente(s) foram regenerados."
    messages.success(request, mensagem)
    return redirect("log_tempo_producao")


# Alteração de horário físico da parada: staff e superusuário passam pelo
# bypass do decorator (decisão do sênior); o guard de permissão anterior
# exigia superusuário OU pode_alterar_paradas. Escopo de recurso visível
# permanece no corpo.
@permissao_requerida("producao.pode_alterar_paradas")
@require_POST
def alterar_horarios_parada_tempo_producao(request, pk):
    if not ParadaMaquina.objects.filter(
        pk=pk, recurso__in=recursos_visiveis_apontamento(request.user)
    ).exists():
        return HttpResponseForbidden("Parada não disponível para o seu usuário.")

    try:
        inicio = data_hora_local(request.POST.get("inicio"))
        fim = data_hora_local(request.POST.get("fim"))
    except TypeError, ValueError:
        messages.error(request, "Informe horários válidos para a parada.")
        return redirect(f"{reverse('log_tempo_producao')}?parada={pk}")
    if inicio is None:
        messages.error(request, "Informe o início da parada.")
        return redirect(f"{reverse('log_tempo_producao')}?parada={pk}")

    try:
        resultado = alterar_horarios_parada(
            parada_id=pk,
            inicio=inicio,
            fim=fim,
            usuario=request.user,
        )
    except ValueError as erro:
        messages.error(request, str(erro))
    else:
        pacotes_regenerados = resultado["pacotes_regenerados"]
        mensagem = "Horários da parada física atualizados."
        if pacotes_regenerados:
            mensagem += f" {pacotes_regenerados} pacote(s) ERP pendente(s) foram regenerados."
        messages.success(request, mensagem)
    return redirect(f"{reverse('log_tempo_producao')}?parada={pk}")


@permissao_requerida("producao.pode_excluir_pendencias_integracao")
@require_POST
def excluir_periodo_tempo_producao(request, pk):
    # Escopo: período de recurso de outra empresa não é alcançável. O
    # select_for_update do período roda dentro do atomic abaixo.
    try:
        with transaction.atomic():
            periodo = get_object_or_404(_periodos_visiveis(request.user).select_for_update(), pk=pk)
            if periodo.paradas.filter(fim__isnull=True).exists():
                messages.error(
                    request,
                    "Não é permitido excluir um período vinculado a uma parada física ainda aberta.",
                )
                return redirect("log_tempo_producao")
            for parada in list(periodo.paradas.select_for_update()):
                if parada.periodos_produtivos.exclude(pk=periodo.pk).exists():
                    parada.periodos_produtivos.remove(periodo)
                else:
                    parada.delete()
            PacoteTempoERP.objects.filter(troca_op_ativa=periodo).delete()
            periodo.delete()
    except Exception:
        messages.error(request, "Não foi possível excluir o período produtivo.")
    else:
        messages.success(
            request,
            "Período produtivo excluído do log, junto com os pacotes ERP vinculados "
            "(mesmo os já integrados — o registro no ERP é preservado). Paradas que "
            "pertenciam somente a ele também foram removidas; compartilhadas com "
            "outros períodos foram preservadas.",
        )
    return redirect("log_tempo_producao")


def _parada_pertence_ao_periodo(parada, periodo):
    return any(
        periodo_produtivo.id == periodo.id for periodo_produtivo in parada.periodos_produtivos.all()
    )


def _pode_alterar_parada(request, parada):
    if request.user.is_staff or request.user.has_perm("producao.pode_alterar_paradas"):
        return True
    recurso = parada.recurso
    if recurso.alt_just == 2:
        return not parada.justificativas.exists()
    if recurso.alt_just == 3:
        return True
    if recurso.alt_just == 4:
        ultima = (
            ParadaMaquina.objects.filter(
                recurso=recurso,
            )
            .order_by("-inicio", "-id")
            .first()
        )
        return ultima and ultima.id == parada.id
    return False


@login_required
def periodos_parada_manual(request):
    recurso_id = request.GET.get("recurso")
    if not recurso_id or not recurso_id.isdigit():
        return JsonResponse({"periodos": []})
    recurso = get_object_or_404(recursos_visiveis_apontamento(request.user), pk=int(recurso_id))
    if not usuario_pode_abrir_parada_manual(request.user, recurso):
        return HttpResponseForbidden("Sem permissão para abrir parada manual neste recurso.")
    periodos = LogTrocaOPAtiva.objects.filter(recurso=recurso)
    origem = (request.GET.get("origem") or "").strip()
    op = (request.GET.get("op") or "").strip()
    if origem:
        periodos = periodos.filter(origem__iexact=origem)
    if op:
        if not op.isdigit():
            return JsonResponse({"periodos": []})
        periodos = periodos.filter(op=int(op))
    periodos = periodos.order_by("-horario_troca")
    return JsonResponse(
        {
            "periodos": [
                {
                    "id": periodo.id,
                    "texto": f"Origem {periodo.origem or '-'} · OP {periodo.op or '-'} · Início {periodo.horario_troca:%d/%m/%Y %H:%M} · {'Aberto' if periodo.horario_saida is None else f'Fim {periodo.horario_saida:%d/%m/%Y %H:%M}'}",
                }
                for periodo in periodos
            ]
        }
    )


# Abrir parada manual pelo log de tempo produção: exige Pode Alterar
# Paradas (diferente da rota de apontamento, que depende de o recurso ter
# Permite Parada Manual e do pode_apontar da própria rota).
@permissao_requerida("producao.pode_alterar_paradas")
@require_POST
def criar_parada_manual_log(request):
    try:
        recurso = get_object_or_404(
            recursos_visiveis_apontamento(request.user), pk=int(request.POST.get("recurso", ""))
        )
        numcad = int(request.POST.get("numcad", ""))
        inicio = data_hora_local(request.POST.get("inicio"))
        fim = data_hora_local(request.POST.get("fim"))
    except TypeError, ValueError:
        messages.error(request, "Informe recurso e código do operador válidos.")
        return _redirect_retorno(request)
    if inicio is None:
        messages.error(request, "Informe o início da parada.")
        return _redirect_retorno(request)

    try:
        with transaction.atomic():
            criar_parada_manual(
                usuario=request.user,
                recurso=recurso,
                numcad=numcad,
                inicio=inicio,
                fim=fim,
            )
    except ValueError as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, "Parada manual criada.")
    return _redirect_retorno(request)


def _tempo_legivel(tempo):
    if tempo is None:
        return ""
    segundos = int(tempo.total_seconds())
    horas, segundos = divmod(segundos, 3600)
    minutos, segundos = divmod(segundos, 60)
    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"


@login_required
@require_POST
def salvar_justificativas_parada(request, pk):
    requisicao_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    def erro(mensagem):
        if requisicao_ajax:
            return JsonResponse({"ok": False, "mensagem": mensagem}, status=400)
        messages.error(request, mensagem)
        return redirect(f"{reverse('log_tempo_producao')}?parada={pk}")

    with transaction.atomic():
        parada = get_object_or_404(
            ParadaMaquina.objects.filter(recurso__in=recursos_visiveis_apontamento(request.user))
            .select_for_update()
            .select_related("recurso"),
            pk=pk,
        )
        if not _pode_alterar_parada(request, parada):
            if requisicao_ajax:
                return JsonResponse(
                    {"ok": False, "mensagem": "Sem permissão para alterar esta parada."}, status=403
                )
            return HttpResponseForbidden("Sem permissão para alterar esta parada.")

        justificativas = list(parada.justificativas.select_for_update().order_by("sequencia"))
        ids_remover = request.POST.getlist("remover_justificativa")
        removeu_ultima = bool(ids_remover)
        if ids_remover:
            if (
                not all(item.isdigit() for item in ids_remover)
                or len(set(ids_remover)) != len(ids_remover)
                or len(ids_remover) > len(justificativas)
            ):
                return erro("Somente a última justificativa pode ser excluída.")
            ids_remover = {int(item) for item in ids_remover}
            ultimas_ids = {
                justificativa.id for justificativa in justificativas[-len(ids_remover) :]
            }
            if ids_remover != ultimas_ids:
                return erro("Somente a última justificativa pode ser excluída.")
            justificativas = justificativas[: -len(ids_remover)]

        motivos = []
        tempos = []
        for justificativa in justificativas:
            motivo = (request.POST.get(f"motivo_{justificativa.id}") or "").strip()
            tempo_texto = (request.POST.get(f"tempo_{justificativa.id}") or "").strip()
            tempo = parse_duration(tempo_texto) if tempo_texto else None
            if tempo is not None:
                tempo -= timedelta(microseconds=tempo.microseconds)
            if not motivo:
                return erro("Informe todos os motivos.")
            if tempo_texto and tempo is None:
                return erro("Tempo inválido. Use HH:MM:SS.")
            motivos.append(motivo)
            tempos.append(tempo)

        novas_sequencias = []
        for indice in sorted(
            {
                chave.removeprefix("novo_motivo_")
                for chave in request.POST
                if chave.startswith("novo_motivo_") and chave.removeprefix("novo_motivo_").isdigit()
            },
            key=int,
        ):
            novo_motivo = (request.POST.get(f"novo_motivo_{indice}") or "").strip()
            novo_tempo_texto = (request.POST.get(f"novo_tempo_{indice}") or "").strip()
            novo_tempo = parse_duration(novo_tempo_texto) if novo_tempo_texto else None
            if novo_tempo is not None:
                novo_tempo -= timedelta(microseconds=novo_tempo.microseconds)
            if novo_tempo_texto and novo_tempo is None:
                return erro("Tempo inválido. Use HH:MM:SS.")
            if not novo_motivo:
                return erro("Informe o motivo de cada nova justificativa.")
            novas_sequencias.append((novo_motivo, novo_tempo))

        if novas_sequencias:
            for novo_motivo, novo_tempo in novas_sequencias:
                motivos.append(novo_motivo)
                tempos.append(novo_tempo)

        if not motivos:
            return erro("Informe ao menos uma justificativa.")

        recurso = parada.recurso
        for motivo in motivos:
            vinculos = recurso.motivos_abrangencia.filter(codmtv=motivo)
            if not any(
                _motivo_ativo_e_vinculado(recurso, vinculo.codgpm, motivo) for vinculo in vinculos
            ):
                return erro("Há motivo inválido ou inativo no ERP.")

        if parada.fim is None:
            tempos_anteriores = tempos[:-1]
            if any(tempo is None for tempo in tempos_anteriores):
                return erro("Somente a última justificativa aberta pode ficar sem tempo.")
            if not removeu_ultima and tempos[-1] is not None:
                return erro(
                    "Adicione a próxima justificativa para manter a última sequência em andamento."
                )
            if any(tempo <= timedelta() for tempo in tempos_anteriores):
                return erro("Tempo zerado só é permitido na última sequência.")
            if (
                sum(tempos_anteriores, timedelta())
                > timezone.now().replace(microsecond=0) - parada.inicio
            ):
                return erro(
                    "A soma das justificativas não pode ultrapassar o tempo decorrido da parada."
                )
            tempos = [*tempos_anteriores, None]
        else:
            if any(tempo is None for tempo in tempos):
                return erro("Informe o tempo de todas as justificativas da parada fechada.")
            if any(tempo < timedelta() for tempo in tempos) or any(
                tempo == timedelta() for tempo in tempos[:-1]
            ):
                return erro("Tempo zerado só é permitido na última sequência.")

        tempo_total = parada.fim - parada.inicio if parada.fim else None
        if motivos and tempo_total is not None and sum(tempos, timedelta()) != tempo_total:
            return erro("A soma das justificativas deve ser igual ao tempo total da parada.")

        parada.justificativas.all().delete()
        parcial = parada.inicio
        agora = timezone.now().replace(microsecond=0)
        for sequencia, (motivo, tempo) in enumerate(zip(motivos, tempos, strict=False), start=1):
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

    if requisicao_ajax:
        return JsonResponse({"ok": True})
    messages.success(request, "Justificativas da parada atualizadas.")
    return redirect(f"{reverse('log_tempo_producao')}?parada={parada.id}")


@login_required
def logs_tempo_producao(request):
    search_query = (request.GET.get("search") or "").strip()
    parada_id = (request.GET.get("parada") or "").strip()
    recurso_id = (request.GET.get("recurso") or "").strip()
    origem = (request.GET.get("origem") or "").strip()
    op = (request.GET.get("op") or "").strip()
    estagio = (request.GET.get("estagio") or "").strip()
    seqrot = (request.GET.get("seqrot") or "").strip()

    periodos = (
        _periodos_visiveis(request.user)
        .select_related("recurso__centro_recurso__setor__departamento__filial__empresa")
        .annotate(
            _periodo_em_aberto=Case(
                When(horario_saida__isnull=True, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .order_by(
            "_periodo_em_aberto",
            "-horario_troca",
            "-id",
        )
    )

    if search_query:
        periodos = periodos.filter(consulta_de_busca(search_query))

    if recurso_id.isdigit():
        periodos = periodos.filter(recurso_id=int(recurso_id))
    if origem:
        periodos = periodos.filter(origem=origem)
    if op.isdigit():
        periodos = periodos.filter(op=int(op))
    if estagio.isdigit():
        periodos = periodos.filter(estagio=int(estagio))
    if seqrot.isdigit():
        periodos = periodos.filter(seqrot=int(seqrot))

    if parada_id.isdigit():
        periodos = periodos.filter(paradas__id=int(parada_id))

    paginator = Paginator(periodos, 14)
    page_obj = paginator.get_page(request.GET.get("page"))
    periodos_pagina = list(page_obj.object_list)
    page_obj.object_list = periodos_pagina

    paradas = []
    if periodos_pagina:
        periodo_ids = [periodo.id for periodo in periodos_pagina]
        paradas = list(
            ParadaMaquina.objects.filter(periodos_produtivos__id__in=periodo_ids)
            .select_related("recurso", "usuario")
            .prefetch_related("justificativas", "periodos_produtivos")
            .order_by("-inicio", "-id")
            .distinct()
        )

    agora = timezone.now().replace(microsecond=0)
    for periodo in periodos_pagina:
        periodo.paradas_periodo = []
        limite_periodo = periodo.horario_saida or agora
        for parada in paradas:
            if not _parada_pertence_ao_periodo(parada, periodo):
                continue
            inicio_exibicao = max(parada.inicio, periodo.horario_troca)
            fim_calculo = min(parada.fim or agora, limite_periodo)
            if inicio_exibicao >= fim_calculo:
                continue
            parada_periodo = copy(parada)
            parada_periodo.inicio_exibicao = inicio_exibicao
            parada_periodo.fim_exibicao = (
                fim_calculo if parada.fim is not None or periodo.horario_saida is not None else None
            )
            parada_periodo.tempo_parada_exibicao = _tempo_legivel(fim_calculo - inicio_exibicao)
            periodo.paradas_periodo.append(parada_periodo)
        tempo_total_periodo = (periodo.horario_saida or agora) - periodo.horario_troca
        periodo.tempo_periodo = _tempo_legivel(max(tempo_total_periodo, timedelta()))
        periodo.tem_parada_aberta = any(parada.fim is None for parada in periodo.paradas_periodo)
        periodo.expandido = parada_id.isdigit() and any(
            parada.id == int(parada_id) for parada in periodo.paradas_periodo
        )

    descricoes_motivos = _descricoes_motivos_erp(periodos_pagina)
    for periodo in periodos_pagina:
        codemp = periodo.recurso.centro_recurso.setor.departamento.filial.empresa.codemp
        for parada in periodo.paradas_periodo:
            parada.justificativas_ordenadas = list(parada.justificativas.all())
            justificativas_exibicao = []
            for justificativa in parada.justificativas_ordenadas:
                justificativa.descricao_motivo = descricoes_motivos.get(
                    (codemp, str(justificativa.motivo or "").strip()),
                    "",
                )
                justificativa.tempo_legivel = _tempo_legivel(justificativa.tempo)
                justificativa.fim_justificativa = (
                    justificativa.parcial + justificativa.tempo
                    if justificativa.tempo is not None
                    else None
                )
                inicio_exibicao = max(justificativa.parcial, periodo.horario_troca)
                fim_justificativa = justificativa.fim_justificativa or (parada.fim or agora)
                fim_exibicao = min(
                    fim_justificativa,
                    periodo.horario_saida or agora,
                )
                if inicio_exibicao >= fim_exibicao:
                    continue
                justificativa_periodo = copy(justificativa)
                justificativa_periodo.inicio_exibicao = inicio_exibicao
                justificativa_periodo.fim_exibicao = fim_exibicao
                justificativa_periodo.tempo_exibicao_legivel = _tempo_legivel(
                    fim_exibicao - inicio_exibicao
                )
                justificativas_exibicao.append(justificativa_periodo)
            parada.justificativas_exibicao = list(reversed(justificativas_exibicao))
            parada.pode_alterar_justificativas = _pode_alterar_parada(request, parada)
            parada.pode_alterar_horarios = _usuario_pode_alterar_horarios_parada(request.user)
            if parada.pode_alterar_justificativas:
                parada.motivos_parada = motivos_ativos_recurso(periodo.recurso)

    pode_abrir_parada_manual = _usuario_pode_alterar_horarios_parada(request.user)
    # Botão e modal seguem o MESMO gate da rota criar_parada_manual_log
    # (@permissao_requerida pode_alterar_paradas): sem a permissão, o controle
    # nem renderiza — o fallback antigo por permite_parada_manual exibia o
    # botão a quem o POST negava com 403.
    recursos_parada_manual = (
        recursos_visiveis_apontamento(request.user).filter(aponta_parada=True).order_by("codigo")
        if pode_abrir_parada_manual
        else recursos_visiveis_apontamento(request.user).none()
    )

    # Botões de exclusão visíveis a quem a rota autoriza (staff/superusuário
    # pelo bypass ou portador da permissão unificada).
    pode_excluir_pendencias = (
        request.user.is_staff
        or request.user.is_superuser
        or request.user.has_perm("producao.pode_excluir_pendencias_integracao")
    )

    return render(
        request,
        "producao/logs_tempo_producao.html",
        {
            "periodos": page_obj,
            "search_query": search_query,
            "rotulos_busca": ROTULOS_BUSCA,
            "parada_id": parada_id,
            "recursos_parada_manual": recursos_parada_manual,
            "pode_excluir_pendencias": pode_excluir_pendencias,
        },
    )
