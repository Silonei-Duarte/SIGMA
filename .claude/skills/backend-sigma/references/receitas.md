# Receitas de back-end Django

Use como ponto de partida, depois de ler um exemplar vivo do app tocado. As
receitas evitam repetir contratos de segurança e fila; não substituem a regra
de negócio nem o documento funcional da área.

## 1. View privada com permissão e escopo

```python
from django.http import Http404

from SIGMA.autorizacao import permissao_requerida


@permissao_requerida("producao.pode_visualizar_exemplo")
def detalhe_exemplo(request, item_id):
    itens = itens_visiveis_para(request.user)
    item = itens.filter(pk=item_id).first()
    if item is None:
        raise Http404
    return render(request, "producao/exemplo.html", {"item": item})
```

Permissão responde **quem pode entrar**; queryset responde **quais objetos
podem ser vistos ou alterados**. Teste: anônimo redireciona, sem permissão
recebe 403, staff funciona e identificador de outra filial não revela dado.

## 2. Formulário antes do service

```python
class ExemploForm(forms.Form):
    codigo = forms.IntegerField(min_value=1)
    observacao = forms.CharField(max_length=500, required=False)


@permissao_requerida("producao.pode_manipular_exemplo")
@require_POST
def salvar_exemplo(request):
    form = ExemploForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)

    executar_exemplo(**form.cleaned_data)
    return JsonResponse({"ok": True})
```

Dados de `request.POST` e `request.GET` não descem para service. Quando o
formulário representa model, prefira `ModelForm` e restrinja seus querysets ao
escopo visível antes de `is_valid()`.

## 3. Migration de modelo Django

1. Altere o model real no pacote, preservando valores já persistidos.
2. Gere migration nova; nunca edite migration aplicada.
3. Se um campo texto deixar de aceitar `NULL`, faça backfill idempotente antes
   de `AlterField`.
4. Teste `makemigrations --check --dry-run` e o caminho que lê/escreve o
   campo. Reverso que não consegue reconstruir dado antigo deve ser declarado
   como noop, não inventado.

## 4. Fila para integração externa

1. Grave a intenção local e feche a transação antes da chamada externa.
2. Reserve somente pendências elegíveis com lock/transação; falha preserva a
   linha como pendente ou erro reprocessável.
3. Transporte usa o client comum: `cursor_oracle_*()` para Oracle e
   `enviar_soap_sapiens()` para Sapiens. Declare timeout.
4. Worker novo entra em `EnviaPendenciasScheduler`, salvo justificativa
   documentada para outro agendamento.
5. Teste sucesso, resposta de erro, exceção de rede, reserva concorrente e
   máscara de segredo. Sempre mocke a integração no ponto de chamada.
