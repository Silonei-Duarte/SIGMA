from django.contrib.postgres.fields import ArrayField
from django.db import models


class Chamado(models.Model):
    class Prioridade(models.TextChoices):
        BAIXA = "BAIXA", "Baixa"
        MEDIA = "MEDIA", "Média"
        ALTA = "ALTA", "Alta"
        CRITICA = "CRITICA", "Crítica"

    class Status(models.TextChoices):
        ABERTO = "ABERTO", "Aberto"
        EM_ATENDIMENTO = "EM_ATENDIMENTO", "Em atendimento"
        PENDENTE = "PENDENTE", "Pendente"
        FECHADO = "FECHADO", "Fechado"

    class Categoria(models.TextChoices):
        ELETRICA = "ELETRICA", "Elétrica"
        MECANICA = "MECANICA", "Mecânica"
        HIDRAULICA = "HIDRAULICA", "Hidráulica"
        PNEUMATICA = "PNEUMATICA", "Pneumática"
        MELHORIAS = "MELHORIAS", "Melhorias"
        MANUTENCAO_INFRA = "MANUTENCAO_INFRA", "Manutenção Infraestrutura"
        MANUTENCAO_LOGISTICA = "MANUTENCAO_LOGISTICA", "Manutenção Logística"

    nome = models.CharField(max_length=150)
    categoria = models.CharField(max_length=50, choices=Categoria.choices)
    prioridade = models.CharField(
        max_length=10, choices=Prioridade.choices, default=Prioridade.MEDIA
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ABERTO)

    recurso = models.ForeignKey("accounts.Recurso", on_delete=models.PROTECT)
    responsaveis = ArrayField(
        base_field=models.IntegerField(),
        blank=True,
        null=True,
        default=list,
        verbose_name="IDs dos responsáveis",
    )
    observadores_id = ArrayField(
        base_field=models.IntegerField(),
        blank=True,
        null=True,
        default=list,
        verbose_name="IDs dos observadores",
    )
    sla_previsto = models.DurationField(null=True, blank=True)
    sla_realizado = models.DurationField(null=True, blank=True)

    class Meta:
        db_table = "chamado"
        default_permissions = ()

    def __str__(self):
        return f"{self.nome} ({self.status})"


class Interacao_Chamado(models.Model):
    chamado = models.ForeignKey(
        Chamado, on_delete=models.CASCADE, related_name="interacoeschamados"
    )
    usuario = models.ForeignKey("accounts.CustomUser", on_delete=models.SET_NULL, null=True)
    mensagem = models.TextField()
    data = models.DateTimeField(auto_now_add=True)
    ultima_edicao = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chamado_interacao"
        default_permissions = ()

    def __str__(self):
        return f"{self.usuario} - {self.data:%d/%m/%Y %H:%M}"


class OrdemServico(models.Model):
    class Status(models.TextChoices):
        ABERTA = "ABERTA", "Aberta"
        EM_EXECUCAO = "EM_EXECUCAO", "Em execução"
        FINALIZADA = "FINALIZADA", "Finalizada"
        CANCELADA = "CANCELADA", "Cancelada"
        PARADA = "PARADA", "Parada"

    chamado = models.ForeignKey("Chamado", on_delete=models.SET_NULL, null=True, blank=True)
    responsaveis = ArrayField(
        base_field=models.IntegerField(),
        blank=True,
        null=True,
        default=list,
        verbose_name="IDs dos responsáveis",
    )
    descricao = models.TextField(blank=False, null=False, default=None)
    recurso = models.ForeignKey("accounts.Recurso", on_delete=models.PROTECT)
    inicio_prev = models.DateTimeField(null=True, blank=True)
    final_prev = models.DateTimeField(null=True, blank=True)
    inicio_real = models.DateTimeField(null=True, blank=True)
    final_real = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ABERTA)
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ordem_servico"
        default_permissions = ()

    def __str__(self):
        return f"OS {self.id} - {self.get_status_display()}"


class Interacao_OS(models.Model):
    ordem_servico = models.ForeignKey(
        OrdemServico, on_delete=models.CASCADE, related_name="interacoesos"
    )
    usuario = models.ForeignKey("accounts.CustomUser", on_delete=models.SET_NULL, null=True)
    inicio = models.DateTimeField(null=True, blank=True)
    fim = models.DateTimeField(null=True, blank=True)
    descricao = models.TextField(blank=True)
    data_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ordem_servico_interacao"
        default_permissions = ()

    def __str__(self):
        return f"Interação OS {self.ordem_servico_id} - {self.usuario}"
