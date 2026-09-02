import logging
import time
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import connections, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import Empresa, Recurso
from producao.services.altera_apontamento import incrementar_lote, normalizar_lote_numerico
from setores.qualidade.models import (
    LiberacaoLote,
    ObservacaoEtiqueta,
    Reuniao,
    ReuniaoParticipante,
    WMS_IntegraçãoOP,
)
from setores.qualidade.utils.rastreamento_lote import _buscar_lotes_anteriores_erp
from setores.qualidade.utils.wms_integracao import (
    chave_wms_liberacao,
    criar_pendencia_wms_ajuste_lote_original,
    criar_pendencia_wms_liberacao_lote,
    montar_sku_wms,
    remover_pendencia_wms_liberacao_lote,
)
from setores.qualidade.views.consulta_lote import (
    PROCESSAMENTO_LOTES_LOCK,
    disparar_envio_lotes,
    reservar_lotes_para_envio,
)
from setores.qualidade.views.wms_views import disparar_integracoes_wms_pendentes
from SIGMA.autorizacao import permissao_requerida
from SIGMA.integracoes.oracle import cursor_oracle_alchemy, cursor_oracle_erp

logger = logging.getLogger(__name__)


def consumir_proximo_lote_empresa(codemp):
    """Reserva o proximo lote numerico da empresa e avanca o contador com lock."""
    with transaction.atomic():
        empresa = Empresa.objects.select_for_update().get(codemp=int(codemp))
        lote = normalizar_lote_numerico(empresa.loteatual)
        empresa.loteatual = incrementar_lote(lote)
        empresa.save(update_fields=["loteatual"])
    return lote


def _validar_saldo_lote_erp(codemp, codlot, coddep, codpro, codder, quantidade_total):
    """Confere no ERP se o lote ainda tem saldo para destinar a quantidade total.

    O total destinado chega no POST e não pode ser maior que o saldo real do
    lote no depósito de origem — senão o Sapiens efetiva um movimento acima
    do disponível e a pendência ERP/WMS nasce com valor arbitrário.
    """
    if not codemp or not codlot or not coddep:
        return False, "Lote sem empresa, lote ou depósito de origem para validar o saldo."

    try:
        with cursor_oracle_erp() as cursor:
            cursor.execute(
                """
                    SELECT NVL(SUM(DLS.QTDEST), 0) AS saldo
                    FROM E210DLS DLS
                    WHERE DLS.CODEMP = :codemp
                      AND DLS.CODLOT = :codlot
                      AND DLS.CODDEP = :coddep
                      AND DLS.CODPRO = :codpro
                      AND DLS.CODDER = :codder
                """,
                {
                    "codemp": int(codemp),
                    "codlot": codlot,
                    "coddep": coddep,
                    "codpro": codpro,
                    "codder": codder,
                },
            )
            row = cursor.fetchone()
            saldo = float(row[0] or 0) if row else 0
    except Exception:
        logger.exception("Falha ao consultar saldo do lote no ERP")
        return False, "Não foi possível consultar saldo do lote no ERP."

    if saldo < float(quantidade_total):
        return False, (
            f"Saldo insuficiente no ERP para destinar {quantidade_total} KG do lote "
            f"{codlot} no depósito {coddep}. Saldo atual: {saldo:,.3f} KG."
        )

    return True, ""


# Carrega as análises do Alchemy para as bobinas exibidas na página atual.
def carregar_analises_alchemy(bobinas_pagina):
    grupos = {}
    for bobina in bobinas_pagina:
        codbobina = bobina.get("usu_numbob")
        codmaquina = bobina.get("codmaquina_alchemy")
        if codbobina and codmaquina:
            grupos.setdefault(codmaquina, set()).add(int(codbobina))

    if not grupos:
        return {}

    clausulas = []
    params = {}

    for indice_grupo, (codmaquina, codbobinas) in enumerate(grupos.items()):
        placeholders = []
        for indice_bobina, codbobina in enumerate(sorted(codbobinas)):
            nome_param = f"bob_{indice_grupo}_{indice_bobina}"
            params[nome_param] = codbobina
            placeholders.append(f":{nome_param}")

        nome_maquina = f"maq_{indice_grupo}"
        params[nome_maquina] = codmaquina
        clausulas.append(
            f"(b.codmaquina = :{nome_maquina} AND b.codbobina IN ({', '.join(placeholders)}))"
        )

    sql = f"""
        SELECT b.codmaquina, b.codbobina, b.flagproducao, b.observacao
        FROM bobinas b
        WHERE {" OR ".join(clausulas)}
    """

    analises = {}
    with cursor_oracle_alchemy() as cursor:
        cursor.execute(sql, params)
        for codmaquina, codbobina, flagproducao, observacao in cursor.fetchall():
            analises[(int(codmaquina), int(codbobina))] = {
                "flag": int(flagproducao) if flagproducao is not None else None,
                "observacao": observacao or "",
            }

    return analises


# Retorna os depósitos configurados para consulta da área vermelha da filial.
def carregar_depositos_area_vermelha(filial):
    depositos = set()
    parametros_filial = getattr(filial, "parametros_filial", None)
    deposito_filial = getattr(parametros_filial, "deposito_area_vermelha_erp", "") or ""
    if deposito_filial:
        depositos.add(deposito_filial.strip())

    depositos_recursos = (
        Recurso.objects.filter(centro_recurso__setor__departamento__filial=filial)
        .exclude(centro_recurso__parametros_centro_recurso__deposito_area_vermelha_erp__isnull=True)
        .exclude(centro_recurso__parametros_centro_recurso__deposito_area_vermelha_erp__exact="")
        .values_list(
            "centro_recurso__parametros_centro_recurso__deposito_area_vermelha_erp", flat=True
        )
    )
    for deposito in depositos_recursos:
        if deposito:
            depositos.add(str(deposito).strip())

    return sorted(depositos)


# Normaliza parâmetros separados por vírgula para comparar transações do ERP.
def separar_valores_parametro(valor):
    return [parte.strip().upper() for parte in str(valor or "").split(",") if parte.strip()]


# Alguns formatos Oracle podem voltar ":" quando a hora é nula; trata como vazio para fallback.
def valor_vazio_area_vermelha(valor):
    return str(valor or "").strip() in {"", "-", ":"}


# Descrição amigável do agrupamento de motivos (USU_ATRCCU do ERP).
DESCRICOES_GRUPO_MOTIVO_AREA_VERMELHA = {
    "OF": "OP de Fabricação",
    "OC": "OP de Consumo",
    "CF": "Centro de Custo fixo",
}


# Carrega do ERP os motivos ativos permitidos para área vermelha.
def carregar_motivos_area_vermelha(codemp):
    if not codemp:
        return []

    with cursor_oracle_erp() as cursor:
        cursor.execute(
            """
                SELECT coddft, desdft, usu_atrccu
                FROM e011def
                WHERE codemp = :codemp
                  AND usu_utiave = 'S'
                  AND sitdft = 'A'
                ORDER BY usu_atrccu NULLS LAST, coddft
            """,
            {"codemp": int(codemp)},
        )
        colunas = [coluna[0].lower() for coluna in cursor.description]
        motivos = []
        for row in (dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()):
            codigo_grupo = str(row["usu_atrccu"] or "").strip()
            grupo = DESCRICOES_GRUPO_MOTIVO_AREA_VERMELHA.get(
                codigo_grupo, codigo_grupo or "Sem categoria"
            )
            motivos.append({"coddft": row["coddft"], "desdft": row["desdft"], "grupo": grupo})
        return motivos


# Monta SQL literal para DBLINK; binds nessa consulta ficaram mais lentos no Oracle.
def sql_literal_com_parametros(sql, params):
    debug_sql = sql
    for chave, valor in sorted(params.items(), key=lambda item: len(item[0]), reverse=True):
        valor_sql = str(valor).replace("'", "''")
        debug_sql = debug_sql.replace(f":{chave}", f"'{valor_sql}'")
    return debug_sql


# Consulta o local WMS por par exato SKU + lote, evitando pegar local de outro lote.
def consultar_locais_wms_lotes(bobinas):
    pares = {}
    for bobina in bobinas:
        sku = montar_sku_wms(bobina.get("codpro"), bobina.get("codder"))
        lote = str(bobina.get("codlot") or "").strip()
        if sku and lote:
            pares[(sku, lote)] = None

    if not pares:
        return {}

    consultas = []
    params = {}
    for indice, (sku, lote) in enumerate(pares):
        sku_param = f"sku_{indice}"
        lote_param = f"lote_{indice}"
        params[sku_param] = sku
        params[lote_param] = lote
        consultas.append(
            f"""
            SELECT e.SKU, e.LOTTABLE01, e.LOC AS Endereco
              FROM wmwhse1.v_XCLotxLocxId_Lottables@SQLDBLINK e
             WHERE e.SKU = :{sku_param}
               AND e.LOTTABLE01 = :{lote_param}
            """
        )

    sql = "\nUNION ALL\n".join(consultas)
    print("[AreaVermelha] Consulta locais WMS DBLINK:")
    # O DBLINK falha no driver Python com filtro OR/IN composto; UNION ALL mantém uma execução e evita ORA-01002.
    sql_literal = sql_literal_com_parametros(sql, params)
    print(sql_literal)

    ultimo_erro = None
    for tentativa in range(1, 3):
        try:
            with cursor_oracle_erp() as cursor:
                cursor.arraysize = 1
                if hasattr(cursor, "prefetchrows"):
                    cursor.prefetchrows = 1
                cursor.execute(sql_literal)
                locais = {}
                for sku, lote, local in cursor:
                    chave = (str(sku or "").strip(), str(lote or "").strip())
                    if chave not in locais:
                        locais[chave] = str(local or "").strip()
            return locais
        except Exception as exc:
            ultimo_erro = exc
            logger.warning("Falha no DBLINK WMS na tentativa %s", tentativa, exc_info=True)
            # ORA-01002 em DBLINK costuma ficar preso na sessão; reabrir conexão limpa o cursor remoto.
            connections["oracle_erp"].close()

    raise ultimo_erro


# Carrega fallback de local WMS quando o lote ainda não existe: recurso primeiro, filial depois.
def carregar_locais_area_vermelha_parametrizados(bobinas, filial):
    parametros_filial = getattr(filial, "parametros_filial", None)
    local_filial = str(getattr(parametros_filial, "deposito_area_vermelha_wms", "") or "").strip()
    codigos = {
        str(bobina.get("codcre") or "").strip()
        for bobina in bobinas
        if str(bobina.get("codcre") or "").strip()
    }
    locais = {}

    if not filial or not codigos:
        return locais, local_filial

    recursos = Recurso.objects.filter(
        centro_recurso__setor__departamento__filial=filial,
        centro_recurso__codigo_integrador__in=codigos,
    ).select_related(
        "parametros_recurso",
        "centro_recurso__parametros_centro_recurso",
        "centro_recurso__setor__departamento__filial__parametros_filial",
        "centro_recurso__setor__departamento__filial__empresa",
    )
    for recurso in recursos:
        codemp = recurso.centro_recurso.setor.departamento.filial.empresa.codemp
        codigo = str(recurso.centro_recurso.codigo_integrador or "").strip()
        locais[(str(codemp), codigo)] = str(
            recurso.get_parametros_efetivos().get("deposito_area_vermelha_wms") or ""
        ).strip()

    return locais, local_filial


# Resolve local e origem no salvamento; não confia no hidden enviado pelo navegador.
def resolver_local_wms_area_vermelha(bobina, filial):
    sku = montar_sku_wms(bobina.get("codpro"), bobina.get("codder"))
    lote = str(bobina.get("codlot") or "").strip()
    try:
        locais_wms = consultar_locais_wms_lotes([bobina])
        local_wms = locais_wms.get((sku, lote))
    except Exception:
        logger.exception("Falha ao resolver local WMS no salvamento")
        local_wms = ""

    if local_wms:
        return local_wms, "wms"

    locais_parametrizados, local_filial_wms = carregar_locais_area_vermelha_parametrizados(
        [bobina], filial
    )
    chave_recurso = (
        str(bobina.get("codemp") or ""),
        str(bobina.get("codcre") or "").strip(),
    )
    return locais_parametrizados.get(chave_recurso) or local_filial_wms or "", "padrao"


# Busca origem/OP/recurso pelo movimento real do lote para a tela da área vermelha.
def buscar_referencia_movimento_lote_area_vermelha(codemp, codlot, transacoes_recurso):
    lotes_anteriores = _buscar_lotes_anteriores_erp(codemp, codlot)

    with cursor_oracle_erp() as cursor:
        cursor.execute(
            """
                SELECT DISTINCT MVP.USU_CODLIG
                FROM E210MVP MVP
                WHERE MVP.CODEMP = :codemp
                  AND MVP.CODLOT = :codlot
                  AND NVL(MVP.USU_CODLIG, 0) <> 0
            """,
            {"codemp": codemp, "codlot": codlot},
        )
        codigos_ligacao = [row[0] for row in cursor.fetchall() if row[0]]
        campo_ligacao = "MVP.USU_CODLIG"
        if not codigos_ligacao:
            cursor.execute(
                """
                    SELECT DISTINCT MVP.CODLIG
                    FROM E210MVP MVP
                    WHERE MVP.CODEMP = :codemp
                      AND MVP.CODLOT = :codlot
                      AND NVL(MVP.CODLIG, 0) <> 0
                """,
                {"codemp": codemp, "codlot": codlot},
            )
            codigos_ligacao = [row[0] for row in cursor.fetchall() if row[0]]
            campo_ligacao = "MVP.CODLIG"

        params = {"codemp": codemp, "codlot": codlot}
        placeholders_lotes_anteriores = []
        for indice, lote in enumerate(lotes_anteriores):
            nome_param = f"lote_anterior_{indice}"
            params[nome_param] = lote
            placeholders_lotes_anteriores.append(f":{nome_param}")

        filtro_ligacao = ""
        if codigos_ligacao:
            placeholders = []
            for indice, codigo in enumerate(codigos_ligacao):
                nome_param = f"codlig_{indice}"
                params[nome_param] = codigo
                placeholders.append(f":{nome_param}")
            filtro_ligacao = f" OR {campo_ligacao} IN ({', '.join(placeholders)})"

        filtro_lotes_anteriores = ""
        if placeholders_lotes_anteriores:
            filtro_lotes_anteriores = (
                f" OR MVP.CODLOT IN ({', '.join(placeholders_lotes_anteriores)})"
            )

        cursor.execute(
            f"""
                SELECT
                    MVP.DATDIG,
                    MVP.HORDIG,
                    MVP.CODTNS,
                    MVP.CODLOT,
                    MVP.ORIORP,
                    MVP.NUMDOC,
                    MVP.SEQMOV,
                    {campo_ligacao} AS CODIGO_LIGACAO
                FROM E210MVP MVP
                WHERE MVP.CODEMP = :codemp
                  AND (MVP.CODLOT = :codlot{filtro_lotes_anteriores}{filtro_ligacao})
                ORDER BY MVP.DATDIG, MVP.HORDIG, MVP.SEQMOV
            """,
            params,
        )
        movimentos = list(cursor.fetchall())

        limites_lotes_anteriores = {}
        lote_sucessor = codlot
        for lote_anterior in lotes_anteriores:
            movimentos_sucessor = [row for row in movimentos if row[3] == lote_sucessor]
            if movimentos_sucessor:
                limites_lotes_anteriores[lote_anterior] = min(
                    (row[0], row[1] or 0, row[6] or 0) for row in movimentos_sucessor
                )
            lote_sucessor = lote_anterior

        codigos_ligacao = set(codigos_ligacao)
        movimentos = [
            row
            for row in movimentos
            if (
                row[3] == codlot
                or row[7] in codigos_ligacao
                or (
                    row[3] in limites_lotes_anteriores
                    and (row[0], row[1] or 0, row[6] or 0) < limites_lotes_anteriores[row[3]]
                )
            )
        ]

        # Para lote transformado, o movimento de recurso pode estar no lote anterior ligado por USU_CODLIG.
        # Por isso a referência de recurso é buscada em toda a cadeia rastreada, não só no lote atual.
        movimentos_recurso = (
            [row for row in movimentos if str(row[2] or "").strip().upper() in transacoes_recurso]
            if transacoes_recurso
            else []
        )
        if movimentos_recurso:
            movimento_recurso = movimentos_recurso[-1]
        else:
            movimentos_lote_atual = [row for row in movimentos if row[3] == codlot]
            if len(movimentos_lote_atual) >= 2:
                movimento_recurso = movimentos_lote_atual[-2]
            else:
                movimentos_anteriores = [row for row in movimentos if row[3] != codlot]
                if not movimentos_anteriores:
                    return None
                movimento_recurso = movimentos_anteriores[-1]

        codori_referencia = movimento_recurso[4]
        numorp_referencia = movimento_recurso[5]
        lote_referencia = movimento_recurso[3]
        if not codori_referencia or not numorp_referencia:
            return None

        cursor.execute(
            """
                SELECT
                    CODCRE,
                    ABRCRE,
                    DESCRE,
                    DATREA,
                    HORREA
                FROM (
                    SELECT
                        EOQ.CODCRE,
                        CRE.ABRCRE,
                        CRE.DESCRE,
                        TO_CHAR(EOQ.DATREA, 'DD/MM/YYYY') AS DATREA,
                        CASE
                            WHEN EOQ.HORREA IS NULL THEN NULL
                            ELSE LPAD(TRUNC(EOQ.HORREA / 60), 2, '0') || ':' ||
                                 LPAD(MOD(EOQ.HORREA, 60), 2, '0')
                        END AS HORREA
                    FROM E900EOQ EOQ
                    LEFT JOIN E725CRE CRE
                      ON CRE.CODEMP = EOQ.CODEMP
                     AND CRE.CODCRE = EOQ.CODCRE
                    WHERE EOQ.CODEMP = :codemp
                      AND EOQ.CODORI = :codori
                      AND EOQ.NUMORP = :numorp
                      AND EOQ.CODLOT = :codlot_referencia
                    ORDER BY EOQ.DATREA DESC, EOQ.HORREA DESC, EOQ.SEQEOQ DESC
                )
                WHERE ROWNUM = 1
            """,
            {
                "codemp": codemp,
                "codori": codori_referencia,
                "numorp": numorp_referencia,
                "codlot_referencia": lote_referencia,
            },
        )
        recurso_row = cursor.fetchone()
        if not recurso_row:
            cursor.execute(
                """
                    SELECT
                        EOQ.CODCRE,
                        CRE.ABRCRE,
                        CRE.DESCRE,
                        TO_CHAR(EOQ.DATREA, 'DD/MM/YYYY') AS DATREA,
                        CASE
                            WHEN EOQ.HORREA IS NULL THEN NULL
                            ELSE LPAD(TRUNC(EOQ.HORREA / 60), 2, '0') || ':' ||
                                 LPAD(MOD(EOQ.HORREA, 60), 2, '0')
                        END AS HORREA
                    FROM E900EOQ EOQ
                    LEFT JOIN E725CRE CRE
                      ON CRE.CODEMP = EOQ.CODEMP
                     AND CRE.CODCRE = EOQ.CODCRE
                    WHERE EOQ.CODEMP = :codemp
                      AND EOQ.CODORI = :codori
                      AND EOQ.NUMORP = :numorp
                      AND EOQ.SEQEOQ = (
                          SELECT MIN(EOQ2.SEQEOQ)
                          FROM E900EOQ EOQ2
                          WHERE EOQ2.CODEMP = EOQ.CODEMP
                            AND EOQ2.CODORI = EOQ.CODORI
                            AND EOQ2.NUMORP = EOQ.NUMORP
                            AND EOQ2.CODCRE IS NOT NULL
                      )
                """,
                {"codemp": codemp, "codori": codori_referencia, "numorp": numorp_referencia},
            )
            recurso_row = cursor.fetchone()

    return {
        "codori": codori_referencia,
        "numorp": numorp_referencia,
        "codcre": recurso_row[0] if recurso_row else None,
        "abrcre": recurso_row[1] if recurso_row else None,
        "descre": recurso_row[2] if recurso_row else None,
        "datrea": recurso_row[3] if recurso_row else None,
        "horrea": recurso_row[4] if recurso_row else None,
    }


# Busca a descrição do produto/derivação no ERP para auxiliar a reclassificação.
@permissao_requerida("qualidade.pode_acessar_area_vermelha")
def buscar_descricao_transformacao(request):
    produto = (request.GET.get("produto") or "").strip()
    filial = getattr(request.user, "filial", None)
    empresa = getattr(filial, "empresa", None)
    codemp = getattr(empresa, "codemp", None)

    if not codemp:
        return JsonResponse({"error": "Usuário sem empresa vinculada."}, status=400)
    if not produto:
        return JsonResponse({"resultados": []})

    try:
        with cursor_oracle_erp() as cursor:
            cursor.execute(
                """
                    SELECT codpro, codder, descricao
                    FROM (
                        SELECT
                            p.codpro,
                            NVL(d.codder, '') AS codder,
                            p.despro || CASE
                                WHEN d.codder IS NOT NULL THEN ' - ' || d.desder
                                ELSE ''
                            END AS descricao
                        FROM e075pro p
                        LEFT JOIN e075der d
                          ON d.codemp = p.codemp
                         AND d.codpro = p.codpro
                        WHERE p.codemp = :codemp
                          AND p.usu_conrel = 'S'
                          AND (
                                UPPER(p.codpro) LIKE :produto
                             OR UPPER(p.despro) LIKE :produto
                          )
                        ORDER BY p.codpro, d.codder
                    )
                    WHERE ROWNUM <= 20
                """,
                {
                    "codemp": int(codemp),
                    "produto": f"%{produto.upper()}%",
                },
            )
            colunas = [coluna[0].lower() for coluna in cursor.description]
            rows = [dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()]
    except Exception:
        logger.exception("Falha ao buscar descrição de transformação no ERP")
        return JsonResponse({"error": "Não foi possível concluir a consulta."}, status=500)

    return JsonResponse(
        {
            "resultados": [
                {
                    "codpro": row["codpro"],
                    "codder": row["codder"] or "",
                    "descricao": row["descricao"],
                }
                for row in rows
            ]
        }
    )


# Lista usuários ERP por nome para registrar participantes da reunião.
@permissao_requerida("qualidade.pode_destinar_area_vermelha")
def buscar_usuarios_erp(request):
    termo = (request.GET.get("q") or "").strip()
    if len(termo) < 3:
        return JsonResponse({"resultados": []})

    # Achado de segurança: a busca expunha o quadro inteiro de usuários do ERP,
    # de todas as empresas, a qualquer um com permissão de destinar. Agora o
    # não-staff só recebe usuários da própria empresa (NUMEMP); staff mantém a
    # visão completa (mesma regra de filial usada nas demais views da app).
    filial_logada = getattr(request.user, "filial", None)
    empresa_logada = getattr(filial_logada, "empresa", None)
    codemp_usuario = getattr(empresa_logada, "codemp", None)

    try:
        with cursor_oracle_erp() as cursor:
            if request.user.is_staff:
                cursor.execute(
                    """
                        SELECT codusu, nomusu
                        FROM (
                            SELECT codusu, nomusu
                            FROM r999usu
                            WHERE UPPER(nomusu) LIKE :termo
                               OR TO_CHAR(codusu) LIKE :termo_codigo
                            ORDER BY nomusu
                        )
                        WHERE ROWNUM <= 20
                    """,
                    {
                        "termo": f"%{termo.upper()}%",
                        "termo_codigo": f"%{termo}%",
                    },
                )
            else:
                cursor.execute(
                    """
                        SELECT codusu, nomusu
                        FROM (
                            SELECT codusu, nomusu
                            FROM r999usu
                            WHERE numemp = :codemp
                              AND (UPPER(nomusu) LIKE :termo
                                   OR TO_CHAR(codusu) LIKE :termo_codigo)
                            ORDER BY nomusu
                        )
                        WHERE ROWNUM <= 20
                    """,
                    {
                        "codemp": str(codemp_usuario),
                        "termo": f"%{termo.upper()}%",
                        "termo_codigo": f"%{termo}%",
                    },
                )
            colunas = [coluna[0].lower() for coluna in cursor.description]
            rows = [dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()]
    except Exception:
        logger.exception("Falha ao buscar usuários no ERP")
        return JsonResponse({"error": "Não foi possível concluir a consulta."}, status=500)

    return JsonResponse(
        {"resultados": [{"codusu": row["codusu"], "nomusu": row["nomusu"]} for row in rows]}
    )


# Controla a reunião da área vermelha e registra as destinações por linha.
@permissao_requerida("qualidade.pode_acessar_area_vermelha")
def liberar_area_vermelha(request):
    # Estado base da tela: filtros, linha selecionada e parâmetros efetivos da filial logada.
    search_query = (request.GET.get("search") or "").strip()
    selected_row = {
        "codemp": "",
        "usu_numbob": "",
        "codlot": "",
        "coddep": "",
        "codpro": "",
        "codder": "",
        "codcre": "",
        "codori": "",
        "local": "",
        "local_origem": "",
        "origem_produto": "",
        "numorp": "",
        "qtdest": "",
    }
    filial_logada = getattr(request.user, "filial", None)
    empresa_logada = getattr(filial_logada, "empresa", None)
    parametros_filial_logada = getattr(filial_logada, "parametros_filial", None)
    codemp_usuario = getattr(empresa_logada, "codemp", None)
    depositos_consulta = carregar_depositos_area_vermelha(filial_logada) if filial_logada else []
    origens_area_vermelha = separar_valores_parametro(
        getattr(parametros_filial_logada, "origens_area_vermelha", "")
    )
    codtns_area_vermelha = str(getattr(parametros_filial_logada, "codtns_area_vermelha", "") or "")
    pode_destinar_area_vermelha = request.user.is_staff or request.user.has_perm(
        "qualidade.pode_destinar_area_vermelha"
    )

    if request.method == "POST":
        # Todas as ações POST desta tela são operações da reunião aberta.
        reuniao_action = request.POST.get("reuniao_action")
        if reuniao_action:
            if not pode_destinar_area_vermelha:
                messages.error(
                    request, "Você não tem permissão para destinar lotes na área vermelha."
                )
                return redirect("qualidade:area_vermelha")

            reuniao_aberta = (
                Reuniao.objects.filter(data_hora_fim__isnull=True)
                .order_by("-data_hora_inicio")
                .first()
            )

            if reuniao_action == "abrir":
                # A reunião aberta é o bloqueio lógico: WMS só envia depois do fechamento.
                if Reuniao.objects.filter(data_hora_fim__isnull=True).exists():
                    messages.warning(request, "Já existe uma reunião aberta.")
                else:
                    Reuniao.objects.create(data_hora_inicio=timezone.now())
                    messages.success(request, "Reunião aberta.")
            elif reuniao_action == "fechar":
                # Fechar a reunião libera os registros locais para os envios ERP e WMS em background.
                if not reuniao_aberta:
                    messages.warning(request, "Não existe reunião aberta para fechar.")
                else:
                    sem_registros = not reuniao_aberta.liberacoes_lote.exists()
                    sem_participantes = not reuniao_aberta.participantes.exists()
                    if sem_registros:
                        reuniao_aberta.delete()
                        messages.success(request, "Reunião sem registros excluída.")
                    elif sem_participantes:
                        messages.warning(
                            request, "Informe ao menos um participante antes de fechar a reunião."
                        )
                    else:
                        data_fechamento = timezone.now()
                        reuniao_aberta.data_hora_fim = data_fechamento
                        reuniao_aberta.save(update_fields=["data_hora_fim"])
                        reuniao_aberta.liberacoes_lote.filter(datger__isnull=True).update(
                            datger=data_fechamento
                        )
                        messages.success(request, "Reunião fechada.")

                        if PROCESSAMENTO_LOTES_LOCK.locked():
                            messages.warning(
                                request,
                                "Já existe um processamento de lotes em background em andamento.",
                            )
                        else:
                            pendentes = (
                                LiberacaoLote.objects.filter(
                                    status=LiberacaoLote.Status.NAO_INTEGRADO,
                                )
                                .filter(
                                    Q(reuniao__isnull=True)
                                    | Q(reuniao__data_hora_fim__isnull=False)
                                )
                                .order_by("id")
                            )
                            if not request.user.is_staff and codemp_usuario:
                                pendentes = pendentes.filter(codemp=codemp_usuario)
                            elif not request.user.is_staff:
                                pendentes = pendentes.none()

                            reservados_ids = reservar_lotes_para_envio(pendentes)
                            if reservados_ids:
                                disparar_envio_lotes(reservados_ids)
                                messages.info(
                                    request,
                                    "Processamento em background iniciado para envio dos lotes pendentes.",
                                )
                            else:
                                messages.info(request, "Não há lotes pendentes para enviar.")

                        disparar_integracoes_wms_pendentes()
            elif reuniao_action == "adicionar_participante":
                # Participantes são obrigatórios antes de fechar reunião com registros.
                nome = (request.POST.get("nome") or "").strip()
                setor = (request.POST.get("setor") or "").strip()
                if not reuniao_aberta:
                    messages.warning(request, "Abra uma reunião antes de adicionar participantes.")
                elif not nome:
                    messages.warning(request, "Selecione o participante.")
                elif setor not in dict(ReuniaoParticipante.Setor.choices):
                    messages.warning(request, "Selecione o setor do participante.")
                else:
                    nome = " ".join(nome.split())
                    ReuniaoParticipante.objects.create(
                        reuniao=reuniao_aberta, nome=nome, setor=setor
                    )
                    messages.success(request, "Participante adicionado.")
            elif reuniao_action == "excluir_participante":
                participante_id = request.POST.get("participante_id")
                if not reuniao_aberta:
                    messages.warning(request, "Não existe reunião aberta.")
                else:
                    excluidos, _ = ReuniaoParticipante.objects.filter(
                        id=participante_id,
                        reuniao=reuniao_aberta,
                    ).delete()
                    if excluidos:
                        messages.success(request, "Participante excluído.")
                    else:
                        messages.warning(request, "Participante não encontrado.")
            elif reuniao_action == "excluir_destinacao_lote":
                # Excluir destinação remove também a pendência WMS ainda não enviada.
                if not reuniao_aberta:
                    messages.warning(request, "Não existe reunião aberta.")
                else:
                    try:
                        codemp = int(request.POST.get("codemp"))
                    except TypeError, ValueError:
                        messages.error(request, "Dados inválidos para excluir a destinação.")
                    else:
                        # Achado de segurança: `codemp` vinha só do POST, sem
                        # comparação com a empresa real do usuário — um não-staff
                        # conseguia excluir (e desfazer a pendência WMS de)
                        # destinação de outra filial só forjando o campo. Mesma
                        # regra já usada no fechamento de reunião desta view:
                        # staff sem restrição, não-staff só na própria empresa.
                        if not request.user.is_staff and codemp != codemp_usuario:
                            messages.error(
                                request,
                                "Você não tem permissão para excluir destinação de outra empresa.",
                            )
                        else:
                            registros_excluir = LiberacaoLote.objects.filter(
                                reuniao=reuniao_aberta,
                                codemp=codemp,
                                codlot=request.POST.get("codlot", ""),
                                codpro=request.POST.get("codpro", ""),
                                codder=request.POST.get("codder", ""),
                                status__in=[
                                    LiberacaoLote.Status.NAO_INTEGRADO,
                                    LiberacaoLote.Status.LOCAL,
                                ],
                            )
                            for registro in registros_excluir:
                                remover_pendencia_wms_liberacao_lote(registro)
                            excluidos, _ = registros_excluir.delete()
                            if excluidos:
                                messages.success(request, "Destinação excluída.")
                            else:
                                messages.warning(
                                    request, "Destinação não encontrada ou já integrada."
                                )
            elif reuniao_action == "registrar_liberacao_lote":
                # Registra uma avaliação da bobina, podendo dividir a quantidade entre destinos.
                if not reuniao_aberta:
                    messages.warning(request, "Abra uma reunião antes de registrar avaliações.")
                else:
                    try:
                        qtdtot = Decimal((request.POST.get("qtdtot") or "0").replace(",", "."))
                        codemp = int(request.POST.get("codemp"))
                        numbob = (
                            int(request.POST.get("numbob"))
                            if request.POST.get("numbob") not in (None, "")
                            else None
                        )
                        codigo_integrador = (request.POST.get("codigo_integrador") or "").strip()
                        codori = (request.POST.get("codori") or "").strip()
                        origem_produto = (request.POST.get("origem_produto") or "").strip()
                        numorp = (
                            int(request.POST.get("numorp"))
                            if request.POST.get("numorp") not in (None, "")
                            else None
                        )
                        destinos = request.POST.getlist("destino")
                        quantidades = [
                            Decimal((valor or "0").replace(",", "."))
                            for valor in request.POST.getlist("quantidade")
                        ]
                        codpro_recls = request.POST.getlist("codpro_recl")
                        codder_recls = request.POST.getlist("codder_recl")
                        coddfts = request.POST.getlist("coddft")
                        etiquetas_ids = request.POST.getlist("id_etiqueta")
                        observacoes_gerais = request.POST.getlist("observacao_geral")
                        total_destinado = sum(quantidades, Decimal("0"))
                    except InvalidOperation, TypeError, ValueError:
                        messages.error(
                            request, "Dados inválidos para registrar a avaliação da bobina."
                        )
                    else:
                        if codemp <= 0:
                            messages.error(request, "Empresa inválida para registrar a avaliação.")
                        # Achado de segurança: sem esta checagem, `codemp` do POST
                        # sobrescrevia a empresa real e permitia registrar avaliação
                        # (e gerar pendência ERP/WMS) em nome de outra filial. Mesma
                        # regra de staff/não-staff usada no fechamento de reunião e
                        # na exclusão de destinação desta view.
                        elif not request.user.is_staff and codemp != codemp_usuario:
                            messages.error(
                                request,
                                "Você não tem permissão para registrar avaliação de outra empresa.",
                            )
                        elif qtdtot <= 0:
                            messages.error(
                                request, "Quantidade total inválida para registrar a avaliação."
                            )
                        elif not destinos or len(destinos) != len(quantidades):
                            messages.error(
                                request, "Informe ao menos uma linha de destinação válida."
                            )
                        elif len(destinos) != len(set(destinos)):
                            messages.error(
                                request, "Cada destino pode ser informado no máximo uma vez."
                            )
                        elif total_destinado <= 0:
                            messages.error(
                                request, "Informe ao menos uma quantidade para registrar."
                            )
                        elif total_destinado != qtdtot:
                            messages.error(
                                request, "A soma das quantidades deve ser igual à quantidade total."
                            )
                        # A empresa do POST já foi autorizada; só então a consulta ao ERP é permitida.
                        # A quantidade destinada precisa respeitar o saldo real do lote para não gerar
                        # pendência ERP/WMS com total arbitrário.
                        elif not (
                            resultado_saldo := _validar_saldo_lote_erp(
                                codemp,
                                request.POST.get("codlot", ""),
                                request.POST.get("coddep", ""),
                                request.POST.get("codpro", ""),
                                request.POST.get("codder", ""),
                                qtdtot,
                            )
                        )[0]:
                            messages.error(request, resultado_saldo[1])
                        elif not origens_area_vermelha:
                            messages.error(
                                request,
                                "Configure as origens permitidas para área vermelha na filial.",
                            )
                        elif not codtns_area_vermelha:
                            messages.error(
                                request,
                                "Configure a Transação do ERP Saída Área Vermelha na filial.",
                            )
                        elif origem_produto.upper() not in origens_area_vermelha:
                            messages.error(
                                request, "Origem não permitida para destinação na área vermelha."
                            )
                        elif LiberacaoLote.objects.filter(
                            codemp=codemp,
                            codlot=request.POST.get("codlot", ""),
                            codpro=request.POST.get("codpro", ""),
                            codder=request.POST.get("codder", ""),
                        ).exists():
                            messages.error(
                                request, "Este lote/bobina já foi destinado em uma reunião."
                            )
                        else:
                            # Valida cada linha do formulário dinâmico antes de salvar qualquer registro.
                            linhas_invalidas = False
                            for indice, destino in enumerate(destinos):
                                quantidade = quantidades[indice]
                                codpro_recl = (
                                    codpro_recls[indice] if indice < len(codpro_recls) else ""
                                ).strip()
                                coddft = coddfts[indice] if indice < len(coddfts) else ""
                                observacao_etiqueta_id = (
                                    etiquetas_ids[indice] if indice < len(etiquetas_ids) else ""
                                )
                                if (
                                    destino
                                    not in ("liberar", "refugar", "reclassificar", "para_prensa")
                                    or quantidade <= 0
                                ):
                                    linhas_invalidas = True
                                    break
                                if not coddft or not observacao_etiqueta_id:
                                    linhas_invalidas = True
                                    break
                                if destino == "reclassificar" and not codpro_recl:
                                    linhas_invalidas = True
                                    break

                            if linhas_invalidas:
                                messages.error(
                                    request, "Revise as linhas de destinação antes de salvar."
                                )
                                return redirect("qualidade:area_vermelha")

                            observacoes_por_id = {
                                str(observacao.id): observacao
                                for observacao in ObservacaoEtiqueta.objects.filter(
                                    id__in=[valor for valor in etiquetas_ids if valor],
                                    ativo=True,
                                )
                            }
                            if len(observacoes_por_id) != len(
                                set(valor for valor in etiquetas_ids if valor)
                            ):
                                messages.error(
                                    request, "Selecione apenas observações de etiqueta ativas."
                                )
                                return redirect("qualidade:area_vermelha")

                            # Produto de refugo vem do recurso; se vazio, usa o parâmetro da filial.
                            recurso_refugo = (
                                Recurso.objects.select_related(
                                    "parametros_recurso",
                                    "centro_recurso__parametros_centro_recurso",
                                    "centro_recurso__setor__departamento__filial__parametros_filial",
                                )
                                .filter(
                                    centro_recurso__codigo_integrador=codigo_integrador,
                                    centro_recurso__setor__departamento__filial__empresa__codemp=codemp,
                                )
                                .first()
                            )
                            parametros_recurso = (
                                recurso_refugo.get_parametros_efetivos() if recurso_refugo else {}
                            )
                            produto_refugo = str(parametros_recurso.get("produto_refugo", "") or "")
                            if produto_refugo:
                                derivacao_refugo = (
                                    ""
                                    if parametros_recurso.get("derivacao_refugo") is None
                                    else str(parametros_recurso.get("derivacao_refugo", ""))
                                )
                            else:
                                filial_refugo = (
                                    recurso_refugo.centro_recurso.setor.departamento.filial
                                    if recurso_refugo
                                    else getattr(request.user, "filial", None)
                                )
                                parametros_filial = getattr(
                                    filial_refugo, "parametros_filial", None
                                )
                                produto_refugo = str(
                                    getattr(parametros_filial, "produto_refugo", "") or ""
                                )
                                derivacao_refugo = (
                                    ""
                                    if getattr(parametros_filial, "derivacao_refugo", None) is None
                                    else str(getattr(parametros_filial, "derivacao_refugo", ""))
                                )

                            if (
                                "refugar" in destinos or "para_prensa" in destinos
                            ) and not produto_refugo:
                                messages.error(
                                    request,
                                    "Produto de refugo não configurado no recurso ou na filial.",
                                )
                                return redirect("qualidade:area_vermelha")

                            # Define se o lote já existe no WMS; isso decide Ajuste x Novo lote.
                            local_wms_registro, local_origem_wms = resolver_local_wms_area_vermelha(
                                {
                                    "codemp": codemp,
                                    "codpro": request.POST.get("codpro", ""),
                                    "codder": request.POST.get("codder", ""),
                                    "codlot": request.POST.get("codlot", ""),
                                    "codcre": codigo_integrador,
                                },
                                getattr(request.user, "filial", None),
                            )
                            if not local_wms_registro:
                                messages.error(
                                    request,
                                    "Local WMS não definido. Configure o local no recurso ou na filial.",
                                )
                                return redirect("qualidade:area_vermelha")

                            dados_base = {
                                # Campos comuns a todas as linhas geradas para esta bobina.
                                "codemp": codemp,
                                "numbob": numbob,
                                "codpro": request.POST.get("codpro", ""),
                                "codder": request.POST.get("codder", ""),
                                "coddep": request.POST.get("coddep", ""),
                                "deptrf": request.POST.get("coddep", ""),
                                "codtns": codtns_area_vermelha,
                                "codigo_integrador": codigo_integrador,
                                "codori": codori,
                                "numorp": numorp,
                                "qtdtot": float(qtdtot),
                                "usuario": request.user,
                                "reuniao": reuniao_aberta,
                                "status": LiberacaoLote.Status.NAO_INTEGRADO,
                            }
                            criados = 0
                            codlot_base = request.POST.get("codlot", "")
                            for indice, destino in enumerate(destinos):
                                # Cada destino vira uma linha própria para manter ERP/WMS rastreáveis.
                                quantidade = quantidades[indice]
                                valores = {
                                    "codlot": codlot_base,
                                    "lottrf": codlot_base,
                                    "qtdlibe": 0,
                                    "qtdaverm": 0,
                                    "qtdrefu": 0,
                                    "qtdrecl": 0,
                                    "qtdprensa": 0,
                                    "coddft": coddfts[indice] if indice < len(coddfts) else "",
                                    "etiqueta": observacoes_por_id.get(
                                        etiquetas_ids[indice] if indice < len(etiquetas_ids) else ""
                                    ),
                                    "observacao_geral": (
                                        observacoes_gerais[indice]
                                        if indice < len(observacoes_gerais)
                                        else ""
                                    ).strip(),
                                }
                                if destino == "liberar":
                                    valores["qtdlibe"] = float(quantidade)
                                elif destino == "refugar":
                                    valores["lottrf"] = consumir_proximo_lote_empresa(codemp)
                                    valores["qtdrefu"] = float(quantidade)
                                    valores["codpro_recl"] = produto_refugo
                                    valores["codder_recl"] = derivacao_refugo
                                elif destino == "reclassificar":
                                    valores["lottrf"] = consumir_proximo_lote_empresa(codemp)
                                    valores["qtdrecl"] = float(quantidade)
                                    valores["codpro_recl"] = (
                                        codpro_recls[indice] if indice < len(codpro_recls) else ""
                                    ).strip()
                                    valores["codder_recl"] = (
                                        codder_recls[indice] if indice < len(codder_recls) else ""
                                    )
                                elif destino == "para_prensa":
                                    # Mesmo lote de origem: a prensa gera lote e integrações próprias fora do SIGMA.
                                    valores["qtdprensa"] = float(quantidade)
                                    valores["codpro_recl"] = produto_refugo
                                    valores["codder_recl"] = derivacao_refugo
                                valores["log"] = "Inserido Registro"
                                dados_registro = {**dados_base, **valores}
                                if destino == "para_prensa":
                                    dados_registro["status"] = LiberacaoLote.Status.LOCAL
                                registro = LiberacaoLote.objects.create(**dados_registro)
                                if destino == "para_prensa":
                                    # Registro só de log local: nunca integra com ERP nem WMS.
                                    criados += 1
                                    continue
                                # Se já existe no WMS, liberar saldo do lote original é ajuste; novos destinos criam lote.
                                if local_origem_wms == "wms" and destino == "liberar":
                                    criar_pendencia_wms_liberacao_lote(
                                        registro,
                                        local=local_wms_registro,
                                        tipo_envio=WMS_IntegraçãoOP.TIPO_AJUSTE,
                                    )
                                else:
                                    criar_pendencia_wms_liberacao_lote(
                                        registro,
                                        local=local_wms_registro,
                                        tipo_envio=WMS_IntegraçãoOP.TIPO_NOVO_LOTE,
                                    )
                                criados += 1

                            if (
                                local_origem_wms == "wms"
                                and "liberar" not in destinos
                                and any(
                                    destino in ("refugar", "reclassificar") for destino in destinos
                                )
                            ):
                                # Sem linha de liberar, cria ajuste zero para o lote original aparecer na fila WMS.
                                registro_referencia = (
                                    LiberacaoLote.objects.filter(
                                        reuniao=reuniao_aberta,
                                        codemp=codemp,
                                        codlot=codlot_base,
                                        codpro=request.POST.get("codpro", ""),
                                        codder=request.POST.get("codder", ""),
                                    )
                                    .order_by("-id")
                                    .first()
                                )
                                if registro_referencia:
                                    criar_pendencia_wms_ajuste_lote_original(
                                        registro_referencia, local=local_wms_registro
                                    )

                            messages.success(request, f"{criados} registro(s) salvo(s) na reunião.")

            return redirect("qualidade:area_vermelha")

        messages.warning(request, "Ação inválida.")
        return redirect("qualidade:area_vermelha")

    # Consulta principal do ERP: traz todos os lotes elegíveis e pagina no Django.
    sql = """
        SELECT
            DLS.CODEMP,
            MAX(NULLIF(EOQ.USU_NUMBOB, 0)) AS USU_NUMBOB,
            MAX(EOQ.NUMORP) AS NUMORP,
            MAX(EOQ.CODORI) AS CODORI,
            DLS.CODLOT,
            DLS.USU_SITLOT AS SITLOT,
            DLS.CODDEP,
            DLS.CODPRO,
            DLS.CODDER,
            PRO.DESPRO,
            PRO.CODORI AS ORIGEM_PRODUTO,
            MAX(EOQ.CODCRE) AS CODCRE,
            MAX(CRE.ABRCRE) AS ABRCRE,
            DLS.QTDEST,
            MAX(EOQ.DATREA) AS DATREA_ORD,
            TO_CHAR(MAX(EOQ.DATREA), 'DD/MM/YYYY') AS DATREA,
            MAX(EOQ.HORREA) AS HORREA_ORD,
            CASE
                WHEN MAX(EOQ.HORREA) IS NULL THEN NULL
                ELSE LPAD(TRUNC(MAX(EOQ.HORREA) / 60), 2, '0') || ':' ||
                     LPAD(MOD(MAX(EOQ.HORREA), 60), 2, '0')
            END AS HORREA
        FROM E210DLS DLS
        LEFT JOIN E900EOQ EOQ
          ON EOQ.CODEMP = DLS.CODEMP
         AND EOQ.CODLOT = DLS.CODLOT
        LEFT JOIN E725CRE CRE
          ON CRE.CODEMP = EOQ.CODEMP
         AND CRE.CODCRE = EOQ.CODCRE
        LEFT JOIN E075PRO PRO
          ON PRO.CODEMP = DLS.CODEMP
         AND PRO.CODPRO = DLS.CODPRO
        WHERE DLS.CODEMP = :codemp
          AND DLS.QTDEST > 0
    """
    params = {"codemp": codemp_usuario}

    if depositos_consulta:
        placeholders = []
        for indice, deposito in enumerate(depositos_consulta):
            nome_param = f"coddep_{indice}"
            params[nome_param] = deposito
            placeholders.append(f":{nome_param}")
        sql += f"""
          AND DLS.CODDEP IN ({", ".join(placeholders)})
        """

    placeholders = []
    for indice, origem in enumerate(origens_area_vermelha):
        nome_param = f"codori_area_{indice}"
        params[nome_param] = origem
        placeholders.append(f":{nome_param}")
    sql += f"""
          AND UPPER(PRO.CODORI) IN ({", ".join(placeholders) if placeholders else "NULL"})
    """

    if search_query:
        sql += """
          AND (
                UPPER(DLS.CODLOT) LIKE :search_text
             OR UPPER(DLS.USU_SITLOT) LIKE :search_text
             OR UPPER(DLS.CODDEP) LIKE :search_text
             OR TO_CHAR(EOQ.USU_NUMBOB) LIKE :search_exact
             OR UPPER(EOQ.CODCRE) LIKE :search_text
             OR UPPER(CRE.ABRCRE) LIKE :search_text
             OR UPPER(CRE.DESCRE) LIKE :search_text
             OR UPPER(DLS.CODPRO) LIKE :search_text
             OR UPPER(DLS.CODDER) LIKE :search_text
             OR UPPER(PRO.DESPRO) LIKE :search_text
             OR TO_CHAR(DLS.QTDEST) LIKE :search_exact
             OR TO_CHAR(EOQ.DATREA, 'DD/MM/YYYY') LIKE :search_exact
             OR (LPAD(TRUNC(EOQ.HORREA / 60), 2, '0') || ':' || LPAD(MOD(EOQ.HORREA, 60), 2, '0')) LIKE :search_exact
          )
        """
        params["search_text"] = f"%{search_query.upper()}%"
        params["search_exact"] = f"%{search_query}%"

    sql += """
        GROUP BY
            DLS.CODEMP,
            DLS.CODLOT,
            DLS.USU_SITLOT,
            DLS.CODDEP,
            DLS.CODPRO,
            DLS.CODDER,
            PRO.DESPRO,
            PRO.CODORI,
            DLS.QTDEST
        ORDER BY MAX(EOQ.DATREA) DESC, MAX(EOQ.HORREA) DESC
    """

    bobinas = []
    erro = None

    # Antes de bater no ERP, valida se os parâmetros mínimos da filial existem.
    if not codemp_usuario:
        erro = "Usuário sem empresa vinculada."
        messages.error(request, erro)
    elif not depositos_consulta:
        erro = "Nenhum depósito área vermelha ERP configurado na filial ou nos recursos da filial."
        messages.error(request, erro)
    elif not origens_area_vermelha:
        erro = "Nenhuma origem permitida para área vermelha configurada na filial."
        messages.error(request, erro)
    else:
        try:
            with cursor_oracle_erp() as cursor:
                inicio = time.perf_counter()
                cursor.execute(sql, params)
                colunas = [col[0].lower() for col in cursor.description]
                for row in cursor.fetchall():
                    dados_bobina = dict(zip(colunas, row, strict=False))
                    dados_bobina.pop("datrea_ord", None)
                    dados_bobina.pop("horrea_ord", None)
                    bobinas.append(dados_bobina)
                print(
                    f"[AreaVermelha] Consulta ERP completa: linhas={len(bobinas)} "
                    f"tempo={time.perf_counter() - inicio:.3f}s"
                )
        except Exception:
            logger.exception("Falha ao consultar bobinas no Oracle")
            messages.error(request, "Não foi possível consultar bobinas no ERP.")

    paginator = Paginator(bobinas, 30)
    page_number = request.GET.get("page")
    bobinas_page = paginator.get_page(page_number)

    # As consultas auxiliares abaixo usam apenas os lotes da página atual.
    transacoes_recurso = set()
    if parametros_filial_logada:
        transacoes_recurso.update(
            separar_valores_parametro(parametros_filial_logada.transacoes_saida_consumo_producao)
        )
        transacoes_recurso.update(
            separar_valores_parametro(parametros_filial_logada.transacoes_entrada_producao_consumo)
        )

    # A tela deve usar origem/OP/recurso do movimento do lote, não apenas o máximo da OP.
    inicio_referencia = time.perf_counter()
    for bobina in bobinas_page.object_list:
        try:
            referencia_movimento = buscar_referencia_movimento_lote_area_vermelha(
                int(bobina.get("codemp") or 0),
                str(bobina.get("codlot") or ""),
                transacoes_recurso,
            )
        except Exception:
            logger.exception("Falha ao consultar referência por movimento do lote")
            messages.warning(
                request,
                f"Não foi possível consultar referência por movimento do lote {bobina.get('codlot')}.",
            )
            continue

        if not referencia_movimento:
            bobina["codori"] = None
            bobina["numorp"] = None
            bobina["codcre"] = None
            bobina["abrcre"] = None
            continue

        bobina["codori"] = referencia_movimento.get("codori")
        bobina["numorp"] = referencia_movimento.get("numorp")
        bobina["codcre"] = referencia_movimento.get("codcre")
        bobina["abrcre"] = referencia_movimento.get("abrcre") or referencia_movimento.get("descre")
        if valor_vazio_area_vermelha(bobina.get("datrea")):
            bobina["datrea"] = referencia_movimento.get("datrea")
        if valor_vazio_area_vermelha(bobina.get("horrea")):
            bobina["horrea"] = referencia_movimento.get("horrea")
    print(
        f"[AreaVermelha] Referência por movimento: linhas={len(bobinas_page.object_list)} "
        f"tempo={time.perf_counter() - inicio_referencia:.3f}s"
    )

    try:
        inicio_wms = time.perf_counter()
        # Só consulta locais WMS da página atual para não pesar a abertura da tela.
        locais_wms = consultar_locais_wms_lotes(bobinas_page.object_list)
        print(
            f"[AreaVermelha] Locais WMS em lote: retornos={len(locais_wms)} "
            f"tempo={time.perf_counter() - inicio_wms:.3f}s"
        )
    except Exception:
        logger.exception("Falha ao consultar locais WMS dos lotes da página")
        locais_wms = {}
        messages.warning(request, "Não foi possível consultar locais WMS dos lotes da página.")

    locais_parametrizados, local_filial_wms = carregar_locais_area_vermelha_parametrizados(
        bobinas_page.object_list,
        filial_logada,
    )
    for bobina in bobinas_page.object_list:
        # Local exibido/salvo: WMS quando existir; senão parâmetro do recurso/filial.
        sku = montar_sku_wms(bobina.get("codpro"), bobina.get("codder"))
        lote = str(bobina.get("codlot") or "").strip()
        chave_recurso = (
            str(bobina.get("codemp") or ""),
            str(bobina.get("codcre") or "").strip(),
        )
        bobina["local"] = (
            locais_wms.get((sku, lote))
            or locais_parametrizados.get(chave_recurso)
            or local_filial_wms
            or ""
        )
        bobina["local_origem"] = "wms" if locais_wms.get((sku, lote)) else "padrao"

    # Mapeia recurso ERP para máquina Alchemy, usado para trazer análise/observação da bobina.
    recursos_alchemy = {}
    if filial_logada:
        for recurso in Recurso.objects.filter(
            centro_recurso__setor__departamento__filial=filial_logada
        ).select_related(
            "centro_recurso__setor__departamento__filial__empresa",
            "centro_recurso__parametros_centro_recurso",
        ):
            parametros_centro = getattr(recurso.centro_recurso, "parametros_centro_recurso", None)
            if not parametros_centro or not parametros_centro.cod_alchemy:
                continue
            codemp_recurso = str(recurso.centro_recurso.setor.departamento.filial.empresa.codemp)
            codigo = recurso.centro_recurso.codigo_integrador
            if codigo:
                recursos_alchemy[(codemp_recurso, str(codigo))] = parametros_centro.cod_alchemy

    for bobina in bobinas_page.object_list:
        bobina["codmaquina_alchemy"] = recursos_alchemy.get(
            (str(bobina.get("codemp") or ""), str(bobina.get("codcre") or ""))
        )

    try:
        inicio_alchemy = time.perf_counter()
        analises = carregar_analises_alchemy(bobinas_page.object_list)
        for bobina in bobinas_page.object_list:
            codmaquina = bobina.get("codmaquina_alchemy")
            codbobina = bobina.get("usu_numbob")
            chave = (int(codmaquina), int(codbobina)) if codmaquina and codbobina else None
            analise = analises.get(chave) or {}
            bobina["analise_flag"] = analise.get("flag")
            bobina["observacao"] = analise.get("observacao", "")
        print(
            f"[AreaVermelha] Análises Alchemy: retornos={len(analises)} "
            f"tempo={time.perf_counter() - inicio_alchemy:.3f}s"
        )
    except Exception:
        logger.exception("Falha ao consultar análises no Alchemy")
        messages.warning(request, "Não foi possível consultar análises no Alchemy.")
        for bobina in bobinas_page.object_list:
            bobina["analise_flag"] = None
            bobina["observacao"] = ""

    parametros_filial = getattr(filial_logada, "parametros_filial", None)
    recursos_refugo = {}
    # Prepara produto/derivação de refugo que o modal mostra para cada bobina.
    if filial_logada:
        for recurso in Recurso.objects.filter(
            centro_recurso__setor__departamento__filial=filial_logada
        ).select_related(
            "parametros_recurso",
            "centro_recurso__parametros_centro_recurso",
            "centro_recurso__setor__departamento__filial__parametros_filial",
        ):
            codigo = recurso.centro_recurso.codigo_integrador
            if codigo:
                recursos_refugo[str(codigo)] = recurso
    for bobina in bobinas_page.object_list:
        recurso = recursos_refugo.get(str(bobina.get("codcre") or ""))
        parametros_recurso = recurso.get_parametros_efetivos() if recurso else {}
        produto_refugo = str(parametros_recurso.get("produto_refugo", "") or "")
        if produto_refugo:
            origem_produto_refugo = "Centro de Recurso"
            derivacao_refugo = (
                ""
                if parametros_recurso.get("derivacao_refugo") is None
                else str(parametros_recurso.get("derivacao_refugo", ""))
            )
        else:
            origem_produto_refugo = "Filial"
            produto_refugo = str(getattr(parametros_filial, "produto_refugo", "") or "")
            derivacao_refugo = (
                ""
                if getattr(parametros_filial, "derivacao_refugo", None) is None
                else str(getattr(parametros_filial, "derivacao_refugo", ""))
            )
        bobina["produto_refugo"] = produto_refugo
        bobina["derivacao_refugo"] = derivacao_refugo
        bobina["origem_produto_refugo"] = origem_produto_refugo if produto_refugo else ""

    reuniao_aberta = (
        # Recarrega a reunião para montar participantes e registros já lançados no painel vermelho.
        Reuniao.objects.filter(data_hora_fim__isnull=True)
        .prefetch_related("participantes")
        .order_by("-data_hora_inicio")
        .first()
    )
    liberacoes_reuniao = (
        LiberacaoLote.objects.filter(reuniao=reuniao_aberta).select_related("usuario", "etiqueta")
        if reuniao_aberta
        else []
    )
    locais_wms_reuniao = {}
    if reuniao_aberta:
        # Local não fica na LiberacaoLote; vem da pendência WMS gerada para a reunião.
        for integracao in WMS_IntegraçãoOP.objects.filter(reuniao=reuniao_aberta):
            chave = (
                integracao.codemp,
                str(integracao.origem or ""),
                integracao.op or 0,
                str(integracao.lote or ""),
                str(integracao.codpro or "").strip(),
                integracao.codder,
                str(integracao.codigo_integrador or ""),
            )
            locais_wms_reuniao[chave] = str(integracao.local or "")

    grupos_liberacoes = []
    grupos_por_chave = {}
    # Agrupa linhas de liberar/refugar/reclassificar por bobina/lote para exibir uma única linha na reunião.
    for registro in liberacoes_reuniao:
        registro.local_wms = locais_wms_reuniao.get(chave_wms_liberacao(registro), "")
        chave = (registro.codlot, registro.numbob, registro.codpro, registro.codder)
        if chave not in grupos_por_chave:
            grupo = {
                "codemp": registro.codemp,
                "codlot": registro.codlot,
                "local": registro.local_wms,
                "numbob": registro.numbob,
                "codpro": registro.codpro,
                "codder": registro.codder,
                "coddep": registro.coddep,
                "codigo_integrador": registro.codigo_integrador,
                "qtdtot": registro.qtdtot,
                "usuario": registro.usuario,
                "status": registro.status,
                "pode_excluir": True,
                "total_libe": 0,
                "total_refu": 0,
                "total_recl": 0,
                "total_prensa": 0,
                "registros": [],
            }
            grupos_por_chave[chave] = grupo
            grupos_liberacoes.append(grupo)
        grupo = grupos_por_chave[chave]
        if not grupo["local"] and registro.local_wms:
            grupo["local"] = registro.local_wms
        grupo["total_libe"] += registro.qtdlibe or 0
        grupo["total_refu"] += registro.qtdrefu or 0
        grupo["total_recl"] += registro.qtdrecl or 0
        grupo["total_prensa"] += registro.qtdprensa or 0
        if registro.status not in (LiberacaoLote.Status.NAO_INTEGRADO, LiberacaoLote.Status.LOCAL):
            grupo["pode_excluir"] = False
        grupo["registros"].append(registro)

    chaves_pagina = []
    # Marca lotes da página que já possuem destinação local para bloquear nova avaliação duplicada.
    for bobina in bobinas_page.object_list:
        try:
            chaves_pagina.append(
                (
                    int(bobina.get("codemp") or 0),
                    str(bobina.get("codlot") or ""),
                    str(bobina.get("codpro") or ""),
                    str(bobina.get("codder") or ""),
                )
            )
        except TypeError, ValueError:
            bobina["destinado_reuniao"] = False

    lotes_destinados = set()
    if chaves_pagina:
        filtros_destinados = LiberacaoLote.objects.none()
        for codemp, codlot, codpro, codder in chaves_pagina:
            filtros_destinados = filtros_destinados | LiberacaoLote.objects.filter(
                codemp=codemp,
                codlot=codlot,
                codpro=codpro,
                codder=codder,
            )
        lotes_destinados = set(
            filtros_destinados.values_list("codemp", "codlot", "codpro", "codder")
        )

    for bobina in bobinas_page.object_list:
        # Situações vindas do ERP/local também bloqueiam a ação na tela.
        try:
            codemp_bobina = int(bobina.get("codemp") or 0)
            codlot_bobina = str(bobina.get("codlot") or "")
            codpro_bobina = str(bobina.get("codpro") or "")
            codder_bobina = str(bobina.get("codder") or "")
            chaves_destinacao = {(codemp_bobina, codlot_bobina, codpro_bobina, codder_bobina)}
        except TypeError, ValueError:
            chaves_destinacao = set()
        sitlot_bobina = str(bobina.get("sitlot") or "").strip().upper()
        bobina["avaliado_erp"] = sitlot_bobina == "A"
        bobina["excluida_erp"] = sitlot_bobina == "E"
        try:
            bobina["aguardando_repesagem"] = (
                Decimal(str(bobina.get("qtdest") or "0").replace(",", ".")) == 1
            )
        except InvalidOperation, TypeError, ValueError:
            bobina["aguardando_repesagem"] = False
        bobina["local_nao_definido"] = not str(bobina.get("local") or "").strip()

        bobina["destinado_reuniao"] = (
            bobina["avaliado_erp"]
            or bobina["excluida_erp"]
            or bobina["aguardando_repesagem"]
            or bobina["local_nao_definido"]
            or bool(chaves_destinacao & lotes_destinados)
        )

    motivos_area_vermelha = []
    # Motivos são carregados só no final; falha aqui não deve impedir a tela de abrir.
    if codemp_usuario:
        try:
            motivos_area_vermelha = carregar_motivos_area_vermelha(codemp_usuario)
        except Exception:
            logger.exception("Falha ao consultar motivos da Área Vermelha no ERP")
            messages.warning(request, "Não foi possível consultar motivos da Área Vermelha.")

    observacoes_etiqueta = ObservacaoEtiqueta.objects.filter(ativo=True)

    # Contexto final consumido pelo template da reunião da área vermelha.
    context = {
        "titulo": "Reunião da Área Vermelha",
        "bobinas": bobinas_page,
        "search_query": search_query,
        "selected_row": selected_row,
        "erro_consulta": erro,
        "mostrar_btn_liberar": True,
        "reuniao_aberta": reuniao_aberta,
        "grupos_liberacoes": grupos_liberacoes,
        "motivos_area_vermelha": motivos_area_vermelha,
        "observacoes_etiqueta": observacoes_etiqueta,
        "pode_destinar_area_vermelha": pode_destinar_area_vermelha,
        "setores_participante": ReuniaoParticipante.Setor.choices,
    }
    return render(request, "setores/qualidade/liberar_area_vermelha.html", context)
