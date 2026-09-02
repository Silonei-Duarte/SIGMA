import logging
import threading
import time
from collections import defaultdict

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import close_old_connections, connections, transaction
from django.utils import timezone

from accounts.models import CentroRecurso, Recurso
from producao.models import LogTrocaOPAtiva, ParadaMaquina, Sequenciamento
from producao.services.status import (
    marcar_ciclo_fim,
    marcar_ciclo_inicio,
    marcar_service_iniciado,
    marcar_service_parado,
    registrar_service,
)
from producao.utils.paradas import (
    congelar_justificativa_aberta,
    pode_encerrar_parada,
    reconciliar_periodos_da_parada,
)
from SIGMA.integracoes.oracle import cursor_oracle_erp

logger = logging.getLogger(__name__)
SERVICE_CODIGO = "sincroniza_ops_encerradas"
SERVICE_NOME = "Sincronização de OPs encerradas"
CAMPO_CODEMP = "recurso__centro_recurso__setor__departamento__filial__empresa__codemp"


def _normalizar_origem(valor):
    texto = str(valor or "").strip()
    return str(int(texto)) if texto.isdigit() else texto.upper()


def _redistribuir_prioridades_op(itens, obter_numpri, obter_desempate, obter_chave=None):
    """Reatribui a prioridade de itens (OPs) para ordenação consistente no
    sequenciamento. `NUMPRI = 0` (ou vazio) é o padrão do ERP para "sem
    prioridade definida" — a prioridade real começa em 1 — então esses itens
    recebem uma prioridade sequencial, continuando depois da última prioridade
    real usada, desempatados por `obter_desempate`. Prioridades reais (>= 1)
    mantêm seu próprio valor, só sendo empurradas para a próxima posição livre
    quando colidem com a anterior já usada (cascata), o que também desfaz
    empates entre reais.

    Retorna um dict {chave: prioridade_atribuida}, usando `obter_chave(item)`
    (por padrão o próprio item) como chave.
    """
    obter_chave = obter_chave or (lambda item: item)

    def numpri_de(item):
        try:
            return int(obter_numpri(item))
        except TypeError, ValueError:
            return 0

    priorizados = sorted(
        (item for item in itens if numpri_de(item) > 0),
        key=lambda item: (numpri_de(item), obter_desempate(item)),
    )
    sem_prioridade = sorted(
        (item for item in itens if numpri_de(item) <= 0),
        key=obter_desempate,
    )

    prioridades = {}
    ordenacao_anterior = 0
    for item in priorizados:
        ordenacao_anterior = max(numpri_de(item), ordenacao_anterior + 1)
        prioridades[obter_chave(item)] = ordenacao_anterior
    for item in sem_prioridade:
        ordenacao_anterior += 1
        prioridades[obter_chave(item)] = ordenacao_anterior

    return prioridades


def _fechar_paradas_abertas(ids_logs, horario_fim, periodos_por_recurso):
    horario_fim = horario_fim.replace(microsecond=0)
    ids_logs = set(ids_logs)
    if not ids_logs:
        return 0, set()

    # A relação com períodos produtivos é N:N. Não use DISTINCT na consulta
    # bloqueada: o PostgreSQL não permite SELECT DISTINCT ... FOR UPDATE.
    # O IN na consulta externa já elimina eventuais repetições da subconsulta.
    ids_paradas = ParadaMaquina.objects.filter(
        periodos_produtivos__id__in=ids_logs, fim__isnull=True
    ).values("pk")
    paradas = list(
        ParadaMaquina.objects.select_for_update()
        .filter(pk__in=ids_paradas)
        .order_by("recurso_id", "id")
        .prefetch_related("justificativas", "periodos_produtivos")
    )
    fechadas = 0
    recursos_aguardando_tempo_minimo = set()
    for parada in paradas:
        # A parada é física e pode atender mais de uma OP. Só a encerra quando
        # nenhum outro período ainda estiver aberto; os vínculos dos períodos
        # encerrados permanecem para a consolidação histórica dos tempos.
        if any(
            periodo.horario_saida is None and periodo.id not in ids_logs
            for periodo in parada.periodos_produtivos.all()
        ):
            continue
        if not pode_encerrar_parada(parada, horario_fim):
            recursos_aguardando_tempo_minimo.add(parada.recurso_id)
            continue
        parada.fim = horario_fim
        parada.save(update_fields=["fim"])

        congelar_justificativa_aberta(parada, agora=horario_fim)
        reconciliar_periodos_da_parada(
            parada,
            periodos=periodos_por_recurso.get(parada.recurso_id, []),
            agora=horario_fim,
        )
        fechadas += 1
    return fechadas, recursos_aguardando_tempo_minimo


def _notificar_ops_encerradas(recurso_ids):
    if not recurso_ids:
        return

    def enviar():
        channel_layer = get_channel_layer()
        if not channel_layer:
            return
        for recurso_id in recurso_ids:
            async_to_sync(channel_layer.group_send)(
                f"recurso_{recurso_id}",
                {"type": "refresh_page"},
            )

    transaction.on_commit(enviar)


class SincronizaOpsEncerradasScheduler(threading.Thread):
    _running = False
    intervalo_segundos = 300
    tempo_limite_ciclo_segundos = 60
    tamanho_lote = 200

    def __init__(self):
        super().__init__(name="SincronizaOpsEncerradasScheduler", daemon=True)
        registrar_service(
            SERVICE_CODIGO,
            SERVICE_NOME,
            self.intervalo_segundos,
            "Fecha paradas abertas no encerramento da última OP ativa, remove do sequenciamento as OPs S, F ou C no ERP "
            "e, para os centros de recurso com OPs prioritizadas (NUMPRI) no ERP, importa esse sequenciamento para o SIGMA.",
            self.tempo_limite_ciclo_segundos,
        )

    def run(self):
        if SincronizaOpsEncerradasScheduler._running:
            print("[SINCRONIZA_OPS_ENCERRADAS] Scheduler já está rodando")
            return

        SincronizaOpsEncerradasScheduler._running = True
        marcar_service_iniciado(SERVICE_CODIGO)
        try:
            while SincronizaOpsEncerradasScheduler._running:
                inicio_ciclo = time.time()
                close_old_connections()
                with connections["default"].cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('application_name', 'sigma-sincroniza-ops', false)"
                    )
                marcar_ciclo_inicio(SERVICE_CODIGO)
                erro_ciclo = ""
                try:
                    self.sincronizar_ops_encerradas()
                except Exception as exc:
                    erro_ciclo = exc
                    logger.error("Erro ao sincronizar OPs encerradas: %s", exc)
                try:
                    self.importar_sequenciamento_erp()
                except Exception as exc:
                    erro_ciclo = erro_ciclo or exc
                    logger.error("Erro ao importar sequenciamento do ERP: %s", exc)
                finally:
                    marcar_ciclo_fim(
                        SERVICE_CODIGO,
                        time.time() - inicio_ciclo,
                        self.intervalo_segundos,
                        erro_ciclo,
                    )
                    connections.close_all()

                time.sleep(self.intervalo_segundos)
        finally:
            SincronizaOpsEncerradasScheduler._running = False
            marcar_service_parado(SERVICE_CODIGO)

    def _buscar_ops_encerradas(self, chaves_por_empresa):
        chaves_encerradas = set()
        with cursor_oracle_erp() as cursor:
            for codemp, chaves in chaves_por_empresa.items():
                lista_chaves = sorted(chaves)
                for inicio in range(0, len(lista_chaves), self.tamanho_lote):
                    params = {"codemp": codemp}
                    clausulas = []
                    for indice, (origem, op) in enumerate(
                        lista_chaves[inicio : inicio + self.tamanho_lote]
                    ):
                        origem_param = f"codori_{indice}"
                        op_param = f"numorp_{indice}"
                        params[origem_param] = origem
                        params[op_param] = op
                        clausulas.append(f"(codori = :{origem_param} AND numorp = :{op_param})")

                    cursor.execute(
                        f"""
                            SELECT codori, numorp
                            FROM e900cop
                            WHERE codemp = :codemp
                              AND sitorp IN ('S', 'F', 'C')
                              AND ({" OR ".join(clausulas)})
                        """,
                        params,
                    )
                    chaves_encerradas.update(
                        (int(codemp), _normalizar_origem(codori), int(numorp))
                        for codori, numorp in cursor.fetchall()
                    )
        return chaves_encerradas

    def sincronizar_ops_encerradas(self):
        logs_abertos = list(
            LogTrocaOPAtiva.objects.filter(horario_saida__isnull=True).values(
                "id", "recurso_id", "origem", "op", CAMPO_CODEMP
            )
        )
        sequenciamentos = list(Sequenciamento.objects.values("id", "origem", "op", CAMPO_CODEMP))

        chaves_por_empresa = defaultdict(set)
        ids_logs_por_chave = defaultdict(list)
        ids_sequenciamento_por_chave = defaultdict(list)

        for registro in logs_abertos:
            try:
                chave = (
                    int(registro[CAMPO_CODEMP]),
                    _normalizar_origem(registro["origem"]),
                    int(registro["op"]),
                )
            except TypeError, ValueError:
                continue
            chaves_por_empresa[chave[0]].add(chave[1:])
            ids_logs_por_chave[chave].append(registro["id"])

        for registro in sequenciamentos:
            try:
                chave = (
                    int(registro[CAMPO_CODEMP]),
                    _normalizar_origem(registro["origem"]),
                    int(registro["op"]),
                )
            except TypeError, ValueError:
                continue
            chaves_por_empresa[chave[0]].add(chave[1:])
            ids_sequenciamento_por_chave[chave].append(registro["id"])

        if not chaves_por_empresa:
            return

        chaves_encerradas = self._buscar_ops_encerradas(chaves_por_empresa)
        if not chaves_encerradas:
            return

        ids_logs = sorted(
            {
                identificador
                for chave in chaves_encerradas
                for identificador in ids_logs_por_chave[chave]
            }
        )
        recursos_ids = {
            registro["recurso_id"] for registro in logs_abertos if registro["id"] in ids_logs
        }
        ids_sequenciamento = [
            identificador
            for chave in chaves_encerradas
            for identificador in ids_sequenciamento_por_chave[chave]
        ]
        horario_saida_op = timezone.now().replace(microsecond=0)
        with transaction.atomic():
            # Ordem canônica para não disputar com abertura/fechamento manual
            # ou automático: Recurso -> LogTrocaOPAtiva -> ParadaMaquina.
            list(Recurso.objects.select_for_update().filter(pk__in=recursos_ids).order_by("pk"))
            periodos_do_recurso = list(
                LogTrocaOPAtiva.objects.select_for_update()
                .filter(recurso_id__in=recursos_ids)
                .order_by("recurso_id", "id")
            )
            ids_logs = set(ids_logs)
            logs_para_fechar = [
                periodo
                for periodo in periodos_do_recurso
                if periodo.id in ids_logs and periodo.horario_saida is None
            ]
            periodos_por_recurso = {}
            for periodo in periodos_do_recurso:
                periodos_por_recurso.setdefault(periodo.recurso_id, []).append(periodo)
            ids_logs_bloqueados = [log.id for log in logs_para_fechar]
            paradas_fechadas, recursos_aguardando_tempo_minimo = _fechar_paradas_abertas(
                ids_logs_bloqueados,
                horario_saida_op,
                periodos_por_recurso,
            )
            if recursos_aguardando_tempo_minimo:
                logs_para_fechar = [
                    periodo
                    for periodo in logs_para_fechar
                    if periodo.recurso_id not in recursos_aguardando_tempo_minimo
                ]
                ids_logs_bloqueados = [log.id for log in logs_para_fechar]
            if ids_logs_bloqueados:
                LogTrocaOPAtiva.objects.filter(pk__in=ids_logs_bloqueados).update(
                    horario_saida=horario_saida_op
                )
            logs_fechados = len(ids_logs_bloqueados)
            sequenciamentos_removidos = Sequenciamento.objects.filter(
                id__in=ids_sequenciamento
            ).delete()[0]
            if logs_fechados:
                _notificar_ops_encerradas({log.recurso_id for log in logs_para_fechar})
        print(
            "[SINCRONIZA_OPS_ENCERRADAS] "
            f"Paradas fechadas={paradas_fechadas}; logs fechados={logs_fechados}; "
            f"sequenciamentos removidos={sequenciamentos_removidos}"
        )

    # Busca no ERP, por empresa, as OPs elegíveis e prioritizadas (NUMPRI preenchido)
    # dos centros informados. Prioridade vazia (NULL) no ERP significa que aquele
    # centro ainda não usa NUMPRI; nesse caso o SIGMA mantém o que já tem localmente.
    def _buscar_sequenciamento_prioritario(self, codcres_por_empresa):
        linhas_por_chave = defaultdict(list)
        with cursor_oracle_erp() as cursor:
            for codemp, codcres in codcres_por_empresa.items():
                lista_codcres = sorted(codcres)
                if not lista_codcres:
                    continue
                for inicio in range(0, len(lista_codcres), self.tamanho_lote):
                    params = {"codemp": codemp}
                    placeholders = []
                    for indice, codcre in enumerate(
                        lista_codcres[inicio : inicio + self.tamanho_lote]
                    ):
                        nome_param = f"codcre_{indice}"
                        params[nome_param] = codcre
                        placeholders.append(f":{nome_param}")

                    cursor.execute(
                        f"""
                            SELECT
                                O.CODCRE AS CODCRE,
                                C.CODORI AS ORIGEM,
                                C.NUMORP AS OP,
                                C.NUMPRI AS NUMPRI,
                                MIN(Q.CODPRO) KEEP (DENSE_RANK FIRST ORDER BY O.SEQROT) AS PRODUTO,
                                MIN(Q.CODDER) KEEP (DENSE_RANK FIRST ORDER BY O.SEQROT) AS DERIVACAO,
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
                            WHERE C.CODEMP  = :codemp
                              AND C.SITORP IN ('L', 'R', 'A')
                              AND C.NUMPRI IS NOT NULL
                              AND O.DTRFIM = DATE '1900-12-31'
                              AND O.CODCRE IN ({", ".join(placeholders)})
                              AND O.MOVORP = 'S'
                              AND Q.PROORI = 'S'
                            GROUP BY O.CODCRE, C.NUMORP, C.CODORI, C.NUMPRI
                        """,
                        params,
                    )
                    colunas = [coluna[0] for coluna in cursor.description]
                    for linha in cursor.fetchall():
                        registro = dict(zip(colunas, linha, strict=False))
                        chave = (int(codemp), str(registro["CODCRE"] or "").strip())
                        linhas_por_chave[chave].append(registro)
        return linhas_por_chave

    @staticmethod
    def _montar_linha_sequenciamento(linha, ordenacao):
        return {
            "ordenacao": ordenacao,
            "origem": linha["ORIGEM"],
            "op": int(linha["OP"]),
            "codproduto": linha["PRODUTO"] or "",
            "derivacao": linha["DERIVACAO"],
            "descricao": linha["DESCRICAO"] or "",
            "estagio": int(linha["ESTAGIO"] or 0),
            "seqrot": int(linha["SEQROTEIRO"] or 0),
            "tempo": float(linha["TEMPO"] or 0),
            "operacao": linha["OPERACAO"] or "",
        }

    # Redistribui NUMPRI (prioridade do ERP) em ordenações inteiras únicas e
    # crescentes, usando a mesma regra aplicada nas telas de componentes a
    # separar/movimentar: `NUMPRI = 0` (ou vazio) é o padrão do ERP para "sem
    # prioridade definida" (a prioridade real começa em 1), então essas OPs vão
    # para o final, desempatadas por tempo de operação (TMPTPR). Se também
    # empatar em tempo, desempata pelo número da OP (menor primeiro), para não
    # depender da ordem (não garantida) de retorno do Oracle entre ciclos.
    @classmethod
    def _redistribuir_prioridades(cls, linhas):
        prioridades = _redistribuir_prioridades_op(
            linhas,
            obter_numpri=lambda linha: linha["NUMPRI"],
            obter_desempate=lambda linha: (float(linha["TEMPO"] or 0), int(linha["OP"])),
            obter_chave=lambda linha: (linha["ORIGEM"], linha["OP"]),
        )
        linhas_ordenadas = sorted(
            linhas, key=lambda linha: prioridades[(linha["ORIGEM"], linha["OP"])]
        )
        return [
            cls._montar_linha_sequenciamento(linha, prioridades[(linha["ORIGEM"], linha["OP"])])
            for linha in linhas_ordenadas
        ]

    # Assinatura comparável do sequenciamento de um recurso: mesma OP, mesmo
    # estágio/roteiro e mesma ordenação, na mesma ordem. Usada para pular a
    # regravação quando o ERP já resultaria exatamente no que já está salvo.
    @staticmethod
    def _assinatura_sequenciamento(itens):
        return tuple(
            (item["origem"], item["op"], item["estagio"], item["seqrot"], item["ordenacao"])
            for item in sorted(itens, key=lambda item: item["ordenacao"])
        )

    # Ponte temporária enquanto o PCP migra o sequenciamento manual para o SIGMA:
    # para cada centro de recurso com recurso ativo, se o ERP tiver alguma OP
    # elegível com NUMPRI preenchido, o sequenciamento do ERP sempre prevalece e
    # substitui o que existir localmente para os recursos ativos daquele centro.
    # Se o ERP não tiver nenhuma OP com prioridade para o centro, o SIGMA não
    # altera o que já existe (permitindo que o PCP passe a sequenciar manualmente
    # ali sem que essa importação sobrescreva o trabalho feito na tela).
    def importar_sequenciamento_erp(self):
        centros = (
            CentroRecurso.objects.filter(recursos__ativo=True)
            .select_related("setor__departamento__filial__empresa")
            .distinct()
        )
        if not centros:
            return

        codcres_por_empresa = defaultdict(set)
        centros_por_chave = {}
        for centro in centros:
            codcre = str(centro.codigo_integrador or "").strip()
            if not codcre:
                continue
            codemp = centro.setor.departamento.filial.empresa.codemp
            codcres_por_empresa[codemp].add(codcre)
            centros_por_chave[(int(codemp), codcre)] = centro

        linhas_por_chave = self._buscar_sequenciamento_prioritario(codcres_por_empresa)
        if not linhas_por_chave:
            return

        centros_atualizados = 0
        centros_sem_alteracao = 0
        recursos_atualizados = 0
        linhas_criadas = 0
        for chave, linhas in linhas_por_chave.items():
            centro = centros_por_chave.get(chave)
            if not centro:
                continue

            recursos_ativos = list(Recurso.objects.filter(centro_recurso=centro, ativo=True))
            if not recursos_ativos:
                continue

            sequenciamento_base = self._redistribuir_prioridades(linhas)
            assinatura_desejada = self._assinatura_sequenciamento(sequenciamento_base)

            atuais_por_recurso = defaultdict(list)
            for registro in Sequenciamento.objects.filter(recurso__in=recursos_ativos).values(
                "recurso_id", "origem", "op", "estagio", "seqrot", "ordenacao"
            ):
                atuais_por_recurso[registro["recurso_id"]].append(registro)

            ja_esta_igual = all(
                self._assinatura_sequenciamento(atuais_por_recurso.get(recurso.id, []))
                == assinatura_desejada
                for recurso in recursos_ativos
            )
            if ja_esta_igual:
                centros_sem_alteracao += 1
                continue

            with transaction.atomic():
                Sequenciamento.objects.filter(recurso__in=recursos_ativos).delete()
                novos = [
                    Sequenciamento(recurso=recurso, **dados)
                    for recurso in recursos_ativos
                    for dados in sequenciamento_base
                ]
                Sequenciamento.objects.bulk_create(novos)

            centros_atualizados += 1
            recursos_atualizados += len(recursos_ativos)
            linhas_criadas += len(novos)

        if centros_atualizados or centros_sem_alteracao:
            print(
                "[SINCRONIZA_OPS_ENCERRADAS] "
                f"Sequenciamento importado do ERP: centros atualizados={centros_atualizados}; "
                f"centros sem alteração={centros_sem_alteracao}; "
                f"recursos atualizados={recursos_atualizados}; linhas criadas={linhas_criadas}"
            )


def start_sincroniza_ops_encerradas_scheduler():
    if not SincronizaOpsEncerradasScheduler._running:
        SincronizaOpsEncerradasScheduler().start()
