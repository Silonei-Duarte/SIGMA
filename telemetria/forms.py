from decimal import Decimal

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from producao.models import RegraParadaRecurso

from .models import FonteColetaHTTP, Sensor, SensorRecurso
from .validacao_http import validar_url_coleta


class SensorForm(forms.ModelForm):
    class Meta:
        model = Sensor
        fields = (
            "fonte",
            "chave_origem",
            "nome",
            "tipo_valor",
            "unidade",
            "ativo",
        )

    def clean_chave_origem(self):
        chave = self.cleaned_data["chave_origem"].strip()
        if not chave:
            raise ValidationError("Informe uma chave JSON válida.")
        fonte = self.cleaned_data.get("fonte")
        existentes = Sensor.objects.exclude(pk=self.instance.pk).filter(
            fonte=fonte, chave_origem=chave
        )
        if existentes.exists():
            raise ValidationError("Esta chave JSON já está cadastrada nesta fonte.")
        return chave


class FonteColetaHTTPForm(forms.ModelForm):
    class Meta:
        model = FonteColetaHTTP
        fields = (
            "url",
            "coleta_ativa",
            "timeout_segundos",
            "pausa_sucesso_segundos",
            "backoff_erro_segundos",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial.setdefault(
                "pausa_sucesso_segundos", settings.TELEMETRIA_PAUSA_SUCESSO_SEGUNDOS
            )
            self.initial.setdefault(
                "backoff_erro_segundos", settings.TELEMETRIA_BACKOFF_ERRO_SEGUNDOS
            )

    def clean_url(self):
        return validar_url_coleta(self.cleaned_data["url"])

    def clean_timeout_segundos(self):
        timeout = self.cleaned_data["timeout_segundos"]
        if timeout > settings.TELEMETRIA_TIMEOUT_MAX_SEGUNDOS:
            raise ValidationError(
                f"O timeout máximo é de {settings.TELEMETRIA_TIMEOUT_MAX_SEGUNDOS} segundos."
            )
        return timeout

    def clean_pausa_sucesso_segundos(self):
        return _validar_pausa(self.cleaned_data["pausa_sucesso_segundos"])

    def clean_backoff_erro_segundos(self):
        return _validar_pausa(self.cleaned_data["backoff_erro_segundos"])


def _validar_pausa(valor):
    if valor > settings.TELEMETRIA_PAUSA_MAX_SEGUNDOS:
        raise ValidationError(
            f"A pausa máxima é de {settings.TELEMETRIA_PAUSA_MAX_SEGUNDOS} segundos."
        )
    return valor


class SensorRecursoForm(forms.ModelForm):
    class Meta:
        model = SensorRecurso
        # "Monitorar variação" só existe na tabela de vínculos já criados
        # (SensorRecursoAtualizacaoForm); todo vínculo novo nasce com o
        # default do model (False) e o usuário liga o monitoramento depois.
        fields = ("sensor",)

    def __init__(self, *args, recurso=None, sensores_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.recurso = recurso
        if recurso:
            # sensores_queryset vem da view já delimitado (filial + ativo);
            # None preserva o comportamento original (qualquer sensor ativo).
            sensores = (sensores_queryset or Sensor.objects.filter(ativo=True)).exclude(
                recursos__recurso=recurso
            )
            fonte_id = (
                SensorRecurso.objects.filter(recurso=recurso)
                .values_list("sensor__fonte_id", flat=True)
                .first()
            )
            self.fields["sensor"].queryset = (
                sensores.filter(fonte_id=fonte_id) if fonte_id else sensores
            ).order_by("chave_origem")

    def clean(self):
        cleaned = super().clean()
        if self.recurso:
            self.instance.recurso = self.recurso
        return cleaned


class SensorRecursoAtualizacaoForm(forms.Form):
    monitorar_variacao = forms.BooleanField(required=False)
    tipo_tolerancia = forms.ChoiceField(
        choices=SensorRecurso.TipoTolerancia.choices, required=False
    )
    tolerancia = forms.DecimalField(min_value=Decimal("0"), required=False)

    def __init__(self, *args, vinculo_id, **kwargs):
        self.vinculo_id = vinculo_id
        super().__init__(*args, **kwargs)

    def add_prefix(self, field_name):
        return f"{field_name}_{self.vinculo_id}"

    def clean(self):
        cleaned = super().clean()
        cleaned["tipo_tolerancia"] = cleaned.get("tipo_tolerancia") or "absoluta"
        cleaned["tolerancia"] = cleaned.get("tolerancia") or Decimal("0")
        return cleaned


class RegraParadaRecursoForm(forms.ModelForm):
    regra = forms.JSONField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = RegraParadaRecurso
        fields = ("ativa", "regra")

    def __init__(self, *args, recurso=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.recurso = recurso
        if recurso:
            self.instance.recurso = recurso

    def clean_regra(self):
        regra = self.cleaned_data.get("regra")
        return {} if regra is None else regra
