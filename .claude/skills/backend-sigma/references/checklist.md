# Critério de aceite — back-end

Lista que o agente `backend` roda antes de dizer que terminou, e que o
agente `revisor` aplica item a item. O que não se aplica à demanda, diga
por quê em vez de pular em silêncio.

## Lugar e forma

- [ ] O código novo está no pacote real (`<app>/models/`, `<app>/views/`,
      `<app>/services/`), e nenhum arquivo de raiz recria pacote existente
      (os stubs `accounts/models.py` e `producao/views.py` foram removidos
      em 2026-08-27; recriá-los os ressuscitaria).
- [ ] Identificador em inglês; comentário, docstring, mensagem e rótulo de
      tela em português.
- [ ] Comentário explica o porquê, não o que a linha faz.
- [ ] Catálogo novo é `TextChoices`/`IntegerChoices`, não inteiro cru com
      comentário.
- [ ] Sem resíduo de depuração: `print()`, `breakpoint()`, `pdb.set_trace()`,
      código comentado morto ou `# TODO` sem responsável nomeado.

## Entrada e dado

- [ ] Toda entrada de usuário passa por `Form`/`ModelForm`; nada de
      `request.POST`/`GET` cru descendo para o service ou para o banco.
- [ ] Query contra Oracle usa `cursor_oracle_erp()` ou
      `cursor_oracle_alchemy()`; nunca `oracledb.connect()` nem cursor direto
      em código novo.
- [ ] Nenhum SQL montado por concatenação/f-string com dado de entrada.

## Acesso

- [ ] View privada nova usa `@permissao_requerida()`; a permissão exigida e o
      bypass staff/superusuário têm teste.
- [ ] O escopo por empresa, filial ou ownership continua limitado dentro da
      view e também tem teste contra identificador forjado.

## Integração e fila (se aplicável)

- [ ] Fila nova segue o padrão de `Apontamento`/`PacoteTempoERP`: status
      na própria linha, nunca apagada por falha.
- [ ] Worker novo está registrado no `EnviaPendenciasScheduler`
      (`producao/services/envia_pendencias.py`) ou o relatório explica por
      que não.
- [ ] Chamada a sistema externo tem timeout declarado.
- [ ] Segredo não aparece em código, log, exceção, teste ou commit — só o
      **nome** da variável de ambiente.
- [ ] Mensagem de erro visível ao usuário (tela ou JSON) não revela se uma
      conta/login existe, caminho de arquivo do servidor, versão de pacote
      ou stack trace — mensagem genérica, detalhe só no log.
- [ ] Exceção interna (`raise`, log de exceção, `except ... as e`) nomeia o
      tipo/natureza do erro, mas nunca carrega o dado sensível ou o
      parâmetro que originou a falha — CPF, senha, token, segredo não
      entram na mensagem da exceção nem no log, mesmo quando a mensagem não
      chega à tela. A regra de mensagem visível acima cobre a tela; esta
      cobre o que fica registrado internamente.
- [ ] Toda ação com efeito em acesso, dado ou integração tem trilha de
      auditoria — critério e formato na skill `auditoria`; este item só
      confere presença, não repete o conteúdo da skill.

## Teste e documentação

- [ ] Existe teste cobrindo o caminho feliz e pelo menos uma guarda (sem
      login, sem papel, formulário inválido).
- [ ] O documento certo em `docs/` foi atualizado, ou o relatório diz por
      que não precisou.
- [ ] `.env.example` atualizado se nasceu variável de ambiente nova.

## Esteira

- [ ] `manage.py check` passou.
- [ ] `manage.py test <app>` passou.
- [ ] `ruff check .` passou (ou só nos arquivos tocados, se o resto do
      projeto já tinha apontamento anterior à demanda).
- [ ] `ruff format --check .` passou.
- [ ] `uv run mypy` (sem passar caminho) passou, sem apontamento — gate
      bloqueante, sem baseline; ver skill `testes`.
