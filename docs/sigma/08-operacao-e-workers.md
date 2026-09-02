---
titulo: Operação, workers e monitoramento
ordem: 8
---

## 7. Operação em background, filas e monitoramento

Os workers são rotinas automáticas que rodam junto da aplicação. Eles existem porque muitas tarefas não devem depender de um usuário ficar esperando na tela. Enviar uma fila ao ERP, importar paletes do WMS, limpar sequenciamento ou recalcular planejado OEE são operações que precisam acontecer em segundo plano.

O ponto central é que o SIGMA não usa um agendador externo separado para esses workers. Eles sobem dentro do próprio processo Django/Daphne, controlados pelo app `accounts`. Para evitar que dois processos executem a mesma rotina ao mesmo tempo, o sistema usa uma trava no PostgreSQL.

### 7.1 Inicialização

Quando a aplicação sobe, ela tenta iniciar os workers. Antes de iniciar, tenta adquirir uma trava no PostgreSQL. Se a trava já estiver em uso, aquele processo não sobe os workers. Isso protege contra duplicidade quando há mais de um processo Django ativo.

A trava usada é um advisory lock do PostgreSQL. Esse tipo de trava não bloqueia uma tabela nem um registro específico; ele funciona como um marcador lógico mantido pela conexão com o banco. O SIGMA usa esse marcador para responder a uma pergunta simples: "já existe outro processo autorizado a rodar os workers?". Se a resposta for sim, o processo atual continua servindo a aplicação, mas não inicia as rotinas automáticas.

A chave `20260430` é o número que identifica essa trava dentro do PostgreSQL. Ela fica definida no código como `_CHAVE_TRAVA_WORKERS` em `accounts/apps.py` e é passada para `pg_try_advisory_lock`. Enquanto uma conexão mantém essa chave travada, outra tentativa com a mesma chave não consegue assumir os workers. Quando o processo encerra e a conexão é fechada, o PostgreSQL libera a trava automaticamente.

Regras:

- Em comandos Django, workers só sobem no `runserver`.
- Em produção, sobem quando o processo ASGI inicia.
- Um `pg_try_advisory_lock` no PostgreSQL evita que mais de um processo suba workers.
- A chave da trava global dos workers é `20260430`.

### 7.2 Supervisor

O supervisor é uma thread permanente que acorda a cada 30 segundos. Ele verifica se os workers estão ativos, tenta reiniciar quando necessário e monitora ciclos travados. Essa checagem é importante porque algumas integrações externas podem travar, demorar ou falhar sem responder corretamente.

Thread:

```text
SupervisorWorkersSigma
```

Intervalo:

```text
30 segundos
```

Responsabilidades:

- Iniciar ou reiniciar workers.
- Monitorar services travados.
- Fechar conexões antigas de banco.

### 7.3 Tabela de workers

Cada worker tem uma responsabilidade diferente. Alguns rodam por intervalo fixo, como importação de bobinas ou limpeza de sequenciamento. Outros são disparados sob demanda, quando existe fila a processar.

| Código | Nome | Intervalo | Limite ciclo | Finalidade |
|---|---:|---:|---:|---|
| `envia_pendencias` | Envio automático de pendências | 300s | 60s | Dispara filas ERP/WMS/lotes/tempos. |
| `fila_logs_apontamentos` | Fila Log Apontamentos | sob demanda | 1800s | Envia apontamentos OP ao ERP. |
| `fila_tempos_erp` | Fila Log Tempos ERP | sob demanda | 1800s | Envia um pacote de produção/paradas ao ERP por chave de OP. |
| `fila_log_apontamento_componentes` | Fila Log Apontamento Componentes | sob demanda | 1800s | Envia componentes ao ERP. |
| `fila_baixa_componentes` | Fila Baixa Componentes | sob demanda | 1800s | Envia ao ERP as baixas de bobina geradas pela tela Multi-OP (View 3), via `TratarBaixa`. |
| `fila_wms_integracoes` | Fila WMS Integrações | sob demanda | 1800s | Envia pendências WMS; o scheduler remove os registros integrados há mais de 30 dias. |
| `fila_consulta_lotes` | Fila Consulta de Lotes | sob demanda | 1800s | Envia LiberacaoLote ao ERP. |
| `importa_palete` | Importação de paletes WMS | 3600s | 180s | Solicita a sincronização WMS para `USU_TPALWMS`. |
| `sincroniza_ops_encerradas` | Sincronização de OPs encerradas | 300s | 60s | Para OPs S, F ou C no ERP, fecha a parada aberta no fim do período, congela a justificativa em andamento, encerra a OP ativa e remove o sequenciamento; depois, para os centros com prioridade (`NUMPRI`) definida no ERP, importa esse sequenciamento para o SIGMA (ver 8.1.2). |
| `consolida_tempos_erp` | Consolidação de tempos ERP | 21600s | 60s | Executa às 00h15, 06h15, 12h15 e 18h15; consolida produção e paradas desde o último corte gerado, mesmo que ciclos anteriores não tenham rodado. |
| `oee_planejado` | Recalcula Planejado OEE | 600s | 180s | Consolida planejado do dia e do dia anterior. |
| `coleta_telemetria` | Coleta de Telemetria | contínuo | timeout HTTP máximo | Coleta fontes HTTP JSON sequencialmente; também atualiza a bobina e a balança dos recursos (ver 7.3.1). |
| `relatorio_falhas_email` | Relatório diário de falhas por e-mail | 300s | 60s | Dispara nos horários configurados em `RELATORIO_FALHAS_HORARIOS` (configuração da aplicação), somente se houver pendência, o acumulado das filas pendentes envelhecidas e das fontes de telemetria ativas em falha (ver 7.3.3). Roda dentro do ciclo do Envio automático de pendências. |

### 7.3.1 Coleta de Telemetria

O coletor HTTP roda dentro da arquitetura existente do SIGMA; não usa management command, agendador externo nem processo separado. O bootstrap em `accounts/apps.py` usa a mesma trava global `pg_try_advisory_lock` dos demais workers, o supervisor garante início idempotente e reinicia a coordenadora se ela parar.

Há uma única thread coordenadora, `CoordenadorColetaTelemetria`. Ela carrega todas as fontes ativas e realiza uma coleta HTTP por vez, sem pool, paralelismo ou dependência de sensores e recursos. Uma fonte recém-cadastrada e ativa acorda a coordenadora e entra na coleta mesmo sem sensor vinculado.

O coordenador é orientado a eventos, sem polling fixo. Ele acorda imediatamente quando uma coleta termina, quando fonte, sensor ou vínculo é alterado, ou quando recebe encerramento. Sem evento, aguarda até a próxima fonte agendada.

A coleta HTTP só é habilitada para equipamentos declarados em `TELEMETRIA_HOSTS_PERMITIDOS`. Antes de ativá-la, configure essa variável no `.env` de desenvolvimento ou em `/etc/sigma/sigma.env` e reinicie o processo. Cada item é um host/IP, com porta opcional; host sem porta aceita somente a porta padrão de HTTP ou HTTPS. URLs com credencial, query, fragmento, redirect ou destino fora dessa allowlist são recusadas. O worker limita timeout, pausas e resposta por `TELEMETRIA_TIMEOUT_MAX_SEGUNDOS`, `TELEMETRIA_PAUSA_MAX_SEGUNDOS` e `TELEMETRIA_RESPOSTA_MAX_BYTES`; falhas exibidas no painel são genéricas e nunca mostram a URL completa ou credenciais.

Cada fonte possui seus próprios campos de pausa após sucesso e espera após erro, ambos iniciando em 10 segundos por padrão. Depois de uma coleta bem-sucedida, ela volta à agenda somente após sua pausa. Depois de erro, volta após sua espera de erro. Como há uma única coleta em andamento, uma fonte lenta aguarda seu timeout antes da próxima fonte.

O coletor aceita resposta simulada nos testes. Em execução, cada fonte responde com um objeto JSON: para cada recurso vinculado, seleciona o bloco pela chave exata de `Recurso.codigo` e, dentro dele, lê os valores pelas chaves `Sensor.chave_origem`. Recurso ausente é ignorado; sensor ausente no bloco é pulado sem impedir a coleta dos demais valores. Vírgula decimal é aceita, booleanos aceitam `1/0`, `true/false`, `sim/não`, `yes/no` e `on/off`; inteiros, decimais, texto e valores nulos são tratados conforme o tipo do sensor. Resposta que não seja objeto JSON, valor inválido, timeout e erro HTTP encerram a coleta como falha. A resposta bruta não é salva: somente o JSON interpretado com a chave do sensor é persistido.

Depois de interpretar uma resposta HTTP com sucesso, o coletor mantém duas referências independentes por recurso: o **último snapshot coletado**, atualizado em toda resposta interpretada, e a **última leitura salva**, usada somente para decidir a persistência. A avaliação da parada automática usa o snapshot atual, mesmo quando a regra de gravação decide não criar uma `LeituraTelemetria`.

Na primeira coleta válida do recurso, a leitura completa é salva. Nas próximas, o coletor compara o JSON completo com a última leitura salva mantida no cache do coordenador. Em qualquer tipo, o vínculo precisa estar marcado para monitorar variação para poder disparar uma nova gravação. Para decimal e inteiro, a mudança também precisa atingir a tolerância absoluta ou percentual; quando o valor anterior é zero, a mudança é tratada sem divisão por zero. Booleano e texto não configuram tolerância: quando monitorados, qualquer mudança dispara gravação. Se nenhum sensor monitorado disparar, não é criada nova leitura. Não há leitura parcial.

A regra de parada é avaliada em toda coleta HTTP interpretada com sucesso e sua falha é tratada separadamente da gravação de telemetria: um erro na regra não impede a leitura, e um erro ao gravar a leitura não impede a avaliação que já ocorreu. Falha HTTP, resposta inválida, sensor ausente ou valor incompatível não representam parada; o avaliador retorna **INDETERMINADO**, não abre nem fecha parada e reinicia a contagem de estabilidade.

`RegraParadaRecurso` é única por recurso e possui `ativa` e uma árvore JSONB validada. Cada folha referencia a chave de um sensor vinculado e ativo, uma comparação (`igual`, `diferente`, `maior`, `maior ou igual`, `menor` ou `menor ou igual`) e o valor esperado. Os nós de grupo usam `E`, `OU` ou `NÃO`, podem ser aninhados e precisam conter itens; `NÃO` possui exatamente um item. A validação confere a estrutura, o vínculo do sensor e a compatibilidade entre comparação, valor e tipo do sensor. A árvore é somente dados: não há `eval`, SQL, Python nem execução de texto armazenado. Resultado verdadeiro significa **PARADO**; falso significa **FUNCIONANDO**.

O campo **Tempo Parada Automática** do recurso é um intervalo não negativo e é o período mínimo de estabilidade antes de qualquer abertura, reabertura ou fechamento automático. Se o sinal oscilar, a coleta falhar, o período produtivo mudar ou o operador alterar uma parada manualmente, a contagem recomeça. Depois de uma parada fechada manualmente, o sinal ainda parado precisa permanecer estável desde o fim dessa parada mais o tempo configurado para que uma nova parada seja aberta. No sentido contrário, a parada só pode ser fechada depois de permanecer aberta pelo menos esse tempo. A abertura usa o momento da ação automática, sem retroceder o horário.

Ao indicar **PARADO**, a rotina reconsulta e trava os registros necessários dentro de transação. Ela exige que o recurso permita apontamento de parada, que exista ao menos um `LogTrocaOPAtiva` aberto e que não haja outra parada aberta; então cria uma única `ParadaMaquina` do tipo **Sinal**, vinculada a todos os períodos abertos do recurso. Ao indicar **FUNCIONANDO**, ela pode fechar a parada aberta atual, manual ou por sinal, sem criar outra. O fechamento preserva o operador, usuário e data/hora da parada, ajusta somente o fim e, quando houver justificativas, congela a última: recalcula seu parcial depois da soma das anteriores, grava o tempo restante exato da parada e atualiza a data/hora dessa justificativa. As notificações `parada_update` são emitidas pelo fluxo já existente somente após o commit da transação.

O cache de fontes é carregado ao iniciar o coletor e atualizado quando se salva fonte, sensor, vínculo ou regra de parada. A primeira comparação de cada recurso busca a última leitura no banco; depois disso, a última leitura salva e o snapshot atual ficam em memória enquanto a coordenadora estiver ativa. O estado de estabilidade da regra é reiniciado quando a configuração do recurso muda. Ao reiniciar o processo, a primeira coleta volta a consultar a última leitura persistida.

Em toda tentativa de coleta, mesmo sem sensor ou recurso vinculado, a fonte atualiza `ultima_coleta_em`, cujo significado é **data/hora da última tentativa**. Em sucesso, `log` recebe `Coleta concluída.`; em falha, recebe mensagem genérica segura.

O coordenador também atualiza `Recurso.bobina` a cada resposta JSON interpretada, para qualquer recurso cujo bloco contenha as chaves `contagemBobinas` e `estouroDeContagem`: `numero_bobina = estouroDeContagem * 32000 + contagemBobinas`. Esse cálculo é independente do cadastro de `Sensor`/`SensorRecurso` — roda para qualquer bloco cujo topo do JSON bata com um `Recurso.codigo` existente, sem exigir vínculo manual nem aparecer nas telas de telemetria. Falta de uma das duas chaves no bloco não gera erro, só é ignorada. O coordenador mantém em memória o último valor de bobina conhecido por recurso e só grava no banco quando o valor calculado muda, evitando escrita a cada ciclo.

Na mesma coleta, `pesoBalanca` atualiza a balança das telas de apontamento pelo WebSocket do recurso. A chave é lida diretamente do bloco cujo topo coincide com `Recurso.codigo`, sem exigir `Sensor` ou `SensorRecurso`, e é emitida na mesma frequência configurada para a fonte. O valor precisa ser decimal finito entre 0 e 5000 kg; chave ausente ou valor inválido publica `0` para o recurso sem interromper a coleta; recurso inexistente é ignorado. Ao abrir o modal de peso, a tela inicia em `0` e aguarda a próxima coleta; não zera uma leitura válida por tempo local. Se a fonte que já forneceu esse peso falhar, o recurso recebe `0`; sem fonte configurada, permanece em `0` aguardando uma coleta futura. Recursos de outras fontes não são alterados.

No painel **Status (Services)**, `Coleta de Telemetria` aparece como serviço contínuo e pode ser expandida como o envio automático de pendências. A expansão lista cada fonte ativa com URL, timeout, pausas, situação (`Coletando` ou `Aguardando`), próxima coleta, última tentativa e log. O painel deixa explícito que somente uma fonte é coletada por vez.

### 7.3.2 Escalabilidade das consultas de histórico

As telas de histórico usam paginação no banco. A página corrente carrega somente os itens exibidos e suas relações necessárias; não percorre todo o histórico para montar a grade.

| Tela | Paginação e índice de suporte |
|---|---|
| Logs Apontamentos | 20 registros por página; índice por empresa/ID na entrada nativa e índice da fila por status e chave da OP. O bloqueio de envio é verificado por `EXISTS` somente nos registros da página. |
| Log Tempo Produção | 14 períodos por página; índice por horário da troca e ID. Paradas e justificativas são consultadas apenas para os períodos exibidos. |
| Log Tempos ERP | 20 pacotes por página; índice por fim do corte e ID. Os itens são carregados somente para os pacotes da página. |
| Logs Componentes | 20 registros por página; índice por empresa/ID na entrada nativa e índice da fila por status e chave da OP. |
| Baixa Componentes | 20 registros por página; índice por empresa/ID na entrada nativa (`idx_baixa_comp_codemp_id`) e índice da fila por status e chave da OP (`idx_baixa_comp_fila_chave`). O botão de envio individual e o bloqueio visual por linha usam `Exists` para checar, sem carregar os registros, se já existe outra baixa do mesmo lote em processamento ou pendente antes dela. |
| Consulta de Lotes | 20 grupos por página; os grupos são paginados no banco por empresa, bobina, lote, produto e derivação. Os registros, reuniões e participantes são carregados apenas para os grupos da página. |
| Chamados de Manutenção | 20 registros por página; não possuem índices personalizados para filtros de responsável, observador, recurso, status ou categoria. |
| Ordens de Serviço | 20 registros por página; não possuem índices personalizados para filtros de responsável, recurso ou status. |

O `Paginator` executa `COUNT(*)` para informar o total de páginas. Isso não traz os registros para a aplicação; é uma contagem no banco. Os índices acima reduzem o custo dos filtros e ordenações mais usados. Buscas livres com `icontains` em texto longo continuam sendo mais caras por natureza e devem ser usadas para localizar casos específicos, não como carga padrão da tela.

### 7.3.3 Relatório diário de falhas por e-mail

O worker `relatorio_falhas_email` (`producao/services/relatorio_falhas_email.py`) roda dentro do ciclo do Envio automático de pendências e leva a quem operar, por e-mail, o acumulado do que envelheceu sem integração — sem que alguém precise abrir o painel para descobrir. Silêncio significa limpo: **sem pendência, o e-mail não sai**, e o gatilho é a pendência, não o dia.

O que ele apura:

- As seis filas de integração (`Apontamento`, `PacoteTempoERP`, `ApontamentoComponente`, `BaixaComponente`, `WMS_IntegraçãoOP`, `LiberacaoLote`): registros no status pendente/"não integrado" cuja data de geração (`datger`) tem mais do que o limiar configurado. Não existe status ERRO nas filas; pendência envelhecida é o que precisa de gente.
- As fontes de telemetria HTTP ativas (`FonteColetaHTTP`) cuja última tentativa de coleta falhou (o coletor grava o log da tentativa na própria fonte).

O e-mail resume por fila: contagem, os registros mais antigos (chave da OP/lote, tempo pendente e motivo, já mascarado) e um corte honesto — acima de 5 exemplos por fila, o corpo informa "e mais N registro(s)…" em vez de crescer sem teto. Todo texto de erro passa por `SIGMA.segredos.mascarar_segredos` antes de entrar na mensagem, e a máscara vem antes da poda de tamanho, para não truncar um segredo ao meio.

Comportamento:

- **Cadência**: dispara nos horários configurados em `RELATORIO_FALHAS_HORARIOS` (tela **Configurações da aplicação**). O worker roda a cada ciclo do agendador (~5 min): a cada ciclo, o horário configurado mais recente já vencido no dia é o candidato — um horário 07:00 dispara entre 07:00 e o primeiro ciclo seguinte — e o envio sai se esse horário ainda não gerou envio hoje e existe pendência envelhecida. Cumprido um horário, o próximo disparo é no horário configurado seguinte; pendência que surge depois de um horário já cumprido sai no horário seguinte.
- **Estado persistido**: a marca de "horário já cumprido" mora no banco (`EstadoRelatorioFalhas`, singleton), não em memória. Falha de envio não grava estado: o ciclo seguinte re-tenta o MESMO horário até conseguir. Reinício do processo não reenvia horário já cumprido do dia. O envio de **"não foi possível apurar"** também conta como envio cumprido do horário.
- **Desativado**: os padrões declarados em código deixam o relatório ativo desde o deploy (horários `07:00,16:00`, destinatário `ti@ipel.ind.br`, limiar 5). Ele fica desativado — sem envio e com aviso por ciclo no log do worker — apenas quando linha gravada por fora do validador (shell/migração) deixa nenhum horário ou nenhum destinatário válido: linha vazia, ou só com itens inválidos. Sem pendência, nada é enviado e nenhum horário é marcado como cumprido. A tela não tem como gravar vazio: o botão **Voltar ao padrão** restabelece o default do código.
- **Guarda de frescor**: o relatório só apresenta dado se o agendador concluiu ciclo recente (tolerância de 2 ciclos sobre o `intervalo_segundos` que o próprio agendador declara no registry). Sem ciclo recente — por exemplo, no primeiro ciclo após um reinício — o corpo diz **"não foi possível apurar"** em vez de mandar dado vencido; nunca relata fila como saudável sem apuração.
- **Falha de envio** (caixa ainda não liberada, canal de e-mail fora) não é falha do sistema: o worker loga e segue, o ciclo do agendador termina normalmente e o ciclo seguinte re-tenta o mesmo horário.

Configuração (tela **Configurações da aplicação**, service `accounts/services/configuracoes.py`; chaves com descrição, default e validador declarados em código):

- `RELATORIO_FALHAS_HORARIOS` — horários de envio, separados por vírgula; padrão `07:00,16:00`.
- `RELATORIO_FALHAS_EMAIL_DESTINATARIOS` — destinatários do relatório, um e-mail por linha; padrão `ti@ipel.ind.br`.
- `RELATORIO_FALHAS_LIMIAR_ATRASO_MINUTOS` — pendência envelhecida = pendente há mais do que este limiar, em minutos (1 a 1440; padrão 5).

O worker lê as três chaves no início de cada apuração pelo cache in-process do service de configurações, invalidado por signal a cada gravação: alterar qualquer uma na tela vale na próxima apuração, sem reinício. Linha gravada fora do validador (shell, migração) não derruba a apuração: horário e destinatário inválidos são ignorados na leitura com aviso em log, e limiar inválido cai no padrão declarado da chave (5 minutos). Credencial de envio (canal Microsoft Graph) continua nas variáveis de ambiente do documento 03 — nada de segredo na tabela de configuração.

### 7.4 Timeout e reprocessamento

O tratamento de timeout existe para impedir que um registro fique preso eternamente como "processando". Quando uma fila reserva um registro, ele muda para o status de processamento definido para a própria fila. Se o processo cair, travar ou for interrompido, esse registro poderia ficar bloqueado. O worker de envio de pendências e o supervisor tratam esse caso liberando registros antigos de volta para pendente.

Padrão das filas:

- `status=0`: pendente. Falha de envio também volta aqui (com o motivo no log).
- `status=1`: integrado.
- `status=2`: processando, igual em todas as filas.
- Estados extras ficam além do padrão: `status=3` é excluído em Apontamentos e Componentes e `status=4` é local (sem integração) em Consulta de Lotes; não são status operacionais do painel.

Reserva:

- Antes de enviar, cada fila tenta assumir um lock de execução em memória, como `PROCESSAMENTO_LOGS_LOCK`, `PROCESSAMENTO_APONTAMENTO_COMPONENTES_LOCK`, `PROCESSAMENTO_WMS_LOCK` ou `PROCESSAMENTO_LOTES_LOCK`. Esse lock evita que duas threads da mesma fila rodem ao mesmo tempo dentro do mesmo processo Django.
- Depois disso, a fila faz a reserva no banco usando uma transação com `select_for_update(skip_locked=True)`. Esse lock transacional protege os registros no momento da seleção, evitando que duas execuções reservem o mesmo item ao mesmo tempo.
- Os registros selecionados são marcados com o status de processamento da fila. Esse status é a reserva persistente: indica que o item já foi capturado e não deve ser pego por outra execução enquanto estiver nessa condição.
- O lock transacional dura apenas durante a reserva no banco. O que permanece depois da transação é o status de processamento e o lock de execução da thread enquanto o envio estiver rodando.

Timeout:

O controle de timeout tem dois níveis. O primeiro é o timeout da chamada externa, usado quando uma fila está aguardando resposta de HTTP, SOAP ou WMS. Esse prazo normalmente é de 180 segundos. Enquanto a última atividade registrada do service ainda está dentro desse prazo, o ciclo não é tratado como travado, mesmo que ele ainda esteja em andamento.

O segundo nível é o limite do ciclo do service. Esse limite protege o worker contra execução presa sem progresso. A cada verificação, o supervisor compara o tempo de execução do ciclo com o limite configurado e também verifica se existe uma atividade externa recente ainda dentro do timeout do webservice. Se ainda houver chamada válida em andamento, o supervisor aguarda. Se o ciclo passou do limite e não existe atividade válida dentro do prazo, `matar_service_travado` registra o timeout e aguarda o término seguro do worker; ele nunca injeta exceção em uma thread em execução.

Depois do término seguro, o próximo ciclo verifica os registros que ficaram no status de processamento. Quando o lock da fila está livre e a reserva já passou do tempo seguro, esses registros voltam para `status=0` para novo processamento.

### 7.4.1 Falha na correção de lote

Uma correção manual de lote fica registrada por empresa e lote antes da chamada mutável ao ERP (`AumentarApontamento`/`DiminuirApontamento`, regra personalizada). Falha depois dessa chamada cai em **Falha**, não bloqueia: `AumentarApontamento`/`DiminuirApontamento` são idempotentes na regra do ERP — reenviar uma correção já aplicada não duplica o efeito, o ERP reconhece que não há mais o que ajustar e responde sucesso. O próprio usuário corrigindo o lote de novo já é aceito, sem conciliação manual — esse fluxo (estado "Requer conciliação", tela "Registrar Conciliação") existiu até 2026-08-25 e foi removido por decisão do sênior.

### 7.5 Manual operacional do painel de Status (Services)

O painel de status dos services não é apenas uma tela técnica. Ele é a principal visão operacional para entender se os workers estão rodando, se alguma fila esta presa, se existem pendências elegiveis para envio e se o processo Django ainda possui telemetria ativa dos services.

Arquitetura de execução:

- `accounts/apps.py` é o ponto de bootstrap dos workers. Ele inicia as rotinas automáticas somente em processo elegivel e usa `pg_try_advisory_lock` para evitar que dois processos executem os mesmos workers ao mesmo tempo.
- `SupervisorWorkersSigma` roda em thread daemon e tenta chamar novamente os `start_*` principais. Cada worker decide internamente se precisa subir ou se já existe uma instancia ativa.
- `producao/services/status.py` é o registro operacional em memória do processo. Ele não substitui log persistente; serve para telemetria em tempo real, ciclo atual, duracao, erro, thread ativa e decisão de timeout.
- `MonitorConexoesPostgres` verifica a ocupação do PostgreSQL e a fila do PgBouncer sem manter conexão própria aberta entre as verificações. Ao cruzar 100 conexões de cliente, grava no journal uma única captura das sessões; quando o total volta a 70 ou menos, registra a normalização e fica pronto para uma nova captura. Se houver cliente aguardando vaga no PgBouncer, registra uma ocorrência da fila e só rearma quando ela zera.
- A faixa **Servidor** da tela mostra as conexões PostgreSQL atuais sobre a capacidade normal disponível e separa quantas estão em execução. A capacidade normal exclui as conexões reservadas para superusuário.
- Quando `PORTAL_BASE_URL` usa HTTPS, a faixa **Servidor** consulta o certificado apresentado pelo domínio configurado na porta 443 e mostra a data de expiração e os dias restantes. Fica amarela abaixo de 30 dias, vermelha abaixo de 7 dias e informa indisponibilidade se a consulta TLS falhar. Em instância sem HTTPS configurado, esse indicador não é exibido.
- Services principais mantém loop próprio. As filas de integração são threads filhas assincronas, disparadas quando existe pendência elegivel.
- A importação de paletes WMS chama imediatamente ao iniciar e depois a cada hora o WebService `ImportaWMS`, com a ação `IMPORTAR-PALETES` e as chaves `chave` e `valor` (vazias nesta ação). O ERP executa o `MERGE` em `USU_TPALWMS` e devolve a quantidade de registros inseridos ou atualizados. O timeout SOAP e o limite de ciclo são de 180 segundos; um lock próprio impede duas importações simultâneas. Ela é um scheduler independente, não uma fila filha do Envio automático de pendências.
- A Sincronização de OPs encerradas consulta as OPs locais abertas no ERP. Quando encontra situação `S`, `F` ou `C`, encerra o período produtivo no instante atual e remove a OP do sequenciamento local. Se a parada física vinculada não possuir outro período ainda aberto, também grava seu fim nesse mesmo instante e congela a última justificativa para cobrir a parada; caso exista outro período aberto associado, a parada permanece aberta. Após confirmar a transação, envia `refresh_page` pelo WebSocket do recurso para a tela refletir a OP encerrada.
- Envio automático de pendências, Sincronização de OPs encerradas e Consolidação de tempos ERP possuem limite de ciclo de 60 segundos. Recalcula Planejado OEE possui limite de 3 minutos.

Orquestrador de integrações:

- O Envio automático de pendências coordena o disparo das filas. Ele não processa os registros diretamente e não espera a fila filha terminar; ele verifica locks, trata interrupções por timeout e dispara nova thread quando aplicável. O erro de um ciclo que falhou é mascarado na origem (`SIGMA.segredos.mascarar_segredos`) antes de entrar no registry e no log — o registry apenas converte o texto que recebe, não mascara, e o erro de banco ou HTTP não sai cru para o painel.
- Antes de disparar novas filas, o orquestrador chama o controle de timeout das filas e services de apoio monitorados: Consulta de Lotes, Logs Apontamentos, Log Apontamento Componentes, Baixa Componentes, WMS Integrações, Envio automático de pendências, Relatório diário de falhas por e-mail, Sincronização de OPs encerradas, Consolidação de tempos ERP e Recalcula Planejado OEE. A importação de paletes mantém monitoramento próprio no seu scheduler. A Fila Baixa Componentes também mantém o lock próprio (`PROCESSAMENTO_BAIXAS_COMPONENTES_LOCK`) e devolve para pendente registros travados em processamento.
- Logs Apontamentos, Log Tempos ERP, Log Apontamento Componentes, Baixa Componentes, WMS Integrações e Consulta de Lotes são disparadas automaticamente quando existem pendências elegiveis e o lock da fila esta livre. A fila de tempos reserva o pacote, mantém somente uma chave de OP em processamento e registra o retorno no próprio pacote.
- A retenção de integrações WMS concluídas é processada pelo `envia_pendencias`: a cada ciclo, ele remove apenas registros com `status=1` integrados há mais de 30 dias. A tela WMS não executa exclusão no carregamento.
- A Fila Baixa Componentes é disparada pelo Envio automático de pendências quando encontra registros pendentes e também abre uma thread própria (`disparar_envio_baixas_componentes`) imediatamente após cada apontamento bem-sucedido ou repesagem na tela Multi-OP. Ela ainda pode ser disparada manualmente pela tela `/producao/logs-baixa-componentes/`, individual ou para todas as pendentes. A fila reserva por lote (`CodLot`): só processa a próxima baixa do mesmo lote depois que a anterior for integrada, preservando a ordem cronológica do consumo daquela bobina. A tabela física é `producao.baixa_componentes`; o índice `idx_baixa_comp_fila_lote` em `(status, codlot, id)`, criado pela migration `producao.0037_baixacomponente_fila_codlot`, atende a busca ordenada de pendências por status e lote usada nessa reserva.

Reserva e status dos registros:

- `status=0`: não integrado/pendente, disponível para reserva e envio. Em Log Tempos ERP, falha de envio também grava `status=0` com o motivo no log — não existe estado de erro separado.
- `status=1`: integrado com sucesso.
- `status=2`: processando em todas as filas, inclusive Log Tempos ERP.
- `status=3`: excluído em Apontamentos e Componentes; não é status operacional comum a todas as filas do painel.
- A reserva e feita no banco antes do envio. Nas filas que usam concorrencia, esse controle reduz captura duplicada entre execucoes concorrentes.
- Registros no status de processamento voltam para pendente em dois cenários seguros: depois de uma interrupção por timeout, ou quando o lock da fila esta livre e a reserva ficou parada por mais tempo que o timeout webservice daquela fila.

Controle de ciclo e timeout:

- Cada service registrado informa intervalo e, quando aplicável, limite maximo de ciclo. O registry calcula ciclo em andamento, próximo ciclo, duracao e condicao de travamento.
- Durante cada chamada externa, a fila marca uma atividade valida até o timeout configurado do próprio webservice. Enquanto esse prazo estiver vigente, o ciclo não e tratado como travado.
- Se o ciclo ultrapassar o limite e não houver chamada externa ainda dentro do prazo de retorno, o orquestrador solicita interrupção da thread registrada.
- A interrupção e sinalizada no registry. No ciclo seguinte, quando o lock da fila não estiver mais preso, os registros reservados daquela fila são devolvidos para pendente e reenviados.
- Se uma thread filha morrer sem registrar timeout, o orquestrador também libera reservas antigas: com lock livre, registros no status de processamento há mais tempo que o timeout webservice da fila voltam para `status=0`.

Leitura das filas de integração:

- Pendentes são registros ainda não reservados para envio.
- Elegíveis consideram regras de negócio da fila, como reunião fechada para WMS e Consulta de Lotes.
- Bloqueados são pendências que existem, mas não podem ser enviadas naquele momento por regra de negócio.
- Processando são registros reservados por uma thread ativa ou por uma execução anterior que ainda não foi liberada pelo timeout ou pela regra de lock livre baseada no timeout webservice.
- Timeout webservice mostra quanto tempo cada chamada externa daquela fila pode aguardar retorno.

Limites conhecidos do painel:

- O painel reflete o estado do processo Django que está executando os workers. Como o registry é em memória, reiniciar o processo limpa a telemetria exibida.
- A trava global dos workers depende do PostgreSQL. Se a aplicação não estiver usando PostgreSQL como banco principal, o bootstrap não adquire essa trava.
- O timeout de ciclo protege fila presa; o timeout de webservice protege chamada externa. São responsabilidades diferentes e aparecem separadas na tela.
- A coluna de erro exibe a última falha conhecida pelo registry, não o histórico completo de logs do registro integrado.

---

*Verificado contra o código em 2026-09-02.*
