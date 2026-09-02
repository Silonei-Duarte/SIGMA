from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from producao.models import JustificativaParada, LogTrocaOPAtiva, ParadaMaquina
from producao.utils.paradas import vincular_parada_aberta_ao_periodo


def notificar_parada_recurso(recurso_id):
    paradas = ParadaMaquina.objects.filter(
        recurso_id=recurso_id,
    ).prefetch_related("justificativas")
    abertas = any(parada.fim is None for parada in paradas)
    bloqueios = 0
    for parada in paradas:
        if parada.fim is None:
            bloqueios += 1
            continue
        tempo_justificado = sum(
            (justificativa.tempo or timedelta() for justificativa in parada.justificativas.all()),
            timedelta(),
        )
        if tempo_justificado < parada.fim - parada.inicio:
            bloqueios += 1

    def enviar():
        from telemetria.services.coleta import invalidar_estado_parada_automatica

        invalidar_estado_parada_automatica(recurso_id)
        channel_layer = get_channel_layer()
        if not channel_layer:
            return
        async_to_sync(channel_layer.group_send)(
            f"recurso_{recurso_id}",
            {
                "type": "parada_update",
                "aberta": abertas,
                "pendentes": bloqueios,
                "bloqueia": bool(bloqueios),
            },
        )

    transaction.on_commit(enviar)


@receiver(post_save, sender=ParadaMaquina)
def parada_maquina_salva(sender, instance, **kwargs):
    notificar_parada_recurso(instance.recurso_id)


@receiver(post_delete, sender=ParadaMaquina)
def parada_maquina_removida(sender, instance, **kwargs):
    notificar_parada_recurso(instance.recurso_id)


@receiver(post_save, sender=LogTrocaOPAtiva)
def vincular_periodo_novo_a_parada_aberta(sender, instance, created, **kwargs):
    """Mantém a parada física aberta associada a toda nova OP do recurso."""
    if created and instance.horario_saida is None:
        vincular_parada_aberta_ao_periodo(instance)


@receiver(m2m_changed, sender=ParadaMaquina.periodos_produtivos.through)
def validar_recurso_periodos_da_parada(sender, instance, action, reverse, model, pk_set, **kwargs):
    """Protege a integridade dos vínculos entre parada física e períodos."""
    if action in {"post_add", "post_remove", "post_clear"}:
        # A relação também altera o estado exibido do recurso: uma nova OP
        # passa a participar da parada física já aberta, ou deixa de exibir
        # uma parada histórica removida por correção administrativa.
        notificar_parada_recurso(instance.recurso_id)
        return

    if action == "pre_add" and pk_set:
        if reverse:
            periodo = instance
            paradas_invalidas = ParadaMaquina.objects.filter(pk__in=pk_set).exclude(
                recurso_id=periodo.recurso_id,
            )
            if paradas_invalidas.exists():
                raise ValidationError(
                    "A parada e o período produtivo devem pertencer ao mesmo recurso."
                )
            return

        parada = instance
        periodos_invalidos = LogTrocaOPAtiva.objects.filter(pk__in=pk_set).exclude(
            recurso_id=parada.recurso_id,
        )
        if periodos_invalidos.exists():
            raise ValidationError(
                "A parada e o período produtivo devem pertencer ao mesmo recurso."
            )
        return

    if action not in {"pre_remove", "pre_clear"}:
        return

    def periodo_pode_sair_de_parada_aberta(parada, periodo):
        limite_intervalo = timezone.now().replace(microsecond=0)
        return not (
            periodo.horario_troca < limite_intervalo
            and (periodo.horario_saida is None or periodo.horario_saida > parada.inicio)
        )

    if reverse:
        periodo = instance
        paradas = (
            ParadaMaquina.objects.filter(pk__in=pk_set)
            if action == "pre_remove"
            else periodo.paradas.all()
        )
        for parada in paradas:
            if parada.fim is None and not periodo_pode_sair_de_parada_aberta(parada, periodo):
                raise ValidationError(
                    "Não é permitido remover o vínculo de um período que cruza uma parada física ainda aberta."
                )
            if not parada.periodos_produtivos.exclude(pk=periodo.pk).exists():
                raise ValidationError(
                    "Não é permitido deixar uma parada física sem período produtivo vinculado."
                )
        return

    parada = instance
    if parada.fim is None and action == "pre_clear":
        raise ValidationError(
            "Não é permitido limpar os vínculos de uma parada física ainda aberta."
        )
    if parada.fim is None:
        periodos_a_remover = LogTrocaOPAtiva.objects.filter(pk__in=pk_set)
        if any(
            not periodo_pode_sair_de_parada_aberta(parada, periodo)
            for periodo in periodos_a_remover
        ):
            raise ValidationError(
                "Não é permitido remover o vínculo de um período que cruza uma parada física ainda aberta."
            )
    if action == "pre_clear" or not parada.periodos_produtivos.exclude(pk__in=pk_set).exists():
        raise ValidationError(
            "Não é permitido deixar uma parada física sem período produtivo vinculado."
        )


@receiver(pre_delete, sender=LogTrocaOPAtiva)
def remover_ou_desvincular_paradas_do_periodo(sender, instance, **kwargs):
    """Evita parada sem período quando um LogTrocaOPAtiva é removido via ORM."""
    paradas = list(instance.paradas.select_for_update().prefetch_related("periodos_produtivos"))
    for parada in paradas:
        if parada.fim is None:
            raise ValidationError(
                "Não é permitido excluir um período produtivo vinculado a uma parada física ainda aberta."
            )
        if parada.periodos_produtivos.exclude(pk=instance.pk).exists():
            parada.periodos_produtivos.remove(instance)
        else:
            parada.delete()


@receiver(post_save, sender=JustificativaParada)
def justificativa_parada_salva(sender, instance, **kwargs):
    notificar_parada_recurso(instance.parada.recurso_id)


@receiver(post_delete, sender=JustificativaParada)
def justificativa_parada_removida(sender, instance, **kwargs):
    recurso_id = (
        ParadaMaquina.objects.filter(pk=instance.parada_id)
        .values_list("recurso_id", flat=True)
        .first()
    )
    if recurso_id:
        notificar_parada_recurso(recurso_id)
