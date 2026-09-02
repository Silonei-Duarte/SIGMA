from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models


class Sequenciamento(models.Model):
    recurso = models.ForeignKey(
        "accounts.Recurso",
        on_delete=models.PROTECT,
        related_name="sequenciamentos",
        verbose_name="Recurso",
    )
    ordenacao = models.IntegerField(verbose_name="Ordenação")
    origem = models.CharField(max_length=10, verbose_name="Origem")
    op = models.IntegerField(verbose_name="Ordem de Produção")
    estagio = models.IntegerField(verbose_name="Estágio")
    seqrot = models.IntegerField(verbose_name="Seq. Roteiro")
    descricao = models.CharField(max_length=255, blank=True, default="", verbose_name="Descrição")
    codproduto = models.CharField(max_length=50, verbose_name="Código do Produto")
    derivacao = models.CharField(max_length=50, blank=True, default="", verbose_name="Derivação")
    tempo = models.FloatField(verbose_name="Tempo")
    operacao = models.CharField(max_length=100, verbose_name="Operação")

    class Meta:
        db_table = 'producao"."sequenciamento'
        verbose_name = "Sequenciamento"
        verbose_name_plural = "Sequenciamentos"
        ordering = ["ordenacao"]
        default_permissions = ()

    def __str__(self):
        return f"{self.recurso} - OP {self.op} - {self.operacao}"

    @property
    def codigo_barra(self):
        """
        Formato:
        [codemp(4)] [origem(2)] [op(9)] [estagio(4)] [seqrot(4)]
        """
        codemp = self.recurso.centro_recurso.setor.departamento.filial.empresa.codemp
        origem = int(self.origem) if str(self.origem).isdigit() else 0

        return f"{codemp:04d}{origem:02d}{self.op:09d}{self.estagio:04d}{self.seqrot:04d}"


class Apontamento(models.Model):
    id = models.BigAutoField(primary_key=True)
    recurso = models.ForeignKey(
        "accounts.Recurso",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="apontamentos",
        verbose_name="Recurso",
    )
    usuario = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="apontamentos_registrados",
        verbose_name="Usuário",
    )
    codemp = models.IntegerField(verbose_name="Empresa")
    origem = models.CharField(max_length=10, verbose_name="Origem")
    numorp = models.IntegerField(verbose_name="Ordem de Produção")
    codetg = models.IntegerField(verbose_name="Estágio")
    seqrot = models.IntegerField(verbose_name="Seq. Roteiro")
    numcad = models.IntegerField(verbose_name="Operador")
    qtdre1 = models.DecimalField(max_digits=12, decimal_places=4, verbose_name="Quantidade")
    qtdrfg = models.DecimalField(max_digits=12, decimal_places=4, verbose_name="Refugo", default=0)
    lote = models.CharField(max_length=50, blank=True, default="", verbose_name="Lote")
    log = models.TextField(blank=True, default="", verbose_name="Log do Webservice")

    class Status(models.IntegerChoices):
        NAO_INTEGRADO = 0, "Não integrado"
        INTEGRADO = 1, "Integrado"
        PROCESSANDO = 2, "Processando"
        EXCLUIDO = 3, "Excluído"

    status = models.IntegerField(
        choices=Status.choices,
        default=Status.NAO_INTEGRADO,
        verbose_name="Status",
    )
    # datger fixa o momento da geração do registro; data_hora é auto_now e muda a cada save.
    datger = models.DateTimeField(blank=True, null=True, verbose_name="Data/Hora Geração")
    data_hora = models.DateTimeField(auto_now=True, verbose_name="Data/Hora")

    codigo_integrador = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Código Integrador"
    )
    datmov = models.CharField(max_length=10, blank=True, default="", verbose_name="Data Movimento")
    hormov = models.CharField(max_length=8, blank=True, default="", verbose_name="Hora Movimento")
    bobina = models.IntegerField(null=True, blank=True, verbose_name="Bobina Atual")
    origem_peso = models.CharField(
        max_length=20, blank=True, default="", verbose_name="Origem do Peso"
    )
    balanca = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True, verbose_name="Balança"
    )

    class Meta:
        db_table = 'producao"."apontamento'
        verbose_name = "Apontamento Sapiens"
        verbose_name_plural = "Apontamentos Sapiens"
        default_permissions = ()
        indexes = [
            models.Index(fields=["codemp", "-id"], name="idx_apont_codemp_id"),
            models.Index(
                fields=["status", "codemp", "origem", "numorp", "codetg", "seqrot", "id"],
                name="idx_apont_fila_chave",
            ),
        ]

    def __str__(self):
        return f"OP {self.numorp} - Estágio {self.codetg} - Qtd {self.qtdre1}"


class CorrecaoLote(models.Model):
    """Estado persistente de uma correção manual enviada ao ERP."""

    class Status(models.TextChoices):
        EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
        CONCLUIDA = "CONCLUIDA", "Concluída"
        FALHA = "FALHA", "Falha"

    codemp = models.IntegerField(verbose_name="Empresa")
    lote = models.CharField(max_length=50, verbose_name="Lote")
    quantidade = models.DecimalField(max_digits=12, decimal_places=4, verbose_name="Quantidade")
    excluir_apontamento = models.BooleanField(default=False, verbose_name="Excluir apontamento")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.EM_ANDAMENTO,
        verbose_name="Status",
    )
    mensagem = models.TextField(blank=True, default="", verbose_name="Resultado")
    iniciado_em = models.DateTimeField(auto_now_add=True, verbose_name="Iniciado em")
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    class Meta:
        db_table = 'producao"."correcao_lote'
        verbose_name = "Correção de lote"
        verbose_name_plural = "Correções de lote"
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=["codemp", "lote"], name="uniq_correcao_lote_empresa")
        ]

    def __str__(self):
        return f"Empresa {self.codemp} - lote {self.lote} ({self.status})"


class ParadaMaquina(models.Model):
    class Tipo(models.IntegerChoices):
        MANUAL = 1, "Manual"
        SINAL = 2, "Sinal"

    id = models.BigAutoField(primary_key=True)
    recurso = models.ForeignKey(
        "accounts.Recurso",
        on_delete=models.PROTECT,
        related_name="paradas_maquina",
        verbose_name="Recurso",
    )
    periodos_produtivos = models.ManyToManyField(
        "producao.LogTrocaOPAtiva",
        related_name="paradas",
        verbose_name="Períodos produtivos afetados",
    )
    operador = models.CharField(max_length=100, blank=True, verbose_name="Operador")
    inicio = models.DateTimeField(verbose_name="Data/Hora Início")
    fim = models.DateTimeField(null=True, blank=True, verbose_name="Data/Hora Fim")
    usuario = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paradas_maquina_registradas",
        verbose_name="Usuário",
    )
    tipo = models.SmallIntegerField(choices=Tipo.choices, verbose_name="Tipo")
    data_hora = models.DateTimeField(null=True, blank=True, verbose_name="Data/Hora")

    class Meta:
        db_table = 'producao"."paradas_maquina'
        verbose_name = "Parada de Máquina"
        verbose_name_plural = "Paradas de Máquina"
        ordering = ["-inicio"]
        default_permissions = ()
        permissions = [
            ("pode_alterar_paradas", "Pode Alterar Paradas"),
        ]
        indexes = [
            models.Index(fields=["recurso", "fim"], name="idx_parada_recurso_fim"),
            models.Index(fields=["tipo", "fim"], name="idx_parada_tipo_fim"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["recurso"],
                condition=models.Q(fim__isnull=True),
                name="uniq_parada_aberta_recurso",
            )
        ]

    def __str__(self):
        return f"{self.recurso.codigo} - parada ({self.inicio} a {self.fim})"


class JustificativaParada(models.Model):
    id = models.BigAutoField(primary_key=True)
    parada = models.ForeignKey(
        "producao.ParadaMaquina",
        db_column="id_parada",
        on_delete=models.CASCADE,
        related_name="justificativas",
        verbose_name="Parada",
    )
    sequencia = models.PositiveIntegerField(verbose_name="Sequência")
    motivo = models.CharField(max_length=4, verbose_name="Motivo ERP")
    parcial = models.DateTimeField(verbose_name="Início Parcial")
    tempo = models.DurationField(null=True, blank=True, verbose_name="Tempo")
    data_hora = models.DateTimeField(null=True, blank=True, verbose_name="Data/Hora do Log")

    class Meta:
        db_table = 'producao"."justificativas_paradas'
        verbose_name = "Justificativa de Parada"
        verbose_name_plural = "Justificativas de Paradas"
        ordering = ["sequencia"]
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(
                fields=["parada", "sequencia"], name="uq_just_parada_sequencia"
            ),
            models.UniqueConstraint(
                fields=["parada"],
                condition=models.Q(tempo__isnull=True),
                name="uq_just_parada_aberta",
            ),
        ]

    def __str__(self):
        return f"{self.parada} - justificativa {self.sequencia}"


class RegraParadaRecurso(models.Model):
    recurso = models.OneToOneField(
        "accounts.Recurso",
        on_delete=models.CASCADE,
        related_name="regra_parada_automatica",
        verbose_name="Recurso",
    )
    ativa = models.BooleanField(default=False, verbose_name="Regra automática ativa")
    regra = models.JSONField(default=dict, blank=True, verbose_name="Regra de parada")

    class Meta:
        db_table = 'producao"."regras_parada_recursos'
        verbose_name = "Regra automática de parada do recurso"
        verbose_name_plural = "Regras automáticas de parada dos recursos"
        default_permissions = ()

    def __str__(self):
        return f"Regra automática de parada - {self.recurso}"

    def clean(self):
        super().clean()
        if not self.recurso_id:
            return
        tempo_parada_aut = self.recurso.tempo_parada_aut
        if self.ativa and tempo_parada_aut is None:
            raise ValidationError(
                {"ativa": "Informe o Tempo Parada Automática no recurso antes de ativar a regra."}
            )
        elif self.ativa and tempo_parada_aut < timedelta():
            raise ValidationError({"ativa": "O Tempo Parada Automática não pode ser negativo."})
        if self.regra != {}:
            from producao.services.paradas_automaticas import validar_regra_parada

            validar_regra_parada(self.regra, self.recurso)
        elif self.ativa:
            raise ValidationError({"regra": "Inclua ao menos uma condição para ativar a regra."})


class LogTrocaOPAtiva(models.Model):
    id = models.BigAutoField(primary_key=True)
    recurso = models.ForeignKey(
        "accounts.Recurso",
        on_delete=models.PROTECT,
        related_name="logs_troca_op_ativa",
        verbose_name="Recurso",
    )
    usuario = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trocas_op_ativas_registradas",
        verbose_name="Usuário",
    )
    origem = models.CharField(max_length=10, blank=True, default="", verbose_name="Origem")
    op = models.IntegerField(null=True, blank=True, verbose_name="Ordem de Produção")
    estagio = models.IntegerField(null=True, blank=True, verbose_name="Estágio")
    seqrot = models.IntegerField(null=True, blank=True, verbose_name="Seq. Roteiro")
    horario_troca = models.DateTimeField(verbose_name="Horário da Troca")
    horario_saida = models.DateTimeField(null=True, blank=True, verbose_name="Horário de Saída")
    id_operador = models.IntegerField(null=True, blank=True, verbose_name="ID Operador")
    log = models.TextField(blank=True, default="", verbose_name="Log")
    data_hora = models.DateTimeField(auto_now=True, verbose_name="Data/Hora")

    class Meta:
        db_table = 'producao"."logs_troca_op_ativa'
        verbose_name = "Log de Troca de OP Ativa"
        verbose_name_plural = "Logs de Troca de OP Ativa"
        ordering = ["-horario_troca"]
        default_permissions = ()
        indexes = [
            models.Index(fields=["-horario_troca", "-id"], name="idx_log_op_troca_id"),
        ]

    def __str__(self):
        return f"{self.recurso} - {self.codigo_barra} - {self.horario_troca}"

    @property
    def codigo_barra(self):
        if self.op is None:
            return ""
        codemp = self.recurso.centro_recurso.setor.departamento.filial.empresa.codemp
        origem = int(self.origem) if str(self.origem).isdigit() else 0
        return f"{codemp:04d}{origem:02d}{self.op:09d}{int(self.estagio or 0):04d}{int(self.seqrot or 0):04d}"


class PacoteTempoERP(models.Model):
    class Status(models.IntegerChoices):
        # Alinhado às demais filas de integração do SIGMA: não existe estado
        # ERRO próprio — falha de envio volta a PENDENTE e quem diferencia é
        # o campo `log` (motivo mascarado). ENVIADO passou a se chamar
        # INTEGRADO, mesmo vocabulário das outras filas.
        PENDENTE = 0, "Pendente"
        INTEGRADO = 1, "Integrado"
        PROCESSANDO = 2, "Processando"

    id = models.BigAutoField(primary_key=True)
    troca_op_ativa = models.ForeignKey(
        "producao.LogTrocaOPAtiva",
        on_delete=models.PROTECT,
        related_name="pacotes_tempo_erp",
        verbose_name="Troca de OP Ativa",
    )
    corte_inicio_real = models.DateTimeField(verbose_name="Corte Início Real")
    corte_fim_real = models.DateTimeField(verbose_name="Corte Fim Real")
    log = models.TextField(blank=True, default="", verbose_name="Log")
    datger = models.DateTimeField(blank=True, null=True, verbose_name="Data/Hora Geração")
    data_hora_log = models.DateTimeField(auto_now=True, verbose_name="Data/Hora Log")
    status = models.SmallIntegerField(
        choices=Status.choices,
        default=Status.PENDENTE,
        verbose_name="Status",
    )

    class Meta:
        db_table = 'producao"."pacotes_tempo_erp'
        verbose_name = "Pacote de Tempo ERP"
        verbose_name_plural = "Pacotes de Tempo ERP"
        ordering = ["-corte_fim_real", "-id"]
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(
                fields=["troca_op_ativa", "corte_inicio_real", "corte_fim_real"],
                name="uq_pacote_tempo_erp_corte",
            ),
        ]
        indexes = [
            models.Index(fields=["-corte_fim_real", "-id"], name="idx_pacote_tempo_erp_corte"),
            models.Index(
                fields=["troca_op_ativa", "-corte_fim_real"], name="idx_pacote_tempo_erp_troca"
            ),
        ]

    def __str__(self):
        return f"{self.troca_op_ativa} - {self.corte_inicio_real} a {self.corte_fim_real}"


class ItemPacoteTempoERP(models.Model):
    class TipoRegistro(models.TextChoices):
        PRODUCAO = "PRODUCAO", "Produção"
        PARADA = "PARADA", "Parada"

    id = models.BigAutoField(primary_key=True)
    pacote_tempo_erp = models.ForeignKey(
        "producao.PacoteTempoERP",
        on_delete=models.CASCADE,
        related_name="itens",
        verbose_name="Pacote de Tempo ERP",
    )
    tipo_registro = models.CharField(
        max_length=10, choices=TipoRegistro.choices, verbose_name="Tipo de Registro"
    )
    operador = models.IntegerField(verbose_name="Operador")
    motivo = models.CharField(max_length=4, blank=True, default="", verbose_name="Motivo ERP")
    data_inicio = models.DateField(verbose_name="Data Início")
    hora_inicio = models.TimeField(verbose_name="Hora Início")
    data_fim = models.DateField(verbose_name="Data Fim")
    hora_fim = models.TimeField(verbose_name="Hora Fim")

    class Meta:
        db_table = 'producao"."itens_pacote_tempo_erp'
        verbose_name = "Item de Pacote de Tempo ERP"
        verbose_name_plural = "Itens de Pacote de Tempo ERP"
        ordering = ["id"]
        default_permissions = ()

    def __str__(self):
        return f"{self.pacote_tempo_erp} - {self.get_tipo_registro_display()}"


class ApontamentoComponente(models.Model):
    id = models.BigAutoField(primary_key=True)
    recurso = models.ForeignKey(
        "accounts.Recurso",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="apontamentos_componentes",
        verbose_name="Recurso",
    )
    usuario = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="apontamentos_componentes_registrados",
        verbose_name="Usuário",
    )
    codemp = models.IntegerField(verbose_name="Empresa")
    origem = models.CharField(max_length=10, verbose_name="Origem")
    numorp = models.IntegerField(verbose_name="Ordem de Produção")
    codetg = models.IntegerField(verbose_name="Estágio")
    seqrot = models.IntegerField(verbose_name="Seq. Roteiro")
    numcad = models.IntegerField(verbose_name="Operador")
    codigo_integrador = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Código Integrador"
    )
    datmov = models.CharField(max_length=10, blank=True, default="", verbose_name="Data Movimento")
    hormov = models.CharField(max_length=8, blank=True, default="", verbose_name="Hora Movimento")
    lote = models.CharField(max_length=50, verbose_name="Lote")
    log = models.TextField(blank=True, default="", verbose_name="Log do Webservice")

    class Status(models.IntegerChoices):
        NAO_INTEGRADO = 0, "Não integrado"
        INTEGRADO = 1, "Integrado"
        PROCESSANDO = 2, "Processando"
        EXCLUIDO = 3, "Excluído"

    status = models.IntegerField(
        choices=Status.choices,
        default=Status.NAO_INTEGRADO,
        verbose_name="Status",
    )
    datger = models.DateTimeField(blank=True, null=True, verbose_name="Data/Hora Geração")
    data_hora = models.DateTimeField(auto_now=True, verbose_name="Data/Hora")

    class Meta:
        db_table = 'producao"."apontamento_componente'
        verbose_name = "Apontamento de Componente"
        verbose_name_plural = "Apontamentos de Componentes"
        default_permissions = ()
        indexes = [
            models.Index(fields=["codemp", "-id"], name="idx_comp_codemp_id"),
            models.Index(
                fields=["status", "codemp", "origem", "numorp", "codetg", "seqrot"],
                name="idx_comp_fila_chave",
            ),
        ]

    def __str__(self):
        return f"OP {self.numorp} - Estágio {self.codetg} - Lote {self.lote}"


class BobinaConsumoRecurso(models.Model):
    class Status(models.IntegerChoices):
        EM_FILA = 0, "Em fila"
        EM_CONSUMO = 1, "Em consumo"
        FINALIZADO = 2, "Finalizado"

    id = models.BigAutoField(primary_key=True)
    recurso = models.ForeignKey(
        "accounts.Recurso",
        on_delete=models.PROTECT,
        related_name="bobinas_consumo",
        verbose_name="Recurso",
    )
    usuario = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bobinas_consumo_alocadas",
        verbose_name="Usuário",
    )
    codemp = models.IntegerField(verbose_name="Empresa")
    lote = models.CharField(max_length=50, verbose_name="Lote")
    codpro = models.CharField(max_length=50, blank=True, default="", verbose_name="Produto")
    codder = models.CharField(max_length=50, blank=True, default="", verbose_name="Derivação")
    quantidade_alocada = models.DecimalField(
        max_digits=12, decimal_places=4, verbose_name="Quantidade Alocada"
    )
    quantidade_restante = models.DecimalField(
        max_digits=12, decimal_places=4, verbose_name="Quantidade Restante"
    )
    status = models.IntegerField(
        choices=Status.choices, default=Status.EM_FILA, verbose_name="Status"
    )
    ordem_fila = models.IntegerField(null=True, blank=True, verbose_name="Ordem na Fila")
    data_hora_alocacao = models.DateTimeField(auto_now_add=True, verbose_name="Data/Hora Alocação")
    data_hora_status = models.DateTimeField(auto_now=True, verbose_name="Data/Hora Status")

    class Meta:
        db_table = 'producao"."bobinas_consumo_recurso'
        verbose_name = "Bobina em Consumo do Recurso"
        verbose_name_plural = "Bobinas em Consumo do Recurso"
        ordering = ["status", "ordem_fila", "id"]
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(
                fields=["recurso", "lote"],
                condition=models.Q(status__in=[0, 1]),
                name="uq_bobina_consumo_lote_ativo",
            ),
        ]
        indexes = [
            models.Index(
                fields=["recurso", "status", "ordem_fila"], name="idx_bobina_consumo_fila"
            ),
        ]

    def __str__(self):
        return f"{self.recurso} - Lote {self.lote} - {self.get_status_display()}"


class BaixaComponente(models.Model):
    id = models.BigAutoField(primary_key=True)
    recurso = models.ForeignKey(
        "accounts.Recurso",
        on_delete=models.PROTECT,
        related_name="baixas_componentes",
        verbose_name="Recurso",
    )
    usuario = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="baixas_componentes_registradas",
        verbose_name="Usuário",
    )
    codemp = models.IntegerField(verbose_name="Empresa")
    origem = models.CharField(max_length=10, verbose_name="Origem")
    numorp = models.IntegerField(verbose_name="Ordem de Produção")
    codetg = models.IntegerField(verbose_name="Estágio")
    seqrot = models.IntegerField(verbose_name="Seq. Roteiro")
    lotdes = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Lote Destino (Produto Produzido)"
    )
    codcmp = models.CharField(max_length=50, verbose_name="Componente")
    dercmp = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Derivação Componente"
    )
    qtduti = models.DecimalField(
        max_digits=14, decimal_places=4, verbose_name="Quantidade Utilizada"
    )
    codigo_integrador = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Código Integrador"
    )
    datmov = models.CharField(max_length=10, blank=True, default="", verbose_name="Data Movimento")
    hormov = models.CharField(max_length=8, blank=True, default="", verbose_name="Hora Movimento")
    codlot = models.CharField(max_length=50, verbose_name="Lote da Bobina em Consumo")
    repesagem = models.CharField(max_length=1, default="N", verbose_name="Repesagem (S/N)")
    consumototal = models.CharField(max_length=1, default="N", verbose_name="Consumo Total (S/N)")
    log = models.TextField(blank=True, default="", verbose_name="Log do Webservice")

    class Status(models.IntegerChoices):
        NAO_INTEGRADO = 0, "Não integrado"
        INTEGRADO = 1, "Integrado"
        PROCESSANDO = 2, "Processando"
        EXCLUIDO = 3, "Excluído"

    status = models.IntegerField(
        choices=Status.choices,
        default=Status.NAO_INTEGRADO,
        verbose_name="Status",
    )
    datger = models.DateTimeField(blank=True, null=True, verbose_name="Data/Hora Geração")
    data_hora = models.DateTimeField(verbose_name="Data/Hora")

    class Meta:
        db_table = 'producao"."baixa_componentes'
        verbose_name = "Baixa de Componente"
        verbose_name_plural = "Baixas de Componentes"
        default_permissions = ()
        indexes = [
            models.Index(fields=["codemp", "-id"], name="idx_baixa_comp_codemp_id"),
            models.Index(
                fields=["status", "codemp", "origem", "numorp", "codetg", "seqrot"],
                name="idx_baixa_comp_fila_chave",
            ),
            models.Index(fields=["status", "codlot", "id"], name="idx_baixa_comp_fila_lote"),
        ]

    def __str__(self):
        return f"OP {self.numorp} - Componente {self.codcmp} - Lote {self.codlot}"
