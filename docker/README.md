# Docker do SIGMA (imagem única)

Referência rápida dos comandos. Documentação formal fica pendente em
`docs/sigma/` (ver `CLAUDE.md` — o agente `documentador` decide a numeração);
este arquivo cobre o essencial até lá.

## Desenho

Uma imagem só: aplicação Django (Daphne/Channels) + PostgreSQL 18 com
TimescaleDB + Nginx, tudo supervisionado por `supervisord`
(`docker/supervisord.conf`). Não há `docker-compose`/múltiplos containers —
decisão do sênior: simplicidade para qualquer pessoa do time rodar rápido, e
portabilidade para o cenário em que a infra só libera "um Docker numa VM",
sem gestão de banco separada.

Base: Ubuntu 24.04 LTS, mesma versão do servidor de produção real
(`docs/sigma/03-servidor-e-hospedagem.md`).

**TLS fica fora de escopo desta primeira versão.** O Nginx dentro do
container escuta HTTP simples na porta 80 (`docker/nginx.conf`). Quem expuser
este container numa VM real decide o certificado por fora (outro Nginx no
host, ou um proxy adicional).

## Build

```bash
docker build -t sigma .
```

O build compila as dependências Python (`uv sync --frozen --no-dev`,
incluindo `python-ldap` a partir do código-fonte), gera o CSS do Tailwind
(`theme/static_src && npm run build`) e roda `manage.py collectstatic`. Nada
disso depende de dado de runtime, por isso acontece só no build — não no
`entrypoint.sh`.

## Rodar (desenvolvimento local)

```bash
cp .env.docker.example .env.docker
# edite .env.docker com os valores reais/de teste

docker run -d \
    --name sigma \
    --restart unless-stopped \
    --env-file ./.env.docker \
    -v sigma-dados:/var/lib/postgresql \
    -p 8000:80 \
    sigma
```

Acesse `http://localhost:8000/`. Ver `deploy/rodar-docker.sh` para o mesmo
comando comentado passo a passo.

Segredo e configuração **nunca** ficam na imagem — só entram via
`--env-file`. Use `.env.docker.example` (ou `.env.example` da raiz, para as
integrações Oracle/Sapiens/WMS/LDAP/Microsoft Graph/Firebase/Telemetria) como
referência de quais chaves existem.

## Persistência do volume

`-v sigma-dados:/var/lib/postgresql` guarda todo o diretório de dados do
PostgreSQL. O pacote `postgresql-18` do Ubuntu já cria um cluster inicial
durante o `apt install` — isso acontece **no build da imagem**. Um volume
montado por fora fica vazio na primeira execução e sombreia esse cluster de
build (o volume cobre o caminho inteiro). Por isso `docker/entrypoint.sh`
verifica, a cada subida do container, se o cluster já existe no volume
(arquivo `PG_VERSION` em `/var/lib/postgresql/18/main`):

- **Não existe** (volume novo): cria o cluster do zero
  (`pg_createcluster`), cria o usuário/banco/extensão TimescaleDB a partir de
  `DB_DEFAULT_NAME`/`DB_DEFAULT_USER`/`DB_DEFAULT_PASSWORD` do `--env-file`.
- **Já existe** (volume reaproveitado): só sobe o cluster existente, sem
  recriar nada.

Em ambos os casos, `manage.py migrate` roda a cada subida (idempotente).

Parar e recriar o container com o mesmo volume não perde dado nem recria o
cluster — validado manualmente antes desta entrega (ver relatório da
demanda).

## Processos supervisionados

`docker/supervisord.conf` mantém três processos:

| Processo | O que faz |
|---|---|
| `postgresql` | Servidor PostgreSQL 18, iniciado direto pelo binário (não pelo wrapper `pg_ctlcluster`, que não roda em primeiro plano) |
| `daphne` | Aplicação Django via ASGI, na porta interna 8000 — o comando real passa antes por `docker/wait-for-postgres.sh`, que espera o Postgres aceitar conexão antes de iniciar o Daphne (evita a corrida em que os workers em background tentam a advisory lock antes do banco estar pronto) |
| `nginx` | Serve `/static/` e faz proxy reverso (incluindo WebSocket) para `127.0.0.1:8000` |

Os workers em background do SIGMA (`envia_pendencias` e afins) **não** têm
processo supervisionado próprio — já rodam como threads dentro do próprio
processo Daphne (`accounts/apps.py::iniciar_workers_em_background()`,
chamado por `SIGMA/asgi.py`).

## Limitações desta versão

- Sem TLS dentro do container (ver acima).
- O processo de preparação (`entrypoint.sh`) roda como `root` — precisa
  criar/ajustar o cluster do PostgreSQL, que é setup de sistema. O Daphne
  em si roda com usuário dedicado sem privilégio (`sigma`, criado no
  `Dockerfile`, aplicado em `docker/supervisord.conf`) — só o PostgreSQL
  roda com o usuário de sistema `postgres` (exigido pelo próprio pacote), e
  o `entrypoint.sh`/`supervisord` seguem root pelo motivo acima.
