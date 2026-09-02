from datetime import datetime

from django.db.models import Q
from django.utils import timezone

from accounts.models import Recurso
from producao.models import LogTrocaOPAtiva, ParadaMaquina
from producao.utils.paradas import criar_parada_nos_periodos
from SIGMA.integracoes.oracle import cursor_oracle_erp


def usuario_pode_abrir_parada_manual(usuario, recurso):
    return recurso.aponta_parada and (
        recurso.permite_parada_manual or usuario.has_perm("producao.pode_alterar_paradas")
    )


def operador_ativo(recurso, numcad):
    with cursor_oracle_erp() as cursor:
        cursor.execute(
            "SELECT 1 FROM e906ope WHERE codemp=:codemp AND numcad=:numcad AND sitope='A'",
            {
                "codemp": recurso.centro_recurso.setor.departamento.filial.empresa.codemp,
                "numcad": numcad,
            },
        )
        return cursor.fetchone() is not None


def data_hora_local(valor):
    if not valor:
        return None
    data_hora = datetime.fromisoformat(valor)
    data_hora = timezone.make_aware(data_hora) if timezone.is_naive(data_hora) else data_hora
    return data_hora.replace(microsecond=0)


def criar_parada_manual(*, usuario, recurso, periodo_id=None, numcad, inicio=None, fim=None):
    if not usuario_pode_abrir_parada_manual(usuario, recurso):
        raise ValueError("Este recurso não permite parada manual para o seu usuário.")
    if not operador_ativo(recurso, numcad):
        raise ValueError("Operador não encontrado ou inativo no ERP.")

    # Mantém a mesma ordem de trava usada pelo coletor automático:
    # Recurso -> LogTrocaOPAtiva -> ParadaMaquina.
    recurso = Recurso.objects.select_for_update().get(pk=recurso.pk)
    if not usuario_pode_abrir_parada_manual(usuario, recurso):
        raise ValueError("Este recurso não permite parada manual para o seu usuário.")

    agora = timezone.now().replace(microsecond=0)
    inicio = inicio.replace(microsecond=0) if inicio else None
    fim = fim.replace(microsecond=0) if fim else None
    inicio_automatico = inicio is None
    if inicio is None:
        inicio = agora
    if fim is not None and fim <= inicio:
        raise ValueError("O fim da parada deve ser posterior ao início.")
    if (not inicio_automatico and inicio >= agora) or (fim is not None and fim > agora):
        raise ValueError("Os horários da parada manual devem ser anteriores ao horário atual.")

    # O período não é dono da parada: ela é física e pertence ao recurso.
    # Busca todos os períodos que cruzam o intervalo para vinculá-los à mesma
    # parada, inclusive várias OPs acopladas simultaneamente na View 3.
    periodos = LogTrocaOPAtiva.objects.select_for_update().filter(recurso=recurso)
    if fim is None:
        # A abertura precisa começar durante ao menos um período atualmente
        # aberto. Os demais períodos abertos do recurso entram na associação
        # central caso tenham sido acoplados enquanto a parada já existia.
        periodos = periodos.filter(horario_saida__isnull=True, horario_troca__lte=inicio)
    else:
        periodos = periodos.filter(horario_troca__lt=fim).filter(
            Q(horario_saida__isnull=True) | Q(horario_saida__gt=inicio)
        )
    periodos = list(periodos.order_by("id"))
    if not periodos:
        raise ValueError(
            "Não há período produtivo deste recurso que coincida com o intervalo informado."
        )

    return criar_parada_nos_periodos(
        periodos=periodos,
        operador=numcad,
        usuario=usuario,
        inicio=inicio,
        fim=fim,
        tipo=ParadaMaquina.Tipo.MANUAL,
        data_hora=agora,
        limite_fim=agora,
    )
