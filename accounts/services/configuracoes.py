"""Configurações de aplicação: leitura com cache em memória e gravação rastreada.

Requisito do desenho: valor salvo pela tela passa a valer sem reiniciar o
servidor e sem que os workers reconsultem a tabela a cada ciclo. O cache é
**in-process**: `obter()` serve da memória na segunda leitura adiante e os
signals `post_save`/`post_delete` de `ConfiguracaoAplicacao` atualizam ou
limpam a entrada no momento em que o dado muda — salvar já é invalidar.

Limitação registrada (não construir hoje): o SIGMA roda num único processo
(Daphne/ASGI; os workers são threads do mesmo processo Django), então um
dict com lock basta. Se um dia algum worker sair para processo próprio,
este desenho precisa de revisão — não há invalidação entre processos, e
TTL/reconsulta periódica foi descartada de propósito.

Por que preenchimento lazy (primeira leitura) e não carga total ao iniciar:
`accounts/apps.py` evita deliberadamente consultar o banco durante o
bootstrap (o Django ainda está inicializando as apps), e uma carga no
startup quebraria `migrate`/teste em banco novo. Lazy é equivalente em
correção — os signals mantêm o cache fresco a partir da primeira leitura —
e não toca o banco antes da hora. As chaves conhecidas sem linha no banco
nem chegam a precisar de carga: o default do registro já responde.

Desenho da tela (dono do produto, 2026-08): a chave é parte do CÓDIGO, não
da tela. A pessoa não digita, não seleciona, não cria e não remove chave —
só edita descrição e valor das chaves declaradas em `CHAVES_CONHECIDAS`.
A tabela é espelho do registro declarado: linha excluída por qualquer via
→ a listagem volta a mostrar o default do código e a chave é reconfigurada
pela edição. Nova chave de configuração = nova declaração aqui (código
versionado), nunca criação em runtime — por isso não existe criar/remover.
"""

import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from accounts.models import ConfiguracaoAplicacao, CustomUser

logger = logging.getLogger(__name__)


# ========================
# Registro de chaves conhecidas
# ========================
@dataclass(frozen=True)
class ChaveConhecida:
    """Chave com contrato declarado: tópico, descrição, default e validação.

    Chave conhecida sem linha no banco responde o `default` em `obter()`;
    a tela mostra esse default na listagem e no formulário de edição. O
    `topico` agrupa a chave na listagem (categoria de negócio, ex.: e-mail
    de relatórios). Consumidor novo de configuração declara a chave aqui,
    com tópico e validador próprios — nunca cria linha direto no banco.
    """

    chave: str
    topico: str
    descricao: str
    default: str
    validador: Callable[[str], str]


_PADRAO_HORARIO = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _validar_destinatarios_email(valor: str) -> str:
    """Um e-mail por linha; devolve lowercase, sem linha vazia, sem repetição."""
    emails = [linha.strip() for linha in valor.splitlines() if linha.strip()]
    if not emails:
        raise ValidationError("Informe pelo menos um e-mail (um por linha).")
    unicos: dict[str, None] = {}
    for email in emails:
        try:
            validate_email(email)
        except ValidationError:
            raise ValidationError(f"E-mail inválido: {email}") from None
        unicos[email.lower()] = None
    return "\n".join(unicos)


def _validar_horarios(valor: str) -> str:
    """Horários HH:MM separados por vírgula; dedupe e ordenação normalizados."""
    itens = [parte.strip() for parte in valor.replace(";", ",").split(",") if parte.strip()]
    if not itens:
        raise ValidationError("Informe pelo menos um horário (ex.: 07:00,16:00).")
    for item in itens:
        if not _PADRAO_HORARIO.match(item):
            raise ValidationError(f"Horário inválido: {item}. Use HH:MM (ex.: 07:00,16:00).")
    return ",".join(sorted(set(itens)))


def _validar_limiar_minutos(valor: str) -> str:
    """Inteiro entre 1 e 1440 (um dia); devolve a forma canônica sem zeros à esquerda."""
    try:
        numero = int(valor.strip())
    except ValueError:
        raise ValidationError("Informe um número inteiro de minutos (ex.: 5).") from None
    if not 1 <= numero <= 1440:
        raise ValidationError("O limiar deve ficar entre 1 e 1440 minutos (um dia).")
    return str(numero)


# Registro das chaves geridas pela tela: só o que está aqui aparece e é
# editável. Chave nova de configuração entra como declaração neste dict
# (código versionado, com tópico e validador) — nunca criação em runtime.
# A ordem de declaração define a ordem dos tópicos na listagem.
CHAVES_CONHECIDAS: Final[dict[str, ChaveConhecida]] = {
    "RELATORIO_FALHAS_EMAIL_DESTINATARIOS": ChaveConhecida(
        chave="RELATORIO_FALHAS_EMAIL_DESTINATARIOS",
        topico="E-mail — Relatórios",
        descricao=(
            "Destinatários do relatório diário de falhas das filas, um e-mail "
            "por linha. Padrão: ti@ipel.ind.br."
        ),
        default="ti@ipel.ind.br",
        validador=_validar_destinatarios_email,
    ),
    "RELATORIO_FALHAS_HORARIOS": ChaveConhecida(
        chave="RELATORIO_FALHAS_HORARIOS",
        topico="E-mail — Relatórios",
        descricao=(
            "Horários de envio do relatório diário de falhas, separados por "
            "vírgula. Padrão: 07:00,16:00."
        ),
        default="07:00,16:00",
        validador=_validar_horarios,
    ),
    "RELATORIO_FALHAS_LIMIAR_ATRASO_MINUTOS": ChaveConhecida(
        chave="RELATORIO_FALHAS_LIMIAR_ATRASO_MINUTOS",
        topico="E-mail — Relatórios",
        descricao=(
            "Pendência envelhecida do relatório de falhas = pendente há mais "
            "do que este limiar, em minutos (1 a 1440)."
        ),
        default="5",
        validador=_validar_limiar_minutos,
    ),
}


# ========================
# Guard anti-segredo
# ========================
# O nome da chave é o que a guard protege: um nome com padrão de segredo
# denuncia intenção de guardar credencial na tabela errada. Padrões em
# inglês cobrem a convenção dos `.env`; SENHA e CREDENCIAL cobrem o
# vocabulário em português. Substring simples é proposital: preferimos
# falso positivo (chave rejeitada, pessoa escolhe outro nome) a falso
# negativo (credencial gravada em banco consultável por tela).
_PADROES_SEGREDO_CHAVE: Final[tuple[str, ...]] = (
    "PASSWORD",
    "SECRET",
    "TOKEN",
    "KEY",
    "CREDENTIAL",
    "SENHA",
    "CREDENCIAL",
)


def chave_parece_segredo(chave: str) -> bool:
    """Verdade quando o NOME da chave carrega padrão de segredo — rejeitar."""
    return any(padrao in chave.upper() for padrao in _PADROES_SEGREDO_CHAVE)


# Valor: a política da tela é ser não sensível, e adivinhar segredo em
# valor é impossível em geral — aqui só o óbvio é avisado (par
# `nome=valor` com nome de credencial). Aviso não bloqueia: quem edita
# vê a tela, o revisor de segurança opina sobre a política, e o log
# registra o fato SEM repetir o valor.
_PADRAO_VALOR_CREDENCIAL = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[-_ ]?key|credential|senha)\b\s*[:=]"
)


def valor_parece_credencial(valor: str) -> bool:
    """Verdade quando o VALOR contém par `nome=valor` óbvio de credencial — só avisar."""
    return bool(_PADRAO_VALOR_CREDENCIAL.search(valor))


# ========================
# Formato da chave
# ========================
# Dono único do formato de chave de configuração: este service. A tela não
# recebe chave nenhuma no desenho atual (o formulário só tem descrição e
# valor; a chave vem da URL e é validada contra `CHAVES_CONHECIDAS`) — a
# constante serve à gravação FORA da tela (shell, comando `manage.py`,
# consumidor futuro): `definir()` rejeita formato inválido antes de tocar
# o banco, para que o que entra por outra via não escape da forma que o
# código declara como chave conhecida.
PADRAO_CHAVE_CONFIGURACAO: Final = re.compile(r"^[A-Z][A-Z0-9_]*$")


# ========================
# Cache in-process
# ========================
# Estado por chave: o valor vigente (str) ou None para "sem linha e sem
# default" — a ausência também é cacheada, para que leitura repetida de
# chave inexistente não vire reconsulta a cada ciclo. Guardado por lock:
# a leitura acontece em várias threads (views e workers).
_cache: Final[dict[str, str | None]] = {}
_trava_cache = threading.Lock()


def limpar_cache() -> None:
    """Esvazia o cache do processo (uso em teste e entre suítes)."""
    with _trava_cache:
        _cache.clear()


def obter(chave: str, default: str | None = None) -> str | None:
    """Valor vigente da configuração, servido do cache do processo.

    - Chave com linha no banco: o valor gravado.
    - Chave conhecida sem linha: o default do registro (também cacheado).
    - Chave desconhecida sem linha: o `default` do chamador (ausência
      cacheada como None — a leitura seguinte não repete a consulta).

    Chamar de novo depois de `definir` (ou de salvar/excluir pelo ORM)
    devolve o valor novo sem nova consulta: os signals mantêm o cache.

    Chave com padrão de segredo é rejeitada — decisão datada do sênior:
    o guard da escrita não cobre linha gravada por shell/migração, e a
    leitura não pode virar a superfície que serve a credencial. Falha
    explícita em vez de valor silencioso. A chave é normalizada como em
    `definir`, para que a caixa usada na chamada não divida o cache.
    """
    chave = (chave or "").strip().upper()
    if chave_parece_segredo(chave):
        raise ValidationError(
            "Chave rejeitada: o nome indica segredo. Credencial vai no .env, não aqui."
        )
    with _trava_cache:
        if chave in _cache:
            estado: str | None = _cache[chave]
            return default if estado is None else estado

    # Fora do lock: uma única query por preenchimento. Duas threads podem
    # consultar em paralelo na primeira leitura; quem grava, revalida sob o
    # lock abaixo para que o valor mais novo prevaleça.
    valor_banco = (
        ConfiguracaoAplicacao.objects.filter(chave=chave).values_list("valor", flat=True).first()
    )
    if valor_banco is not None:
        estado = valor_banco
    else:
        conhecida = CHAVES_CONHECIDAS.get(chave)
        estado = conhecida.default if conhecida is not None else None
    with _trava_cache:
        if chave in _cache:
            # Revalidação antes de gravar: entre a query e esta escrita,
            # outra thread pode ter preenchido a entrada (ex.: signal de um
            # `definir()` com valor mais novo que o lido do banco). Gravar
            # por cima ressuscitaria o valor velho até a próxima gravação —
            # prevalece quem gravou por último, não quem leu primeiro.
            estado = _cache[chave]
        else:
            _cache[chave] = estado
    return default if estado is None else estado


def definir(
    chave: str,
    valor: str,
    usuario: CustomUser | None,
    descricao: str | None = None,
) -> ConfiguracaoAplicacao:
    """Grava a configuração com rastreio e registra o fato em log.

    Segunda barreira da guard anti-segredo (a primeira é o formulário):
    normaliza a chave para a forma canônica, rejeita formato inválido e
    chave com padrão de segredo, e aplica o validador da chave conhecida,
    mesmo quando chamado fora da tela. A tela chama `definir` só para chave
    de `CHAVES_CONHECIDAS` — chave fora do registro não é gerida por ela
    (o guard de leitura em `obter` é quem protege o consumidor). O log de
    auditoria registra ator, chave e ação — nunca o valor (a chave é
    genérica; registrar o valor seria decisão de política, e o rastreio
    consultável já vive no próprio registro e na tela).
    """
    # Normaliza antes de qualquer barreira: a chave gravada é a canônica
    # (maiúsculas, sem espaço das pontas), igual ao formulário — gravar fora
    # da tela não escapa da regra, e uma chave conhecida digitada em
    # minúsculas cai no validador dela em vez de virar linha nova.
    chave = (chave or "").strip().upper()
    if not PADRAO_CHAVE_CONFIGURACAO.match(chave):
        raise ValidationError(
            "Chave inválida: use apenas letras maiúsculas, dígitos e underscore, "
            "começando por letra (ex.: RELATORIO_FALHAS_HORARIOS)."
        )

    if chave_parece_segredo(chave):
        raise ValidationError(
            "Chave rejeitada: o nome indica segredo. Credencial vai no .env, não aqui."
        )

    conhecida = CHAVES_CONHECIDAS.get(chave)
    if conhecida is not None:
        valor = conhecida.validador(valor)

    if valor_parece_credencial(valor):
        logger.warning(
            "Configuração %s salva com valor que aparenta conter credencial; "
            "a política desta tela é não sensível.",
            chave,
        )

    padroes: dict[str, Any] = {"valor": valor, "atualizado_por": usuario}
    if descricao is not None:
        padroes["descricao"] = descricao
    linha, criada = ConfiguracaoAplicacao.objects.update_or_create(chave=chave, defaults=padroes)
    logger.info(
        "Configuração %s %s por %s.",
        chave,
        "criada" if criada else "atualizada",
        usuario.get_username() if usuario is not None else "sistema",
    )
    return linha


def voltar_ao_padrao(chave: str, usuario: CustomUser | None) -> bool:
    """Exclui a linha da chave, que volta ao default do código — a ação
    "Voltar ao padrão" da tela de edição.

    Sem linha no banco, `obter()` já responde o default declarado em
    `CHAVES_CONHECIDAS`; devolve False nesse caso (a tela esconde o botão
    nesse estado, e uma corrida entre render e POST só confirma o estado —
    nada a excluir não é erro).

    A exclusão é SEMPRE por instância (`instance.delete()`), nunca
    `queryset.update()` nem `queryset.delete()` em massa: a invalidação do
    cache do processo depende do signal `post_delete` disparado por linha
    excluída — a mesma regra que o model impõe à gravação (update/bulk não
    disparam signal e deixariam o cache servindo valor velho até reinício).

    Log de auditoria registra ator, chave e ação — nunca o valor, igual ao
    log de `definir`: o rastreio do que havia morre junto com a linha, e o
    registro operacional é quem guarda o fato de quem voltou o quê.
    """
    chave = (chave or "").strip().upper()
    linha = ConfiguracaoAplicacao.objects.filter(chave=chave).first()
    if linha is None:
        return False
    linha.delete()
    logger.info(
        "Configuração %s voltada ao padrão do código por %s.",
        chave,
        usuario.get_username() if usuario is not None else "sistema",
    )
    return True


@receiver(
    post_save,
    sender=ConfiguracaoAplicacao,
    dispatch_uid="accounts.configuracoes.cache_salvamento",
)
def _cache_por_salvamento(
    sender: type[ConfiguracaoAplicacao], instance: ConfiguracaoAplicacao, **kwargs: Any
) -> None:
    """Salvou (tela, ORM ou comando) → próxima leitura já serve o valor novo."""
    with _trava_cache:
        _cache[instance.chave] = instance.valor


@receiver(
    post_delete,
    sender=ConfiguracaoAplicacao,
    dispatch_uid="accounts.configuracoes.cache_exclusao",
)
def _cache_por_exclusao(
    sender: type[ConfiguracaoAplicacao], instance: ConfiguracaoAplicacao, **kwargs: Any
) -> None:
    """Excluiu → esquece a chave: conhecida volta ao default, desconhecida
    volta ao default do chamador (estado recarregado na próxima leitura)."""
    with _trava_cache:
        _cache.pop(instance.chave, None)
