from datetime import date, datetime, time, timedelta

from django.db.models import Q

from ..models import CalendarioEvento, HoraExtraPlanejada, OEEPlanejadoDiario, Recurso, TurnoRecurso


def get_intervalos_planejados(recurso, dia):
    """
    Retorna a lista de tuplas (datetime_inicio, datetime_fim) representando os períodos
    em que o recurso deveria estar trabalhando no dia informado.
    """
    # Se o recurso for passado como objeto, pegar o ID.
    # Se for passado como ID, usar diretamente.
    recurso_id = recurso.id if hasattr(recurso, "id") else recurso

    # 1. Calendário: Se houver qualquer evento no dia -> vazio
    # No modelo, CalendarioEvento aponta para Calendario. Calendario aponta para Filial.
    # Recurso aponta para CentroRecurso -> Setor -> Departamento -> Filial.

    # Busca a filial do recurso da forma mais eficiente possível
    # Ideal: a função sempre receber o objeto com select_related já feito
    try:
        filial = recurso.centro_recurso.setor.departamento.filial
    except AttributeError, Recurso.DoesNotExist:
        recurso_obj = Recurso.objects.select_related(
            "centro_recurso__setor__departamento__filial"
        ).get(pk=recurso_id)
        filial = recurso_obj.centro_recurso.setor.departamento.filial

    if CalendarioEvento.objects.filter(calendario__filial=filial, data=dia).exists():
        return []

    intervalos = []

    # Limites rígidos do dia
    dia_inicio_limite = datetime.combine(dia, time.min)
    dia_fim_limite = datetime.combine(dia, time(23, 59, 59, 999999))

    # 2. Turnos (TurnoRecurso)
    # dia.weekday() retorna 0 para segunda e 6 para domingo.
    # No modelo TurnoRecurso, as escolhas de dias são (1, "Segunda") ... (7, "Domingo").
    dia_semana_modelo = dia.weekday() + 1
    dia_anterior = dia - timedelta(days=1)
    dia_semana_anterior = dia_anterior.weekday() + 1

    # Otimização: buscar todos os turnos relevantes em uma única query
    # Turnos do dia atual OU turnos de ontem que podem cruzar (hora_fim < hora_inicio)
    turnos_query = TurnoRecurso.objects.filter(recurso_id=recurso_id).filter(
        Q(dias__contains=[dia_semana_modelo]) | Q(dias__contains=[dia_semana_anterior])
    )

    # Dicionário para garantir unicidade por ID
    todos_turnos = list({t.id: t for t in turnos_query}.values())

    for turno in todos_turnos:
        # 1. Turno do dia atual (Início do turno)
        if dia_semana_modelo in turno.dias:
            inicio_dt = datetime.combine(dia, turno.hora_inicio)

            # Se hora_fim > hora_inicio -> termina hoje (Caso Normal)
            # Se hora_fim < hora_inicio -> cruza o dia -> termina 23:59:59 (Caso Cruzado)
            if turno.hora_fim > turno.hora_inicio:
                fim_dt = datetime.combine(dia, turno.hora_fim)
            else:
                fim_dt = dia_fim_limite

            intervalos.append((inicio_dt, fim_dt))

        # 2. Turno vindo do dia anterior (Fim do turno na madrugada)
        # Só entra se ele realmente cruzar (fim < inicio) e se o dia anterior for um dia de trabalho dele
        if turno.hora_fim < turno.hora_inicio and dia_semana_anterior in turno.dias:
            # Validação: só considerar se realmente invade o dia atual (fim > 00:00)
            if turno.hora_fim > time.min:
                inicio_hoje = dia_inicio_limite
                fim_hoje = datetime.combine(dia, turno.hora_fim)
                intervalos.append((inicio_hoje, fim_hoje))

    # 3. Horas Extras (HoraExtraPlanejada)
    hes = HoraExtraPlanejada.objects.filter(
        Q(dias__contains=[dia_semana_modelo]) | Q(dias__isnull=True),
        recurso_id=recurso_id,
        data_inicio__lte=dia,
        data_fim__gte=dia,
    )

    for he in hes:
        inicio_dt = datetime.combine(dia, he.hora_inicio)
        fim_dt = datetime.combine(dia, he.hora_fim)

        # Se cruzar o dia (ex: 22:00 -> 02:00), o enunciado diz "nunca retornar intervalos cruzando dias"
        if he.hora_fim < he.hora_inicio:
            # Tratamos a parte do dia atual
            # Bug fix: Garantir min(hora_fim_real, dia_fim_limite) se necessário,
            # mas se hora_fim < hora_inicio e estamos no dia_inicio, ele vai até o fim do dia.
            fim_dt = dia_fim_limite
            intervalos.append((inicio_dt, fim_dt))
        else:
            # Garantir limite do dia
            fim_dt = min(datetime.combine(dia, he.hora_fim), dia_fim_limite)
            intervalos.append((inicio_dt, fim_dt))

    # 4. Pré-processamento e Normalização
    if not intervalos:
        return []

    # Filtrar intervalos inválidos (fim <= inicio) ANTES da normalização
    intervalos_validos = [i for i in intervalos if i[1] > i[0]]
    if not intervalos_validos:
        return []

    # Ordenar por horário de início
    intervalos_validos.sort(key=lambda x: x[0])

    # Unir intervalos sobrepostos ou encostados
    normalizados = []
    atual_inicio, atual_fim = intervalos_validos[0]

    for i in range(1, len(intervalos_validos)):
        prox_inicio, prox_fim = intervalos_validos[i]

        if prox_inicio <= atual_fim:
            atual_fim = max(atual_fim, prox_fim)
        else:
            normalizados.append((atual_inicio, atual_fim))
            atual_inicio, atual_fim = prox_inicio, prox_fim

    normalizados.append((atual_inicio, atual_fim))

    return normalizados


def get_minutos_planejados(recurso, dia):
    """
    Retorna a soma total de minutos planejados para o recurso no dia.
    """
    intervalos = get_intervalos_planejados(recurso, dia)
    total_segundos = 0
    for inicio, fim in intervalos:
        total_segundos += (fim - inicio).total_seconds()

    return round(total_segundos / 60)


def consolidar_planejado_dia(data):
    """
    Percorre todos os recursos com habilita_oee=True, calcula os minutos planejados
    e salva na tabela OEEPlanejadoDiario.
    """
    # Regra de execução:
    # Ontem (D-1): recalcular 1x e considerar fechado.
    # Hoje: recalcular sempre.
    # Não recalcular dias antigos automaticamente.
    # No entanto, a função recebe 'data', então ela processa a data informada.
    # A lógica de "não recalcular dias antigos" deve ser controlada por quem chama
    # ou podemos colocar uma trava aqui se necessário.
    # O prompt diz: "Hoje: recalcular sempre. Ontem: recalcular 1x. Não recalcular antigos automaticamente."

    hoje = date.today()
    ontem = hoje - timedelta(days=1)

    # Regra de fechamento: hoje e ontem recalcula, D-2 pra trás NÃO.
    if data < ontem:
        return

    # Otimização N+1: traz as tabelas relacionadas em uma única query
    recursos = Recurso.objects.filter(habilita_oee=True).select_related(
        "centro_recurso__setor__departamento__filial"
    )
    for recurso in recursos:
        minutos = get_minutos_planejados(recurso, data)

        OEEPlanejadoDiario.objects.update_or_create(
            recurso=recurso, data=data, defaults={"minutos_planejados": minutos}
        )


def consolidar_planejado_periodo(data_inicio, data_fim):
    """
    Consolida o tempo planejado para um intervalo de datas.
    """
    d = data_inicio
    while d <= data_fim:
        consolidar_planejado_dia(d)
        d += timedelta(days=1)
