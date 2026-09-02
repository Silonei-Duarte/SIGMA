---
titulo: Escopo — Configurações da aplicação (variáveis não sensíveis em runtime)
---

# Escopo — Configurações da aplicação (variáveis não sensíveis em runtime)

**Aberta em:** 2026-08-29
**Última revisão:** 2026-08-30
**Status:** concluída

## Pedido

Tela genérica de configurações da aplicação — uma "tela de variáveis de
ambiente não sensíveis" editável em runtime, salva no banco, que passe a
valer sem reiniciar o servidor e sem os workers reconsultarem a tabela a
cada ciclo (cache em memória invalidado quando o dado muda). Primeiro
consumidor previsto: o relatório diário de falhas por e-mail
(`../../producao/services/relatorio_falhas_email.py`), cuja adaptação fica para
um trabalho seguinte. Pedido de 2026-08-29, pela operação/desenvolvimento.

## Estado por parte

| Parte | Implementado | Bloqueado / pendente |
|---|---|---|
| Model `ConfiguracaoAplicacao` (app `accounts`) | tabela `configuracoes_aplicacao` com chave única, valor, descrição e rastreio (`atualizado_por`/`atualizado_em`); migration `accounts/0024`; docstring do model proíbe gravação por `update()`/`bulk_update()`/SQL cru (não dispara signal, cache ficaria velho) | — |
| Service de leitura com cache in-process | `obter()`/`definir()` em `../../accounts/services/configuracoes.py`; invalidação por signal `post_save`/`post_delete`; guard anti-segredo na gravação **e na leitura** (`obter()` rejeita chave com padrão de segredo — decisão datada abaixo); `definir()` normaliza a chave e valida formato também fora da tela; revalidação sob lock no preenchimento do cache | — |
| Tela lista (por tópico) e editar por chave | `/configuracoes/` com permissão `accounts.configurar_aplicacao`; **desenho revisado pelo dono do produto em 2026-08-29: a chave é parte do código** — a listagem mostra só as chaves declaradas em `CHAVES_CONHECIDAS`, agrupadas pelo tópico declarado, e a edição (por NOME de chave, não por pk) oferece só descrição e valor; "Voltar ao padrão" (`POST /configuracoes/padrao/<chave>/`, só com linha salva) exclui a linha por instância e restitui o default do código; sem criar chave pela tela, e linha excluída por qualquer via volta a mostrar o default do código | — |
| Chaves conhecidas | `RELATORIO_FALHAS_EMAIL_DESTINATARIOS`, `RELATORIO_FALHAS_HORARIOS`, `RELATORIO_FALHAS_LIMIAR_ATRASO_MINUTOS` — com descrição, default e validador em código | — |
| Consumidor: worker do relatório de falhas | `relatorio_falhas_email` lê as três chaves via `obter()` no início de cada apuração (vale sem reinício); cadência por horários configurados, com estado persistido em `EstadoRelatorioFalhas` (singleton pk=1, migration `producao/0050`): falha de envio re-tenta o mesmo horário, reinício não reenvia horário cumprido, "não foi possível apurar" conta como horário cumprido; sem horários ou sem destinatários o relatório fica desativado (aviso em log); valores plantados fora do validador são ignorados na leitura com aviso (limiar inválido cai no padrão) | — |
| Fim da configuração em variável de ambiente | `RELATORIO_FALHAS_EMAIL_DESTINATARIOS` e `RELATORIO_FALHAS_LIMIAR_ATRASO_MINUTOS` removidos de `../../SIGMA/settings.py` e `../../.env.example` — o worker não lê mais variável; quem tinha as linhas no `../../.env`/`sigma.env` cadastra os valores na tela e remove-as (roteiro abaixo) | — |
| Correção de infraestrutura de e2e | `../../conftest.py` agora monta o banco de teste para a marca `e2e` (antes, e2e-only rodava contra o banco de desenvolvimento); baselines visuais de `producao` regeneradas no ambiente isolado | revisão visual das baselines novas (configurações e producao) — bloqueio abaixo |

## Decisões datadas

| Data | Decisão | Quem decidiu (papel) | Alternativa descartada |
|---|---|---|---|
| 2026-08-29 | Configuração da aplicação mora no app `accounts`, onde vive o painel de serviços (`../../accounts/views/services.py`) — é administração do sistema | backend, seguindo sugestão da demanda | `producao` (área de negócio, não de administração) |
| 2026-08-29 | Cache in-process com preenchimento lazy (primeira leitura), invalidado por signals; sem TTL nem reconsulta periódica | backend, conforme desenho da demanda | carga total ao iniciar (`../../accounts/apps.py` evita banco no bootstrap; lazy é equivalente pelos signals) |
| 2026-08-29 | Permissão própria `accounts.configurar_aplicacao` (pós-migrate) em vez da permissão padrão `change` do model | backend | permissão `change` nativa — o projeto desliga `create_permissions` no `../../manage.py`, ela não existiria em produção |
| 2026-08-29 | Valor exibido sem máscara na tela | backend | mascarar valores — a política da tela é não sensível; guard rejeita chave com nome de segredo e valor com aparência óbvia de credencial só gera aviso em log |
| 2026-08-29 | Log de auditoria em `definir`/remoção registra ator, chave e ação — nunca o valor | backend, seguindo a skill `auditoria` | registrar o valor no log (a chave é genérica; o rastreio consultável vive no registro e na tela) |
| 2026-08-29 | Guard anti-segredo também na **leitura**: `obter()` rejeita chave com padrão de segredo, não só a gravação | sênior, na revisão da demanda | rejeitar só na escrita — linha gravada por shell/migração escaparia da guard da gravação e a leitura viraria a superfície que serve a credencial; falha explícita vale mais que valor silencioso |
| 2026-08-29 | Cadência do relatório de falhas por **horários configurados** (`RELATORIO_FALHAS_HORARIOS`), com estado persistido em `EstadoRelatorioFalhas` (singleton pk=1): falha de envio re-tenta o mesmo horário, reinício não reenvia horário cumprido, envio "não foi possível apurar" conta como horário cumprido | o time, na evolução da demanda | manter o disparo único 1×/dia do desenho original — horário fixo no código não cobre jornada que começa depois dele e não se ajusta sem redeploy |
| 2026-08-29 | Configuração do relatório mora exclusivamente na tela: `RELATORIO_FALHAS_EMAIL_DESTINATARIOS` e `RELATORIO_FALHAS_LIMIAR_ATRASO_MINUTOS` saíram de `settings.py`/`../../.env.example` | o time, na evolução da demanda | manter a variável de ambiente como fallback — duas fontes de verdade para o mesmo valor |
| 2026-08-29 | Corrigir `../../conftest.py` para a marca `e2e` montar o banco de teste | backend — achado de infraestrutura exposto pela tela nova | manter e2e contra o banco de desenvolvimento (a tela nova gravaria/apagaria dados reais de dev) |
| 2026-08-29 | **A chave é parte do código, não da tela**: `ChaveConhecida` ganha `topico`; a tela lista só chaves declaradas, agrupadas por tópico, e edita apenas descrição/valor por NOME de chave — sem criar/remover; linha excluída por qualquer via reaparece com o default do código | dono do produto, na revisão da tela (implementação: `backend`) | manter criação/remoção pela tela (duplicação de chave e linha órfã, que o default do código já resolve) |
| 2026-08-29 | Ação **"Voltar ao padrão"** na tela de edição (`POST /configuracoes/padrao/<chave>/`): exclui a linha da chave por instância (o signal `post_delete` é quem invalida o cache — update/delete em queryset não disparam), log registra quem voltou qual chave sem o valor, e a listagem volta a mostrar o default | dono do produto; implementação `backend` | deixar a volta ao padrão só para shell/ORM (ação rotineira de operação merece botão, e a tela é a superfície da configuração) |

## Bloqueios por falta de dado

| O que falta | Com quem está | Desde quando |
|---|---|---|
| Revisão visual das baselines de screenshot novas (configurações desktop/mobile e producao desktop/mobile) — este agente não inspeciona imagens | sênior/usuário | 2026-08-29 |

## Ponto de retomada

A troca de fonte aconteceu: o worker lê a configuração do banco e as
variáveis saíram de `settings.py`/`../../.env.example`. A implementação está
commitada no repositório. O que resta depende de pessoa: a conferência
visual das baselines de screenshot (bloqueio abaixo) e a publicação
manual em produção — `manage.py migrate` (tabelas
`configuracoes_aplicacao` e `producao.estado_relatorio_falhas`),
concessão da permissão `accounts.configurar_aplicacao` e configuração
dos valores das chaves na tela (o roteiro abaixo), se os padrões não
servirem — as chaves já aparecem na listagem com o default do código,
sem cadastro prévio.

## Roteiro operacional de migração da configuração (2026-08-29)

Quem mantinha a configuração do relatório por variável de ambiente
(`../../.env` em desenvolvimento, `/etc/sigma/sigma.env` em produção) migra para
a tela **Configurações da aplicação** — as três chaves já estão declaradas
em código e aparecem na tela com os padrões (destinatários `ti@ipel.ind.br`,
horários `07:00,16:00`, limiar 5); o trabalho é só ajustar os valores:

1. Editar `RELATORIO_FALHAS_EMAIL_DESTINATARIOS` (um e-mail por linha) e
   `RELATORIO_FALHAS_LIMIAR_ATRASO_MINUTOS` (minutos, 1 a 1440) se os
   padrões não servirem.
2. Editar `RELATORIO_FALHAS_HORARIOS` se a cadência padrão (07:00,16:00)
   não servir.
3. Remover as linhas do arquivo de ambiente: o worker não lê mais essas
   variáveis; a linha sobrante não tem efeito, mas fica órfã e engana
   quem lê o arquivo.

O valor cadastrado vale na próxima apuração, sem reinício. A credencial do
canal de e-mail continua no arquivo de ambiente — nada de segredo na tela.
A ação **Voltar ao padrão** na edição exclui a linha e restabelece os
padrões do código (não "desativa": o padrão de horários/destinatários é
preenchido).

## Reconciliação com produção

Nada desta demanda está confirmado em produção: o código está commitado
no repositório e a publicação é manual, por SSH, pelo desenvolvedor
sênior — nada indica que o deploy ocorreu. Em produção a tela só ficará
acessível após `manage.py migrate` (tabelas `configuracoes_aplicacao` e
`estado_relatorio_falhas`) e concessão da permissão
`accounts.configurar_aplicacao` (staff/superusuário já passam pelo bypass
do decorator). Com os padrões declarados em código (destinatários
`ti@ipel.ind.br`, horários `07:00,16:00`), o relatório de falhas já nasce
ATIVO em produção no primeiro deploy — o ajuste na tela é opcional, para
trocar destinatários/horários/limiar.

---

*Verificado contra o código em 2026-08-30.*
