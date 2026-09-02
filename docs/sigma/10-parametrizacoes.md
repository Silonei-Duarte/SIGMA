---
titulo: Parametrizações críticas
ordem: 10
---

## 9. Parametrizacoes críticas

Os parâmetros são a parte configuravel da regra de negócio. Eles evitam que depósitos, locais WMS, transacões ERP e limites fiquem fixos no código. Isso é importante porque a mesma regra geral pode precisar se comportar de forma diferente por filial, centro de recurso ou recurso.

A regra de leitura é hierarquica:

1. O sistema parte dos parâmetros da filial.
2. Se o centro de recurso tiver um valor preenchido, esse valor substitui o da filial.
3. Para alguns campos especificos, o recurso pode ter configuração própria.

Exemplo prático: uma filial pode ter um depósito padrão de liberação, mas determinado centro pode liberar para outro depósito. Nesse caso, o usuário não precisa escolher manualmente a cada operação; o SIGMA resolve o parâmetro efetivo conforme o recurso/centro envolvido.

Isso torna os parâmetros uma das partes mais críticas do sistema. Um parâmetro incorreto pode fazer uma consulta buscar saldo no depósito errado, uma liberação criar pendência WMS para local errado ou uma movimentação ERP usar transacão inadequada. Por esse motivo, alterações nesses cadastros devem ser tratadas como mudança operacional, não apenas manutenção de cadastro.

| Parâmetro | Nível | Impacto |
|---|---|---|
| `tempo_sem_comunicacao_manual` | Filial/Recurso | Tempo para apontamento manual. |
| `limite_apontamento_minimo` | Filial/Recurso | Limite minimo de apontamento. |
| `limite_apontamento_maximo` | Filial/Recurso | Limite maximo de apontamento. |
| `deposito_apontamento_erp` | Filial/Centro | Depósitos consultados para lotes apontados. |
| `deposito_armazenamento_erp` | Filial/Centro | Depósito destino de liberação. |
| `deposito_armazenamento_wms` | Filial/Centro | Local WMS de liberação. |
| `deposito_area_vermelha_erp` | Filial/Centro | Depósito de área vermelha. |
| `deposito_area_vermelha_wms` | Filial/Centro | Local WMS de área vermelha. |
| `codtns` | Filial | Transacao ERP de transferência. |
| `codtns_area_vermelha` | Filial | Transação ERP específica de área vermelha. |
| `produto_refugo` | Filial/Centro | Produto destino de refugo. |
| `derivacao_refugo` | Filial/Centro | Derivação destino de refugo. |
| `origens_area_vermelha` | Filial | Origens elegíveis na área vermelha. |
| `transacoes_saida_consumo_producao` | Filial | Ajuda rastreamento/referência de movimento. |
| `transacoes_entrada_producao_consumo` | Filial | Ajuda rastreamento/referência de movimento. |
| `cod_alchemy` | Centro | Vinculo do recurso com máquina Alchemy. |

Descrição dos principais grupos de parâmetros:

Parâmetros de apontamento controlam limites minimos e maximos de quantidade e regras de apontamento manual. Eles protegem a operação contra apontamentos fora de faixa e ajudam a separar apontamento automático, apontamento manual e situações sem comunicação.

Parâmetros de depósito ERP definem onde o sistema consulta saldo e para onde movimenta lote no ERP. Eles aparecem em liberação de lote, área vermelha, consulta de lote e validações de estoque. Se o depósito configurado não corresponder ao processo real, o sistema pode concluir que não existe saldo ou direcionar movimento para local indevido.

Parâmetros de local WMS definem o endereço usado ao criar pendências para o WMS. Eles são diferentes dos depósitos ERP porque representam o lado logistico/WMS do processo. Um lote pode ter movimento no ERP e, ao mesmo tempo, precisar ser recebido ou ajustado em local WMS especifico.

Parâmetros de área vermelha definem quais origens entram na tela, quais depósitos são considerados e quais transacões ajudam a rastrear a referência real do lote. Essa configuração e sensível porque a área vermelha trata material em exceção, onde a decisão pode ser liberar, refugar, reclassificar ou manter pendente de reunião.

Parâmetros de refugo definem produto e derivacão usados quando a qualidade destina quantidade como refugo. Isso évita que o usuário tenha que informar manualmente o destino técnico do refugo em cada processo.

O parâmetro Alchemy liga um centro ou recurso do SIGMA a uma máquina no Alchemy para buscar análises. Ele é usado para complementar a decisão de qualidade e manter informações de bobina alinhadas ao recurso correto.

### 9.1 Limites de Telemetria por ambiente

Os limites de coleta HTTP não pertencem ao cadastro hierárquico de fábrica e
são configurados no ambiente: `TELEMETRIA_HOSTS_PERMITIDOS`,
`TELEMETRIA_TIMEOUT_MAX_SEGUNDOS`, `TELEMETRIA_PAUSA_MAX_SEGUNDOS` e
`TELEMETRIA_RESPOSTA_MAX_BYTES`. A allowlist é obrigatória e deve conter apenas
equipamentos de telemetria controlados pela empresa; os demais valores definem
limites operacionais, não uma regra por recurso.

---

*Verificado contra o código em 2026-08-24.*
