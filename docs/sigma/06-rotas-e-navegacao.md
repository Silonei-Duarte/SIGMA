---
titulo: Rotas e navegação
ordem: 6
---

## 5. Navegacao e rotas principais

As rotas indicam os endereços internos das funcionalidades no sistema web. Elas servem para mostrar como o sistema está organizado para o usuário, não para explicar código.

As telas principais ficam agrupadas por área:

- Cadastros e administração na raiz do sistema.
- Produção em `/producao/`.
- Qualidade em `/setores/qualidade/`.
- Manutenção em `/setores/manutencao/`.
- Telemetria em `/telemetria/`, vinculada ao cadastro de recursos.
- WebSocket em `/ws/`, usado por recursos em tempo real.

### 5.1 Raiz

As rotas de raiz são os pontos de entrada dos grandes blocos do sistema. Elas não representam uma tela única, mas a divisão principal de navegacao. Quando o usuário acessa produção, qualidade ou manutenção, o Django encaminha para o conjunto de URLs daquele módulo.

| Rota | Módulo |
|---|---|
| `/` | `accounts.urls` |
| `/producao/` | `producao.urls` |
| `/setores/` | `setores.urls` |
| `/select2/` | `django_select2` |
| `/telemetria/` | `telemetria.urls` |

### 5.2 Telemetria

| Rota | Finalidade |
|---|---|
| `/telemetria/sensores/` | Cadastro de fontes HTTP e sensores. |
| `/telemetria/recursos/<id>/configurar/` | Grava vínculos de sensores e regras do recurso. |

### 5.3 Produção

As rotas de produção concentram as telas usadas no acompanhamento e registro da operação produtiva. Elas permitem apontar OP, consultar status de recursos, verificar filas de envio ao ERP, tratar componentes e organizar sequenciamento. Para suporte, essas rotas ajudam a localizar rapidamente onde um erro operacional se manifesta.

| Rota | Finalidade |
|---|---|
| `/producao/apontamentos/` | Tela base de apontamento. |
| `/producao/status-recursos/` | Painel de status de recursos. |
| `/producao/logs-apontamentos/` | Logs/fila de apontamento OP. |
| `/producao/log-tempo-producao/` | Histórico local de períodos produtivos, paradas e justificativas. |
| `/producao/log-tempos-erp/` | Logs/fila dos pacotes de tempos enviados ao ERP. |
| `/producao/logs-apontamento-componentes/` | Logs/fila de apontamento de componentes (v1/v2, via `ApontamentoComponente`). |
| `/producao/logs-baixa-componentes/` | Logs/fila de baixa de componentes gerada pela tela Multi-OP (View 3), via `TratarBaixa`. |
| `/producao/sequenciamento/` | Sequenciamento de OPs. |

### 5.4 Qualidade

As rotas de qualidade concentram as decisões que afetam lote e estoque. A mesma área permite liberar lote, abrir ou tratar área vermelha, consultar lote destinado, rastrear origem/destino é acompanhar pendências de WMS. Isso mostra que qualidade não é apenas uma consulta: ela participa da movimentação controlada do material.

| Rota | Finalidade |
|---|---|
| `/setores/qualidade/liberar-lotes/` | Liberação de lotes. |
| `/setores/qualidade/area-vermelha/` | Reunião/área vermelha. |
| `/setores/qualidade/consulta-lote/` | Consulta de lotes destinados. |
| `/setores/qualidade/consulta-lote/rastreamento/` | Rastreamento de lote por empresa e lote; disponível também em Produção > Relatórios. |
| `/setores/qualidade/integracao-wms/` | Fila WMS. |

### 5.5 PCP

O PCP disponibiliza uma visão de calendário das OPs por estágio. A tela é somente de consulta: usa as datas do ERP para identificar em quais dias cada estágio estará em produção e permite restringir a visualização por máquina, origem, estágio, produto-derivação e situação da OP.

| Rota | Finalidade |
|---|---|
| `/setores/pcp/calendario-ops/` | Tela do Calendário de OPs. |
| `/setores/pcp/calendario-ops/eventos/` | Consulta JSON dos eventos exibidos no período e filtros selecionados. |
| `/setores/pcp/calendario-ops/detalhes/` | Consulta JSON do detalhamento do cálculo de comprometimento da OP selecionada. |

### 5.6 Manutenção

As rotas de manutenção conectam solicitacao, atendimento e recurso. O QR Code por recurso permite que o usuário abra chamado a partir do ponto físico de operação, reduzindo erro de seleção de equipamento. As ordens de serviço complementam o chamado com planejamento, responsáveis e execução.

| Rota | Finalidade |
|---|---|
| `/setores/manutencao/` | Lista chamados. |
| `/setores/manutencao/chamados/novo/` | Abre chamado. |
| `/setores/manutencao/recurso/<id>/qrcode/` | Gera QR Code para recurso. |
| `/setores/manutencao/os/` | Lista ordens de serviço. |
| `/setores/manutencao/os/abrir/` | Abre ordem de serviço. |

### 5.7 Suprimentos

| Rota | Finalidade |
|---|---|
| `/setores/suprimentos/componentes-a-separar/` | Necessidade real de separação de componentes das OPs abertas/em andamento (ver 8.11). |

### 5.8 WebSocket

As rotas WebSocket existem para dados que precisam chegar na tela sem recarregar a página. No caso da balança, a leitura `pesoBalanca` da telemetria HTTP pode ser enviada para a tela aberta do recurso. No caso de OP, a tela pode receber atualizacoes relacionadas a OP ativa.

| Rota | Consumidor | Finalidade |
|---|---|---|
| `/ws/balanca/<recurso_id>/` | `ConsumidorBalanca` | Atualização da balança em tempo real. |
| `/ws/op/<codbar>/` | `OPConsumer` | Atualização de OP ativa. |

---

*Verificado contra o código em 2026-09-02.*
