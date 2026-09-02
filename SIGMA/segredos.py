"""Máscara única de segredos para texto de origem desconhecida.

Um só lugar conhece os segredos configurados em `SIGMA/settings.py` —
`DJANGO_SECRET_KEY`, credencial de Oracle (ERP e Alchemy), senha do banco
local, credencial SOAP do Sapiens, segredo do canal de e-mail (Microsoft
Graph), senha de bind do LDAP e caminho do arquivo de conta de serviço do
Firebase — e sabe mascará-los num texto que vai para log, tela ou e-mail:
erro de conexão, retorno de sistema externo, exceção de banco.

As máscaras por transporte continuam existindo onde já estão
(`mascarar_credenciais_soap_sapiens` para o envelope SOAP, em
`producao/utils/sapiens_soap.py`; `mascarar_url_coleta` para a URL de
coleta, em `telemetria/validacao_http.py`); este helper as agrega e
acrescenta os valores de segredo das configurações — consolida, não
substitui a abordagem. É pré-requisito do relatório de falhas: texto de erro
só vai para e-mail depois de passar por aqui.
"""

import re
from pathlib import PureWindowsPath
from typing import Any

from django.conf import settings

from producao.utils.sapiens_soap import mascarar_credenciais_soap_sapiens
from telemetria.validacao_http import mascarar_url_coleta

MASCARA = "***"
TAMANHO_MAXIMO_TOKEN_CURTO = 3

# Só http/https: a máscara de URL de telemetria foi feita para URL de coleta
# e devolve "URL inválida" para o que não reconhece — aplicá-la a qualquer
# scheme reescreveria trecho que não é dela.
_PADRAO_URL = re.compile(r"""https?://[^\s<>"']+""", re.IGNORECASE)


def _valores_segredos() -> frozenset[str]:
    """Coleta os valores de segredo das configurações no momento da chamada.

    Lê de `django.conf.settings` (nunca `os.getenv` fora de settings.py) e
    sem cache: `override_settings` em teste precisa valer na próxima
    máscara, não numa cópia congelada na importação.
    """
    configuracoes: dict[str, Any] = settings.DATABASES
    valores = (
        settings.SECRET_KEY,
        settings.SAPIENS_PASSWORD,
        settings.MICROSOFT_GRAPH_CLIENT_SECRET,
        settings.AUTH_LDAP_BIND_PASSWORD,
        settings.FIREBASE_CREDENTIALS_FILE,
        configuracoes.get("default", {}).get("PASSWORD"),
        configuracoes.get("oracle_erp", {}).get("PASSWORD"),
        configuracoes.get("oracle_alchemy", {}).get("PASSWORD"),
    )
    segredos = {valor for valor in valores if isinstance(valor, str) and valor}
    # O segredo do Firebase é o conteúdo do arquivo de conta de serviço; o
    # settings conhece só o caminho. O caminho é mascarado — inclusive pelo
    # nome do arquivo, porque erros de SDK costumam citar só o basename.
    if settings.FIREBASE_CREDENTIALS_FILE:
        nome_arquivo = PureWindowsPath(settings.FIREBASE_CREDENTIALS_FILE).name
        if nome_arquivo:
            segredos.add(nome_arquivo)
    return frozenset(segredos)


def _mascarar_valor_configurado(conteudo: str, segredo: str) -> str:
    """Mascara um segredo sem desmontar palavras ou tags por valor curto."""
    if len(segredo) <= TAMANHO_MAXIMO_TOKEN_CURTO:
        padrao_token = re.compile(rf"(?<!\w){re.escape(segredo)}(?!\w)")
        return padrao_token.sub(MASCARA, conteudo)
    return conteudo.replace(segredo, MASCARA)


def mascarar_segredos(texto: object) -> str:
    """Mascara segredos conhecidos num texto de origem desconhecida.

    Aplica, em ordem: a máscara de URL de telemetria (credencial na
    autoridade e query/fragmento somem da URL), a substituição literal dos
    valores de segredo das configurações e a máscara de credenciais do
    envelope SOAP. Idempotente: a saída desta função reapresentada a ela
    mesma sai igual.

    Aceita `None` (devolve "") e bytes (decodificados com errors="replace");
    qualquer outro objeto é convertido com `str()` — a mesma conversão que
    o chamador faria para logar. Texto sem nenhum segredo sai intocado.
    """
    if texto is None:
        return ""
    if isinstance(texto, bytes | bytearray):
        conteudo: str = bytes(texto).decode("utf-8", errors="replace")
    elif isinstance(texto, str):
        conteudo = texto
    else:
        conteudo = str(texto)

    # 1. URLs: credencial na autoridade e query/fragmento somem (padrão telemetria).
    conteudo = _PADRAO_URL.sub(lambda achou: mascarar_url_coleta(achou.group(0)), conteudo)

    # 2. Valores maiores são literais; os curtos só valem como token isolado,
    # para que uma credencial de uma letra não altere palavras ou tags do XML.
    for segredo in sorted(_valores_segredos(), key=len, reverse=True):
        conteudo = _mascarar_valor_configurado(conteudo, segredo)

    # 3. Envelope SOAP por último: <user>/<password> que sobrarem de
    # estrutura XML são mascarados (padrão Sapiens).
    return mascarar_credenciais_soap_sapiens(conteudo)
