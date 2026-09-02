import json
import logging

import pandas as pd
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from accounts.models import CentroRecurso, Empresa, Recurso
from producao.models import Sequenciamento
from SIGMA.autorizacao import permissao_requerida
from SIGMA.integracoes.oracle import cursor_oracle_erp

logger = logging.getLogger(__name__)


def _centros_visiveis(usuario):
    centros = CentroRecurso.objects.select_related("setor__departamento__filial__empresa")
    if usuario.is_staff:
        return centros
    filial = getattr(usuario, "filial", None)
    if not filial or not filial.empresa_id:
        return centros.none()
    return centros.filter(setor__departamento__filial__empresa_id=filial.empresa_id)


def _centro_visivel(usuario, centro_id):
    return _centros_visiveis(usuario).filter(pk=centro_id).first()


def _consultar_estoque(cursor, codemp, codpro, codder):
    """Retorna estoque somado de todos os depósitos para um produto/derivação."""
    sql = """
        SELECT
            NVL(SUM(QTDEST), 0) AS QTDEST,
            NVL(SUM(QTDRES), 0) AS QTDRES,
            NVL(MAX(ESTMIN), 0) AS ESTMIN,
            NVL(MAX(ESTMAX), 0) AS ESTMAX
        FROM E210EST
        WHERE CODEMP = :codemp
          AND CODPRO  = :codpro
          AND CODDER  = :codder
    """
    cursor.execute(sql, {"codemp": codemp, "codpro": codpro, "codder": codder or ""})
    row = cursor.fetchone()
    if row:
        cols = [c[0] for c in cursor.description]
        return dict(zip(cols, row, strict=False))
    return {"QTDEST": 0, "QTDRES": 0, "ESTMIN": 0, "ESTMAX": 0}


def consultar_sequenciamento(codemp, codcre):
    sql = """
          SELECT
            C.CODORI AS ORIGEM,
            C.NUMORP AS OP,
            MIN(Q.CODPRO) KEEP (DENSE_RANK FIRST ORDER BY O.SEQROT) AS PRODUTO,
            MIN(Q.CODDER) KEEP (DENSE_RANK FIRST ORDER BY O.SEQROT) AS DERIVACAO,
            MIN(Q.QTDPRV) AS QTDPRV,
            MIN(PR.DESPRO || ' - ' || DER.DESDER) KEEP (DENSE_RANK FIRST ORDER BY O.SEQROT) AS DESCRICAO,
            MIN(O.CODETG) KEEP (DENSE_RANK FIRST ORDER BY O.SEQROT) AS ESTAGIO,
            MIN(O.SEQROT) KEEP (DENSE_RANK FIRST ORDER BY O.SEQROT) AS SEQROTEIRO,
            MIN(O.CODOPR) KEEP (DENSE_RANK FIRST ORDER BY O.SEQROT) AS OPERACAO,
            MIN(O.TMPTPR) KEEP (DENSE_RANK FIRST ORDER BY O.SEQROT) AS TEMPO
          FROM E900COP C
            JOIN E900QDO Q   ON Q.CODEMP = C.CODEMP AND Q.CODORI = C.CODORI AND Q.NUMORP = C.NUMORP AND Q.CODPRO = C.CODPRO
            JOIN E900OOP O   ON O.CODEMP = C.CODEMP AND O.NUMORP = C.NUMORP AND O.CODORI = C.CODORI
            JOIN E075PRO PR  ON PR.CODEMP = C.CODEMP AND PR.CODPRO = C.CODPRO
            JOIN E075DER DER ON DER.CODEMP = C.CODEMP AND DER.CODPRO = C.CODPRO AND DER.CODDER = Q.CODDER
            JOIN E725CRE R   ON R.CODEMP = C.CODEMP AND R.CODCRE = O.CODCRE
            JOIN E083ORI ORI ON ORI.CODEMP = C.CODEMP AND ORI.CODORI = C.CODORI
          WHERE C.CODEMP    = :codemp
            AND C.SITORP   IN ('L', 'R', 'A')
            AND O.DTRFIM = DATE '1900-12-31'
            AND O.CODCRE    = :codcre
            AND O.MOVORP    = 'S'
            AND Q.PROORI    = 'S'
          GROUP BY C.NUMORP, C.CODORI
          ORDER BY MIN(ORI.NUMORI), MIN(O.TMPTPR)
          """

    with cursor_oracle_erp() as cursor:
        cursor.execute(sql, {"codemp": codemp, "codcre": codcre})
        colunas = [c[0] for c in cursor.description]
        resultados = [dict(zip(colunas, linha, strict=False)) for linha in cursor.fetchall()]

        # Enriquece com estoque (cache por produto+derivação para não repetir consultas)
        cache_est = {}
        for item in resultados:
            codpro = item.get("PRODUTO") or ""
            codder = item.get("DERIVACAO") or ""
            key = (codpro, codder)
            if key not in cache_est:
                cache_est[key] = _consultar_estoque(cursor, codemp, codpro, codder)
            est = cache_est[key]
            item["QTDEST"] = est["QTDEST"]
            item["QTDRES"] = est["QTDRES"]
            item["ESTMIN"] = est["ESTMIN"]
            item["ESTMAX"] = est["ESTMAX"]

        return resultados


@permissao_requerida("producao.pode_acessar_sequenciamento")
def sequenciamento_view(request):
    resultados = None
    erro = None
    recursos = []

    empresa_id = request.GET.get("empresa") or request.POST.get("empresa", "")

    # --- USUÁRIO COMUM ---
    if not request.user.is_staff and getattr(request.user, "filial", None):
        empresa_user = request.user.filial.empresa
        empresas = Empresa.objects.filter(id=empresa_user.id)
        empresa_id = empresa_user.id
        centros = (
            CentroRecurso.objects.filter(setor__departamento__filial__empresa=empresa_user)
            .exclude(descricao__icontains="Geral")
            .select_related("setor__departamento__filial__empresa")
            .order_by("descricao")
        )

    # --- ADMINISTRADOR ---
    elif request.user.is_staff:
        empresas = Empresa.objects.all().order_by("nome")

        if not empresa_id:
            empresa_id = empresas.values_list("id", flat=True).first()

        centros = (
            CentroRecurso.objects.filter(setor__departamento__filial__empresa_id=empresa_id)
            .exclude(descricao__icontains="Geral")
            .select_related("setor__departamento__filial__empresa")
            .order_by("descricao")
        )

    # --- SEM FILIAL (usuário mal cadastrado) ---
    else:
        empresas = Empresa.objects.none()
        centros = []

    # --- CONSULTA PRINCIPAL ---
    if request.method == "POST":
        centro_id = request.POST.get("centro")
        try:
            centro = _centro_visivel(request.user, centro_id)
            if not centro:
                raise ValueError("Centro não disponível para o seu usuário.")
            codcre = centro.codigo_integrador
            codemp = centro.setor.departamento.filial.empresa.codemp

            resultados = consultar_sequenciamento(codemp, codcre)
            recursos = Recurso.objects.filter(centro_recurso=centro, ativo=True).order_by(
                "ordenacao_sequenciamento", "descricao"
            )
        except Exception:
            logger.exception("Falha ao consultar sequenciamento no ERP")
            erro = "Não foi possível consultar o sequenciamento no ERP."

    # --- SEQUENCIAMENTOS EXISTENTES ---
    sequenciamentos_existentes = Sequenciamento.objects.select_related("recurso").filter(
        recurso__centro_recurso__in=_centros_visiveis(request.user)
    )
    mapa_seqs = {}
    sequencias_existentes = set()
    for s in sequenciamentos_existentes:
        mapa_seqs.setdefault(s.recurso_id, []).append(s)
        sequencias_existentes.add(f"{s.op}-{s.estagio}-{s.seqrot}")
    recursos_sequenciamentos = [
        {"recurso": recurso, "sequenciamentos": mapa_seqs.get(recurso.id, [])}
        for recurso in recursos
    ]

    pode_consolidar_sequenciamento_erp = request.user.is_staff or request.user.has_perm(
        "producao.pode_consolidar_sequenciamento_erp"
    )

    return render(
        request,
        "producao/sequenciamento.html",
        {
            "empresas": empresas,
            "empresa_id": empresa_id,
            "centros": centros,
            "resultados": resultados,
            "recursos": recursos,
            "erro": erro,
            "recursos_sequenciamentos": recursos_sequenciamentos,
            "sequencias_existentes": sequencias_existentes,
            "pode_consolidar_sequenciamento_erp": pode_consolidar_sequenciamento_erp,
        },
    )


@permissao_requerida("producao.pode_consolidar_sequenciamento_erp")
@require_POST
@transaction.atomic
def consolidar_sequenciamento(request):
    # O deny de autorização é o 403 do decorator (mesma regra do guard que
    # existia aqui dentro); o client JS trata resposta não-JSON como erro genérico.
    try:
        dados = json.loads(request.POST.get("sequenciamento_json", "[]"))
    except json.JSONDecodeError:
        return JsonResponse({"status": "erro", "msg": "Sequenciamento inválido."}, status=400)
    if not isinstance(dados, list):
        return JsonResponse({"status": "erro", "msg": "Sequenciamento inválido."}, status=400)

    centro_id = request.POST.get("centro_id")
    if not centro_id and dados:
        if not isinstance(dados[0], dict):
            return JsonResponse({"status": "erro", "msg": "Sequenciamento inválido."}, status=400)
        centro_id = dados[0].get("centro_id")
    centro = _centro_visivel(request.user, centro_id) if centro_id else None
    if not centro:
        return JsonResponse({"status": "erro", "msg": "Centro não disponível."}, status=403)

    try:
        recursos_ids = {int(item["recurso"]) for item in dados}
        recursos = {
            recurso.id: recurso
            for recurso in Recurso.objects.filter(id__in=recursos_ids, centro_recurso=centro)
        }
        if len(recursos) != len(recursos_ids):
            raise ValueError
        registros = [
            Sequenciamento(
                recurso=recursos[int(item["recurso"])],
                ordenacao=int(item["ordenacao"]),
                op=int(item["op"]),
                origem=str(item["origem"]),
                codproduto=str(item["codproduto"]),
                descricao=str(item.get("descricao", "")),
                derivacao=item.get("derivacao") or None,
                estagio=int(item["estagio"]),
                seqrot=int(item["seqrot"]),
                tempo=float(str(item["tempo"]).replace(",", ".")),
                operacao=str(item["operacao"]),
            )
            for item in dados
        ]
    except KeyError, TypeError, ValueError:
        return JsonResponse({"status": "erro", "msg": "Sequenciamento inválido."}, status=400)

    Sequenciamento.objects.filter(recurso__centro_recurso=centro).delete()
    Sequenciamento.objects.bulk_create(registros)
    return JsonResponse({"status": "ok", "msg": "Tudo removido" if not dados else ""})


@permissao_requerida("producao.pode_consolidar_sequenciamento_erp")
@require_POST
def sequenciar_automatico(request):
    # Deny de autorização idem consolidar: 403 do decorator.
    if request.method == "POST":
        centro_id = request.POST.get("centro_id")
        manter_atual = request.POST.get("manter_atual") == "true"
        try:
            sequenciamento_tela = json.loads(request.POST.get("sequenciamento_json", "[]"))
        except json.JSONDecodeError:
            return JsonResponse({"status": "erro", "msg": "Sequenciamento inválido."}, status=400)
        if not isinstance(sequenciamento_tela, list):
            return JsonResponse({"status": "erro", "msg": "Sequenciamento inválido."}, status=400)

        if not centro_id:
            return JsonResponse({"status": "erro", "msg": "Centro não informado"})

        try:
            from django.db.models import Max, Sum

            centro = _centro_visivel(request.user, centro_id)
            if not centro:
                return JsonResponse({"status": "erro", "msg": "Centro não disponível."}, status=403)
            codcre = centro.codigo_integrador
            codemp = centro.setor.departamento.filial.empresa.codemp

            # 1. Obter OPs disponíveis do ERP
            ops_disponiveis = consultar_sequenciamento(codemp, codcre)

            # 2. Obter Recursos do centro
            recursos = list(
                Recurso.objects.filter(centro_recurso=centro, ativo=True).order_by(
                    "ordenacao_sequenciamento", "descricao"
                )
            )
            if not recursos:
                return JsonResponse(
                    {"status": "erro", "msg": "Nenhum recurso ativo encontrado para este centro."}
                )

            # 3. Lidar com sequenciamento atual
            if not manter_atual:
                # Não deletar do banco ainda, apenas ignorar para a distribuição visual
                chaves_sequenciadas = set()
            else:
                # Priorizar o que está na tela (não consolidado) se houver dados
                if sequenciamento_tela:
                    chaves_sequenciadas = {
                        f"{s['op']}-{s['estagio']}-{s['seqrot']}" for s in sequenciamento_tela
                    }
                else:
                    sequenciados = Sequenciamento.objects.filter(
                        recurso__centro_recurso=centro
                    ).values("op", "estagio", "seqrot")
                    chaves_sequenciadas = {
                        f"{s['op']}-{s['estagio']}-{s['seqrot']}" for s in sequenciados
                    }

            # Filtrar apenas as que faltam
            ops_para_sequenciar = [
                op
                for op in ops_disponiveis
                if f"{op['OP']}-{op['ESTAGIO']}-{op['SEQROTEIRO']}" not in chaves_sequenciadas
            ]

            if not ops_para_sequenciar:
                return JsonResponse({"status": "ok", "msg": "Não há novas OPs para sequenciar."})

            # 4. Ordenar OPs: estoque disponível vs mínimo (mais crítico primeiro), depois tempo
            def _disponivel(op):
                qtdest = float(op.get("QTDEST") or 0)
                qtdres = float(op.get("QTDRES") or 0)
                estmin = float(op.get("ESTMIN") or 0)
                return qtdest - qtdres - estmin

            ops_para_sequenciar.sort(
                key=lambda x: (_disponivel(x), float(str(x.get("TEMPO") or 0).replace(",", ".")))
            )

            # 5. Distribuir entre os recursos
            carga_recursos = {r.id: 0.0 for r in recursos}
            proxima_ordem = {r.id: 1 for r in recursos}

            if manter_atual:
                if sequenciamento_tela:
                    # Usar o que está na tela
                    for r in recursos:
                        itens_tela = [s for s in sequenciamento_tela if int(s["recurso"]) == r.id]
                        carga_recursos[r.id] = sum(
                            float(str(s["tempo"]).replace(",", ".")) for s in itens_tela
                        )
                        proxima_ordem[r.id] = (
                            max([int(s["ordenacao"]) for s in itens_tela] + [0]) + 1
                        )
                else:
                    # Usar o que está no banco
                    for r in recursos:
                        tempo_atual = (
                            Sequenciamento.objects.filter(recurso=r).aggregate(total=Sum("tempo"))[
                                "total"
                            ]
                            or 0.0
                        )
                        carga_recursos[r.id] = tempo_atual
                        max_ord = (
                            Sequenciamento.objects.filter(recurso=r).aggregate(
                                max_ord=Max("ordenacao")
                            )["max_ord"]
                            or 0
                        )
                        proxima_ordem[r.id] = max_ord + 1

            proposta_sequenciamento = []
            for op_dados in ops_para_sequenciar:
                # Escolhe o recurso com menor carga
                recurso_escolhido = min(recursos, key=lambda r: carga_recursos[r.id])

                try:
                    t_str = str(op_dados.get("TEMPO") or "0").replace(",", ".")
                    tempo = float(t_str)
                except ValueError, TypeError:
                    tempo = 0.0

                try:
                    op_val = int(op_dados.get("OP") or 0)
                except ValueError, TypeError:
                    op_val = 0

                try:
                    estagio_val = int(op_dados.get("ESTAGIO") or 0)
                except ValueError, TypeError:
                    estagio_val = 0

                try:
                    seq_val = int(op_dados.get("SEQROTEIRO") or 0)
                except ValueError, TypeError:
                    seq_val = 0

                proposta_sequenciamento.append(
                    {
                        "recurso_id": recurso_escolhido.id,
                        "ordenacao": proxima_ordem[recurso_escolhido.id],
                        "op": op_val,
                        "origem": op_dados.get("ORIGEM") or "",
                        "codproduto": op_dados.get("PRODUTO") or "",
                        "descricao": op_dados.get("DESCRICAO") or "",
                        "derivacao": op_dados.get("DERIVACAO") or None,
                        "estagio": estagio_val,
                        "seqrot": seq_val,
                        "tempo": tempo,
                        "operacao": op_dados.get("OPERACAO") or "",
                        "key": f"{op_val}-{estagio_val}-{seq_val}",
                    }
                )

                carga_recursos[recurso_escolhido.id] += tempo
                proxima_ordem[recurso_escolhido.id] += 1

            return JsonResponse(
                {
                    "status": "ok",
                    "msg": f"{len(proposta_sequenciamento)} OPs distribuídas. Clique em 'Consolidar' para salvar.",
                    "proposta": proposta_sequenciamento,
                    "limpar_atual": not manter_atual,
                }
            )

        except Exception:
            logger.exception("Falha ao sequenciar automaticamente")
            return JsonResponse(
                {"status": "erro", "msg": "Falha ao sequenciar no ERP."}, status=500
            )

    return JsonResponse({"status": "erro", "msg": "Método inválido"}, status=400)


@permissao_requerida("producao.pode_acessar_sequenciamento")
def exportar_sequenciamento(request):
    centro_id = request.GET.get("centro")
    if not centro_id:
        return HttpResponse("Centro não informado.", status=400)

    centro = _centro_visivel(request.user, centro_id)
    if not centro:
        return HttpResponseForbidden("Centro não disponível para o seu usuário.")
    codcre = centro.codigo_integrador
    codemp = centro.setor.departamento.filial.empresa.codemp

    dados = consultar_sequenciamento(codemp, codcre)
    df = pd.DataFrame(dados)

    if df.empty:
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="sequenciamento_{centro.descricao}.xlsx"'
        )
        pd.DataFrame().to_excel(response, index=False)
        return response

    # Recurso e ordem consolidados (usa ESTAGIO/SEQROTEIRO internamente)
    consolidado = Sequenciamento.objects.select_related("recurso").filter(
        recurso__centro_recurso=centro
    )
    mapa = {(s.op, s.estagio, s.seqrot): (s.recurso.descricao, s.ordenacao) for s in consolidado}
    df["_recurso"] = df.apply(
        lambda r: mapa.get((r["OP"], r["ESTAGIO"], r["SEQROTEIRO"]), (None, None))[0], axis=1
    )
    df["_ordem"] = df.apply(
        lambda r: mapa.get((r["OP"], r["ESTAGIO"], r["SEQROTEIRO"]), (None, None))[1], axis=1
    )

    # Formata tempo (minutos → "Xh Ymin")
    def fmt_tempo(minutos):
        try:
            m = float(str(minutos).replace(",", "."))
            if m <= 0:
                return ""
            h = int(m // 60)
            r = int(round(m % 60))
            if h and r:
                return f"{h}h {r}min"
            return f"{h}h" if h else f"{r}min"
        except Exception:
            return ""

    df["_tempo_fmt"] = df["TEMPO"].apply(fmt_tempo)

    # Seleciona e renomeia colunas na mesma ordem do template
    export = pd.DataFrame(
        {
            "Origem": df["ORIGEM"],
            "OP": df["OP"],
            "Produto": df["PRODUTO"],
            "Derivação": df["DERIVACAO"],
            "Descrição": df["DESCRICAO"],
            "Qt. Prev.": df["QTDPRV"],
            "Tempo": df["_tempo_fmt"],
            "Estoque": df["QTDEST"],
            "Reservado": df["QTDRES"],
            "Est. Mín": df["ESTMIN"],
            "Est. Máx": df["ESTMAX"],
            "Recurso Consolidado": df["_recurso"],
            "Ordem Consolidada": df["_ordem"],
        }
    )

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="sequenciamento_{centro.descricao}.xlsx"'
    )
    export.to_excel(response, index=False)
    return response
