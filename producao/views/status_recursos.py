from django.core.paginator import Paginator
from django.db.models import OuterRef, Subquery
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin

from accounts.models import CentroRecurso, Empresa, Recurso, Setor
from producao.models import LogTrocaOPAtiva
from SIGMA.autorizacao import permissao_requerida
from SIGMA.integracoes.oracle import cursor_oracle_erp


def _formatar_op_ativa(origem, numero_op):
    if numero_op is None:
        return "-"
    return f"{origem}/{numero_op}"


def _buscar_nomes_operadores(cards):
    operadores_por_empresa = {}
    for card in cards:
        codemp = card.get("codemp")
        id_operador = card.get("id_operador")
        if codemp and id_operador:
            operadores_por_empresa.setdefault(int(codemp), set()).add(int(id_operador))

    nomes = {}
    if not operadores_por_empresa:
        return nomes

    with cursor_oracle_erp() as cursor:
        for codemp, operadores in operadores_por_empresa.items():
            placeholders = []
            params = {"codemp": codemp}
            for indice, operador in enumerate(sorted(operadores)):
                nome_param = f"operador_{codemp}_{indice}"
                params[nome_param] = operador
                placeholders.append(f":{nome_param}")

            cursor.execute(
                f"""
                    SELECT numcad, nomope
                    FROM e906ope
                    WHERE codemp = :codemp
                      AND numcad IN ({", ".join(placeholders)})
                """,
                params,
            )
            for numcad, nomope in cursor.fetchall():
                nomes[(int(codemp), int(numcad))] = nomope

    return nomes


def _buscar_producao_total_dia(recursos_qs):
    recursos = list(
        recursos_qs.values(
            "centro_recurso__codigo_integrador",
            "centro_recurso__setor__departamento__filial__empresa__codemp",
        )
    )
    if not recursos:
        return {}

    chaves_por_empresa = {}
    for recurso in recursos:
        codcre = str(recurso.get("centro_recurso__codigo_integrador") or "").strip()
        codemp = recurso.get("centro_recurso__setor__departamento__filial__empresa__codemp")
        if codcre and codemp:
            chaves_por_empresa.setdefault(int(codemp), set()).add(codcre)

    if not chaves_por_empresa:
        return {}

    producao = {}
    data_hoje = timezone.localdate()

    with cursor_oracle_erp() as cursor:
        for codemp, codcres in chaves_por_empresa.items():
            placeholders = []
            params = {"codemp": codemp, "data_hoje": data_hoje}
            for indice, codcre in enumerate(sorted(codcres)):
                nome_param = f"codcre_{codemp}_{indice}"
                params[nome_param] = codcre
                placeholders.append(f":{nome_param}")

            cursor.execute(
                f"""
                    SELECT codcre, NVL(SUM(qtdre1), 0) AS qtd_total
                    FROM e900eoq
                    WHERE codemp = :codemp
                      AND datrea = :data_hoje
                      AND codcre IN ({", ".join(placeholders)})
                    GROUP BY codcre
                """,
                params,
            )

            for codcre, qtd_total in cursor.fetchall():
                producao[(int(codemp), str(codcre).strip())] = qtd_total or 0

    return producao


def _buscar_producao_desde_troca(recursos_qs):
    recursos = list(
        recursos_qs.values(
            "centro_recurso__codigo_integrador",
            "centro_recurso__setor__departamento__filial__empresa__codemp",
            "horario_inicio_log",
        )
    )
    if not recursos:
        return {}

    recursos_por_empresa = {}
    for recurso in recursos:
        codcre = str(recurso.get("centro_recurso__codigo_integrador") or "").strip()
        codemp = recurso.get("centro_recurso__setor__departamento__filial__empresa__codemp")
        horario_inicio = recurso.get("horario_inicio_log")
        if codcre and codemp and horario_inicio:
            horario_local = timezone.localtime(horario_inicio)
            recursos_por_empresa.setdefault(int(codemp), []).append(
                {
                    "codcre": codcre,
                    "data": horario_local.date(),
                    "minutos": (horario_local.hour * 60) + horario_local.minute,
                }
            )

    if not recursos_por_empresa:
        return {}

    producao = {}
    with cursor_oracle_erp() as cursor:
        for codemp, recursos_empresa in recursos_por_empresa.items():
            clausulas = []
            params = {"codemp": codemp}
            for indice, recurso in enumerate(recursos_empresa):
                codcre_param = f"codcre_{indice}"
                data_param = f"data_{indice}"
                hora_param = f"hora_{indice}"
                params[codcre_param] = recurso["codcre"]
                params[data_param] = recurso["data"]
                params[hora_param] = recurso["minutos"]
                clausulas.append(
                    f"""
                        (
                            codcre = :{codcre_param}
                            AND (
                                datrea > :{data_param}
                                OR (datrea = :{data_param} AND horrea >= :{hora_param})
                            )
                        )
                    """
                )

            cursor.execute(
                f"""
                    SELECT codcre, NVL(SUM(qtdre1), 0) AS qtd_total
                    FROM e900eoq
                    WHERE codemp = :codemp
                      AND ({" OR ".join(clausulas)})
                    GROUP BY codcre
                """,
                params,
            )

            for codcre, qtd_total in cursor.fetchall():
                producao[(int(codemp), str(codcre).strip())] = qtd_total or 0

    return producao


@permissao_requerida("producao.pode_acessar_relatorios_producao")
@xframe_options_sameorigin
def status_recursos_view(request):
    context = montar_contexto_status_recursos(request)
    return render(request, "producao/status_recursos.html", context)


def montar_contexto_status_recursos(request):
    empresa_id = request.GET.get("empresa", "").strip()
    setor_id = request.GET.get("setor", "").strip()
    centro_id = request.GET.get("centro", "").strip()
    recurso_id = request.GET.get("recurso", "").strip()
    pagina = request.GET.get("page", "1").strip()

    if request.user.is_staff or request.user.is_superuser:
        empresas = Empresa.objects.filter(ativa=True).order_by("nome")
        if not empresa_id:
            empresa_id = str(empresas.values_list("id", flat=True).first() or "")
    else:
        filial = getattr(request.user, "filial", None)
        empresa_usuario = getattr(filial, "empresa", None)
        if empresa_usuario:
            empresas = Empresa.objects.filter(id=empresa_usuario.id, ativa=True)
            if not empresa_id:
                empresa_id = str(empresa_usuario.id)
        else:
            empresas = Empresa.objects.none()

    if empresa_id and not empresas.filter(pk=empresa_id).exists():
        empresa_id = setor_id = centro_id = recurso_id = ""

    setores = Setor.objects.none()
    centros = CentroRecurso.objects.none()
    if empresa_id:
        setores = (
            Setor.objects.filter(
                departamento__filial__empresa_id=empresa_id,
                centrorecurso__recursos__ativo=True,
            )
            .values_list("descricao", flat=True)
            .distinct()
            .order_by("descricao")
        )
        centros = (
            CentroRecurso.objects.filter(
                setor__departamento__filial__empresa_id=empresa_id,
                recursos__ativo=True,
            )
            .exclude(descricao__icontains="Geral")
            .distinct()
            .order_by("descricao")
        )
        if setor_id:
            centros = centros.filter(setor__descricao=setor_id)

    recursos = Recurso.objects.none()
    if empresa_id and centro_id:
        recursos = Recurso.objects.filter(
            centro_recurso_id=centro_id,
            centro_recurso__setor__departamento__filial__empresa_id=empresa_id,
            ativo=True,
        ).order_by("ordenacao", "descricao")
    elif empresa_id:
        recursos = (
            Recurso.objects.filter(
                centro_recurso__setor__departamento__filial__empresa_id=empresa_id,
                ativo=True,
            )
            .exclude(centro_recurso__descricao__icontains="Geral")
            .order_by("ordenacao", "descricao")
        )
    if setor_id:
        recursos = recursos.filter(centro_recurso__setor__descricao=setor_id)

    log_aberto = LogTrocaOPAtiva.objects.filter(
        recurso=OuterRef("pk"),
        horario_saida__isnull=True,
    ).order_by("-horario_troca")

    recursos_qs = (
        Recurso.objects.select_related(
            "centro_recurso",
            "centro_recurso__setor",
            "centro_recurso__setor__departamento",
            "centro_recurso__setor__departamento__filial",
            "centro_recurso__setor__departamento__filial__empresa",
        )
        .filter(ativo=True)
        .exclude(centro_recurso__descricao__icontains="Geral")
        .annotate(
            op_ativa_origem=Subquery(log_aberto.values("origem")[:1]),
            op_ativa_op=Subquery(log_aberto.values("op")[:1]),
            horario_inicio_log=Subquery(log_aberto.values("horario_troca")[:1]),
            id_operador_log=Subquery(log_aberto.values("id_operador")[:1]),
        )
        .order_by("ordenacao", "centro_recurso__descricao", "descricao")
    )

    if empresa_id:
        recursos_qs = recursos_qs.filter(
            centro_recurso__setor__departamento__filial__empresa_id=empresa_id
        )
    if setor_id:
        recursos_qs = recursos_qs.filter(centro_recurso__setor__descricao=setor_id)
    if centro_id:
        recursos_qs = recursos_qs.filter(centro_recurso_id=centro_id)
    if recurso_id:
        recursos_qs = recursos_qs.filter(id=recurso_id)

    producao_total_dia = _buscar_producao_total_dia(recursos_qs)
    producao_desde_troca = _buscar_producao_desde_troca(recursos_qs)

    cards = []
    for recurso in recursos_qs:
        filial = recurso.centro_recurso.setor.departamento.filial
        empresa = filial.empresa
        chave_recurso = (
            int(empresa.codemp),
            str(recurso.centro_recurso.codigo_integrador or "").strip(),
        )
        possui_atividade = recurso.op_ativa_op is not None
        cards.append(
            {
                "recurso_id": recurso.id,
                "recurso_codigo": recurso.codigo,
                "recurso_descricao": recurso.descricao,
                "empresa_nome": empresa.nome,
                "centro": recurso.centro_recurso.descricao,
                "codemp": empresa.codemp,
                "op_ativa": _formatar_op_ativa(recurso.op_ativa_origem, recurso.op_ativa_op)
                if possui_atividade
                else "Sem atividade",
                "horario_inicio": recurso.horario_inicio_log,
                "id_operador": recurso.id_operador_log,
                "possui_atividade": possui_atividade,
                "producao_total_dia": producao_total_dia.get(chave_recurso, 0),
                "producao_desde_troca": producao_desde_troca.get(chave_recurso, 0),
            }
        )

    nomes_operadores = _buscar_nomes_operadores(cards)
    for card in cards:
        chave = (
            (int(card["codemp"]), int(card["id_operador"]))
            if card.get("codemp") and card.get("id_operador")
            else None
        )
        card["operador_nome"] = nomes_operadores.get(chave, "-") if chave else "-"

    paginator = Paginator(cards, 9)
    page_obj = paginator.get_page(pagina)

    return {
        "empresas": empresas,
        "setores": setores,
        "centros": centros,
        "recursos": recursos,
        "empresa_id": empresa_id,
        "setor_id": setor_id,
        "centro_id": centro_id,
        "recurso_id": recurso_id,
        "cards": page_obj.object_list,
        "page_obj": page_obj,
        "titulo": "Status Recursos",
    }
