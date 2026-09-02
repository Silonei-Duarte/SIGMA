import logging
from datetime import datetime, timedelta

from django.http import JsonResponse
from django.shortcuts import render

from accounts.models import Empresa
from SIGMA.autorizacao import permissao_requerida
from SIGMA.integracoes.oracle import cursor_oracle_erp

logger = logging.getLogger(__name__)

# Origem de OP exibida no painel.
CODORI_PAINEL = "110"

_LIMITE_INATIVIDADE = timedelta(hours=4)

# Limiares de consumo.
_LIMITE_ATENCAO = 90.0
_LIMITE_CRITICO = 100.0


def _listar_recursos_erp(codemp, codori=CODORI_PAINEL):
    # Recursos com OP aberta na origem do painel.
    with cursor_oracle_erp() as cursor:
        cursor.execute(
            """
        SELECT DISTINCT O.CODCRE, R.DESCRE
          FROM E900COP C
          JOIN E900OOP O ON O.CODEMP = C.CODEMP AND O.CODORI = C.CODORI AND O.NUMORP = C.NUMORP
          JOIN E725CRE R ON R.CODEMP = O.CODEMP AND R.CODCRE = O.CODCRE
         WHERE C.CODEMP = :codemp
           AND C.CODORI = :codori
           AND C.SITORP IN ('A', 'L')
           AND O.MOVORP = 'S'
         ORDER BY R.DESCRE
        """,
            {"codemp": codemp, "codori": codori},
        )
        colunas = [coluna[0] for coluna in cursor.description]
        return [dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()]


def _buscar_ops_por_recurso(codemp, codcre, origem_componente="", codori=CODORI_PAINEL):
    # OPs e componentes do recurso selecionado.
    with cursor_oracle_erp() as cursor:
        cursor.execute(
            """
        SELECT
             oop.CODCRE MAQUINA,
             cop.CODEMP EMPRESA,
             cop.CODORI ORIGEM,
             cop.NUMORP OP,
             cop.NUMPRI PRIORIDADE,
             cop.SITORP SIT,
             CASE WHEN cop.DTRINI IS NULL OR EXTRACT(YEAR FROM cop.DTRINI) <= 1900 THEN NULL ELSE cop.DTRINI END DATINI,
             CASE WHEN cop.DTRFIM IS NULL OR EXTRACT(YEAR FROM cop.DTRFIM) <= 1900 THEN NULL ELSE cop.DTRFIM END DATFIM,
             cop.CODPRO SKU,
             produto.DESPRO DESCRICAO,
             cop.QTDPRV QTD_PREVISTO_OP,
             cop.QTDRE1 QTD_REALIZADO_OP,
             ROUND((cop.QTDRE1 / NULLIF(cop.QTDPRV, 0)) * 100, 2) PCTAVANCO_OP,
             qdo.UNIMED UM_PRODUTO,
             cmo.CODCMP COMPONENTE,
             cmo.CODDER DER_COMPONENTE,
             componente.DESPRO DESC_COMPONENTE,
             cmo.QTDPRV QTD_PREVISTO,
             cmo.QTDUTI QTD_UTILIZADO,
             cmo.UNIMED UM_COMPONENTE,
             ROUND((cmo.QTDUTI / NULLIF(cmo.QTDPRV, 0)) * 100, 2) PCTCONSUMO,
             CASE WHEN origem.CODORI IN ('230', '405', '410') THEN 'Bobina' ELSE origem.DESORI END ORIGEM_COMPONENTE
           FROM E900COP cop
           JOIN E900CMO cmo ON cmo.CODEMP = cop.CODEMP AND cmo.NUMORP = cop.NUMORP AND cmo.CODORI = cop.CODORI
           JOIN E900OOP oop ON oop.CODEMP = cop.CODEMP AND oop.CODORI = cop.CODORI AND oop.NUMORP = cop.NUMORP
           LEFT JOIN E075PRO produto ON produto.CODEMP = cop.CODEMP AND produto.CODPRO = cop.CODPRO
           LEFT JOIN E900QDO qdo ON qdo.CODEMP = cop.CODEMP AND qdo.CODORI = cop.CODORI AND qdo.NUMORP = cop.NUMORP
                                 AND qdo.CODPRO = cop.CODPRO AND qdo.PROORI = 'S'
           LEFT JOIN E075PRO componente ON componente.CODEMP = cmo.CODEMP AND componente.CODPRO = cmo.CODCMP
           LEFT JOIN E083ORI origem ON origem.CODEMP = componente.CODEMP AND origem.CODORI = componente.CODORI
          WHERE oop.CODEMP = :codemp
            AND oop.CODCRE = :codcre
            AND cop.CODORI = :codori
            AND cop.SITORP IN ('A', 'L')
            AND (:origem_componente IS NULL OR :origem_componente = ''
                 OR CASE WHEN origem.CODORI IN ('230', '405', '410') THEN 'Bobina' ELSE origem.DESORI END = :origem_componente)
          ORDER BY (CASE WHEN cop.NUMPRI > 0 THEN 0 ELSE 1 END), cop.NUMPRI, cop.NUMORP, cmo.SEQCMP
        """,
            {
                "codemp": codemp,
                "codcre": codcre,
                "codori": codori,
                "origem_componente": origem_componente,
            },
        )
        colunas = [coluna[0] for coluna in cursor.description]
        return [dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()]


def _listar_origens_componentes(codemp, codcre, codori=CODORI_PAINEL):
    # Origens disponíveis nos componentes da máquina.
    with cursor_oracle_erp() as cursor:
        cursor.execute(
            """
        SELECT DISTINCT
             CASE WHEN origem.CODORI IN ('230', '405', '410') THEN 'Bobina' ELSE origem.DESORI END ORIGEM_COMPONENTE
          FROM E900COP cop
          JOIN E900CMO cmo ON cmo.CODEMP = cop.CODEMP AND cmo.CODORI = cop.CODORI AND cmo.NUMORP = cop.NUMORP
          JOIN E900OOP oop ON oop.CODEMP = cop.CODEMP AND oop.CODORI = cop.CODORI AND oop.NUMORP = cop.NUMORP
          LEFT JOIN E075PRO componente ON componente.CODEMP = cmo.CODEMP AND componente.CODPRO = cmo.CODCMP
          LEFT JOIN E083ORI origem ON origem.CODEMP = componente.CODEMP AND origem.CODORI = componente.CODORI
         WHERE oop.CODEMP = :codemp
           AND oop.CODCRE = :codcre
           AND cop.CODORI = :codori
           AND cop.SITORP IN ('A', 'L')
           AND origem.DESORI IS NOT NULL
         ORDER BY ORIGEM_COMPONENTE
        """,
            {"codemp": codemp, "codcre": codcre, "codori": codori},
        )
        return [linha[0] for linha in cursor.fetchall()]


def _buscar_ultimo_apontamento_por_ops(codemp, numorps):
    # Último apontamento de cada OP.
    if not numorps:
        return []
    placeholders = ", ".join(f":op{i}" for i in range(len(numorps)))
    params = {"codemp": codemp}
    params.update({f"op{i}": numorp for i, numorp in enumerate(numorps)})
    with cursor_oracle_erp() as cursor:
        cursor.execute(
            f"""
        SELECT NUMORP,
               MAX(
                 CASE WHEN FIMORP = 'S' THEN DATREA + (HORREA / 1440) ELSE DATINI + (HORINI / 1440) END
               ) ULTIMO_APONTAMENTO
          FROM E900EOQ
         WHERE CODEMP = :codemp
           AND NUMORP IN ({placeholders})
         GROUP BY NUMORP
        """,
            params,
        )
        colunas = [coluna[0] for coluna in cursor.description]
        return [dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()]


def _buscar_componentes_op(codemp, codori, numorp):
    # Componentes da OP consultada no WMS.
    with cursor_oracle_erp() as cursor:
        cursor.execute(
            """
        SELECT
             cmo.CODETG,
             cmo.SEQCMP,
             cmo.CODCMP,
             cmo.CODDER,
             cmo.QTDPRV,
             cmo.QTDUTI
           FROM E900CMO cmo
          WHERE cmo.CODEMP = :codemp
            AND cmo.CODORI = :codori
            AND cmo.NUMORP = :numorp
          ORDER BY cmo.SEQCMP
        """,
            {"codemp": codemp, "codori": codori, "numorp": numorp},
        )
        colunas = [coluna[0] for coluna in cursor.description]
        return [dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()]


def _buscar_bobinas_wms(sku, qtd_necessaria):
    # Bobinas disponíveis no WMS para o saldo necessário.
    with cursor_oracle_erp() as cursor:
        cursor.execute(
            """
        SELECT
             ID LOTE,
             LOC ENDERECO,
             LOT ID,
             QTY QTD,
             SUM(QTY) OVER (ORDER BY QTY DESC ROWS UNBOUNDED PRECEDING) QTD_ACUMULADA
          FROM wmwhse1.vITLotxLocxId_Lottables_XC@SQLDBLINK
         WHERE sku = :sku
           AND LOC <> 'P1BJ27'
         ORDER BY QTY DESC
        """,
            {"sku": sku},
        )
        colunas = [coluna[0] for coluna in cursor.description]
        linhas = [dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()]
        linhas_necessarias = [
            linha for linha in linhas if linha["QTD_ACUMULADA"] - linha["QTD"] < qtd_necessaria
        ]
        return linhas_necessarias, len(linhas)


def _buscar_historico_lote(codemp, codori, numorp, codcmp, codder, codtns="90251"):
    # Movimentações de consumo do componente na OP.
    with cursor_oracle_erp() as cursor:
        cursor.execute(
            """
        SELECT
             E210MVP.CODLOT LOTE,
             E210MVP.CODDEP DEPOSITO,
             E210MVP.QTDMOV QTD,
             E210MVP.DATMOV DATA,
             E210MVP.SEQMOV SEQ,
             E210MVP.USURES || '-' || E099USU.NOMUSU USUARIO
           FROM E210MVP
           JOIN E099USU ON E099USU.CODEMP = E210MVP.CODEMP AND E099USU.CODUSU = E210MVP.USURES
          WHERE E210MVP.CODEMP = :codemp
            AND E210MVP.CODPRO = :codcmp
            AND NVL(TRIM(E210MVP.CODDER), ' ') = :codder
            AND E210MVP.ORIORP = :codori
            AND E210MVP.NUMDOC = :numorp
            AND E210MVP.CODTNS = :codtns
          ORDER BY E210MVP.DATMOV DESC, E210MVP.SEQMOV
        """,
            {
                "codemp": codemp,
                "codcmp": codcmp,
                # No ERP, componente sem derivação é gravado como espaço.
                # String vazia é tratada pelo Oracle como NULL e não encontra
                # essas movimentações quando usada em uma comparação direta.
                "codder": (codder or "").strip() or " ",
                "codori": codori,
                "numorp": numorp,
                "codtns": codtns,
            },
        )
        colunas = [coluna[0] for coluna in cursor.description]
        return [dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()]


def _montar_sku_componente(codcmp, codder):
    """Monta o SKU com a derivação."""
    der = (codder or "").strip()
    return f"{codcmp}-{der}" if der else str(codcmp)


def _classificar_situacao(datini, datfim):
    """Classifica a OP como atual ou próxima."""
    return "ATUAL" if datini and not datfim else "PROXIMA"


def _ja_finalizada_pelo_realizado(qtd_previsto, qtd_realizado):
    """Identifica OP concluída pelo realizado."""
    return qtd_previsto is not None and qtd_realizado is not None and qtd_realizado >= qtd_previsto


def _status_consumo(pct):
    if pct is None:
        return "ok"
    if pct > _LIMITE_CRITICO:
        return "critico"
    if pct >= _LIMITE_ATENCAO:
        return "atencao"
    return "ok"


def _calcular_percentual_consumo(qtd_previsto, qtd_utilizado):
    if not qtd_previsto:
        return None
    return round((qtd_utilizado or 0) / qtd_previsto * 100, 2)


def _como_datetime(valor):
    """Converte o valor do Oracle para data e hora."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(valor)[: len(formato) + 2].strip(), formato)
        except ValueError:
            continue
    return None


def _identificar_finalizadas_por_inatividade(ops_atuais, ultimos_apontamentos):
    """Identifica OPs atuais sem movimentação recente."""
    ultimo_por_op = {}
    for linha in ultimos_apontamentos:
        valor = _como_datetime(linha.get("ULTIMO_APONTAMENTO"))
        if valor is not None:
            ultimo_por_op[linha["NUMORP"]] = valor

    agora = datetime.now()
    finalizadas = set()

    for op in ops_atuais:
        ultimo = ultimo_por_op.get(op["OP"])
        if ultimo is None or (agora - ultimo) <= _LIMITE_INATIVIDADE:
            continue

        existe_outra_mais_recente = any(
            outra["OP"] != op["OP"]
            and ultimo_por_op.get(outra["OP"]) is not None
            and ultimo_por_op[outra["OP"]] > ultimo
            for outra in ops_atuais
        )
        if existe_outra_mais_recente:
            finalizadas.add(op["OP"])

    return finalizadas


def _ordenar_ops(ops):
    """Ordena OPs por situação e prioridade. NUMPRI = 0 é 'sem prioridade
    definida' no ERP (a prioridade real começa em 1), então vai para o final,
    junto com as OPs sem prioridade nenhuma."""
    return sorted(
        ops,
        key=lambda op: (
            0 if op["SITUACAO"] == "ATUAL" else 1,
            op["PRIORIDADE"] if op["PRIORIDADE"] not in (None, 0) else float("inf"),
            op["OP"],
        ),
    )


def _montar_ops(codemp, codcre, origem_componente=""):
    """Agrupa os componentes por OP."""
    linhas = _buscar_ops_por_recurso(codemp, codcre, origem_componente)

    ops_por_numero = {}
    for linha in linhas:
        numero = linha["OP"]
        if numero not in ops_por_numero:
            ops_por_numero[numero] = {
                "MAQUINA": linha["MAQUINA"],
                "ORIGEM": linha["ORIGEM"],
                "OP": numero,
                "PRIORIDADE": linha["PRIORIDADE"],
                "SIT": linha["SIT"],
                "DATINI": linha["DATINI"],
                "DATFIM": linha["DATFIM"],
                "SKU": linha["SKU"],
                "DESCRICAO": linha["DESCRICAO"],
                "SITUACAO": _classificar_situacao(linha["DATINI"], linha["DATFIM"]),
                "QTD_PREVISTO_OP": linha["QTD_PREVISTO_OP"],
                "QTD_REALIZADO_OP": linha["QTD_REALIZADO_OP"],
                "PCTAVANCO_OP": linha["PCTAVANCO_OP"],
                "UM_PRODUTO": linha["UM_PRODUTO"],
                "_finalizada": _ja_finalizada_pelo_realizado(
                    linha["QTD_PREVISTO_OP"], linha["QTD_REALIZADO_OP"]
                ),
                "componentes": [],
            }

        pct = linha["PCTCONSUMO"]
        if pct is None:
            pct = _calcular_percentual_consumo(linha["QTD_PREVISTO"], linha["QTD_UTILIZADO"])

        ops_por_numero[numero]["componentes"].append(
            {
                "COMPONENTE": linha["COMPONENTE"],
                "DER_COMPONENTE": linha["DER_COMPONENTE"],
                "SKU_COMPONENTE": _montar_sku_componente(
                    linha["COMPONENTE"], linha["DER_COMPONENTE"]
                ),
                "DESC_COMPONENTE": linha["DESC_COMPONENTE"],
                "ORIGEM_COMPONENTE": linha["ORIGEM_COMPONENTE"],
                "QTD_PREVISTO": linha["QTD_PREVISTO"],
                "QTD_UTILIZADO": linha["QTD_UTILIZADO"],
                "UM_COMPONENTE": linha["UM_COMPONENTE"],
                "PCTCONSUMO": pct,
                # Mantém ponto decimal para a largura da barra.
                "PCT_LARGURA": f"{min(pct, 100):.2f}" if pct is not None else "0",
                "STATUS_CONSUMO": _status_consumo(pct),
            }
        )

    ops_abertas = [op for op in ops_por_numero.values() if not op["_finalizada"]]
    ops_atuais = [op for op in ops_abertas if op["SITUACAO"] == "ATUAL"]

    if len(ops_atuais) > 1:
        numorps = [op["OP"] for op in ops_atuais]
        ultimos = _buscar_ultimo_apontamento_por_ops(codemp, numorps)
        finalizadas_por_inatividade = _identificar_finalizadas_por_inatividade(ops_atuais, ultimos)
        if finalizadas_por_inatividade:
            ops_abertas = [op for op in ops_abertas if op["OP"] not in finalizadas_por_inatividade]

    for op in ops_abertas:
        op.pop("_finalizada", None)

    return _ordenar_ops(ops_abertas)


def _resolver_empresa(request):
    if not request.user.is_staff and getattr(request.user, "filial", None):
        empresa = request.user.filial.empresa
        empresas = Empresa.objects.filter(id=empresa.id)
        empresa_id = str(empresa.id)
    elif request.user.is_staff:
        empresas = Empresa.objects.all().order_by("nome")
        empresa_id = request.GET.get("empresa") or str(
            empresas.values_list("id", flat=True).first() or ""
        )
        empresa = Empresa.objects.filter(id=empresa_id).first()
    else:
        empresas = Empresa.objects.none()
        empresa_id = ""
        empresa = None
    return empresa, empresas, empresa_id


def _empresa_da_requisicao(request, empresa_id):
    if not str(empresa_id).isdigit():
        return None

    if request.user.is_staff:
        return Empresa.objects.filter(id=empresa_id).first()

    filial = getattr(request.user, "filial", None)
    if filial and str(filial.empresa_id) == str(empresa_id):
        return filial.empresa
    return None


@permissao_requerida("logistica.pode_visualizar_componentes_movimentar")
def componentes_movimentar_view(request):
    empresa, empresas, empresa_id = _resolver_empresa(request)
    codcre = request.GET.get("codcre", "").strip()
    origem_selecionada = request.GET.get("origem", "").strip()

    empresas_opcoes = [
        {
            "id": item.id,
            "codemp": item.codemp,
            "nome": item.nome,
            "selecionada": str(item.id) == empresa_id,
        }
        for item in empresas
    ]
    recursos = []
    atuais = []
    proximas = []
    origens_componente = []
    erro = None

    if empresa:
        try:
            recursos = _listar_recursos_erp(empresa.codemp)
            for recurso in recursos:
                recurso["SELECIONADO"] = str(recurso["CODCRE"]) == codcre
            if codcre:
                origens_componente = _listar_origens_componentes(empresa.codemp, codcre)
                ops = _montar_ops(empresa.codemp, codcre, origem_selecionada)
                atuais = [op for op in ops if op["SITUACAO"] == "ATUAL"]
                proximas = [op for op in ops if op["SITUACAO"] == "PROXIMA"]
        except Exception:
            logger.exception("Falha ao consultar o painel de componentes")
            erro = "Não foi possível consultar os componentes da máquina."

    origens_opcoes = [
        {
            "valor": origem,
            "selecionada": origem == origem_selecionada,
        }
        for origem in origens_componente
    ]
    return render(
        request,
        "setores/logistica/componentes_movimentar.html",
        {
            "empresas": empresas_opcoes,
            "empresa_id": empresa_id,
            "recursos": recursos,
            "codcre": codcre,
            "atuais": atuais,
            "proximas": proximas,
            "origens_componente": origens_opcoes,
            "origem_selecionada": origem_selecionada,
            "erro": erro,
        },
    )


@permissao_requerida("logistica.pode_visualizar_componentes_movimentar")
def historico_lote_componente(request):
    """Retorna os lotes baixados do componente."""
    empresa_id = request.GET.get("empresa", "")
    empresa = _empresa_da_requisicao(request, empresa_id)
    if not empresa:
        return JsonResponse({"erro": "Empresa inválida ou sem acesso."}, status=403)

    codori = request.GET.get("codori", "")
    numorp = request.GET.get("numorp", "")
    codcmp = request.GET.get("codcmp", "")
    codder = request.GET.get("codder", "")

    try:
        linhas = _buscar_historico_lote(empresa.codemp, codori, numorp, codcmp, codder)
        return JsonResponse({"linhas": linhas})
    except Exception:
        logger.exception("Falha ao consultar lotes do componente")
        return JsonResponse({"erro": "Não foi possível consultar os lotes."}, status=500)


@permissao_requerida("logistica.pode_visualizar_componentes_movimentar")
def bobinas_disponiveis(request):
    """Retorna bobinas disponíveis no WMS."""
    empresa_id = request.GET.get("empresa", "")
    empresa = _empresa_da_requisicao(request, empresa_id)
    if not empresa:
        return JsonResponse({"erro": "Empresa inválida ou sem acesso."}, status=403)

    codori = request.GET.get("codori", "")
    numorp = request.GET.get("numorp", "")
    codcmp = request.GET.get("codcmp", "")
    codder = (request.GET.get("codder", "") or "").strip()

    try:
        componente = next(
            (
                c
                for c in _buscar_componentes_op(empresa.codemp, codori, numorp)
                if str(c["CODCMP"]) == codcmp and (c["CODDER"] or "").strip() == codder
            ),
            None,
        )
        if componente is None:
            return JsonResponse({"linhas": []})

        qtd_necessaria = (componente["QTDPRV"] or 0) - (componente["QTDUTI"] or 0)
        if qtd_necessaria <= 0:
            return JsonResponse({"linhas": []})

        sku = _montar_sku_componente(componente["CODCMP"], componente["CODDER"])
        linhas, total_linhas = _buscar_bobinas_wms(sku, qtd_necessaria)
        return JsonResponse({"linhas": linhas, "total_linhas": total_linhas})
    except Exception:
        logger.exception("Falha ao consultar bobinas disponíveis no WMS")
        return JsonResponse({"erro": "Não foi possível consultar as bobinas no WMS."}, status=500)
