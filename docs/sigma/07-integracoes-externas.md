---
titulo: Integrações externas
ordem: 7
---

## 6. Integrações externas e contratos de comunicação

As integrações são a parte mais sensível do SIGMA. Elas conectam a operação local com sistemas que possuem regras e disponibilidade proprias. Por isso, o SIGMA évita depender de uma única chamada imediata para concluir uma operação crítica. Sempre que possível, ele registra localmente, tenta enviar, interpreta o retorno e deixa log para reprocessamento.

Existem dois tipos de integração:

1. Consulta: o SIGMA busca informações em outro sistema para exibir, validar ou decidir.
2. Envio: o SIGMA énvia uma solicitacao para outro sistema éfetivar uma ação.

Exemplo: consultar saldo de lote no Oracle ERP e uma consulta. Enviar `MovimentarEstoque` para o Sapiens e um envio.

### 6.1 ERP Oracle - consulta direta

O Oracle ERP e consultado diretamente quando o SIGMA precisa ler dados que já existem no ERP. Essas consultas alimentam telas e validações, mas em geral não fazem a movimentação principal do processo. A movimentação é feita por webservice.

Essa abordagem permite que o SIGMA mostre dados atualizados do ERP sem duplicar toda a base localmente. Ao mesmo tempo, mantém as alterações importantes passando pelas regras do ERP/Sapiens.

Principais tabelas usadas:

| Tabela | Uso |
|---|---|
| `E900COP` | OPs, situação da OP, sequenciamento e encerramento. |
| `E900QDO` | Dados da OP/quantidade. |
| `E900OOP` | Operações/roteiro/centro de recurso. |
| `E900CMO` | Componentes da OP. |
| `E900EOQ` | Eventos/apontamentos, bobina, lote, recurso, data/hora. |
| `E210DLS` | Saldo de lote por depósito/produto/derivacao. |
| `E210MVP` | Movimentos de estoque e rastreabilidade. |
| `E725CRE` | Centro de recurso ERP. |
| `E075PRO` / `E075DER` | Produto e derivacao. |
| `E906OPE` | Operadores. |
| `E011DEF` | Motivos/defeitos de área vermelha. |
| `USU_TPALWMS` | Paletes WMS importados no ERP. |
| `USU_TRESPED` | Reservas de pedidos por OP, usadas para mostrar quantidade comprometida no Calendário de OPs. |

### 6.2 ERP Sapiens/Senior - SOAP

O Sapiens/Senior SOAP e usado quando o SIGMA precisa pedir ao ERP para executar uma ação de negócio que não pode ser resolvida apenas no banco local. Cada webservice existe para um motivo operacional especifico: registrar produção, controlar consumo de componente, movimentar lote, tratar refugo/reclassificação, enviar lote para área vermelha ou desfazer baixa de componente.

O SIGMA monta um JSON com os dados da operação e envia esse JSON dentro de um envelope SOAP. O ERP processa a regra customizada em LSP e devolve um retorno. O SIGMA interpreta esse retorno para decidir se o registro local deve virar integrado ou voltar para pendente.

O ponto mais importante e que esses webservices não são apenas "envio de dados". Eles executam regras do lado do Senior: chamam rotinas padrão do ERP, ajustam situação customizada de lote, controlam baixa automática de componentes, gravam pendências internas para baixa posterior e preservam ligacoes de rastreabilidade.

Base:

```text
SAPIENS_URL_BASE/g5-senior-services/sapiens_Synccustom.senior.man.producao
```

Formato:

- HTTP POST.
- Content-Type `application/soap+xml; charset=ISO-8859-1`.
- Envelope SOAP.
- Usuário e senha vindos de ambiente.
- Payload JSON colocado em CDATA no campo `wdados`.

O envelope e o CDATA são escapados antes do envio. Logs técnicos e mensagens
persistidas mascaram usuário e senha do SOAP; a tela recebe mensagem operacional
genérica, enquanto o detalhe permanece no logger do servidor.

As respostas desses webservices podem voltar em codificação diferente do UTF-8 usado pela aplicação. Por isso, o SIGMA centraliza a leitura de resposta HTTP em utilitário próprio de codificação. Esse tratamento evita que uma resposta SOAP valida seja interpretada com caracteres quebrados ou gere erro ao gravar log da fila.

#### 6.2.1 Webservices enviados e motivo operacional

| Serviço | Quando o SIGMA usa | Motivo do envio | O que a regra Senior faz |
|---|---|---|---|
| `Apontamentos` | Apontamento normal de OP. | Efetivar no ERP a produção apontada na fábrica, com quantidade boa, refugo, lote, bobina, recurso, operador e horário. | Executa o apontamento da OP, evita duplicidade do mesmo apontamento, controla início/fim quando necessário, desliga temporariamente a baixa automática da OP, restaura a configuração original e cria pendências de baixa de componentes em `USU_TBXACMP` com `USU_SITPEN=1` e `USU_IDEUNI` gerado por GUID. A quantidade da pendência segue o modelo técnico: fixa quando configurada ou proporcional à quantidade apontada. Também marca o lote apontado como pendente na situação customizada do ERP. |
| `AumentarApontamento` | Correcao/aumento de apontamento já existente. | Acrescentar quantidade a uma OP/lote sem repetir o fluxo operacional completo da tela de apontamento. | Reaproveita a lógica de apontamento para incrementar quantidade, evita duplicidade, calcula componentes proporcionais, preserva a configuração original de baixa automática e gera pendências de baixa em `USU_TBXACMP` com status pendente e identificador único. |
| `ApontamentoComponente` | Apontamento de componente informado pela operação, normalmente a partir de lote ERP ou palete WMS resolvido pelo SIGMA. | Registrar no ERP que determinado componente foi consumido para a OP e, ao mesmo tempo, apontar a OP pela quantidade liquida correspondente quando aplicável. | Valida saldo do lote do componente, calcula quantidade liquida considerando perda de processo, aponta a OP, grava pendências proporcionais de componentes e grava também o componente recebido para baixa posterior, usando `USU_SITPEN=1`, `USU_LOGINC` e `USU_IDEUNI`. |
| `ApontamentoTempos` | Pacote consolidado de produção e paradas de uma OP/recurso. | Registrar no ERP os períodos de produção e as paradas com operador, motivo e horários. | Recebe a chave da OP (`empresa`, `origem`, `op`, `estagio`, `roteiro`, `maquina`) e as listas `producoes` e `paradas`. Exige OP liberada ou em andamento, recurso com centro de custo, nenhum início de OP sem fim no ERP e exatamente uma Produção. O início da Produção identifica duplicidade. Produção e Paradas exigem operador com superior cadastrado; se a Parada tiver outro superior, usa o superior da Produção. O pacote é uma única transação: erro em um item impede a efetivação dos demais. |
| Regra orquestradora 230 | Processamento automático Senior para pendências `USU_TBXACMP`. | Separar o disparo da baixa do momento em que o apontamento cria a pendência. | Segue o fluxo automático da IPEL: busca pendências com `USU_SITPEN=1`, respeita o paralelismo configurado em `E000PDV`, marca como `USU_SITPEN=2` e envia os registros de forma assíncrona para o webservice interno `BaixaComponenteERP`, informando o `USU_IDEUNI`. |
| `BaixarComponentes` | Regra do webservice interno `BaixaComponenteERP`, chamada pela orquestração automática. | Efetivar a baixa de componentes que ficaram pendentes após apontamento de OP ou apontamento de componente. | Recebe `ideUni`, busca a pendência por `USU_IDEUNI`, valida família, centro de custo, depósito, saldo e lote, libera o componente na OP, executa a baixa e atualiza a pendência para `USU_SITPEN=3` em sucesso ou `USU_SITPEN=4` em erro. Também grava log de processamento com `CodPrc=3` e `IdePrc=BXC`. |
| `MovimentarEstoque` | Liberação normal de lote ou envio de lote para Área Vermelha quando o produto/lote permanece o mesmo e muda o depósito/local. | Movimentar estoque no ERP entre depósitos e atualizar a situação customizada do lote. | Executa movimentação de estoque quando origem é destino éxigem movimento. Se não houver movimento necessário, apenas trata a situação. Ao final, grava em `E210DLS.USU_SITLOT` a situação enviada pelo SIGMA. |
| `TransferenciaProduto` | Refugo ou reclassificação de lote. | Transformar o saldo de um produto/derivacao/lote em outro produto/derivacao/lote, preservando rastreabilidade. | Executa transferência entre produtos, calcula valor de entrada com base no preco medio da derivacao destino, aplica centro de custo conforme regra fiscal, preserva a ligacao de rastreabilidade em campo customizado e atualiza a situação customizada do lote original e do lote destino. |
| `DiminuirApontamento` | Correção de quantidade para menor. | Aplicar a quantidade final desejada de um lote. | O SIGMA envia uma única solicitação com a chave do lote e a quantidade final. A regra ERP deve ratear as sequências, executar os acertos e gravar as pendências de componentes em `USU_TESTCMP` dentro da mesma transação; qualquer falha desfaz tudo. |
| `TratarBaixa` | Baixa de componente gerada pela tela Multi-OP (View 3), um registro por bobina de consumo debitada em cada apontamento. | Registrar no ERP o consumo de bobina de matéria-prima da máquina, incluindo o caso de repesagem (bobina retirada da máquina após já ter sido parcialmente consumida). | Não executa a baixa física: grava a pendência em `USU_TBXACMP` com `USU_SITPEN=1`, mesma tabela usada por `Apontamentos`/`ApontamentoComponente`. A quantidade enviada só é usada quando `repesagem=N` e `consumototal=N`; quando `repesagem=S`, a regra ignora a quantidade recebida e recalcula ela mesma como saldo atual do lote menos 1 (preserva saldo 1 para não duplicar repesagem); quando `consumototal=S`, usa todo o saldo atual do lote. Rejeita quando os dois indicadores vêm `S` ao mesmo tempo. A execução física continua na regra orquestradora 230, exatamente como as demais pendências de `USU_TBXACMP`. |

#### 6.2.2 Por que o envio de apontamento não baixa componente diretamente ?

No apontamento de OP, o SIGMA envia ao ERP a produção realizada. A regra Senior precisa lidar com um problema operacional: Foi realizado fisicamente a produção da OP que logo imediatamente pode ser usado para movimentações ou outras operações, porem pode ocorrer de nao ter estoque dos componentes e por conta disso o apontamneto retornaria erro e não seria efetivado no sistema.

Por isso, a regra de apontamento desliga temporariamente a baixa automática dos componentes da OP, executa o apontamento da produção e depois restaura a configuração original. Em seguida, grava pendências de baixa em `USU_TBXACMP`. Essas pendências representam os componentes que precisam ser baixados em etapa controlada, com validação de saldo, lote, depósito e regra de componente.

Esse desenho separa duas responsabilidades:

1. O apontamento da OP registra a produção do produto acabado.
2. A baixa de componentes consome os materiais associados, com controle posterior e rastreabilidade.

No `ApontamentoComponente`, a regra vai além: ela também recebe explicitamente o componente informado pela operação. Esse componente pode vir de leitura de lote ou de palete WMS resolvido previamente pelo SIGMA. A regra valida se existe saldo suficiente e grava a baixa desse componente como pendência, mesmo que ele não esteja marcado como componente de baixa automática original da OP.

#### 6.2.3 Por que existe a orquestração automática da baixa de componentes ?

A baixa de componentes foi separada em duas partes dentro do Senior. Os webservices de apontamento (`Apontamentos`, `AumentarApontamento`, `ApontamentoComponente` e `TratarBaixa`) não executam a baixa no mesmo momento em que apontam a OP. Eles apenas criam pendências em `USU_TBXACMP`, com `USU_SITPEN=1`, log de inclusão em `USU_LOGINC` e um identificador único `USU_IDEUNI` gerado por GUID.

`TratarBaixa` existe como ponto de entrada próprio, em vez de reaproveitar `ApontamentoComponente`, porque a origem do consumo é diferente na tela Multi-OP: não é o operador informando um componente lido por etiqueta ou palete, é o rateio de bobinas de matéria-prima da máquina calculado pelo SIGMA a cada apontamento de produção. O webservice recebe direto o resultado desse rateio — quanto foi debitado de cada bobina — e apenas grava a pendência; a mesma regra também sabe tratar o caso de **repesagem** (quando uma bobina que já teve consumo real é retirada da máquina antes de zerar), recalculando a quantidade a baixar a partir do saldo real do lote no ERP em vez de confiar no valor local, que pode estar defasado entre o momento da retirada física e o envio da baixa.

A regra orquestradora 230 é a responsável por consumir essa fila dentro do ERP. Ela segue o fluxo padrão da IPEL para processamentos automáticos: busca pendências com `USU_SITPEN=1`, respeita o nível de paralelismo configurado em `E000PDV` pela chave `CUSTOM.SENIOR.MAN.PRODUCAO.BAIXACOMPONENTEERP`, marca os registros como `USU_SITPEN=2` e envia os registros de forma assíncrona para o webservice interno `BaixaComponenteERP`, informando o `USU_IDEUNI` da pendência.

O `BaixarComponentes` é a regra do webservice interno. Ele recebe `BaixaComponenteERP.pendencias.ideUni`, busca a pendência correspondente em `USU_TBXACMP` por `USU_IDEUNI` e mantém a lógica de baixa: valida família, centro de custo, depósito, saldo e lote; libera o componente na OP e executa a baixa no ERP. Quando a pendência informa lote, esse lote é obrigatório: se não houver saldo nele, a baixa falha sem substituir por outro. Sem lote informado, a regra procura um lote disponível.

O resultado da baixa volta para a própria pendência:

- `USU_SITPEN=1`: pendente.
- `USU_SITPEN=2`: em processamento.
- `USU_SITPEN=3`: processado com sucesso.
- `USU_SITPEN=4`: erro.

Os dados do processamento ficam em `USU_DATPRC`, `USU_HORPRC` e `USU_USUPRC`. O log técnico do processamento é gravado pelo serviço interno `interno.custom.senior.logs.GravarLog`, com `CodPrc=3` e `IdePrc=BXC`. O campo adicional do log inclui origem, OP, componente e quantidade, permitindo rastrear qual pendência foi processada e qual foi o retorno.

Quando uma pendência precisa voltar para a fila, o fluxo de reabilitação de pendências da IPEL também trata esse processo. Para processos com `CodPrc=3` e `IdePrc=BXC`, a reabilitação volta a pendência de componente para `USU_SITPEN=1` e limpa `USU_DATPRC`, `USU_HORPRC` e `USU_USUPRC`, permitindo novo processamento pelo fluxo automático.

#### 6.2.4 Webservices de lote e situação customizada

Os webservices `MovimentarEstoque` e `TransferenciaProduto` tratam destinação de lote. Eles não existem apenas para mudar saldo; também atualizam a situação customizada do lote no ERP.

`MovimentarEstoque` e usado quando a operação muda depósito/local do mesmo produto e lote. E o caso de liberação normal e envio para Área Vermelha. Se origem é destino já forem equivalentes, a regra não precisa executar movimento, mas ainda pode atualizar a situação do lote.

`TransferenciaProduto` e usado quando a qualidade destina quantidade para refugo ou reclassificação. Nesse caso, a regra cria saída do produto/lote original e entrada no produto/derivacao/lote destino. Também preserva a ligacao de rastreabilidade em campo customizado, para que o rastreamento consiga reconstruir a cadeia mesmo após transferência/reclassificação.

#### 6.2.5 Análise do campo `acaoBotao` nos webservices de lote

O campo `acaoBotao` faz parte do contrato entre o SIGMA é os webservices customizados do Senior/Sapiens nos fluxos de lote. Ele não é apenas uma informação visual da tela. No LSP, esse campo e lido e usado para atualizar a situação customizada do lote em `E210DLS.USU_SITLOT`.

No Python, dois pontos montam esse campo:

| Origem Python | Serviço enviado | Valor de `acaoBotao` | Significado operacional |
|---|---|---|---|
| `setores/qualidade/views/consulta_lote.py` | `MovimentarEstoque` ou `TransferenciaProduto` | `A` | Liberação normal, refugo ou reclassificação a partir da consulta/liberação de lote. |

O envio dos registros de qualidade é centralizado em `consulta_lote.py`. O campo `acaoBotao=A` identifica a destinação final registrada pela qualidade. Antes da reunião, a tela `liberar_lotes.py` também pode mover o lote pendente para o depósito de Área Vermelha com `acaoBotao=V`; essa transferência física usa a transação interna padrão da filial e deixa a análise/destinação final para a reunião.

No `WebService Apontamento/MovimentarEstoque.lsp`, o JSON recebido é lido e o valor de `acaoBotao` e usado para gravar a situação do lote em `E210DLS.USU_SITLOT` depois da movimentação, quando não há erro de webservice.

No `WebService Apontamento/TransferenciaProduto.lsp`, o mesmo campo também é lido do JSON e usado para gravar `E210DLS.USU_SITLOT`, considerando o lote original e o lote transferido/reclassificado.

Conclusao técnica: o campo `acaoBotao` não deve ser removido do payload sem ajuste correspondente nos LSP, pois ele continua fazendo parte do contrato de situação do lote enviado ao Senior.

Como o retorno e tratado:

- O código procura tag `<waRetorno>`.
- Quando o conteúdo e JSON:
  - sucesso se `message == "OK"` ou `status == "OK"`.
- Quando não e JSON:
  - sucesso se texto contem `Processado com sucesso` ou variante.
- Falhas retornam o registro para pendente (`status=0`) com log.

### 6.3 WMS XC API

O WMS recebe informações de lote e ajuste de estoque por API HTTP JSON. Diferente do ERP SOAP, aqui o envio é feito para endpoints REST/HTTP do WMS XC.

O SIGMA não envia todos os tipos de WMS do mesmo jeito. Quando a qualidade libera um lote novo para armazenamento o envio normalmente é `novo_lote`, que cria/recebe o lote no WMS. Quando na área vermelha apenas transforma um lote já existente manda `novo_lote` e `ajuste` no original avaliado.
Quando o apontamento de componente consome um palete WMS, o envio normalmente é `ajuste`, que acerta saldo do palete/lote. Na tela Multi-OP (View 3, ver 8.2.1), cada baixa de bobina integrada no ERP também gera um `ajuste`, com a quantidade sendo o novo saldo real do lote — não um valor fixo.

Antes de enviar, a aplicação grava uma pendência local. Essa pendência é o controle de auditoria: informa o lote, palete, quantidade, produto, derivacao, local WMS, status e log do retorno.

A fila respeita ordem por lote: antes de reservar uma pendência para envio, o sistema verifica se existe outra pendência mais antiga do mesmo `(empresa, lote)` ainda pendente ou em processamento; se existir, a mais nova fica bloqueada e não é enviada, mesmo que o worker automático ou o botão manual de envio tentem processá-la. Essa regra existe porque nem todo `ajuste` é idempotente: os ajustes de baixa de componente da View 3 carregam saldos diferentes a cada envio, então processar fora de ordem poderia regredir o saldo do WMS para um valor desatualizado. Na tela `/setores/qualidade/integracao-wms/`, uma pendência bloqueada por essa regra aparece como **Bloqueado (lote)**; uma pendência vinculada a uma reunião de área vermelha ainda aberta aparece como **Bloqueado (reunião)** — ambas em azul, mesma cor usada para bloqueio por ordem de fila nas demais telas de log do sistema.

Base:

```text
WMS_XC_API_URL
```

Endpoints:

| Tipo local | Endpoint | Objetivo |
|---|---|---|
| `novo_lote` | `rec_ska` | Receber/criar lote no WMS. |
| `ajuste` | `ajuste_estoque` | Ajustar saldo de lote/palete existente. |

Payload `novo_lote`:

| Campo | Origem |
|---|---|
| `WHSEID` | Fixo `WMWHSE1` |
| `STORERKEY` | Fixo `00001` |
| `RECEIPTKEY` | `<origem>-<op>` |
| `TOLOC` | Local WMS |
| `SKU` | Produto-derivacao |
| `QTYRECEIVED` | Quantidade |
| `TOID` | Palete/lote |
| `LOTTABLE01` | Lote |
| `USER` | Usuário WMS do ambiente |

Payload `ajuste`:

| Campo | Origem |
|---|---|
| `ARMAZEM` | Fixo `WMWHSE1` |
| `LOTE` | Lote da pendência |
| `PALETE` | Palete da pendência |
| `QTD_AJUSTADA` | Quantidade |
| `SKU` | Produto-derivacao |
| `USUARIO` | Usuário WMS do ambiente |
| `MOTBLOQ` | Fixo `""` (motivo do bloqueio; ainda não configurável) |
| `FLAGBLOQ` | Fixo `"0"` (desbloqueia a quantidade ajustada) |

`MOTBLOQ`/`FLAGBLOQ` fazem parte do contrato de bloqueio de qualidade do
WMS: quantidade que cai na área vermelha deve ficar bloqueada até a
qualidade liberar, e `FLAGBLOQ = "0"` é o valor que desbloqueia a
quantidade ajustada. O SIGMA ainda não decide bloqueio nem expõe motivo
configurável — os dois campos são enviados sempre com o mesmo valor fixo,
em todo `ajuste_estoque`, qualquer que seja o fluxo de origem (componente,
baixa de bobina View 3, área vermelha).

Retorno:

- Sucesso se HTTP `200` ou `201` e corpo não contem `Erro`.
- Falha se status diferente ou se corpo contem `Erro`.
- Falha retorna a pendência para `status=0`.

### 6.4 WMS via DBLINK Oracle

O DBLINK é usado quando a informação do WMS precisa ser consultada a partir do Oracle ERP. Isso evita que a aplicação abra uma conexão direta separada para algumas leituras específicas e aproveita a visão já exposta no ambiente Oracle.

Usos principais:

- Importação de paletes para `USU_TPALWMS`.
- Resolução de local WMS na área vermelha, isso é necessario para saber se o lote ja existe no WMS e se existe para qual local os lotes a partir dele devem ser gerados tambem.

Objeto principal:

```text
wmwhse1.v_XCLotxLocxId_Lottables@SQLDBLINK
```

### 6.5 Oracle Alchemy

O Alchemy e usado como apoio de qualidade e produção. Ele não e a base de estoque nem de OP; sua funcao e fornecer dados de análise/bobina que complementam a decisão operacional.

Usado em:

- Liberação de lote.
- Área vermelha.
- Rastreamento de lote.

Tabela principal:

```text
bobinas
```

Campos usados:

- `codmaquina`.
- `codbobina`.
- `flagproducao`.
- `observacao`.

#### 6.5.1 Coleta HTTP de Telemetria

O coletor de Telemetria consulta cada `FonteColetaHTTP` uma vez e interpreta a
resposta como um objeto JSON. O bloco de cada recurso é localizado pela chave
exata de `Recurso.codigo`; dentro dele, cada valor é localizado pela
`Sensor.chave_origem`. Recurso ausente na resposta é ignorado e sensor ausente
no bloco não interrompe a coleta dos demais sensores encontrados. As chaves não
são posições nem texto extraído de HTML.

Além dos sensores cadastrados, o coletor calcula a bobina atual dos recursos
(MP-III, MP-IV, MP-V) a partir das chaves `contagemBobinas` e
`estouroDeContagem` do mesmo JSON: `numero_bobina = estouroDeContagem * 32000 +
contagemBobinas`, gravado em `Recurso.bobina`. Esse cálculo roda para qualquer
bloco cujo topo bata com um `Recurso.codigo` existente, independente de
`Sensor`/`SensorRecurso` cadastrado — não precisa de vínculo manual nem
aparece nas telas de telemetria. Falta de uma das duas chaves no bloco é
ignorada sem erro.

A URL não aceita credenciais, query string ou fragmento e precisa usar `http`
ou `https` em host ou `host:porta` presente em `TELEMETRIA_HOSTS_PERMITIDOS`.
O serviço revalida a URL antes de cada coleta, não segue redirects, limita
timeout, pausas e tamanho de resposta e não persiste a resposta bruta. Falhas
são registradas internamente com mensagem genérica no painel, sem exibir
credenciais ou URL completa.

##### Legenda atual de sensores

A referência operacional atual é a planilha
[`sensores_maquinas (2).xlsx`](../sensores_maquinas%20%282%29.xlsx). As tags
abaixo são chaves JSON: devem permanecer exatamente como estão, inclusive
`Produção`, `diamentroBobina` e `satusInicioBobina`. Renomeá-las exige alteração
coordenada no produtor da resposta e nos cadastros de sensores do SIGMA.

Os limites indicados são referências operacionais da planilha; não representam,
por si só, validações já aplicadas pelo código.

Para todo sensor do tipo Booleano, o coletor aceita tanto `0`/`1` quanto
variações textuais (`"sim"`/`"não"`, `"yes"`/`"no"`, `"on"`/`"off"`,
`"true"`/`"false"`, case-insensitive) e persiste o valor booleano convertido;
qualquer outro valor recebido levanta `ErroColetaTelemetria`. As descrições da
tabela indicam o significado operacional de cada estado.

| Tag JSON | Tipo SIGMA | Unidade / referência operacional | Significado |
|---|---|---|---|
| `contagemBobinas` | Inteiro | Limite: 32000 | Contagem de bobinas. |
| `estouroDeContagem` | Inteiro | Limite: 32000 | Estouro da contagem de bobinas. |
| `velocidadeYankee` | Decimal | m/min; limite: 2000 | Velocidade do Yankee. |
| `velocidadeEnroladeira` | Decimal | m/min; limite: 2000 | Velocidade da enroladeira. |
| `valvulaControle` | Decimal | m³/h; limite: 70 | Vazão da válvula de controle. |
| `pesoBalanca` | Decimal | kg; 2 casas decimais; limite: 5000 | Peso informado pela balança. |
| `diamentroBobina` | Decimal | mm; limite: 5000 | Diâmetro da bobina. |
| `toneladaHora` | Decimal | ton/h; limite: 100 | Taxa de produção. |
| `pressaoYankee` | Decimal | Bar; limite: 15 | Pressão do Yankee. |
| `statusbombaMistura` | Booleano | `0` desligado; `1` ligado | Estado da bomba de mistura. |
| `sensorQuebra` | Booleano | `0` folha não rompida; `1` folha rompida | Indicação de quebra da folha. |
| `statusPrensa` | Booleano | `0` afastado; `1` encostado | Estado da prensa. |
| `statusTrocaRaspaCrepe` | Booleano | `0` afastado; `1` encostado | Estado da troca da raspa de crepe. |
| `satusInicioBobina` | Booleano | `0` início; `1` fim | Estado de início ou fim da bobina. |
| `spDiamentroBobina` | Decimal | mm; limite: 5000 | Setpoint de diâmetro da bobina. |
| `statusBombaGramatura` | Booleano | `0` desligado; `1` ligado | Estado da bomba de gramatura. |

### 6.6 LDAP / Active Directory

O LDAP integra o SIGMA com o ambiente corporativo de usuários. Na prática, isso reduz a necessidade de manter senhas separadas dentro do SIGMA é permite que usuários usem a credencial de rede.

O grupo requerido `GP_Sigma` funciona como uma barreira de entrada: mesmo que o usuário exista no AD, ele precisa pertencer ao grupo autorizado para acessar o sistema.

Configuração:

- Servidor LDAPS: `ldaps://DC01.indaialpapel.com.br:636`.
- Dominio: `indaialpapel.com.br`.
- Grupo requerido: `GP_Sigma`.
- Certificado CA em `/opt/SIGMA/certs/ca_indaialpapel.pem`.

Comportamento:

- Backend LDAP vem antes do backend Django.
- Usuários LDAP podem ser criados automaticamente.
- Nome, sobrenome e e-mail são atualizados pelo AD.

### 6.7 E-mail Microsoft 365

O SIGMA usa o Microsoft Graph para notificações, principalmente no módulo de manutenção. Ele permite que abertura, atualização ou mudança de status de chamados e ordens de serviço gerem comunicação por e-mail para responsáveis e envolvidos, usando a identidade da aplicação Microsoft 365 em vez de autenticação SMTP por senha.

Configuração:

- Backend Django: `SIGMA.mail_backends.MicrosoftGraphEmailBackend`.
- Autenticação: client credentials OAuth 2.0 contra Microsoft Entra ID.
- Remetente: `sigma@ipel.ind.br` (`MICROSOFT_GRAPH_MAIL_SENDER`).
- Variáveis obrigatórias: `MICROSOFT_GRAPH_TENANT_ID`, `MICROSOFT_GRAPH_CLIENT_ID`, `MICROSOFT_GRAPH_CLIENT_SECRET` e `MICROSOFT_GRAPH_MAIL_SENDER`.
- Usado principalmente por manutenção para notificar chamados e ordens de serviço.

Os valores ficam exclusivamente no arquivo de ambiente local ou em `/etc/sigma/sigma.env` em produção. A aplicação precisa ter permissão de aplicativo `Mail.Send` no Microsoft Graph, e a caixa remetente deve existir no tenant.

Erros do Microsoft Graph (autenticação ou envio) são propagados com o corpo da resposta HTTP incluído na mensagem da exceção (não só o status code), para facilitar diagnóstico — por exemplo `MailboxNotEnabledForRESTAPI` quando a caixa remetente está inativa, soft-deleted ou hospedada on-premise.

A tela `/utilitarios/` (`accounts/views/utilitarios.py`, template `templates/accounts/utilitarios.html`) tem uma seção de teste de envio de e-mail: qualquer usuário autenticado digita um endereço e recebe na própria tela o retorno do envio (sucesso ou o erro detalhado do backend). Rota: `POST /utilitarios/email/enviar/` (`enviar_email_teste`).

### 6.8 Retornos, status e tratamento de erro das integrações

Esta seção explica como o SIGMA decide se uma integração deu certo ou não. Isso é importante porque o sistema conversa com tecnologias diferentes: SOAP, JSON HTTP e Oracle. Cada uma retorna erro de um jeito.

O principio geral e: se a resposta externa não comprova sucesso, o SIGMA não marca o registro como integrado. Ele registra o erro no log e deixa o registro pendente para tentativa futura.

As filas usam status numerico para simplificar filtros e reprocessamento. O usuário ve isso nas telas como pendente, integrado ou processando. Na prática, a fila e o mecanismo que impede perda de informação. Quando uma ação precisa ser enviada ao ERP ou WMS, o SIGMA guarda um registro local. Esse registro pode estar pendente, processando, integrado ou em outro estado de controle.

Padrão geral:

- Sucesso grava `status=1`.
- Falha grava `status=0` e registra log.
- Em processamento usa `status=2`.
- Exclusão lógica ou bloqueio pode usar `status=3` em alguns modelos.

No SOAP ERP, o retorno pode vir com um JSON dentro de `<waRetorno>` ou com texto simples. Por isso, o SIGMA tenta interpretar das duas formas. Quando encontra um retorno OK, marca sucesso. Quando não encontra, considera falha. O sucesso pode ser indicado por `message == "OK"`, `status == "OK"` ou por texto equivalente a processamento concluído.

No WMS, o HTTP pode retornar 200 ou 201 mesmo quando o corpo indica erro. Por isso, o SIGMA não olha apenas o status HTTP; ele também verifica se o corpo contem a palavra `Erro`. Um retorno HTTP tecnicamente bem sucedido significa apenas que o WMS respondeu; não significa, sozinho, que o lote foi recebido ou que o ajuste foi aceito pela regra do WMS.

Nas consultas Oracle, a falha normalmente impede a continuidade da operação, porque o Oracle e fonte de verdade para saldo, lote, OP e movimentos. Em tela, a falha aparece como mensagem ao usuário. Em worker, o erro fica no status do serviço ou no log da fila.

Para reduzir falhas por texto mal decodificado, o SIGMA usa `producao.utils.codificacao` nos pontos de integração. O módulo fornece:

- `get_response_text`: lê respostas HTTP de SOAP/WMS/contadores web respeitando a codificação detectada ou fazendo fallback seguro.
- `safe_str`: transforma exceções e mensagens em texto seguro antes de salvar log de fila, status de service ou erro operacional.

Esse utilitário é usado nos fluxos SOAP ERP, WMS, consulta/liberação de lotes, logs de apontamento, logs de componentes, importação de números de bobina e status dos services. A finalidade não e mudar a regra de negócio, mas preservar o retorno real recebido das integrações e impedir que um problema de codificação esconda a causa operacional da falha.

Quando a falha acontece durante uma ação de tela, o usuário recebe uma mensagem de erro e o registro não deve ser tratado como concluído. Quando a falha acontece em uma fila, o registro volta para pendente ou permanece em estado controlado para nova tentativa, conforme o ponto em que a execução parou.

Esse comportamento é comum aos fluxos de apontamento, componente, liberação de lote e WMS: o SIGMA só encerra a pendência quando existe retorno externo suficiente para considerar a operação concluída. Caso contrario, preserva a rastreabilidade local para suporte, correcao ou reenvio.

### Redução de apontamento e pendência ERP de estorno

O SIGMA envia uma única quantidade final e não possui fila local de estorno. A regra `DiminuirApontamento.lsp` busca as sequências do lote, reduz da mais nova para a mais antiga, chama `Acertar` para cada linha alterada e grava em `USU_TESTCMP` uma pendência por componente. Acerto, pendências e a marcação de exclusão do lote, quando solicitada, pertencem à mesma transação; qualquer falha chama `DesfazerTransacao`.

`USU_TESTCMP` usa `USU_IDEUNI` gerado por GUID e inicia em `USU_SITPEN=1`. O componente proporcional é calculado pela redução da própria sequência; o componente fixo (`TipQtd=F`) só gera pendência quando essa sequência é zerada. Reenviar a mesma quantidade final é sucesso sem nova pendência. A etapa seguinte, ainda pendente no ERP, é o job que selecionará essas linhas e chamará o `EstornaComp` já existente.

---

*Verificado contra o código em 2026-09-02.*
