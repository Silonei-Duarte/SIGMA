---
titulo: Fluxos de negócio
ordem: 9
---

## 8. Fluxos de negócio

### 8.1 Sequenciamento de produção

O sequenciamento é o módulo que organiza as ordens de produção vindas do ERP em uma fila operacional por recurso. Ele não substitui o ERP como origem da OP; ele cria uma visão local de prioridade e distribuição para a fábrica trabalhar no curto prazo.

Consultar, exportar, consolidar e distribuir automaticamente usam apenas centros
da empresa da filial do usuário não-staff. A consolidação valida toda a carga e
os recursos do centro antes de substituir a sequência local, dentro de transação;
uma carga inválida não apaga o sequenciamento já salvo. Staff conserva escopo global.

O usuário seleciona empresa e centro de recurso. O sistema consulta o ERP para listar OPs liberadas, em andamento ou aptas para produção, considerando roteiro, operação, produto, derivação, quantidade prevista, tempo previsto e saldo de estoque. A tela permite distribuir essas OPs entre recursos do centro e depois consolidar a ordem planejada no banco local.

O sequenciamento automático prioriza a necessidade de estoque: calcula `QTDEST - QTDRES - ESTMIN`, ordena primeiro as OPs com menor saldo disponível e usa o tempo de operação como desempate. Depois distribui a proposta entre os recursos com menor carga acumulada. Essa proposta só vira oficial quando o usuário consolida. Enquanto não consolida, a distribuição é apenas simulada na tela.

A consulta trabalha com produto e derivação da OP. `E900QDO.PROORI = 'S'` mantém as OPs com derivação definida; `E900QDO.QTDPRV` informa a quantidade prevista; e a descrição exibida reúne produto e derivação. Para cada par produto/derivação, o sistema soma todos os depósitos de `E210EST` e obtém estoque, reservado, estoque mínimo e máximo. Esses resultados ficam em cache durante a consulta para não repetir a busca do mesmo produto/derivação.

A tela ERP exibe Origem, OP, Produto, Derivação, Descrição, quantidade prevista, tempo, estoque, reservado, estoque mínimo e máximo. Estágio, sequência de roteiro e operação permanecem ocultos na tela porque são necessários para consolidar a sequência. A lista de recursos mostra `OP | Origem | Produto | Derivação | Descrição`. A exportação Excel segue essas colunas, formata o tempo como `Xh Ymin` e inclui Recurso Consolidado e Ordem Consolidada.

| Tabela Oracle | Uso no sequenciamento |
|---|---|
| `E900COP` | Cabeçalho da OP: origem e número da OP. |
| `E900QDO` | Produto, derivação, quantidade prevista e filtro de origem do produto. |
| `E900OOP` | Estágio, sequência, operação e tempo do roteiro. |
| `E075PRO` e `E075DER` | Descrições do produto e da derivação. |
| `E725CRE` e `E083ORI` | Centro de recurso e origem da OP. |
| `E210EST` | Estoque, reservado, estoque mínimo e máximo por depósito. |

Fluxo:

1. Usuário acessa a tela de sequenciamento.
2. Sistema carrega empresas/centros conforme permissão e filial.
3. Ao consultar um centro, busca OPs no Oracle ERP.
4. Usuário distribui OPs nos recursos ou usa sequenciamento automático.
5. Consolidação apaga o sequenciamento anterior do centro e grava novo sequenciamento local.
6. Exportacao gera Excel com dados do ERP e recurso/ordem consolidada.

### 8.1.1 Calendário de OPs

O **Calendário de OPs**, no menu **Setores > PCP**, é uma visão de consulta do planejamento e da execução dos estágios das OPs no ERP. Cada evento representa um estágio da OP, identificado na linha por OP, produto-derivação e abreviatura do recurso (`E725CRE.ABRCRE`). As cores distinguem eventos que coincidem ou se encostam no período; não indicam situação da OP.

Cada ponta do evento usa a data real do estágio quando ela é válida (`E900EOP.DTRINI` para início e `E900EOP.DTRFIM` para fim); quando uma dessas datas não existe, somente aquela ponta usa a respectiva previsão (`DTPINI` ou `DTPFIM`). OPs finalizadas (`F`) são limitadas ao período entre o primeiro dia do mês anterior e o fim da visualização, evitando que a seleção traga todo o histórico do ERP.

Os filtros de máquina, origem, produto-derivação e situação são de múltipla seleção; quando algum valor está selecionado, o respectivo seletor fica azul. O filtro de produto-derivação preserva a distinção entre derivação nula e derivação composta somente por espaço, pois ambas existem no ERP. As situações disponíveis são: `A` andamento, `L` liberada, `E` explodida, `R` reabilitada e `F` finalizada; as quatro primeiras vêm selecionadas inicialmente. As linhas do calendário exibem o percentual, usam fonte ampliada e a área do calendário possui rolagem horizontal; abaixo do nome do mês, o rótulo informa que `%` é o percentual comprometido da OP.

Ao posicionar o mouse sobre qualquer parte do evento, o detalhe mostra situação, origem, estágio, máquina, período previsto e real, produto-derivação com suas descrições, quantidade prevista, quantidade já produzida, quantidade reservada e os pedidos reservados. A reserva é obtida em `USU_TRESPED`, filtrada por `USU_CODEMP` e `USU_CODFIL` da filial do usuário e por `USU_NUMORP` da OP; `USU_QTDRES` é somada por `USU_NUMPED` e no total comprometido.

O comprometimento é calculado somente quando o fim previsto do cabeçalho da OP (`E900COP.DTPFIM`) é igual ou posterior à data atual e o fim real (`E900COP.DTRFIM`), quando informado, ainda não passou. Para OP com fim previsto ou real passado, o calendário não mostra percentual nem dados de comprometimento no tooltip e não abre o modal. Ao clicar em uma OP elegível, o modal **Detalhamento do comprometimento** apresenta o estoque por depósito da `E210EST`, todas as OPs abertas de produção da `E900QDO`, todas as OPs abertas de consumo da `E900CMO` e as reservas por pedido da `USU_TRESPED`. Cada reserva também mostra a previsão de estoque do pedido em `E120PED.USU_PRVEST`, vinculada por empresa, filial e número do pedido. O estoque ignora os depósitos `01.25`, `AV.01`, `05.14`, `01.14`, `01.23`, `01.DV`, `C1.25`, `OP.25`, `P01.01`, `P01.02`, `P01.03` e `01.30`. As tabelas de produção e consumo exibem origem, número, situação, fim previsto, quantidade prevista, realizada e pendente; as fórmulas do resumo identificam quais registros entram em cada intervalo pela data de fim prevista.

Para as origens configuradas em **Origens área vermelha** nos Parâmetros da Filial do usuário, o modal mostra três grupos de fórmulas por produto-derivação: **Comprometido até a data de corte**, **Comprometido após a data de corte** e **Comprometido TOTAL**. Em cada grupo são mostrados, em texto, `Estoque + Produção pendente = Disponível`, `Consumo pendente + Reservas = Comprometido` e `Disponível - Comprometido = Saldo`, acompanhado do percentual que o comprometido representa do disponível. Nas demais origens, o comprometimento continua sendo exclusivamente a reserva da própria OP.

O preenchimento da faixa do evento mostra o percentual de **Comprometido após a data de corte**. Para as demais origens, ele é calculado como `quantidade reservada da OP / quantidade prevista`. Para produtos cujas origens estejam configuradas em **Origens área vermelha** nos Parâmetros da Filial, a data de corte é o fim previsto do cabeçalho da OP avaliada (`E900COP.DTPFIM`), mesmo que o evento esteja sendo desenhado por datas reais. Produção pendente é `E900QDO.QTDPRV - E900QDO.QTDRE1`; consumo pendente é `E900CMO.QTDPRV - E900CMO.QTDUTI`; ambos consideram somente OPs `A`, `E`, `L` e `R`, e nunca ficam negativos. O reservado é a soma de `USU_TRESPED.USU_QTDRES` por empresa, filial, produto e derivação, sem filtro por data.

Os três grupos não repetem OPs entre o cálculo até o corte e o cálculo posterior: **até a data de corte** parte do estoque atual, usa produção com `E900COP.DTPFIM` entre a data atual e a data de corte, inclusive, e consumo com `DTPFIM` menor ou igual à data de corte; **após a data de corte** parte do saldo obtido no grupo anterior e usa somente produção e consumo com `DTPFIM` maior que a data de corte, somando as reservas; e **TOTAL** usa o estoque atual, toda a produção e todo o consumo abertos, sem filtro de data, somando as reservas. A tabela continua exibindo todas as OPs abertas: ao lado do fim previsto, o triângulo vermelho aponta registros até o corte e o verde aponta registros posteriores; produção com fim anterior à data atual permanece listada, mas não recebe marcador nem entra no cálculo até o corte. Uma OP que começa na data de corte e termina depois dela entra no grupo posterior, pois a classificação considera somente seu fim previsto. A parte comprometida da barra mantém a cor da OP e o saldo restante usa a mesma cor misturada com 70% de branco. Para OP finalizada, o percentual não é exibido na linha.

| Tabela Oracle | Uso no Calendário de OPs |
|---|---|
| `E900COP` | Cabeçalho e situação da OP. |
| `E900EOP` | Estágio e datas previstas/reais. |
| `E900OOP` e `E725CRE` | Recurso do estágio e sua abreviatura. |
| `E093ETG` e `E083ORI` | Descrições de estágio e origem. |
| `E900QDO`, `E075PRO` e `E075DER` | Produto, derivação, quantidades e descrições. |
| `USU_TRESPED` | Pedidos e quantidade reservada para a OP. |

### 8.1.2 Importação automática do sequenciamento do ERP

A ideia de longo prazo é o PCP sequenciar as OPs diretamente no SIGMA (8.1). Como essa migração leva tempo, o worker `sincroniza_ops_encerradas` (9.1) ganhou um segundo passo, executado a cada ciclo depois da limpeza de OPs encerradas: para cada centro de recurso com ao menos um recurso ativo, ele verifica se o ERP tem alguma OP elegível (`E900COP.SITORP IN ('L','R','A')`) com prioridade (`NUMPRI`) preenchida naquele centro (`E900OOP.CODCRE`). Se tiver, o sequenciamento do ERP **sempre prevalece** e substitui o que estiver salvo localmente para os recursos ativos daquele centro. Se o ERP não tiver nenhuma OP com prioridade para o centro — por exemplo, porque o PCP já passou a sequenciar aquele centro manualmente pela tela do SIGMA e parou de preencher `NUMPRI` no ERP — o worker não altera nada, preservando o sequenciamento manual.

`NUMPRI = 0` é o padrão do ERP para "sem prioridade definida"; a prioridade real começa em `1`. Por isso, ao montar o sequenciamento local, as OPs com prioridade real (`NUMPRI >= 1`) mantêm seu próprio valor — só sendo empurradas para a próxima posição livre em cascata quando colidem com a anterior já usada, o que também desfaz empates entre elas — enquanto as OPs com `0` (ou nulo) recebem uma ordenação sequencial **depois da última prioridade real usada**. Por exemplo, prioridades reais `2, 5, 50, 99` mais três OPs em `0` resultam em `2, 5, 50, 99, 100, 101, 102` — nunca `1, 2, 3, ...`. Em ambos os grupos, o desempate é feito por tempo de operação (`E900OOP.TMPTPR`) e, se também empatar em tempo, pelo número da OP (menor primeiro), para o resultado não variar de um ciclo para o outro por causa da ordem, não garantida, de retorno do Oracle.

Como o ERP identifica apenas o centro de recurso da operação (`E900OOP.CODCRE`), não um recurso específico dentro dele, essa importação replica o mesmo sequenciamento para **todos** os recursos ativos do centro — aceitando que recursos do mesmo centro recebam as mesmas OPs, já que o ERP não tem como distinguir qual recurso individual deveria receber cada uma.

Antes de apagar e regravar, o worker compara o sequenciamento que resultaria dessa importação com o que já está salvo (mesma OP, estágio, sequência de roteiro e ordenação, para todos os recursos ativos do centro); se for idêntico, pula esse centro sem tocar no banco. Se qualquer recurso do centro estiver diferente do esperado — por exemplo, um recurso novo ainda sem sequenciamento, ou um dado divergente —, o worker regrava **todos** os recursos daquele centro juntos, para manter a cópia idêntica entre eles.

### 8.2 Apontamentos de produção

O apontamento de OP é o fluxo usado para registrar produção realizada, refugo, lote, bobina, operador, recurso e horário de movimento. O SIGMA atua como camada operacional entre a tela de fábrica e o ERP: primeiro grava uma evidencia local do apontamento e depois tenta integrar essa evidencia ao ERP por webservice.

Esse desenho evita perda de informação quando o ERP ou a rede falha. Mesmo se o envio ao ERP não concluir, o registro local permanece com status pendente e pode ser reenviado automaticamente pelo worker ou manualmente pela tela de logs.

Ao entrar no apontamento por uma OP/código de barras, o SIGMA não usa uma tela fixa para todos os recursos. A tela base identifica o recurso da OP e consulta o campo `view_id` do cadastro do recurso. Esse campo aparece na aba OEE do recurso, mas hoje sua função operacional é selecionar a versão da tela de apontamento. Se o recurso estiver configurado com `1`, o sistema carrega a versão `apontamentos_v1`; se estiver configurado com `2`, carrega `apontamentos_v2`; se estiver configurado com `3`, carrega `apontamentos_v3`, a versão Multi-OP descrita em 8.2.1. Os demais campos dessa aba permanecem cadastrados para uso futuro do módulo de OEE.

Em todas as versões, empresa, centro, recurso e código de barras são resolvidos
no conjunto visível da filial. Um valor forjado de outra empresa não permite
consultar nem alterar OP, recurso, bobina ou parada externa.

Os seletores de centro de recurso e recurso dessas telas (base, v1, v2 e v3) só listam recursos com `Ativo = Sim`; um centro de recurso sem nenhum recurso ativo vinculado também fica oculto do seletor de centro. Isso permite cadastrar centro de recurso e recurso apenas para fins de parametrização — por exemplo, para configurar o local de área vermelha de um equipamento que ainda não aponta produção no SIGMA — sem que esse cadastro apareça como opção de apontamento. O mesmo campo `Ativo` também é usado pela coleta de telemetria (ver 6.2) e pelo sequenciamento/status de recursos: um recurso inativo não é apontado, não é sequenciado e não tem telemetria coletada, mesmo que tenha sensores e configuração de coleta ativos.

O envio ao webservice `Apontamentos` existe para efetivar a produção no ERP e, ao mesmo tempo, manter controle sobre a baixa de componentes. A regra Senior aponta a OP, evita duplicidade, controla início/fim quando necessário, desliga temporariamente a baixa automática da OP e grava pendências de componentes para baixa posterior. Assim, o produto acabado e apontado no ERP sem perder o controle dos componentes que precisam ser consumidos com lote, saldo e rastreabilidade.

Na tela `apontamentos_v1`, o operador escolhe o número de bobina numa lista construída a partir da leitura atual de `Recurso.bobina` (calculada pela coleta de telemetria, ver 6.5.1 em `07-integracoes-externas.md`) e da última bobina já apontada localmente ou no ERP: a lista mostra, em ordem decrescente, até 100 números entre a bobina atual e um a mais que a última já registrada. Quando a bobina atual está atrás ou igual à última já apontada — sinal de sensor/contador com erro, por exemplo após reset do contador na máquina —, a lista fica vazia e a tela oferece **"Sem número de bobina"** em vez de repetir um valor que a validação de duplicidade recusaria. Esse apontamento é permitido, para não bloquear a produção por falha de sensor: `Apontamento.bobina` é gravado como `NULL`, valor que as demais consultas de última bobina (aqui e no cálculo da própria lista) já ignoram pelo filtro `bobina__isnull=False`.

Quando uma correção manual de lote tem resultado desconhecido após a chamada ao
ERP, ela entra em **conciliação** e bloqueia nova tentativa para o mesmo
empresa/lote. Usuário autorizado confirma a situação real, registra observação
auditável e libera a próxima tentativa.

#### 8.2.1 Apontamento Multi-OP (View 3, rebobinadeira)

A View `3` existe para um tipo de máquina que as versões `1` e `2` não conseguem representar bem: a rebobinadeira. Ela pode ter várias OPs acopladas ao mesmo tempo, porque o tempo de máquina precisa ser dividido entre elas, mas a produção nunca é apontada em mais de uma OP ao mesmo tempo — o operador pesa o lote de uma OP, tira da máquina, depois pesa o da próxima. Por isso a tela separa duas responsabilidades que nas versões anteriores eram uma só: **acoplamento de OP** (controla tempo, pode ter várias abertas) e **apontamento de produção** (sempre de uma OP por vez).

Acoplar uma OP não é livre: ela só entra se tiver ao menos um componente em comum — mesma combinação de produto e derivação — com todas as OPs já acopladas ao recurso. A razão é que o consumo de bobina de matéria-prima é **da máquina**, não da OP: todas as OPs acopladas compartilham as mesmas bobinas em consumo, então misturar OPs com componentes incompatíveis geraria baixa de matéria-prima errada para uma delas. A View `3` também não usa o botão de desacoplar OP das demais versões: o encerramento de uma OP acontece pelo próprio fluxo de alocação de bobina, sem depender de uma ação manual separada.

**Consumo de bobina como fila.** Cada bobina alocada ao recurso fica em `BobinaConsumoRecurso`, em um de dois estados: `EM_CONSUMO` (ativa, sendo debitada agora) ou `EM_FILA` (reserva, entra automaticamente quando uma bobina em consumo esgota). Quando o operador pesa um lote, o peso é dividido em fatias iguais pelo número de bobinas em `EM_CONSUMO` — se há duas bobinas em consumo, cada uma recebe metade do peso pesado, independente de qual OP foi apontada. Se uma fatia não cabe inteira na bobina correspondente, o restante daquela mesma fatia é emendado com bobinas da fila, na ordem, encadeando quantas forem necessárias; uma bobina da fila nunca cobre mais de uma fatia no mesmo apontamento, para que o rastreamento de qual bobina abasteceu qual pedaço do peso pesado não se perca.

**Confirmação de consumo real antes de debitar.** O cálculo de quanto cada bobina teria que fornecer é só uma estimativa teórica — uma bobina física pode render mais ou menos do que esse cálculo prevê. Por isso, o cálculo do rateio acontece em duas fases dentro da mesma transação: primeiro monta um plano teórico (sem gravar nada) e verifica quais bobinas esse plano zeraria; se houver alguma, a transação é abortada sem debitar nada (só houve leitura com `select_for_update`) e a tela volta pedindo confirmação, com a lista de bobinas pendentes guardada na sessão do recurso — o operador reenvia o mesmo apontamento junto com a resposta de cada bobina, sem precisar repetir peso, refugo ou OP selecionada. Para cada bobina pendente, o operador escolhe entre três opções: confirmar que consumiu tudo e a cadeia deve emendar com a próxima bobina da fila (só aparece quando o plano já previa essa próxima bobina); confirmar que consumiu tudo mas sem emendar, parando a cadeia ali — a próxima bobina da fila que seria usada fica intacta, sem debitar nada dela; ou informar que ainda resta um peso estimado, caso em que o sistema debita só a diferença entre o saldo teórico e o valor informado, nunca um valor negativo — se a bobina rendeu mais do que o previsto, nenhum débito é gerado para ela e ela sequer aparece na `BaixaComponente` gerada. Essa confirmação é a proteção de negócio para que uma OP, ao final, não apareça como tendo consumido mais bobinas do que era teoricamente esperado — o operador sempre tem a palavra final sobre o que realmente saiu da máquina. Uma bobina que zera de verdade (seja pelo plano teórico direto, seja por confirmação do operador) é removida da tabela de bobinas em consumo, e não apenas marcada como finalizada — o controle de repesagem, que é o único motivo para preservar histórico de um lote já retirado, é feito por uma tabela separada (`BaixaComponente`), então o registro de consumo em si não precisa continuar existindo depois de esgotado.

**Geração de `Apontamento` e lote.** Depois que o consumo de bobina é resolvido, o peso pesado é dividido pelas "Bobinas planejadas" da OP (`E900COP.USU_QTDBOB`) e cada parte gera um `Apontamento` com lote próprio, incrementado de `Empresa.loteatual` — mesma regra de geração de lote da v1. A diferença é que na v3 não existe número de bobina informado pelo operador: cada bobina cortada já é o próprio lote, então `Apontamento.bobina` fica sempre vazio. Quando a OP não tem `USU_QTDBOB` cadastrado no ERP, o sistema usa `1` como fallback em vez de bloquear o apontamento, para não deixar uma OP mal cadastrada impedir a produção. Refugo sem produção é permitido, condicionado ao parâmetro `Aponta Refugo` do recurso, do mesmo jeito que nas demais versões. Antes de gravar, o sistema confere no ERP se o estágio ainda existe na rota daquela OP — a mesma checagem feita na v1 — porque o estágio salvo no acoplamento pode ter ficado desatualizado se o roteiro for alterado depois.

Todo esse fluxo — rateio de consumo, confirmação do operador quando necessário e geração dos `Apontamento` — roda dentro de uma única transação: se algum `Apontamento` não puder ser gerado, o débito de bobina já calculado é desfeito, para nunca sobrar consumo debitado sem produção correspondente registrada.

**Baixa de componente.** Cada bobina de consumo efetivamente debitada em um apontamento gera um `BaixaComponente` local, um registro por bobina (não por lote de produção gerado, já que o consumo é da máquina e não de uma bobina de produto acabado específica). O `BaixaComponente` é enviado ao ERP pelo webservice `TratarBaixa` (ver 6.2.1), que grava a pendência em `USU_TBXACMP` da mesma forma que os demais fluxos de apontamento — a execução física da baixa continua acontecendo pela regra orquestradora 230, fora do SIGMA.

**Repesagem.** Quando uma bobina que já teve consumo real é removida da máquina antes de zerar totalmente — porque o operador decidiu tirá-la, não porque ela esgotou —, o sistema gera um `BaixaComponente` com `repesagem=S`, e o lote fica bloqueado para nova alocação (em consumo ou fila) enquanto essa repesagem não for resolvida no ERP. A quantidade enviada nesse caso não é a estimativa local: `TratarBaixa` recalcula ela mesma como o saldo atual do lote no ERP menos 1, preservando saldo 1 para não repetir a repesagem em cada nova tentativa de baixa do mesmo lote. Esse bloqueio evita que o operador aloque de novo uma bobina cujo saldo real ainda não foi conferido pela balança/pesagem física, que é o motivo de existir a repesagem.

**Ajuste automático no WMS.** Cada baixa integrada com sucesso no ERP também gera um ajuste em `WMS_IntegraçãoOP` (`tipo_envio=ajuste`), para o WMS saber o novo saldo real do lote depois do consumo — o mesmo padrão usado pelo fluxo de apontamento de componente da v1/v2 (ver 8.4), mas com a quantidade calculada de forma diferente: em vez de sempre `0`, aqui o valor é `1` quando a baixa é repesagem, `0` quando é consumo total, ou o saldo restante lido da própria `BobinaConsumoRecurso` no caso comum (por exemplo, uma bobina que tinha 1500 kg e debitou 1300 kg gera um ajuste de 200 kg). O palete usado no ajuste é resolvido a partir do lote consumido, procurando em `USU_TPALWMS` por `USU_CODLOT`; sem palete correspondente, o próprio lote é usado como identificador, igual ao que já ocorre no fluxo de área vermelha. Como o valor do ajuste muda a cada baixa do mesmo lote, cada baixa gera sempre um novo registro de ajuste, sem reaproveitar um pendente anterior — reaproveitar sobrescreveria um saldo que ainda não foi confirmado no WMS. Por esse mesmo motivo, a fila WMS (ver 6.3) só libera para envio a pendência mais antiga de cada lote: se houver uma pendência anterior do mesmo `(empresa, lote)` ainda pendente ou em processamento, as seguintes ficam bloqueadas até a anterior ser integrada — evitando que um reprocessamento fora de ordem regrida o saldo já corrigido no WMS. Uma falha ao gerar esse ajuste não desfaz a baixa já confirmada no ERP; ela só fica registrada no log daquela baixa, sem bloquear as baixas seguintes.

A tela também interage com WebSocket quando a telemetria HTTP fornece `pesoBalanca`. A balança pode atualizar a interface em tempo real e ficar registrada junto do apontamento como evidencia auxiliar.

O operador da tela de apontamento é validado contra o ERP em `E906OPE`. A OP ativa é controlada em `logs_troca_op_ativa`: ao trocar OP, a tela fecha o log aberto do recurso preenchendo `horario_saida` e cria um novo log com a OP decomposta em `origem`, `op`, `estagio` e `seqrot`, além de `horario_troca` e do código `id_operador`. A troca exige operador validado e é bloqueada se existir parada aberta ou pendente de justificativa. As telas `apontamentos_v1` e `apontamentos_v2` exigem exatamente uma OP ativa para qualquer ação de escrita; se o recurso tiver mais de uma, elas recusam a operação para não encerrar ou alterar todas por engano. Se uma troca alcançar uma parada física aberta, ela permanece a mesma e é vinculada ao período novo; cada período consolida somente sua própria parte temporal, sem criar parada artificial nem intervalo de segundos. O campo `ParadaMaquina.operador` guarda sempre o código do operador, não o nome. Os registros locais de `Apontamento` e `ApontamentoComponente` também gravam `usuario_id`, indicando o usuário Django autenticado que executou o apontamento na tela.

### 8.3 Tempos de produção, paradas e justificativas

Um **período produtivo** é o intervalo de permanência de uma OP em um recurso. Ele é o registro `LogTrocaOPAtiva`: começa em `horario_troca`, recebe a OP decomposta e permanece aberto até `horario_saida`. Em operação normal, há somente um período aberto por recurso. A primeira OP apenas cria o período; cada troca posterior fecha o período ativo e cria o período da nova OP.

Nas Views `0`, `1` e `2`, a lista de sequenciamento da tela de apontamento permite **desacoplar** a OP ativa. Desacoplar não exclui a OP do sequenciamento: somente encerra o período produtivo aberto, deixando o recurso sem OP ativa. A ação só é exibida e aceita quando não existe parada aberta nem parada fechada com justificativa incompleta. A mesma regra é validada no backend. A View `3` não mostra nem aceita esse botão: o encerramento de uma OP é feito pelo fluxo de alocação da própria tela, sem afetar as demais OPs do recurso. Nela, uma OP só pode ser acoplada quando houver pelo menos um componente comum — mesma combinação de produto e derivação — entre ela e todas as OPs que já estão acopladas ao recurso (ver 8.2.1 para o fluxo completo de acoplamento, consumo de bobina e baixa de componente dessa tela).

`ParadaMaquina` representa a parada física do recurso e guarda início, fim, código do operador, usuário que fez a última alteração, tipo (`Manual` ou `Sinal`) e data/hora de log. Cada parada se relaciona a um ou mais períodos produtivos do mesmo recurso. Uma parada aberta é vinculada a todos os períodos abertos do recurso; se uma OP for alocada enquanto a máquina estiver parada, o período novo também recebe o vínculo. Uma parada fechada lançada manualmente é vinculada a todos os períodos que cruzarem seu intervalo. Há no máximo uma parada aberta por recurso. Assim, um período pode conter nenhuma, uma ou várias paradas, e a tela Log Tempo Produção mostra a hierarquia período → parada → justificativas. A parada e suas justificativas são físicas e únicas, mesmo quando vinculadas a mais de um período. Na consolidação, cada período recebe somente a interseção da parada com seu próprio intervalo, sem antecipar o início do período nem alterar o início físico da parada.

No **Log Tempo Produção**, quem possui a permissão **Pode Alterar Paradas** pode corrigir os horários físicos de início e fim, com precisão de segundos. A alteração é única para a parada, mesmo quando ela aparece em mais de uma OP: ao fechar ou corrigir o intervalo, o SIGMA recompõe os vínculos pelos períodos que realmente o cruzam. A mesma reconciliação é executada quando a parada termina por telemetria, encerramento manual ou sincronização de OP. Por exemplo, se o fim for trazido para antes do começo da OP B, B deixa de contabilizar essa parada; se ainda houver interseção, conserva somente o trecho correspondente. Enquanto a parada estiver aberta, todos os períodos ainda abertos que a cruzam permanecem obrigatoriamente vinculados; um período já encerrado pode ser removido somente se não tiver participado do intervalo físico. Parada já fechada não pode ser reaberta por essa ação. As justificativas anteriores mantêm seus motivos e durações, seus inícios parciais são recalculados a partir do novo início e a última sequência recebe o saldo; a redução é recusada quando as sequências já fixas não couberem no novo intervalo. A exclusão administrativa usa o mesmo recálculo dos pacotes ERP locais que a alteração de horário.

Os motivos não são gravados diretamente na parada. A aba **Motivos de Parada** do recurso cadastra a abrangência local da combinação ERP `CODEMP`, `CODGPM` e `CODMTV`. `USU_T018GPM` fornece os grupos ativos; `USU_T018MVP` liga grupo e motivo; e `E018MTV` fornece o motivo e a descrição ativos. Ao justificar, o SIGMA só aceita motivo que esteja vinculado ao recurso e ainda ativo no ERP.

Cada `JustificativaParada` representa uma parte cronológica da parada e possui sequência, motivo, início parcial e tempo. A soma dos tempos de uma parada fechada deve ser exatamente igual à duração entre início e fim. Em parada aberta, a última justificativa fica sem tempo e representa o trecho ainda em andamento; ao encerrar a parada, esse último tempo é recalculado para fechar toda a duração. É possível dividir uma parada, por exemplo, em tempo de setup e tempo de quebra, sem perder a linha do tempo.

O bloqueio de apontamento ocorre por duas condições: parada aberta sempre bloqueia; parada fechada bloqueia enquanto as justificativas não cobrirem toda a duração. Nas telas que exibem justificativas, o operador deve justificar todas as pendências e, quando necessário, usar **Encerrar todas as paradas abertas** para informar o fim forçado. Essa regra também bloqueia troca de operador e troca/desacoplamento de OP enquanto houver pendência.

Paradas manuais exigem `Aponta Parada` no cadastro do recurso. A abertura é permitida quando o recurso possui `Permite Parada Manual` ou quando o usuário recebe a permissão `Pode Alterar Paradas`, diretamente ou por grupo. No apontamento, a abertura usa automaticamente o horário atual, o operador validado e o usuário logado, vinculando a parada física aos períodos abertos do recurso. No Log Tempo Produção, o usuário autorizado informa somente recurso, operador, início e, opcionalmente, fim: não seleciona OP nem período de referência. O SIGMA localiza e vincula automaticamente todos os períodos do recurso que cruzarem o intervalo. Os horários devem ser anteriores ao momento atual, o intervalo fechado deve respeitar o tempo mínimo configurado no recurso e não pode coincidir com outra parada; é obrigatório existir ao menos um período produtivo coincidente. Mesmo com uma parada aberta, pode registrar uma parada histórica já fechada se o intervalo não coincidir; uma segunda parada aberta continua bloqueada.

Todo `save`, exclusão ou alteração de vínculo de parada e justificativa publica, após o commit, o estado atualizado no WebSocket do recurso: se há parada aberta, quantas pendências existem e se o apontamento deve bloquear. Com isso, todas as abas abertas do mesmo recurso atualizam sem abrir WebSockets separados para cada tipo de evento.

Na versão `apontamentos_v1`, depois que um apontamento local é salvo com sucesso em `producao.apontamento`, a validação visual do operador é invalidada para exigir nova validação no próximo apontamento. Como essa tela aguarda alguns segundos antes de recarregar automaticamente, ela também marca no navegador que o operador foi limpo; se o usuário atualizar manualmente antes do contador terminar, a tela já volta pedindo novo ID de operador. Na versão `apontamentos_v2`, o operador permanece validado até troca manual do operador, troca de recurso ou nova regra específica da tela.

Quando o recurso está com `aponta_parada` e `exibir_jus` ativos ao mesmo tempo, uma `ParadaMaquina` aberta bloqueia o envio de apontamento; uma parada fechada também bloqueia enquanto a soma das justificativas for menor que sua duração. O modal lista as ocorrências e cria a primeira justificativa individual por parada, com um único operador validado em `E906OPE`, aplicado a todas as pendências. Ao lado do status de cada parada, o modal também mostra o tempo total decorrido: para parada já fechada, é um valor fixo calculado no momento da renderização; para parada ainda aberta, um contador no navegador recalcula esse tempo a cada segundo a partir do horário de início, sem precisar recarregar a página. Cada parada pode possuir várias `JustificativaParada`: cada sequência inicia em `parcial`, guarda o seu `CODMTV` e seu tempo; numa parada aberta a última sequência fica em andamento e é congelada quando a parada termina. Alterações posteriores são feitas no Log Tempo Produção, de acordo com a regra `Alteração de Justificativas` do recurso ou a permissão `Pode Alterar Paradas`. Salvar justificativas altera somente as respectivas `JustificativaParada`; o usuário, operador e data/hora da `ParadaMaquina` permanecem inalterados. Ao abrir, encerrar ou alterar os horários da parada, o sistema registra em `usuario` o usuário Django autenticado responsável pela ação. Cada motivo é revalidado no ERP pelo tipo vinculado e por `E018MTV.SITMTV='A'`.

A parada manual usa a mesma tabela e o mesmo WebSocket das demais paradas. Nas telas de apontamento, o botão abre uma parada no recurso com início atual, tipo Manual, código do operador validado e usuário Django logado. Ele exige período produtivo aberto, operador validado, nenhuma parada aberta e autorização pelo parâmetro `permite_parada_manual` ou pela permissão `Pode Alterar Paradas`; `aponta_parada` é obrigatório em todos os casos. No Log Tempo Produção, o usuário autorizado informa recurso, código do operador, início e fim opcional. O sistema associa a mesma parada física a todos os períodos do recurso que cruzarem o intervalo, aplica o tempo mínimo do recurso e recusa sobreposição com outra parada. Toda inclusão, alteração ou exclusão de parada/justificativa notifica o grupo WebSocket do recurso após o commit, atualizando as abas abertas.

O submenu de apontamentos possui a tela `Log Tempo Produção`, acessível pelo atalho azul `Log Tempos` nas telas de apontamento quando há OP carregada. Cada registro principal representa um período produtivo controlado pela troca de OP: mostra a OP, o recurso, o código do operador, o início e o fechamento do período. A primeira coluna contém a seta de expansão da produção e das paradas; ao expandir, a tela apresenta as paradas vinculadas ao período e, dentro delas, as justificativas sequenciais. Sem `horario_saida`, o período aparece como `Parado` se existir parada aberta ou como em produção nos demais casos. A tela pagina 14 períodos por página. Uma parada aberta não pode perder vínculo nem ter período vinculado excluído: a relação é preservada até o fim físico da parada, inclusive se o período já tiver sido encerrado. Depois de fechada, a correção dos horários recompõe automaticamente os vínculos temporais; a exclusão administrativa pode remover um vínculo restante, e a parada física só é excluída quando não resta nenhum período associado. Ao corrigir ou excluir um trecho que já possui pacotes locais, os pacotes pendentes daquele corte e dos cortes posteriores mantêm seus cortes e têm seus itens regenerados, sem o item de parada que deixou de existir. Pacotes integrados ou em processamento permanecem imutáveis no SIGMA e não retornam à fila; qualquer ajuste correspondente no ERP é manual. Pacotes anteriores ao trecho corrigido permanecem intactos.

#### 8.3.1 Consolidação e envio de tempos ao ERP

O `Log Tempos ERP` transforma o histórico local em pacotes para o webservice `ApontamentoTempos`. Cada `PacoteTempoERP` pertence a um único período de `LogTrocaOPAtiva` e representa um intervalo real, guardado em `corte_inicio_real` e `corte_fim_real`. Os itens do pacote não repetem os dados da OP ou do recurso: eles guardam somente tipo (`PRODUCAO` ou `PARADA`), operador, motivo quando for parada, data/hora inicial e data/hora final.

O worker `consolida_tempos_erp` é agendado para 00h15, 06h15, 12h15 e 18h15. A agenda não obriga cortes físicos de seis horas: em cada execução, o início é o fim do último pacote do período e o término é o horário atual ou o fechamento do período. Assim, se a rotina ficar dois dias sem executar, ela gera o intervalo completo ainda não consolidado, sem criar cortes artificiais intermediários.

Para cada pacote, o SIGMA cria uma produção para todo o intervalo e inclui as paradas que se sobrepõem a ele. O motivo da parada é a justificativa que ocupou o maior tempo dentro daquele intervalo. Produção e parada são enviadas em listas separadas, mas compartilham a mesma chave de OP do pacote: empresa, origem, OP, estágio, roteiro e máquina.

Os horários enviados ao ERP são consistidos em minutos inteiros e gravados nos itens em horário local. Antes de criar o pacote, início e fim do corte têm segundos e microssegundos removidos; assim, um corte exibido como `12:11` gera Produção terminando em `12:11`, sem avanço para `12:12`. O payload usa sempre `HH:MM:00`. O ERP não aceita `00:00`, portanto início ou fim exatamente à meia-noite seguem como `00:01`.

As paradas são encaixadas entre esses limites sem sobreposição. No início, a primeira parada só pode começar um minuto após o início da Produção e após a última parada do pacote anterior, quando houver. No fim, o cálculo é feito da última parada para a primeira: o minuto final fica reservado para a Produção, a última parada termina no máximo um minuto antes do corte e cada parada anterior termina antes da próxima já encaixada. Depois do encaixe, os itens são gravados em ordem cronológica. Quando não há um minuto válido para uma parada, ela não é criada; se não houver minuto válido para a Produção, o pacote é descartado.

O pacote possui `status=0` para pendente — falha de envio também volta aqui, com o motivo no log, pois não existe estado de erro separado —, `status=1` para integrado e `status=2` para processando. O log e a data/hora registram o último retorno. A tela `/producao/log-tempos-erp/` pagina 20 pacotes, expande para mostrar seus itens e permite envio individual ou dos pendentes. O botão global é bloqueado enquanto a fila estiver processando; também não deixa enviar um pacote quando houver pacote anterior pendente ou processando para a mesma chave de OP. Superusuários podem excluir pacotes ainda não integrados e, dentro de um pacote pendente, excluir individualmente somente itens do tipo Parada; itens de Produção e pacotes integrados ou em processamento não podem ser excluídos.

O worker `fila_tempos_erp` reserva os pacotes no banco antes de enviar, usa lock em memória e processa apenas uma chave de OP por vez. O envio usa SOAP no serviço `ApontamentoTempos`, imprime o envelope enviado e a resposta bruta no processo, grava o retorno no pacote e respeita timeout de 180 segundos. O `envia_pendencias` dispara a fila automaticamente para pacotes pendentes (falha de envio também é pendente, com o motivo no log); pacotes que permanecerem em processamento além do timeout voltam a pendente quando o lock da fila estiver livre.

Quando a tela de logs ou apontamento precisa aumentar uma quantidade já integrada, o SIGMA usa `AumentarApontamento`. O motivo não e criar uma nova operação desconectada, mas complementar o apontamento existente no ERP. A regra Senior evita duplicidade, incrementa a quantidade e gera as pendências proporcionais de componentes da mesma forma controlada do apontamento principal.

Fluxo resumido:

1. Usuário seleciona OP/recurso na tela.
2. Sistema identifica o recurso e escolhe a tela de apontamento conforme o `view_id` configurado no cadastro do recurso.
3. Sistema valida operador no ERP.
4. Sistema grava um ou mais registros locais em `producao.apontamento`.
5. Na v1, se o registro local foi criado com sucesso, a validação do operador é limpa para o próximo apontamento.
6. Registro inicia como `status=0`.
7. Worker `fila_logs_apontamentos` reserva para `status=2`.
8. Envia `Apontamentos` com `wacao=APONTAR-OP` para efetivar a produção no ERP e gerar o controle de baixa posterior dos componentes.
9. Interpreta `<waRetorno>`.
10. Se sucesso, marca `status=1`.
11. Se erro, volta para `status=0` com log.

Payload principal:

- `empresa`.
- `CodOri`.
- `NumOrp`.
- `NumCad`.
- `CodEtg`.
- `SeqRot`.
- `QtdRe1`.
- `QtdRfg`.
- `DatMov`.
- `HorMov`.
- `NumBob`.
- `NumMaq`.
- `CodLot`.

No apontamento normal com quantidade produzida ou refugo, o lote não é digitado livremente pelo operador. O SIGMA gera o `CodLot` a partir do `loteatual` da empresa, grava esse lote no registro local e incrementa o próximo lote disponível. Quando a OP gera mais de uma bobina, o sistema divide a quantidade entre as bobinas e gera um lote para cada registro criado.

O `CodLot` só deixa de ser enviado quando o registro local fica sem lote, situação usada para apontamento sem quantidade produzida e sem refugo. Nesse caso, o JSON enviado ao Senior não recebe a chave `CodLot`; na regra LSP o valor fica vazio e o apontamento segue sem criação de novo lote de produto acabado.

### 8.4 Apontamento de componente

O apontamento de componente registra a baixa ou consumo de componentes vinculados a uma OP. Esse fluxo tem uma particularidade importante: o valor informado pelo operador pode ser um lote ERP ou um palete WMS. Por isso, antes de chamar o webservice do ERP, o SIGMA resolve qual e a origem real do dado.

Na tela `apontamentos_v2`, o valor informado para o lote/palete do componente precisa ter pelo menos 4 caracteres. Valores menores são bloqueados antes de gravar `ApontamentoComponente`, para evitar registros acidentais de leituras incompletas.

Quando o valor e um palete WMS, o sistema consulta a tabela de paletes importados para descobrir o lote ERP, o componente, a derivacao e a quantidade disponível. Quando não encontra o palete, tenta tratar o valor como lote ERP e consulta o saldo no estoque. Essa ordem evita baixar componente usando o identificador errado.

Depois que o ERP confirma o apontamento do componente, se o registro veio de palete WMS, o SIGMA cria um ajuste de estoque no WMS para zerar ou ajustar o palete consumido. Essa etapa acontece somente depois do sucesso no ERP, para não alterar o WMS se o ERP não aceitou o movimento.

O envio ao webservice `ApontamentoComponente` existe porque o componente informado pela operação precisa entrar no controle do ERP como consumo vinculado a OP. A regra Senior valida o saldo do lote do componente, calcula a quantidade liquida da OP quando aplicável, aponta a OP e grava o componente recebido como pendência de baixa em `USU_TBXACMP`. Esse comportamento e importante porque o componente informado pode não ser exatamente o mesmo que o ERP baixaria automaticamente pela éstrutura original da OP.

A baixa efetiva do componente não acontece diretamente nesse mesmo fluxo. O apontamento cria a pendência com `USU_SITPEN=1` e `USU_IDEUNI`; depois a regra orquestradora 230 reserva a pendência, muda para `USU_SITPEN=2` e envia o registro de forma assíncrona para o webservice interno `BaixaComponenteERP`. O processamento final marca a pendência como sucesso (`3`) ou erro (`4`).

Fluxo:

1. Usuário informa/bipa etiqueta.
2. Sistema grava `ApontamentoComponente`.
3. Worker consulta `USU_TPALWMS` por empresa e palete.
4. Se encontrar:
   - Usa lote ERP vinculado.
   - Usa componente, derivacao e quantidade disponível do palete.
   - Guarda `PalWms` para ajuste WMS posterior.
5. Se não encontrar na `USU_TPALWMS`, consulta `E210DLS` por lote pois pode ser uma etiqueta de bobina refugada gerada pelo SIGMA.
6. Envia `ApontamentoComponente` com `wacao=APONTAR-COMPONENTE` para registrar o consumo do componente no controle do ERP e gerar a pendência em `USU_TBXACMP`.
7. Se ERP OK e havia palete WMS:
   - Cria `WMS_IntegraçãoOP`.
   - `tipo_envio=ajuste`.
   - `quantidade=0`.
   - `palete` igual ao palete bipado.
   - Envia para WMS `ajuste_estoque`.
8. Regra orquestradora 230 busca pendências com `USU_SITPEN=1`, reserva como `USU_SITPEN=2` e envia para `BaixaComponenteERP`.
9. `BaixarComponentes` processa a baixa pelo `USU_IDEUNI` e atualiza `USU_SITPEN` para `3` em sucesso ou `4` em erro.
10. Se WMS falhar na criação da pendência, componente volta para pendente com log.

#### 8.4.1 Movimentação de Componentes

A tela **Movimentação de Componentes** (menu Logística; antigo "Painel de OPs") é somente consulta e usa a origem de OP `110` como filtro. O acesso é permitido para staff ou para quem possui a permissão `Pode visualizar componentes movimentar`; usuário não staff consulta apenas a empresa da sua filial. O filtro **Máquina** lista somente recursos com OP aberta nessa origem, em situação `A` ou `L` e marcada para movimentação (`MOVORP='S'`); ao selecionar o recurso, a tela é recarregada com suas OPs. Componentes das origens `230`, `405` e `410` são exibidos como **Bobina**. O alerta de consumo começa em 90% e torna-se crítico acima de 100%.

Uma OP é atual quando possui início e ainda não possui fim; as demais aparecem como próximas. OP concluída pelo realizado não é exibida. Quando houver mais de uma OP atual, o painel também consulta o último apontamento: uma OP sem movimentação há mais de quatro horas é removida somente se existir outra OP atual com movimentação mais recente.

O painel permite consultar os lotes já baixados do componente na OP pela transação `90251` e, para componentes classificados como bobina, consultar no WMS os paletes/lotes disponíveis para cobrir apenas o saldo ainda necessário da OP.

### 8.5 Correção de quantidade para menor

Quando a nova quantidade do lote é menor que a já registrada, o SIGMA envia uma única chamada a `DiminuirApontamento` com `wacao=DIMINUIR-OP`, a chave do lote e a quantidade final desejada. O SIGMA não calcula rateio por sequência, não grava estornos de componente e não mantém worker ou tela para essa operação.

A regra personalizada do ERP localiza e rateia as sequências, chama o serviço nativo `Acertar`, cria as pendências de componentes na tabela ERP `USU_TESTCMP` e finaliza tudo em uma transação. Falha no acerto ou na criação de uma pendência desfaz a transação. O job ERP posterior será o único responsável por consumir essas pendências e ainda é uma etapa separada.

Quando o ajuste é para maior, o comportamento é diferente: o SIGMA faz um apontamento complementar pelo fluxo de aumento, enviando apenas a diferença positiva. Assim, aumento complementa o apontamento; redução confirma uma quantidade final no ERP.

Na exclusão de lote integrado, a chamada única recebe `ExcluirLote=S`. Depois do acerto e das pendências de componentes, a mesma transação ERP marca o lote em `E210DLS.USU_SITLOT='E'`, usando empresa, lote e depósito de consulta. A partir daí, o SIGMA grava o histórico local de exclusão com `status=3`.

Fluxo:

1. Usuário solicita acerto de apontamento.
2. Se a nova quantidade for maior, o SIGMA envia apontamento complementar, aguarda o retorno na tela e não cria estorno.
3. Se a nova quantidade for menor, o SIGMA chama `DiminuirApontamento` uma vez, com a quantidade final desejada.
4. A regra ERP rateia sequências, acerta o apontamento e grava as pendências de componentes em `USU_TESTCMP` de forma atômica.
5. A próxima etapa ERP implementará o job que consome as pendências; não há fila local do SIGMA.

### 8.6 Liberação de lotes

A liberação de lotes é o fluxo da qualidade para retirar um lote recém produzido da condição de pendência/consulta e movimentá-lo para o depósito/local de armazenamento aprovado. O SIGMA não trabalha apenas com uma decisão visual: ele valida a situação no ERP, grava um registro local de liberação, gera movimento para o ERP e cria a pendência correspondente para o WMS.

O acesso a essa tela é controlado pela permissão **Pode acessar a tela de liberação de lotes**. A única ação de destinação nessa tela é **Liberar**, que exige a permissão **Pode destinar lotes na tela de liberação**.

Os depósitos de origem, depósito destino ERP, local WMS e transação de movimento não são fixos no código. Eles são resolvidos a partir dos parâmetros da filial e, quando houver configuração mais específica, do centro de recurso. Isso permite que recursos ou centros tenham regras diferentes sem alterar o programa.

O fluxo também consulta Alchemy para trazer informação de análise da bobina, ajudando a qualidade a decidir antes de liberar.

Na liberação direta, o envio ao ERP usa `MovimentarEstoque` com `acaoBotao` igual a `A`. O motivo do envio é mover o saldo para o depósito aprovado e gravar a situação customizada do lote como liberada. Nesse caso, o SIGMA também cria pendência WMS do tipo `novo_lote`, porque o lote liberado precisa ser recebido/criado no WMS no local de armazenamento definido.

Enviar um lote para Área Vermelha é a etapa de triagem física disponível nesta tela para origens permitidas: usa `MovimentarEstoque`, a transação interna padrão da filial e o depósito de Área Vermelha do recurso ou filial, gravando situação `V`. A análise, a decisão de liberar/refugar/reclassificar e as integrações WMS continuam exclusivamente na reunião de **Área Vermelha**.

Refugo e reclassificação não são tratados como liberação direta. Eles acontecem depois da avaliação da Área Vermelha, quando a reunião define o destino do lote. Nessa etapa, se houver refugo ou reclassificação, o envio ao ERP usa `TransferenciaProduto`, porque o saldo precisa ser transformado para outro produto/derivação/lote. Se a decisão final for liberar quantidade sem troca de produto, o envio usa `MovimentarEstoque`.

Fluxo:

1. Tela consulta lotes no ERP com saldo em depósitos configurados.
2. Busca dados em `E210DLS`, `E900EOQ`, `E725CRE`, `E075PRO`.
3. Consulta Alchemy para flag de análise.
4. Usuário escolhe liberar.
5. Sistema valida `USU_SITLOT` no ERP.
6. Sistema resolve parâmetros:
   - Depósito destino ERP.
   - Transação ERP.
   - Local WMS.
7. Para liberação direta, grava um registro local em `qualidade.liberacao_lote`.
8. A partir desse registro, grava uma pendência local em `qualidade.wms_integracao_op` com tipo `novo_lote`.
9. Dispara a fila WMS para enviar o lote ao WMS no local de armazenamento definido.
10. Na sequência, reserva o registro de `qualidade.liberacao_lote` e dispara a fila de consulta de lotes para enviar `MovimentarEstoque` ao ERP.

Na liberação direta, o código dispara a fila WMS antes de disparar a fila ERP. Isso não significa que os dois sistemas sejam atualizados em uma mesma transação. O SIGMA cria registros locais e aciona duas integrações assíncronas: uma para o WMS e outra para o ERP. Como são filas separadas, cada uma pode concluir, falhar ou ser reprocessada de forma independente.

### 8.7 Área vermelha

A área vermelha é o fluxo de avaliação de lotes que exigem decisão de qualidade antes da destinação final. O processo funciona por reunião: os participantes avaliam os lotes, definem quantidades para liberar, refugar, reclassificar ou destinar para prensa, registram motivos e observações, e só depois o sistema envia os movimentos.

Esse desenho evita que uma decisão parcial seja enviada ao ERP ou ao WMS antes do fechamento da análise. Enquanto a reunião está aberta, os registros ERP (`LiberacaoLote`) e as pendências WMS vinculados a ela ficam bloqueados para envio. O envio só é liberado depois do fechamento da reunião, quando o sistema grava a data de fechamento, atualiza a data de geração dos registros e reserva os lotes pendentes para processamento.

O módulo também faz uma resolução mais complexa da origem do lote. Ele consulta movimentos do ERP para encontrar OP, origem e recurso reais, inclusive quando o lote atual é resultado de transformações ou transferências anteriores. Para o WMS, a consulta via DBLINK identifica se o par SKU/lote já existe. Quando já existe, o fluxo usa o local encontrado no WMS; somente quando o par não existe usa o local padrão de Área Vermelha configurado no recurso ou, na falta dele, na filial. Sem um local resolvido, o salvamento é cancelado. Liberar gera `ajuste`; refugo e reclassificação geram `novo_lote`. Quando o lote original já existe no WMS e a decisão não contém uma linha de liberar, o sistema também cria o ajuste de quantidade zero para manter o lote original consistente.

Os motivos exibidos na reunião vêm do cadastro de defeitos/motivos do ERP, na tela `F011DEF`. O SIGMA lista apenas motivos ativos e marcados com `Utiliza na Área Vermelha = S`, campo customizado `USU_UTIAVE` na tabela `E011DEF`. Isso evita que a tela permita escolher motivos que existem no ERP, mas não devem ser usados nesse processo de qualidade. No combo de seleção, os motivos aparecem agrupados pelo mesmo campo `USU_ATRCCU` (Forma de Atribuição de Centro de Custo) usado no envio ao ERP — descrito no parágrafo seguinte —, exibindo o rótulo amigável do grupo (`OP de Fabricação`, `OP de Consumo` ou `Centro de Custo fixo`) em vez do código bruto, para facilitar a localização do motivo certo.

O atalho **Área Vermelha** em Liberação de Lotes move somente o saldo para o depósito de triagem e grava a situação `V`; não define destinação final nem cria liberação, refugo ou reclassificação. Essas decisões permanecem no contexto da reunião, que só libera suas filas após o fechamento.

Quando a decisão da reunião gera refugo ou reclassificação, o envio ao ERP usa `TransferenciaProduto`. Nessa regra, o motivo escolhido também define como o centro de custo será atribuído ao movimento de estoque. O campo `Forma de Atribuição de Centro de Custo` (`USU_ATRCCU`) pode assumir três comportamentos: `OF`, usando a OP de fabricação do lote; `OC`, usando a OP que consumiu o lote; ou `CF`, usando um centro de custo fixo. Quando a forma é `CF`, o ERP usa o campo `Centro de Custo` (`USU_CCUFIX`) cadastrado no próprio motivo.

Na regra atual do webservice, o comportamento é:

- `OF`: busca em `E900EOQ` a primeira operação vinculada ao próprio lote classificado (`CODLOT`) que tenha centro de recurso preenchido. Com esse centro de recurso, consulta `E725CRE.CODCCU` e usa esse centro de custo no movimento. A regra atual não busca primeiro o movimento de entrada em `E210MVP` para descobrir a OP de fabricação; ela resolve diretamente pela operação registrada para o lote.
- `OC`: busca em `E210MVP` o último movimento do lote com transação `90251`. A origem e o número do documento desse movimento indicam a OP de consumo. Com essa OP, busca a primeira operação em `E900EOQ`, obtém o centro de recurso e depois consulta `E725CRE.CODCCU`.
- `CF`: usa diretamente o centro de custo fixo cadastrado no motivo (`USU_CCUFIX`).

O centro de custo encontrado é aplicado tanto no movimento de saída quanto no movimento de entrada da transferência entre produtos. Se a regra configurada não conseguir resolver um centro de custo, o webservice não executa a transferência e retorna erro.

**Para Prensa.** Esse destino existe para material que vai para a prensa, onde ganhará lote e integração próprios fora do SIGMA — o sistema só precisa manter um registro local de log, sem efetivar nada externamente. Na tela, o comportamento é igual ao Refugar: a pessoa informa quantidade, motivo e observação de etiqueta, e o produto/derivação são preenchidos automaticamente a partir do mesmo parâmetro de refugo do recurso/filial (`produto_refugo`/`derivacao_refugo`). As diferenças são: não consome um novo número de lote (fica registrado no próprio lote de origem, já que o lote real nasce na prensa), a linha correspondente de `LiberacaoLote` é gravada com o status `Local (sem integração)` em vez de `Não integrado`, e nenhuma pendência de ERP ou de WMS é criada para essa linha — apenas o registro local. Por não integrar, essa linha nunca gera etiqueta e nunca é enviada pela fila; ainda assim, ela aparece normalmente na Consulta de Lote (ver 8.8), pode ser excluída livremente enquanto isolada (sem bloquear a exclusão por causa de outras linhas do mesmo grupo que já estejam integradas) e não impede o envio das demais linhas do mesmo lote que estejam de fato pendentes.

Fluxo:

1. Usuário abre reunião ou usa reunião aberta.
2. Sistema consulta lotes elegíveis no ERP.
3. Filtros principais:
   - Empresa do usuário.
   - Depósitos de área vermelha.
   - Origens permitidas pela filial.
   - Produto com `USU_CONREL='S'`.
   - Saldo maior que zero.
4. As origens permitidas vêm do parâmetro `origens_area_vermelha` da filial. O select principal aplica esse parâmetro sobre `E075PRO.CODORI`, então a tela só lista produtos cuja origem esteja liberada para avaliação de Área Vermelha naquela filial. O lote no depósito de Área Vermelha não precisa estar marcado como consumo real (`USU_CONREL='S'`).
   - A busca textual aceita lote, bobina, produto, código, sigla ou descrição do recurso.
5. Sistema busca referência real de movimento em `E210MVP` e cadeia de lotes.
6. Sistema busca recurso/OP em `E900EOQ`.
7. Sistema consulta o WMS via DBLINK para verificar se o par SKU/lote já existe e qual é o local atual do estoque.
8. A consulta identifica se o par SKU/lote já existe no WMS. Para gerar as pendências, usa o local encontrado quando existir; somente para lote ainda inexistente usa o local padrão de Área Vermelha do recurso ou, na falta dele, da filial. Sem local resolvido, cancela o salvamento:
   - Liberar gera `ajuste`.
   - Refugar e reclassificar geram `novo_lote`.
   - Se o lote original existe no WMS e não há uma linha de liberar, gera também `ajuste` com quantidade zero para o lote original.
9. Sistema consulta Alchemy para análise/observação.
10. Sistema carrega os motivos ativos do ERP permitidos para Área Vermelha:
   - Cadastro `F011DEF`.
   - Motivo ativo.
   - Campo `Utiliza na Área Vermelha` igual a `S`.
12. Usuário destina quantidades:
   - Liberar.
   - Refugar.
   - Reclassificar.
   - Para Prensa.
13. Para refugo e reclassificação, o motivo escolhido define a forma de atribuição do centro de custo no movimento ERP:
   - `OF`: centro de custo pela primeira operação registrada para o lote em `E900EOQ`.
   - `OC`: centro de custo pela última OP que consumiu o lote, encontrada em `E210MVP` pela transação `90251`.
   - `CF`: centro de custo fixo cadastrado no motivo.
14. Sistema cria linhas `LiberacaoLote`; linhas Para Prensa nascem com status `Local (sem integração)`.
15. Sistema cria pendências WMS conforme destino; linhas Para Prensa não geram pendência WMS.
16. Enquanto a reunião está aberta, os envios ERP e WMS ficam bloqueados.
17. Após o fechamento, as filas podem enviar ERP e WMS.

### 8.8 Consulta de lote, etiqueta e rastreamento

A consulta de lote é a tela de acompanhamento das destinacões já registradas pela qualidade. Ela permite ver o status das liberacões, acompanhar logs de envio, reenviar registros pendentes, excluir o que ainda não foi integrado e imprimir etiquetas quando o movimento já foi concluído.

Uma linha destinada Para Prensa (ver 8.7) aparece com status `Local (sem integração)`, nunca entra na fila de envio ao ERP/WMS e nunca oferece impressão de etiqueta para ela mesma; ela pode ser excluída como qualquer registro não integrado. O grupo (bobina/lote/produto/derivação) só exibe o status `Local` quando todas as suas linhas são desse tipo — se o mesmo grupo tiver ao menos uma linha integrada, processando ou pendente, o status e as ações do grupo (enviar, imprimir) seguem refletindo essas outras linhas normalmente, sem a linha local interferir.

Antes da impressão, o sistema consulta saldo no ERP para confirmar se o lote ainda possui quantidade suficiente no depósito destino. Essa validação evita imprimir etiqueta para um lote que já não tem saldo compatível.

O rastreamento monta uma linha do tempo do lote a partir dos movimentos do ERP, incluindo transformações, transferências, origem, destino e informações de qualidade. Quando há vínculo com Alchemy, também busca dados de análise por bobina/máquina.

Comportamentos:

- Lista registros `LiberacaoLote`.
- Agrupa por lote/produto/derivacao/bobina.
- Permite envio manual de registros pendentes.
- Valida saldo no ERP antes de imprimir etiqueta.
- Gera etiqueta com código de barras Code128 e QR Code de rastreamento.
- Rastreamento consulta movimentos do ERP e dados de qualidade/Alchemy.

### 8.9 Status de recursos

O painel de status de recursos consolida a situação operacional dos recursos produtivos. Ele cruza informações locais e do ERP para mostrar OP ativa, operador, produção do dia e produção desde a última troca de OP.

O painel, os logs de produção, os pacotes de tempo ERP e o sequenciamento respeitam a empresa da filial do usuário. Staff tem escopo global; usuário sem filial não recebe dados desses recursos. Ações que alteram filas ou consolidações usam POST com CSRF.

As paradas de máquina são controladas em `ParadaMaquina`, onde `fim` vazio indica parada aberta. Cada parada pertence fisicamente a um recurso e se associa a um ou mais períodos de `LogTrocaOPAtiva` desse recurso, sem repetir os campos da OP. O motivo não fica na parada: cada motivo é registrado em `JustificativaParada`, permitindo dividir a duração em várias sequências. A parada registra início, fim, código do operador, usuário que alterou por último, tipo manual/sinal e `data_hora`. Uma parada só deixa de bloquear o apontamento quando está fechada e o tempo de suas justificativas cobre toda a duração; o fim pode ter sido informado pelo operador ou pelo processo automático. A troca normal de OP é bloqueada enquanto existir parada aberta ou pendente; se uma parada física acompanhar uma troca autorizada, ela permanece contínua e cada período recebe somente sua interseção temporal. A produção realizada é consultada no ERP, porque o ERP é a fonte oficial dos apontamentos já efetivados.

Comportamentos:

- Lista recursos por empresa/centro.
- Mostra OP ativa aberta.
- Busca operador no ERP.
- Busca produção total do dia em `E900EOQ`.
- Busca produção desde última troca de OP.
- Usa dados locais de OP ativa e paradas de máquina.

### 8.10 Manutenção

O módulo de manutenção controla chamados e ordens de serviço relacionados aos recursos cadastrados. Todo acesso exige autenticação: `Pode acessar Chamados` libera a aba, a listagem e a abertura de chamados; `Pode acessar OS` libera a aba de ordens de serviço. `Pode listar todos os chamados` permite consultar qualquer chamado, inclusive os que o usuário não abriu, não observa e não atende. `Pode manipular chamados` permite editar e excluir chamados. O usuário logado que abre o chamado é registrado como autor da primeira interação. O QR Code por recurso direciona para a abertura já vinculada ao equipamento correto, exigindo login antes do acesso.

Chamados registram categoria, prioridade, status, recurso, responsáveis, observadores e interações. Ordens de serviço podem nascer de chamados ou ser abertas diretamente, com responsáveis, previsao, execução real e histórico de interações.

O módulo também envia notificações por e-mail para envolvidos, usando o SMTP configurado no sistema.

Chamados:

1. Usuário abre chamado por tela ou QR Code de recurso.
2. Sistema grava chamado e interação inicial.
3. Lista chamados conforme permissão:
   - Staff ou `Pode listar todos os chamados` ve todos.
   - Usuário com `Pode acessar Chamados`, sem a permissão global, ve chamados que abriu, observa ou atende.
4. Envia e-mail para envolvidos quando aplicável.

Ordens de serviço:

1. Usuário autorizado abre OS.
2. OS pode nascer de um chamado.
3. Responsáveis são armazenados como lista de IDs.
4. Interações registram execução, início/fim e descrição.
5. E-mails são enviados em eventos relevantes.

### 8.11 Componentes a Separar (Suprimentos)

A tela `Componentes a Separar` responde a uma pergunta operacional simples: de todos os componentes que as OPs abertas/em andamento ainda vão consumir, o que realmente precisa ser levado do almoxarifado para a planta, descontando o que já está disponível no piso de fábrica? Sem essa consolidação, o setor de suprimentos dependia de checar máquina por máquina.

A base é a mesma lógica de outras telas de produção: `E900COP` (OPs com `SITORP` em `A`/`L`) junta com `E900CMO` (componentes ainda pendentes, `QTDPRV > QTDUTI`), `E900OOP`/`E725CRE` (recurso responsável) e `E075PRO`/`E075DER`/`E012FAM` (descrição e família do componente). O produto que a própria OP deveria produzir vem de `E900QDO` filtrado por `PROORI = 'S'` (o registro oficial, não um produto lançado por engano); como uma OP pode ter mais de uma derivação marcada como original, os valores são somados e a derivação de maior quantidade é usada como descrição representativa.

Por padrão a tela já restringe o escopo às famílias de matéria-prima e insumos de produção (`FAMILIAS_ESCOPO`: `61`, `62`, `621`, `629`, `63`, `631`, `64`, `66`, `67`, `68`, `70`, `71`, `72`, `73` e `731`), evitando ruído de famílias que não fazem sentido para separação física.

O saldo em estoque é tratado em duas categorias independentes, ambas configuráveis por lista de depósitos:

- **Na planta** (`DEPOSITOS_PLANTA`): depósitos que já ficam no piso de fábrica — hoje `P01.01` (Pulmão Planta 1) e `P01.02` (Pulmão Planta 2). Esse saldo **entra no cálculo**: é descontado da necessidade bruta para chegar na necessidade real de separação.
- **Em Estoque** (`DEPOSITOS_ESTOQUE`): depósitos de almoxarifado — hoje `01.03` (Alpino). É só informativo — ajuda quem vai separar a saber se existe saldo em outro lugar antes de sair buscando, mas **não entra em nenhum cálculo**.

O rateio do saldo da planta é sequencial por prioridade da OP (`NUMPRI`, menor valor = mais urgente): a OP mais prioritária consome o saldo disponível primeiro, e o restante fica para as próximas. `NUMPRI = 0` é o padrão do ERP para "sem prioridade definida" (a prioridade real começa em `1`), então essas OPs sempre vão para o final da fila de rateio — nunca furam a frente de uma OP com prioridade real — desempatadas entre si pelo número da OP. A tela mostra o valor original do ERP, sem recalcular ou renumerar nada; só a posição no rateio muda. Esse rateio é feito uma vez contra o total do componente (gera o `A separar` agregado) e uma segunda vez contra o saldo do depósito específico de cada OP (`E900CMO.CODDEP`), já que OPs diferentes de um mesmo componente podem apontar para depósitos diferentes. Quando o componente tem alguma necessidade de separação, todas as OPs dele aparecem — inclusive as totalmente cobertas pela planta, com `A separar` zero (é assim que se vê quem consumiu o rateio); só não é listado o componente inteiramente coberto pela planta.

A visualização pode ser agrupada de três formas (mais a opção de uma prioridade específica): juntar tudo em uma linha por componente, separar uma linha por prioridade, ou separar uma linha por recurso. Em qualquer modo, a soma das linhas exibidas sempre bate com o total real de separação — o estoque nunca é descontado duas vezes.

Filtros de recurso, depósito de planta, componente/derivação e família são combobox com checkbox multi-seleção (mesmo padrão do Calendário de OPs em `/setores/pcp/calendario-ops/`), exigindo o botão "Filtrar" para aplicar; a legenda junto ao total explica as cores do "A separar".

Ao clicar em uma linha, um modal mostra o detalhamento de **todas as OPs relacionadas ao componente** — o agrupamento por prioridade/recurso divide apenas a tabela principal; o modal lista sempre todas: origem-OP, situação, previsto/realizado do produto (com a descrição do produto-derivação vindo do `E900QDO` original), previsto/consumido do componente, necessário, quanto do estoque da planta foi rateado para a OP (coluna "Em Planta") e o quanto efetivamente falta separar após o rateio — além do saldo por depósito da planta e do estoque geral.

A tela é responsiva: a tabela principal e a tabela de OPs do modal viram cards empilhados em telas pequenas, mantendo os mesmos dados e o mesmo clique para abrir o modal. Um botão de impressão busca em segundo plano todos os itens filtrados (sem paginação) e imprime só a tabela de dados, sem menu, filtros ou rodapé do site.

Comportamentos:

- Lista apenas OPs abertas (`A`) ou liberadas (`L`) do componente com consumo pendente.
- Exclui o recurso de produção externa (`RECURSO_PRODUCAO_EXTERNA`, hoje `930`) já na consulta ao ERP — consumo dele não passa pelo piso de fábrica.
- Restringe por padrão às famílias de matéria-prima/insumo (`FAMILIAS_ESCOPO`).
- Descobre o produto original da OP via `E900QDO.PROORI = 'S'`, somando quantidades quando há mais de uma derivação.
- Permite restringir o rateio a um subconjunto dos depósitos de planta (filtro "Depósito de planta" na tabela principal), já que a relação recurso × planta não existe no ERP; o modal continua listando todas as OPs e o saldo completo por depósito.
- Desconta do cálculo apenas o saldo dos depósitos de planta (`DEPOSITOS_PLANTA`); o saldo de estoque geral (`DEPOSITOS_ESTOQUE`) é só exibido.
- Rateia o saldo disponível por prioridade da OP, tanto no agregado quanto por depósito específico de cada OP.
- Exibe o "A separar" em verde quando é zero, em azul quando falta mas há saldo no almoxarifado (`DEPOSITOS_ESTOQUE`) e em vermelho quando falta sem estoque disponível.
- Permite agrupar por componente, por prioridade, por recurso ou por uma prioridade específica.
- Paginação de 30 itens; botão de impressão ignora a paginação e traz tudo.
- Exige a permissão `suprimentos.pode_visualizar_componentes_separar`.

---

*Verificado contra o código em 2026-09-01.*
