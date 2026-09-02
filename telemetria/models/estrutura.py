from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class FonteColetaHTTP(models.Model):
    # Filial que administra a fonte. Declarada também na fonte (e não só
    # derivada via Sensor → recurso) porque a listagem e a exclusão de fontes
    # filtram por filial diretamente — fonte sem sensor algum não teria filial
    # derivável e ficaria invisível/exposta a qualquer não-staff. Null/blank
    # porque registros existentes podem não ter filial derivável (staff vê,
    # não-staff não); PROTECT porque configuração de coleta não deve sumir
    # junto com a filial.
    filial = models.ForeignKey(
        "accounts.Filial",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="fontes_coleta_telemetria",
        verbose_name="Filial",
    )
    url = models.URLField(max_length=500, unique=True, verbose_name="URL HTTP")
    coleta_ativa = models.BooleanField(default=True, verbose_name="Coleta ativa")
    timeout_segundos = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        verbose_name="Timeout (segundos)",
    )
    pausa_sucesso_segundos = models.PositiveIntegerField(
        default=10,
        verbose_name="Pausa após sucesso (segundos)",
    )
    backoff_erro_segundos = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        verbose_name="Espera após erro (segundos)",
    )
    log = models.TextField(blank=True, verbose_name="Log da última coleta")
    ultima_coleta_em = models.DateTimeField(
        null=True, blank=True, verbose_name="Data/hora da última coleta"
    )

    class Meta:
        db_table = 'telemetria"."fontes_coleta_http'
        verbose_name = "Fonte HTTP de telemetria"
        verbose_name_plural = "Fontes HTTP de telemetria"
        default_permissions = ()

    def __str__(self):
        return self.url


class Sensor(models.Model):
    class TipoValor(models.TextChoices):
        DECIMAL = "decimal", "Decimal"
        INTEIRO = "inteiro", "Inteiro"
        BOOLEANO = "booleano", "Booleano"
        TEXTO = "texto", "Texto"

    fonte = models.ForeignKey(
        "telemetria.FonteColetaHTTP",
        on_delete=models.PROTECT,
        related_name="sensores",
        verbose_name="Fonte de coleta",
    )
    # Filial que administra o sensor: é o critério de escopo das telas de
    # sensores (não-staff só consulta/altera a própria filial). Mesma política
    # de null/blank e PROTECT da fonte de coleta.
    filial = models.ForeignKey(
        "accounts.Filial",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sensores_telemetria",
        verbose_name="Filial",
    )
    chave_origem = models.CharField(max_length=200, verbose_name="Chave na resposta JSON")
    nome = models.CharField(max_length=200, verbose_name="Nome amigável")
    tipo_valor = models.CharField(
        max_length=10, choices=TipoValor.choices, verbose_name="Tipo do valor"
    )
    unidade = models.CharField(max_length=30, blank=True, verbose_name="Unidade")
    ativo = models.BooleanField(default=True)

    class Meta:
        db_table = 'telemetria"."sensores'
        verbose_name = "Sensor"
        verbose_name_plural = "Sensores"
        default_permissions = ()
        ordering = ["chave_origem"]
        constraints = [
            models.UniqueConstraint(
                fields=["fonte", "chave_origem"], name="uq_tlm_sensor_fonte_chave"
            )
        ]

    def __str__(self):
        return f"{self.chave_origem} - {self.nome}"


class SensorRecurso(models.Model):
    class TipoTolerancia(models.TextChoices):
        # Catálogo do tipo de tolerância aplicado à variação monitorada.
        ABSOLUTA = "absoluta", "Absoluta"
        PERCENTUAL = "percentual", "Percentual"

    recurso = models.ForeignKey(
        "accounts.Recurso",
        on_delete=models.CASCADE,
        related_name="sensores_telemetria",
        verbose_name="Recurso",
    )
    sensor = models.ForeignKey(
        "telemetria.Sensor",
        on_delete=models.PROTECT,
        related_name="recursos",
        verbose_name="Sensor",
    )
    monitorar_variacao = models.BooleanField(default=False, verbose_name="Monitorar variação")
    tipo_tolerancia = models.CharField(
        max_length=10,
        choices=TipoTolerancia.choices,
        default=TipoTolerancia.ABSOLUTA,
        verbose_name="Tipo de tolerância",
    )
    tolerancia = models.FloatField(default=0.0, verbose_name="Variação mínima")

    class Meta:
        db_table = 'telemetria"."sensores_recursos'
        verbose_name = "Sensor do recurso"
        verbose_name_plural = "Sensores dos recursos"
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=["recurso", "sensor"], name="uq_tlm_sensor_recurso"),
        ]
        ordering = ["recurso", "sensor__chave_origem"]

    def __str__(self):
        return f"{self.recurso}: {self.sensor.chave_origem}"

    def clean(self):
        super().clean()
        if self.tolerancia < 0:
            raise ValidationError({"tolerancia": "A tolerância não pode ser negativa."})
        if self.recurso_id and self.sensor_id:
            existentes = SensorRecurso.objects.filter(recurso_id=self.recurso_id).exclude(
                pk=self.pk
            )
            if existentes.exclude(sensor__fonte_id=self.sensor.fonte_id).exists():
                raise ValidationError(
                    {"sensor": "Todos os sensores do recurso devem usar a mesma fonte."}
                )


class LeituraTelemetria(models.Model):
    pk = models.CompositePrimaryKey("recurso", "coletado_em")
    recurso = models.ForeignKey(
        "accounts.Recurso",
        on_delete=models.PROTECT,
        related_name="leituras_telemetria",
        verbose_name="Recurso",
    )
    coletado_em = models.DateTimeField(default=timezone.now, verbose_name="Data/hora da coleta")
    valores = models.JSONField(default=dict, verbose_name="Valores interpretados")

    class Meta:
        db_table = 'telemetria"."leituras'
        verbose_name = "Leitura de telemetria"
        verbose_name_plural = "Leituras de telemetria"
        default_permissions = ()
        ordering = ["-coletado_em"]
        indexes = [
            models.Index(fields=["recurso", "-coletado_em"], name="idx_tlm_leitura_rec_data")
        ]

    def __str__(self):
        return f"{self.recurso} - {self.coletado_em:%d/%m/%Y %H:%M:%S}"

    def clean(self):
        super().clean()
        if not isinstance(self.valores, dict):
            raise ValidationError({"valores": "Os valores interpretados devem ser um objeto JSON."})

        if not self.recurso_id or not self.valores:
            return

        sensores = {
            sensor.chave_origem: sensor
            for sensor in Sensor.objects.filter(recursos__recurso_id=self.recurso_id)
        }
        erros = []
        for chave, valor in self.valores.items():
            sensor = sensores.get(chave)
            if sensor is None:
                erros.append(f"{chave}: sensor não cadastrado para este recurso.")
                continue
            if not self._valor_compativel(sensor.tipo_valor, valor):
                erros.append(f"{chave}: valor incompatível com o tipo {sensor.tipo_valor}.")

        if erros:
            raise ValidationError({"valores": erros})

    @staticmethod
    def _valor_compativel(tipo_valor, valor):
        if tipo_valor == Sensor.TipoValor.DECIMAL:
            return isinstance(valor, (int, float, Decimal)) and not isinstance(valor, bool)
        if tipo_valor == Sensor.TipoValor.INTEIRO:
            return isinstance(valor, int) and not isinstance(valor, bool)
        if tipo_valor == Sensor.TipoValor.BOOLEANO:
            return isinstance(valor, bool)
        return isinstance(valor, str)
