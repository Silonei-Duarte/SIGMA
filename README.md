# SIGMA

Sistema integrado de gestão e monitoramento da operação industrial. Conecta o chão de fábrica com os sistemas corporativos — ERP Senior/Sapiens, WMS, Oracle Alchemy e banco local PostgreSQL — sem substituí-los: atua como camada operacional entre o usuário de fábrica e esses sistemas.

## Módulos

### Produção
- **Sequenciamento** — distribui ordens de produção por recurso, com ordenação automática por menor saldo disponível
- **Apontamento de OP** — registra produção local e envia ao ERP via webservice Sapiens (fila com reprocessamento automático); inclui a versão Multi-OP para recursos que acoplam várias OPs, com rateio do consumo de bobina entre elas
- **Apontamento de componentes** — resolve palete WMS ou lote ERP e efetiva a baixa no ERP; aciona ajuste no WMS quando aplicável
- **Correção de quantidade de lote** — complementa um apontamento (aumento) ou confirma a quantidade final no ERP (redução), sem fila local própria
- **Status de recursos** — painel em tempo real com OP ativa, operador, produção do turno e paradas em aberto

### Qualidade
- **Liberação de lotes** — movimenta lotes no ERP e cria registro no WMS; suporta liberação direta e área vermelha
- **Área vermelha** — controle por reunião; bloqueia registros até fechamento; suporta refugo, reclassificação e destinação para prensa, com rastreabilidade de centro de custo
- **Consulta de lote e rastreamento** — histórico de movimentos ERP cruzado com análises Oracle Alchemy; impressão de etiqueta Code128 + QR Code
- **Integração WMS** — sincroniza paletes, saldos e locais via API HTTP e DBLINK Oracle

### PCP
- **Calendário de OPs** — consulta do planejamento e execução dos estágios das OPs no ERP, com cálculo de comprometimento por produto/derivação

### Logística
- **Movimentação de componentes** — painel de consumo de componentes por OP/recurso, com consulta de lotes já baixados e de paletes/lotes disponíveis no WMS

### Suprimentos
- **Componentes a separar** — consolida a necessidade real de separação de componentes das OPs abertas, descontando o saldo já disponível na planta e rateando por prioridade de OP

### Manutenção
- Chamados abertos por tela ou por QR Code fixado no recurso, com responsáveis, observadores e interações
- Ordens de serviço vinculadas a chamados ou abertas diretamente, com notificações por e-mail

### Telemetria e OEE
- Coleta HTTP contínua por recurso (balança, bobina, sensores), com atualização em tempo real via WebSocket e detecção automática de parada por regra configurável
- Cálculo de planejado OEE por turno e dia, a partir de calendário, turnos e horas extras

## Integrações

| Sistema | Tipo | Uso |
|---|---|---|
| ERP Senior/Sapiens | SOAP (webservice) | Apontamentos, movimentos de lote, baixas de componentes, correções de quantidade, tempos de produção |
| Oracle ERP | Consulta direta | OPs, lotes, saldos, operadores, campos customizados |
| WMS XC | API HTTP/JSON | Criação de lote, ajuste de estoque |
| WMS via DBLINK Oracle | Consulta direta | Paletes, saldos, locais |
| Oracle Alchemy | Consulta direta | Análises de bobina para rastreamento de qualidade |
| Telemetria HTTP | Fonte JSON por recurso | Leitura de balança e sensores de recurso |
| Active Directory | LDAP sobre TLS | Autenticação e autorização dos usuários |
| Firebase FCM | Push | Notificações no aplicativo Android |
| Microsoft Graph (Microsoft 365) | E-mail | Notificações do módulo de manutenção; relatório diário de falhas das filas |

## Stack

- **Backend:** Python ≥3.14 · Django 6 · Daphne (ASGI) · Django Channels (WebSocket)
- **Banco local:** PostgreSQL + TimescaleDB
- **Frontend:** Templates Django · Tailwind CSS · ícones Lucide · JavaScript
- **Mobile:** Capacitor → APK Android, notificações push via Firebase (FCM)

## Workers em background

Executam dentro do próprio processo Django. Um supervisor reinicia automaticamente qualquer worker com falha. Trava via advisory lock no PostgreSQL garante execução única por instância.

| Worker | Função |
|---|---|
| `envia_pendencias` | Coordena todas as filas de integração |
| `fila_logs_apontamentos` | Envia apontamentos de OP ao ERP |
| `fila_tempos_erp` | Envia pacote de produção e paradas ao ERP |
| `fila_log_apontamento_componentes` | Envia baixas de componentes ao ERP |
| `fila_baixa_componentes` | Envia ao ERP as baixas de bobina de matéria-prima geradas pela tela Multi-OP |
| `fila_wms_integracoes` | Envia pendências ao WMS |
| `fila_consulta_lotes` | Libera lotes no ERP |
| `importa_palete` | Sincroniza paletes WMS ↔ ERP |
| `sincroniza_ops_encerradas` | Fecha OPs encerradas no ERP |
| `consolida_tempos_erp` | Consolida tempos de produção (4×/dia) |
| `oee_planejado` | Recalcula planejado OEE |
| `coleta_telemetria` | Coleta HTTP JSON por fonte; também atualiza bobina atual dos recursos |
| `relatorio_falhas_email` | Envia, nos horários configurados na tela Configurações da aplicação, o relatório de falhas das filas e da telemetria por e-mail — somente se houver pendência |

## Docker

Existe uma imagem única (aplicação + PostgreSQL/TimescaleDB + Nginx, sem
TLS nesta versão) para rodar o SIGMA rápido em qualquer máquina. Ver [`docker/README.md`](docker/README.md).

## Documentação

Documentação técnica completa em [`docs/sigma/README.md`](docs/sigma/README.md) (índice dos documentos 01 a 13).
