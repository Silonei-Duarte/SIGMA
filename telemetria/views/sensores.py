from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Recurso
from producao.models import RegraParadaRecurso
from SIGMA.autorizacao import permissao_requerida

from ..forms import (
    FonteColetaHTTPForm,
    RegraParadaRecursoForm,
    SensorForm,
    SensorRecursoAtualizacaoForm,
    SensorRecursoForm,
)
from ..models import FonteColetaHTTP, Sensor, SensorRecurso

# As telas de sensores exigem a permissão própria do módulo
# (telemetria.pode_gerenciar_sensores) e, para não-staff, ficam presas à
# filial do usuário. Staff/superusuário mantêm escopo global — inclusive
# registros sem filial. Usuário sem filial recebe lista vazia ou negação
# conforme a rota, no padrão das views já convertidas da fatia Autorizações.


def _sensores_visiveis(usuario):
    if usuario.is_staff:
        return Sensor.objects.all()
    filial = getattr(usuario, "filial", None)
    if not filial:
        return Sensor.objects.none()
    return Sensor.objects.filter(filial=filial)


def _fontes_visiveis(usuario):
    if usuario.is_staff:
        return FonteColetaHTTP.objects.all()
    filial = getattr(usuario, "filial", None)
    if not filial:
        return FonteColetaHTTP.objects.none()
    return FonteColetaHTTP.objects.filter(filial=filial)


def _recursos_visiveis(usuario):
    if usuario.is_staff:
        return Recurso.objects.all()
    filial = getattr(usuario, "filial", None)
    if not filial:
        return Recurso.objects.none()
    return Recurso.objects.filter(centro_recurso__setor__departamento__filial=filial)


# Cadastro de sensores: tela /telemetria/sensores/.
@permissao_requerida("telemetria.pode_gerenciar_sensores")
def cadastro_sensores(request, sensor_id=None, fonte_id=None):
    usuario = request.user
    filial_usuario = None if usuario.is_staff else getattr(usuario, "filial", None)
    # Não-staff sem filial não tem escopo de dados: as listas ficam vazias e
    # as escritas são negadas — criar com filial NULL faria o próprio usuário
    # perder o registro de vista (e staff já pode criar sem filial quando
    # quiser).
    sem_filial = not usuario.is_staff and filial_usuario is None

    sensores = _sensores_visiveis(usuario)
    fontes = _fontes_visiveis(usuario)

    fonte = get_object_or_404(fontes, pk=fonte_id) if fonte_id else None
    if request.method == "POST" and request.POST.get("acao") == "fonte":
        fonte_form = FonteColetaHTTPForm(request.POST, instance=fonte)
        if sem_filial:
            messages.error(request, "Usuário sem filial não pode gerenciar fontes de telemetria.")
        elif fonte_form.is_valid():
            fonte = fonte_form.save(commit=False)
            if not usuario.is_staff:
                fonte.filial = filial_usuario
            fonte.save()
            from telemetria.services.coleta import notificar_alteracao_fonte

            notificar_alteracao_fonte(fonte.id)
            messages.success(
                request,
                "Fonte HTTP atualizada com sucesso."
                if fonte_id
                else "Fonte HTTP salva com sucesso.",
            )
            return redirect("telemetria_sensores")
        else:
            mensagens = [erro for erros in fonte_form.errors.values() for erro in erros]
            messages.error(
                request, " ".join(mensagens) or "Verifique a configuração da fonte HTTP."
            )
    sensor = get_object_or_404(sensores, pk=sensor_id) if sensor_id else None
    form = SensorForm(request.POST or None, instance=sensor)
    if not usuario.is_staff:
        # Queryset limitado antes da validação: sem isso, um POST forjado
        # apontaria o sensor para fonte de outra filial.
        form.fields["fonte"].queryset = fontes
    if request.method == "POST" and form.is_valid():
        sensor = form.save(commit=False)
        if not usuario.is_staff:
            sensor.filial = filial_usuario
        sensor.save()
        from telemetria.services.coleta import (
            notificar_alteracao_fonte,
            notificar_alteracao_recurso,
        )

        notificar_alteracao_fonte(sensor.fonte_id)
        for recurso_id in sensor.recursos.values_list("recurso_id", flat=True):
            notificar_alteracao_recurso(recurso_id)
        messages.success(request, "Sensor salvo com sucesso.")
        return redirect("telemetria_sensores")
    return render(
        request,
        "telemetria/sensores.html",
        {
            "sensores": sensores.order_by("chave_origem"),
            "form": form,
            "sensor_editando": sensor,
            "fonte_form": FonteColetaHTTPForm(instance=fonte),
            "fonte_editando": fonte,
            "fontes": fontes.order_by("url"),
        },
    )


@permissao_requerida("telemetria.pode_gerenciar_sensores")
@require_POST
def excluir_sensor(request, sensor_id):
    # get filtrado pelo escopo: sensor de outra filial nunca chega ao delete
    # (com DEBUG=False o 404 vira redirect para o portal, nunca 200).
    sensor = get_object_or_404(_sensores_visiveis(request.user), pk=sensor_id)
    try:
        sensor.delete()
        messages.success(request, "Sensor excluído com sucesso.")
    except ProtectedError:
        messages.warning(
            request, "O sensor não pode ser excluído porque está vinculado a um recurso."
        )
    return redirect("telemetria_sensores")


@permissao_requerida("telemetria.pode_gerenciar_sensores")
@require_POST
def excluir_fonte(request, fonte_id):
    fonte = get_object_or_404(_fontes_visiveis(request.user), pk=fonte_id)
    try:
        fonte.delete()
        messages.success(request, "Fonte HTTP excluída com sucesso.")
    except ProtectedError:
        messages.warning(
            request, "A fonte não pode ser excluída porque possui sensores vinculados."
        )
    return redirect("telemetria_sensores")


# Aba Telemetria do cadastro de recursos: /recursos/?editar=<id>#tab-telemetria.
@permissao_requerida("telemetria.pode_gerenciar_sensores")
def configurar_recurso(request, recurso_id):
    recurso = get_object_or_404(_recursos_visiveis(request.user), pk=recurso_id)
    if request.method != "POST":
        return redirect(f"/recursos/?editar={recurso.id}#tab-telemetria")

    acao = request.POST.get("acao")
    aba_destino = "tab-telemetria"
    if acao == "configuracao":
        messages.error(request, "A configuração HTTP é cadastrada nas fontes de sensores.")
    elif acao == "vincular":
        form = SensorRecursoForm(
            request.POST,
            recurso=recurso,
            # Escopo de filial + apenas sensores ativos: sem o filtro ativo
            # aqui, o fallback do form (Sensor.objects.filter(ativo=True))
            # ficava inalcançável e sensor inativo voltava a ser vinculável.
            sensores_queryset=_sensores_visiveis(request.user).filter(ativo=True),
        )
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Sensor vinculado ao recurso.")
            except IntegrityError:
                messages.error(request, "Já existe este sensor vinculado ao recurso.")
        else:
            messages.error(
                request,
                "Não foi possível vincular o sensor ao recurso.",
            )
    elif acao == "atualizar_vinculos":
        vinculos = list(SensorRecurso.objects.filter(recurso=recurso).order_by("id"))
        formularios = {
            vinculo.id: SensorRecursoAtualizacaoForm(request.POST, vinculo_id=vinculo.id)
            for vinculo in vinculos
        }
        if all(formulario.is_valid() for formulario in formularios.values()):
            with transaction.atomic():
                for vinculo in vinculos:
                    dados = formularios[vinculo.id].cleaned_data
                    vinculo.monitorar_variacao = dados["monitorar_variacao"]
                    vinculo.tipo_tolerancia = dados["tipo_tolerancia"]
                    vinculo.tolerancia = float(dados["tolerancia"])
                    vinculo.full_clean()
                    vinculo.save(
                        update_fields=[
                            "monitorar_variacao",
                            "tipo_tolerancia",
                            "tolerancia",
                        ]
                    )
            messages.success(request, "Vínculos dos sensores atualizados.")
        else:
            messages.error(request, "Verifique os parâmetros dos sensores.")
    elif acao == "excluir_vinculo":
        # vinculo_id chega cru do POST; pk não numérico quebraria o filter
        # com ValueError (HTTP 500). Inválido é tratado como vínculo
        # inexistente: mesma resposta da view, sem excluir nada.
        vinculo_id = request.POST.get("vinculo_id")
        if vinculo_id and vinculo_id.isdigit():
            SensorRecurso.objects.filter(pk=vinculo_id, recurso=recurso).delete()
        messages.success(request, "Sensor desvinculado do recurso.")
    elif acao == "regra_parada":
        aba_destino = "tab-parada-automatica"
        regra, _ = RegraParadaRecurso.objects.get_or_create(recurso=recurso)
        form = RegraParadaRecursoForm(request.POST, instance=regra, recurso=recurso)
        if form.is_valid():
            form.save()
            messages.success(request, "Regra automática de parada salva com sucesso.")
        else:
            mensagens = []
            for erros in form.errors.values():
                mensagens.extend(erros)
            messages.error(
                request,
                " ".join(mensagens) or "Não foi possível salvar a regra automática de parada.",
            )
    from telemetria.services.coleta import notificar_alteracao_recurso

    notificar_alteracao_recurso(recurso.id)
    return redirect(f"/recursos/?editar={recurso.id}#{aba_destino}")
