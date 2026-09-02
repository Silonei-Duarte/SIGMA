from datetime import timedelta
from typing import cast
from urllib.parse import urlsplit

from django import forms
from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from SIGMA.autorizacao import APPS_PERMISSOES_GESTAO_ACESSOS

from .models import (
    Calendario,
    CalendarioEvento,
    CentroRecurso,
    CustomUser,
    Departamento,
    Empresa,
    Filial,
    HoraExtraPlanejada,
    ParametrosCentroRecurso,
    ParametrosFilial,
    ParametrosRecurso,
    Recurso,
    Setor,
    Tara,
    TurnoBase,
    TurnoRecurso,
)
from .services.configuracoes import ChaveConhecida


# ========================
# Usuários
# ========================
class CustomUserForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Senha", widget=forms.PasswordInput(attrs={"class": "form-control"}), required=False
    )
    password2 = forms.CharField(
        label="Confirmar senha",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        required=False,
    )
    is_staff = forms.BooleanField(required=False, label="Administrador")
    is_active = forms.BooleanField(required=False, label="Ativo")

    user_permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.filter(
            content_type__app_label__in=APPS_PERMISSOES_GESTAO_ACESSOS
        ).order_by("name"),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label="Permissões específicas",
    )

    class Meta:
        model = CustomUser
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "is_staff",
            "is_active",
            "filial",
            "idintegracao",
            "idoperador",
            "paginicial",
            "user_permissions",
        )
        labels = {
            "paginicial": "Página inicial",
        }

    def __init__(self, *args, pode_definir_staff: bool = False, **kwargs):
        super().__init__(*args, **kwargs)

        # Staff é escalada apenas por superusuário: sem o poder, o campo sai do
        # form e um valor forjado no POST é ignorado (o banco mantém o original).
        if not pode_definir_staff:
            del self.fields["is_staff"]

        # bloqueia edição do usuário após criado
        if self.instance and self.instance.pk:
            self.fields["username"].disabled = True

        for name, field in self.fields.items():
            if field.widget.__class__.__name__ not in ("CheckboxInput", "CheckboxSelectMultiple"):
                field.widget.attrs.update({"class": "form-control"})
            else:
                field.widget.attrs.update({"class": "form-check-input"})
            field.widget.attrs.update({"id": f"id_{name}"})

        # nomes simples nas permissões
        campo_permissoes = cast("forms.ModelMultipleChoiceField", self.fields["user_permissions"])
        permissoes_base = Permission.objects.filter(
            content_type__app_label__in=APPS_PERMISSOES_GESTAO_ACESSOS
        )
        campo_permissoes.choices = [(p.id, p.name) for p in permissoes_base]

        def get_app_name(app_label):
            mapping = {
                "accounts": "Geral",
                "producao": "Produção",
                "manutencao": "Manutenção",
                "qualidade": "Qualidade",
                "pcp": "PCP",
                "logistica": "Logística",
                "suprimentos": "Suprimentos",
            }
            return mapping.get(app_label, app_label.capitalize())

        def build_perms_by_app(queryset, exclude_ids=None):
            perms = {}
            # Ordenação alfabética insensível a maiúsculas
            sorted_qs = sorted(queryset, key=lambda x: x.name.lower())
            for p in sorted_qs:
                if exclude_ids and p.id in exclude_ids:
                    continue
                app_label = p.content_type.app_label
                app_name = get_app_name(app_label)
                if app_name not in perms:
                    perms[app_name] = []
                perms[app_name].append(p)

            # Garantir a ordem: Geral, Produção, Manutenção, Qualidade, PCP
            ordered_keys = [
                "Geral",
                "Produção",
                "Manutenção",
                "Qualidade",
                "PCP",
                "Logística",
                "Suprimentos",
            ]
            # Adicionar outros apps se houver (caso futuro)
            for k in perms.keys():
                if k not in ordered_keys:
                    ordered_keys.append(k)

            return [(k, perms[k]) for k in ordered_keys if k in perms]

        if self.instance and self.instance.pk:
            grupos_ids = self.instance.groups.values_list("id", flat=True)

            herdadas_ids = set(
                Permission.objects.filter(
                    group__id__in=grupos_ids,
                    content_type__app_label__in=APPS_PERMISSOES_GESTAO_ACESSOS,
                ).values_list("id", flat=True)
            )

            diretas_ids = set(
                self.instance.user_permissions.filter(
                    content_type__app_label__in=APPS_PERMISSOES_GESTAO_ACESSOS
                ).values_list("id", flat=True)
            )

            # apenas diretas nos checkboxes
            campo_permissoes.queryset = Permission.objects.filter(
                content_type__app_label__in=APPS_PERMISSOES_GESTAO_ACESSOS
            ).exclude(id__in=herdadas_ids)

            # marca só as diretas
            self.initial["user_permissions"] = Permission.objects.filter(id__in=diretas_ids)

            # herdadas só em texto, fora da lista de checkboxes
            self.herdadas_display = [p.name for p in Permission.objects.filter(id__in=herdadas_ids)]

            # remove herdadas também da lista inicial se acaso duplicar
            campo_permissoes.choices = [
                (p.id, p.name) for p in campo_permissoes.queryset if p.id not in herdadas_ids
            ]

            # Atualiza a lista agrupada removendo as herdadas
            self.perms_by_app = build_perms_by_app(campo_permissoes.queryset, herdadas_ids)
        else:
            self.herdadas_display = []
            # Garante que perms_by_app existe mesmo para novo usuário
            self.perms_by_app = build_perms_by_app(campo_permissoes.queryset)

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")

        # Novo usuário: senha obrigatória
        if not self.instance.pk:
            if not p1 or not p2:
                raise forms.ValidationError("É necessário definir uma senha para o novo usuário.")
            if p1 != p2:
                raise forms.ValidationError("As senhas não coincidem.")
            validate_password(p1, self.instance)
        # Edição: se preencher, deve coincidir
        elif p1 or p2:
            if p1 != p2:
                raise forms.ValidationError("As senhas não coincidem.")
            validate_password(p1, self.instance)

        return cleaned

    def clean_paginicial(self):
        pagina = (self.cleaned_data.get("paginicial") or "").strip()
        if not pagina:
            return ""
        parsed = urlsplit(pagina)
        if (
            parsed.scheme
            or parsed.netloc
            or not pagina.startswith("/")
            or pagina.startswith("//")
            or "\\" in pagina
        ):
            raise forms.ValidationError(
                "Informe apenas uma rota interna, por exemplo: /producao/apontamentos/?empresa=1&centro=26&recurso=21"
            )
        return pagina

    def save(self, commit=True):
        user = super().save(commit=False)
        p1 = self.cleaned_data.get("password1")
        if p1:
            user.set_password(p1)
        if commit:
            user.save()
            if "user_permissions" in self.cleaned_data:
                user.user_permissions.set(self.cleaned_data["user_permissions"])

            # remove duplicadas (permissões já herdadas por grupos)
            grupos_ids = user.groups.values_list("id", flat=True)
            herdadas_ids = Permission.objects.filter(group__id__in=grupos_ids).values_list(
                "id", flat=True
            )
            user.user_permissions.remove(*herdadas_ids)

        return user


# ========================
# Empresas
# ========================
class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = ["codemp", "nome", "fantasia", "loteatual", "ativa"]
        widgets = {
            "codemp": forms.NumberInput(attrs={"class": "form-control"}),
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "fantasia": forms.TextInput(attrs={"class": "form-control"}),
            "loteatual": forms.TextInput(attrs={"class": "form-control"}),
            "ativa": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["codemp"].disabled = True
            # O próximo lote é reservado e incrementado pelos fluxos de apontamento.
            # Campo desabilitado também faz o Django desconsiderar valores enviados no POST.
            self.fields["loteatual"].disabled = True

    def clean_loteatual(self):
        lote = str(self.cleaned_data.get("loteatual") or "").strip()
        if not lote.isdigit():
            raise forms.ValidationError("Informe somente números no lote atual.")
        return lote


# ========================
# Filiais
# ========================
class FilialForm(forms.ModelForm):
    empresa = forms.ModelChoiceField(
        queryset=Empresa.objects.filter(ativa=True).order_by("nome"),
        empty_label="Selecione uma empresa",
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Empresa",
    )

    class Meta:
        model = Filial
        fields = ["empresa", "codfil", "nome", "fantasia", "cnpj", "ativa"]
        widgets = {
            "codfil": forms.NumberInput(attrs={"class": "form-control"}),
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "fantasia": forms.TextInput(attrs={"class": "form-control"}),
            "cnpj": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "00.000.000/0000-00"}
            ),
            "ativa": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["empresa"].disabled = True
            self.fields["codfil"].disabled = True

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not self.instance.pk:
            if self.cleaned_data["empresa"]:
                instance.codemp = self.cleaned_data["empresa"].codemp
        if commit:
            instance.save()
        return instance


class ParametroApontamentoMixin:
    recurso_fields = [
        "tempo_sem_comunicacao_manual",
        "limite_apontamento_minimo",
        "limite_apontamento_maximo",
    ]
    integracao_fields = [
        "deposito_apontamento_erp",
        "deposito_armazenamento_erp",
        "deposito_armazenamento_wms",
        "deposito_area_vermelha_erp",
        "deposito_area_vermelha_wms",
        "produto_refugo",
        "derivacao_refugo",
    ]
    parametro_fields = recurso_fields + integracao_fields

    parametro_widgets = {
        "tempo_sem_comunicacao_manual": forms.NumberInput(
            attrs={"class": "form-control", "min": "1"}
        ),
        "limite_apontamento_minimo": forms.NumberInput(
            attrs={"class": "form-control", "step": "0.01"}
        ),
        "limite_apontamento_maximo": forms.NumberInput(
            attrs={"class": "form-control", "step": "0.01"}
        ),
        "deposito_apontamento_erp": forms.TextInput(attrs={"class": "form-control"}),
        "deposito_armazenamento_erp": forms.TextInput(attrs={"class": "form-control"}),
        "deposito_armazenamento_wms": forms.TextInput(attrs={"class": "form-control"}),
        "deposito_area_vermelha_erp": forms.TextInput(attrs={"class": "form-control"}),
        "deposito_area_vermelha_wms": forms.TextInput(attrs={"class": "form-control"}),
        "produto_refugo": forms.TextInput(attrs={"class": "form-control"}),
        "derivacao_refugo": forms.TextInput(attrs={"class": "form-control"}),
    }

    parametro_labels = {
        "tempo_sem_comunicacao_manual": "Tempo para liberar apontamento manual (seg.)",
        "limite_apontamento_minimo": "Limite mínimo de apontamento",
        "limite_apontamento_maximo": "Limite máximo de apontamento",
        "deposito_apontamento_erp": "Depósito de consulta apontamento ERP",
        "deposito_armazenamento_erp": "Depósito de liberação ERP",
        "deposito_armazenamento_wms": "Local de liberação WMS",
        "deposito_area_vermelha_erp": "Depósito área vermelha ERP",
        "deposito_area_vermelha_wms": "Local área vermelha WMS",
        "produto_refugo": "Produto refugo",
        "derivacao_refugo": "Derivação refugo",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "derivacao_refugo" in self.fields:
            self.fields["derivacao_refugo"].strip = False

    def clean(self):
        cleaned = super().clean()
        minimo = cleaned.get("limite_apontamento_minimo")
        maximo = cleaned.get("limite_apontamento_maximo")

        if minimo is not None and maximo is not None and minimo > maximo:
            self.add_error(
                "limite_apontamento_maximo", "O limite máximo deve ser maior ou igual ao mínimo."
            )

        return cleaned


class ParametrosFilialForm(ParametroApontamentoMixin, forms.ModelForm):
    class Meta:
        model = ParametrosFilial
        fields = ParametroApontamentoMixin.parametro_fields + [
            "codtns",
            "codtns_area_vermelha",
            "origens_area_vermelha",
            "transacoes_saida_consumo_producao",
            "transacoes_entrada_producao_consumo",
        ]
        widgets = {
            **ParametroApontamentoMixin.parametro_widgets,
            "codtns": forms.TextInput(attrs={"class": "form-control"}),
            "codtns_area_vermelha": forms.TextInput(attrs={"class": "form-control"}),
            "origens_area_vermelha": forms.TextInput(attrs={"class": "form-control"}),
            "transacoes_saida_consumo_producao": forms.TextInput(attrs={"class": "form-control"}),
            "transacoes_entrada_producao_consumo": forms.TextInput(attrs={"class": "form-control"}),
        }
        labels = {
            **ParametroApontamentoMixin.parametro_labels,
            "codtns": "Transação de ERP Saída por Transferência Interna",
            "codtns_area_vermelha": "Transação do ERP Saída Área Vermelha",
            "origens_area_vermelha": "Origens área vermelha",
            "transacoes_saida_consumo_producao": "Transações de saída para consumo na produção",
            "transacoes_entrada_producao_consumo": "Transações de entrada por Produção",
        }


# ========================
# Departamentos
# ========================
class DepartamentoForm(forms.ModelForm):
    filial = forms.ModelChoiceField(
        queryset=Filial.objects.filter(ativa=True).order_by("nome"),
        empty_label="Selecione uma filial",
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Filial",
    )

    class Meta:
        model = Departamento
        fields = ["filial", "descricao"]
        widgets = {
            "descricao": forms.TextInput(attrs={"class": "form-control"}),
        }
        labels = {
            "descricao": "Descrição",
        }


# ========================
# Turno Base
# ========================
class TurnoBaseForm(forms.ModelForm):
    calendario = forms.ModelChoiceField(
        queryset=Calendario.objects.order_by("descricao"),
        empty_label="Selecione um calendário",
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Calendário",
    )

    class Meta:
        model = TurnoBase
        fields = ["codigo", "descricao", "ordenacao", "calendario"]
        widgets = {
            "codigo": forms.TextInput(
                attrs={"class": "form-control", "style": "text-transform: uppercase;"}
            ),
            "descricao": forms.TextInput(
                attrs={"class": "form-control", "style": "text-transform: capitalize;"}
            ),
            "ordenacao": forms.NumberInput(attrs={"class": "form-control"}),
        }

    def clean_codigo(self):
        codigo = self.cleaned_data.get("codigo")
        return codigo.upper() if codigo else codigo

    def clean_descricao(self):
        descricao = self.cleaned_data.get("descricao")
        return descricao.title() if descricao else descricao


# ========================
# Calendário
# ========================
class CalendarioForm(forms.ModelForm):
    filial = forms.ModelChoiceField(
        queryset=Filial.objects.filter(ativa=True).order_by("nome"),
        empty_label="Selecione uma filial",
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Filial",
    )

    class Meta:
        model = Calendario
        fields = ["filial", "descricao"]
        widgets = {
            "descricao": forms.TextInput(attrs={"class": "form-control"}),
        }
        labels = {
            "descricao": "Descrição",
            "filial": "Filial",
        }


class CalendarioEventoForm(forms.ModelForm):
    class Meta:
        model = CalendarioEvento
        fields = ["motivo"]  # só motivo
        widgets = {
            "motivo": forms.Select(attrs={"class": "form-control"}),
        }
        labels = {"motivo": "Motivo"}


# ========================
# Setores
# ========================
class SetorForm(forms.ModelForm):
    departamento = forms.ModelChoiceField(
        queryset=Departamento.objects.order_by("descricao"),
        empty_label="Selecione um departamento",
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Departamento",
    )

    class Meta:
        model = Setor
        fields = ["departamento", "descricao"]
        widgets = {
            "descricao": forms.TextInput(attrs={"class": "form-control"}),
        }
        labels = {
            "descricao": "Descrição",
        }


# ========================
# Centros de Recursos
# ========================
class CentroRecursoForm(forms.ModelForm):
    setor = forms.ModelChoiceField(
        queryset=Setor.objects.order_by("descricao"),
        empty_label="Selecione um setor",
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Setor",
    )

    class Meta:
        model = CentroRecurso
        fields = ["setor", "codigo", "descricao", "codigo_integrador"]
        widgets = {
            "codigo": forms.TextInput(attrs={"class": "form-control"}),
            "descricao": forms.TextInput(attrs={"class": "form-control"}),
            "codigo_integrador": forms.TextInput(attrs={"class": "form-control"}),
        }
        labels = {
            "setor": "Setor",
            "codigo": "Código",
            "descricao": "Descrição",
            "codigo_integrador": "Código Integrador",
        }


class ParametrosCentroRecursoForm(ParametroApontamentoMixin, forms.ModelForm):
    class Meta:
        model = ParametrosCentroRecurso
        fields = ParametroApontamentoMixin.integracao_fields + ["cod_alchemy"]
        widgets = {
            **{
                campo: ParametroApontamentoMixin.parametro_widgets[campo]
                for campo in ParametroApontamentoMixin.integracao_fields
            },
            "cod_alchemy": forms.NumberInput(attrs={"class": "form-control"}),
        }
        labels = {
            **{
                campo: ParametroApontamentoMixin.parametro_labels[campo]
                for campo in ParametroApontamentoMixin.integracao_fields
            },
            "cod_alchemy": "Cód. Alchemy",
        }


# ========================
#  Recursos
# ========================
class ParametrosRecursoForm(ParametroApontamentoMixin, forms.ModelForm):
    class Meta:
        model = ParametrosRecurso
        fields = ParametroApontamentoMixin.recurso_fields + ["aponta_refugo"]
        widgets = {
            **{
                campo: ParametroApontamentoMixin.parametro_widgets[campo]
                for campo in ParametroApontamentoMixin.recurso_fields
            },
            "aponta_refugo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            **{
                campo: ParametroApontamentoMixin.parametro_labels[campo]
                for campo in ParametroApontamentoMixin.recurso_fields
            },
            "aponta_refugo": "Aponta Refugo",
        }


class RecursoForm(forms.ModelForm):
    centro_recurso = forms.ModelChoiceField(
        queryset=CentroRecurso.objects.order_by("descricao"),
        empty_label="Selecione um centro de recurso",
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Centro de Recurso",
    )
    view_id = forms.TypedChoiceField(
        choices=(
            (0, "0: Tela padrão"),
            (1, "1: Apontamento Lote MP"),
            (2, "2: Apontamento Componentes"),
            (3, "3: Apontamento Multi-OP"),
        ),
        coerce=int,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
        label="View",
    )

    class Meta:
        model = Recurso
        fields = [
            "centro_recurso",
            "codigo",
            "descricao",
            "habilita_oee",
            "ativo",
            "ordenacao",
            "ordenacao_sequenciamento",
            "modelo_prd",
            "opers_simut",
            "permite_parada_manual",
            "telemetria_encerra_parada_manual",
            "tempo_parada_aut",
            "tempo_minimo_parada",
            "metadis",
            "metaper",
            "metaqual",
            "metaooee",
            "view_id",
            "quant_pes",
            "aponta_parada",
            "exibir_jus",
            "alt_just",
            "inic_parada_prog",
            "fin_parada_prog",
            "alt_parada_prog",
            "mod_he",
        ]
        widgets = {
            "codigo": forms.TextInput(attrs={"class": "form-control"}),
            "descricao": forms.TextInput(attrs={"class": "form-control"}),
            "habilita_oee": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "ordenacao": forms.NumberInput(attrs={"class": "form-control"}),
            "ordenacao_sequenciamento": forms.NumberInput(attrs={"class": "form-control"}),
            "modelo_prd": forms.Select(attrs={"class": "form-control"}),
            "opers_simut": forms.Select(attrs={"class": "form-control"}),
            "permite_parada_manual": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "telemetria_encerra_parada_manual": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "tempo_parada_aut": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "hh:mm:ss"}
            ),
            "tempo_minimo_parada": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "hh:mm:ss"}
            ),
            "metadis": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "metaper": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "metaqual": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "metaooee": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "quant_pes": forms.NumberInput(attrs={"class": "form-control"}),
            "aponta_parada": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "exibir_jus": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "alt_just": forms.Select(attrs={"class": "form-control"}),
            "inic_parada_prog": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "fin_parada_prog": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "alt_parada_prog": forms.Select(attrs={"class": "form-control"}),
            "mod_he": forms.Select(attrs={"class": "form-control"}),
        }
        labels = {
            "centro_recurso": "Centro de Recurso",
            "codigo": "Código",
            "descricao": "Descrição",
            "habilita_oee": "Habilita OEE",
            "ativo": "Ativo",
            "ordenacao": "Ordenação Visual",
            "ordenacao_sequenciamento": "Ordenação Sequenciamento",
            "modelo_prd": "Modelo de Produção",
            "opers_simut": "Operações Simultâneas",
            "permite_parada_manual": "Permite Parada Manual",
            "telemetria_encerra_parada_manual": "Telemetria encerra parada manual",
            "tempo_parada_aut": "Tempo Parada Automática",
            "tempo_minimo_parada": "Tempo mínimo de parada",
            "metadis": "Meta Disponibilidade",
            "metaper": "Meta Performance",
            "metaqual": "Meta Qualidade",
            "metaooee": "Meta OEE",
            "view_id": "View",
            "quant_pes": "Quantidade de Operadores",
            "aponta_parada": "Aponta Parada",
            "exibir_jus": "Exibir Justificativas",
            "alt_just": "Alteração de Justificativas",
            "inic_parada_prog": "Operador Inicia Parada Programada",
            "fin_parada_prog": "Operador Finaliza Parada Programada",
            "alt_parada_prog": "Operador Altera Parada Programada",
            "mod_he": "Modo Geração HE",
        }
        help_texts = {
            "tempo_parada_aut": (
                "Tempo mínimo com o sinal indicando parada antes de abrir a parada automática."
            ),
            "tempo_minimo_parada": (
                "Duração mínima antes de permitir encerrar uma parada manual ou por sinal."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["tempo_parada_aut"].initial = timedelta(seconds=1)
        else:
            if self.instance.descricao.strip().lower() == "geral":
                # bloqueia edição de nome e centro no formulário
                self.fields["descricao"].disabled = True
                self.fields["centro_recurso"].disabled = True

    def clean(self):
        cleaned = super().clean()

        habilita = cleaned.get("habilita_oee")

        campos_oee = [
            "modelo_prd",
            "opers_simut",
            "permite_parada_manual",
            "telemetria_encerra_parada_manual",
            "tempo_parada_aut",
            "tempo_minimo_parada",
            "metadis",
            "metaper",
            "metaqual",
            "metaooee",
            "view_id",
            "quant_pes",
            "aponta_parada",
            "exibir_jus",
            "alt_just",
            "inic_parada_prog",
            "fin_parada_prog",
            "alt_parada_prog",
            "mod_he",
        ]

        if habilita:
            for campo in campos_oee:
                valor = cleaned.get(campo)
                if valor in [None, ""]:
                    self.add_error(campo, "Obrigatório quando OEE está habilitado.")

        tempo_parada_aut = cleaned.get("tempo_parada_aut")
        if tempo_parada_aut is not None:
            tempo_parada_aut -= timedelta(microseconds=tempo_parada_aut.microseconds)
            if tempo_parada_aut == timedelta():
                tempo_parada_aut = timedelta(seconds=1)
            cleaned["tempo_parada_aut"] = tempo_parada_aut
        if tempo_parada_aut is not None and tempo_parada_aut < timedelta():
            self.add_error("tempo_parada_aut", "O tempo não pode ser negativo.")

        tempo_minimo_parada = cleaned.get("tempo_minimo_parada")
        if tempo_minimo_parada is not None:
            tempo_minimo_parada -= timedelta(microseconds=tempo_minimo_parada.microseconds)
            cleaned["tempo_minimo_parada"] = tempo_minimo_parada
        if tempo_minimo_parada is None or tempo_minimo_parada < timedelta(minutes=1):
            self.add_error("tempo_minimo_parada", "Informe ao menos 00:01:00.")

        return cleaned


# ========================
#  Turnos
# ========================
class TurnoRecursoForm(forms.ModelForm):
    HORAS = [(f"{h:02d}", f"{h:02d}") for h in range(0, 24)]
    MINUTOS = [(f"{m:02d}", f"{m:02d}") for m in range(0, 60)]
    SEGUNDOS = [(f"{s:02d}", f"{s:02d}") for s in range(0, 60)]

    hora_inicio_h = forms.ChoiceField(
        choices=HORAS, widget=forms.Select(attrs={"class": "form-control"})
    )
    hora_inicio_m = forms.ChoiceField(
        choices=MINUTOS, widget=forms.Select(attrs={"class": "form-control"})
    )
    hora_inicio_s = forms.ChoiceField(
        choices=SEGUNDOS, widget=forms.Select(attrs={"class": "form-control"})
    )

    hora_fim_h = forms.ChoiceField(
        choices=HORAS, widget=forms.Select(attrs={"class": "form-control"})
    )
    hora_fim_m = forms.ChoiceField(
        choices=MINUTOS, widget=forms.Select(attrs={"class": "form-control"})
    )
    hora_fim_s = forms.ChoiceField(
        choices=SEGUNDOS, widget=forms.Select(attrs={"class": "form-control"})
    )

    class Meta:
        model = TurnoRecurso
        fields = ["turnobase", "recurso", "dias", "hora_inicio", "hora_fim"]
        widgets = {
            "turnobase": forms.Select(attrs={"class": "form-control"}),
            "recurso": forms.Select(attrs={"class": "form-control"}),
            "dias": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: 1,2,3"}),
            "hora_inicio": forms.HiddenInput(),
            "hora_fim": forms.HiddenInput(),
        }

    def clean(self):
        cleaned = super().clean()
        hi_h = cleaned.get("hora_inicio_h")
        hi_m = cleaned.get("hora_inicio_m")
        hi_s = cleaned.get("hora_inicio_s")
        hf_h = cleaned.get("hora_fim_h")
        hf_m = cleaned.get("hora_fim_m")
        hf_s = cleaned.get("hora_fim_s")

        if hi_h and hi_m and hi_s:
            cleaned["hora_inicio"] = f"{hi_h}:{hi_m}:{hi_s}"
        if hf_h and hf_m and hf_s:
            cleaned["hora_fim"] = f"{hf_h}:{hf_m}:{hf_s}"

        return cleaned


# ========================
#  Planejamento HE
# ========================
class HoraExtraPlanejadaForm(forms.ModelForm):
    HORAS = [(f"{h:02d}", f"{h:02d}") for h in range(0, 24)]
    MINUTOS = [(f"{m:02d}", f"{m:02d}") for m in range(0, 60)]
    SEGUNDOS = [(f"{s:02d}", f"{s:02d}") for s in range(0, 60)]

    hora_inicio_h = forms.ChoiceField(choices=HORAS)
    hora_inicio_m = forms.ChoiceField(choices=MINUTOS)
    hora_inicio_s = forms.ChoiceField(choices=SEGUNDOS)
    hora_fim_h = forms.ChoiceField(choices=HORAS)
    hora_fim_m = forms.ChoiceField(choices=MINUTOS)
    hora_fim_s = forms.ChoiceField(choices=SEGUNDOS)

    turnobase = forms.ModelMultipleChoiceField(
        queryset=TurnoBase.objects.all().order_by("descricao"),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
    )
    recursos = forms.ModelMultipleChoiceField(
        queryset=Recurso.objects.all().order_by("descricao"),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
    )

    class Meta:
        model = HoraExtraPlanejada
        fields = [
            "turnobase",
            "recurso",
            "dias",
            "data_inicio",
            "data_fim",
            "hora_inicio",
            "hora_fim",
            "considera_feriado",
        ]
        widgets = {
            "data_inicio": forms.DateInput(attrs={"type": "date"}),
            "data_fim": forms.DateInput(attrs={"type": "date"}),
            "hora_inicio": forms.HiddenInput(),
            "hora_fim": forms.HiddenInput(),
            "considera_feriado": forms.CheckboxInput(),
        }

    def clean(self):
        cleaned = super().clean()
        hi_h, hi_m, hi_s = (
            cleaned.get("hora_inicio_h"),
            cleaned.get("hora_inicio_m"),
            cleaned.get("hora_inicio_s"),
        )
        hf_h, hf_m, hf_s = (
            cleaned.get("hora_fim_h"),
            cleaned.get("hora_fim_m"),
            cleaned.get("hora_fim_s"),
        )
        if hi_h and hi_m and hi_s:
            cleaned["hora_inicio"] = f"{hi_h}:{hi_m}:{hi_s}"
        if hf_h and hf_m and hf_s:
            cleaned["hora_fim"] = f"{hf_h}:{hf_m}:{hf_s}"
        return cleaned


# ========================
# Taras
# ========================
class TaraForm(forms.ModelForm):
    class Meta:
        model = Tara
        fields = ["tara", "peso"]
        widgets = {
            "tara": forms.TextInput(
                attrs={"class": "border border-black w-full p-1 rounded bg-white"}
            ),
            "peso": forms.NumberInput(
                attrs={"class": "border border-black w-full p-1 rounded bg-white", "step": "0.001"}
            ),
        }


# ========================
# Configurações da aplicação
# ========================
class ConfiguracaoAplicacaoForm(forms.Form):
    """Descrição e valor de uma chave JÁ DECLARADA em código.

    Desenho do dono do produto (2026-08): a chave é parte do código, não da
    tela — a pessoa não digita, não seleciona, não cria e não remove chave.
    A chave vem da URL; a view valida que está em `CHAVES_CONHECIDAS`
    (desconhecida → 404) e entrega o registro pronto a este form. O
    validador da chave conhecida roda aqui (primeira barreira) e de novo no
    service `definir` (segunda). Chave conhecida sem linha no banco edita o
    default: salvar cria a linha; linha excluída por qualquer via devolve o
    default na tela — a tabela é espelho do declarado, nunca a fonte dele.
    """

    descricao = forms.CharField(
        label="Descrição",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    valor = forms.CharField(
        label="Valor",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def __init__(self, *args, conhecida: ChaveConhecida, **kwargs):
        super().__init__(*args, **kwargs)
        self.conhecida = conhecida

    def clean_valor(self):
        valor = self.cleaned_data.get("valor")
        try:
            return self.conhecida.validador(valor)
        except ValidationError as erro:
            raise forms.ValidationError(erro.messages) from None
