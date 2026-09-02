---
titulo: Visão geral
ordem: 0
---

# Documentação do SIGMA

Registro do que o SIGMA é e do ambiente em que roda. Descreve **o estado
atual**, não a história de como se chegou nele.

Base documental: projeto `SIGMA` e ambiente de produção `nex01`. Autoria
original: Silonei Duarte. Estes documentos vieram da divisão de um
documento mestre único (até 2026-08-19) em arquivos por assunto, no
mesmo padrão de numeração usado daqui em diante.

---

## Os documentos

| Documento | Assunto |
|---|---|
| [01 — Visão geral](01-visao-geral.md) | o que o sistema é, escopo, objetivos, organização funcional dos módulos |
| [02 — Arquitetura técnica](02-arquitetura-tecnica.md) | stack de backend e frontend, rede dos equipamentos, arquitetura lógica |
| [03 — Servidor e hospedagem](03-servidor-e-hospedagem.md) | infraestrutura, systemd, PostgreSQL/TimescaleDB, variáveis de ambiente de produção |
| [04 — Aplicativo mobile](04-aplicativo-mobile.md) | o app Android (Capacitor), notificações push, geração e assinatura do APK |
| [05 — Dados e bancos](05-dados-e-bancos.md) | PostgreSQL local, Oracle ERP e Alchemy, campos customizados, índices, modelos locais |
| [06 — Rotas e navegação](06-rotas-e-navegacao.md) | endereços internos por área do sistema |
| [07 — Integrações externas](07-integracoes-externas.md) | Oracle, SOAP Sapiens/Senior, WMS (API e DBLINK), Alchemy, telemetria HTTP, LDAP, e-mail — contratos e tratamento de erro |
| [08 — Operação, workers e monitoramento](08-operacao-e-workers.md) | workers em background, supervisor, timeout e reprocessamento, painel de status |
| [09 — Fluxos de negócio](09-fluxos-de-negocio.md) | sequenciamento, apontamento, qualidade, manutenção, componentes a separar |
| [10 — Parametrizações críticas](10-parametrizacoes.md) | parâmetros hierárquicos (filial → centro → recurso) que a regra de negócio consulta |
| [11 — Segurança e acessos](11-seguranca-e-acessos.md) | autenticação, autorização, observações de segurança, HTTPS e renovação de certificado |
| [12 — Sistema de design](Style-Guide-IPEL.md) | a interface do SIGMA: cores, tipografia, espaçamento, formas e componentes |
| [13 — Marca e identidade](13-marca-e-identidade.md) | a identidade própria do SIGMA — mascote, tom, onde aparece |
| [Documentação ERP](../erp-senior/Mapeamento_campos_USU.md) | dicionário de campos `USU_` customizados, índices Oracle e PostgreSQL — pasta `docs/erp-senior/` |
| [Arquivos da marca](../marca/) | pranchas e manuais originais da identidade visual — pasta `docs/marca/`, fora da numeração, não é texto de projeto |

---

## Documentos que não são publicados

Hoje o SIGMA não tem um visualizador de documentação embutido na própria
aplicação (diferente de outros sistemas da IPEL). Todos os documentos
acima ficam só no repositório. Se um visualizador nascer, o critério para
decidir o que fica público segue a mesma régua: *"como o sistema é"* pode
ser público; *"como trabalhar no projeto"* (convenção de código, roteiro
de dev) fica só no repositório.

| Documento | Conteúdo |
|---|---|
| [`../../CLAUDE.md`](../../CLAUDE.md) | como os agentes de IA trabalham neste projeto |
| `../../.claude/skills/` | o padrão de arquitetura, integração, teste, segurança e commit que o código deve seguir |
| [`../escopos/`](../escopos/) | documento de escopo de cada demanda de negócio — pedido, decisões datadas, bloqueios e reconciliação com produção; convenção e modelo dentro |

---

## Segredos

**Nenhuma credencial, chave ou senha existe neste repositório**, e nenhum
documento aqui indica onde elas estão guardadas.

- `.env` está no `.gitignore` e nunca deve ser commitado.
- `DJANGO_SECRET_KEY`, senha de banco e demais segredos são fornecidos
  fora do repositório (`.env` em dev, `/etc/sigma/sigma.env` em produção).
- Ao documentar qualquer configuração nova, cite o **nome** da variável,
  nunca o valor.

---

## Manutenção destes documentos

Estes arquivos só têm valor enquanto forem verdade. Ao alterar o servidor
ou a aplicação, atualize o documento correspondente **no mesmo commit**
da mudança (agente `documentador`).

Cada documento traz no rodapé a data da última verificação contra o
código ou o servidor real.

| Documento | Atualizar quando |
|---|---|
| 01 — Visão geral | mudar escopo, objetivo ou a organização de um módulo |
| 02 — Arquitetura técnica | mudar stack, estrutura de app, ou a arquitetura do tema visual |
| 03 — Servidor e hospedagem | mudar versão de PostgreSQL/TimescaleDB, configuração do systemd, ou variável de ambiente de produção |
| 04 — Aplicativo mobile | mudar versão do app, permissão, plugin, configuração do Firebase ou processo de build/assinatura |
| 05 — Dados e bancos | criar/alterar model local, campo `USU_` customizado no ERP, ou índice de performance |
| 06 — Rotas e navegação | criar, mover ou remover rota |
| 07 — Integrações externas | criar/alterar contrato de webservice, endpoint, payload, ou regra de tratamento de erro |
| 08 — Operação, workers e monitoramento | criar/alterar worker, mudar intervalo, timeout, ou o painel de status |
| 09 — Fluxos de negócio | mudar regra de um fluxo (apontamento, liberação, chamado...) |
| 10 — Parametrizações críticas | criar/alterar parâmetro hierárquico |
| 11 — Segurança e acessos | mudar permissão, política de acesso, ou certificado/TLS |
| 12 — Sistema de design | criar ou alterar token, componente ou estado — **antes** de a mudança virar CSS |
| 13 — Marca e identidade | chegar prancha nova, mudar o mascote ou o vocabulário de identidade |
| Documentação ERP (`docs/erp-senior/`) | mapear novo campo `USU_`, tabela ou índice do Oracle |
| `CLAUDE.md` / `.claude/skills` | mudar agente, skill, hook ou convenção de desenvolvimento |
