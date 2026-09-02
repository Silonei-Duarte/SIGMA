---
titulo: Visão geral e escopo
ordem: 1
---

## 1. Sumário executivo

O SIGMA conecta a operação industrial diária com os sistemas corporativos que registram produção, estoque, qualidade e manutenção. Na prática, ele funciona como uma camada operacional entre o usuário de fábrica e os sistemas como ERP Senior/Sapiens, WMS, Alchemy, telemetria HTTP de equipamentos e banco local PostgreSQL.

O objetivo do sistema não é apenas "mostrar telas". Ele organiza fluxos que normalmente ficariam espalhados entre apontamentos manuais, consultas ao ERP, decisões de qualidade, controles de lote, movimentações de estoque, chamados de manutenção e acompanhamento de recursos. Por isso, o SIGMA possui duas naturezas ao mesmo tempo: é um portal operacional para usuários e também um integrador técnico entre sistemas.

Quando um operador aponta uma OP, quando a qualidade libera um lote, quando um componente é consumido, quando uma pendência precisa ir ao WMS ou quando uma balança envia leitura em tempo real, o SIGMA registra, valida, envia, interpreta retorno e mantém rastreabilidade. Essa rastreabilidade é importante porque a operação industrial não pode depender de uma chamada externa perfeita o tempo todo. Se ERP ou WMS falham, o sistema precisa deixar claro o que ficou pendente, o que foi integrado e o que precisa de reprocessamento.

O sistema tem três papéis principais:

1. Interface operacional para usuários de produção, qualidade, manutenção e administração.
2. Camada de integração entre dados locais, ERP Senior/Sapiens, WMS, Oracle Alchemy e telemetria HTTP de recursos.
3. Orquestrador de filas e serviços em background, com controle de status, timeout e reprocessamento.

Em linguagem simples: o SIGMA recebe a ação do usuário, consulta o que precisa nos bancos externos, grava uma trilha local no PostgreSQL, chama ERP ou WMS quando necessário e depois mostra se a ação foi concluída ou se ficou pendente.

## 2. Visão funcional, escopo e objetivos

O escopo do SIGMA cobre os processos que precisam unir operação de fábrica, rastreabilidade local e integração com sistemas externos. Ele não substitui o ERP nem o WMS. O papel dele é facilitar a execução operacional, reduzir retrabalho e registrar uma trilha própria do que foi feito, enviado, aceito ou recusado.

O principal objetivo de negócio é reduzir a distância entre o que acontece na fábrica e o que precisa ficar registrado nos sistemas oficiais. Em vez de depender de planilhas, consultas manuais, chamadas diretas ao ERP ou controles paralelos, o sistema concentra os fluxos em uma interface única e registra a trilha operacional.

Outro objetivo central é dar visibilidade ao erro. Uma integração pode falhar por indisponibilidade de ERP, retorno inválido, timeout, dado incorreto ou regra de negócio recusada. O SIGMA precisa deixar a pendência visível e reprocessável, em vez de simplesmente perder a ação ou obrigar o usuário a repetir tudo manualmente.

Tecnicamente, o SIGMA separa controle local de efetivação externa. O PostgreSQL local guarda a operação do SIGMA: filas, logs, parâmetros, cadastros, reuniões, chamados e paradas de máquina. O banco Oracle ERP, Alchemy e XC WMS são consultados para buscar informações oficiais ou complementares. As alterações no ERP são feitas quase que unicamente por webservices Sapiens/Senior, respeitando as regras do ERP.

### 2.1 Áreas atendidas

Na parte de cadastro e parametrização, o sistema controla a estrutura usada pelos demais fluxos: empresas, filiais, departamentos, setores, centros de recurso, recursos, turnos, calendários, horas extras e taras. Esses cadastros não são apenas informativos. Eles definem como cada recurso trabalha, quais depósitos devem ser usados, quais parâmetros se aplicam por filial ou centro e como o OEE deve calcular o planejado.

Na autenticação, o SIGMA usa login Django e integração LDAP/Active Directory. Isso permite que o acesso acompanhe o ambiente corporativo. O usuário pode ser criado ou atualizado automaticamente a partir do AD, mas continua tendo dados locais necessários para operação, como filial, operador ERP e página inicial.

Na produção, o sistema cobre sequenciamento de OPs, apontamento de OP, apontamento de componentes, correção de quantidade de lote, logs de integração, status de recursos e controle de OP ativa por recurso. Essa área transforma a ação da fábrica em registro local e, quando aplicável, em chamada ao ERP Senior/Sapiens.

Na qualidade, o sistema cobre liberação de lotes, área vermelha, consulta de lotes, rastreamento, etiquetas, observações de etiqueta e integração WMS. A decisão de qualidade pode gerar efeitos diferentes: liberar lote, mandar para área vermelha, refugar, reclassificar, destinar para prensa, transferir produto ou criar pendência WMS.

Na manutenção, o sistema controla chamados, QR Code por recurso, ordens de serviço, interações e notificações por e-mail. O objetivo é vincular problemas e atendimentos aos recursos produtivos, criando histórico de manutenção e comunicação entre solicitantes, responsáveis e observadores.

Em suprimentos, o sistema consolida a necessidade real de separação de componentes das OPs abertas/em andamento, descontando o que já está disponível na planta e rateando o saldo por prioridade da OP. O objetivo é dar ao setor uma visão única de o que precisa ser levado à fábrica, sem depender de checagem manual máquina a máquina.

No OEE e status de recursos, o SIGMA coleta telemetria HTTP para atualizar balança em tempo real e consolida planejado diário com base em calendário, turnos e horas extras. As paradas de máquina são registradas em tabela própria, permitindo identificar se existe parada em aberto por recurso.

Manutenção e OEE operam em produção: chamados e ordens de serviço vinculados a recursos, coleta de telemetria HTTP e parada automática por sinal já sustentam a rotina diária da fábrica — o detalhe operacional de cada fluxo está em [08 — Operação, workers e monitoramento](08-operacao-e-workers.md) e [09 — Fluxos de negócio](09-fluxos-de-negocio.md).

Nas integrações, o sistema conversa com PostgreSQL local, Banco Oracle ERP Senior, webservices Sapiens G5, WMS XC API, WMS via DBLINK Oracle, Banco Oracle Alchemy, telemetria HTTP, WebSocket e SMTP Microsoft 365. Cada integração tem uma responsabilidade própria: algumas consultam dados, outras efetivam movimentos e outras servem para notificação ou tempo real.

### 2.2 Objetivos consolidados

Os objetivos de negócio são:

- Reduzir operação manual entre produção, qualidade, ERP e WMS.
- Garantir rastreabilidade local das integrações enviadas ao ERP e WMS.
- Apoiar decisões de qualidade sobre liberação, refugo e reclassificação de lotes.
- Concentrar status de recursos e apontamentos em uma interface única.
- Permitir reprocessamento controlado de pendências quando uma integração falha.
- Integrar operação de manutenção ao cadastro de recursos.

Os objetivos técnicos são:

- Manter uma base local PostgreSQL como controle operacional e fila de integração.
- Consultar Oracle ERP e Oracle Alchemy sem copiar dados desnecessários.
- Efetivar movimentos no ERP via webservices oficiais Sapiens/Senior.
- Enviar eventos de WMS via API HTTP JSON.
- Executar workers automáticos com monitoramento de timeout.
- Evitar duplicidade de workers usando trava no PostgreSQL.
- Expor telas em tempo real via WebSocket quando necessário.

### 2.3 Organização funcional

A organização funcional abaixo não representa cronograma nem ordem de desenvolvimento. Ela serve para decompor o SIGMA mm blocos compreensiveis. A ideia é responder: "quais grandes partes formam o sistema?" e "que entregas existem dentro de cada parte?".

Para leitores não técnicos, esta divisão deve ser lida como um mapa de responsabilidades. Por exemplo, "Produção" concentra tudo que envolve OP, sequenciamento, apontamento e componentes. "Qualidade" concentra liberação de lote, área vermelha, rastreamento e WMS. "Integrações externas" agrupa os pontos em que o SIGMA deixa de trabalhar apenas com dados locais e passa a consultar ou enviar informações para outros sistemas.

Essa divisão também ajuda a entender impacto de mudanças. Uma alteração em "Parâmetros de filial", por exemplo, pode afetar Produção e Qualidade, porque os mesmos parâmetros definem depósitos, transacões e locais usados nos fluxos de integração.

- **1.1 Aplicação web:** estrutura da aplicação web, rotas, telas, renderização das páginas e entrada ASGI usada pelo servidor.
- **1.2 Autenticação:** login de usuários, integração com LDAP/Active Directory, grupos, permissões e controle de acesso às telas.
- **2.1 Estrutura empresarial:** cadastro e organização de empresa, filial, departamento e setor, usados como base para permissões, filtros e parâmetros.
- **2.2 Estrutura produtiva:** cadastro de centros de recurso, recursos produtivos e parâmetros operacionais usados por produção, OEE, manutenção e integrações.
- **2.3 Calendário e turnos:** definição de calendário, eventos, turnos base, turnos por recurso e horas extras para cálculo de disponibilidade e planejado.
- **3.1 Sequenciamento:** consulta de OPs no ERP, organização da sequência por recurso e manutenção da ordem operacional local.
- **3.2 Apontamento OP:** tela de apontamento da produção, geração de registros locais, envio ao ERP por webservice e acompanhamento dos retornos. Inclui a versão Multi-OP (View 3) para recursos que acoplam várias OPs ao mesmo tempo mas apontam uma por vez, com consumo de bobina de matéria-prima rateado entre elas.
- **3.3 Apontamento componente:** registro do consumo de componentes, validação do contexto ERP/WMS, envio ao ERP e ajuste de estoque quando aplicável. Inclui a baixa de bobina de matéria-prima gerada pela View 3, enviada por webservice próprio (`TratarBaixa`).
- **4.1 Liberação de lote:** consulta de dados no ERP e Alchemy, decisão de qualidade, criação da liberação local e envio ao WMS quando houver novo lote.
- **4.2 Área vermelha:** controle de reunião, definição de destino do lote, comunicação com ERP/WMS e uso de dados de qualidade do Alchemy.
- **4.3 Consulta e etiqueta:** consulta de lotes e saldos no ERP, visualização do resultado e emissão de etiqueta em PDF/HTML.
- **4.4 Rastreamento:** acompanhamento da cadeia do lote, movimentos no ERP e informações complementares de qualidade vindas do Alchemy. A tela permite informar empresa e lote diretamente; também é aberta pelos links de Consulta de Lotes e Área Vermelha quando o lote já está definido. Antes da consulta pesada, abre imediatamente com o estado `Rastreando lote...`.
- **5.1 Chamados:** abertura e acompanhamento de chamados por recurso, QR Code, responsáveis, interações e notificações por e-mail.
- **5.2 Ordens de serviço:** controle de ordens de serviço, responsáveis, interações, histórico operacional e comunicação por e-mail.
- **5.3 Componentes a Separar:** consolidação da necessidade real de separação de componentes das OPs abertas/em andamento, descontando saldo da planta e rateando por prioridade/recurso.
- **6.1 Telemetria HTTP:** coleta contínua de valores JSON dos recursos, interpretação tipada, atualização de balança, armazenamento de leituras e avaliação automática de parada por sinal.
- **6.2 OEE planejado:** consolidação do planejado diário, uso de calendário/turnos e reprocessamento quando dados operacionais mudam.
- **7.1 ERP Oracle:** consultas diretas ao Oracle ERP para buscar OP, lote, saldo, movimentos, operadores e demais informações oficiais.
- **7.2 ERP Sapiens SOAP:** envio de apontamentos, componentes, correções de lote e movimentações para efetivação pelas regras do ERP Senior/Sapiens.
- **7.3 WMS API:** envio de novo lote, ajuste de estoque e pendências de integração relacionadas ao WMS.
- **7.4 Alchemy:** consulta de análises de bobina e dados complementares usados nos fluxos de qualidade e rastreamento.
- **8.1 Hospedagem:** execução em Ubuntu Server com systemd, Daphne, Nginx, PostgreSQL local e variáveis de ambiente.
- **9.1 Workers:** execução dos serviços em background, controle de filas, timeout, status operacional e reprocessamento.

### 2.4 Módulos do sistema

O SIGMA possui uma base de configuração que sustenta todos os módulos: bancos de dados, integrações externas, autenticação, e-mail, arquivos estáticos, fuso horário, idioma, rotas HTTP e rotas WebSocket. Essa base define como a aplicação se conecta aos sistemas externos, como publica suas telas e quais valores vêm do ambiente de execução em vez de ficarem fixos no código.

Cadastros, usuários e estrutura fabril sustentam todos os outros módulos. Eles definem quem usa o sistema, a qual filial o usuário pertence, quais empresas existem, como a fábrica está organizada e quais recursos produtivos podem receber apontamentos, chamados, turnos e telemetria.

A estrutura principal segue esta hierarquia:

```text
Empresa -> Filial -> Departamento -> Setor -> Centro de Recurso -> Recurso
```

Os parâmetros de integração também seguem uma regra de herança. Primeiro o sistema usa o parâmetro da filial. Se houver configuração no centro de recurso, ela substitui a configuração da filial. Em alguns casos, o recurso possui parâmetros próprios, que ficam acima dos demais. Essa hierarquia evita repetir configurações e permite exceções por máquina ou centro.

Autenticação, permissões e segurança de acesso controlam quem entra e o que cada usuário pode fazer. A autenticação principal usa LDAP/Active Directory, permitindo que usuários corporativos entrem com suas credenciais de rede. Depois do login, o acesso às telas é controlado por permissões Django e por regras de staff/superusuário.

O módulo de produção cobre a rotina operacional da fábrica. Ele consulta OPs no ERP, permite organizar sequenciamento local, registra apontamentos, controla OP ativa por recurso, envia apontamentos ao ERP e mantém logs locais para reprocessamento. O ponto mais importante desse módulo é a fila local: um apontamento não depende de o ERP responder imediatamente para existir no SIGMA.

O módulo de qualidade controla a destinação dos lotes após produção. Ele consulta saldos e situação no ERP, consulta dados de análise no Alchemy, localização do lote no WMS ou nos Paramêtros, permite liberar lotes, conduzir reuniões de área vermelha, registrar refugo/reclassificação/destinação para prensa, gerar etiquetas, rastrear lotes e enviar pendências ao WMS.

O módulo de manutenção registra problemas e atividades de manutenção ligadas aos recursos da fábrica. Chamados podem ser abertos pela tela ou por QR Code do recurso. Ordens de serviço organizam execução, responsáveis, previsao, status e histórico de interações.

OEE, telemetria HTTP e paradas de máquina acompanham sinais dos recursos. O SIGMA coleta valores HTTP configurados por fonte, atualiza a balança em tempo real via WebSocket, avalia regras de parada por sinal, registra paradas em tabela própria e recalcula planejado OEE a partir de turnos, calendários e horas extras.

### 2.5 Fora do escopo desta Versão

Este documento ainda não substitui uma validação formal com usuários-chave. Ele descreve o sistema a partir do projeto, das configurações e do ambiente de produção, mas algumas regras devem ser alinhadas com as áreas de negócio para garantir que o comportamento documentado corresponde ao processo aprovado.

Também não faz parte desta Versão um desenho BPMN formal, um manual operacional tela a tela, um inventario completo de permissões por grupo real no banco de produção, uma auditoria de segurança ou uma revisao de performance baseada em metricas historicas. Esses itens podem ser produzidos depois, usando esta documentação como base.

---

*Verificado contra o código em 2026-09-02.*
