---
name: commits
description: O padrão de commit do SIGMA e o procedimento para commitar — Conventional Commits em português (tipo, escopo, resumo no imperativo, corpo que explica o porquê), um commit por mudança lógica, verificação local antes, e o que nunca entra. Use ao preparar, escrever ou revisar um commit, e quando a demanda pedir "commita", "faz o commit", "prepara o commit", "mensagem de commit", "git".
argument-hint: "[mensagem opcional]"
---

# Commits no SIGMA

O histórico é documentação: `git log` precisa responder "o que mudou e por
quê" sem abrir o diff. Padrão: **Conventional Commits, em português**, com
corpo que explica a decisão.

## A mensagem

```
tipo(escopo): resumo no imperativo, minúsculas, sem ponto final

Por que a mudança existe — o problema, a decisão, a alternativa descartada.
Em português, parágrafos curtos.

Doc: docs/sigma/07-integracoes-externas.md (ou "sem doc a atualizar: <motivo>")

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
```

**Tipos** (o único inglês da mensagem):

| Tipo | Quando |
|---|---|
| `feat` | comportamento novo para quem usa ou opera |
| `fix` | correção de comportamento errado |
| `refactor` | mudança de estrutura sem mudar comportamento |
| `perf` | mais rápido ou mais leve, sem mudar comportamento |
| `test` | só testes |
| `docs` | só documentação (`docs/`, comentários, `CLAUDE.md`, skills) |
| `chore` | manutenção que não é nenhum dos anteriores (dependência, config de ferramenta) |
| `style` | formatação sem mudança de código (`ruff format`) |
| `revert` | desfaz um commit; o corpo cita o hash |

**Escopo** (opcional, curto): `producao`, `qualidade`, `manutencao`,
`suprimentos`, `telemetria`, `accounts`, `oracle`, `sapiens`, `wms`,
`ldap`, `telemetria`, `notificacoes`, `deploy`, `docs`. Sem escopo quando a
mudança é transversal.

**Resumo**: o que a mudança **faz**, no imperativo:
`feat(producao): registra baixa de bobina na view multi-op`,
`fix(sapiens): trata erroExecucao vazio como falha, não como sucesso`.
Nada de "ajustes", "correções diversas", "wip".

**Corpo**: obrigatório para `feat`, `fix`, `refactor` e qualquer mudança
com decisão. Explica o **porquê**; o "o quê" está no diff.

**Rodapé**: `Co-Authored-By` quando a IA escreveu o código.

### Exemplo

```
fix(sapiens): trata resposta vazia do webservice como falha

O worker de logs_apontamentos marcava o apontamento como integrado sempre
que o Sapiens respondia 200, mesmo com o corpo vazio. Fábrica em operação
não tem zero apontamento pendente às 14h — resposta vazia é o sistema fora
do ar ou credencial sem permissão, nunca "nada para enviar".

Doc: sem doc a atualizar — comportamento interno do worker, não documentado
no momento em docs/sigma/07-integracoes-externas.md.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
```

## O que é um commit

- **Uma mudança lógica por commit.** Refatoração que a feature exigiu é
  commit separado (`refactor` primeiro).
- **Código e teste juntos** quando o teste existir para a mudança.
- **Commit que passa a esteira local.** `git bisect` depende disso.
- **Sem arquivo gerado ou de máquina**: `.env`, `staticfiles/`,
  `__pycache__`, `.venv`, `node_modules`, `artifacts/SIGMA.apk`. Já devem
  estar no `.gitignore`; `git status` antes de `git add` confere.
- **Sem segredo, nunca.**

## O procedimento

1. `git status` e `git diff` — ler o que vai entrar. Arquivo inesperado é
   pergunta, não `git add -A`.
2. Esteira local: `manage.py check`, `manage.py test`, `ruff check .`,
   `ruff format --check .`. Vermelho não commita.
3. Conferir `backend-sigma/references/checklist.md` para o que foi
   tocado.
4. `git add` **por arquivo** (ou por pasta coesa), nunca `-A` sem ter lido
   o status.
5. `git diff --cached --check` e `git diff --cached` — revise exatamente o
   que será gravado, inclusive teste e documento exigidos.
6. Mensagem no formato acima (`git commit -F` a partir de um arquivo, ou
   `-m`/`-m`).
7. `git log -1 --stat` para conferir.
8. **Push só quando a demanda pedir explicitamente.** Publicação em
   produção é manual, por SSH, do desenvolvedor sênior — nenhum agente
   publica.

O hook de guarda do projeto (`.claude/hooks/guarda_de_comandos.py`)
bloqueia `push --force`, `manage.py flush`, `migrate ... zero` e outros
comandos irreversíveis. Não tente contornar; informe a pessoa.

## Fluxo de branch

Commits pequenos em `main` para o dia a dia. Para trabalho longo que
quebra a suíte no meio, branch curta e merge quando verde — sem merge de
branch vermelha.
