"""Relatório de falhas das filas de integração por e-mail, em horários configurados.

Leva a quem operar, nos horários configurados e somente se houver pendência,
o acumulado das filas pendentes envelhecidas e das fontes de telemetria ativas
em falha — silêncio significa limpo, e o gatilho é a pendência, não o relógio.

Regras do desenho:

- Configuração vem do banco, pelo service de configurações
  (accounts/services/configuracoes.py): as chaves
  `RELATORIO_FALHAS_HORARIOS`, `RELATORIO_FALHAS_EMAIL_DESTINATARIOS` e
  `RELATORIO_FALHAS_LIMIAR_ATRASO_MINUTOS` são lidas por `obter()` no
  início de cada apuração. O cache in-process do service é invalidado por
  signal a cada gravação — alterar na tela vale sem reiniciar o processo,
  sem reconsulta a tabela a cada ciclo. Os padrões declarados em código
  (horários 07:00,16:00; destinatários ti@empresa.com.br; limiar 5) fazem o
  relatório nascer ativo; sem horário configurado (linha gravada vazia
  por fora do validador) o relatório fica desativado: o worker loga um
  aviso por ciclo e não envia nada.
- Cadência por horários: o agendador chama `executar()` a cada ciclo
  (~5 min). A cada ciclo, o horário configurado mais recente já vencido
  hoje (`horario <= agora`) é o candidato; dispara se esse horário ainda
  não gerou envio hoje e existe pendência envelhecida. Um horário 07:00
  dispara, portanto, entre 07:00 e o primeiro ciclo seguinte — a
  granularidade do disparo é a do ciclo do agendador, não o minuto exato.
  Após o envio cumprir um horário, o próximo disparo é no horário
  configurado seguinte; pendência que surge depois de um horário já
  cumprido sai no horário seguinte.
- Estado do "já cumpriu este horário" é persistido em
  `EstadoRelatorioFalhas` (singleton pk=1, producao/models/): falha de
  envio não grava estado, então o ciclo seguinte re-tenta o MESMO horário
  até conseguir; e o reinício do processo não reenvia horário já cumprido
  do dia — a marca está no banco, não em memória.
- Não existe status ERRO nas filas: pendência é o estado "não integrado"
  (o mesmo vocabulário das filas). Entra no relatório a pendência cuja
  data de geração (`datger`) tem mais do que o limiar configurado —
  regra de negócio em `RELATORIO_FALHAS_LIMIAR_ATRASO_MINUTOS`.
- Guarda de frescor: sem ciclo recente concluído pelo agendador, o
  relatório sai "não foi possível apurar" — o lado seguro do erro é
  declarar ignorância, nunca dado velho passado por fresco. A tolerância
  deriva do `intervalo_segundos` que o próprio agendador declarou no
  registry (producao/services/status.py), sem duplicar número. Esse envio
  também conta como horário cumprido (e grava o estado).
- Texto de erro cru só entra na mensagem depois de
  `SIGMA.segredos.mascarar_segredos`, e a máscara vem antes da poda:
  cortar primeiro poderia partir um segredo ao meio e a máscara não o
  reconheceria.
- Falha de envio não é falha do sistema: loga e segue — o ciclo seguinte
  re-tenta o mesmo horário. O ciclo do agendador termina normalmente.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import time as dt_time
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import QuerySet
from django.utils import timezone

from producao.services.status import (
    listar_status_services,
    marcar_ciclo_fim,
    marcar_ciclo_inicio,
    marcar_service_iniciado,
    registrar_service,
)
from SIGMA.segredos import mascarar_segredos

logger = logging.getLogger(__name__)

SERVICE_CODIGO = "relatorio_falhas_email"
SERVICE_NOME = "Relatório diário de falhas por e-mail"

# Chaves conhecidas do service de configurações (accounts/services/configuracoes.py).
CHAVE_HORARIOS = "RELATORIO_FALHAS_HORARIOS"
CHAVE_DESTINATARIOS = "RELATORIO_FALHAS_EMAIL_DESTINATARIOS"
CHAVE_LIMIAR = "RELATORIO_FALHAS_LIMIAR_ATRASO_MINUTOS"

ASSUNTO = "SIGMA — Relatório diário de falhas das filas"

_MENSAGEM_SEM_APURACAO = (
    "NÃO FOI POSSÍVEL APURAR.\n"
    "O agendador de pendências não concluiu ciclo recente. Para não relatar "
    "dado vencido, nenhuma pendência é apontada neste relatório. Consulte o "
    "painel Status (Services) e verifique o agendador."
)

# Uma seção apurada: (título, total, exemplos já formatados, registros
# omitidos pelo teto de exemplos).
Secao = tuple[str, int, list[str], int]


@dataclass(frozen=True)
class FilaRelatorio:
    """Descritor de uma fila de integração consumida pelo relatório."""

    titulo: str
    # Campos extras que o `.values()` precisa carregar para a chave.
    campos_chave: tuple[str, ...]
    formatar_chave: Callable[[dict[str, Any]], str]


class RelatorioFalhasEmailWorker:
    """Disparado a cada ciclo do EnviaPendenciasScheduler; não é thread.

    A cadência mora aqui e no banco: os horários vêm da configuração
    (`RELATORIO_FALHAS_HORARIOS`, lida a cada apuração — mudou na tela,
    vale no ciclo seguinte), e a marca de horário cumprido é
    `EstadoRelatorioFalhas`, persistida para que falha de envio re-tente o
    mesmo horário no ciclo seguinte e o reinício do processo não reenvie
    horário já cumprido do dia. A pendência continua sendo o gatilho: sem
    pendência, nada é enviado e nenhum horário é marcado como cumprido.
    """

    # O worker é invocado a cada ciclo do EnviaPendenciasScheduler: o valor
    # espelha esse ciclo e alimenta o painel (próximo ciclo), não é cadência
    # própria — a cadência é a dos horários configurados.
    INTERVALO_SEGUNDOS = 300
    TEMPO_LIMITE_CICLO_SEGUNDOS = 60
    # Tolerância da guarda de frescor, em ciclos do agendador. O intervalo
    # em segundos não vive aqui: vem do registry, declarado pelo próprio
    # scheduler — nenhum número de intervalo duplicado.
    TOLERANCIA_FRESCOR_CICLOS = 2
    TETO_EXEMPLOS_POR_FILA = 5
    TAMANHO_MAXIMO_LOG = 200

    @classmethod
    def registrar(cls) -> None:
        """Registra o worker no painel Status (Services) — chamado pelo scheduler."""
        registrar_service(
            SERVICE_CODIGO,
            SERVICE_NOME,
            intervalo_segundos=cls.INTERVALO_SEGUNDOS,
            descricao=(
                "Relatório por e-mail das pendências envelhecidas das filas "
                "de integração e das fontes de telemetria em falha; dispara "
                "nos horários configurados em RELATORIO_FALHAS_HORARIOS "
                "(configuração da aplicação), somente quando há pendência. "
                "Sem horário configurado, fica desativado."
            ),
            tempo_limite_ciclo_segundos=cls.TEMPO_LIMITE_CICLO_SEGUNDOS,
        )

    @classmethod
    def executar(cls) -> None:
        """Apura e envia; chamado dentro do ciclo do agendador.

        Falha aqui não derruba o ciclo do agendador (as filas seguintes do
        ciclo precisam rodar): loga, marca erro no registry próprio e segue.
        """
        inicio = time.time()
        marcar_service_iniciado(SERVICE_CODIGO)
        marcar_ciclo_inicio(SERVICE_CODIGO)
        erro = ""
        try:
            cls._executar_ciclo()
        except Exception:
            erro = "Falha na apuração ou no envio do relatório"
            logger.exception("Falha no relatório diário de falhas das filas.")
        finally:
            marcar_ciclo_fim(SERVICE_CODIGO, time.time() - inicio, cls.INTERVALO_SEGUNDOS, erro)

    @classmethod
    def _executar_ciclo(cls) -> None:
        agora = timezone.now()

        horarios = cls._horarios_configurados()
        if not horarios:
            logger.warning(
                "Relatório de falhas desativado: nenhum horário configurado em %s.",
                CHAVE_HORARIOS,
            )
            return

        # Guarda antes de apurar: sem destinatários a apuração inteira seria
        # trabalho jogado fora e o relatório ficaria mudo com pendência real.
        destinatarios = cls._destinatarios()
        if not destinatarios:
            logger.warning(
                "Relatório de falhas desativado: %s sem destinatários.",
                CHAVE_DESTINATARIOS,
            )
            return

        horario_vencido = cls._horario_vencido(horarios, agora)
        if horario_vencido is None or cls._horario_ja_cumprido(horario_vencido, agora):
            return

        corte = agora - timedelta(minutes=cls._limiar_minutos())
        secoes = cls._apurar_filas(corte, agora) + cls._apurar_telemetria(agora)
        if not any(total for _titulo, total, _exemplos, _restantes in secoes):
            # Sem pendência não envia nada e NÃO marca o horário como
            # cumprido: a pendência que surgir depois dispara no próximo
            # ciclo, ainda dentro deste horário.
            return

        if not cls._apuracao_fresca():
            # O gatilho continua sendo a pendência (por isso apuramos a
            # existência), mas o corpo não apresenta dado: sem ciclo recente
            # do agendador, declara ignorância. Conta como horário cumprido.
            cls._enviar(cls._corpo(_MENSAGEM_SEM_APURACAO), agora, destinatarios)
            return

        cls._enviar(cls._corpo(cls._corpo_secoes(secoes)), agora, destinatarios)

    # ========================
    # Configuração (banco, via service de configurações)
    # ========================
    @staticmethod
    def _config_valor(chave: str) -> str:
        """Valor vigente da chave, servido do cache do service de configurações.

        Import local: este módulo é carregado pelo scheduler durante o
        bootstrap dos apps (mesmo padrão dos models abaixo).
        """
        from accounts.services.configuracoes import obter

        return obter(chave) or ""

    @classmethod
    def _horarios_configurados(cls) -> list[dt_time]:
        """Horários HH:MM configurados, ordenados; item inválido é ignorado.

        O validador da chave conhecida só vale na gravação pelo `definir()`;
        linha plantada por outra via (shell, migração) pode trazer lixo —
        ignora o item e segue com os válidos em vez de derrubar a apuração.
        """
        horarios: list[dt_time] = []
        for parte in cls._config_valor(CHAVE_HORARIOS).split(","):
            item = parte.strip()
            if not item:
                continue
            try:
                horarios.append(datetime.strptime(item, "%H:%M").time())
            except ValueError:
                logger.warning("Horário inválido ignorado em %s: %s.", CHAVE_HORARIOS, item)
        return sorted(horarios)

    @classmethod
    def _limiar_minutos(cls) -> int:
        """Limiar de envelhecimento (minutos); inválido cai no default da chave."""
        from accounts.services.configuracoes import CHAVES_CONHECIDAS

        try:
            limiar = int(cls._config_valor(CHAVE_LIMIAR))
        except ValueError:
            limiar = 0
        if limiar < 1:
            # Gravado fora do validador: o default declarado na chave
            # conhecida responde — config ruim não derruba a apuração.
            logger.warning("%s inválido; usando o padrão declarado.", CHAVE_LIMIAR)
            limiar = int(CHAVES_CONHECIDAS[CHAVE_LIMIAR].default)
        return limiar

    @classmethod
    def _destinatarios(cls) -> list[str]:
        """Destinatários da configuração (um por linha); vazio é sem envio.

        Revalidação na leitura: o validador da chave conhecida só vale na
        gravação pelo `definir()`; linha plantada por outra via (shell,
        migração) pode trazer endereço malformado — loga aviso e ignora o
        item, no mesmo espírito dos horários inválidos, para que o envio
        não fique re-tentando um destinatário que a API sempre rejeita.
        """
        from django.core.exceptions import ValidationError
        from django.core.validators import validate_email

        validos: list[str] = []
        for linha in cls._config_valor(CHAVE_DESTINATARIOS).splitlines():
            item = linha.strip()
            if not item:
                continue
            try:
                validate_email(item)
            except ValidationError:
                logger.warning(
                    "Destinatário inválido ignorado em %s: %s.", CHAVE_DESTINATARIOS, item
                )
                continue
            validos.append(item)
        return validos

    # ========================
    # Cadência por horários
    # ========================
    @staticmethod
    def _horario_vencido(horarios: list[dt_time], agora: datetime) -> dt_time | None:
        """Horário configurado mais recente já vencido hoje (None se nenhum)."""
        hora_agora = timezone.localtime(agora).time()
        vencidos = [horario for horario in horarios if horario <= hora_agora]
        return vencidos[-1] if vencidos else None

    @staticmethod
    def _horario_ja_cumprido(horario: dt_time, agora: datetime) -> bool:
        """Verdade quando o horário já gerou envio hoje, pelo estado no banco.

        O envio acontece depois do horário (entre ele e o próximo ciclo do
        agendador), então "cumprido" é: último envio hoje, às `horario` ou
        depois. Falha de envio não grava estado — o horário permanece por
        cumprir e o ciclo seguinte re-tenta. Reinício do processo não perde
        a marca: ela está no banco.
        """
        from producao.models import EstadoRelatorioFalhas

        estado = EstadoRelatorioFalhas.objects.filter(pk=1).first()
        ultimo = estado.ultimo_envio_em if estado else None
        if ultimo is None:
            return False
        if timezone.localdate(ultimo) != timezone.localdate(agora):
            return False
        return timezone.localtime(ultimo).time() >= horario

    @staticmethod
    def registrar_envio(quando: datetime) -> None:
        """Marca o horário como cumprido no estado persistido (singleton pk=1).

        Gravação por save de instância: model de estado próprio do worker,
        sem cache a invalidar (a regra de `definir()`/signal é da tabela de
        configuração, não desta).
        """
        from producao.models import EstadoRelatorioFalhas

        estado, _criado = EstadoRelatorioFalhas.objects.get_or_create(pk=1)
        estado.ultimo_envio_em = quando
        estado.save()

    # ========================
    # Guarda de frescor
    # ========================
    @classmethod
    def _apuracao_fresca(cls) -> bool:
        ultimo_fim, intervalo = cls._ciclo_agendador()
        if ultimo_fim is None or not intervalo:
            return False
        tolerancia = cls.TOLERANCIA_FRESCOR_CICLOS * intervalo
        return (timezone.now() - ultimo_fim).total_seconds() <= tolerancia

    @staticmethod
    def _ciclo_agendador() -> tuple[datetime | None, int | None]:
        """Último ciclo concluído e intervalo declarado pelo próprio agendador."""
        from producao.services.envia_pendencias import SERVICE_CODIGO as CODIGO_AGENDADOR

        # Constante do dono, não literal: se o código do agendador mudar,
        # a guarda deixa de achar e o relatório passa a "não apurar" —
        # segura, mas visível; um literal silenciaria isso.
        for service in listar_status_services():
            if service.get("codigo") == CODIGO_AGENDADOR:
                return service.get("ultimo_ciclo_fim"), service.get("intervalo_segundos")
        return None, None

    # ========================
    # Apuração
    # ========================
    @classmethod
    def _filas(cls, corte: datetime) -> list[tuple[FilaRelatorio, QuerySet[Any]]]:
        """Filas pendentes envelhecidas, mais antigos primeiro.

        Imports locais: este módulo é carregado pelo scheduler durante o
        bootstrap dos apps; models por aqui seguem o padrão de
        envia_pendencias.
        """
        from producao.models import (
            Apontamento,
            ApontamentoComponente,
            BaixaComponente,
            PacoteTempoERP,
        )
        from setores.qualidade.models import LiberacaoLote
        from setores.qualidade.models.estrutura import WMS_IntegraçãoOP

        def chave_apontamento(registro: dict[str, Any]) -> str:
            return f"OP {registro['numorp']} (estágio {registro['codetg']})"

        def chave_pacote(registro: dict[str, Any]) -> str:
            return f"OP {registro['troca_op_ativa__op']}"

        def chave_componente(registro: dict[str, Any]) -> str:
            return f"OP {registro['numorp']} (lote {registro['lote']})"

        def chave_baixa(registro: dict[str, Any]) -> str:
            return f"OP {registro['numorp']} (lote bobina {registro['codlot']})"

        def chave_wms(registro: dict[str, Any]) -> str:
            return f"OP {registro['op']} (lote {registro['lote']})"

        def chave_lote(registro: dict[str, Any]) -> str:
            return f"lote {registro['codlot']} (bobina {registro['numbob']})"

        descritores = [
            FilaRelatorio("Fila Log Apontamentos", ("numorp", "codetg"), chave_apontamento),
            FilaRelatorio("Fila Log Tempos ERP", ("troca_op_ativa__op",), chave_pacote),
            FilaRelatorio(
                "Fila Log Apontamento Componentes",
                ("numorp", "lote"),
                chave_componente,
            ),
            FilaRelatorio("Fila Baixa Componentes", ("numorp", "codlot"), chave_baixa),
            FilaRelatorio("Fila WMS Integrações", ("op", "lote"), chave_wms),
            FilaRelatorio("Fila Consulta de Lotes", ("codlot", "numbob"), chave_lote),
        ]

        querysets = [
            Apontamento.objects.filter(status=Apontamento.Status.NAO_INTEGRADO, datger__lt=corte),
            PacoteTempoERP.objects.filter(status=PacoteTempoERP.Status.PENDENTE, datger__lt=corte),
            ApontamentoComponente.objects.filter(
                status=ApontamentoComponente.Status.NAO_INTEGRADO, datger__lt=corte
            ),
            BaixaComponente.objects.filter(
                status=BaixaComponente.Status.NAO_INTEGRADO, datger__lt=corte
            ),
            WMS_IntegraçãoOP.objects.filter(
                status=WMS_IntegraçãoOP.Status.NAO_INTEGRADO, datger__lt=corte
            ),
            LiberacaoLote.objects.filter(
                status=LiberacaoLote.Status.NAO_INTEGRADO, datger__lt=corte
            ),
        ]
        # Mesma ordem de construção, sempre em pares; um desencontro aqui
        # é erro de programação e strict=True o levanta imediatamente.
        return list(zip(descritores, querysets, strict=True))

    @classmethod
    def _apurar_filas(cls, corte: datetime, agora: datetime) -> list[Secao]:
        secoes: list[Secao] = []
        for descritor, queryset in cls._filas(corte):
            registros = queryset.order_by("datger", "id").values(
                "id", "datger", "log", *descritor.campos_chave
            )
            total = registros.count()
            if not total:
                continue
            exemplos = [
                cls._linha_exemplo(registro, descritor.formatar_chave, agora)
                for registro in registros[: cls.TETO_EXEMPLOS_POR_FILA]
            ]
            secoes.append((descritor.titulo, total, exemplos, total - len(exemplos)))
        return secoes

    @classmethod
    def _apurar_telemetria(cls, agora: datetime) -> list[Secao]:
        from telemetria.models import FonteColetaHTTP
        from telemetria.services.coleta import LOG_COLETA_SUCESSO

        # Fonte ativa cuja última tentativa não tem o log de sucesso está
        # em falha; a constante vive no coletor, dono do contrato.
        fontes = (
            FonteColetaHTTP.objects.filter(coleta_ativa=True)
            .exclude(ultima_coleta_em=None)
            .exclude(log=LOG_COLETA_SUCESSO)
            .order_by("ultima_coleta_em")
        )
        total = fontes.count()
        if not total:
            return []

        exemplos: list[str] = []
        for fonte in fontes[: cls.TETO_EXEMPLOS_POR_FILA]:
            ultima = fonte.ultima_coleta_em
            if ultima is None:  # inalcançável: a consulta exclui fonte sem tentativa
                continue
            # A URL de coleta pode carregar credencial: sai mascarada
            # (host permanece, é o que identifica a fonte para operar).
            exemplos.append(
                f"{mascarar_segredos(fonte.url)} — última tentativa há "
                f"{cls._formatar_idade(ultima, agora)}"
            )
        return [("Fontes de telemetria ativas em falha", total, exemplos, total - len(exemplos))]

    @classmethod
    def _linha_exemplo(
        cls,
        registro: dict[str, Any],
        formatar_chave: Callable[[dict[str, Any]], str],
        agora: datetime,
    ) -> str:
        partes = [f"id {registro['id']}", formatar_chave(registro)]
        datger = registro.get("datger")
        if datger:
            partes.append(f"pendente há {cls._formatar_idade(datger, agora)}")
        motivo = cls._poda_mascara(registro.get("log") or "")
        if motivo:
            partes.append(f"motivo: {motivo}")
        return " — ".join(partes)

    @classmethod
    def _poda_mascara(cls, texto: str) -> str:
        """Máscara antes da poda: cortar primeiro truncaria o segredo ao meio."""
        mascarado = mascarar_segredos(texto)
        compacto = " ".join(mascarado.split())
        if len(compacto) <= cls.TAMANHO_MAXIMO_LOG:
            return compacto
        return compacto[: cls.TAMANHO_MAXIMO_LOG].rstrip() + "…"

    @staticmethod
    def _formatar_idade(inicio: datetime, fim: datetime) -> str:
        segundos = max(int((fim - inicio).total_seconds()), 0)
        minutos, _ = divmod(segundos, 60)
        horas, minutos = divmod(minutos, 60)
        dias, horas = divmod(horas, 24)
        if dias:
            return f"{dias}d{horas:02d}h"
        if horas:
            return f"{horas}h{minutos:02d}min"
        return f"{minutos}min"

    @staticmethod
    def _corpo(conteudo: str) -> str:
        cabecalho = (
            "Relatório diário de falhas das filas — SIGMA\n"
            f"Gerado em {timezone.localtime().strftime('%d/%m/%Y %H:%M')}.\n"
        )
        return f"{cabecalho}\n{conteudo}".rstrip() + "\n"

    @classmethod
    def _corpo_secoes(cls, secoes: list[Secao]) -> str:
        linhas: list[str] = []
        for titulo, total, exemplos, restantes in secoes:
            linhas.append(f"{titulo}: {total} pendência(s) envelhecida(s).")
            linhas.extend(f"- {exemplo}" for exemplo in exemplos)
            if restantes > 0:
                linhas.append(f"- e mais {restantes} registro(s)…")
            linhas.append("")
        return "\n".join(linhas).rstrip()

    @classmethod
    def _enviar(cls, corpo: str, agora: datetime, destinatarios: list[str]) -> None:
        if not destinatarios:
            logger.warning(
                "Relatório de falhas não enviado: %s sem destinatários.",
                CHAVE_DESTINATARIOS,
            )
            return

        try:
            enviados = send_mail(
                subject=ASSUNTO,
                message=corpo,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=destinatarios,
                fail_silently=False,
            )
        except Exception:
            # Caixa ainda não liberada (ou canal de e-mail fora) não é falha
            # do sistema: loga e segue — o ciclo seguinte re-tenta o MESMO
            # horário, porque falha de envio não grava estado.
            logger.exception("Falha no envio do relatório diário de falhas por e-mail.")
            return

        if enviados == 0:
            logger.warning(
                "Relatório de falhas não enviado: o backend de e-mail não aceitou nenhum destinatário."
            )
            return

        cls.registrar_envio(agora)
