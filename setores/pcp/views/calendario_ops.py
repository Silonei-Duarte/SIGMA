import re
from colorsys import hls_to_rgb
from datetime import date, datetime, timedelta

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from SIGMA.autorizacao import permissao_requerida
from SIGMA.integracoes.oracle import cursor_oracle_erp

CORES_OP = (
    "#93c5fd",
    "#86efac",
    "#fcd34d",
    "#c4b5fd",
    "#fda4af",
    "#5eead4",
    "#bfdbfe",
    "#bbf7d0",
    "#fdba74",
    "#ddd6fe",
    "#f5d0fe",
    "#7dd3fc",
    "#a5b4fc",
    "#fde68a",
    "#99f6e4",
    "#fecdd3",
    "#c7d2fe",
    "#fed7aa",
)
SITUACOES_OP = {
    "A": "Andamento",
    "L": "Liberada",
    "E": "Explodida",
    "R": "Reabilitada",
    "F": "Finalizada",
}
DEPOSITOS_DESCONSIDERADOS_COMPROMETIMENTO = (
    "01.25",
    "AV.01",
    "05.14",
    "01.14",
    "01.23",
    "01.DV",
    "C1.25",
    "OP.25",
    "P01.01",
    "P01.02",
    "P01.03",
    "01.30",
)
SQL_DEPOSITOS_DESCONSIDERADOS = ", ".join(
    f"'{deposito}'" for deposito in DEPOSITOS_DESCONSIDERADOS_COMPROMETIMENTO
)


def _empresa_do_usuario(request):
    filial = getattr(request.user, "filial", None)
    if filial and filial.empresa_id:
        return filial.empresa.codemp
    return None


def _filial_do_usuario(request):
    filial = getattr(request.user, "filial", None)
    return filial.codfil if filial else None


def _origens_comprometimento_por_produto(request):
    filial = getattr(request.user, "filial", None)
    parametros_filial = getattr(filial, "parametros_filial", None) if filial else None
    return {
        origem.strip().upper()
        for origem in str(getattr(parametros_filial, "origens_area_vermelha", "") or "").split(",")
        if origem.strip()
    }


def _user_without_filial(request):
    """Não-staff sem filial vinculada não tem empresa para consultar; staff mantém escopo global."""
    return not request.user.is_staff and not getattr(request.user, "filial", None)


def _periodo_parametros(request):
    try:
        inicio = datetime.strptime(request.GET["start"][:10], "%Y-%m-%d").date()
        fim_exclusivo = datetime.strptime(request.GET["end"][:10], "%Y-%m-%d").date()
    except KeyError, TypeError, ValueError:
        inicio = date.today().replace(day=1)
        proximo_mes = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1)
        fim_exclusivo = proximo_mes

    if fim_exclusivo <= inicio:
        fim_exclusivo = inicio + timedelta(days=1)
    return inicio, fim_exclusivo


def _valores_filtro(request, nome):
    return list(
        dict.fromkeys(valor.strip() for valor in request.GET.getlist(nome) if valor.strip())
    )


def _condicao_in(campo, valores, prefixo, parametros):
    chaves = []
    for indice, valor in enumerate(valores):
        chave = f"{prefixo}{indice}"
        chaves.append(f":{chave}")
        parametros[chave] = valor
    return f"{campo} IN ({', '.join(chaves)})"


def _condicao_produto_derivacao(valores, parametros):
    condicoes = []
    for indice, valor in enumerate(valores):
        codpro, separador, codder = valor.partition("|")
        if not separador:
            continue
        chave_produto = f"produto{indice}"
        parametros[chave_produto] = codpro
        if codder == "__NULO__":
            condicoes.append(f"(q.CODPRO = :{chave_produto} AND q.CODDER IS NULL)")
        elif codder == "__ESPACO__":
            condicoes.append(f"(q.CODPRO = :{chave_produto} AND q.CODDER = ' ')")
        else:
            chave_derivacao = f"derivacao{indice}"
            parametros[chave_derivacao] = codder
            condicoes.append(f"(q.CODPRO = :{chave_produto} AND q.CODDER = :{chave_derivacao})")
    return f"({' OR '.join(condicoes)})" if condicoes else ""


def _data_valida(valor):
    if not valor:
        return False
    valor_data = valor.date() if hasattr(valor, "date") else valor
    return valor_data >= date(2000, 1, 1)


def _data_exibicao(valor, ausente="Não informado"):
    if not _data_valida(valor):
        return ausente
    valor_data = valor.date() if hasattr(valor, "date") else valor
    return valor_data.strftime("%d/%m/%Y")


def _data_sem_hora(valor):
    return valor.date() if hasattr(valor, "date") else valor


def _calcular_comprometimento(fim_previsto, fim_real):
    fim_previsto = _data_sem_hora(fim_previsto)
    fim_real = _data_sem_hora(fim_real)
    return (
        _data_valida(fim_previsto)
        and fim_previsto >= date.today()
        and (not _data_valida(fim_real) or fim_real >= date.today())
    )


def _linhas_oracle(sql, parametros):
    with cursor_oracle_erp() as cursor:
        chaves = set(re.findall(r":([A-Za-z][A-Za-z0-9_]*)", sql))
        cursor.execute(sql, {chave: parametros[chave] for chave in chaves})
        colunas = [coluna[0].lower() for coluna in cursor.description]
        return [dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()]


def _atribuir_cores(eventos):
    ativos = []
    for evento in sorted(eventos, key=lambda item: (item["_inicio"], item["_fim"], item["id"])):
        inicio = evento["_inicio"]
        ativos = [item for item in ativos if item[0] + timedelta(days=1) >= inicio]
        cores_em_uso = {cor for _, cor in ativos}
        cor = next((cor for cor in CORES_OP if cor not in cores_em_uso), None)
        if cor is None:
            indice = 0
            while True:
                vermelho, verde, azul = hls_to_rgb(((indice * 137) % 360) / 360, 0.72, 0.65)
                cor = f"#{round(vermelho * 255):02x}{round(verde * 255):02x}{round(azul * 255):02x}"
                if cor not in cores_em_uso:
                    break
                indice += 1
        evento["backgroundColor"] = cor
        evento["borderColor"] = cor
        ativos.append((evento["_fim"], cor))

    for evento in eventos:
        evento["extendedProps"]["cor_op"] = evento["backgroundColor"]
        evento.pop("_inicio")
        evento.pop("_fim")


def _consultar_comprometimentos_por_produto(codemp, codfil, alvos):
    """Calcula o comprometimento apenas dos produto-derivação exibidos no calendário."""
    alvos_unicos = {
        (codpro, codder, _data_sem_hora(data_corte))
        for codpro, codder, data_corte in alvos
        if codpro is not None and _data_valida(data_corte)
    }
    if not alvos_unicos:
        return {}

    parametros = {"codemp": codemp, "codfil": codfil, "data_atual": date.today()}
    selecoes_alvos = []
    for indice, (codpro, codder, data_corte) in enumerate(alvos_unicos):
        parametros.update(
            {
                f"alvo_codpro{indice}": codpro,
                f"alvo_codder{indice}": codder,
                f"alvo_data{indice}": data_corte,
            }
        )
        selecoes_alvos.append(
            f"SELECT {indice} AS ID_ALVO, :alvo_codpro{indice} AS CODPRO, "
            f":alvo_codder{indice} AS CODDER, :alvo_data{indice} AS DTPFIM FROM DUAL"
        )

    sql = f"""
        WITH alvos AS (
            {" UNION ALL ".join(selecoes_alvos)}
        ),
        producao_aberta AS (
            SELECT q.CODEMP,
                   q.CODPRO,
                   q.CODDER,
                   c.DTPFIM,
                   GREATEST(0, NVL(q.QTDPRV, 0) - NVL(q.QTDRE1, 0)) AS QTD_PENDENTE
              FROM E900QDO q
              JOIN E900COP c
                ON c.CODEMP = q.CODEMP
               AND c.CODORI = q.CODORI
               AND c.NUMORP = q.NUMORP
             WHERE c.CODEMP = :codemp
               AND c.SITORP IN ('A', 'E', 'L', 'R')
               AND q.PROORI = 'S'
        ),
        consumo_aberto AS (
            SELECT m.CODEMP,
                   m.CODCMP AS CODPRO,
                   m.CODDER,
                   c.DTPFIM,
                   GREATEST(0, NVL(m.QTDPRV, 0) - NVL(m.QTDUTI, 0)) AS QTD_PENDENTE
              FROM E900CMO m
              JOIN E900COP c
                ON c.CODEMP = m.CODEMP
               AND c.CODORI = m.CODORI
               AND c.NUMORP = m.NUMORP
             WHERE c.CODEMP = :codemp
               AND c.SITORP IN ('A', 'E', 'L', 'R')
        ),
        estoque_por_alvo AS (
            SELECT a.ID_ALVO, SUM(NVL(e.QTDEST, 0)) AS QTD_ESTOQUE
              FROM alvos a
              LEFT JOIN E210EST e
                ON e.CODEMP = :codemp
               AND e.CODPRO = a.CODPRO
               AND NVL(e.CODDER, CHR(0)) = NVL(a.CODDER, CHR(0))
               AND e.CODDEP NOT IN ({SQL_DEPOSITOS_DESCONSIDERADOS})
             GROUP BY a.ID_ALVO
        ),
        producao_por_alvo AS (
            SELECT a.ID_ALVO,
                   SUM(CASE WHEN p.DTPFIM >= :data_atual AND p.DTPFIM <= a.DTPFIM THEN NVL(p.QTD_PENDENTE, 0) ELSE 0 END) AS QTD_ATE_CORTE,
                   SUM(CASE WHEN p.DTPFIM > a.DTPFIM THEN NVL(p.QTD_PENDENTE, 0) ELSE 0 END) AS QTD_RESERVAS,
                   SUM(NVL(p.QTD_PENDENTE, 0)) AS QTD_TOTAL
              FROM alvos a
              LEFT JOIN producao_aberta p
                ON p.CODEMP = :codemp
               AND p.CODPRO = a.CODPRO
               AND NVL(p.CODDER, CHR(0)) = NVL(a.CODDER, CHR(0))
             GROUP BY a.ID_ALVO
        ),
        consumo_por_alvo AS (
            SELECT a.ID_ALVO,
                   SUM(CASE WHEN c.DTPFIM <= a.DTPFIM THEN NVL(c.QTD_PENDENTE, 0) ELSE 0 END) AS QTD_ATE_CORTE,
                   SUM(CASE WHEN c.DTPFIM > a.DTPFIM THEN NVL(c.QTD_PENDENTE, 0) ELSE 0 END) AS QTD_RESERVAS,
                   SUM(NVL(c.QTD_PENDENTE, 0)) AS QTD_TOTAL
              FROM alvos a
              LEFT JOIN consumo_aberto c
                ON c.CODEMP = :codemp
               AND c.CODPRO = a.CODPRO
               AND NVL(c.CODDER, CHR(0)) = NVL(a.CODDER, CHR(0))
             GROUP BY a.ID_ALVO
        ),
        reserva_por_alvo AS (
            SELECT a.ID_ALVO, SUM(NVL(t.USU_QTDRES, 0)) AS QTD_RESERVADA
              FROM alvos a
              LEFT JOIN USU_TRESPED t
                ON t.USU_CODEMP = :codemp
               AND t.USU_CODFIL = :codfil
               AND t.USU_CODPRO = a.CODPRO
               AND NVL(t.USU_CODDER, CHR(0)) = NVL(a.CODDER, CHR(0))
             GROUP BY a.ID_ALVO
        )
        SELECT a.CODPRO,
               a.CODDER,
               a.DTPFIM,
               NVL(e.QTD_ESTOQUE, 0) AS ESTOQUE,
               NVL(p.QTD_ATE_CORTE, 0) AS PRODUCAO_ATE_CORTE,
               NVL(c.QTD_ATE_CORTE, 0) AS CONSUMO_ATE_CORTE,
               NVL(p.QTD_RESERVAS, 0) AS PRODUCAO_RESERVAS,
               NVL(c.QTD_RESERVAS, 0) AS CONSUMO_RESERVAS,
               NVL(p.QTD_TOTAL, 0) AS PRODUCAO_TOTAL,
               NVL(c.QTD_TOTAL, 0) AS CONSUMO_TOTAL,
               NVL(r.QTD_RESERVADA, 0) AS QUANTIDADE_RESERVADA
          FROM alvos a
          LEFT JOIN estoque_por_alvo e ON e.ID_ALVO = a.ID_ALVO
          LEFT JOIN producao_por_alvo p ON p.ID_ALVO = a.ID_ALVO
          LEFT JOIN consumo_por_alvo c ON c.ID_ALVO = a.ID_ALVO
          LEFT JOIN reserva_por_alvo r ON r.ID_ALVO = a.ID_ALVO
    """
    with cursor_oracle_erp() as cursor:
        cursor.execute(sql, parametros)
        return {
            (codpro, codder, _data_sem_hora(data_corte)): {
                "estoque": float(estoque or 0),
                "producao_ate_corte": float(producao_ate_corte or 0),
                "consumo_ate_corte": float(consumo_ate_corte or 0),
                "producao_reservas": float(producao_reservas or 0),
                "consumo_reservas": float(consumo_reservas or 0),
                "producao_total": float(producao_total or 0),
                "consumo_total": float(consumo_total or 0),
                "quantidade_reservada": float(quantidade_reservada or 0),
            }
            for (
                codpro,
                codder,
                data_corte,
                estoque,
                producao_ate_corte,
                consumo_ate_corte,
                producao_reservas,
                consumo_reservas,
                producao_total,
                consumo_total,
                quantidade_reservada,
            ) in cursor.fetchall()
        }


def _montar_indicadores_comprometimento(dados):
    """Monta os três indicadores a partir dos valores já apurados para um produto."""
    estoque = dados.get("estoque", 0)
    quantidade_reservada = dados.get("quantidade_reservada", 0)

    def indicador(producao, consumo, incluir_reservas=False, estoque_base=estoque):
        disponivel = estoque_base + producao
        comprometido = consumo + (quantidade_reservada if incluir_reservas else 0)
        percentual = (comprometido / disponivel) * 100 if disponivel else 0
        return {
            "estoque": estoque_base,
            "producao": producao,
            "consumo": consumo,
            "disponivel": disponivel,
            "comprometido": comprometido,
            "saldo": disponivel - comprometido,
            "percentual": percentual,
            "reservas": quantidade_reservada if incluir_reservas else 0,
        }

    ate_corte = indicador(
        dados.get("producao_ate_corte", 0),
        dados.get("consumo_ate_corte", 0),
    )
    return {
        "ate_corte": ate_corte,
        "reservas": indicador(
            dados.get("producao_reservas", 0),
            dados.get("consumo_reservas", 0),
            incluir_reservas=True,
            estoque_base=ate_corte["saldo"],
        ),
        "total": indicador(
            dados.get("producao_total", 0),
            dados.get("consumo_total", 0),
            incluir_reservas=True,
        ),
    }


def _consultar_eventos(
    codemp,
    codfil,
    inicio,
    fim_exclusivo,
    maquinas=None,
    origens=None,
    produtos=None,
    situacoes=None,
):
    maquinas = maquinas or []
    origens = origens or []
    produtos = produtos or []
    situacoes = [
        situacao for situacao in (situacoes or ["A", "L", "E", "R"]) if situacao in SITUACOES_OP
    ]
    if not situacoes:
        situacoes = ["A", "L", "E", "R"]
    inicio_finalizadas = (inicio.replace(day=1) - timedelta(days=1)).replace(day=1)
    filtros = [
        "c.CODEMP = :codemp",
        "e.DTPINI >= DATE '2000-01-01'",
        "e.DTPFIM < DATE '2100-01-01'",
    ]
    parametros = {
        "codemp": codemp,
        "codfil": codfil,
        "fim_exclusivo": fim_exclusivo,
    }

    if maquinas:
        filtros.append(_condicao_in("o.CODCRE", maquinas, "maquina", parametros))
    if origens:
        filtros.append(_condicao_in("c.CODORI", origens, "origem", parametros))
    if produtos:
        condicao_produtos = _condicao_produto_derivacao(produtos, parametros)
        if condicao_produtos:
            filtros.append(condicao_produtos)

    situacoes_abertas = [situacao for situacao in situacoes if situacao != "F"]
    condicoes_situacao = []
    if situacoes_abertas:
        parametros["inicio"] = inicio
        condicoes_situacao.append(
            f"({_condicao_in('c.SITORP', situacoes_abertas, 'situacao_aberta', parametros)} "
            "AND (CASE WHEN c.SITORP = 'A' AND e.DTRINI >= DATE '2000-01-01' THEN e.DTRINI ELSE e.DTPINI END) < :fim_exclusivo "
            "AND e.DTPFIM >= :inicio)"
        )
    if "F" in situacoes:
        parametros["inicio_finalizadas"] = inicio_finalizadas
        condicoes_situacao.append(
            "(c.SITORP = 'F' AND ("
            "(e.DTRINI >= :inicio_finalizadas AND e.DTRINI < :fim_exclusivo) OR "
            "(e.DTRFIM >= :inicio_finalizadas AND e.DTRFIM < :fim_exclusivo)"
            "))"
        )
    filtros.append(f"({' OR '.join(condicoes_situacao)})")

    sql = f"""
        WITH reservas_por_pedido AS (
            SELECT t.USU_NUMORP,
                   t.USU_NUMPED,
                   SUM(NVL(t.USU_QTDRES, 0)) AS QTD_RESERVADA
              FROM USU_TRESPED t
             WHERE t.USU_CODEMP = :codemp
               AND t.USU_CODFIL = :codfil
             GROUP BY t.USU_NUMORP, t.USU_NUMPED
        ),
        reservas_op AS (
            SELECT USU_NUMORP,
                   LISTAGG(
                       TO_CHAR(USU_NUMPED) || ' (' || TO_CHAR(QTD_RESERVADA) || ')',
                       ', ' ON OVERFLOW TRUNCATE '...' WITHOUT COUNT
                   ) WITHIN GROUP (ORDER BY USU_NUMPED) AS PEDIDOS_RESERVADOS,
                   SUM(QTD_RESERVADA) AS QUANTIDADE_RESERVADA
              FROM reservas_por_pedido
             GROUP BY USU_NUMORP
        )
        SELECT e.CODORI,
               c.NUMORP,
               c.SITORP,
               e.CODETG,
               etg.DESETG,
               e.SFXETR,
               e.DTPINI,
               e.DTPFIM,
               c.DTPFIM AS DTPFIM_OP,
               e.DTRINI,
               e.DTRFIM,
               c.DTRFIM AS DTRFIM_OP,
               o.CODCRE,
               r.ABRCRE,
               r.DESCRE,
               ori.DESORI,
               q.QTDPRV,
               q.QTDRE1,
               q.UNIMED,
               q.CODPRO,
               p.DESPRO,
               q.CODDER,
               d.DESDER,
               NVL(ro.PEDIDOS_RESERVADOS, '') AS PEDIDOS_RESERVADOS,
               NVL(ro.QUANTIDADE_RESERVADA, 0) AS QUANTIDADE_RESERVADA
          FROM E900EOP e
          JOIN E900COP c
            ON c.CODEMP = e.CODEMP
           AND c.CODORI = e.CODORI
           AND c.NUMORP = e.NUMORP
          LEFT JOIN E900QDO q
            ON q.CODEMP = c.CODEMP
           AND q.CODORI = c.CODORI
           AND q.NUMORP = c.NUMORP
           AND q.PROORI = 'S'
          LEFT JOIN E900OOP o
            ON o.CODEMP = e.CODEMP
           AND o.CODORI = e.CODORI
           AND o.NUMORP = e.NUMORP
           AND o.CODETG = e.CODETG
           AND o.SFXETR = e.SFXETR
          LEFT JOIN E725CRE r
            ON r.CODEMP = o.CODEMP
           AND r.CODCRE = o.CODCRE
          LEFT JOIN E093ETG etg
            ON etg.CODEMP = e.CODEMP
           AND etg.CODETG = e.CODETG
          LEFT JOIN E083ORI ori
            ON ori.CODEMP = c.CODEMP
           AND ori.CODORI = c.CODORI
          LEFT JOIN E075PRO p
            ON p.CODEMP = q.CODEMP
           AND p.CODPRO = q.CODPRO
          LEFT JOIN E075DER d
            ON d.CODEMP = q.CODEMP
           AND d.CODPRO = q.CODPRO
           AND d.CODDER = q.CODDER
          LEFT JOIN reservas_op ro
            ON ro.USU_NUMORP = c.NUMORP
         WHERE {" AND ".join(filtros)}
         ORDER BY e.DTPINI, c.NUMORP, e.CODETG, o.CODCRE
    """

    with cursor_oracle_erp() as cursor:
        cursor.execute(sql, parametros)
        return cursor.fetchall()


def _opcoes_filtros(codemp):
    sql = """
        SELECT tipo, codigo, descricao
          FROM (
                SELECT 'maquina' AS tipo,
                       o.CODCRE AS codigo,
                       NVL(r.ABRCRE, o.CODCRE) || ' - ' || r.DESCRE AS descricao
                  FROM E900EOP e
                  JOIN E900COP c
                    ON c.CODEMP = e.CODEMP
                   AND c.CODORI = e.CODORI
                   AND c.NUMORP = e.NUMORP
                  JOIN E900OOP o
                    ON o.CODEMP = e.CODEMP
                   AND o.CODORI = e.CODORI
                   AND o.NUMORP = e.NUMORP
                   AND o.CODETG = e.CODETG
                   AND o.SFXETR = e.SFXETR
                  LEFT JOIN E725CRE r
                    ON r.CODEMP = o.CODEMP
                   AND r.CODCRE = o.CODCRE
                 WHERE c.CODEMP = :codemp
                   AND c.SITORP IN ('A', 'L', 'E', 'R')
                   AND o.CODCRE IS NOT NULL
                 GROUP BY o.CODCRE, r.ABRCRE, r.DESCRE
                UNION ALL
                SELECT 'origem' AS tipo, c.CODORI AS codigo, ori.DESORI AS descricao
                  FROM E900EOP e
                  JOIN E900COP c
                    ON c.CODEMP = e.CODEMP
                   AND c.CODORI = e.CODORI
                   AND c.NUMORP = e.NUMORP
                  LEFT JOIN E083ORI ori
                    ON ori.CODEMP = c.CODEMP
                   AND ori.CODORI = c.CODORI
                 WHERE c.CODEMP = :codemp
                   AND c.SITORP IN ('A', 'L', 'E', 'R')
                 GROUP BY c.CODORI, ori.DESORI
                UNION ALL
                SELECT 'produto' AS tipo,
                       q.CODPRO || '|' || CASE
                           WHEN q.CODDER IS NULL THEN '__NULO__'
                           WHEN q.CODDER = ' ' THEN '__ESPACO__'
                           ELSE q.CODDER
                       END AS codigo,
                       p.DESPRO || '-' || d.DESDER AS descricao
                  FROM E900EOP e
                  JOIN E900COP c
                    ON c.CODEMP = e.CODEMP
                   AND c.CODORI = e.CODORI
                   AND c.NUMORP = e.NUMORP
                  JOIN E900QDO q
                    ON q.CODEMP = c.CODEMP
                   AND q.CODORI = c.CODORI
                   AND q.NUMORP = c.NUMORP
                   AND q.PROORI = 'S'
                  LEFT JOIN E075PRO p
                    ON p.CODEMP = q.CODEMP
                   AND p.CODPRO = q.CODPRO
                  LEFT JOIN E075DER d
                    ON d.CODEMP = q.CODEMP
                   AND d.CODPRO = q.CODPRO
                   AND d.CODDER = q.CODDER
                 WHERE c.CODEMP = :codemp
                   AND c.SITORP IN ('A', 'L', 'E', 'R')
                 GROUP BY q.CODPRO, q.CODDER, p.DESPRO, d.DESDER
          )
         ORDER BY tipo, codigo
    """
    opcoes = {"maquinas": [], "origens": [], "produtos": []}
    destino = {"maquina": "maquinas", "origem": "origens", "produto": "produtos"}
    with cursor_oracle_erp() as cursor:
        cursor.execute(sql, {"codemp": codemp})
        for tipo, codigo, descricao in cursor.fetchall():
            codigo = str(codigo).strip()
            opcao = {"codigo": codigo, "descricao": (descricao or "").strip()}
            if tipo == "produto":
                codpro, _, codder = codigo.partition("|")
                exibicao_derivacao = {
                    "__NULO__": "(nulo)",
                    "__ESPACO__": "(espaço)",
                }.get(codder, codder)
                opcao["exibicao"] = f"{codpro}-{exibicao_derivacao}"
            opcoes[destino[tipo]].append(opcao)
    return opcoes


@permissao_requerida("pcp.pode_visualizar_calendario_ops")
def calendario_ops(request):
    if _user_without_filial(request):
        return render(
            request,
            "setores/pcp/calendario_ops.html",
            {
                "filtros": {},
                "opcoes": {"maquinas": [], "origens": [], "produtos": []},
                "situacoes": SITUACOES_OP.items(),
                "cores_op_coloridas": True,
            },
        )
    codemp = _empresa_do_usuario(request)
    return render(
        request,
        "setores/pcp/calendario_ops.html",
        {
            "filtros": {
                "maquinas": _valores_filtro(request, "maquina"),
                "origens": _valores_filtro(request, "origem"),
                "produtos": _valores_filtro(request, "produto"),
                # Sem seleção explícita o filtro considera todas as situações,
                # mas os checkboxes nascem desmarcados (mesma convenção dos
                # demais filtros): destaque só quando há restrição real.
                "situacoes": _valores_filtro(request, "situacao"),
            },
            "opcoes": _opcoes_filtros(codemp),
            "situacoes": SITUACOES_OP.items(),
            "cores_op_coloridas": request.session.get("calendario_ops_cores_coloridas", True),
        },
    )


@permissao_requerida("pcp.pode_visualizar_calendario_ops")
@require_POST
def salvar_cores_calendario_ops(request):
    if _user_without_filial(request):
        return JsonResponse({"erro": "Usuário sem filial vinculada."}, status=403)
    valor = request.POST.get("colorido")
    if valor not in ("true", "false"):
        return JsonResponse({"erro": "Modo de cores inválido."}, status=400)

    request.session["calendario_ops_cores_coloridas"] = valor == "true"
    return JsonResponse({"colorido": request.session["calendario_ops_cores_coloridas"]})


@permissao_requerida("pcp.pode_visualizar_calendario_ops")
def eventos_calendario_ops(request):
    if _user_without_filial(request):
        return JsonResponse([], safe=False)
    inicio, fim_exclusivo = _periodo_parametros(request)
    maquinas = _valores_filtro(request, "maquina")
    origens = _valores_filtro(request, "origem")
    produtos = _valores_filtro(request, "produto")
    situacoes = _valores_filtro(request, "situacao") or ["A", "L", "E", "R"]
    origens_comprometimento = _origens_comprometimento_por_produto(request)

    linhas = _consultar_eventos(
        _empresa_do_usuario(request),
        _filial_do_usuario(request),
        inicio,
        fim_exclusivo,
        maquinas,
        origens,
        produtos,
        situacoes,
    )
    alvos_comprometimento = [
        (linha[19], linha[21], linha[8])
        for linha in linhas
        if (
            str(linha[0]).upper() in origens_comprometimento
            and _calcular_comprometimento(linha[8], linha[11])
        )
    ]
    comprometimentos_por_produto = _consultar_comprometimentos_por_produto(
        _empresa_do_usuario(request), _filial_do_usuario(request), alvos_comprometimento
    )

    eventos = []
    for (
        codori,
        numorp,
        sitorp,
        codetg,
        desetg,
        sfxetr,
        dtpini,
        dtpfim,
        dtpfim_op,
        dtrini,
        dtrfim,
        dtrfim_op,
        codcre,
        abrcre,
        descre,
        desori,
        qtdprv,
        qtdre1,
        unimed,
        codpro,
        despro,
        codder,
        desder,
        pedidos_reservados,
        quantidade_reservada,
    ) in linhas:
        fim_base = dtrfim if _data_valida(dtrfim) else dtpfim
        fim = fim_base.date() if hasattr(fim_base, "date") else fim_base
        inicio_base = dtrini if _data_valida(dtrini) else dtpini
        inicio_evento = inicio_base.date() if hasattr(inicio_base, "date") else inicio_base
        calcular_comprometimento = _calcular_comprometimento(dtpfim_op, dtrfim_op)
        produto_codigo = str(codpro) if codpro is not None else "sem produto"
        derivacao_codigo = str(codder) if codder is not None else "sem derivação"
        usa_comprometimento_por_consumo = str(codori).upper() in origens_comprometimento
        quantidade_comprometida = (
            float(quantidade_reservada or 0) if calcular_comprometimento else None
        )
        base_percentual = float(qtdprv or 0)
        saldo_disponivel = None
        quantidade_comprometida_produto = None
        indicadores_comprometimento = None
        if calcular_comprometimento and usa_comprometimento_por_consumo:
            dados_comprometimento = comprometimentos_por_produto.get(
                (codpro, codder, _data_sem_hora(dtpfim_op)), {}
            )
            quantidade_reservada = dados_comprometimento.get("quantidade_reservada", 0)
            indicadores_comprometimento = _montar_indicadores_comprometimento(dados_comprometimento)
            saldo_disponivel = indicadores_comprometimento["reservas"]["disponivel"]
            quantidade_comprometida_produto = indicadores_comprometimento["reservas"][
                "comprometido"
            ]
            quantidade_comprometida = quantidade_comprometida_produto
            base_percentual = saldo_disponivel
        percentual_comprometido = (
            (quantidade_comprometida / base_percentual) * 100
            if calcular_comprometimento and base_percentual
            else 0
        )
        percentual_titulo = (
            f"{percentual_comprometido:.2f}".rstrip("0").rstrip(".").replace(".", ",")
        )
        sufixo_percentual = (
            "" if sitorp == "F" or not calcular_comprometimento else f" · {percentual_titulo}%"
        )
        eventos.append(
            {
                "id": f"{codori}-{numorp}-{codetg}-{sfxetr}-{codcre or 'sem-recurso'}",
                "title": f"{numorp} · {produto_codigo}-{derivacao_codigo} · {abrcre or 'sem máquina'}{sufixo_percentual}",
                "start": inicio_evento.isoformat(),
                "end": (fim + timedelta(days=1)).isoformat(),
                "allDay": True,
                "_inicio": inicio_evento,
                "_fim": fim,
                "extendedProps": {
                    "op": numorp,
                    "codigo_origem": codori,
                    "origem": f"{codori} - {desori or ''}".rstrip(" -"),
                    "estagio": f"{codetg} - {desetg or ''}".rstrip(" -"),
                    "maquina": f"{abrcre or ''} - {descre or ''}".strip(" -"),
                    "situacao": f"{sitorp} - {SITUACOES_OP.get(sitorp, sitorp)}",
                    "previsto_inicio": _data_exibicao(dtpini),
                    "previsto_fim": _data_exibicao(dtpfim),
                    "real_inicio": _data_exibicao(dtrini, "Não iniciada"),
                    "real_fim": _data_exibicao(
                        dtrfim,
                        "Não finalizada" if _data_valida(dtrini) else "Não iniciada",
                    ),
                    "quantidade_prevista": float(qtdprv) if qtdprv is not None else None,
                    "quantidade_produzida": float(qtdre1) if qtdre1 is not None else None,
                    "calcular_comprometimento": calcular_comprometimento,
                    "quantidade_reservada": (
                        float(quantidade_reservada)
                        if calcular_comprometimento and quantidade_reservada is not None
                        else None
                    ),
                    "quantidade_comprometida": quantidade_comprometida,
                    "saldo_disponivel": (
                        float(saldo_disponivel)
                        if calcular_comprometimento
                        and usa_comprometimento_por_consumo
                        and saldo_disponivel is not None
                        else None
                    ),
                    "saldo_restante": (
                        float(saldo_disponivel or 0) - float(quantidade_comprometida_produto or 0)
                        if calcular_comprometimento and usa_comprometimento_por_consumo
                        else None
                    ),
                    "percentual_comprometido": percentual_comprometido,
                    "percentual_visual": min(percentual_comprometido, 100)
                    if calcular_comprometimento
                    else 0,
                    "indicadores_comprometimento": indicadores_comprometimento,
                    "unidade_medida": unimed or "",
                    "produto_derivacao": "-".join(
                        descricao for descricao in (despro, desder) if descricao
                    ),
                    "produto_derivacao_codigo": "-".join(
                        str(codigo) for codigo in (codpro, codder) if codigo is not None
                    ),
                    "codpro": codpro or "",
                    "codder": codder or "",
                    "pedidos_reservados": pedidos_reservados or "",
                },
            }
        )

    _atribuir_cores(eventos)
    return JsonResponse(eventos, safe=False)


@permissao_requerida("pcp.pode_visualizar_calendario_ops")
def detalhes_calendario_ops(request):
    if _user_without_filial(request):
        return JsonResponse({"erro": "OP não localizada."}, status=404)
    try:
        codori = request.GET["codori"]
        numorp = int(request.GET["numorp"])
        codpro = request.GET["codpro"]
    except KeyError, TypeError, ValueError:
        return JsonResponse({"erro": "Parâmetros da OP inválidos."}, status=400)

    codemp = _empresa_do_usuario(request)
    codfil = _filial_do_usuario(request)
    codder = request.GET.get("codder") or None
    parametros = {
        "codemp": codemp,
        "codfil": codfil,
        "codori": codori,
        "numorp": numorp,
        "codpro": codpro,
        "codder": codder,
    }
    alvo = _linhas_oracle(
        """
        SELECT c.CODORI, c.DTPFIM, c.DTRFIM, q.UNIMED
          FROM E900COP c
          JOIN E900QDO q
            ON q.CODEMP = c.CODEMP
           AND q.CODORI = c.CODORI
           AND q.NUMORP = c.NUMORP
         WHERE c.CODEMP = :codemp
           AND c.CODORI = :codori
           AND c.NUMORP = :numorp
           AND q.CODPRO = :codpro
           AND NVL(q.CODDER, CHR(0)) = NVL(:codder, CHR(0))
    """,
        parametros,
    )
    if not alvo:
        return JsonResponse({"erro": "OP não localizada."}, status=404)
    if not _calcular_comprometimento(alvo[0]["dtpfim"], alvo[0]["dtrfim"]):
        return JsonResponse(
            {"erro": "Comprometimento indisponível para OP com fim previsto passado."}, status=400
        )

    data_corte = _data_sem_hora(alvo[0]["dtpfim"])
    if request.GET.get("data_corte"):
        try:
            data_corte = date.fromisoformat(request.GET["data_corte"])
        except ValueError:
            return JsonResponse({"erro": "Data de corte inválida."}, status=400)
        if data_corte < date.today():
            return JsonResponse(
                {"erro": "A data de corte não pode ser anterior à data atual."}, status=400
            )

    calcula_por_produto = str(alvo[0]["codori"]).upper() in _origens_comprometimento_por_produto(
        request
    )
    if request.GET.get("data_corte") and not calcula_por_produto:
        return JsonResponse(
            {"erro": "Simulação disponível somente para origens com cálculo por produto."},
            status=400,
        )
    reservas_op = None
    if not calcula_por_produto:
        reservas_op = _linhas_oracle(
            """
            SELECT t.USU_NUMPED AS NUMPED,
                   t.USU_ORIORP AS ORIGEM_OP,
                   t.USU_NUMORP AS NUMORP,
                   MAX(p.USU_PRVEST) AS PREVISAO_ESTOQUE,
                   SUM(NVL(t.USU_QTDRES, 0)) AS RESERVADO
              FROM USU_TRESPED t
              LEFT JOIN E120PED p
                ON p.CODEMP = t.USU_CODEMP
               AND p.CODFIL = t.USU_CODFIL
               AND p.NUMPED = t.USU_NUMPED
             WHERE t.USU_CODEMP = :codemp
               AND t.USU_CODFIL = :codfil
               AND t.USU_NUMORP = :numorp
             GROUP BY t.USU_NUMPED, t.USU_ORIORP, t.USU_NUMORP
             ORDER BY t.USU_NUMPED, t.USU_ORIORP, t.USU_NUMORP
        """,
            parametros,
        )

    parametros["dtpfim"] = data_corte
    estoque = _linhas_oracle(
        f"""
        SELECT e.CODDEP, NVL(e.QTDEST, 0) AS ESTOQUE
          FROM E210EST e
         WHERE e.CODEMP = :codemp
           AND e.CODPRO = :codpro
           AND NVL(e.CODDER, CHR(0)) = NVL(:codder, CHR(0))
           AND e.CODDEP NOT IN ({SQL_DEPOSITOS_DESCONSIDERADOS})
           AND NVL(e.QTDEST, 0) <> 0
         ORDER BY e.CODDEP
    """,
        parametros,
    )
    producao = _linhas_oracle(
        """
        SELECT c.CODORI, c.NUMORP, c.SITORP, c.DTPFIM,
               SUM(NVL(q.QTDPRV, 0)) AS PREVISTO,
               SUM(NVL(q.QTDRE1, 0)) AS REALIZADO,
               SUM(GREATEST(0, NVL(q.QTDPRV, 0) - NVL(q.QTDRE1, 0))) AS PENDENTE
          FROM E900QDO q
          JOIN E900COP c
            ON c.CODEMP = q.CODEMP
           AND c.CODORI = q.CODORI
           AND c.NUMORP = q.NUMORP
         WHERE c.CODEMP = :codemp
           AND c.SITORP IN ('A', 'E', 'L', 'R')
           AND q.PROORI = 'S'
           AND q.CODPRO = :codpro
           AND NVL(q.CODDER, CHR(0)) = NVL(:codder, CHR(0))
         GROUP BY c.CODORI, c.NUMORP, c.SITORP, c.DTPFIM
         ORDER BY c.DTPFIM, c.CODORI, c.NUMORP
    """,
        parametros,
    )
    consumo = _linhas_oracle(
        """
        SELECT c.CODORI, c.NUMORP, c.SITORP, c.DTPFIM,
               SUM(NVL(m.QTDPRV, 0)) AS PREVISTO,
               SUM(NVL(m.QTDUTI, 0)) AS REALIZADO,
               SUM(GREATEST(0, NVL(m.QTDPRV, 0) - NVL(m.QTDUTI, 0))) AS PENDENTE
          FROM E900CMO m
          JOIN E900COP c
            ON c.CODEMP = m.CODEMP
           AND c.CODORI = m.CODORI
           AND c.NUMORP = m.NUMORP
         WHERE c.CODEMP = :codemp
           AND c.SITORP IN ('A', 'E', 'L', 'R')
           AND m.CODCMP = :codpro
           AND NVL(m.CODDER, CHR(0)) = NVL(:codder, CHR(0))
         GROUP BY c.CODORI, c.NUMORP, c.SITORP, c.DTPFIM
         ORDER BY c.DTPFIM, c.CODORI, c.NUMORP
    """,
        parametros,
    )
    sql_reservas = """
        SELECT t.USU_NUMPED AS NUMPED,
               t.USU_ORIORP AS ORIGEM_OP,
               t.USU_NUMORP AS NUMORP,
               MAX(p.USU_PRVEST) AS PREVISAO_ESTOQUE,
               SUM(NVL(t.USU_QTDRES, 0)) AS RESERVADO
          FROM USU_TRESPED t
          LEFT JOIN E120PED p
            ON p.CODEMP = t.USU_CODEMP
           AND p.CODFIL = t.USU_CODFIL
           AND p.NUMPED = t.USU_NUMPED
         WHERE t.USU_CODEMP = :codemp
           AND t.USU_CODFIL = :codfil
    """
    sql_reservas += """
           AND t.USU_CODPRO = :codpro
           AND NVL(t.USU_CODDER, CHR(0)) = NVL(:codder, CHR(0))
    """
    sql_reservas += """
         GROUP BY t.USU_NUMPED, t.USU_ORIORP, t.USU_NUMORP
         ORDER BY t.USU_NUMPED, t.USU_ORIORP, t.USU_NUMORP
    """
    reservas = reservas_op if reservas_op is not None else _linhas_oracle(sql_reservas, parametros)
    indicadores_comprometimento = None
    if calcula_por_produto:
        dados_comprometimento = _consultar_comprometimentos_por_produto(
            codemp, codfil, [(codpro, codder, data_corte)]
        ).get((codpro, codder, data_corte), {})
        indicadores_comprometimento = _montar_indicadores_comprometimento(dados_comprometimento)
    return JsonResponse(
        {
            "calcula_por_produto": calcula_por_produto,
            "data_corte": data_corte,
            "data_atual": date.today(),
            "unidade_medida": alvo[0]["unimed"] or "",
            "estoque": estoque,
            "producao": producao,
            "consumo": consumo,
            "reservas": reservas,
            "indicadores_comprometimento": indicadores_comprometimento,
        }
    )
