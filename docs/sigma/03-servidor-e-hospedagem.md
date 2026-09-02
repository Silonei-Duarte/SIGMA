---
titulo: Servidor e hospedagem
ordem: 3
---

### 3.4 Infraestrutura

Em produção, a aplicação roda em um servidor Ubuntu. O systemd mantém o serviço ativo e reinicia em caso de queda. O Daphne atende a aplicação na porta interna 8000. O Nginx atua como camada web/reverse proxy.

O banco PostgreSQL roda no mesmo servidor, o que reduz latência para as filas e cadastros locais. As conexões com Oracle, WMS, telemetria HTTP, LDAP e Sapiens dependem da rede interna.

Resumo do ambiente:

| Camada | Tecnologia/valor |
|---|---|
| Sistema operacional | Ubuntu 24.04.4 LTS |
| Host | `nex01` |
| Usuário do processo | `nexus` |
| Diretório da aplicação | `/opt/SIGMA` |
| Processo web | Daphne ASGI |
| Porta interna | `8000` |
| Banco local | PostgreSQL 18.4 com TimescaleDB 2.29.1 |
| Arquivo de ambiente | `/etc/sigma/sigma.env` |

### Hospedagem e execução em produção

*(No documento mestre original este título repetia "3.4" — os dois assuntos ficaram juntos aqui; ver histórico do git se precisar do texto exato de antes da divisão.)*

#### 3.4.1 Servidor de produção

Esta seção descreve onde a aplicação roda de fato. O objetivo não é documentar código, mas permitir que alguem de infraestrutura ou suporte saiba onde procurar quando a aplicação estiver fora do ar, lenta ou com erro de ambiente.

O serviço principal se chama `sigma.service`. Ele roda com o usuário Linux `nexus` e usa o diretório `/opt/SIGMA` como raiz da aplicação. Quando o servidor reinicia, o systemd sobe esse serviço automaticamente. Se o processo cair, a diretiva `Restart=always` tenta reiniciar.

Dados do ambiente:

| Item | Valor |
|---|---|
| Usuário SSH | `nexus` |
| Host | `nex01` |
| Sistema operacional | Ubuntu 24.04.4 LTS |
| Diretório inicial | `/home/nexus` |
| Diretório da aplicação | `/opt/SIGMA` |
| Serviço systemd | `sigma.service` |
| Processo web | Daphne |
| Porta interna | `8000` |
| Banco local | PostgreSQL 18.4 com TimescaleDB 2.29.1 |

#### 3.4.2 Unidade systemd

O systemd é o gerenciador responsável por manter a aplicação rodando. Ele define quem executa o processo, de onde ele executa e qual comando inicia o servidor web Python. A aplicação não e iniciada manualmente com `python manage.py runserver` em produção; ela é iniciada pelo Daphne por meio do systemd.

Serviço:

```ini
[Unit]
Description=SIGMA Django
After=network.target

[Service]
User=nexus
WorkingDirectory=/opt/SIGMA
Environment="PYTHONUNBUFFERED=1"
ExecStart=/opt/SIGMA/.venv/bin/python -u /opt/SIGMA/.venv/bin/daphne -b 127.0.0.1 -p 8000 SIGMA.asgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

Drop-in do systemd:

O drop-in é um complemento da configuração principal do serviço. Ele permite adicionar ou sobrescrever partes do `sigma.service` sem editar diretamente o arquivo base da unit. No SIGMA, esse complemento é usado para informar ao systemd que o serviço deve carregar as variáveis de ambiente do arquivo `/etc/sigma/sigma.env` antes de iniciar a aplicação. É por esse caminho que o processo recebe configurações como bancos, integrações, chaves de ambiente, e-mail e demais parâmetros externos ao código.

```ini
[Service]
EnvironmentFile=/etc/sigma/sigma.env
```

#### 3.4.3 Processo em produção

O processo web usa a entrada ASGI (`SIGMA.asgi:application`). ASGI é a interface entre o servidor web Python e a aplicação Django para aplicações assíncronas. Na prática, é o ponto por onde o Daphne chama o SIGMA para atender requisições. Isso é importante porque ASGI permite tanto requisições HTTP comuns quanto WebSocket, necessário para recursos como balança em tempo real e atualização de OP.

Comando do processo web:

```text
/opt/SIGMA/.venv/bin/python -u /opt/SIGMA/.venv/bin/daphne -b 127.0.0.1 -p 8000 SIGMA.asgi:application
```

Serviços ativos relacionados:

- `sigma.service`: ativo e rodando.
- `nginx.service`: ativo e rodando.
- `postgresql@18-main.service`: ativo e rodando.

Comandos operacionais de atualização:

```bash
cd /opt/SIGMA
.venv/bin/python manage.py migrate
.venv/bin/python manage.py tailwind build
.venv/bin/python manage.py collectstatic --noinput
sudo systemctl reset-failed sigma
sudo systemctl restart sigma
systemctl status sigma --no-pager -l
```

#### 3.4.3.1 Atualização de PostgreSQL e TimescaleDB

Os pacotes `postgresql-18` e `postgresql-18-timescaledb` permanecem em *hold* no APT. Portanto, um `apt upgrade` comum pode atualizar os demais pacotes do servidor, mas não altera o PostgreSQL nem o TimescaleDB. Não remover o *hold* nem atualizar esses pacotes fora de janela de manutenção aprovada.

O TimescaleDB possui duas versões que precisam permanecer alinhadas: a biblioteca instalada no servidor e a extensão SQL registrada em cada banco. Depois de instalar uma versão nova do pacote, executar imediatamente a atualização da extensão no banco `sigma`. Se isso não ocorrer, a aplicação não consegue abrir conexões com o PostgreSQL.

Procedimento para uma atualização planejada do TimescaleDB:

```bash
# 1. Conferir os holds e criar dump lógico antes da alteração.
apt-mark showhold
sudo -u postgres pg_dump -Fc -d sigma \
  -f /var/backups/sigma/sigma_pre_timescaledb_$(date -u +%Y%m%dT%H%M%SZ).dump

# 2. Liberar somente os pacotes envolvidos e instalar a versão aprovada.
sudo apt-mark unhold postgresql-18 postgresql-18-timescaledb
sudo apt-get update
sudo apt-get install postgresql-18-timescaledb=<VERSAO_APROVADA>

# 3. Este DEVE ser o primeiro comando da sessão psql no banco sigma.
sudo -u postgres psql -X -d sigma -v ON_ERROR_STOP=1 \
  -c "ALTER EXTENSION timescaledb UPDATE;"

# 4. Reiniciar os consumidores de conexões e validar as versões.
sudo systemctl restart pgbouncer sigma
sudo -u postgres psql -X -d sigma -P pager=off \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';"
sudo -u postgres psql -X -d sigma -P pager=off \
  -c "SELECT value FROM _timescaledb_catalog.metadata WHERE key = 'timescaledb_version';"
cd /opt/SIGMA && .venv/bin/python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print('DJANGO_DB_OK')"

# 5. Reter novamente os pacotes após a validação.
sudo apt-mark hold postgresql-18 postgresql-18-timescaledb
```

Usar `psql -X` evita comandos automáticos do perfil do cliente. O `ALTER EXTENSION` deve ser o primeiro comando da sessão porque o TimescaleDB não aceita carregar uma biblioteca nova com o catálogo SQL ainda na versão anterior. Não executar `apt update && apt upgrade -y` em produção como forma de atualizar PostgreSQL ou TimescaleDB.

O caminho da aplicação em produção é sensível a maiúsculas e minúsculas. O diretório correto é `/opt/SIGMA`; caminhos como `/opt/sigma` ou `/opt/Sigma` não existem nesse ambiente.

Quando `uv` estiver disponível no `PATH` do usuário `nexus`, os comandos Python também podem ser executados com `uv run --frozen python` — **a flag `--frozen` é obrigatória em produção**. `pyproject.toml`/`uv.lock` são um lock único cobrindo Linux e Windows (`python-ldap` tem fonte diferente por `sys_platform` — PyPI no Linux, wheel local em `Uteis_projeto/` só no Windows). Sem `--frozen`, `uv run` revalida o lock inteiro contra `pyproject.toml` antes de instalar, o que exige acesso aos metadados de **todas** as entradas do lock, das duas plataformas — inclusive o wheel Windows, que não existe (nem deveria existir) no servidor Linux, e o comando falha com `Failed to generate package metadata` / `No such file or directory`. `--frozen` confia no `uv.lock` como está e só instala o que já foi travado para a plataforma atual, sem revalidar nada — é o comportamento correto para um ambiente de produção, que nunca deveria reresolver dependência na hora. Se o shell ainda não reconhecer `uv`, usar `.venv/bin/python` evita o problema por completo (não passa pelo resolvedor do `uv`).

#### 3.4.3.2 Log de erro da aplicação (traceback de 500)

`sigma.service` não declara `StandardOutput`/`StandardError` no unit
(§3.4.2) — por padrão do systemd, isso já significa `journal`: todo
`stdout`/`stderr` do processo Daphne cai em `journalctl -u sigma.service`
sem precisar de arquivo intermediário nem mudança na unit. O que faltava
era o Django efetivamente escrever no `stderr` do processo quando uma
exceção não tratada vira um 500.

`SIGMA/settings.py::LOGGING` cobre isso: o logger `django.request` (o que
o Django usa para todo 500 de exceção não tratada em view, com ou sem
`DEBUG`) tem um handler `stderr_processo` — `StreamHandler` com `stream`
explícito para `ext://sys.stderr` (não o `sys.stderr` implícito resolvido
no import do módulo, para acompanhar corretamente o stream real do
processo supervisionado pelo systemd) e `formatter` com timestamp, nível e
PID. Teste que prova a emissão: `SIGMA/tests/test_logging.py`, usando a
rota sintética de `SIGMA/tests/urls_logging_teste.py`.

Consulta em produção:

```bash
journalctl -u sigma.service --since "-1h" | grep -A 30 ERROR
```

**Ainda não implementado (decisão de sênior):** alerta automático por
e-mail a cada 500 via `ADMINS`/`EMAIL_SUBJECT_PREFIX` do Django — hoje
`ADMINS` não está configurado, então esse mecanismo pronto do framework
continua sem uso. Não bloqueia o log em `journalctl`, que já funciona
independente disso.

#### 3.4.4 Variáveis de ambiente de produção

As variáveis de ambiente são a camada de configuração sensível do sistema. Elas indicam para onde o SIGMA deve conectar, quais bancos usar, qual URL de webservice chamar e quais credenciais utilizar. As credenciais, chaves e usuários não aparecem neste documento funcional, este documento registra apenas valores não sensíveis.

Arquivo usado:

```text
/etc/sigma/sigma.env
```

Valores não sensíveis:

| Variável | Valor |
|---|---|
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | `sigma.indaialpapel.com.br` |
| `DJANGO_HTTPS_ENABLED` | `True` |
| `DB_DEFAULT_NAME` | `sigma` |
| `DB_DEFAULT_HOST` | `127.0.0.1` (PgBouncer) |
| `DB_DEFAULT_PORT` | `6432` |
| `POSTGRES_USA_PGBOUNCER` | `1` |
| `POSTGRES_DIRECT_HOST` | `127.0.0.1` |
| `POSTGRES_DIRECT_PORT` | `5432` |
| `ORACLE_ERP_NAME` | `172.16.30.51/dbdev` |
| `ORACLE_ALCHEMY_NAME` | `172.16.30.10/dbprod` |
| `SAPIENS_URL_BASE` | `http://172.16.30.26:8080` |
| `WMS_XC_API_URL` | `http://10.61.31.10:1919/` |
| `LDAP_SERVER_URI` | `ldaps://DC01.indaialpapel.com.br:636` |
| `LDAP_USER_DOMAIN` | `indaialpapel.com.br` |
| `LDAP_CA_CERT_FILE` | `/opt/SIGMA/certs/ca_indaialpapel.pem` |
| `PORTAL_BASE_URL` | `https://sigma.indaialpapel.com.br` |
| `NPM_BIN_PATH` | `/usr/local/bin/npm` |

Antes de ativar a coleta HTTP de Telemetria, `/etc/sigma/sigma.env` precisa definir
`TELEMETRIA_HOSTS_PERMITIDOS` com os hosts ou pares `host:porta` dos equipamentos
autorizados. Sem essa allowlist a coleta falha fechada. Os limites
`TELEMETRIA_TIMEOUT_MAX_SEGUNDOS`, `TELEMETRIA_PAUSA_MAX_SEGUNDOS` e
`TELEMETRIA_RESPOSTA_MAX_BYTES` mantêm, respectivamente, o teto de tempo,
intervalo e tamanho de resposta do coletor; devem ser revisados junto da inclusão
de cada novo endpoint.

Além das variáveis de ambiente, existe a tela **Configurações da Aplicação**
(`/configuracoes/`, app `accounts`, model `ConfiguracaoAplicacao`) para
variáveis **não sensíveis** editáveis em runtime: o valor salvo passa a valer
na próxima leitura, sem reiniciar o servidor — o service de leitura
(`accounts/services/configuracoes.py`) serve de cache em memória do processo,
invalidado por signal quando o dado muda; os workers, que são threads do
mesmo processo, enxergam o valor novo no ciclo seguinte sem reconsultar a
tabela a cada leitura. A chave é parte do **código**, não da tela: a
listagem mostra apenas as chaves declaradas em `CHAVES_CONHECIDAS`, agrupadas
pelo tópico declarado (ex.: "E-mail — Relatórios"), e a pessoa só edita
**descrição e valor** — a edição é por nome de chave
(`/configuracoes/editar/<chave>/`), não por pk, porque chave conhecida sem
linha no banco não tem pk. Não existe criar chave pela tela: chave nova
de configuração = nova declaração em `CHAVES_CONHECIDAS` (código versionado,
com tópico, descrição, default e validador). A tela de edição oferece a ação
**Voltar ao padrão** (`POST /configuracoes/padrao/<chave>/`), que exclui a
linha salva — sempre por instância, `instance.delete()`, porque a
invalidação do cache depende do signal `post_delete` de cada linha (update/
delete em queryset não disparam) — e registra em log quem voltou qual chave,
sem o valor. A tabela é espelho do registro declarado: linha excluída por
qualquer via (tela, ORM/shell) → a listagem volta a mostrar o default do
código e a chave é só reconfigurada. Credencial (senha,
token, chave de API) continua exclusivamente nas variáveis de ambiente deste
documento: a tela rejeita chaves cujo nome carrega padrão de segredo e a
leitura pelo service (`obter()`) rejeita também — linha gravada por outra via
não encontra superfície que sirva a credencial; a política é não guardar
valor sensível nela. A gravação (`definir()`, service) normaliza a chave para
maiúsculas e valida o formato (`^[A-Z][A-Z0-9_]*$`) mesmo fora da tela; linha
plantada por outra via com chave fora do registro não é listada nem editável
pela tela — o guard de leitura é quem protege o consumidor.

### Convenção de registro quando uma hipótese de causa é refutada

Quando um problema documentado neste ou em outro documento operacional
(ex.: [08 — Operação, workers e monitoramento](08-operacao-e-workers.md))
tiver sua causa revisada — uma hipótese inicial corrigida por uma causa
real descoberta depois —, a hipótese antiga **não é apagada nem
reescrita**: ela permanece registrada, marcada como refutada, ao lado da
causa real. Isso importa sobretudo quando uma mitigação ligada à hipótese
antiga continua válida por outro motivo — apagar a hipótese apagaria
também a justificativa visível da mitigação. Esta é uma convenção para uso
daqui em diante; não retroage sobre nenhum incidente já documentado.

---

*Verificado contra o código em 2026-08-29.*
