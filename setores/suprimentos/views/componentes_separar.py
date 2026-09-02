import logging

from django.core.paginator import Paginator
from django.shortcuts import render

from accounts.models import Empresa
from SIGMA.autorizacao import permissao_requerida
from SIGMA.integracoes.oracle import cursor_oracle_erp

logger = logging.getLogger(__name__)

# Depósitos que representam o estoque já disponível na planta (piso de fábrica).
# Saldo nesses depósitos não precisa ser separado/movimentado novamente.
DEPOSITOS_PLANTA = ("P01.01", "P01.02")

# Depósitos de almoxarifado (ex.: 01.03 Alpino), só para informação — mostra
# quanto existe ali para ajudar quem vai separar, mas NÃO entra no cálculo de
# necessidade/rateio. Novo depósito entra aqui só por decisão do desenvolvedor
# sênior.
DEPOSITOS_ESTOQUE = ("01.03",)

# Recurso de produção externa: o consumo não passa pelo piso de fábrica,
# então não tem separação de componentes — sai da consulta inteira.
RECURSO_PRODUCAO_EXTERNA = "930"

# Escopo padrão da tela: só componentes dessas famílias (matéria-prima e
# insumos de produção). Restringe o volume de dados já na consulta ao ERP.
FAMILIAS_ESCOPO = (
    "61",
    "62",
    "629",
    "63",
    "631",
    "64",
    "66",
    "67",
    "68",
    "70",
    "71",
    "72",
    "73",
    "731",
)

ITENS_POR_PAGINA = 30

SITUACOES_OP = {"A": "Aberta", "L": "Liberada"}

MODOS_AGRUPAMENTO = ("juntar", "prioridade", "recurso")


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


def _montar_sku_componente(codcmp, codder):
    der = (codder or "").strip()
    return f"{codcmp}-{der}" if der else str(codcmp)


def _combinar_descricao(descricao, derivacao):
    descricao = descricao or ""
    derivacao = (derivacao or "").strip()
    return f"{descricao} - {derivacao}" if derivacao else descricao


def formatar_quantidade(valor):
    """Mostra 2 casas quando elas já carregam informação; só usa as 5 quando
    as 2 primeiras são zero e a diferença aparece somente nas últimas 3."""
    valor = float(valor or 0)
    arredondado_2 = round(valor, 2)
    parte_decimal_2 = abs(arredondado_2 - int(arredondado_2))
    if parte_decimal_2 > 1e-9:
        return f"{arredondado_2:.2f}"
    arredondado_5 = round(valor, 5)
    if abs(arredondado_5 - arredondado_2) < 1e-9:
        return f"{arredondado_2:.2f}"
    return f"{arredondado_5:.5f}"


def _etiqueta_a_separar(valor, tem_estoque):
    """Destaque do "A separar", no estilo da coluna Qtd Prod. dos logs de
    apontamento (fundo suave na célula): verde quando nada falta; azul quando
    falta mas há saldo no almoxarifado (informativo); vermelho quando falta e
    não há estoque."""
    if valor <= 0:
        cor = "sucesso"
    elif tem_estoque:
        cor = "informacao"
    else:
        cor = "erro"
    return f"bg-{cor}-sutil text-{cor}-base"


def _buscar_necessidade_ops(codemp):
    """Componentes com consumo pendente nas OPs abertas/em andamento."""
    with cursor_oracle_erp() as cursor:
        placeholders_familia = ", ".join(f":fam{i}" for i in range(len(FAMILIAS_ESCOPO)))
        params = {"codemp": codemp, "recurso_externo": RECURSO_PRODUCAO_EXTERNA}
        params.update({f"fam{i}": familia for i, familia in enumerate(FAMILIAS_ESCOPO)})
        cursor.execute(
            f"""
        SELECT
             oop.CODCRE,
             cre.DESCRE,
             cop.CODORI,
             cop.NUMORP,
             cop.NUMPRI,
             cop.SITORP,
             qdo.QTDPRV QTD_PREVISTO_OP,
             qdo.QTDRE1 QTD_REALIZADO_OP,
             qdo.UNIMED UM_PRODUTO,
             produto_op.DESPRO DESC_PRODUTO_OP,
             der_op.DESDER DESC_DER_OP,
             cmo.CODCMP,
             cmo.CODDER,
             cmo.CODDEP,
             produto.DESPRO,
             NVL(der.DESDER, ' ') DESDER,
             produto.CODFAM,
             fam.DESFAM,
             cmo.UNIMED,
             cmo.QTDPRV,
             cmo.QTDUTI
           FROM E900COP cop
           JOIN E900CMO cmo ON cmo.CODEMP = cop.CODEMP AND cmo.CODORI = cop.CODORI AND cmo.NUMORP = cop.NUMORP
           JOIN E900OOP oop ON oop.CODEMP = cop.CODEMP AND oop.CODORI = cop.CODORI AND oop.NUMORP = cop.NUMORP AND oop.CODETG = cmo.CODETG
           JOIN E725CRE cre ON cre.CODEMP = oop.CODEMP AND cre.CODCRE = oop.CODCRE
           LEFT JOIN E075PRO produto ON produto.CODEMP = cmo.CODEMP AND produto.CODPRO = cmo.CODCMP
           LEFT JOIN E075DER der ON der.CODEMP = cmo.CODEMP AND der.CODPRO = cmo.CODCMP AND der.CODDER = cmo.CODDER
           LEFT JOIN E012FAM fam ON fam.CODEMP = produto.CODEMP AND fam.CODFAM = produto.CODFAM
           LEFT JOIN (
                SELECT CODEMP, CODORI, NUMORP, CODPRO,
                       MIN(UNIMED) UNIMED, SUM(QTDPRV) QTDPRV, SUM(QTDRE1) QTDRE1,
                       MAX(CODDER) KEEP (DENSE_RANK FIRST ORDER BY QTDPRV DESC) CODDER_PRINCIPAL
                  FROM E900QDO
                 WHERE PROORI = 'S'
                 GROUP BY CODEMP, CODORI, NUMORP, CODPRO
           ) qdo ON qdo.CODEMP = cop.CODEMP AND qdo.CODORI = cop.CODORI AND qdo.NUMORP = cop.NUMORP AND qdo.CODPRO = cop.CODPRO
           LEFT JOIN E075PRO produto_op ON produto_op.CODEMP = qdo.CODEMP AND produto_op.CODPRO = qdo.CODPRO
           LEFT JOIN E075DER der_op ON der_op.CODEMP = qdo.CODEMP AND der_op.CODPRO = qdo.CODPRO AND der_op.CODDER = qdo.CODDER_PRINCIPAL
          WHERE cop.CODEMP = :codemp
            AND cop.SITORP IN ('A', 'L')
            AND cmo.QTDPRV > NVL(cmo.QTDUTI, 0)
            AND TRIM(oop.CODCRE) <> :recurso_externo
            AND TRIM(produto.CODFAM) IN ({placeholders_familia})
          ORDER BY (CASE WHEN cop.NUMPRI > 0 THEN 0 ELSE 1 END), cop.NUMPRI, cop.NUMORP, cmo.SEQCMP
        """,
            params,
        )
        colunas = [coluna[0] for coluna in cursor.description]
        return [dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()]


def _buscar_estoque_componentes(codemp, codigos_componentes):
    """Saldo em estoque de todos os depósitos, por componente/derivação/depósito.

    Não filtra por depósito porque o depósito específico de uma OP (E900CMO.CODDEP)
    pode não ser um dos depósitos de planta configurados em DEPOSITOS_PLANTA."""
    if not codigos_componentes:
        return []
    with cursor_oracle_erp() as cursor:
        placeholders = ", ".join(f":cod{i}" for i in range(len(codigos_componentes)))
        params = {"codemp": codemp}
        params.update({f"cod{i}": codigo for i, codigo in enumerate(codigos_componentes)})
        cursor.execute(
            f"""
        SELECT
             est.CODPRO,
             NVL(est.CODDER, ' ') CODDER,
             TRIM(est.CODDEP) CODDEP,
             SUM(est.QTDEST) QTDEST
           FROM E210EST est
          WHERE est.CODEMP = :codemp
            AND est.CODPRO IN ({placeholders})
          GROUP BY est.CODPRO, NVL(est.CODDER, ' '), TRIM(est.CODDEP)
        """,
            params,
        )
        colunas = [coluna[0] for coluna in cursor.description]
        return [dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()]


def _buscar_nomes_depositos(codemp):
    """Nome cadastrado de cada depósito, para exibir junto ao código."""
    with cursor_oracle_erp() as cursor:
        cursor.execute(
            """
        SELECT TRIM(CODDEP) CODDEP, DESDEP
          FROM E205DEP
         WHERE CODEMP = :codemp
        """,
            {"codemp": codemp},
        )
        return {linha[0]: linha[1] for linha in cursor.fetchall()}


def _opcoes_recursos(linhas):
    vistos = {linha["CODCRE"]: linha["DESCRE"] for linha in linhas}
    return sorted(
        ({"codcre": codcre, "descre": descre} for codcre, descre in vistos.items()),
        key=lambda item: item["descre"] or "",
    )


def _opcoes_prioridades(linhas):
    return sorted({linha["NUMPRI"] for linha in linhas if linha["NUMPRI"] is not None})


def _opcoes_familias(linhas):
    vistos = {}
    for linha in linhas:
        codfam = (linha["CODFAM"] or "").strip()
        if codfam and codfam not in vistos:
            vistos[codfam] = (linha["DESFAM"] or "").strip() or codfam
    return sorted(
        ({"codfam": codfam, "desfam": desfam} for codfam, desfam in vistos.items()),
        key=lambda item: item["desfam"],
    )


def _filtrar_linhas(linhas, codcres, familias, numpri):
    resultado = linhas
    if codcres:
        codcres = set(codcres)
        resultado = [linha for linha in resultado if str(linha["CODCRE"]) in codcres]
    if familias:
        familias = set(familias)
        resultado = [linha for linha in resultado if (linha["CODFAM"] or "").strip() in familias]
    if numpri:
        resultado = [linha for linha in resultado if str(linha["NUMPRI"]) == numpri]
    return resultado


def _montar_necessidade_separacao(
    linhas,
    estoque_componentes,
    nomes_depositos=None,
    separar_prioridades=False,
    separar_recursos=False,
    depositos_planta=None,
):
    nomes_depositos = nomes_depositos or {}
    # Depósitos de planta que entram no rateio da tabela principal. O detalhe
    # do modal continua mostrando o saldo de todos os depósitos de planta.
    depositos_planta = tuple(depositos_planta) if depositos_planta else DEPOSITOS_PLANTA
    estoque_total_por_chave = {}
    estoque_detalhe_por_chave = {}
    estoque_geral_total_por_chave = {}
    estoque_geral_detalhe_por_chave = {}
    estoque_por_deposito_especifico = {}
    for linha in estoque_componentes:
        codder = (linha["CODDER"] or "").strip()
        coddep = (linha["CODDEP"] or "").strip()
        saldo = float(linha["QTDEST"] or 0)
        estoque_por_deposito_especifico[(linha["CODPRO"], codder, coddep)] = saldo
        chave = (linha["CODPRO"], codder)

        if coddep in DEPOSITOS_PLANTA:
            estoque_detalhe_por_chave.setdefault(chave, {})[coddep] = saldo
            if coddep in depositos_planta:
                estoque_total_por_chave[chave] = estoque_total_por_chave.get(chave, 0.0) + saldo

        if coddep in DEPOSITOS_ESTOQUE:
            estoque_geral_total_por_chave[chave] = (
                estoque_geral_total_por_chave.get(chave, 0.0) + saldo
            )
            estoque_geral_detalhe_por_chave.setdefault(chave, {})[coddep] = saldo

    # Fase 1: agrega sempre por componente/derivação, nunca dividido por
    # prioridade ou recurso aqui. O rateio de estoque precisa considerar TODAS
    # as OPs do componente de uma vez, na ordem de prioridade — se dividisse
    # antes, cada grupo descontaria o mesmo saldo da planta mais de uma vez.
    componentes = {}
    for linha in linhas:
        codder = (linha["CODDER"] or "").strip()
        chave = (linha["CODCMP"], codder)
        necessidade_op = max(float(linha["QTDPRV"] or 0) - float(linha["QTDUTI"] or 0), 0.0)

        if chave not in componentes:
            componentes[chave] = {
                "codcmp": linha["CODCMP"],
                "codder": codder,
                "sku": _montar_sku_componente(linha["CODCMP"], codder),
                "descricao": _combinar_descricao(linha["DESPRO"], linha["DESDER"]),
                "codfam": (linha["CODFAM"] or "").strip(),
                "desfam": (linha["DESFAM"] or "").strip(),
                "unimed": linha["UNIMED"],
                "_ops": {},
            }

        item = componentes[chave]
        op_info = item["_ops"].setdefault(
            linha["NUMORP"],
            {
                "numorp": linha["NUMORP"],
                "numpri": linha["NUMPRI"],
                "codori": linha["CODORI"],
                "sitorp": linha["SITORP"],
                "situacao": SITUACOES_OP.get(linha["SITORP"], linha["SITORP"]),
                "qtd_previsto_op": float(linha["QTD_PREVISTO_OP"] or 0),
                "qtd_realizado_op": float(linha["QTD_REALIZADO_OP"] or 0),
                "um_produto": linha["UM_PRODUTO"],
                "descricao_produto": _combinar_descricao(
                    linha["DESC_PRODUTO_OP"], linha["DESC_DER_OP"]
                ),
                "qtd_previsto_componente": 0.0,
                "qtd_consumido_componente": 0.0,
                "necessidade": 0.0,
                "codcre": linha["CODCRE"],
                "descre": linha["DESCRE"],
                "coddep": (linha["CODDEP"] or "").strip(),
            },
        )
        op_info["qtd_previsto_componente"] += float(linha["QTDPRV"] or 0)
        op_info["qtd_consumido_componente"] += float(linha["QTDUTI"] or 0)
        op_info["necessidade"] += necessidade_op

    resultado = []
    for item in componentes.values():
        chave_estoque = (item["codcmp"], item["codder"])
        estoque = estoque_total_por_chave.get(chave_estoque, 0.0)

        ops_ordenadas = sorted(
            item["_ops"].values(),
            key=lambda op: (
                op["numpri"] if op["numpri"] not in (None, 0) else float("inf"),
                op["numorp"],
            ),
        )

        detalhe_estoque = estoque_detalhe_por_chave.get(chave_estoque, {})
        estoque_detalhe = [
            {
                "deposito": deposito,
                "nome": nomes_depositos.get(deposito, ""),
                "saldo": detalhe_estoque.get(deposito, 0.0),
            }
            for deposito in DEPOSITOS_PLANTA
        ]

        # Estoque geral (almoxarifado) — só informativo, não entra no rateio
        # nem desconta da necessidade real.
        estoque_geral = estoque_geral_total_por_chave.get(chave_estoque, 0.0)
        detalhe_estoque_geral = estoque_geral_detalhe_por_chave.get(chave_estoque, {})
        estoque_geral_detalhe = [
            {
                "deposito": deposito,
                "nome": nomes_depositos.get(deposito, ""),
                "saldo": detalhe_estoque_geral.get(deposito, 0.0),
            }
            for deposito in DEPOSITOS_ESTOQUE
        ]

        # Rateia o estoque pelas OPs na ordem de prioridade: a OP mais urgente
        # consome o saldo disponível primeiro, sobrando o restante para as demais.
        # Feito duas vezes: uma vez contra o total da planta ("a_separar") e outra
        # vez contra o saldo do depósito específico de cada OP ("estoque_deposito"),
        # pois OPs diferentes podem apontar para depósitos diferentes.
        saldo_restante = estoque
        saldo_restante_por_deposito = {}
        for op in ops_ordenadas:
            consumo_do_saldo = min(op["necessidade"], saldo_restante)
            op["a_separar"] = op["necessidade"] - consumo_do_saldo
            op["em_planta"] = consumo_do_saldo
            op["classe_a_separar"] = _etiqueta_a_separar(op["a_separar"], estoque_geral > 0)
            saldo_restante -= consumo_do_saldo

            coddep = op["coddep"]
            if coddep not in saldo_restante_por_deposito:
                saldo_restante_por_deposito[coddep] = estoque_por_deposito_especifico.get(
                    (item["codcmp"], item["codder"], coddep), 0.0
                )
            op["estoque_deposito"] = saldo_restante_por_deposito[coddep]
            consumo_deposito = min(op["necessidade"], saldo_restante_por_deposito[coddep])
            saldo_restante_por_deposito[coddep] -= consumo_deposito

        # Componente totalmente coberto pelo estoque da planta não entra na
        # tela (não há nada a separar). Quando há necessidade, porém, TODAS as
        # OPs aparecem — inclusive as com "A separar" zero — para dar
        # visibilidade de quem consumiu o rateio da planta.
        if sum(op["a_separar"] for op in ops_ordenadas) <= 0:
            continue

        # Fase 2: agrupa as OPs (já com o rateio correto da fase 1) conforme o
        # modo de visualização escolhido. Cada linha exibida apenas soma o que
        # já foi calculado — o estoque não é descontado de novo aqui.
        if not separar_prioridades and not separar_recursos:
            grupos = {(): ops_ordenadas}
        else:
            grupos = {}
            for op in ops_ordenadas:
                chave_grupo = []
                if separar_prioridades:
                    chave_grupo.append(op["numpri"])
                if separar_recursos:
                    chave_grupo.append(op["codcre"])
                grupos.setdefault(tuple(chave_grupo), []).append(op)

        for ops_do_grupo in grupos.values():
            necessidade_op_grupo = sum(op["necessidade"] for op in ops_do_grupo)
            necessidade_real_grupo = sum(op["a_separar"] for op in ops_do_grupo)

            prioridades_grupo = [op["numpri"] for op in ops_do_grupo if op["numpri"] is not None]
            # NUMPRI = 0 é "sem prioridade definida" no ERP; só conta como prioridade
            # real quando maior que zero. Se o grupo só tiver OPs sem prioridade,
            # mantém 0 como representante (não há prioridade real para mostrar).
            prioridades_reais_grupo = [numpri for numpri in prioridades_grupo if numpri > 0]
            estoque_grupo = necessidade_op_grupo - necessidade_real_grupo

            novo_item = {chave: valor for chave, valor in item.items() if chave != "_ops"}
            novo_item["necessidade_op"] = necessidade_op_grupo
            novo_item["estoque_planta"] = estoque_grupo
            novo_item["necessidade_real"] = necessidade_real_grupo
            novo_item["necessidade_op_fmt"] = formatar_quantidade(necessidade_op_grupo)
            novo_item["estoque_planta_fmt"] = formatar_quantidade(estoque_grupo)
            novo_item["necessidade_real_fmt"] = formatar_quantidade(necessidade_real_grupo)
            novo_item["classe_a_separar"] = _etiqueta_a_separar(
                necessidade_real_grupo, estoque_geral > 0
            )
            novo_item["prioridade"] = (
                min(prioridades_reais_grupo)
                if prioridades_reais_grupo
                else (0 if prioridades_grupo else None)
            )
            novo_item["prioridades"] = sorted(set(prioridades_grupo))
            novo_item["recursos"] = sorted(
                {f"{op['codcre']} - {op['descre']}" for op in ops_do_grupo}
            )
            # O modal sempre lista TODAS as OPs do componente — o agrupamento
            # por prioridade/recurso divide apenas a tabela principal.
            novo_item["ops"] = ops_ordenadas
            novo_item["estoque_detalhe"] = estoque_detalhe
            novo_item["estoque_geral"] = estoque_geral
            novo_item["estoque_geral_fmt"] = formatar_quantidade(estoque_geral)
            novo_item["estoque_geral_detalhe"] = estoque_geral_detalhe
            resultado.append(novo_item)

    resultado.sort(
        key=lambda item: (
            item["prioridade"] if item["prioridade"] not in (None, 0) else float("inf"),
            item["codcmp"],
        )
    )
    return resultado


@permissao_requerida("suprimentos.pode_visualizar_componentes_separar")
def componentes_separar(request):
    empresa, empresas, empresa_id = _resolver_empresa(request)

    codcres_selecionados = [v.strip() for v in request.GET.getlist("codcre") if v.strip()]
    familias_selecionadas = [v.strip() for v in request.GET.getlist("familia") if v.strip()]
    componentes_selecionados = [v.strip() for v in request.GET.getlist("componente") if v.strip()]
    depositos_planta_selecionados = [
        v.strip() for v in request.GET.getlist("deposito_planta") if v.strip()
    ]
    # Valor desconhecido na lista é ignorado; sem seleção válida, o rateio
    # considera todos os depósitos de planta (comportamento padrão).
    depositos_planta_rateio = (
        tuple(codigo for codigo in DEPOSITOS_PLANTA if codigo in depositos_planta_selecionados)
        or DEPOSITOS_PLANTA
    )
    modo_agrupamento = request.GET.get("modo_agrupamento", "juntar").strip()

    numpri_filtro = ""
    if modo_agrupamento not in MODOS_AGRUPAMENTO:
        numpri_filtro = modo_agrupamento
        modo_agrupamento = "prioridade"

    empresas_opcoes = [
        {
            "id": item.id,
            "codemp": item.codemp,
            "nome": item.nome,
            "selecionada": str(item.id) == empresa_id,
        }
        for item in empresas
    ]

    recursos_opcoes = []
    familias_opcoes = []
    prioridades_opcoes = []
    componentes_opcoes = []
    necessidades_pagina = []
    total_necessidades = 0
    nomes_depositos = {}
    imprimir = request.GET.get("imprimir") == "1"
    erro = None

    params_paginacao = request.GET.copy()
    params_paginacao.pop("page", None)
    querystring = params_paginacao.urlencode()

    if empresa:
        try:
            linhas = _buscar_necessidade_ops(empresa.codemp)
            recursos_opcoes = _opcoes_recursos(linhas)
            familias_opcoes = _opcoes_familias(linhas)
            prioridades_opcoes = _opcoes_prioridades(linhas)

            linhas_filtradas = _filtrar_linhas(
                linhas, codcres_selecionados, familias_selecionadas, numpri_filtro
            )
            codigos_componentes = sorted({linha["CODCMP"] for linha in linhas_filtradas})
            estoque_componentes = _buscar_estoque_componentes(empresa.codemp, codigos_componentes)
            nomes_depositos = _buscar_nomes_depositos(empresa.codemp)
            necessidades = _montar_necessidade_separacao(
                linhas_filtradas,
                estoque_componentes,
                nomes_depositos,
                separar_prioridades=(modo_agrupamento == "prioridade"),
                separar_recursos=(modo_agrupamento == "recurso"),
                depositos_planta=depositos_planta_rateio,
            )

            componentes_opcoes = sorted(
                ({"sku": item["sku"], "descricao": item["descricao"]} for item in necessidades),
                key=lambda item: item["descricao"] or item["sku"],
            )
            # Remove duplicatas mantendo a ordem (o mesmo sku pode repetir quando
            # o agrupamento está separado por prioridade ou por recurso).
            componentes_opcoes = list({item["sku"]: item for item in componentes_opcoes}.values())

            if componentes_selecionados:
                selecionados = set(componentes_selecionados)
                necessidades = [item for item in necessidades if item["sku"] in selecionados]

            total_necessidades = len(necessidades)
            itens_por_pagina = (
                total_necessidades if imprimir and total_necessidades else ITENS_POR_PAGINA
            )
            paginador = Paginator(necessidades, itens_por_pagina)
            necessidades_pagina = paginador.get_page(1 if imprimir else request.GET.get("page"))
            for indice, item in enumerate(necessidades_pagina):
                item["ops_id"] = f"ops-{indice}"
                item["estoque_id"] = f"estoque-{indice}"
                item["estoque_geral_id"] = f"estoquegeral-{indice}"
        except Exception:
            logger.exception("Falha ao consultar a necessidade de separação de componentes")
            erro = "Não foi possível consultar a necessidade de separação de componentes."

    for recurso in recursos_opcoes:
        recurso["selecionado"] = str(recurso["codcre"]) in codcres_selecionados
    for opcao_familia in familias_opcoes:
        opcao_familia["selecionada"] = opcao_familia["codfam"] in familias_selecionadas
    prioridades_opcoes = [
        {"valor": valor, "selecionada": str(valor) == numpri_filtro} for valor in prioridades_opcoes
    ]
    for componente in componentes_opcoes:
        componente["selecionado"] = componente["sku"] in componentes_selecionados
    depositos_planta_todos = depositos_planta_rateio == DEPOSITOS_PLANTA
    depositos_planta_opcoes = [
        {
            "codigo": codigo,
            "nome": nomes_depositos.get(codigo, ""),
            # "Todos" (padrão) nasce sem nada marcado, igual aos outros
            # filtros — só aparece checked quando há restrição explícita.
            "selecionada": not depositos_planta_todos and codigo in depositos_planta_rateio,
        }
        for codigo in DEPOSITOS_PLANTA
    ]

    return render(
        request,
        "setores/suprimentos/componentes_separar.html",
        {
            "empresas": empresas_opcoes,
            "empresa_id": empresa_id,
            "recursos": recursos_opcoes,
            "codcres_selecionados": codcres_selecionados,
            "modo_agrupamento": modo_agrupamento,
            "numpri_filtro": numpri_filtro,
            "prioridades": prioridades_opcoes,
            "familias": familias_opcoes,
            "familias_selecionadas": familias_selecionadas,
            "componentes_opcoes": componentes_opcoes,
            "componentes_selecionados": componentes_selecionados,
            "depositos_planta_opcoes": depositos_planta_opcoes,
            "depositos_planta_selecionados": depositos_planta_rateio,
            "depositos_planta_todos": depositos_planta_todos,
            "necessidades": necessidades_pagina,
            "total_necessidades": total_necessidades,
            "querystring": querystring,
            "erro": erro,
        },
    )
