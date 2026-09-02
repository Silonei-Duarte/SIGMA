---
name: testes
description: Como escrever e rodar testes no SIGMA com Django TestCase, pytest-django e manage.py test. Define onde o teste mora, como se nomeia, o que toda entrega cobre, como mockar cada sistema externo (Oracle, Sapiens, WMS, LDAP, Telemetria HTTP), e a esteira local. Use ao escrever, consertar ou revisar teste, e ao rodar a verificação antes de um commit. Dispara em "teste", "testes", "testar", "cobrir", "cobertura", "pytest", "rodar os testes", "rodar a esteira", "ruff", "node --test", "javascript".
paths: "**/tests/** **/tests.py **/test_*.py pyproject.toml"
---

# Testes no SIGMA

A auditoria de 2026-08 criou testes em `accounts`, `producao`,
`setores/qualidade`, `setores/manutencao`, `setores/pcp` e `telemetria`.
Leia primeiro os testes vivos do app tocado; eles são o padrão de fixtures,
escopo por filial e mocks. `ruff` e `pytest`/`pytest-django` pertencem ao
grupo `dev` do `pyproject.toml`.

## Onde o teste mora

`<app>/tests/__init__.py` + `<app>/tests/test_<assunto>.py` para app com
mais de um teste; `<app>/tests.py` single-file só se for realmente pouca
coisa. Nome de método afirma o comportamento, em português:

```python
class ApontamentoViewTests(TestCase):
    def test_sem_login_redireciona_para_pagina_de_entrada(self): ...

    def test_usuario_sem_permissao_recebe_403(self): ...

    def test_formulario_valido_cria_apontamento_pendente(self): ...
```

## Framework e configuração

`pyproject.toml` já declara:

```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "SIGMA.settings"
python_files = ["tests.py", "test_*.py", "*_tests.py"]
addopts = "--reuse-db"
```

## `manage.py test` precisa rodar fora do PgBouncer

Em desenvolvimento, a conexão padrão do Django (`DB_DEFAULT_PORT`, normalmente
`6432`) passa pelo PgBouncer. `SIGMA/settings.py` só aplica o `search_path`
correto (`-c search_path=...` nas `OPTIONS` da conexão) **quando não está
usando PgBouncer** — é decisão deliberada e comentada no código: PgBouncer em
`pool_mode = transaction` não garante repassar `options` de conexão de forma
confiável entre transações compartilhadas do pool. Rodar teste pela porta
padrão faz migrations de apps diferentes colidirem de schema (erro de índice
"já existe" numa tabela que deveria estar noutro schema).

**Sempre rode a suíte assim** (aponta direto pro PostgreSQL, sem o pool):

```bash
DB_DEFAULT_PORT=5432 POSTGRES_USA_PGBOUNCER=0 .venv/Scripts/python.exe manage.py test [app]
```

Isso não é workaround — é a forma correta dado o desenho atual da conexão.
Não "conserte" isso mudando `settings.py` para aplicar `search_path` também
com PgBouncer ligado sem o sênior decidir: o gate existe por um motivo
documentado, e mudar pode reintroduzir o problema que ele evita (em vez do
óbvio, dessa vez silencioso).

Se um teste travar achando o banco de teste "já existe" ou "sendo acessado
por outros usuários": o PgBouncer mantém a conexão física do servidor viva
no pool mesmo depois do cliente Django desconectar (comportamento normal do
`pool_mode = transaction`). Rode como sênior, fora do agente:

```sql
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'test_sigma' AND pid <> pg_backend_pid();
```

antes de rodar a suíte de novo.

Rode com `uv run pytest` ou com `manage.py test` (ambos funcionam;
`pytest-django` lê a mesma configuração). `--reuse-db` evita recriar o
banco de teste do PostgreSQL a cada rodada — se o schema mudou
(`migrations` nova), rode uma vez com `--create-db`.

`django.test.TestCase` é a base padrão (transação por teste, rollback
automático); use `TransactionTestCase` só quando o comportamento sob
teste depender de commit real (ex.: `select_for_update` cross-thread).

## E2E com Playwright

Teste de navegador complementa, não substitui, `TestCase`: toda alteração de
tela ou fluxo ganha/atualiza um teste marcado com `@pytest.mark.e2e` no mesmo
pacote `<app>/tests/`. Mudança só de backend não precisa de navegador.

Os testes usam Chromium, `pytest-playwright`, o servidor local `servidor_e2e` e
uma conta criada pela fixture `usuario_e2e` de `conftest.py`; o backend LDAP é
trocado temporariamente por `ModelBackend`. Portanto nunca chamam LDAP, Oracle,
WMS ou outro serviço real. A fixture `pagina_autenticada` entra pelo formulário
real, não injeta cookie de sessão.

Use locators semânticos (`get_by_role`, `get_by_label`) antes de criar
`data-testid`. Alteração visual crítica (token, componente compartilhado,
tema, tipografia, card, tabela, layout ou responsividade) ganha screenshot
determinístico desktop e mobile versionado; telas com dados externos só entram
nessa comparação depois de isoladas por fixtures locais.

Instale o navegador uma vez por máquina de desenvolvimento:

```powershell
uv run playwright install chromium
```

O teste normal pula a marca `e2e`. Para executá-la e reter evidências de
falha, rode com PostgreSQL direto:

```powershell
$env:DB_DEFAULT_PORT='5432'; $env:POSTGRES_USA_PGBOUNCER='0'; uv run pytest --run-e2e -m e2e --browser chromium --tracing retain-on-failure --screenshot only-on-failure
```

`test-results/` guarda trace e screenshot só quando houver falha e é ignorado
no Git. Para depurar visualmente, acrescente `--headed` ao comando.

Para uma alteração visual crítica, estabilize os dados e use
`page.set_viewport_size()` com `expect(page).to_have_screenshot()` para desktop
e mobile. Gere ou atualize o baseline apenas após revisão visual, com o mesmo
comando E2E acrescido de `--update-snapshots`.

## Utilitário JavaScript puro: `node --test`

Utilitário JavaScript **puro e compartilhado** (ex.: scripts de tokens
do tema em `theme/static_src/scripts/`) é coberto com o runner nativo do
Node — **sem pacote novo** (nada de jest/vitest, nada de alterar o
`package.json` de produção), **sem navegador** e **sem CI** (CI/CD é
decisão pendente do sênior e não faz parte deste padrão).

O Node já existe na máquina pelo build do Tailwind. O teste mora ao lado
do utilitário, com sufixo `.test.mjs`:

```js
// theme/static_src/scripts/exemplo.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { tokenToCamelCase } from "./exemplo.mjs";

test("converte token kebab-case para camelCase", () => {
  assert.equal(tokenToCamelCase("cor-fundo"), "corFundo");
});
```

Roda direto, sem configuração, com glob a partir da raiz do repositório:

```powershell
node --test "theme/static_src/scripts/*.test.mjs"
```

Alternativa equivalente: rodar `node --test` de dentro da pasta do
script — sem argumento, o runner varre o diretório atual.

Não passe a **pasta** como argumento (`node --test theme/static_src/scripts/`):
no Node 24/Windows o runner não a expande e tenta executá-la como módulo,
falhando com `MODULE_NOT_FOUND`. O glob contorna o comportamento.

Não é escopo desta receita: script que depende do navegador, do Tailwind
ou do DOM — esse é território do E2E com Playwright acima.

## O que toda entrega cobre

- Caminho feliz.
- Cada guarda de acesso: sem sessão → redireciona/nega; sem papel
  (`is_staff`/grupo) → nega; com o certo → funciona.
- Cada guarda de fila/integração: resposta de erro do sistema externo não
  marca como integrado; resposta vazia é tratada como falha, não como
  "sem dados".
- Em alteração de acesso, escopo ou estado: prove também o que **não** muda
  (objeto de outra filial, permissão de terceiro, fila já existente).
- Quando houver trilha de auditoria implementada para a ação, prove o evento
  sem serializar segredo ou payload externo no teste.

## Mockar sistema externo — nunca rede real

| Sistema | Como mockar |
|---|---|
| Oracle (`connections["oracle_erp"]`/`oracle_alchemy`) | `unittest.mock.patch("django.db.connections")`, ou patch direto na função que abre o cursor; retorno como lista de tuplas igual ao `cursor.fetchall()` real |
| SOAP Sapiens | `unittest.mock.patch("requests.post")` com XML de resposta copiado de uma chamada real quando existir; senão, o mesmo XML de exemplo do helper `sapiens_soap.py`, e avisar no relatório que é presumido |
| WMS (API) | `unittest.mock.patch("requests.post")`/`get`, corpo JSON de exemplo |
| LDAP | Django tem suporte a backend de teste; para não depender do AD real, mocke `django_auth_ldap` ou crie o `User` direto via `User.objects.create_user(...)` e teste só a parte que roda depois do login |
| Telemetria HTTP | `unittest.mock.patch("telemetria.services.coleta...")`, nunca chamar uma fonte real |
| Firebase/e-mail | `unittest.mock.patch` no ponto de chamada do SDK/backend; Django já tem `django.core.mail.outbox` para teste de e-mail se o backend for o padrão |

Sem rede real, sem `time.sleep()`, sem depender de servidor externo
estar no ar. Configuração específica de teste vai em `override_settings`
ou `setUp`, nunca no `.env` da máquina.

## Testar parsing de variável de ambiente com valor padrão/ausente

`override_settings`/`setUp` sobrescreve o valor já carregado em
`settings.py` — não reexecuta o parsing feito na leitura de `os.getenv()`
em `SIGMA/settings.py` (ex.: `int(os.getenv(nome, str(padrao)))`,
`... or None`). Para provar que o fallback de uma variável ausente ou
vazia funciona de verdade, exercite o parsing outra vez com
`monkeypatch.delenv`/`monkeypatch.setenv` seguido de
`importlib.reload(SIGMA.settings)`:

```python
def test_ldap_require_group_usa_padrao_quando_variavel_ausente(monkeypatch):
    monkeypatch.delenv("LDAP_REQUIRE_GROUP", raising=False)
    import importlib
    from SIGMA import settings

    importlib.reload(settings)
    assert settings.LDAP_REQUIRE_GROUP == valor_padrao_esperado
```

Use só quando o parsing tiver lógica não trivial a proteger (valor padrão,
conversão de tipo, `or None`); configuração simples continua em
`override_settings`. Recarregar `settings` vaza para o processo do teste —
isole em teste próprio ou recarregue de novo ao final para não afetar
outros testes do módulo.

## A esteira local

```bash
.venv/Scripts/python.exe manage.py check
$env:DB_DEFAULT_PORT='5432'; $env:POSTGRES_USA_PGBOUNCER='0'; .venv/Scripts/python.exe manage.py test
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Quando a entrega tocou tela ou fluxo, rode também o comando E2E acima.

**Rode `uv run mypy` sem passar caminho** — o escopo (`SIGMA`, `accounts`,
`producao`, `setores`, `telemetria`, `theme`) vem do `files` em
`[tool.mypy]` no `pyproject.toml`. Passar `.` ou qualquer caminho na linha
de comando ignora esse `files` e volta a escanear `Outros/` (scripts soltos,
não é app Django) e pastas de referência externa (checkouts que
o `CLAUDE.md` da raiz proíbe tocar).

`mypy` é gate bloqueante desde 2026-08-25, sem baseline: qualquer
apontamento nos pacotes do projeto reprova, inclusive em código legado fora
da demanda — decisão do sênior, ciente do volume que a base legada sem
anotação de tipo pode gerar. Se um apontamento for de código fora da
demanda, corrija-o também (anotação de tipo, não lógica) em vez de
silenciar com `# type: ignore` sem justificativa registrada no relatório.

Suíte inteira quando a demanda for "rodar a esteira". Se `ruff check`
reprovar, rode `uv run ruff check --fix` só nos arquivos tocados pela
demanda.

## Configuração que o teste precisa, o teste declara

Princípio: **teste que precisa de configuração declara a configuração.**
Nenhum teste depende do que a máquina local tem no `.env` — toda
configuração necessária (chave de feature, limite, URL, allowlist) vem de
`override_settings`, fixture ou `setUp` explícito no próprio teste, nunca
do ambiente onde a suíte roda por acaso. Isso evita o cenário clássico de
teste verde numa máquina e vermelho em outra só por diferença de `.env` —
o teste tem que passar (ou falhar) pelo mesmo motivo em qualquer máquina.

## O que não se faz

Anti-padrões que reprovam em revisão, mesmo que a suíte passe:

- **Assert que sempre passa**, como `assertTrue(True)` ou comparar um valor
  com ele mesmo — não prova nada sobre o comportamento do código.
- **Teste sem nenhum assert** — só executa o caminho e não verifica
  resultado; dá falso sinal de cobertura.
- **Teste que depende da ordem de execução** de outros testes (estado
  deixado por um teste anterior, contador global, fixture não isolada) —
  cada teste tem que passar sozinho e em qualquer ordem.
- **Alterar código de produção só para o teste passar**, sem entender a
  causa raiz da falha — ver "Ao consertar suíte que reprova" abaixo.

## Ao consertar suíte que reprova

Entenda antes de mexer: leia a mensagem, o teste, o código. Se o teste
está certo e o código errado, o conserto é demanda para `backend` ou
`integracoes` (a menos que seja trivial e você diga exatamente o que
mudou). Nunca enfraqueça um `assert` só para o teste passar.
