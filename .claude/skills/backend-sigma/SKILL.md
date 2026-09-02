---
name: backend-sigma
description: O padrão de arquitetura e engenharia do back-end do SIGMA (Django 6, Python ≥3.14). Use antes de escrever ou revisar qualquer código de servidor — view, template, form, model, migration, comando `manage.py`, regra de negócio. Traz o mapa de camadas real do projeto (inclusive o que é dívida técnica e não deve ser copiado), o idioma do código, o que é proibido e o critério de aceite. Dispara em "back-end", "Django", "view", "model", "migration", "form", "comando manage.py", "arquitetura", "padrão do projeto", "implementar", "CRUD".
paths: "accounts/** producao/** setores/** telemetria/** SIGMA/**"
---

# O padrão de back-end do SIGMA

Esta skill descreve o padrão vigente do projeto.

---

## Estado real do código

- **Stubs mortos do `startapp` removidos**: `accounts/models.py` e `producao/views.py` foram apagados; o código real está nos pacotes `accounts/models/`, `producao/models/`, `producao/views/`, reexportado pelo `__init__.py` de cada pacote. Não recrie o `.py` de raiz — ele sombreia o pacote e ressuscita o stub.
- **Reexportação por app**: `accounts/views/__init__.py` importa a maioria dos módulos de view; `producao/views/__init__.py` reexporta três (`apontamento_base`, `status_recursos`, `sequenciamento`) — os demais são importados por caminho completo em `producao/urls.py`. Ao criar view nova, siga a forma do app.
- **Clientes compartilhados de integração**: Oracle ERP/Alchemy usa `SIGMA.integracoes.oracle`; SOAP Sapiens usa `producao.services.sapiens`. WMS tem helpers por área. Código novo usa o client correspondente; ver skill `integracoes`.
- **Catálogo unificado**: todos os campos de lista fechada são `TextChoices` ou `IntegerChoices` (`Apontamento.status`, `PacoteTempoERP`, `TipoValor`, etc.).
- **Autorização padronizada**: `SIGMA.autorizacao.permissao_requerida()` é a convenção para rota privada — permite staff/superusuário, devolve 403 a autenticado sem permissão. Todas as rotas privadas usam o decorator.
- **Suíte automatizada por app**: os pacotes `<app>/tests/` cobrem autorização, filas e integrações. Entrega nova amplia essa base; não remove nem enfraquece regressões.
- **Configuração** em `SIGMA/settings.py` via `os.getenv()` + `python-dotenv` (`.env` local, `/etc/sigma/sigma.env` produção). Não há `config/` nem `django-environ`.

---

## O mapa: quem faz o quê (padrão a seguir)

| Pasta | Responde por | Nunca |
|---|---|---|
| `<app>/models/<arquivo>.py` | a entidade, campos, `TextChoices`/`IntegerChoices` de catálogo, métodos de transição de estado simples | lógica de chamada a sistema externo; regra que cruza vários apps |
| `<app>/views/<arquivo>.py` | receber requisição, checar login/papel, validar via form, chamar service quando a regra for grande, renderizar ou responder JSON | query Oracle direta remontando conexão a cada função; regra de negócio grande demais para caber numa função legível |
| `<app>/forms.py` (ou `<app>/forms/`) | validação de formulário, `clean_*`, listas fechadas vindas do `TextChoices` do model | autorização — isso é da view |
| `<app>/services/<arquivo>.py` | orquestração, worker, scheduler, o que fala com sistema externo em nome de várias views | ler `request` diretamente — recebe o que precisa por parâmetro |
| `<app>/utils/<arquivo>.py` | função pura, conversão, helper de protocolo (ex.: `sapiens_soap.py`) | estado, conexão de banco, sessão |
| `<app>/migrations/` | esquema do PostgreSQL local | qualquer coisa contra Oracle — Oracle não recebe migration deste projeto |
| `templates/<app>/` | apresentação; usa os tokens de `theme/static_src/src/styles.css` (skill `interface-sigma`) | query, regra de negócio, `{% if request.user.is_staff %}` decidindo algo que devia estar na view |
| `SIGMA/settings.py` | **o único lugar onde `os.getenv()` aparece** | valor sem comentário dizendo para que serve |
| `SIGMA/urls.py`, `<app>/urls.py` | rota | lógica |

---

## Idioma do código

| Em inglês | Em português |
|---|---|
| classes, métodos, funções, variáveis | comentários e docstrings |
| nome de coluna e tabela | rótulo de campo (`verbose_name`), mensagem de validação, texto de tela |
| chave de configuração (`SIGMA/settings.py`) | nome de app quando o domínio é em português (`producao`, `setores`) — já é a convenção do projeto |

Comentário explica **por quê** — a decisão, a alternativa descartada — não
o que a linha faz.

---

## O que é proibido, e por quê

| Proibido | Por quê | Em vez disso |
|---|---|---|
| `os.getenv()` fora de `SIGMA/settings.py` | credencial e configuração espalhadas, sem um lugar só pra auditar | ler de `settings.X` no código de app |
| recriar arquivo de raiz com nome de pacote existente (`accounts/models.py`, `producao/views.py`) | o `.py` de raiz sombreia o pacote e ressuscita o stub morto do `startapp` (removido em 2026-08-27) | arquivo novo no pacote (`models/`, `views/`) |
| `oracledb.connect()` ou cursor Oracle direto numa view/service nova | duplica a gestão de conexão e contorna o client compartilhado | `cursor_oracle_erp()`/`cursor_oracle_alchemy()` de `SIGMA.integracoes.oracle` |
| catálogo novo como inteiro cru com comentário | ninguém lê o comentário na hora de usar; `case` esquecido não dá erro nenhum | `TextChoices`/`IntegerChoices`, como `telemetria/models/estrutura.py:TipoValor` |
| `request.POST`/`request.GET` cru descendo para o service | atribuição em massa, tipo errado, validação inexistente | `Form`/`ModelForm` com `cleaned_data` |
| lógica de negócio pesada no template (`{% if %}` decidindo fluxo) | não testável | mover para a view ou para um service |
| `dd`/`print()` de depuração deixado no commit | vaza dado, polui log de produção | `logging` com nível certo, e remover antes do commit |
| segredo (senha, token) em código, log, exceção, commit ou teste | credencial real (Oracle, Sapiens, WMS, LDAP, Firebase) exposta | nome da variável de ambiente, nunca o valor |
| pacote novo sem justificativa no relatório | `uv.lock` muda para todo mundo | propor no relatório; o sênior decide (`uv add`) |
| `.raw()` / `cursor.execute()` com SQL montado por f-string/concatenação de entrada de usuário | injeção SQL | parâmetros posicionais (`cursor.execute(sql, [params])`) ou ORM |

---

## Fonte única dos campos de busca

A lista de campos que uma busca varre é **constante única no módulo da
view**, nunca cadeia de `Q()` escrita à mão e nunca texto solto no
template:

- Formato: `CAMPOS_BUSCA` — tupla de pares `(campo_orm, rotulo_de_tela)`.
  Grupo extra com o mesmo formato só quando o operador difere (ex.:
  igualdade exata numérica), e a consulta decide pelo grupo.
- **A consulta** percorre a constante (`Q(**{f"{campo}__icontains": termo})`
  em loop), com os extras legítimos (ex.: data convertida) claramente
  separados.
- **A instrução da tela** (placeholder ou pastilhas) é alimentada pela
  MESMA constante via contexto — nunca escrita à mão no template.
- **Teste anti-divergência** em `<app>/tests/`: compara o conjunto de
  lookups que a consulta constrói com a constante, e o texto de instrução
  renderizado com os rótulos da constante. A tela não pode prometer um
  conjunto diferente do que a busca varre.

---

## O fluxo de uma feature de back-end

1. **Ler o que existe.** Há view/model da mesma família no mesmo app? Qual
   documento em `docs/` (índice em `docs/sigma/README.md`) fala da área?
2. **Catálogo.** Se nasce lista fechada, `TextChoices`/`IntegerChoices` no
   model.
3. **Esquema.** Migration no PostgreSQL local; nunca contra Oracle.
4. **Model.** Campos, `TextChoices`, métodos de transição de estado
   simples (o model muda e salva o próprio estado; não chama serviço
   externo).
5. **Form.** Validação de entrada, listas fechadas do `TextChoices`.
6. **Service** (se a regra for grande ou tocar sistema externo) — recebe
   dados já validados, não lê `request`.
7. **View + rota**: para código novo, `@permissao_requerida()` e escopo de
   empresa/filial/ownership dentro da view; permissão não substitui filtro de
   objeto.
8. **Template** com os tokens de `interface-sigma`.
9. **Teste** (skill `testes`) — siga o exemplo vivo do app e cubra caminho
   feliz, guardas e estado que não pode mudar.
10. **Nota de documentação** — o que muda no documento certo em `docs/`.
11. **Esteira local verde**: `manage.py check`, `manage.py test`, `ruff
    check .`, `ruff format --check .`.

---

## Critério de aceite

Uma entrega de back-end está pronta quando passa por
[references/checklist.md](references/checklist.md) inteiro — a mesma
lista que o agente `revisor` aplica.

## Referências

| Arquivo | Quando ler |
|---|---|
| [references/arquitetura.md](references/arquitetura.md) | mapa completo de apps, exemplares bons e exemplares que são dívida técnica, com caminho real |
| [references/checklist.md](references/checklist.md) | antes de dar qualquer entrega por pronta, e ao revisar a de outro |
| [references/receitas.md](references/receitas.md) | ao criar view, formulário, migration ou fila de integração recorrente |
| skill `integracoes` | qualquer coisa que fale com Oracle, Sapiens, WMS, LDAP, Telemetria HTTP |
| skill `testes` | como escrever teste, mockar integração e ampliar os exemplos vivos |
| skill `seguranca` | a lista que toda view, formulário e integração tem de passar |
| skill `interface-sigma` | tokens de tema, componentes, build do Tailwind |
| skill `auditoria` | quando ação, histórico e log operacional precisarem ser distinguídos |
