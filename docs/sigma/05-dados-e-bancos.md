---
titulo: Dados e bancos
ordem: 5
---

## 4. Dados, bancos e modelo local

O SIGMA trabalha com mais de um banco porque cada um tem uma responsabilidade diferente. O PostgreSQL é o banco da aplicação: guarda o que o SIGMA controla. O Oracle ERP é a fonte oficial de OP, estoque, lote e movimentos. O Oracle Alchemy fornece informações de análise de bobina. Essa separação é fundamental para entender o sistema: nem tudo que aparece na tela está salvo localmente, e nem tudo que é salvo localmente já foi efetivado no ERP.

Em termos práticos:

- Se o usuário cadastrou um parâmetro, abriu chamado, gerou fila ou criou uma reunião, isso está no PostgreSQL.
- Se a tela mostra saldo de lote, situação de OP, operador ou movimento de estoque, normalmente isso veio do Oracle ERP.
- Se a tela mostra análise de bobina, flag de produção ou observação de qualidade vinda de máquina, isso vem do Alchemy.

### 4.1 PostgreSQL local

Configuração:

- Alias Django: `default`.
- Engine: `django.db.backends.postgresql`.
- Banco: `sigma`.
- Host nos ambientes de desenvolvimento e produção: PgBouncer local em `127.0.0.1:6432`; o PostgreSQL permanece em `127.0.0.1:5432`.
- Search path: `producao, manutencao, public`.
- PostgreSQL: `18.4`, com TimescaleDB `2.28.3` habilitado.
- Limite PostgreSQL: `max_connections = 150`, com `3` conexões reservadas para superusuário e até `147` conexões normais. O PgBouncer limita o SIGMA a no máximo `100` conexões reais nesse banco, preservando margem para a trava direta dos workers e administração.

Uso:

O PostgreSQL é a memória operacional do SIGMA. Ele guarda os registros que a aplicação precisa controlar independentemente do ERP. Isso inclui cadastros, usuários, permissões, parâmetros, filas de integração, reuniões de qualidade, chamados de manutenção e leituras de telemetria.

Nos ambientes de desenvolvimento e produção, o Django abre conexões curtas para o PgBouncer (`CONN_MAX_AGE = 0`). O PgBouncer, em pool por transação, devolve ao pool a conexão real do PostgreSQL ao final de cada transação. Ele mantém até `80` conexões normais e mais `20` de reserva, com teto de `100` conexões reais e até `300` clientes do SIGMA. Assim, aumentar threads ou usuários não multiplica diretamente as sessões no banco; requisições acima da capacidade aguardam uma conexão livre. O `search_path` é configurado no papel PostgreSQL do banco `sigma`, e não como parâmetro inicial da conexão. Os ciclos dos serviços em background também fecham suas conexões ao terminar.

No Windows de desenvolvimento, o serviço automático `SIGMA-PgBouncer` atende em `127.0.0.1:6432`; sua configuração fica em `C:\ProgramData\SIGMA\PgBouncer\pgbouncer.ini`. O arquivo local de autenticação é restrito ao serviço, administradores e usuário de desenvolvimento. O `.env` usa a porta `6432` para a aplicação e mantém `POSTGRES_DIRECT_PORT=5432` exclusivamente para a advisory lock global.

O PgBouncer fecha conexão real ociosa não reutilizada após 10 minutos (`server_idle_timeout = 600`). Também encerra cliente parado dentro de transação e query PostgreSQL que ultrapassem 5 minutos (`idle_transaction_timeout = 300` e `query_timeout = 300`), evitando que uma sessão travada consuma o pool indefinidamente.

A trava global dos workers é exceção: ela usa diretamente `127.0.0.1:5432`, fora do PgBouncer, pois o advisory lock precisa permanecer na mesma sessão durante a vida do processo. As conexões Oracle usadas por consultas específicas continuam sendo abertas e fechadas no próprio fluxo que as executa.

Cada conexão local do SIGMA informa sua origem em `application_name`: `sigma-web` para atendimento web, nomes específicos para serviços em background e `sigma-worker-lock` para a trava global. Isso permite separar, no PostgreSQL, conexões de tela, telemetria, integrações e coordenação de workers.

O processo também monitora a ocupação de conexões PostgreSQL e a fila do PgBouncer a cada 5 segundos. Ao alcançar 100 conexões de cliente, registra uma captura única no journal do `sigma.service` com total, limite do banco, PID, usuário, banco, origem/IP, `application_name`, estado, horários e a última query de cada sessão. O monitor só é rearmado quando o total cai para 70 ou menos, evitando repetição de logs durante o mesmo pico. Se algum cliente aguardar conexão no PgBouncer, registra uma captura única com clientes aguardando, tempo máximo de espera, clientes ativos, servidores ativos e conexões reais do pool; só rearma quando a fila zera. O journal é persistente no servidor; a consulta operacional é:

```bash
journalctl -u sigma.service --since "today 00:00" | grep -E 'POSTGRES_CONEXOES|PGBOUNCER_FILA'
```

Na faixa **Servidor** de `/services/status/`, `PgBouncer: usadas/100` é o consumo das conexões reais reservadas pelo pool para o banco `sigma`; `Esperando` mostra clientes que aguardam conexão livre. `PostgreSQL: total/147` é a contagem global das sessões reais do banco, incluindo a trava direta dos workers e conexões administrativas. Os dois indicadores medem camadas diferentes e devem ser lidos juntos. O botão **Detalhar conexões** abre o snapshot das sessões PostgreSQL com PID, rota, aplicação, estado, origem, evento de espera, horários e última query. A rota é comparada com `SHOW SERVERS` do PgBouncer: `PgBouncer` identifica uma conexão real mantida pelo pool e `Direta` identifica uma conexão que chegou ao PostgreSQL sem o pool, como a trava global dos workers.

No detalhe das conexões, `Livre para reutilização` significa a sessão ociosa que o PgBouncer pode emprestar para a próxima operação. `Aguardando próximo comando` é o estado técnico `ClientRead`: a conexão não está travada nem processando trabalho. `Em uso` indica query ou transação em execução; `Parada dentro de transação` merece atenção porque uma transação aberta não devolve a conexão ao pool.

A fila **Logs Apontamentos** processa no máximo `10` grupos de OP/estágio em paralelo (`LOGS_APONTAMENTOS_MAX_WORKERS`). Os demais grupos ficam na fila do executor e são enviados assim que um dos dez termina; esse limite impede que um lote grande crie uma thread por grupo.

As filas **Logs Apontamentos** e **Log Apontamento Componentes** usam a mesma chave de agrupamento — empresa, origem, OP, estágio e sequência — para reservar no máximo um registro da mesma OP/estágio por ciclo e evitar envio duplicado. A chave não determina a quantidade de threads: ambas podem enviar grupos diferentes em paralelo, limitadas a dez workers por fila (`LOGS_APONTAMENTOS_MAX_WORKERS` e `LOGS_APONTAMENTO_COMPONENTES_MAX_WORKERS`). Os grupos excedentes aguardam no executor; ao terminar uma chamada, inclusive com erro, a próxima chave inicia. Cada worker renova a atividade da fila antes de chamar o webservice, por até 180 segundos. O limite do ciclo da fila é 1.800 segundos (30 minutos); assim, a espera normal por vaga no limite de dez não é interpretada como travamento e o supervisor só solicita interrupção quando esse ciclo excede 30 minutos sem atividade válida.

A aplicação acessa esse banco principalmente pelo ORM do Django. Na prática, tabelas como apontamentos, liberações, pendências WMS, reuniões, chamados, cadastros e leituras de telemetria são manipuladas por modelos Python, não por SQL manual espalhado nas telas. Isso ajuda a manter validações, relacionamentos e regras de persistência centralizados no próprio projeto.

A principal razão de existir uma fila local é proteger a operação. Se o operador faz um apontamento e o ERP esta indisponivel, o SIGMA não perde a ação; ele grava localmente e deixa pendente para envio posterior. O mesmo vale para WMS e algumas movimentações de qualidade.

### 4.2 Oracle ERP

Configuração:

- Alias Django: `oracle_erp`.
- Engine: `django.db.backends.oracle`.
- Host/DSN: `172.16.30.51/dbdev`.

Uso:

O Oracle ERP é tratado como fonte de verdade para dados industriais e administrativos do processo produtivo. Quando o SIGMA precisa saber se uma OP existe, qual a situação de um lote, quanto saldo existe em um depósito, qual operador esta cadastrado ou quais movimentos formam a rastreabilidade de um lote, ele consulta o ERP.

O SIGMA também usa o ERP como caminho para algumas consultas ao WMS via DBLINK. Isso ocorre, por exemplo, na consulta de endereço/local WMS da área vermelha e na importação de paletes para a tabela `USU_TPALWMS`.

Importante: o SIGMA consulta o Oracle diretamente, mas os movimentos que alteram o ERP são enviados preferencialmente por webservice Sapiens/Senior, respeitando as regras do ERP.

### 4.3 Oracle Alchemy

Configuração:

- Alias Django: `oracle_alchemy`.
- Engine: `django.db.backends.oracle`.
- Host/DSN: `172.16.30.10/dbprod`.

Uso:

O Alchemy aparece como base auxiliar de qualidade e máquina. Ele fornece dados de bobina e análise que ajudam a qualidade a decidir se um lote pode ser liberado, deve ir para área vermelha ou precisa de outra destinação.

A bobina atual de MP-III, MP-IV e MP-V é calculada pelo coletor de Telemetria (ver 4.6.2), a partir das chaves `contagemBobinas`/`estouroDeContagem` da mesma fonte HTTP JSON usada pelos demais sensores desses recursos, e gravada em `Recurso.bobina`.

### 4.4 Campos e tabelas customizadas no Oracle ERP

O SIGMA depende de campos `USU_` no Oracle ERP para complementar regras que não existem nos campos padrão do Senior. Esses campos funcionam como extensoes da regra industrial: guardam situação customizada de lote, ligacao entre movimentos, número de bobina, backup de configuração de baixa de componente e dados auxiliares usados pelas regras LSP dos webservices.

Essas customizacoes precisam ser tratadas como parte da arquitetura do sistema. Se um campo `USU_` estiver ausente, com tipo incorreto, sem carga ou com regra diferente da esperada, o erro pode aparecer como falha de apontamento, falha de rastreamento, lote não localizado, baixa duplicada de componente ou divergencia entre ERP e WMS.

Campos customizados:

| Campo | Tabela | Uso |
|---|---|---|
| `USU_ATRCCU` | `E011DEF` | Forma de atribuição do centro de custo no movimento de estoque: `OF` para OP de fabricação, `OC` para OP de consumo ou `CF` para centro de custo fixo. |
| `USU_CCUFIX` | `E011DEF` | Centro de custo fixo do motivo, usado quando `USU_ATRCCU` está configurado como `CF`. |
| `USU_UTIAVE` | `E011DEF` | Campo "Utiliza na Área Vermelha" da `F011DEF`; quando está como `S`, permite que o motivo apareça na reunião de Área Vermelha. |
| `USU_SITLOT` | `E210DLS` | Situação personalizada do lote; valida pendência, exibe status, filtra busca e recebe ação dos webservices. |
| `USU_CODLIG` | `E210MVP` | Liga movimentos de estoque no rastreamento de lote; usar o código nativo geraria inconsistências fiscais nas transformações de produto. |
| `USU_NUMBOB` | `E900EOQ` | Número de bobina usado em apontamento, qualidade, rastreamento e localização de depósito do lote; liga ERP, Alchemy e recurso. |
| `USU_BXAORP` | `E900CMO` | Backup do `BXAORP` original do componente da OP para evitar baixa duplicada e restaurar o comportamento após a regra customizada. |
| `USU_QTDBOB` | `E900COP` | Quantidade de bobinas planejada/esperada da OP, exibida na tela de apontamento. |
| `USU_DESCRE` | `E725CRE` | Descrição/local personalizado do centro de recurso usado no envio ao WMS. |

A tabela customizada `USU_TRESPED` registra a reserva de pedidos para OPs. O Calendário de OPs a consulta somente para leitura, sempre pela empresa e filial do usuário logado, para mostrar o total comprometido e os pedidos reservados da OP. Ela não é uma tabela local do SIGMA nem é alterada pelo calendário.

Campos usados da `USU_TRESPED`:

| Campo | Uso no Calendário de OPs |
|---|---|
| `USU_CODEMP` | Empresa da reserva; recebe a empresa da filial do usuário. |
| `USU_CODFIL` | Filial da reserva; recebe a filial do usuário. |
| `USU_NUMORP` | OP consultada. |
| `USU_NUMPED` | Pedido reservado exibido no detalhe da OP. |
| `USU_QTDRES` | Quantidade reservada; é somada por pedido e no total da OP. |

A tabela customizada `USU_TPALWMS` é usada como ponte entre palete WMS e componente ERP. Ela permite que o apontamento de componente receba um palete lido na operação e descubra, no ERP, qual lote, produto, derivação e quantidade estão associados a esse palete.

Campos principais da `USU_TPALWMS`:

| Campo | Uso |
|---|---|
| `USU_CODEMP` | Empresa usada para localizar e atualizar palete WMS. Faz parte da chave da importação. |
| `USU_PALWMS` | Código do palete WMS recebido no apontamento de componente. |
| `USU_QTDDIS` | Quantidade disponível do palete, usada como quantidade do componente e validação de saldo. |
| `USU_CODLOT` | Lote ERP vinculado ao palete WMS. |
| `USU_CODCMP` | Código do componente vinculado ao palete. |
| `USU_DERCMP` | Derivação do componente vinculado ao palete. |
| `USU_DATGER` | Data de geração/processamento da importação ou leitura. |
| `USU_HORGER` | Hora de geração da importação do palete, gravada em minutos do dia. |
| `USU_ARMWMS` | Armazém/origem WMS do palete importado. |
| `USU_HORLOG` | Hora de log atualizada quando o palete é lido ou apontado. |
| `USU_LOGPRC` | Log do processo do palete WMS, como leitura ou apontamento pelo `APONTAR-COMPONENTE`. |

A tabela customizada `USU_TBXACMP` registra pendências de baixa de componente geradas pelos webservices de apontamento. Ela existe para separar o apontamento da OP da baixa posterior de componentes quando a regra precisa controlar a baixa de forma assíncrona, pelo fluxo automático do ERP e pelo webservice interno de baixa.

Campos principais da `USU_TBXACMP`:

| Campo | Uso |
|---|---|
| `USU_CODEMP` | Empresa da pendência de baixa de componente. |
| `USU_CODORI` | Origem da OP vinculada a pendência. |
| `USU_NUMORP` | Número da OP vinculada a pendência. |
| `USU_CODETG` | Etapa da OP vinculada a pendência. |
| `USU_CODCMP` | Código do componente cuja baixa ficou pendente. |
| `USU_DERCMP` | Derivação do componente pendente. |
| `USU_LOTDES` | Lote destino/produto acabado associado a pendência. |
| `USU_QTDUTI` | Quantidade utilizada que deve ser baixada posteriormente. |
| `USU_LOGINC` | Log da inclusão da pendência, gravado no momento em que o apontamento cria o registro. |
| `USU_CODCRE` | Centro de recurso associado a pendência. |
| `USU_CODLOT` | Lote do componente a consumir. Quando não há lote informado, é gravado vazio; a regra de baixa trata espaço/vazio como ausência de lote. |
| `USU_DATMOV` | Data do movimento usado para registrar a pendência. |
| `USU_HORMOV` | Hora do movimento usado para registrar a pendência. |
| `USU_SITPEN` | Situação da pendência: `1` pendente, `2` em processamento, `3` sucesso e `4` erro. |
| `USU_DATPRC` | Data do processamento da baixa. |
| `USU_HORPRC` | Hora do processamento da baixa. |
| `USU_USUPRC` | Usuário/processo responsável pelo processamento. |
| `USU_IDEUNI` | Identificador único da pendência, gerado por GUID na inclusão e usado pela orquestração automática/webservice para processar o registro correto. |

### 4.5 Índices personalizados

Os índices personalizados existem para sustentar consultas que seriam caras nas tabelas de rastreamento, paradas de máquina e OEE. Eles não mudam a regra de negócio, mas reduzem o custo de busca e ordenação em pontos onde o sistema precisa responder rápido.

No PostgreSQL local, os índices estão ligados principalmente ao histórico local do SIGMA: liberação de lote, paradas de máquina e planejado OEE.

#### `ix_liberacao_lote_codlot`

Uso: rastreamento público de lote. Busca eventos locais de qualidade pelo lote original e ordena por `datger`.

SQL:

```sql
CREATE INDEX ix_liberacao_lote_codlot
ON qualidade.liberacao_lote (codemp, codlot, datger);
```

#### `ix_liberacao_lote_lottrf`

Uso: rastreamento público de lote. Quando a URL recebe um lote transferido ou reclassificado, encontra o lote original pelo campo `lottrf`.

SQL:

```sql
CREATE INDEX ix_liberacao_lote_lottrf
ON qualidade.liberacao_lote (codemp, lottrf, datger);
```

#### `idx_parada_recurso_fim`

Uso: consultas de parada por recurso, principalmente para localizar parada em aberto ou histórico recente.

SQL:

```sql
CREATE INDEX idx_parada_recurso_fim
ON producao.paradas_maquina (recurso_id, fim);
```

#### `idx_parada_tipo_fim`

Uso: consultas de parada por tipo manual ou sinal, filtrando paradas abertas ou encerradas.

SQL:

```sql
CREATE INDEX idx_parada_tipo_fim
ON producao.paradas_maquina (tipo, fim);
```

#### `idx_tlm_leitura_rec_data`

Uso: histórico de telemetria por recurso, em ordem da leitura mais recente para a mais antiga.

SQL:

```sql
CREATE INDEX idx_tlm_leitura_rec_data
ON telemetria.leituras (recurso_id, coletado_em DESC);
```

A tabela `telemetria.leituras` é uma hypertable do TimescaleDB particionada por `coletado_em`. Sua identificação única é composta por `recurso_id` e `coletado_em`; nenhuma outra tabela possui referência direta a uma leitura. O intervalo padrão dos chunks é de sete dias. Não há política automática de retenção ou compressão configurada.

#### `idx_apont_codemp_id`

Uso: entrada nativa da tela Logs Apontamentos para usuários restritos à empresa, mantendo os registros mais recentes primeiro.

SQL:

```sql
CREATE INDEX idx_apont_codemp_id
ON producao.apontamento (codemp, id DESC);
```

#### `idx_apont_fila_chave`

Uso: ordenação e bloqueio da fila de apontamentos da mesma OP.

SQL:

```sql
CREATE INDEX idx_apont_fila_chave
ON producao.apontamento (status, codemp, origem, numorp, codetg, seqrot, id);
```

#### `idx_comp_codemp_id`

Uso: entrada nativa da tela Logs Componentes para usuários restritos à empresa, mantendo os registros mais recentes primeiro.

SQL:

```sql
CREATE INDEX idx_comp_codemp_id
ON producao.apontamento_componente (codemp, id DESC);
```

#### `idx_comp_fila_chave`

Uso: bloqueio da fila de componentes da mesma OP.

SQL:

```sql
CREATE INDEX idx_comp_fila_chave
ON producao.apontamento_componente (status, codemp, origem, numorp, codetg, seqrot);
```

#### `idx_log_op_troca_id`

Uso: paginação do Log Tempo Produção. Períodos ainda abertos aparecem antes dos fechados; dentro de cada grupo, os mais recentes aparecem primeiro.

SQL:

```sql
CREATE INDEX idx_log_op_troca_id
ON producao.logs_troca_op_ativa (horario_troca DESC, id DESC);
```

#### `idx_lote_grupo_id`

Uso: agrupamento e paginação da Consulta de Lotes por empresa, bobina, lote, produto e derivação.

SQL:

```sql
CREATE INDEX idx_lote_grupo_id
ON qualidade.liberacao_lote (codemp, numbob, codlot, codpro, codder, id DESC);
```

#### `idx_lote_status_id`

Uso: filtro de status e processamento da fila de liberação de lotes.

SQL:

```sql
CREATE INDEX idx_lote_status_id
ON qualidade.liberacao_lote (status, id DESC);
```

#### `oee_planeja_data_30140b_idx`

Uso: consultas de OEE planejado por data.

SQL:

```sql
CREATE INDEX oee_planeja_data_30140b_idx
ON public.oee_planejado_diario (data);
```

No Oracle ERP, os índices estão ligados principalmente ao rastreamento público de lote. O rastreamento cruza eventos de apontamento, saldo atual e movimentos de estoque. Sem índices adequados, essas consultas podem ficar lentas porque as tabelas ERP possuem alto volume histórico.

#### `I_NEX_E900EOQ_LOTE`

Uso: rastreamento público de lote. Busca eventos de produção/apontamento ERP do lote e ordena por `DATREA` e `HORREA`.

SQL:

```sql
CREATE INDEX I_NEX_E900EOQ_LOTE
ON E900EOQ (CODEMP, CODLOT, DATREA, HORREA);
```

#### `I_NEX_E210DLS_LOTE`

Uso: rastreamento público de lote. Busca saldo atual ERP dos lotes encontrados no rastreamento.

SQL:

```sql
CREATE INDEX I_NEX_E210DLS_LOTE
ON E210DLS (CODEMP, CODLOT, CODDEP, CODPRO, CODDER);
```

#### `I_NEX_E210MVP_LOTE_FULL`

Uso: rastreamento público de lote. Busca movimentos ERP do lote original, obtém `USU_CODLIG` e ordena por `DATDIG`, `HORDIG` e `SEQMOV`.

SQL:

```sql
CREATE INDEX I_NEX_E210MVP_LOTE_FULL
ON E210MVP (CODEMP, CODLOT, USU_CODLIG, DATDIG, HORDIG, SEQMOV);
```

#### `I_NEX_E210MVP_LIG`

Uso: rastreamento público de lote. Busca movimentos ERP ligados pelo mesmo `USU_CODLIG` e mantém transferências/reclassificações agrupadas no fluxo.

SQL:

```sql
CREATE INDEX I_NEX_E210MVP_LIG
ON E210MVP (CODEMP, USU_CODLIG, DATDIG, HORDIG, SEQMOV);
```

#### `I_NEX_E210MVP_LOTE_CODLIG`

Uso: rastreamento público de lote. Atende o fallback por `CODLIG` quando o movimento não possui `USU_CODLIG`, buscando o lote original e ordenando por `DATDIG`, `HORDIG` e `SEQMOV`.

SQL:

```sql
CREATE INDEX I_NEX_E210MVP_LOTE_CODLIG
ON E210MVP (CODEMP, CODLOT, ESTEOS, CODLIG, DATDIG, HORDIG, SEQMOV);
```

#### `I_NEX_E210MVP_CODLIG`

Uso: rastreamento público de lote. Busca movimentos ERP ligados pelo mesmo `CODLIG` quando o fallback é necessário, preservando a separação entre entrada e saída por `ESTEOS`.

SQL:

```sql
CREATE INDEX I_NEX_E210MVP_CODLIG
ON E210MVP (CODEMP, CODLIG, ESTEOS, DATDIG, HORDIG, SEQMOV, CODLOT);
```

#### `I_NEX_E900EOQ_OP_RECURSO`

Uso: rastreamento público de lote. Busca a máquina/recurso da OP a partir dos movimentos de estoque `E210MVP.ORIORP` e `E210MVP.NUMDOC`, usando a menor sequência de operação com `CODCRE` preenchido.

SQL:

```sql
CREATE INDEX I_NEX_E900EOQ_OP_RECURSO
ON E900EOQ (CODEMP, CODORI, NUMORP, CODCRE, SEQEOQ);
```

### 4.6 Principais modelos locais do projeto

Esta seção descreve as principais entidades que o SIGMA controla localmente. Não é necessário memorizar os nomes técnicos; o importante é entender que cada entidade representa uma parte da operação que o sistema precisa guardar para funcionar.

Os modelos locais podem ser divididos em cinco grupos:

1. Estrutura e parâmetros: definem a organização da fábrica e como cada filial/centro/recurso deve se comportar.
2. Produção: guardam sequenciamento, apontamentos e filas de envio ao ERP.
3. Qualidade: guardam reuniões, liberações de lote e filas WMS.
4. Manutenção: guardam chamados, ordens de serviço e interações.
5. Telemetria: guardam configuração HTTP, sensores, vínculos por recurso e leituras interpretadas.

#### 4.6.1 Accounts

O grupo `Accounts` representa a base administrativa do SIGMA. Ele define quem usa o sistema, em qual filial trabalha, quais recursos existem, quais centros produtivos organizam esses recursos e quais parâmetros devem ser aplicados nos fluxos operacionais. Sem essa camada, os módulos de produção, qualidade, manutenção e OEE não conseguem decidir corretamente onde buscar saldo, para onde movimentar lote, qual recurso recebe apontamento ou qual calendário deve ser usado.

Um ponto importante e que esses modelos não são apenas "cadastro". Muitos deles interferem diretamente na regra de negócio. Por exemplo, `ParametrosFilial`, `ParametrosCentroRecurso` e `ParametrosRecurso` determinam depósitos, limites e comportamentos que aparecem nos fluxos de apontamento, liberação de lote, área vermelha e OEE. O cadastro de `Recurso` também é usado por telemetria, manutenção, sequenciamento, OP ativa e calculo de planejado.

No cadastro de recursos, a aba OEE possui campos que foram mantidos para evolução futura do módulo de OEE, como metas e quantidade de pessoas. No funcionamento atual, os campos dessa aba que interferem diretamente no fluxo produtivo são `view_id`, `aponta_parada`, `exibir_jus` e `permite_parada_manual`. O `view_id` define qual versão da tela de apontamento será aberta para o recurso quando o operador entrar por uma OP/código de barras e define se o sequenciamento base pode controlar a OP ativa: as Views `0`, `1` e `2` usam o fluxo de uma OP; a View `3` é reservada ao fluxo Multi-OP e controla suas alocações na própria tela. Os campos `aponta_parada` e `exibir_jus` atuam em conjunto no modal de justificativa e no bloqueio visual de apontamento. `permite_parada_manual` autoriza a abertura manual somente se `aponta_parada` também estiver ativo; a permissão `Pode Alterar Paradas` também autoriza essa abertura, inclusive quando recebida por grupo, mas nunca ignora `aponta_parada`.

A aba `Motivos de Parada` do recurso mantém a abrangência dos motivos ERP permitidos para aquele recurso. O sistema deriva `codemp` da empresa da filial do recurso, lista os grupos ativos de `USU_T018GPM` (`USU_CODGPM`, `USU_DESGPM`, `USU_SITGPM='A'`) e, após a escolha, lista os motivos ativos de `E018MTV` (`CODMTV`, `DESMTV`, `SITMTV='A'`) ligados ao grupo em `USU_T018MVP` (`USU_CODEMP`, `USU_CODGMP`, `USU_CODMTV`). As consultas usam a conexão Oracle padrão, que já seleciona o schema do ambiente. O vínculo local guarda `id_recurso`, `codemp`, `codgpm` e `codmtv`; a chave única impede repetir a combinação recurso, empresa, grupo e motivo ERP. A mesma aba também copia os vínculos de um recurso ativo escolhido por empresa: os códigos são gravados para a empresa do recurso de destino somente quando continuam ativos no ERP, sem duplicar vínculos já existentes. O botão **Sincronizar motivos de todos os recursos** remove os vínculos locais cujo grupo ou motivo não esteja ativo e ligado em `USU_T018MVP`; se a consulta ERP falhar para alguma empresa, não remove vínculo algum. Nas telas de apontamento, esses vínculos são a lista visual de motivos disponível para justificar uma parada aberta.

| Modelo | Tabela | Finalidade |
|---|---|---|
| `CustomUser` | `accounts_customuser` | Usuário do sistema, filial, operador ERP e página inicial. |
| `Empresa` | `empresas` | Empresa, código ERP, lote atual e status ativo. |
| `Filial` | `filial` | Filial vinculada a empresa. |
| `ParametrosFilial` | `parametros_filial` | Parâmetros integração/qualidade por filial. |
| `Departamento` | `departamentos` | Agrupamento organizacional. |
| `Setor` | `setores` | Setor vinculado a departamento. |
| `CentroRecurso` | `centros_recursos` | Centro produtivo, código e código integrador ERP. |
| `ParametrosCentroRecurso` | `parametros_centros_recursos` | Depósitos e parâmetros por centro. |
| `Recurso` | `recursos` | Recurso produtivo, configurações OEE/apontamento e bobina atual. |
| `ParametrosRecurso` | `parametros_recursos` | Parâmetros especificos do recurso. |
| `Tara` | `taras` | Cadastro de taras. |
| `RecursoTara` | `recurso_taras` | Relacao recurso x tara. |
| `MotivoAbrangencia` | `motivos_abrangencia` | Grupo e motivo ERP ativos permitidos por recurso e empresa, identificados por `CODGPM` e `CODMTV`. |
| `LogTrocaOPAtiva` | `logs_troca_op_ativa` | Histórico de OP ativa por recurso, guardando a OP em campos decompostos (`origem`, `op`, `estagio`, `seqrot`), horário da troca/saída, operador e status/log/data_hora de integração. |
| `TurnoBase` | `turnos_base` | Turno padrão. |
| `TurnoRecurso` | `turnos_recursos` | Turno aplicado ao recurso e dias da semana. |
| `Calendario` | `calendario` | Calendário por filial. |
| `CalendarioEvento` | `calendario_eventos` | Feriado, parada e evento. |
| `HoraExtraPlanejada` | `horas_extras_planejadas` | Horas extras planejadas por recurso. |
| `ParadaMaquina` | `producao.paradas_maquina` | Parada física do recurso, com início, fim, código do operador, usuário, tipo e data/hora. Relaciona-se a um ou mais períodos de `LogTrocaOPAtiva` afetados. |
| `JustificativaParada` | `producao.justificativas_paradas` | Justificativas sequenciais da parada, com motivo ERP, início parcial e tempo. A última justificativa de uma parada aberta permanece sem tempo até ser substituída ou até o fim da parada. |
| `PacoteTempoERP` | `producao.pacotes_tempo_erp` | Corte local de um período de `LogTrocaOPAtiva` para envio de tempos ao ERP, com início/fim reais, status, log e data/hora do retorno. |
| `ItemPacoteTempoERP` | `producao.itens_pacote_tempo_erp` | Produção ou parada pertencente ao pacote, com operador, motivo de parada e data/hora inicial e final que serão enviadas ao ERP. |
| `OEEPlanejadoDiario` | `public.oee_planejado_diario` | Minutos planejados por recurso/dia. |
| `ConfiguracaoAplicacao` | `configuracoes_aplicacao` | Configuração **não sensível** da aplicação, editável em runtime na tela Configurações da Aplicação; gravação só por `definir()`/save de instância — o signal mantém o cache do service de configurações fresco. |

#### 4.6.2 Telemetria

O módulo `telemetria` é independente dos demais cadastros, mas usa `accounts.Recurso` como referência. Seus dados ficam no schema PostgreSQL `telemetria`; o recurso continua na tabela `public.recursos`. A regra automática de parada pertence ao domínio de produção, fica no schema `producao` e também se relaciona diretamente ao recurso. Não há OPC-UA, Modbus ou autenticação HTTP neste módulo.

A configuração HTTP pertence à fonte, com URL única, coleta ativa, timeout, pausa após sucesso e espera após erro. Cada sensor pertence a uma fonte e informa uma chave única dentro dela, recebida no JSON. Um recurso pode vincular sensores de uma única fonte.

À parte do cadastro de `Sensor`/`SensorRecurso`, o coletor também calcula `Recurso.bobina` a partir das chaves `contagemBobinas`/`estouroDeContagem` de qualquer bloco do JSON cujo topo bata com um `Recurso.codigo` existente (ver 6.5.1 em `07-integracoes-externas.md`). Não é um sensor cadastrável nem aparece na aba Telemetria.

| Modelo | Tabela | Finalidade |
|---|---|---|
| `FonteColetaHTTP` | `telemetria.fontes_coleta_http` | Fonte HTTP única, com URL, timeout, pausas, backoff e último erro. |
| `Sensor` | `telemetria.sensores` | Sensor da fonte, com chave JSON única por fonte, nome, tipo, unidade e situação. |
| `SensorRecurso` | `telemetria.sensores_recursos` | Vínculo do sensor ao recurso, limitado a uma fonte por recurso, com monitoramento e tolerância. |
| `LeituraTelemetria` | `telemetria.leituras` | Leitura interpretada em JSONB, identificada por recurso e data/hora da coleta. |
| `RegraParadaRecurso` | `producao.regras_parada_recursos` | Regra automática de parada, única por recurso, com situação e árvore JSONB de grupos e condições. |

Na aba **Telemetria** do cadastro do recurso, o usuário configura a comunicação e os vínculos, além de consultar o cache do coletor com o último snapshot interpretado e a última leitura efetivamente salva. A aba **Parada Automática** concentra a regra de parada por telemetria: ela pode ser ativada ou desativada e é montada visualmente com condições, grupos `E`, `OU` e `NÃO`, grupos aninhados e reordenação dos itens; entre os itens de um quadro aparece um conector com o operador daquele grupo (`E · todas precisam ocorrer`, `OU · basta uma ocorrer`, `NÃO · inverte o resultado`), e abaixo do editor a regra é traduzida ao vivo para uma fórmula em português com o rótulo "PARADO SE:" (sem substituir o JSON). A tela só oferece sensores ativos vinculados ao próprio recurso. A própria tela explica que uma condição testa um sensor e que um grupo combina resultados, e exibe em modo somente leitura o JSON montado que será salvo. O cadastro mestre **Sensores** fica no submenu de Recursos e permite listar, incluir, editar, ativar/desativar e excluir sensores que não estejam vinculados.

Campos do cadastro de usuário (`CustomUser`):

| Campo | Tela | Onde aparece | Uso no sistema |
|---|---|---|---|
| `filial` | `Filial` | Cadastro/edição de usuário e lista de usuários. | Define a empresa e filial do usuário logado. A filial limita empresas e centros exibidos nas telas, filtra logs e registros para usuários sem perfil staff, busca parâmetros de liberação de lote e Área Vermelha, e valida acesso a etiquetas de outra empresa. |
| `idintegracao` | `Idintegracao` ou `ID Integração` | Cadastro/edição e lista de usuários. | Identificador enviado ao ERP nas ações de qualidade. É usado em Área Vermelha, liberação, refugo e reclassificação de lote. No SOAP alimenta `usuRes`. Sem esse valor, a integração retorna erro de usuário sem ID configurado. |
| `idoperador` | `ID Operador` | Cadastro/edição de usuário. | Campo cadastral sem uso operacional atual. O operador do apontamento é digitado na tela, validado no ERP em `E906OPE` e gravado em `LogTrocaOPAtiva.id_operador`. |

#### 4.6.3 Produção

Os modelos de produção guardam a trilha local do que a fábrica tentou executar. Eles são essenciais porque o ERP não e chamado de forma cega e descartavel; antes ou durante a integração, o SIGMA cria registros locais que permitem consultar, acompanhar e reprocessar.

O `Sequenciamento` organiza a ordem planejada das OPs por recurso. O `Apontamento` registra apontamentos de OP e controla se foram enviados com sucesso ao ERP. O `ApontamentoComponente` faz o mesmo para consumo/baixa de componentes, podendo também gerar ajuste no WMS quando o componente vem de palete WMS. A correção de quantidade do lote é transacional no ERP e não mantém uma fila local de estorno.

As filas de integração locais (`Apontamento`, `ApontamentoComponente`, `BaixaComponente`, `PacoteTempoERP`, `LiberacaoLote` e `WMS_IntegraçãoOP`) têm o campo `datger`, que fixa o momento em que o registro foi gerado, gravado na criação e nunca mais alterado — diferente de `data_hora`/`data_hora_log`, que se atualizam a cada save. O nome segue o vocabulário Sapiens das filas (`datmov`/`hormov`); em `LiberacaoLote` o campo se chamava `datager` e foi unificado para `datger` pela migration 0015 (o PostgreSQL ajusta os índices existentes no rename da coluna).

| Modelo | Tabela | Finalidade |
|---|---|---|
| `Sequenciamento` | `producao.sequenciamento` | Sequência local de OPs por recurso. |
| `Apontamento` | `producao.apontamento` | Fila/log local de apontamentos de OP. |
| `ApontamentoComponente` | `producao.apontamento_componente` | Fila/log local de apontamentos de componentes. |
| `CorrecaoLote` | `producao.correcao_lote` | Controle da correção manual de lote, incluindo estado de conciliação, responsável, data e observação. |

#### 4.6.4 Qualidade

Os modelos de qualidade guardam decisões e pendências que impactam lote, estoque e WMS. A qualidade não apenas consulta informações: ela decide se um lote pode seguir, se deve ficar em área vermelha, se será refugo, se será reclassificado ou se precisa gerar movimento externo.

A `Reuniao` representa a análise da área vermelha e seus participantes. A `LiberacaoLote` registra decisões de liberação, refugo ou reclassificação que depois podem virar movimentação no ERP. A fila `WMS_IntegraçãoOP` e o controle local do que precisa ser enviado ao WMS, seja novo lote, ajuste de estoque ou outro tipo suportado pelo fluxo.

| Modelo | Tabela | Finalidade |
|---|---|---|
| `Reuniao` | `qualidade.reuniao` | Reunião de área vermelha. |
| `ReuniaoParticipante` | `qualidade.reuniao_participantes` | Participantes da reunião. |
| `ObservacaoEtiqueta` | `qualidade.observacao_etiqueta` | Observações selecionaveis na etiqueta. |
| `LiberacaoLote` | `qualidade.liberacao_lote` | Liberação, refugo ou reclassificação de lote. |
| `WMS_IntegraçãoOP` | `qualidade.wms_integracao_op` | Fila de envio ao WMS. |

#### 4.6.5 Manutenção

Os modelos de manutenção registram solicitacoes, ordens de serviço e histórico de comunicação. A relacao com `Recurso` e importante porque o chamado nasce ligado ao equipamento ou ponto produtivo afetado. Isso permite consultar histórico por recurso e direcionar atendimento.

As interações funcionam como linha do tempo. Elas indicam o que foi informado, quem respondeu, quais anexos ou descrições foram acrescentados e como a OS ou chamado evoluiu até encerramento.

| Modelo | Tabela | Finalidade |
|---|---|---|
| `Chamado` | `chamado` | Chamado de manutenção por recurso. |
| `Interacao_Chamado` | `chamado_interacao` | Histórico de interações do chamado. |
| `OrdemServico` | `ordem_servico` | Ordem de serviço. |
| `Interacao_OS` | `ordem_servico_interacao` | Histórico de execução/interação da OS. |

---

*Verificado contra o código em 2026-09-02.*
