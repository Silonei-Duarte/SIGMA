# SIGMA — guia para assistentes de IA

Portal operacional da IPEL. Django 6 (Python ≥3.14), Channels + Daphne
(ASGI, WebSocket), templates server-side com Tailwind. Integra com o ERP
Senior/Sapiens (SOAP), Oracle ERP e Oracle Alchemy (consulta direta), WMS XC
(API HTTP e DBLINK Oracle), Active Directory (LDAP), Firebase (push) e
SMTP (Microsoft 365). PostgreSQL + TimescaleDB é o banco operacional local.

A documentação funcional completa está em [`docs/sigma/README.md`](docs/sigma/README.md)
(índice dos documentos 01 a 13) e o padrão de interface em
[`docs/sigma/Style-Guide-IPEL.md`](docs/sigma/Style-Guide-IPEL.md).
**Antes de escrever código, leia o documento numerado que descreve a área
que você vai tocar** (índice em `docs/sigma/README.md`).

## Assets e cena de login

- Cedro e Flora são personagens próprios do SIGMA. A fonte normativa é
  `docs/sigma/13-marca-e-identidade.md`.
- Direção de arte: `docs/marca/brief-seguir-prancha.md`.
- O fundo do login usa somente camadas CSS animadas e tokens semânticos. Não
  há PNG de fundo, mascote, modelo 3D, rig, GLB ou WebM no runtime; cada ciclo
  inicia e termina no mesmo estado. Por direção artística aprovada, o login
  mantém seus efeitos mesmo com `prefers-reduced-motion`.
- Não introduzir asset, nome de classe ou contrato de outro projeto sem
  uma nova direção artística aprovada.

## Estado real do código

- `accounts.models` e `producao.views` resolvem para os pacotes `accounts/models/__init__.py` e `producao/views/__init__.py`. Nunca recrie arquivo de raiz com nome de pacote existente — o `.py` de raiz sombreia o pacote e ressuscita o stub.
- Oracle ERP e Alchemy usam `SIGMA/integracoes/oracle.py`; código novo usa `cursor_oracle_erp()` ou `cursor_oracle_alchemy()`; não usar `oracledb.connect()` nem cursor direto no consumidor.
- SOAP do Sapiens usa `producao/services/sapiens.enviar_soap_sapiens()` para transporte, timeout e erro HTTP; `producao/utils/sapiens_soap.py` para protocolo. Todo envio novo usa `enviar_soap_sapiens()`.
- Catálogo (lista fechada) é `TextChoices` ou `IntegerChoices` (`Apontamento.status`, `PacoteTempoERP`, `TipoValor`, etc.).
- Rota privada usa `SIGMA.autorizacao.permissao_requerida()`: `Permission`/`has_perm()`, permite staff/superusuário, devolve 403 a autenticado sem permissão. Todas as rotas privadas usam o decorator.
- Suíte automatizada em `<app>/tests/` com cobertura de autorização, filas e integrações; novas entregas ampliam a base sem enfraquecer regressões.

## Como o trabalho é dividido

Os agentes em `.claude/agents/` carregam o padrão do projeto. Toda demanda
de código passa por eles. Quando o pedido disser "use os devidos agentes",
escolha pela tabela — e use mais de um quando a demanda tiver mais de uma
natureza:

| A demanda fala de… | Agente |
|---|---|
| tela, view, template, model, migration, form, comando `manage.py`, regra de negócio, CRUD | `backend` |
| Oracle (ERP/Alchemy/WMS), SOAP Sapiens, API do WMS, LDAP/AD, Firebase, e-mail, worker, fila, agendamento | `integracoes` |
| escrever ou consertar testes; rodar a esteira local | `testes` |
| "está decente?", revisar, code review, qualidade, padrão | `revisor` |
| "está seguro?", brecha, vulnerabilidade, permissão, entrada, segredo | `seguranca` |
| documentar, atualizar `docs/` ou `README.md` | `documentador` |

Implementações trabalham **em sequência**, nunca em paralelo sobre os mesmos
arquivos. Auditorias somente leitura podem ocorrer em paralelo. Cada agente
termina com um relatório para quem não é desenvolvedor; repasse-o inteiro,
inclusive pendências e pedidos ao sênior.

## O ciclo de uma demanda de back-end

1. `backend` ou `integracoes` implementa — com teste (skill `testes`) e
   nota de documentação; sem isso não é entrega.
2. `testes` roda a esteira local: `.venv/Scripts/python.exe manage.py
   check`, `manage.py test` (ou `uv run pytest`), `ruff check .`, `ruff
   format --check .`. Alteração de tela ou fluxo roda também o E2E aplicável
   com `--run-e2e`.
3. `revisor` revisa contra o padrão. Se a mudança tocou autenticação,
   autorização, entrada de usuário, integração ou segredo, `seguranca`
   revisa também — integração passa **sempre** pelos dois.
4. Correções voltam para quem implementou; nova revisão se houve achado
   alto ou crítico.
5. `documentador` atualiza o documento certo em `docs/` (índice em
   `docs/sigma/README.md`) — ou o `README.md` da raiz — **no mesmo commit** do
   código, se o implementador não o fez.
6. Commit pela skill `commits`. Push só quando a pessoa pedir. A
   publicação em produção é manual, por SSH, pelo desenvolvedor sênior
   (`systemctl restart sigma`) — nenhum agente faz deploy.

## O ciclo de uma auditoria de código legado

Diferente do ciclo acima: aqui não existe demanda nova, é código legado que
ainda não passou pelos agentes. A auditoria ampla de 2026-08 cobriu
`accounts`, `producao`, `setores/*` e `telemetria`; reabra este ciclo apenas
para módulo legado que venha a ser incorporado ao escopo.

1. `revisor` e `seguranca` auditam o app (ou uma fatia dele — apps
   grandes, audite por submódulo, não tudo de uma vez) **em paralelo**,
   sem diff — cada um recebe explicitamente "não é diff, é o app/pasta
   inteira". Nenhum dos dois corrige nada.
2. Achado que exige decisão de política ou arquitetura (quem pode editar
   o quê, onde mora um bootstrap, se um `csrf_exempt` tem motivo real)
   **para no sênior** — os agentes não decidem isso sozinhos, só
   perguntam com as opções.
3. Com a decisão tomada, `backend` ou `integracoes` corrige — só o que foi
   decidido, nada a mais — com teste novo cobrindo o achado.
4. `revisor` e `seguranca` conferem de novo, agora só o diff dessa
   correção (voltam ao modo normal). Só fecha quando os dois liberarem.
5. Commit pela skill `commits`. `documentador` só entra se algum documento
   tiver ficado desatualizado — auditoria corrigindo dívida não costuma
   mudar o que os documentos já descrevem.

## Regras que não se negociam

- Identificadores em inglês; comentários, docstrings, mensagens, rótulos de
  tela e strings de interface em português. Comentário explica **por quê**.
- `os.getenv()` só em `SIGMA/settings.py`. Credencial só em `.env`
  (dev) ou `/etc/sigma/sigma.env` (produção); nunca em código, log,
  exceção, teste ou commit — cite o **nome** da variável.
- Toda entrada de formulário passa por `Form`/`ModelForm` com validação;
  não usar dado de `request.POST`/`request.GET` sem passar por um form ou
  por validação explícita.
- Catálogo novo é `TextChoices`/`IntegerChoices`, nunca inteiro cru com
  comentário nem nova tabela de domínio que o código já poderia expressar.
- Consulta Oracle nova usa `SIGMA.integracoes.oracle`, pelos helpers
  `cursor_oracle_erp()` ou `cursor_oracle_alchemy()`; nunca abra conexão
  própria com `oracledb.connect()` nem cursor direto no consumidor.
- Envio ao Sapiens usa `producao.services.sapiens.enviar_soap_sapiens()` para
  transporte, timeout e erro HTTP; `producao/utils/sapiens_soap.py` continua
  responsável por protocolo, escape e máscara. O consumidor interpreta a
  resposta de negócio sem repetir `requests.post`.
- Fila de integração (o padrão de `Apontamento`, `PacoteTempoERP` etc.):
  status nunca é apagado por falha; toda pendência fica visível e
  reprocessável; worker novo entra no scheduler de
  `producao/services/envia_pendencias.py` ou justifica por que não.
- Pacote novo, `uv add` de dependência de produção, alteração em
  `pyproject.toml` fora do grupo `dev`, `push --force`: decisão do
  desenvolvedor sênior. O hook em `.claude/hooks/` bloqueia os
  irreversíveis; não o contorne.
- O documento muda no mesmo commit da mudança que o tornou falso.
- O hook de commit bloqueia alteração em `views/` sem teste novo ou alterado no
  mesmo app em `<app>/tests/`. Ele comprova a presença da regressão; a execução
  da esteira continua obrigatória e deve constar no relatório.

## Skills

| Skill | Conteúdo |
|---|---|
| `backend-sigma` | mapa de camadas do Django no sigma, idioma do código, o que é proibido, fluxo de uma feature |
| `integracoes` | Oracle, SOAP Sapiens, WMS (API e DBLINK), LDAP/AD — o desenho de fila local que já existe e como não piorar a dívida de transporte |
| `testes` | como ampliar testes Django existentes, mockar integrações e rodar a esteira local |
| `seguranca` | modelo de ameaça do sigma, regras por camada, revisão |
| `auditoria` | diferença entre trilha de auditoria e log operacional; o que registrar sem vazar dados |
| `commits` | padrão de mensagem e procedimento de commit |
| `interface-sigma` | aponta para `docs/sigma/Style-Guide-IPEL.md` e `docs/sigma/02-arquitetura-tecnica.md` §3.2 — tokens semânticos, tema claro/escuro, build do Tailwind |

## E2E de telas

- Alteração de tela ou fluxo cria/atualiza teste `e2e` com Chromium no mesmo
  app. Mudança visual crítica (token, componente compartilhado, tema,
  tipografia, card, tabela, layout ou responsividade) inclui screenshot
  determinístico desktop e mobile; o restante retém trace e screenshot só na
  falha.
- Playwright e `pytest-playwright` pertencem ao grupo `dev`. Instale Chromium
  por máquina com `uv run playwright install chromium`; a marca `e2e` só roda
  quando o comando tiver `--run-e2e`, conforme a skill `testes`.

## Ambiente

- Gerenciador de pacotes: `uv` (`uv sync`, `uv run <comando>`,
  `uv add <pacote>` só com aprovação do sênior).
- Servidor de desenvolvimento: `.venv/Scripts/python.exe manage.py
  runserver` (ou `uv run python manage.py runserver`). WebSocket e HTTP no
  mesmo processo via Daphne/Channels em produção; em dev o `runserver`
  padrão do Django serve para telas sem tempo real.
- Depois de alterar token ou classe Tailwind: `cd theme/static_src && npm
  run build`.
- A suíte (`ruff`, `pytest`) foi adicionada junto com esta arquitetura de
  agentes — não existia antes. `uv sync` instala os dois no grupo `dev`.
- **`manage.py test` precisa rodar com `DB_DEFAULT_PORT=5432
  POSTGRES_USA_PGBOUNCER=0`** — pela porta padrão (PgBouncer, `6432`) o
  `search_path` correto não é aplicado e migrations de apps diferentes
  colidem de schema. Não é workaround, é a forma certa; motivo completo na
  skill `testes`.
- Não há CI configurado ainda (`.github/workflows` não existe neste
  repositório). A esteira local é a única verificação até que exista uma.
