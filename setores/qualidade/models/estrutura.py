from django.conf import settings
from django.db import models


class Reuniao(models.Model):
    data_hora_inicio = models.DateTimeField(verbose_name="Data e hora início")
    data_hora_fim = models.DateTimeField(blank=True, null=True, verbose_name="Data e hora fim")

    class Meta:
        verbose_name = "Reunião"
        verbose_name_plural = "Reuniões"
        db_table = 'qualidade"."reuniao'
        ordering = ["-data_hora_inicio"]
        default_permissions = ()

    def __str__(self):
        return f"Reunião {self.pk}"


class ReuniaoParticipante(models.Model):
    class Setor(models.TextChoices):
        CONVERSAO = "conversao", "Conversão"
        INDUSTRIAL = "industrial", "Industrial"
        QUALIDADE = "qualidade", "Qualidade"
        LOGISTICA = "logistica", "Logística"
        PCP = "pcp", "PCP"

    reuniao = models.ForeignKey(
        Reuniao,
        on_delete=models.CASCADE,
        related_name="participantes",
        verbose_name="Reunião",
    )
    nome = models.CharField(max_length=150, verbose_name="Nome")
    setor = models.CharField(
        max_length=20, choices=Setor.choices, blank=True, default="", verbose_name="Setor"
    )

    class Meta:
        verbose_name = "Participante da reunião"
        verbose_name_plural = "Participantes da reunião"
        db_table = 'qualidade"."reuniao_participantes'
        ordering = ["nome"]
        default_permissions = ()

    def __str__(self):
        setor = self.get_setor_display()
        return f"{self.nome} - {setor}" if setor else self.nome


class ObservacaoEtiqueta(models.Model):
    descricao = models.CharField(max_length=255, unique=True, verbose_name="Descrição")
    ativo = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Observação de etiqueta"
        verbose_name_plural = "Observações de etiqueta"
        db_table = 'qualidade"."observacao_etiqueta'
        ordering = ["descricao"]
        default_permissions = ()

    def __str__(self):
        return self.descricao


class LiberacaoLote(models.Model):
    class Status(models.IntegerChoices):
        # Catálogo fechado de estados da fila de integração do lote.
        NAO_INTEGRADO = 0, "Não integrado"
        INTEGRADO = 1, "Integrado"
        PROCESSANDO = 2, "Processando"
        # LOCAL saiu do 3: o valor fica reservado ao esquema numérico comum das filas de integração.
        LOCAL = 4, "Local (sem integração)"

    codemp = models.IntegerField(default=0, verbose_name="Empresa")
    numbob = models.IntegerField(blank=True, null=True, verbose_name="Número da bobina")
    codpro = models.CharField(max_length=50, verbose_name="Produto")
    codder = models.CharField(max_length=20, verbose_name="Derivação")
    coddep = models.CharField(max_length=20, verbose_name="Depósito")
    deptrf = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Depósito transferido"
    )
    codtns = models.CharField(max_length=50, blank=True, default="", verbose_name="Transação ERP")
    codigo_integrador = models.CharField(max_length=50, verbose_name="Código Integrador")
    codlot = models.CharField(max_length=50, verbose_name="Lote")
    lottrf = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Lote transferido"
    )
    codori = models.CharField(max_length=20, blank=True, default="", verbose_name="Origem")
    numorp = models.IntegerField(blank=True, null=True, verbose_name="Ordem de produção")
    qtdtot = models.FloatField(verbose_name="Quantidade total")
    qtdlibe = models.FloatField(default=0, verbose_name="Quantidade liberada")
    qtdaverm = models.FloatField(default=0, verbose_name="Quantidade área vermelha")
    qtdrefu = models.FloatField(default=0, verbose_name="Quantidade refugada")
    qtdrecl = models.FloatField(default=0, verbose_name="Quantidade reclassificada")
    qtdprensa = models.FloatField(default=0, verbose_name="Quantidade para prensa")
    codpro_recl = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Produto reclassificado"
    )
    codder_recl = models.CharField(
        max_length=20, blank=True, default="", verbose_name="Derivação reclassificada"
    )
    coddft = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Código do motivo"
    )
    etiqueta = models.ForeignKey(
        ObservacaoEtiqueta,
        on_delete=models.PROTECT,
        related_name="liberacoes_lote",
        db_column="id_etiqueta",
        verbose_name="Observação etiqueta",
        blank=True,
        null=True,
    )
    observacao_geral = models.TextField(blank=True, default="", verbose_name="Observação geral")
    log = models.TextField(blank=True, default="", verbose_name="Log")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="liberacoes_lote_qualidade",
        verbose_name="Usuário",
    )
    status = models.IntegerField(
        default=Status.NAO_INTEGRADO, choices=Status.choices, verbose_name="Status"
    )
    datger = models.DateTimeField(blank=True, null=True, verbose_name="Data/Hora Geração")
    data_hora = models.DateTimeField(auto_now_add=True, verbose_name="Data e hora")
    reuniao = models.ForeignKey(
        Reuniao,
        on_delete=models.PROTECT,
        related_name="liberacoes_lote",
        verbose_name="Reunião",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Liberação de lote"
        verbose_name_plural = "Liberações de lote"
        db_table = 'qualidade"."liberacao_lote'
        ordering = ["-data_hora"]
        default_permissions = ()
        indexes = [
            models.Index(
                fields=["codemp", "numbob", "codlot", "codpro", "codder", "-id"],
                name="idx_lote_grupo_id",
            ),
            models.Index(fields=["status", "-id"], name="idx_lote_status_id"),
        ]

    def __str__(self):
        return f"{self.codlot} - Bobina {self.numbob}"


class WMS_IntegraçãoOP(models.Model):
    class TipoEnvio(models.TextChoices):
        NOVO_LOTE = "novo_lote", "Novo lote"
        AJUSTE = "ajuste", "Ajuste"

    # Aliases para compatibilidade — consumidores referenciam WMS_IntegraçãoOP.TIPO_NOVO_LOTE.
    TIPO_NOVO_LOTE = TipoEnvio.NOVO_LOTE
    TIPO_AJUSTE = TipoEnvio.AJUSTE

    class Status(models.IntegerChoices):
        # Catálogo fechado de estados da fila de integração WMS.
        NAO_INTEGRADO = 0, "Não integrado"
        INTEGRADO = 1, "Integrado"
        PROCESSANDO = 2, "Processando"

    id = models.BigAutoField(primary_key=True)
    codemp = models.IntegerField(verbose_name="Código da Empresa")
    origem = models.CharField(max_length=10, verbose_name="Origem")
    op = models.IntegerField(verbose_name="Ordem de Produção")
    lote = models.CharField(max_length=50, default="0", verbose_name="Lote")
    palete = models.CharField(max_length=50, blank=True, default="", verbose_name="Palete")
    quantidade = models.DecimalField(max_digits=12, decimal_places=4, verbose_name="Quantidade")
    codigo_integrador = models.CharField(max_length=50, verbose_name="Código Integrador")
    local = models.CharField(max_length=50, blank=True, default="", verbose_name="Local WMS")
    codpro = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Código do Produto"
    )
    codder = models.IntegerField(null=True, blank=True, verbose_name="Derivação")
    log = models.TextField(blank=True, default="", verbose_name="Log")
    status = models.IntegerField(
        default=Status.NAO_INTEGRADO, choices=Status.choices, verbose_name="Status"
    )
    tipo_envio = models.CharField(
        max_length=20,
        choices=TipoEnvio.choices,
        default=TipoEnvio.NOVO_LOTE,
        verbose_name="Tipo de envio WMS",
    )
    datger = models.DateTimeField(blank=True, null=True, verbose_name="Data/Hora Geração")
    data_hora = models.DateTimeField(auto_now=True, verbose_name="Data/Hora Log")
    reuniao = models.ForeignKey(
        Reuniao,
        on_delete=models.PROTECT,
        related_name="integracoes_wms",
        verbose_name="Reunião",
        blank=True,
        null=True,
    )

    class Meta:
        db_table = 'qualidade"."wms_integracao_op'
        verbose_name = "Integração WMS OP"
        verbose_name_plural = "Integrações WMS OP"
        default_permissions = ()

    def __str__(self):
        return f"OP {self.op} - Qtd: {self.quantidade}"
