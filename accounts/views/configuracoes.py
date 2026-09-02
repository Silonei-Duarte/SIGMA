"""Tela de configurações da aplicação: listagem agrupada e edição por chave.

Desenho do dono do produto (2026-08): a chave é parte do CÓDIGO, não da
tela. A pessoa não digita, não seleciona, não cria chave — só edita
descrição e valor das chaves declaradas em `CHAVES_CONHECIDAS`, e pode
voltar uma chave ao padrão do código (exclui a linha do banco; a declaração
em código é que define o comportamento). Não existe criar chave pela tela:
a tabela `ConfiguracaoAplicacao` é espelho do registro declarado, e linha
excluída por qualquer via → a listagem volta a mostrar o default do código
e a chave é só reconfigurada. Chave nova de configuração = nova declaração
em `CHAVES_CONHECIDAS` (código versionado), nunca criação em runtime.

Rota privada com `accounts.configurar_aplicacao` — altera comportamento de
workers e serviços em runtime, alcance que não se confunde com cadastros.
Não há escopo por filial: configuração de aplicação é única para o sistema
inteiro, o que o gate de rota resolve.

A gravação passa pelo service `definir` (validador da chave conhecida,
rastreio e log de auditoria) — a view não escreve direto. Linha no banco
com chave fora do registro não é listada nem editável por aqui: não é
gerida pela tela, e o guard de leitura do service (`obter`) é quem protege
o consumidor.
"""

from typing import Any

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render

from SIGMA.autorizacao import permissao_requerida

from ..forms import ConfiguracaoAplicacaoForm
from ..models import ConfiguracaoAplicacao
from ..services.configuracoes import CHAVES_CONHECIDAS, definir, voltar_ao_padrao

MENSAGEM_VALOR_VIGENTE = (
    "Configuração salva: {chave} passa a valer na próxima leitura, sem "
    "reiniciar o servidor — o próximo ciclo de cada worker já a enxerga."
)
MENSAGEM_PADRAO_RESTAURADO = (
    "Configuração {chave} voltou ao padrão do código: a configuração salva "
    "foi excluída e a próxima leitura devolve o default declarado."
)
MENSAGEM_JA_NO_PADRAO = (
    "Nada a voltar: {chave} já está no padrão do código — não há "
    "configuração salva no banco para esta chave."
)


def _topicos_da_lista() -> list[dict[str, Any]]:
    """Chaves conhecidas agrupadas por tópico, prontas para o template.

    Só chaves de `CHAVES_CONHECIDAS` aparecem: a tela só edita o que o
    código declara. Tópicos na ordem de primeira aparição no registro (o
    dict preserva a ordem de declaração); chaves em ordem alfabética dentro
    do tópico. Cada item mostra o que `obter()` responde: descrição e valor
    gravados no banco, ou o default do código quando não há linha (ou a
    descrição gravada ficou vazia) — com a indicação "Padrão" nesses casos,
    para que salvar por cima do que está na tela seja sempre seguro.
    """
    linhas = {
        linha.chave: linha
        # O filtro expressa a política da tela — ela só lida com o que o
        # código declara: linha plantada fora do registro já fica de fora
        # da consulta, em vez de carregar a tabela e descartar na varredura.
        for linha in ConfiguracaoAplicacao.objects.filter(
            chave__in=CHAVES_CONHECIDAS
        ).select_related("atualizado_por")
    }
    topicos: dict[str, list[dict[str, Any]]] = {}
    for conhecida in CHAVES_CONHECIDAS.values():
        linha = linhas.get(conhecida.chave)
        if linha is None:
            topicos.setdefault(conhecida.topico, []).append(
                {
                    "chave": conhecida.chave,
                    "descricao": conhecida.descricao,
                    "descricao_e_padrao": True,
                    "valor": conhecida.default,
                    "usa_padrao": True,
                    "tem_linha": False,
                    "atualizado_por": None,
                    "atualizado_em": None,
                }
            )
        else:
            # Descrição gravada vazia (ou nunca editada) cai na default do
            # código: o vazio não é uma descrição melhor que a declarada.
            descricao_e_padrao = not linha.descricao
            topicos.setdefault(conhecida.topico, []).append(
                {
                    "chave": conhecida.chave,
                    "descricao": conhecida.descricao if descricao_e_padrao else linha.descricao,
                    "descricao_e_padrao": descricao_e_padrao,
                    "valor": linha.valor,
                    "usa_padrao": False,
                    "tem_linha": True,
                    "atualizado_por": linha.atualizado_por,
                    "atualizado_em": linha.atualizado_em,
                }
            )
    for itens in topicos.values():
        itens.sort(key=lambda item: item["chave"])
    return [{"topico": topico, "itens": itens} for topico, itens in topicos.items()]


@permissao_requerida("accounts.configurar_aplicacao")
def lista_configuracoes(request):
    return render(
        request,
        "accounts/configuracoes.html",
        {"titulo": "Configurações da Aplicação", "topicos": _topicos_da_lista()},
    )


@permissao_requerida("accounts.configurar_aplicacao")
def editar_configuracao(request, chave: str):
    """Edita descrição e valor de UMA chave conhecida, por NOME, não por pk.

    A rota é por chave porque chave conhecida sem linha no banco não tem
    pk. A URL é normalizada como em `definir` (a chave em minúsculas ainda
    encontra o registro); desconhecida → 404: a tela não cria configuração,
    e o que o código não declara não é endereço de edição — tentar acessar
    é erro de endereço, não formulário esperando dados.
    """
    chave = (chave or "").strip().upper()
    conhecida = CHAVES_CONHECIDAS.get(chave)
    if conhecida is None:
        raise Http404("Chave de configuração não declarada em código.")
    linha = ConfiguracaoAplicacao.objects.filter(chave=chave).first()

    if request.method == "POST":
        form = ConfiguracaoAplicacaoForm(request.POST, conhecida=conhecida)
        if form.is_valid():
            definir(
                chave,
                form.cleaned_data["valor"],
                request.user,
                descricao=form.cleaned_data["descricao"],
            )
            messages.success(request, MENSAGEM_VALOR_VIGENTE.format(chave=chave))
            return redirect("lista_configuracoes")
    else:
        # Valores VIGENTES no form: o gravado no banco, ou o default do
        # código quando não há linha — o que a tela mostra é o que `obter()`
        # responde, e salvar por cima disso é sempre seguro.
        form = ConfiguracaoAplicacaoForm(
            initial={
                "descricao": (
                    conhecida.descricao if linha is None or not linha.descricao else linha.descricao
                ),
                "valor": conhecida.default if linha is None else linha.valor,
            },
            conhecida=conhecida,
        )
    return render(
        request,
        "accounts/form_configuracao.html",
        {
            "titulo": f"Editar {chave}",
            "form": form,
            "conhecida": conhecida,
            # "Voltar ao padrão" só tem sentido com linha salva no banco:
            # sem linha, o default já vale e o botão não renderiza.
            "tem_linha": linha is not None,
        },
    )


@permissao_requerida("accounts.configurar_aplicacao")
def voltar_ao_padrao_configuracao(request, chave: str):
    """Volta UMA chave conhecida ao padrão do código, por NOME, não por pk.

    POST próprio — a ação exclui a linha do banco, e as demais exclusões do
    app também rejeitam GET (efeito persistente não dispara por link).
    Desconhecida → 404, mesma regra da edição: o que o código não declara
    não é endereço. A exclusão em si passa pelo service `voltar_ao_padrao`
    (delete por instância, invalidação do cache, log de auditoria) — a view
    não escreve direto, como na gravação via `definir`.
    """
    chave = (chave or "").strip().upper()
    if chave not in CHAVES_CONHECIDAS:
        raise Http404("Chave de configuração não declarada em código.")

    if request.method != "POST":
        messages.error(request, "A volta ao padrão só pode ser feita por POST.")
        return redirect("lista_configuracoes")

    if voltar_ao_padrao(chave, request.user):
        messages.success(request, MENSAGEM_PADRAO_RESTAURADO.format(chave=chave))
    else:
        # Chave conhecida sem linha: o estado desejado já vale — informa em
        # vez de falhar (render e POST podem correr em paralelo).
        messages.info(request, MENSAGEM_JA_NO_PADRAO.format(chave=chave))
    return redirect("lista_configuracoes")
