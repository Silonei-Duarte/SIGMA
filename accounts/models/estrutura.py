# accounts/models.py
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField
from django.db import models


class CustomUser(AbstractUser):
    filial = models.ForeignKey("accounts.Filial", on_delete=models.SET_NULL, null=True, blank=True)
    idintegracao = models.IntegerField(null=True, blank=True)
    idoperador = models.IntegerField(null=True, blank=True, verbose_name="ID Operador")
    paginicial = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "accounts_customuser"
        default_permissions = ()


class Empresa(models.Model):
    id = models.AutoField(primary_key=True)
    codemp = models.IntegerField(unique=True, verbose_name="Código da Empresa")
    nome = models.CharField(max_length=255, verbose_name="Nome")
    fantasia = models.CharField(max_length=255, verbose_name="Nome Fantasia")
    loteatual = models.CharField(max_length=50, default="100000000", verbose_name="Lote Atual")
    ativa = models.BooleanField(default=True, verbose_name="Ativa")

    class Meta:
        db_table = "empresas"
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        ordering = ["nome"]
        default_permissions = ()

    def __str__(self):
        return f"{self.codemp} - {self.nome}"


class Filial(models.Model):
    id = models.AutoField(primary_key=True)
    empresa = models.ForeignKey(  # 🔹 aqui vira FK de verdade
        Empresa, on_delete=models.PROTECT, related_name="filiais", verbose_name="Empresa"
    )
    codfil = models.IntegerField(verbose_name="Código da Filial")
    nome = models.CharField(max_length=255, verbose_name="Nome")
    fantasia = models.CharField(max_length=255, verbose_name="Nome Fantasia")
    cnpj = models.CharField(max_length=18, verbose_name="CNPJ")
    ativa = models.BooleanField(default=True, verbose_name="Ativa")

    class Meta:
        db_table = "filial"
        verbose_name = "Filial"
        verbose_name_plural = "Filiais"
        unique_together = ("empresa", "codfil")  # 🔹 agora com FK
        ordering = ["nome"]
        default_permissions = ()

    def __str__(self):
        return f"{self.empresa.codemp}.{self.codfil} - {self.nome}"


class ParametrosFilial(models.Model):
    CAMPOS = [
        "tempo_sem_comunicacao_manual",
        "limite_apontamento_minimo",
        "limite_apontamento_maximo",
        "codtns",
        "codtns_area_vermelha",
        "deposito_apontamento_erp",
        "deposito_armazenamento_erp",
        "deposito_armazenamento_wms",
        "deposito_area_vermelha_erp",
        "deposito_area_vermelha_wms",
        "produto_refugo",
        "derivacao_refugo",
        "origens_area_vermelha",
        "transacoes_saida_consumo_producao",
        "transacoes_entrada_producao_consumo",
    ]
    PADRAO = {
        "tempo_sem_comunicacao_manual": 15,
        "limite_apontamento_minimo": 0,
        "limite_apontamento_maximo": 4000,
        "codtns": "",
        "codtns_area_vermelha": "",
        "deposito_apontamento_erp": "",
        "deposito_armazenamento_erp": "",
        "deposito_armazenamento_wms": "",
        "deposito_area_vermelha_erp": "",
        "deposito_area_vermelha_wms": "",
        "produto_refugo": "",
        "derivacao_refugo": "",
        "origens_area_vermelha": "",
        "transacoes_saida_consumo_producao": "",
        "transacoes_entrada_producao_consumo": "",
    }

    filial = models.OneToOneField(
        "accounts.Filial",
        on_delete=models.CASCADE,
        related_name="parametros_filial",
        verbose_name="Filial",
    )
    tempo_sem_comunicacao_manual = models.PositiveIntegerField(
        default=15, verbose_name="Tempo sem comunicação para apontar manualmente (segundos)"
    )
    limite_apontamento_minimo = models.FloatField(
        default=0, verbose_name="Limite mínimo de apontamento"
    )
    limite_apontamento_maximo = models.FloatField(
        default=4000, verbose_name="Limite máximo de apontamento"
    )
    codtns = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Transação de ERP Saída por Transferência Interna",
    )
    codtns_area_vermelha = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Transação do ERP Saída Área Vermelha"
    )
    deposito_apontamento_erp = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Depósito de consulta apontamento ERP"
    )
    deposito_armazenamento_erp = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Depósito de armazenamento ERP"
    )
    deposito_armazenamento_wms = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Local de liberação WMS"
    )
    deposito_area_vermelha_erp = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Depósito área vermelha ERP"
    )
    deposito_area_vermelha_wms = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Local área vermelha WMS"
    )
    produto_refugo = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Produto refugo"
    )
    derivacao_refugo = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Derivação refugo"
    )
    origens_area_vermelha = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Origens área vermelha"
    )
    transacoes_saida_consumo_producao = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Transações de saída para consumo na produção",
    )
    transacoes_entrada_producao_consumo = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Transações de entrada por Produção"
    )

    class Meta:
        db_table = "parametros_filial"
        verbose_name = "Parâmetros da Filial"
        verbose_name_plural = "Parâmetros das Filiais"
        default_permissions = ()

    def __str__(self):
        return f"Parâmetros - {self.filial}"

    @classmethod
    def defaults(cls):
        return cls.PADRAO.copy()

    def as_dict(self):
        return {campo: getattr(self, campo) for campo in self.CAMPOS}


PARAMETROS_INTEGRACAO_CENTRO_RECURSO = [
    "deposito_apontamento_erp",
    "deposito_armazenamento_erp",
    "deposito_armazenamento_wms",
    "deposito_area_vermelha_erp",
    "deposito_area_vermelha_wms",
    "produto_refugo",
    "derivacao_refugo",
    "cod_alchemy",
]


class Departamento(models.Model):
    id = models.AutoField(primary_key=True)
    filial = models.ForeignKey("accounts.Filial", on_delete=models.PROTECT, verbose_name="Filial")
    descricao = models.CharField(max_length=255, verbose_name="Descrição")

    class Meta:
        db_table = "departamentos"
        verbose_name = "Departamento"
        verbose_name_plural = "Departamentos"
        ordering = ["descricao"]
        default_permissions = ()

    def __str__(self):
        return f"{self.filial} - {self.descricao}"


class TurnoBase(models.Model):
    codigo = models.CharField(max_length=20, unique=True, verbose_name="Código")
    descricao = models.CharField(max_length=255, verbose_name="Descrição")
    ordenacao = models.IntegerField(verbose_name="Ordenação")
    calendario = models.ForeignKey(  # 🔹 nova FK
        "accounts.Calendario", on_delete=models.PROTECT, verbose_name="Calendário"
    )

    class Meta:
        db_table = "turnos_base"
        verbose_name = "Turno Base"
        verbose_name_plural = "Turnos Base"
        default_permissions = ()

    def __str__(self):
        return f"{self.codigo} - {self.descricao}"


class Calendario(models.Model):
    filial = models.ForeignKey(
        "accounts.Filial",
        on_delete=models.PROTECT,
        related_name="calendarios",
        verbose_name="Filial",
    )
    descricao = models.CharField(max_length=100, verbose_name="Descrição")

    class Meta:
        db_table = "calendario"
        verbose_name = "Calendário"
        verbose_name_plural = "Calendários"
        ordering = ["descricao"]
        default_permissions = ()

    def __str__(self):
        return f"{self.filial} - {self.descricao}"


class CalendarioEvento(models.Model):
    class Motivo(models.IntegerChoices):
        DIA_NAO_PRODUTIVO = 1, "Dia Não Produtivo"
        FERIADO = 2, "Feriado"
        MANUTENCAO = 3, "Manutenção"

    calendario = models.ForeignKey(
        Calendario, on_delete=models.CASCADE, related_name="eventos", verbose_name="Calendário"
    )
    data = models.DateField(verbose_name="Data")
    motivo = models.SmallIntegerField(choices=Motivo.choices, verbose_name="Motivo")
    observacao = models.CharField(max_length=200, blank=True, default="", verbose_name="Observação")

    class Meta:
        db_table = "calendario_eventos"
        verbose_name = "Evento de Calendário"
        verbose_name_plural = "Eventos de Calendário"
        ordering = ["data"]
        default_permissions = ()

    def __str__(self):
        return f"{self.get_motivo_display()} em {self.data}"


# ========================
# Setores
# ========================
class Setor(models.Model):
    id = models.AutoField(primary_key=True)
    departamento = models.ForeignKey(
        "accounts.Departamento", on_delete=models.PROTECT, verbose_name="Departamento"
    )
    descricao = models.CharField(max_length=255, verbose_name="Descrição")

    class Meta:
        db_table = "setores"
        verbose_name = "Setor"
        verbose_name_plural = "Setores"
        ordering = ["descricao"]
        default_permissions = ()

    def __str__(self):
        return f"{self.departamento} - {self.descricao}"


# ========================
# Centros de Recursos
# ========================
class CentroRecurso(models.Model):
    id = models.AutoField(primary_key=True)
    setor = models.ForeignKey("accounts.Setor", on_delete=models.PROTECT, verbose_name="Setor")
    codigo = models.CharField(max_length=50, verbose_name="Código")  # varchar
    descricao = models.CharField(max_length=255, verbose_name="Descrição")  # varchar
    codigo_integrador = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Código Integrador",  # opcional varchar
    )

    class Meta:
        db_table = "centros_recursos"
        verbose_name = "Centro de Recurso"
        verbose_name_plural = "Centros de Recursos"
        ordering = ["descricao"]
        default_permissions = ()

    def __str__(self):
        return f"{self.setor} - {self.codigo}"


class ParametrosCentroRecurso(models.Model):
    CAMPOS = PARAMETROS_INTEGRACAO_CENTRO_RECURSO

    centro_recurso = models.OneToOneField(
        "accounts.CentroRecurso",
        on_delete=models.CASCADE,
        related_name="parametros_centro_recurso",
        db_column="centros_recursos_id",
        verbose_name="Centro de Recurso",
    )
    deposito_apontamento_erp = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Depósito de consulta apontamento ERP"
    )
    deposito_armazenamento_erp = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Depósito de armazenamento ERP"
    )
    deposito_armazenamento_wms = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Local de liberação WMS"
    )
    deposito_area_vermelha_erp = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Depósito área vermelha ERP"
    )
    deposito_area_vermelha_wms = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Local área vermelha WMS"
    )
    produto_refugo = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Produto refugo"
    )
    derivacao_refugo = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Derivação refugo"
    )
    cod_alchemy = models.IntegerField(null=True, blank=True, verbose_name="Cód. Alchemy")

    class Meta:
        db_table = "parametros_centros_recursos"
        verbose_name = "Parâmetros do Centro de Recurso"
        verbose_name_plural = "Parâmetros dos Centros de Recursos"
        default_permissions = ()

    def __str__(self):
        return f"Parâmetros - {self.centro_recurso}"


# ========================
# Recursos
# ========================
class Recurso(models.Model):
    class ModeloPrd(models.IntegerChoices):
        UNITARIO = 1, "Unitário"
        LOTE = 2, "Lote"
        BATELADA = 3, "Batelada"
        CONTINUO = 4, "Contínuo"
        SERVICO = 5, "Serviço"

    class OpersSimut(models.IntegerChoices):
        UNICA = 1, "Única"
        MULTIPLA = 2, "Múltipla"
        SIMULTANEA = 3, "Simultânea"

    class AltJust(models.IntegerChoices):
        BLOQUEADO = 1, "Bloqueado"
        APENAS_SEM_JUSTIFICATIVA = 2, "Apenas Sem Justificativa"
        LIBERADO = 3, "Liberado"
        ULTIMA_PARADA = 4, "Última Parada"

    class AltParadaProg(models.IntegerChoices):
        BLOQUEADO = 1, "Bloqueado"
        LIBERADO = 2, "Liberado"
        APENAS_REDUCAO = 3, "Apenas Redução"
        APENAS_ACRESCIMO = 4, "Apenas Acréscimo"

    class ModHe(models.IntegerChoices):
        AUTOMATICA = 1, "Automática"
        MANUAL = 2, "Manual"
        OPERACAO_ABERTA = 3, "Operação Aberta"

    codigo = models.CharField(max_length=50)
    descricao = models.CharField(max_length=200)
    centro_recurso = models.ForeignKey(
        "accounts.CentroRecurso", on_delete=models.PROTECT, related_name="recursos"
    )
    habilita_oee = models.BooleanField(default=False)
    ativo = models.BooleanField(default=True)
    ordenacao = models.IntegerField(null=True, blank=True, verbose_name="Ordenação Visual")
    ordenacao_sequenciamento = models.IntegerField(
        null=True, blank=True, verbose_name="Ordenação Sequenciamento"
    )

    modelo_prd = models.SmallIntegerField(choices=ModeloPrd.choices, null=True, blank=True)
    opers_simut = models.SmallIntegerField(choices=OpersSimut.choices, null=True, blank=True)
    permite_parada_manual = models.BooleanField(default=False, verbose_name="Permite Parada Manual")
    telemetria_encerra_parada_manual = models.BooleanField(
        default=False,
        verbose_name="Telemetria encerra parada manual",
    )

    tempo_parada_aut = models.DurationField(null=True, blank=True)
    tempo_minimo_parada = models.DurationField(
        default=timedelta(minutes=1),
        verbose_name="Tempo mínimo de parada",
    )

    metadis = models.FloatField(null=True, blank=True)
    metaper = models.FloatField(null=True, blank=True)
    metaqual = models.FloatField(null=True, blank=True)
    metaooee = models.FloatField(null=True, blank=True)

    view_id = models.IntegerField(null=True, blank=True, verbose_name="View")

    quant_pes = models.IntegerField(null=True, blank=True)
    aponta_parada = models.BooleanField(default=False, verbose_name="Aponta Parada")
    exibir_jus = models.BooleanField(default=False, verbose_name="Exibir Justificativas")

    alt_just = models.SmallIntegerField(choices=AltJust.choices, null=True, blank=True)
    inic_parada_prog = models.BooleanField(null=True, blank=True)
    fin_parada_prog = models.BooleanField(null=True, blank=True)
    alt_parada_prog = models.SmallIntegerField(choices=AltParadaProg.choices, null=True, blank=True)
    mod_he = models.SmallIntegerField(choices=ModHe.choices, null=True, blank=True)
    bobina = models.IntegerField(null=True, blank=True, editable=False, verbose_name="Bobina")

    class Meta:
        db_table = "recursos"
        ordering = ["ordenacao", "descricao"]
        default_permissions = ()

    def __str__(self):
        return f"{self.codigo} - {self.descricao}"

    def get_parametros_efetivos(self):
        filial = self.centro_recurso.setor.departamento.filial
        parametros_filial = getattr(filial, "parametros_filial", None)
        parametros_centro = getattr(self.centro_recurso, "parametros_centro_recurso", None)
        parametros_recurso = getattr(self, "parametros_recurso", None)

        parametros = (
            parametros_filial.as_dict() if parametros_filial else ParametrosFilial.defaults()
        )

        parametros["cod_alchemy"] = None

        if parametros_centro:
            for campo in ParametrosCentroRecurso.CAMPOS:
                valor = getattr(parametros_centro, campo)
                if valor not in (None, ""):
                    parametros[campo] = valor

        if parametros_recurso:
            for campo in ParametrosRecurso.CAMPOS:
                if not hasattr(parametros_recurso, campo):
                    continue
                valor = getattr(parametros_recurso, campo)
                if valor not in (None, ""):
                    parametros[campo] = valor

        parametros["tempo_sem_comunicacao_manual"] = int(parametros["tempo_sem_comunicacao_manual"])
        parametros["limite_apontamento_minimo"] = float(parametros["limite_apontamento_minimo"])
        parametros["limite_apontamento_maximo"] = float(parametros["limite_apontamento_maximo"])
        parametros["aponta_refugo"] = (
            parametros_recurso.aponta_refugo if parametros_recurso else True
        )
        return parametros


class ParametrosRecurso(models.Model):
    CAMPOS = [
        "tempo_sem_comunicacao_manual",
        "limite_apontamento_minimo",
        "limite_apontamento_maximo",
    ]

    recurso = models.OneToOneField(
        "accounts.Recurso",
        on_delete=models.CASCADE,
        related_name="parametros_recurso",
        verbose_name="Recurso",
    )
    tempo_sem_comunicacao_manual = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Tempo sem comunicação para apontar manualmente (segundos)",
    )
    limite_apontamento_minimo = models.FloatField(
        null=True, blank=True, verbose_name="Limite mínimo de apontamento"
    )
    limite_apontamento_maximo = models.FloatField(
        null=True, blank=True, verbose_name="Limite máximo de apontamento"
    )
    aponta_refugo = models.BooleanField(default=True, verbose_name="Aponta Refugo")

    class Meta:
        db_table = "parametros_recursos"
        verbose_name = "Parâmetros do Recurso"
        verbose_name_plural = "Parâmetros dos Recursos"
        default_permissions = ()

    def __str__(self):
        return f"Parâmetros - {self.recurso}"


class Tara(models.Model):
    tara = models.CharField(max_length=100, verbose_name="Tara")
    peso = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Peso (kg)")

    class Meta:
        db_table = "taras"
        verbose_name = "Tara"
        verbose_name_plural = "Taras"
        default_permissions = ()

    def __str__(self):
        return f"{self.tara} ({self.peso} kg)"


class RecursoTara(models.Model):
    recurso = models.ForeignKey("Recurso", on_delete=models.CASCADE, related_name="recurso_taras")
    tara = models.ForeignKey("Tara", on_delete=models.PROTECT, related_name="tara_recursos")

    class Meta:
        db_table = "recurso_taras"
        unique_together = ("recurso", "tara")
        verbose_name = "Relacionamento Recurso Tara"
        verbose_name_plural = "Relacionamentos Recurso Tara"
        default_permissions = ()

    def __str__(self):
        return f"{self.recurso} - {self.tara}"


class MotivoAbrangencia(models.Model):
    id = models.BigAutoField(primary_key=True)
    recurso = models.ForeignKey(
        "Recurso",
        db_column="id_recurso",
        on_delete=models.CASCADE,
        related_name="motivos_abrangencia",
        verbose_name="Recurso",
    )
    codemp = models.IntegerField(verbose_name="Código da Empresa")
    codgpm = models.IntegerField(verbose_name="Código do Grupo de Parada")
    codmtv = models.CharField(max_length=4, verbose_name="Código ERP do Motivo")

    class Meta:
        db_table = "motivos_abrangencia"
        verbose_name = "Motivo de Abrangência"
        verbose_name_plural = "Motivos de Abrangência"
        ordering = ["codemp", "codgpm", "codmtv"]
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(
                fields=["recurso", "codemp", "codgpm", "codmtv"],
                name="uq_mot_abr_rec_emp_gpm_mtv",
            ),
        ]

    def __str__(self):
        return f"{self.recurso} - {self.codemp}/{self.codgpm}/{self.codmtv}"


# ========================
# Turnos
# ========================
class TurnoRecurso(models.Model):
    class DiaSemana(models.IntegerChoices):
        SEGUNDA = 1, "Segunda"
        TERCA = 2, "Terça"
        QUARTA = 3, "Quarta"
        QUINTA = 4, "Quinta"
        SEXTA = 5, "Sexta"
        SABADO = 6, "Sábado"
        DOMINGO = 7, "Domingo"

    turnobase = models.ForeignKey("TurnoBase", on_delete=models.PROTECT)
    recurso = models.ForeignKey("Recurso", on_delete=models.PROTECT)
    dias = ArrayField(models.IntegerField(choices=DiaSemana.choices))
    hora_inicio = models.TimeField()
    hora_fim = models.TimeField()

    class Meta:
        db_table = "turnos_recursos"
        verbose_name = "Turno de Recurso"
        verbose_name_plural = "Turnos de Recursos"
        ordering = ["recurso", "hora_inicio"]
        default_permissions = ()

    def __str__(self):
        dias_str = ",".join(str(d) for d in self.dias)
        return f"{self.recurso} [{dias_str}] {self.hora_inicio}–{self.hora_fim}"


# ========================
# HE Planejadas
# ========================
class HoraExtraPlanejada(models.Model):
    class DiaSemana(models.IntegerChoices):
        SEGUNDA = 1, "Segunda"
        TERCA = 2, "Terça"
        QUARTA = 3, "Quarta"
        QUINTA = 4, "Quinta"
        SEXTA = 5, "Sexta"
        SABADO = 6, "Sábado"
        DOMINGO = 7, "Domingo"

    id = models.BigAutoField(primary_key=True)
    turnobase = models.ForeignKey("TurnoBase", on_delete=models.PROTECT, verbose_name="Turno Base")
    recurso = models.ForeignKey("Recurso", on_delete=models.PROTECT, verbose_name="Recurso")
    dias = ArrayField(
        models.IntegerField(choices=DiaSemana.choices),
        blank=True,
        null=True,
        verbose_name="Dias da Semana",
    )
    data_inicio = models.DateField(verbose_name="Data Início")
    data_fim = models.DateField(verbose_name="Data Fim")
    hora_inicio = models.TimeField(verbose_name="Hora Início")
    hora_fim = models.TimeField(verbose_name="Hora Fim")
    considera_feriado = models.BooleanField(default=False, verbose_name="Considera Feriado")

    class Meta:
        db_table = "horas_extras_planejadas"
        verbose_name = "Hora Extra Planejada"
        verbose_name_plural = "Horas Extras Planejadas"
        ordering = ["data_inicio", "hora_inicio"]
        default_permissions = ()

    def __str__(self):
        return f"HE {self.turnobase.descricao} - {self.recurso.descricao} ({self.data_inicio} a {self.data_fim})"


class OEEPlanejadoDiario(models.Model):
    recurso = models.ForeignKey("Recurso", on_delete=models.CASCADE)
    data = models.DateField()
    minutos_planejados = models.IntegerField()

    class Meta:
        db_table = 'public"."oee_planejado_diario'
        unique_together = ("recurso", "data")
        default_permissions = ()
        indexes = [
            models.Index(fields=["data"]),
        ]

    def __str__(self):
        return f"{self.recurso} - {self.data}"
