from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import Recurso
from producao.models import LogTrocaOPAtiva, PacoteTempoERP, ParadaMaquina


def tempo_minimo_parada(recurso):
    return recurso.tempo_minimo_parada or timedelta(minutes=1)


def pode_encerrar_parada(parada, fim):
    return fim >= parada.inicio + tempo_minimo_parada(parada.recurso)


def validar_tempo_minimo_parada(recurso, inicio, fim):
    minimo = tempo_minimo_parada(recurso)
    if fim - inicio < minimo:
        total_segundos = int(minimo.total_seconds())
        horas, resto = divmod(total_segundos, 3600)
        minutos, segundos = divmod(resto, 60)
        raise ValueError(
            f"A parada deve permanecer aberta por ao menos {horas:02d}:{minutos:02d}:{segundos:02d}."
        )


def congelar_justificativa_aberta(parada, agora=None):
    """Fecha o trecho final da última justificativa de uma parada encerrada."""
    justificativas = list(parada.justificativas.order_by("sequencia"))
    if not justificativas or parada.fim is None:
        return None

    ultima = justificativas[-1]
    tempo_anteriores = sum(
        (justificativa.tempo or timedelta() for justificativa in justificativas[:-1]),
        timedelta(),
    )
    duracao_total = parada.fim - parada.inicio
    if tempo_anteriores > duracao_total:
        raise ValueError("As justificativas anteriores ultrapassam a duração da parada.")
    ultima.parcial = parada.inicio + tempo_anteriores
    ultima.tempo = duracao_total - tempo_anteriores
    ultima.data_hora = (agora or timezone.now()).replace(microsecond=0)
    ultima.save(update_fields=["parcial", "tempo", "data_hora"])
    return ultima


@transaction.atomic
def criar_parada_nos_periodos(
    *, periodos, operador, usuario, inicio, fim=None, tipo, data_hora=None, limite_fim=None
):
    """Cria uma parada física associada a um ou mais períodos do mesmo recurso.

    O chamador já deve validar autorização, período e limites de data. Esta
    função concentra a trava e a regra de sobreposição usada por aberturas
    manuais e automáticas.
    """
    periodos = list(periodos)
    if not periodos:
        raise ValueError("Informe ao menos um período produtivo para a parada.")

    recurso_id = periodos[0].recurso_id
    if any(periodo.recurso_id != recurso_id for periodo in periodos):
        raise ValueError("Todos os períodos produtivos da parada devem pertencer ao mesmo recurso.")

    # Ordem canônica de trava: Recurso -> períodos -> parada. Ela serializa a
    # abertura de parada da telemetria com a criação de um período novo.
    recurso = Recurso.objects.select_for_update().get(pk=recurso_id)

    inicio = inicio.replace(microsecond=0)
    fim = fim.replace(microsecond=0) if fim else None
    data_hora = data_hora.replace(microsecond=0) if data_hora else None
    if fim:
        validar_tempo_minimo_parada(recurso, inicio, fim)

    # A parada é física: vincula todos os períodos que participam de seu
    # intervalo, tanto para abertura em andamento como para lançamento fechado.
    if fim is None:
        periodos_do_intervalo = list(
            LogTrocaOPAtiva.objects.select_for_update()
            .filter(recurso_id=recurso_id, horario_saida__isnull=True)
            .order_by("id")
        )
    else:
        periodos_do_intervalo = list(
            LogTrocaOPAtiva.objects.select_for_update()
            .filter(recurso_id=recurso_id, horario_troca__lt=fim)
            .filter(Q(horario_saida__isnull=True) | Q(horario_saida__gt=inicio))
            .order_by("id")
        )
    periodos = list(
        {periodo.pk: periodo for periodo in [*periodos, *periodos_do_intervalo]}.values()
    )
    limite_fim = (limite_fim or periodos[0].horario_saida or timezone.now()).replace(microsecond=0)
    paradas = ParadaMaquina.objects.select_for_update().filter(recurso_id=recurso_id)
    fim_nova_parada = fim or limite_fim
    for parada in paradas:
        fim_parada = parada.fim or limite_fim
        if parada.fim is None and fim is None:
            raise ValueError("Já existe uma parada aberta neste recurso.")
        if parada.inicio < fim_nova_parada and fim_parada > inicio:
            raise ValueError("O intervalo informado coincide com outra parada deste recurso.")

    parada = ParadaMaquina.objects.create(
        recurso_id=recurso_id,
        operador=str(operador or ""),
        inicio=inicio,
        fim=fim,
        usuario=usuario,
        tipo=tipo,
        data_hora=data_hora or timezone.now().replace(microsecond=0),
    )
    parada.periodos_produtivos.add(*periodos)
    return parada


@transaction.atomic
def vincular_parada_aberta_ao_periodo(periodo):
    """Inclui um período novo na parada física aberta do mesmo recurso, se houver."""
    # A mesma trava usada pela telemetria impede a corrida onde o período é
    # criado entre a consulta dos períodos abertos e a criação da parada.
    Recurso.objects.select_for_update().get(pk=periodo.recurso_id)
    parada = (
        ParadaMaquina.objects.select_for_update()
        .filter(recurso_id=periodo.recurso_id, fim__isnull=True)
        .order_by("id")
        .first()
    )
    if parada:
        parada.periodos_produtivos.add(periodo)
    return parada


def reconciliar_periodos_da_parada(parada, *, periodos, agora=None):
    """Mantém na parada somente os períodos que cruzam seu intervalo físico.

    O chamador deve seguir a ordem de trava Recurso -> períodos -> parada.
    Para uma parada aberta, o limite direito é ``agora``; por isso todo
    período aberto continua vinculado e um período já encerrado só é removido
    se realmente não participou da parada.
    """
    agora = (agora or timezone.now()).replace(microsecond=0)
    limite_intervalo = parada.fim or agora
    periodos = list(periodos)
    periodos_intersectantes = [
        periodo
        for periodo in periodos
        if periodo.horario_troca < limite_intervalo
        and (periodo.horario_saida is None or periodo.horario_saida > parada.inicio)
    ]
    if not periodos_intersectantes:
        raise ValueError("A parada física não pode ficar sem período produtivo vinculado.")

    ids_anteriores = set(parada.periodos_produtivos.values_list("pk", flat=True))
    ids_intersectantes = {periodo.pk for periodo in periodos_intersectantes}

    # Inclui primeiro para preservar a invariante de nunca haver uma parada
    # sem período, inclusive quando a correção troca uma OP vinculada por outra.
    parada.periodos_produtivos.add(*periodos_intersectantes)
    ids_remover = ids_anteriores - ids_intersectantes
    if ids_remover:
        parada.periodos_produtivos.remove(*ids_remover)
    return periodos_intersectantes


def _intervalo_da_parada_no_periodo(*, periodo, inicio, fim, agora):
    """Retorna a contribuição efetiva da parada no período, em [início, fim)."""
    inicio_efetivo = max(inicio, periodo.horario_troca)
    fim_efetivo = min(fim or agora, periodo.horario_saida or agora)
    if inicio_efetivo >= fim_efetivo:
        return None
    return inicio_efetivo, fim_efetivo


def _primeiro_instante_alterado(intervalo_anterior, intervalo_corrigido):
    """Obtém o primeiro instante em que duas janelas semiabertas divergem."""
    if intervalo_anterior == intervalo_corrigido:
        return None
    if intervalo_anterior is None:
        return intervalo_corrigido[0]
    if intervalo_corrigido is None:
        return intervalo_anterior[0]
    if intervalo_anterior[0] != intervalo_corrigido[0]:
        return min(intervalo_anterior[0], intervalo_corrigido[0])
    return min(intervalo_anterior[1], intervalo_corrigido[1])


@transaction.atomic
def alterar_horarios_parada(*, parada_id, inicio, fim, usuario, agora=None):
    """Corrige o intervalo físico de uma parada e recompõe seus efeitos locais.

    A edição sempre acontece na parada física. Os períodos afetados são
    recalculados pela interseção temporal. Pacotes ERP pendentes ou com erro,
    a partir do primeiro corte afetado, são regenerados; os já integrados ou
    em processamento permanecem intactos e não retornam à fila de envio.
    """
    agora = (agora or timezone.now()).replace(microsecond=0)
    inicio = inicio.replace(microsecond=0)
    fim = fim.replace(microsecond=0) if fim else None
    limite_intervalo = fim or agora
    if inicio >= limite_intervalo:
        raise ValueError("O início da parada deve ser anterior ao fim informado.")
    if inicio > agora or (fim and fim > agora):
        raise ValueError("Os horários da parada não podem estar no futuro.")

    recurso_id = (
        ParadaMaquina.objects.filter(pk=parada_id).values_list("recurso_id", flat=True).first()
    )
    if not recurso_id:
        raise ValueError("Parada não encontrada.")

    # Mantém a ordem canônica de trava: Recurso -> períodos -> parada.
    recurso = Recurso.objects.select_for_update().get(pk=recurso_id)
    if fim:
        validar_tempo_minimo_parada(recurso, inicio, fim)
    periodos = list(
        LogTrocaOPAtiva.objects.select_for_update().filter(recurso=recurso).order_by("id")
    )
    try:
        parada = ParadaMaquina.objects.select_for_update().get(pk=parada_id)
    except ParadaMaquina.DoesNotExist:
        raise ValueError("Parada não encontrada.") from None
    if parada.fim is not None and fim is None:
        raise ValueError("Uma parada já fechada não pode ser reaberta por esta alteração.")
    if parada.inicio == inicio and parada.fim == fim:
        return {
            "parada": parada,
            "pacotes_regenerados": 0,
        }

    inicio_anterior = parada.inicio
    fim_anterior = parada.fim

    periodos_intersectantes = [
        periodo
        for periodo in periodos
        if periodo.horario_troca < limite_intervalo
        and (periodo.horario_saida is None or periodo.horario_saida > inicio)
    ]
    if not periodos_intersectantes:
        raise ValueError(
            "O intervalo corrigido não coincide com nenhum período produtivo do recurso."
        )

    for outra in (
        ParadaMaquina.objects.select_for_update().filter(recurso=recurso).exclude(pk=parada.pk)
    ):
        fim_outra = outra.fim or agora
        if outra.inicio < limite_intervalo and fim_outra > inicio:
            raise ValueError("O intervalo informado coincide com outra parada deste recurso.")

    justificativas = list(parada.justificativas.select_for_update().order_by("sequencia"))
    if any(justificativa.tempo is None for justificativa in justificativas[:-1]):
        raise ValueError("Somente a última justificativa pode permanecer em andamento.")
    tempo_fixo = sum(
        (justificativa.tempo or timedelta() for justificativa in justificativas[:-1]),
        timedelta(),
    )
    duracao_corrigida = limite_intervalo - inicio
    if tempo_fixo > duracao_corrigida:
        raise ValueError(
            "As justificativas anteriores ultrapassam a duração corrigida da parada. "
            "Ajuste as justificativas antes de reduzir esse intervalo."
        )

    ids_periodos_anteriores = set(parada.periodos_produtivos.values_list("pk", flat=True))
    ids_periodos_corrigidos = {periodo.pk for periodo in periodos_intersectantes}
    ids_periodos_afetados = ids_periodos_anteriores | ids_periodos_corrigidos
    periodos_por_id = {periodo.pk: periodo for periodo in periodos}
    primeiro_corte_afetado = {}
    for periodo_id in ids_periodos_afetados:
        periodo = periodos_por_id.get(periodo_id)
        if periodo is None:
            continue
        intervalo_anterior = (
            _intervalo_da_parada_no_periodo(
                periodo=periodo,
                inicio=inicio_anterior,
                fim=fim_anterior,
                agora=agora,
            )
            if periodo_id in ids_periodos_anteriores
            else None
        )
        intervalo_corrigido = (
            _intervalo_da_parada_no_periodo(
                periodo=periodo,
                inicio=inicio,
                fim=fim,
                agora=agora,
            )
            if periodo_id in ids_periodos_corrigidos
            else None
        )
        inicio_alteracao = _primeiro_instante_alterado(
            intervalo_anterior,
            intervalo_corrigido,
        )
        if inicio_alteracao is not None:
            primeiro_corte_afetado[periodo_id] = inicio_alteracao

    filtro_pacotes = Q()
    for periodo_id, inicio_alteracao in primeiro_corte_afetado.items():
        # O gerador parte apenas do maior corte já existente. Por isso, ao
        # tocar um corte, remove-se o sufixo inteiro daquele período; assim
        # não se deixa uma lacuna entre pacotes locais.
        filtro_pacotes |= Q(
            troca_op_ativa_id=periodo_id,
            corte_fim_real__gt=inicio_alteracao,
        )
    pacotes = (
        list(PacoteTempoERP.objects.select_for_update().filter(filtro_pacotes))
        if primeiro_corte_afetado
        else []
    )
    parada.inicio = inicio
    parada.fim = fim
    parada.usuario = usuario
    parada.data_hora = agora
    parada.save(update_fields=["inicio", "fim", "usuario", "data_hora"])

    if justificativas:
        parcial = inicio
        ultima_posicao = len(justificativas) - 1
        for indice, justificativa in enumerate(justificativas):
            if indice == ultima_posicao:
                tempo = None if fim is None else duracao_corrigida - tempo_fixo
            else:
                tempo = justificativa.tempo
            justificativa.parcial = parcial
            justificativa.tempo = tempo
            justificativa.data_hora = agora
            justificativa.save(update_fields=["parcial", "tempo", "data_hora"])
            if tempo is not None:
                parcial += tempo

    reconciliar_periodos_da_parada(parada, periodos=periodos, agora=agora)

    # Pacote enviado/processando é um retrato já entregue ou em voo para o
    # ERP: fica imutável localmente e nunca volta à fila. Os demais mantêm o
    # mesmo corte e recebem somente os itens reconstruídos.
    from producao.services.consolida_tempos_erp import reconsolidar_pacotes_tempo_erp

    pacotes_regenerados = reconsolidar_pacotes_tempo_erp(pacotes)

    return {
        "parada": parada,
        "pacotes_regenerados": pacotes_regenerados,
    }


def criar_parada_no_periodo(
    *, periodo, operador, usuario, inicio, fim=None, tipo, data_hora=None, limite_fim=None
):
    """Compatibiliza os fluxos atuais de um único período com a regra central."""
    return criar_parada_nos_periodos(
        periodos=[periodo],
        operador=operador,
        usuario=usuario,
        inicio=inicio,
        fim=fim,
        tipo=tipo,
        data_hora=data_hora,
        limite_fim=limite_fim,
    )
