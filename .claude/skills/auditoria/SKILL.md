---
name: auditoria
description: Padrão do SIGMA para separar trilha de auditoria de log operacional, registrar ações relevantes sem vazar segredo e revisar rastreabilidade. Use ao alterar acesso, dado de negócio, integração, log ou histórico de alterações.
paths: "**/views/** **/services/** **/models/** **/admin.py **/tests/**"
---

# Auditoria e registro no SIGMA

Trilha de auditoria e log operacional não são a mesma coisa.

| | Trilha de auditoria | Log operacional |
|---|---|---|
| Pergunta | quem fez o quê e quando? | por que falhou e como operar? |
| Leitor | gestão, segurança e suporte autorizado | desenvolvimento e operação |
| Conteúdo | fato de negócio estável e consultável | diagnóstico técnico e contexto da execução |

## Regras

1. Ação relevante ocorre primeiro; o registro descreve um resultado já
   persistido. Se a ação e a trilha pertencem à mesma transação, ambas usam a
   mesma transação.
2. Nunca registrar senha, token, cookie, cabeçalho de autenticação, URL com
   credencial, payload SOAP/REST bruto ou dado pessoal sem necessidade.
3. A trilha guarda ator, ação, objeto, escopo de empresa/filial quando houver,
   instante e resumo seguro. Ela é somente leitura para usuários comuns.
4. Log técnico usa nível adequado, contexto mínimo e `logger.exception` para
   diagnóstico; a resposta HTTP para a pessoa continua genérica.
5. Coletas recorrentes não geram uma trilha por linha. Registre uma execução
   agregada ou mantenha o registro de fila/execução existente.

## Estado atual

O SIGMA possui registros de fila e logs por integração, mas não uma trilha
genérica única. Não crie uma tabela ou tela de auditoria incidentalmente em
uma feature: proponha o desenho usando
[references/trilha-de-auditoria.md](references/trilha-de-auditoria.md) e
aguarde a decisão de escopo.

Uma feature nova pode ter seu próprio registro auditável, sem esperar a
trilha genérica, quando reúne quatro propriedades ao mesmo tempo: registro
do próprio objeto da ação, tela consultável, permissão própria e caráter
append-only na prática. Ação auditável que não reúna as quatro não repete
essa saída — implementa a base genérica acima (ou aguarda o desenho dela).

## Referências

| Arquivo | Quando ler |
|---|---|
| [references/logs.md](references/logs.md) | ao criar ou revisar logs e tratamento de exceção |
| [references/trilha-de-auditoria.md](references/trilha-de-auditoria.md) | ao propor a implementação futura de histórico consultável |
