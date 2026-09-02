import logging
from datetime import datetime, time

from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from accounts.models import ParametrosFilial, Recurso
from setores.qualidade.models import LiberacaoLote
from SIGMA.integracoes.oracle import cursor_oracle_alchemy, cursor_oracle_erp

logger = logging.getLogger(__name__)

# Rastreamento é público por decisão de negócio (QR da etiqueta é bipado
# sem login), então a proteção contra abuso é por limitação de requisições
# por IP na janela, via cache padrão do Django.
RASTREIO_JANELA_SEGUNDOS = 60
RASTREIO_LIMITE_JANELA = 30


def _ip_do_cliente(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "desconhecido")


def _esta_acima_do_limite_rastreio(request):
    chave = f"rastreio_lote:{_ip_do_cliente(request)}"
    contagem = cache.get(chave, 0)
    if contagem >= RASTREIO_LIMITE_JANELA:
        return True
    if contagem == 0:
        cache.add(chave, 1, RASTREIO_JANELA_SEGUNDOS)
    else:
        cache.set(chave, contagem + 1, RASTREIO_JANELA_SEGUNDOS)
    return False


def _parse_data_hora_movimento(data_valor, hora_valor=None):
    if isinstance(data_valor, datetime):
        base = data_valor
    elif (
        hasattr(data_valor, "year") and hasattr(data_valor, "month") and hasattr(data_valor, "day")
    ):
        base = datetime.combine(data_valor, time.min)
    else:
        texto = str(data_valor or "").strip()
        base = None
        for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                base = datetime.strptime(texto[:10], formato)
                break
            except ValueError:
                pass
        if base is None:
            return None

    hora_texto = str(hora_valor or "").strip()
    if hora_texto:
        try:
            if hora_texto.isdigit():
                minutos = int(hora_texto)
                base = base.replace(hour=minutos // 60, minute=minutos % 60, second=0)
            else:
                partes = [int(parte) for parte in hora_texto.split(":")]
                base = base.replace(
                    hour=partes[0] if len(partes) > 0 else 0,
                    minute=partes[1] if len(partes) > 1 else 0,
                    second=partes[2] if len(partes) > 2 else 0,
                )
        except TypeError, ValueError:
            pass

    return timezone.make_aware(base) if timezone.is_naive(base) else base


def _adicionar_evento(
    eventos,
    data_hora,
    tipo,
    titulo,
    descricao="",
    origem="",
    dados=None,
    ordem=0,
    data_hora_ordenacao=None,
    seqmov=None,
    tag_qualidade=None,
):
    eventos.append(
        {
            "data_hora": data_hora,
            "data_hora_ordenacao": data_hora_ordenacao or data_hora,
            "tipo": tipo,
            "titulo": titulo,
            "descricao": descricao,
            "origem": origem,
            "dados": dados or [],
            "ordem": ordem or 0,
            "seqmov": seqmov,
            "tag_qualidade": tag_qualidade,
        }
    )


def _data_hora_minuto(valor):
    if not valor:
        return None
    return valor.replace(second=0, microsecond=0)


def _prioridade_evento_no_minuto(item):
    if item.get("tipo") == "Qualidade":
        return 0
    if "ERP" in str(item.get("tipo") or ""):
        return 2
    return 1


def _descricao_entrada_saida(valor):
    valor = str(valor or "").strip().upper()
    if valor == "E":
        return "Entrada"
    if valor == "S":
        return "Saída"
    return valor


def _codigo_descricao(codigo, descricao):
    codigo = str(codigo or "").strip()
    descricao = str(descricao or "").strip()
    if codigo and descricao:
        return f"{codigo} - {descricao}"
    return codigo or descricao


def _separar_valores_parametro(valor):
    return {parte.strip().upper() for parte in str(valor or "").split(",") if parte.strip()}


def _chave_bobina_maquina(item, campo_bobina="codbob", campo_maquina="codmaq"):
    try:
        return int(item.get(campo_maquina)), int(item.get(campo_bobina))
    except TypeError, ValueError:
        return None


def _deduplicar_bobinas_maquinas(bobinas_maquinas):
    unicas = []
    chaves = set()
    for item in bobinas_maquinas:
        chave = _chave_bobina_maquina(item)
        if not chave or chave in chaves:
            continue
        chaves.add(chave)
        unicas.append(item)
    return unicas


def _valor_ordenacao_data_teste(valor):
    if isinstance(valor, datetime):
        return valor
    if hasattr(valor, "year") and hasattr(valor, "month") and hasattr(valor, "day"):
        return datetime.combine(valor, time.min)
    return datetime.min


def _deduplicar_dados_qualidade(dados_qualidade):
    unicos = {}
    for item in dados_qualidade:
        chave = _chave_bobina_maquina(item, campo_bobina="CODBOBINA", campo_maquina="CODMAQUINA")
        if not chave:
            continue
        atual = unicos.get(chave)
        data_teste = _valor_ordenacao_data_teste(item.get("DATA_TESTE"))
        data_teste_atual = (
            _valor_ordenacao_data_teste(atual.get("DATA_TESTE")) if atual else datetime.min
        )
        if atual is None or data_teste > data_teste_atual:
            unicos[chave] = item
    return list(unicos.values())


def _buscar_lotes_anteriores_erp(codemp, codlot):
    lotes_anteriores = []
    lote_atual = codlot
    visitados = {codlot}
    with cursor_oracle_erp() as cursor:
        while lote_atual:
            cursor.execute(
                """
                    SELECT CODLOT
                    FROM (
                        SELECT ORIGEM.CODLOT
                        FROM E210MVP DESTINO
                        JOIN E210MVP ORIGEM
                          ON ORIGEM.CODEMP = DESTINO.CODEMP
                         AND ORIGEM.USU_CODLIG = DESTINO.USU_CODLIG
                         AND ORIGEM.ESTEOS = 'S'
                         AND ORIGEM.CODLOT <> DESTINO.CODLOT
                        WHERE DESTINO.CODEMP = :codemp
                          AND DESTINO.CODLOT = :codlot
                          AND DESTINO.ESTEOS = 'E'
                          AND NVL(DESTINO.USU_CODLIG, 0) <> 0
                        ORDER BY DESTINO.DATDIG, DESTINO.HORDIG, DESTINO.SEQMOV,
                                 ORIGEM.DATDIG, ORIGEM.HORDIG, ORIGEM.SEQMOV
                    )
                    WHERE ROWNUM = 1
                """,
                {"codemp": codemp, "codlot": lote_atual},
            )
            row = cursor.fetchone()
            if not row:
                cursor.execute(
                    """
                        SELECT CODLOT
                        FROM (
                            SELECT ORIGEM.CODLOT
                            FROM E210MVP DESTINO
                            JOIN E210MVP ORIGEM
                              ON ORIGEM.CODEMP = DESTINO.CODEMP
                             AND ORIGEM.CODLIG = DESTINO.CODLIG
                             AND ORIGEM.ESTEOS = 'S'
                             AND ORIGEM.CODLOT <> DESTINO.CODLOT
                            WHERE DESTINO.CODEMP = :codemp
                              AND DESTINO.CODLOT = :codlot
                              AND DESTINO.ESTEOS = 'E'
                              AND NVL(DESTINO.CODLIG, 0) <> 0
                            ORDER BY DESTINO.DATDIG, DESTINO.HORDIG, DESTINO.SEQMOV,
                                     ORIGEM.DATDIG, ORIGEM.HORDIG, ORIGEM.SEQMOV
                        )
                        WHERE ROWNUM = 1
                    """,
                    {"codemp": codemp, "codlot": lote_atual},
                )
                row = cursor.fetchone()
            lote_anterior = row[0] if row else None
            if not lote_anterior or lote_anterior in visitados:
                break
            lotes_anteriores.append(lote_anterior)
            visitados.add(lote_anterior)
            lote_atual = lote_anterior
    return lotes_anteriores


def _chave_movimento(row):
    return row[0], row[1] or 0, row[12] or 0


def _buscar_eventos_erp_lote(codemp, codlot, transacoes_recurso=None):
    eventos = []
    saldos = []
    avisos = []
    referencia_anterior = None
    dados_bobinas = []
    lotes_saldo = {codlot}
    lotes_anteriores = _buscar_lotes_anteriores_erp(codemp, codlot)
    lotes_rastreamento = [codlot, *lotes_anteriores]
    transacoes_recurso = {
        str(valor).strip().upper() for valor in (transacoes_recurso or set()) if str(valor).strip()
    }

    try:
        with cursor_oracle_erp() as cursor:
            params = {"codemp": codemp}
            placeholders = []
            for indice, lote in enumerate(lotes_rastreamento):
                nome_param = f"lote_producao_{indice}"
                params[nome_param] = lote
                placeholders.append(f":{nome_param}")
            cursor.execute(
                f"""
                    SELECT
                        EOQ.DATREA,
                        EOQ.HORREA,
                        EOQ.CODORI,
                        EOQ.NUMORP,
                        EOQ.CODETG,
                        EOQ.SEQROT,
                        EOQ.CODCRE,
                        CRE.ABRCRE,
                        CRE.DESCRE,
                        EOQ.USU_NUMBOB,
                        EOQ.QTDRE1,
                        EOQ.CODDEP,
                        DEP.DESDEP,
                        EOQ.CODPRO,
                        PRO.DESPRO,
                        EOQ.CODDER,
                        DER.DESDER
                    FROM E900EOQ EOQ
                    LEFT JOIN E725CRE CRE
                      ON CRE.CODEMP = EOQ.CODEMP
                     AND CRE.CODCRE = EOQ.CODCRE
                    LEFT JOIN E205DEP DEP
                      ON DEP.CODEMP = EOQ.CODEMP
                     AND DEP.CODDEP = EOQ.CODDEP
                    LEFT JOIN E075PRO PRO
                      ON PRO.CODEMP = EOQ.CODEMP
                     AND PRO.CODPRO = EOQ.CODPRO
                    LEFT JOIN E075DER DER
                      ON DER.CODEMP = EOQ.CODEMP
                     AND DER.CODPRO = EOQ.CODPRO
                     AND DER.CODDER = EOQ.CODDER
                    WHERE EOQ.CODEMP = :codemp
                      AND EOQ.CODLOT IN ({", ".join(placeholders)})
                    ORDER BY EOQ.DATREA, EOQ.HORREA
                """,
                params,
            )
            for row in cursor.fetchall():
                _adicionar_evento(
                    eventos,
                    _parse_data_hora_movimento(row[0], row[1]),
                    "Produção ERP",
                    "Lote produzido/apontado no ERP",
                    origem="E900EOQ",
                    dados=[
                        ("Bobina", row[9]),
                        ("Origem", row[2]),
                        ("OP", row[3]),
                        ("Estágio", row[4]),
                        ("Máquina", row[7] or row[8]),
                        ("Qtd. apontada", row[10]),
                        ("Depósito", _codigo_descricao(row[11], row[12])),
                        ("Produto", _codigo_descricao(row[13], row[14])),
                        ("Der.", _codigo_descricao(row[15], row[16])),
                    ],
                )
                if row[9]:  # USU_NUMBOB
                    dados_bobinas.append({"codbob": row[9], "codcre": row[6]})
    except Exception:
        logger.exception("Falha ao consultar produção e saldo no ERP durante rastreamento")
        avisos.append("Não foi possível consultar produção e saldo no ERP.")

    try:
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
                        TNS.DESTNS,
                        MVP.CODLOT,
                        MVP.ORIORP,
                        MVP.NUMDOC,
                        MVP.CODDEP,
                        MVP.CODPRO,
                        MVP.CODDER,
                        MVP.QTDMOV,
                        MVP.ESTEOS,
                        MVP.SEQMOV,
                        {campo_ligacao} AS CODIGO_LIGACAO,
                        MVP.USURES,
                        USU.NOMUSU,
                        DEP.DESDEP,
                        PRO.DESPRO,
                        DER.DESDER,
                        EOQ.CODCRE,
                        CRE.ABRCRE,
                        CRE.DESCRE
                    FROM E210MVP MVP
                    LEFT JOIN E001TNS TNS
                      ON TNS.CODEMP = MVP.CODEMP
                     AND TNS.CODTNS = MVP.CODTNS
                    LEFT JOIN R999USU USU
                      ON USU.CODUSU = MVP.USURES
                    LEFT JOIN E205DEP DEP
                      ON DEP.CODEMP = MVP.CODEMP
                     AND DEP.CODDEP = MVP.CODDEP
                    LEFT JOIN E075PRO PRO
                      ON PRO.CODEMP = MVP.CODEMP
                     AND PRO.CODPRO = MVP.CODPRO
                    LEFT JOIN E075DER DER
                      ON DER.CODEMP = MVP.CODEMP
                     AND DER.CODPRO = MVP.CODPRO
                     AND DER.CODDER = MVP.CODDER
                    LEFT JOIN E900EOQ EOQ
                      ON EOQ.CODEMP = MVP.CODEMP
                     AND EOQ.CODORI = MVP.ORIORP
                     AND EOQ.NUMORP = MVP.NUMDOC
                     AND EOQ.SEQEOQ = (
                         SELECT MIN(EOQ2.SEQEOQ)
                         FROM E900EOQ EOQ2
                         WHERE EOQ2.CODEMP = MVP.CODEMP
                           AND EOQ2.CODORI = MVP.ORIORP
                           AND EOQ2.NUMORP = MVP.NUMDOC
                           AND EOQ2.CODCRE IS NOT NULL
                     )
                    LEFT JOIN E725CRE CRE
                      ON CRE.CODEMP = EOQ.CODEMP
                     AND CRE.CODCRE = EOQ.CODCRE
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
                movimentos_sucessor = [row for row in movimentos if row[4] == lote_sucessor]
                if movimentos_sucessor:
                    limites_lotes_anteriores[lote_anterior] = min(
                        _chave_movimento(row) for row in movimentos_sucessor
                    )
                lote_sucessor = lote_anterior

            codigos_ligacao = set(codigos_ligacao)
            movimentos = [
                row
                for row in movimentos
                if (
                    row[4] == codlot
                    or row[13] in codigos_ligacao
                    or (
                        row[4] in limites_lotes_anteriores
                        and _chave_movimento(row) < limites_lotes_anteriores[row[4]]
                    )
                )
            ]
            lotes_saldo.update(row[4] for row in movimentos if row[4])

            movimentos_lote_atual = [row for row in movimentos if row[4] == codlot]
            movimentos_anteriores = [row for row in movimentos if row[4] != codlot]
            if len(movimentos_lote_atual) >= 2 or movimentos_anteriores:
                movimento_referencia = (
                    movimentos_lote_atual[-2]
                    if len(movimentos_lote_atual) >= 2
                    else movimentos_anteriores[-1]
                )
                movimentos_recurso = (
                    [
                        row
                        for row in movimentos
                        if str(row[2] or "").strip().upper() in transacoes_recurso
                    ]
                    if transacoes_recurso
                    else []
                )
                movimento_recurso = (
                    movimentos_recurso[-1] if movimentos_recurso else movimento_referencia
                )
                codori_referencia = movimento_recurso[5]
                numorp_referencia = movimento_recurso[6]
                referencia_anterior = {
                    "deposito": _codigo_descricao(
                        movimento_referencia[7], movimento_referencia[16]
                    ),
                    "codori": codori_referencia,
                    "numorp": numorp_referencia,
                    "codcre": None,
                    "recurso": None,
                    "codccu": None,
                }

                if codori_referencia and numorp_referencia:
                    cursor.execute(
                        """
                            SELECT
                                EOQ.CODCRE,
                                CRE.ABRCRE,
                                CRE.DESCRE,
                                CRE.CODCCU
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
                        {
                            "codemp": codemp,
                            "codori": codori_referencia,
                            "numorp": numorp_referencia,
                        },
                    )
                    recurso_row = cursor.fetchone()
                    if recurso_row:
                        referencia_anterior.update(
                            {
                                "codcre": recurso_row[0],
                                "recurso": recurso_row[2] or recurso_row[1],
                                "codccu": recurso_row[3],
                            }
                        )

            grupos_ligacao = {}
            for indice, row in enumerate(movimentos):
                codlig = row[13]
                if not codlig:
                    continue
                grupo = grupos_ligacao.setdefault(
                    codlig,
                    {
                        "data_hora": _parse_data_hora_movimento(row[0], row[1]),
                        "indice": indice,
                        "linhas": [],
                    },
                )
                if row[4] == codlot and grupo["linhas"]:
                    grupo["data_hora"] = _parse_data_hora_movimento(row[0], row[1])
                    grupo["indice"] = indice
                grupo["linhas"].append((indice, row))

            ordem_ligacao = {}
            for codlig, grupo in grupos_ligacao.items():
                linhas_ordenadas = sorted(
                    grupo["linhas"],
                    key=lambda item: (
                        0 if str(item[1][11] or "").strip().upper() == "S" else 1,
                        item[0],
                    ),
                )
                for ordem, (indice_linha, _) in enumerate(linhas_ordenadas):
                    ordem_ligacao[(codlig, indice_linha)] = ordem

            for indice, row in enumerate(movimentos):
                codlig = row[13]
                grupo = grupos_ligacao.get(codlig)
                ordem = row[12] or 0
                data_hora = _parse_data_hora_movimento(row[0], row[1])
                data_hora_ordenacao = data_hora
                if grupo:
                    ordem = (grupo["indice"] * 1000) + ordem_ligacao.get((codlig, indice), indice)
                    data_hora_ordenacao = grupo["data_hora"]

                dados_movimento = [
                    ("Lote", row[4]),
                    ("Depósito", _codigo_descricao(row[7], row[16])),
                    ("Produto", _codigo_descricao(row[8], row[17])),
                    ("Der.", _codigo_descricao(row[9], row[18])),
                    ("Qtd.", row[10]),
                    ("Entrada/Saída", _descricao_entrada_saida(row[11])),
                    ("Responsável", f"{row[14]} - {row[15]}" if row[15] else row[14]),
                ]
                if codlig:
                    dados_movimento.append(
                        (
                            "Ligação (USU_CODLIG)"
                            if campo_ligacao == "MVP.USU_CODLIG"
                            else "Ligação (CODLIG)",
                            codlig,
                        )
                    )
                if str(row[2] or "").strip().upper() in transacoes_recurso:
                    dados_movimento.extend(
                        [
                            ("Origem", row[5]),
                            ("OP/Documento", row[6]),
                            ("Máquina", _codigo_descricao(row[19], row[21] or row[20])),
                        ]
                    )

                _adicionar_evento(
                    eventos,
                    data_hora,
                    "Movimento ERP",
                    f"Movimento de estoque {row[2] or ''}{' - ' + row[3] if row[3] else ''}".strip(),
                    origem="E210MVP",
                    dados=dados_movimento,
                    ordem=ordem,
                    data_hora_ordenacao=data_hora_ordenacao,
                    seqmov=row[12],
                )
    except Exception:
        logger.exception("Falha ao consultar movimentos de estoque no ERP durante rastreamento")
        avisos.append("Movimentos de estoque ERP não carregados.")

    try:
        params = {"codemp": codemp}
        placeholders = []
        for indice, lote in enumerate(sorted(lotes_saldo)):
            nome_param = f"lote_saldo_{indice}"
            params[nome_param] = lote
            placeholders.append(f":{nome_param}")

        with cursor_oracle_erp() as cursor:
            cursor.execute(
                f"""
                    SELECT
                        DLS.CODLOT,
                        DLS.CODDEP,
                        DLS.CODPRO,
                        DLS.CODDER,
                        DLS.QTDEST,
                        DLS.USU_SITLOT,
                        DEP.DESDEP
                    FROM E210DLS DLS
                    LEFT JOIN E205DEP DEP
                      ON DEP.CODEMP = DLS.CODEMP
                     AND DEP.CODDEP = DLS.CODDEP
                    WHERE DLS.CODEMP = :codemp
                      AND DLS.CODLOT IN ({", ".join(placeholders)})
                      AND NVL(DLS.QTDEST, 0) <> 0
                    ORDER BY DLS.CODLOT, DLS.CODDEP, DLS.CODPRO, DLS.CODDER
                """,
                params,
            )
            saldos = [
                {
                    "lote": row[0],
                    "deposito": _codigo_descricao(row[1], row[6]),
                    "produto": row[2],
                    "derivacao": row[3],
                    "saldo": row[4],
                    "situacao": row[5],
                }
                for row in cursor.fetchall()
            ]
    except Exception:
        logger.exception("Falha ao consultar saldo dos lotes ligados no ERP durante rastreamento")
        avisos.append("Não foi possível consultar saldo dos lotes ligados no ERP.")

    return eventos, saldos, avisos, referencia_anterior, dados_bobinas


def _buscar_dados_qualidade_alchemy(bobinas_maquinas):
    if not bobinas_maquinas:
        return []

    bobinas_maquinas = _deduplicar_bobinas_maquinas(bobinas_maquinas)
    resultados = []
    try:
        with cursor_oracle_alchemy() as cursor:
            for bm in bobinas_maquinas:
                cursor.execute(
                    """
                        SELECT
                            t.ALVURA,
                            t.B,
                            t.CREPE,
                            t.ESPESSURA,
                            t.POROSIDADE,
                            t.RU AS RU_CURA,
                            t.RU_SECO,
                            t.RTRANS AS RESIST_TRANSVERSAL,
                            t.RLONG AS RESIST_LONGITUDINAL,
                            CASE
                                WHEN t.RLONG IS NOT NULL AND t.RLONG <> 0 THEN
                                    (t.RU / t.RLONG) * 100
                                ELSE
                                    NULL
                            END AS PERC_RESISTENCIA_UMIDO,
                            t.ALONG AS ALONGAMENTO,
                            t.UMIDADE,
                            t.LARGURA AS LARGURA_CM,
                            t.DIAMETRO AS DIAMETRO_CM,
                            t.INDICEMACIEZ,
                            t.HANDFEEL,
                            pb.MEDIA AS MEDIA_GRAMATURA,
                            pb.DESVIOPADRAO AS DESVIO_GRAMATURA,
                            b.OBSERVACAO,
                            b.DATA_PRO,
                            b.TURNO,
                            b.NUMERO_EMENDAS,
                            b.NUMERO_PICKS,
                            b.DATA_TESTE,
                            t.CODBOBINA,
                            t.CODMAQUINA
                        FROM TESTE t
                        LEFT JOIN PERFIL_BOBINA pb
                            ON pb.CODMAQUINA = t.CODMAQUINA
                           AND pb.CODBOBINA  = t.CODBOBINA
                        LEFT JOIN BOBINAS b
                            ON b.CODMAQUINA = t.CODMAQUINA
                           AND b.CODBOBINA  = t.CODBOBINA
                        WHERE t.CODBOBINA = :codbob
                          AND t.CODMAQUINA = :codmaq
                    """,
                    {"codbob": bm["codbob"], "codmaq": bm["codmaq"]},
                )
                if cursor.description:
                    columns = [col[0] for col in cursor.description]
                    for row in cursor.fetchall():
                        resultados.append(dict(zip(columns, row, strict=False)))
    except Exception:
        pass
    return _deduplicar_dados_qualidade(resultados)


def rastreamento_lote(request):
    if _esta_acima_do_limite_rastreio(request):
        return HttpResponse("Muitas requisições. Tente novamente em instantes.", status=429)

    codemp = request.GET.get("codemp")
    codlot = (request.GET.get("codlot") or "").strip()
    processar = request.GET.get("processar") == "1"

    try:
        codemp_int = int(codemp)
    except TypeError, ValueError:
        codemp_int = None

    eventos = []
    saldos = []
    avisos = []
    dados_qualidade = []
    referencia_anterior = None

    rastreando = bool(codemp_int and codlot and not processar)

    if codemp_int and codlot and processar:
        parametros_filial = (
            ParametrosFilial.objects.filter(filial__empresa__codemp=codemp_int, filial__ativa=True)
            .order_by("filial__codfil")
            .first()
        )
        transacoes_recurso = set()
        if parametros_filial:
            transacoes_recurso.update(
                _separar_valores_parametro(parametros_filial.transacoes_saida_consumo_producao)
            )
            transacoes_recurso.update(
                _separar_valores_parametro(parametros_filial.transacoes_entrada_producao_consumo)
            )

        codlot_erp = codlot
        origem_lote = LiberacaoLote.objects.filter(
            codemp=codemp_int,
            lottrf=codlot,
        )

        origem_lote = (
            origem_lote.order_by("-datger", "-data_hora").values_list("codlot", flat=True).first()
        )
        codlot_qualidade = origem_lote or codlot

        liberacoes = LiberacaoLote.objects.select_related("usuario", "reuniao", "etiqueta").filter(
            codemp=codemp_int,
            codlot=codlot_qualidade,
        )
        for liberacao in liberacoes.order_by("datger"):
            destino = "Liberação"
            tag_qualidade = "liberacao"
            dados_quantidade = [("Qtd. liberada", liberacao.qtdlibe)]
            if (liberacao.qtdrefu or 0) > 0:
                destino = "Refugo"
                tag_qualidade = "refugo"
                dados_quantidade = [("Qtd. refugada", liberacao.qtdrefu)]
            elif (liberacao.qtdrecl or 0) > 0:
                destino = "Reclassificação"
                tag_qualidade = "reclassificacao"
                dados_quantidade = [("Qtd. reclassificada", liberacao.qtdrecl)]
            _adicionar_evento(
                eventos,
                liberacao.datger,
                "Qualidade",
                f"{destino} registrada na consulta de lote",
                origem="qualidade.liberacao_lote",
                dados=[
                    ("Bobina", liberacao.numbob),
                    ("Lote origem", liberacao.codlot),
                    ("Lote transf.", liberacao.lottrf),
                    ("Dep. origem", liberacao.coddep),
                    ("Dep. destino", liberacao.deptrf),
                    *dados_quantidade,
                    ("Produto recl.", liberacao.codpro_recl),
                    ("Der. recl.", liberacao.codder_recl),
                    ("Usuário", liberacao.usuario),
                    (
                        "Reunião início",
                        liberacao.reuniao.data_hora_inicio if liberacao.reuniao else None,
                    ),
                    ("Reunião fim", liberacao.reuniao.data_hora_fim if liberacao.reuniao else None),
                ],
                tag_qualidade=tag_qualidade,
            )

        eventos_erp, saldos, avisos_erp, referencia_anterior, dados_bobinas = (
            _buscar_eventos_erp_lote(
                codemp_int,
                codlot_erp,
                transacoes_recurso=transacoes_recurso,
            )
        )
        eventos.extend(eventos_erp)
        avisos.extend(avisos_erp)

        if dados_bobinas:
            bobinas_maquinas = []
            for item in dados_bobinas:
                recurso = (
                    Recurso.objects.filter(
                        centro_recurso__codigo_integrador=item["codcre"],
                        centro_recurso__setor__departamento__filial__empresa__codemp=codemp_int,
                    )
                    .select_related("centro_recurso__parametros_centro_recurso")
                    .first()
                )
                parametros_centro = (
                    getattr(recurso.centro_recurso, "parametros_centro_recurso", None)
                    if recurso
                    else None
                )
                if parametros_centro and parametros_centro.cod_alchemy:
                    bobinas_maquinas.append(
                        {"codbob": item["codbob"], "codmaq": parametros_centro.cod_alchemy}
                    )

            bobinas_maquinas = _deduplicar_bobinas_maquinas(bobinas_maquinas)
            if bobinas_maquinas:
                dados_qualidade = _buscar_dados_qualidade_alchemy(bobinas_maquinas)

    eventos.sort(
        key=lambda item: (
            item["data_hora_ordenacao"] is None,
            _data_hora_minuto(item["data_hora_ordenacao"]) or timezone.now(),
            _prioridade_evento_no_minuto(item),
            item["data_hora_ordenacao"] or timezone.now(),
            item["ordem"],
        )
    )

    return render(
        request,
        "setores/qualidade/rastreamento_lote.html",
        {
            "titulo": "Rastreamento de Lote",
            "codemp": codemp_int,
            "codlot": codlot,
            "eventos": eventos,
            "saldos": saldos,
            "avisos": avisos,
            "referencia_anterior": referencia_anterior,
            "dados_qualidade": dados_qualidade,
            "rastreando": rastreando,
        },
    )
