import json

from django.contrib import messages
from django.db import DatabaseError, transaction
from django.db.models import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from producao.models import RegraParadaRecurso
from SIGMA.autorizacao import permissao_requerida
from SIGMA.integracoes.oracle import cursor_oracle_erp
from telemetria.forms import RegraParadaRecursoForm, SensorRecursoForm
from telemetria.models import SensorRecurso

from ..forms import ParametrosRecursoForm, RecursoForm
from ..models import (
    CentroRecurso,
    Departamento,
    Empresa,
    Filial,
    MotivoAbrangencia,
    Recurso,
    RecursoTara,
    Setor,
    Tara,
)


def _parametros_recurso_vazios(form):
    for campo in form.Meta.fields:
        valor = form.cleaned_data.get(campo)
        if valor not in (None, ""):
            return False
    return True


def _salvar_parametros_recurso(form, recurso):
    if _parametros_recurso_vazios(form):
        if form.instance and form.instance.pk:
            form.instance.delete()
        return

    parametros = form.save(commit=False)
    parametros.recurso = recurso
    parametros.save()


def _codemp_recurso(recurso):
    return recurso.centro_recurso.setor.departamento.filial.empresa.codemp


def _grupos_parada_erp_ativos(codemp):
    with cursor_oracle_erp() as cursor:
        cursor.execute(
            """
            SELECT g.usu_codgpm, g.usu_desgpm
            FROM usu_t018gpm g
            WHERE g.usu_codemp = :codemp
              AND g.usu_sitgpm = 'A'
              AND EXISTS (
                  SELECT 1
                  FROM usu_t018mvp m
                  INNER JOIN e018mtv e
                      ON e.codemp = m.usu_codemp
                     AND e.codmtv = m.usu_codmtv
                  WHERE m.usu_codemp = g.usu_codemp
                    AND m.usu_codgmp = g.usu_codgpm
                    AND e.sitmtv = 'A'
              )
            ORDER BY g.usu_codgpm
            """,
            {"codemp": codemp},
        )
        return [
            {
                "codgpm": str(codgpm).strip(),
                "desgpm": str(desgpm or "").strip(),
            }
            for codgpm, desgpm in cursor.fetchall()
        ]


def _motivos_grupo_erp_ativos(codemp, codgpm=None):
    params = {"codemp": codemp}
    filtro_grupo = ""
    if codgpm is not None:
        filtro_grupo = " AND m.usu_codgmp = :codgpm"
        params["codgpm"] = codgpm

    with cursor_oracle_erp() as cursor:
        cursor.execute(
            f"""
            SELECT m.usu_codmtv,
                   e.desmtv,
                   g.usu_codgpm,
                   g.usu_desgpm
            FROM usu_t018mvp m
            INNER JOIN e018mtv e
                ON e.codemp = m.usu_codemp
               AND e.codmtv = m.usu_codmtv
            INNER JOIN usu_t018gpm g
                ON g.usu_codemp = m.usu_codemp
               AND g.usu_codgpm = m.usu_codgmp
            WHERE m.usu_codemp = :codemp
              AND e.sitmtv = 'A'
              AND g.usu_sitgpm = 'A'
              {filtro_grupo}
            ORDER BY g.usu_codgpm, m.usu_codmtv
            """,
            params,
        )
        return [
            {
                "codmtv": str(codmtv).strip(),
                "desmtv": str(desmtv or "").strip(),
                "codgpm": str(codgpm_resultado).strip(),
                "desgpm": str(desgpm or "").strip(),
            }
            for codmtv, desmtv, codgpm_resultado, desgpm in cursor.fetchall()
        ]


def _sincronizar_motivos_abrangencia():
    vinculos = list(MotivoAbrangencia.objects.values("id", "codemp", "codgpm", "codmtv"))
    ativos_por_empresa = {}

    for codemp in {vinculo["codemp"] for vinculo in vinculos}:
        ativos_por_empresa[codemp] = {
            (int(motivo["codgpm"]), motivo["codmtv"])
            for motivo in _motivos_grupo_erp_ativos(codemp)
        }

    ids_inativos = [
        vinculo["id"]
        for vinculo in vinculos
        if (vinculo["codgpm"], vinculo["codmtv"]) not in ativos_por_empresa[vinculo["codemp"]]
    ]
    if not ids_inativos:
        return 0

    with transaction.atomic():
        MotivoAbrangencia.objects.filter(id__in=ids_inativos).delete()
    return len(ids_inativos)


def _dados_motivos_abrangencia(recurso):
    codemp = _codemp_recurso(recurso)
    motivos_vinculados = list(
        MotivoAbrangencia.objects.filter(recurso=recurso, codemp=codemp).order_by(
            "codgpm", "codmtv"
        )
    )

    try:
        grupos_erp = _grupos_parada_erp_ativos(codemp)
        motivos_erp = _motivos_grupo_erp_ativos(codemp)
    except DatabaseError:
        for motivo in motivos_vinculados:
            motivo.desmtv_erp = ""
            motivo.desgpm_erp = ""
        return (
            codemp,
            motivos_vinculados,
            [],
            "Não foi possível consultar os motivos ativos no ERP.",
        )

    dados_motivos = {(motivo["codgpm"], motivo["codmtv"]): motivo for motivo in motivos_erp}
    for motivo in motivos_vinculados:
        dados_erp = dados_motivos.get((str(motivo.codgpm), motivo.codmtv), {})
        motivo.desmtv_erp = dados_erp.get("desmtv", "")
        motivo.desgpm_erp = dados_erp.get("desgpm", "")

    return codemp, motivos_vinculados, grupos_erp, None


@permissao_requerida("accounts.manipular_cadastros")
def lista_recursos(request):

    recursos = Recurso.objects.select_related("centro_recurso__setor__departamento").order_by(
        "ordenacao", "descricao"
    )

    recurso_editando = None
    filial_sel = dep_sel = setor_sel = None
    editar_param = request.GET.get("editar")
    form = RecursoForm()
    param_form = ParametrosRecursoForm()
    taras_disponiveis = []
    taras_vinculadas = []
    motivos_vinculados = []
    grupos_erp = []
    codemp_motivos = None
    erro_motivos_erp = None
    sensor_recurso_form = None
    sensores_recurso = []
    cache_telemetria_json = None
    regra_parada_automatica_form = None
    sensores_regra_parada = []

    # SALVAR / ATUALIZAR
    if request.method == "POST":
        if "salvar" in request.POST:
            form = RecursoForm(request.POST)
            param_form = ParametrosRecursoForm(request.POST)
            if form.is_valid() and param_form.is_valid():
                recurso = form.save(commit=False)
                centro_id = request.POST.get("centro_recurso")
                if centro_id:
                    recurso.centro_recurso_id = centro_id
                recurso.save()
                _salvar_parametros_recurso(param_form, recurso)
                from telemetria.services.coleta import notificar_alteracao_recurso

                notificar_alteracao_recurso(recurso.id)
                messages.success(request, "Recurso cadastrado com sucesso.")
                return redirect(f"{request.path}?editar={recurso.id}")
            else:
                editar_param = "novo"

        elif "atualizar" in request.POST:
            recurso_id = request.POST.get("recurso_id")
            recurso = get_object_or_404(Recurso, pk=recurso_id)

            form = RecursoForm(request.POST, instance=recurso)
            parametros = getattr(recurso, "parametros_recurso", None)
            param_form = ParametrosRecursoForm(request.POST, instance=parametros)
            if form.is_valid() and param_form.is_valid():
                recurso_editado = form.save(commit=False)

                centro_id = request.POST.get("centro_recurso")
                if centro_id:
                    recurso_editado.centro_recurso_id = centro_id

                # impede alteração do recurso ID 1 (Geral)
                if recurso.id == 1:
                    if recurso_editado.descricao.strip() != recurso.descricao:
                        messages.warning(request, "O nome deste recurso não pode ser alterado.")
                        return redirect("lista_recursos")

                    if recurso_editado.centro_recurso_id != recurso.centro_recurso_id:
                        messages.warning(
                            request, "O centro de recurso deste item não pode ser alterado."
                        )
                        return redirect("lista_recursos")

                recurso_editado.save()
                _salvar_parametros_recurso(param_form, recurso_editado)
                from telemetria.services.coleta import notificar_alteracao_recurso

                notificar_alteracao_recurso(recurso_editado.id)
                messages.success(request, "Recurso atualizado com sucesso.")
                return redirect("lista_recursos")
            else:
                # Se o form não for válido, precisamos carregar os dados para re-renderizar a página de edição
                recurso_editando = recurso
                setor = recurso_editando.centro_recurso.setor
                dep = setor.departamento
                filial = dep.filial
                filial_sel, dep_sel, setor_sel = filial.id, dep.id, setor.id

                taras_vinculadas = Tara.objects.filter(
                    tara_recursos__recurso=recurso_editando
                ).order_by("tara")
                taras_disponiveis = Tara.objects.exclude(
                    id__in=taras_vinculadas.values_list("id", flat=True)
                ).order_by("tara")
                codemp_motivos, motivos_vinculados, grupos_erp, erro_motivos_erp = (
                    _dados_motivos_abrangencia(recurso_editando)
                )

        elif "vincular_tara" in request.POST:
            recurso_id = request.POST.get("recurso_id")
            tara_id = request.POST.get("tara_id")
            recurso = get_object_or_404(Recurso, pk=recurso_id)
            tara = get_object_or_404(Tara, pk=tara_id)
            RecursoTara.objects.get_or_create(recurso=recurso, tara=tara)
            messages.success(request, "Tara vinculada com sucesso.")
            return redirect(f"{request.path}?editar={recurso_id}#tab-taras")

        elif "desvincular_tara" in request.POST:
            recurso_id = request.POST.get("recurso_id")
            tara_id = request.POST.get("tara_id")
            RecursoTara.objects.filter(recurso_id=recurso_id, tara_id=tara_id).delete()
            messages.success(request, "Tara desvinculada com sucesso.")
            return redirect(f"{request.path}?editar={recurso_id}#tab-taras")

        elif "vincular_motivo_abrangencia" in request.POST:
            recurso_id = request.POST.get("recurso_id")
            codgpm = request.POST.get("codgpm", "").strip()
            codmtv = request.POST.get("codmtv", "").strip()
            recurso = get_object_or_404(Recurso, pk=recurso_id)
            codemp = _codemp_recurso(recurso)

            if not codgpm.isdigit() or not codmtv:
                messages.error(request, "Selecione um grupo e um motivo válidos.")
            else:
                try:
                    motivos_ativos = _motivos_grupo_erp_ativos(codemp, codgpm)
                except DatabaseError:
                    messages.error(request, "Não foi possível consultar os motivos ativos no ERP.")
                else:
                    motivo_ativo = next(
                        (motivo for motivo in motivos_ativos if motivo["codmtv"] == codmtv),
                        None,
                    )
                    if not motivo_ativo:
                        messages.error(
                            request,
                            "O motivo selecionado não está ativo para a empresa do recurso.",
                        )
                    else:
                        _, criado = MotivoAbrangencia.objects.get_or_create(
                            recurso=recurso,
                            codemp=codemp,
                            codgpm=int(codgpm),
                            codmtv=codmtv,
                        )
                        if criado:
                            messages.success(request, "Motivo de parada vinculado com sucesso.")
                        else:
                            messages.warning(request, "Este motivo já está vinculado ao recurso.")
            return redirect(f"{request.path}?editar={recurso_id}#tab-motivos-abrangencia")

        elif "desvincular_motivo_abrangencia" in request.POST:
            recurso_id = request.POST.get("recurso_id")
            motivo_id = request.POST.get("motivo_id")
            MotivoAbrangencia.objects.filter(id=motivo_id, recurso_id=recurso_id).delete()
            messages.success(request, "Motivo de parada desvinculado com sucesso.")
            return redirect(f"{request.path}?editar={recurso_id}#tab-motivos-abrangencia")

        elif "sincronizar_motivos_abrangencia" in request.POST:
            recurso_id = request.POST.get("recurso_id")
            try:
                removidos = _sincronizar_motivos_abrangencia()
            except DatabaseError:
                messages.error(
                    request,
                    "Não foi possível consultar os motivos ativos no ERP. Nenhum vínculo foi removido.",
                )
            else:
                if removidos:
                    messages.success(
                        request,
                        f"{removidos} vínculo(s) de motivo de parada inativo(s) ou sem grupo no ERP foram removidos.",
                    )
                else:
                    messages.info(
                        request, "Todos os vínculos de motivos de parada continuam ativos no ERP."
                    )
            return redirect(f"{request.path}?editar={recurso_id}#tab-motivos-abrangencia")

        elif "clonar_motivos_abrangencia" in request.POST:
            recurso_id = request.POST.get("recurso_id")
            recurso_origem_id = request.POST.get("recurso_origem_id")
            recurso_destino = get_object_or_404(Recurso, pk=recurso_id)

            if not recurso_origem_id or not recurso_origem_id.isdigit():
                messages.error(request, "Selecione o recurso de origem.")
            else:
                recurso_origem = get_object_or_404(
                    Recurso,
                    pk=recurso_origem_id,
                    ativo=True,
                    centro_recurso__setor__departamento__filial__empresa__ativa=True,
                )
                if recurso_origem.id == recurso_destino.id:
                    messages.error(
                        request, "O recurso de origem deve ser diferente do recurso em edição."
                    )
                else:
                    codemp_origem = _codemp_recurso(recurso_origem)
                    codemp_destino = _codemp_recurso(recurso_destino)
                    chaves_origem = list(
                        MotivoAbrangencia.objects.filter(
                            recurso=recurso_origem,
                            codemp=codemp_origem,
                        ).values_list("codmtv", "codgpm")
                    )

                    if not chaves_origem:
                        messages.warning(
                            request, "O recurso de origem não possui motivos de parada vinculados."
                        )
                    else:
                        try:
                            chaves_ativas_destino = {
                                (int(motivo["codgpm"]), motivo["codmtv"])
                                for motivo in _motivos_grupo_erp_ativos(codemp_destino)
                            }
                        except DatabaseError:
                            messages.error(
                                request,
                                "Não foi possível validar os motivos ativos no ERP para o recurso de destino.",
                            )
                        else:
                            criados = existentes = ignorados = 0
                            with transaction.atomic():
                                for codmtv, codgpm in chaves_origem:
                                    if (codgpm, codmtv) not in chaves_ativas_destino:
                                        ignorados += 1
                                        continue
                                    _, criado = MotivoAbrangencia.objects.get_or_create(
                                        recurso=recurso_destino,
                                        codemp=codemp_destino,
                                        codgpm=codgpm,
                                        codmtv=codmtv,
                                    )
                                    if criado:
                                        criados += 1
                                    else:
                                        existentes += 1

                            if criados:
                                messages.success(
                                    request,
                                    f"{criados} motivo(s) de parada copiado(s) de {recurso_origem}.",
                                )
                            else:
                                messages.info(request, "Nenhum novo motivo de parada foi copiado.")
                            if existentes:
                                messages.info(
                                    request,
                                    f"{existentes} vínculo(s) já existiam no recurso de destino.",
                                )
                            if ignorados:
                                messages.warning(
                                    request,
                                    f"{ignorados} vínculo(s) não estão ativos para a empresa do recurso de destino e não foram copiados.",
                                )
            return redirect(f"{request.path}?editar={recurso_id}#tab-motivos-abrangencia")

    elif "editar" in request.GET:
        recurso_id = request.GET.get("editar")
        if recurso_id != "novo":
            recurso_editando = get_object_or_404(Recurso, pk=recurso_id)
            form = RecursoForm(instance=recurso_editando)
            parametros = getattr(recurso_editando, "parametros_recurso", None)
            param_form = ParametrosRecursoForm(instance=parametros)
            setor = recurso_editando.centro_recurso.setor
            dep = setor.departamento
            filial = dep.filial
            filial_sel, dep_sel, setor_sel = filial.id, dep.id, setor.id

            taras_vinculadas = Tara.objects.filter(
                tara_recursos__recurso=recurso_editando
            ).order_by("tara")
            taras_disponiveis = Tara.objects.exclude(
                id__in=taras_vinculadas.values_list("id", flat=True)
            ).order_by("tara")
            codemp_motivos, motivos_vinculados, grupos_erp, erro_motivos_erp = (
                _dados_motivos_abrangencia(recurso_editando)
            )
            sensor_recurso_form = SensorRecursoForm(recurso=recurso_editando)
            sensores_recurso = (
                SensorRecurso.objects.filter(recurso=recurso_editando)
                .select_related("sensor")
                .order_by("sensor__chave_origem")
            )
            regra_parada, _ = RegraParadaRecurso.objects.get_or_create(recurso=recurso_editando)
            regra_parada_automatica_form = RegraParadaRecursoForm(
                instance=regra_parada,
                recurso=recurso_editando,
            )
            sensores_regra_parada = list(
                SensorRecurso.objects.filter(
                    recurso=recurso_editando,
                    sensor__ativo=True,
                )
                .select_related("sensor")
                .order_by("sensor__chave_origem")
                .values("sensor__chave_origem", "sensor__nome", "sensor__tipo_valor")
            )
            from telemetria.services.coleta import obter_cache_recurso

            cache_telemetria = obter_cache_recurso(recurso_editando.id)
            if cache_telemetria is not None:
                cache_telemetria_json = json.dumps(cache_telemetria, ensure_ascii=False, indent=2)
        else:
            form = RecursoForm()
            param_form = ParametrosRecursoForm()

    context = {
        "recursos": recursos,
        "form": form,
        "param_form": param_form,
        "recurso_editando": recurso_editando,
        "filiais": Filial.objects.filter(ativa=True).order_by("nome"),
        "filial_sel": filial_sel,
        "dep_sel": dep_sel,
        "setor_sel": setor_sel,
        "editar_param": editar_param,
        "taras_disponiveis": taras_disponiveis,
        "taras_vinculadas": taras_vinculadas,
        "motivos_vinculados": motivos_vinculados,
        "codemp_motivos": codemp_motivos,
        "erro_motivos_erp": erro_motivos_erp,
        "grupos_erp": grupos_erp,
        "empresas_ativas": Empresa.objects.filter(ativa=True).order_by("nome"),
        "sensor_recurso_form": sensor_recurso_form,
        "sensores_recurso": sensores_recurso,
        "cache_telemetria_json": cache_telemetria_json,
        "regra_parada_automatica_form": regra_parada_automatica_form,
        "sensores_regra_parada": sensores_regra_parada,
    }

    return render(request, "accounts/recursos.html", context)


@require_POST
@permissao_requerida("accounts.manipular_cadastros")
def deletar_recurso(request, pk):

    recurso = get_object_or_404(Recurso, pk=pk)

    if recurso.id == 1:
        messages.warning(request, "Este recurso não pode ser excluído.")
        return redirect("lista_recursos")

    try:
        recurso.delete()
        messages.success(request, "Recurso excluído com sucesso.")
    except ProtectedError as e:
        # Extrai os nomes das tabelas relacionadas que impediram a exclusão
        protected_objects = e.protected_objects
        related_models = set()
        for obj in protected_objects:
            related_models.add(obj._meta.verbose_name or obj._meta.model_name)

        models_str = ", ".join(related_models)
        messages.warning(
            request,
            f"Não é possível excluir este recurso pois está vinculado a: {models_str}. Exclua esses vínculos primeiro.",
        )
    return redirect("lista_recursos")


# ============================
# ENDPOINTS AJAX CASCATA
# ============================
@permissao_requerida("accounts.manipular_cadastros")
def filtrar_departamentos(request):

    filial_id = request.GET.get("filial_id")
    departamentos = Departamento.objects.filter(filial_id=filial_id).values("id", "descricao")
    return JsonResponse(list(departamentos), safe=False)


@permissao_requerida("accounts.manipular_cadastros")
def filtrar_setores(request):

    departamento_id = request.GET.get("departamento_id")
    setores = Setor.objects.filter(departamento_id=departamento_id).values("id", "descricao")
    return JsonResponse(list(setores), safe=False)


@permissao_requerida("accounts.manipular_cadastros")
def filtrar_centros(request):

    setor_id = request.GET.get("setor_id")
    centros = CentroRecurso.objects.filter(setor_id=setor_id).values("id", "descricao")
    return JsonResponse(list(centros), safe=False)


@permissao_requerida("accounts.manipular_cadastros")
def motivos_por_grupo_parada(request):

    recurso_id = request.GET.get("recurso_id")
    codgpm = request.GET.get("codgpm", "").strip()
    if not recurso_id or not recurso_id.isdigit() or not codgpm.isdigit():
        return JsonResponse({"erro": "Recurso ou grupo de parada inválido."}, status=400)

    recurso = get_object_or_404(Recurso, pk=recurso_id)
    codemp = _codemp_recurso(recurso)
    try:
        motivos_erp = _motivos_grupo_erp_ativos(codemp, codgpm)
    except DatabaseError:
        return JsonResponse(
            {"erro": "Não foi possível consultar os motivos ativos no ERP."}, status=503
        )

    chaves_vinculadas = set(
        MotivoAbrangencia.objects.filter(
            recurso=recurso,
            codemp=codemp,
        ).values_list("codgpm", "codmtv")
    )
    motivos_disponiveis = [
        {
            "codmtv": motivo["codmtv"],
            "desmtv": motivo["desmtv"],
        }
        for motivo in motivos_erp
        if (int(motivo["codgpm"]), motivo["codmtv"]) not in chaves_vinculadas
    ]
    return JsonResponse(motivos_disponiveis, safe=False)


@permissao_requerida("accounts.manipular_cadastros")
def recursos_ativos_por_empresa(request):

    empresa_id = request.GET.get("empresa_id")
    recurso_destino_id = request.GET.get("recurso_destino_id")
    if not empresa_id or not empresa_id.isdigit():
        return JsonResponse({"erro": "Empresa inválida."}, status=400)

    recursos = Recurso.objects.filter(
        ativo=True,
        centro_recurso__setor__departamento__filial__empresa_id=empresa_id,
        centro_recurso__setor__departamento__filial__empresa__ativa=True,
    )
    if recurso_destino_id and recurso_destino_id.isdigit():
        recursos = recursos.exclude(pk=recurso_destino_id)

    return JsonResponse(
        list(recursos.order_by("descricao").values("id", "codigo", "descricao")),
        safe=False,
    )
