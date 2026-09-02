from django import forms
from django_select2.forms import Select2MultipleWidget

from accounts.models import CustomUser
from setores.manutencao.models import Chamado, Interacao_Chamado, Interacao_OS, OrdemServico

GRUPO_RESPONSAVEIS = "CHA E OS - Responsáveis"
GRUPO_OBSERVADORES = "CHA - Observadores"


class ChamadoForm(forms.ModelForm):
    categoria = forms.ChoiceField(
        choices=Chamado.Categoria.choices,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
        label="Categoria",
    )

    responsaveis = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.all().order_by("first_name"),
        required=False,
        widget=Select2MultipleWidget(
            attrs={"data-placeholder": "Selecione responsáveis...", "style": "width:100%;"}
        ),
    )
    observadores_id = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.all().order_by("first_name"),
        required=False,
        widget=Select2MultipleWidget(
            attrs={"data-placeholder": "Selecione observadores...", "style": "width:100%;"}
        ),
    )

    class Meta:
        model = Chamado
        fields = [
            "nome",
            "categoria",
            "prioridade",
            "status",
            "recurso",
            "sla_previsto",
            "sla_realizado",
        ]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "prioridade": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "status": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "recurso": forms.Select(
                attrs={"class": "form-select form-select-sm", "id": "id_recurso"}
            ),
        }


class InteracaoChamadoForm(forms.ModelForm):
    mensagem = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control form-control-sm",
                "rows": 3,
                "placeholder": "Escreva uma observação...",
            }
        ),
    )

    class Meta:
        model = Interacao_Chamado
        fields = ["mensagem"]


class OrdemServicoForm(forms.ModelForm):
    responsaveis = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.filter(groups__name=GRUPO_RESPONSAVEIS).order_by("first_name"),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        label="Responsáveis",
    )

    class Meta:
        model = OrdemServico
        fields = [
            "chamado",
            "descricao",
            "recurso",
            "inicio_prev",
            "final_prev",
            "inicio_real",
            "final_real",
        ]
        widgets = {
            "chamado": forms.Select(
                attrs={"class": "form-select form-select-sm", "style": "width:100%;"}
            ),
            "descricao": forms.Textarea(
                attrs={"class": "form-control form-control-sm text-uppercase", "rows": 3}
            ),
            "recurso": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "inicio_prev": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "border w-full p-1 rounded"}
            ),
            "final_prev": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "border w-full p-1 rounded"}
            ),
            "inicio_real": forms.DateTimeInput(
                attrs={"class": "form-control form-control-sm", "type": "datetime-local"}
            ),
            "final_real": forms.DateTimeInput(
                attrs={"class": "form-control form-control-sm", "type": "datetime-local"}
            ),
        }

    def __init__(self, *args, recurso_queryset=None, chamado_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if recurso_queryset is not None:
            self.fields["recurso"].queryset = recurso_queryset
        if chamado_queryset is not None:
            self.fields["chamado"].queryset = chamado_queryset.exclude(status="FECHADO").order_by(
                "-id"
            )
        else:
            self.fields["chamado"].queryset = Chamado.objects.exclude(status="FECHADO").order_by(
                "-id"
            )

    def clean_descricao(self):
        desc = (self.cleaned_data.get("descricao") or "").strip()
        if not desc:
            raise forms.ValidationError("A descrição da OS é obrigatória.")
        return desc.upper()

    def clean(self):
        cleaned_data = super().clean()
        inicio_prev = cleaned_data.get("inicio_prev")
        final_prev = cleaned_data.get("final_prev")

        if not inicio_prev or not final_prev:
            raise forms.ValidationError("As datas de início e fim previstas são obrigatórias.")

        if final_prev < inicio_prev:
            raise forms.ValidationError("A data final prevista não pode ser menor que a inicial.")

        return cleaned_data


class InteracaoOSForm(forms.ModelForm):
    class Meta:
        model = Interacao_OS
        fields = ["inicio", "fim", "descricao"]
        widgets = {
            "inicio": forms.DateTimeInput(
                attrs={"class": "form-control form-control-sm", "type": "datetime-local"}
            ),
            "fim": forms.DateTimeInput(
                attrs={"class": "form-control form-control-sm", "type": "datetime-local"}
            ),
            "descricao": forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
        }

    def clean(self):
        cleaned_data = super().clean()
        inicio = cleaned_data.get("inicio")
        fim = cleaned_data.get("fim")
        if not inicio and not fim:
            raise forms.ValidationError("Selecione uma data e hora para registrar a interação.")
        if inicio and fim:
            raise forms.ValidationError("Informe somente início ou fim para a interação.")
        return cleaned_data
