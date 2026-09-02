from django.db import models


class EstadoRelatorioFalhas(models.Model):
    """Estado persistido da cadência do relatório de falhas por e-mail.

    Singleton (`pk=1`): guarda o momento do último envio efetivado para que
    a cadência por horários (`RELATORIO_FALHAS_HORARIOS`) sobreviva ao
    processo e seja honesta com o retry:

    - falha de envio não grava estado → o ciclo seguinte do worker re-tenta
      o MESMO horário vencido, em vez de pular para o horário seguinte;
    - reinício do processo não reenvia horário já cumprido do dia — a marca
      do "já cumpriu este horário" mora no banco, não em memória.

    É estado de worker, não configuração: gravação por save de instância
    (a proibição de `queryset.update()` é da tabela de configuração, que
    tem cache a invalidar; aqui não há cache nem signal).
    """

    ultimo_envio_em = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Último envio",
    )

    class Meta:
        db_table = 'producao"."estado_relatorio_falhas'
        verbose_name = "Estado do relatório de falhas"
        verbose_name_plural = "Estado do relatório de falhas"
        default_permissions = ()

    def __str__(self):
        return f"Último envio: {self.ultimo_envio_em or 'nunca'}"
