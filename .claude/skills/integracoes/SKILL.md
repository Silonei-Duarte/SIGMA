---
name: integracoes
description: Como o SIGMA integra com outros sistemas — Oracle (ERP Senior, Alchemy), SOAP do Sapiens/Senior, WMS XC (API HTTP e DBLINK Oracle), telemetria HTTP, Active Directory (LDAP), Firebase (push) e SMTP. Traz o que existe hoje sem gateway único, o desenho de fila local que já funciona (status → worker → scheduler), a decisão fila × consulta ao vivo, e as regras que não se negociam. Use antes de escrever ou revisar qualquer código que fale com um sistema de fora. Dispara em "integração", "Oracle", "Sapiens", "SOAP", "WMS", "telemetria", "Active Directory", "LDAP", "Firebase", "notificação", "e-mail", "worker", "fila", "agendamento", "sincronização", "token".
paths: "accounts/services/** producao/services/** producao/utils/** producao/views/** setores/**/utils/** setores/**/views/** telemetria/services/**"
---

# Integrações no SIGMA

O SIGMA lê e efetiva em outros sistemas **sem substituí-los**: consulta
Oracle direto para ERP Senior e Alchemy, efetiva no ERP só por webservice
SOAP do Sapiens, fala com o WMS por API HTTP e por DBLINK Oracle,
autentica no Active Directory por LDAP, coleta telemetria HTTP de equipamento, envia
push por Firebase e e-mail por SMTP.

**O SIGMA ainda não tem um client único para todos os sistemas.** Este
documento separa o que já é compartilhado do que ainda é dívida, para que
código novo reutilize a camada certa e não aumente duplicações.

---

## O que existe hoje, por sistema

| Sistema | Transporte | Onde mora | Gateway único? |
|---|---|---|---|
| Oracle ERP / Alchemy | `SIGMA.integracoes.oracle` sobre os aliases Django (`SIGMA/settings.py`) | `cursor_oracle_erp()` e `cursor_oracle_alchemy()` centralizam abertura e fechamento de cursores | **Sim.** Consumidores usam o client, sem `oracledb.connect()` nem cursor direto. |
| SOAP Sapiens | `producao/services/sapiens.py` + helper de protocolo `producao/utils/sapiens_soap.py` | transporte compartilhado; consumidores montam somente o envelope e interpretam a resposta | **Sim.** Use `enviar_soap_sapiens()` para toda chamada HTTP SOAP. |
| WMS (API HTTP) | `requests`, payload em `setores/qualidade/utils/wms_integracao.py` | `setores/qualidade/views/wms_views.py`, `liberar_lotes.py`, `liberar_area_vermelha.py` | **Não.** Sem client, cada view monta a chamada. |
| WMS (DBLINK Oracle) | consulta Oracle via DBLINK, mesmo alias `oracle_erp` ou dedicado, conforme a view | espalhado, ver arquivos de qualidade/suprimentos | **Não.** |
| Active Directory (LDAP) | `django_auth_ldap` | `AUTHENTICATION_BACKENDS` em `SIGMA/settings.py` | **Sim** — é o backend padrão do pacote, sem bind manual paralelo. |
| Telemetria HTTP | `requests` | `telemetria/services/coleta.py` | **Sim.** Coleta fontes JSON e republica `pesoBalanca` via Channels para WebSocket. |
| Firebase (push) | `firebase-admin` | `accounts/services/notificacoes.py` | Sim, um serviço central de envio (ver `docs/sigma/04-aplicativo-mobile.md` §3.6.2). |
| SMTP (e-mail) | Django `EmailBackend` customizado (`SIGMA/email_backends`) | usado pelo módulo de manutenção | — |

**Não crie um segundo cliente de telemetria, Oracle, Sapiens, uma segunda config LDAP
ou um segundo serviço Firebase.** Para WMS, onde ainda não há client único,
reaproveite o helper local existente e não invente uma terceira forma de
fazer a mesma coisa.

---

## A primeira decisão: fila ou consulta ao vivo?

| A pergunta é... | Família | Grava? |
|---|---|---|
| "status de todas as OPs abertas, pra tela/painel recarregar" | **fila local** (o padrão de `Apontamento`, `PacoteTempoERP`) | sim, com status e reprocessamento |
| "qual o saldo do lote X agora", sob ação de gente | **consulta ao vivo** | não |
| "o WMS/Sapiens recebeu, preciso confirmar que efetivou" | **fila de envio** (grava intenção antes de mandar) | sim, intenção + desfecho |
| "equipamento fornece leitura" | **telemetria HTTP**, já com coletor único | sim, se for persistir; não, se for só broadcast em tempo real |

Errar aqui é caro: dezenas de telas recarregando não podem virar dezenas
de idas ao Oracle ou ao Sapiens. Se ao escrever uma consulta ao vivo surgir
vontade de guardar o resultado, a pergunta era de fila.

---

## O desenho de fila que já funciona — copie este

```
Ação local (apontamento, liberação, baixa de componente...)
   │
   ▼
Registro local com status (Apontamento, PacoteTempoERP, ...)
   │  status inicial: pendente/não integrado
   ▼
Worker (producao/views/logs_*.py, setores/.../wms_views.py)
   │  monta chamada (SOAP/REST), envia, interpreta retorno
   ▼
Atualiza status (integrado | erro | processando)
   │  NUNCA apaga a linha por falha
   ▼
EnviaPendenciasScheduler (producao/services/envia_pendencias.py)
   dispara o worker a cada 300s, para todas as filas
```

Worker novo: função que filtra o que está pendente, processa, atualiza
status — e uma chamada nova em `EnviaPendenciasScheduler.run()` (ou
justificativa no relatório para um scheduler próprio).

---

## Regras que você não negocia

**Transporte**

1. **Oracle**: use `connections["oracle_erp"]`/`connections["oracle_alchemy"]`
   em código novo. Não abrir conexão própria com `oracledb.connect()`.
2. **Sapiens**: reaproveite `producao/utils/sapiens_soap.py` para
   namespace/envelope. XML monta com `xml.sax.saxutils.escape` no dado de
   entrada — nunca concatenação crua.
3. **Credencial só em `.env`/`/etc/sigma/sigma.env`**, lida por
   `os.getenv()` em `SIGMA/settings.py`. Nunca em código, log, exceção,
   teste ou commit.
4. **Timeout sempre declarado** em `requests`/SOAP. Retentativa só para
   falha de conexão/rede; nunca para escrita já enviada com desfecho
   desconhecido.
5. **Host e endpoint vêm de `SIGMA/settings.py`** (lido de variável de
   ambiente), nunca montados com entrada de usuário.

**Fila e coleta**

6. **Resposta vazia ou campo de erro do próprio protocolo preenchido é
   FALHA**, nunca "sem dados" — a fábrica em operação não tem zero OP
   aberta.
7. **O registro local nunca é apagado por falha de integração.** Status
   muda; a linha permanece para reprocessamento.
8. **Worker é responsável por uma fila só**, e entra no
   `EnviaPendenciasScheduler` existente (ou justifica scheduler próprio).
9. **"Não encontrado" na consulta ao vivo não é falha** — devolve `None`/
   vazio. Confundir os dois faz a operação caçar problema de rede onde há
   só um resultado vazio legítimo.
10. **Coleta em lote nova que puder ser derrubada por um único registro
    malformado isola esse registro** (ex. bisseção do intervalo/página) em
    vez de falhar o lote inteiro, e registra visivelmente qual registro foi
    isolado e por quê. Convenção preventiva: hoje as integrações do SIGMA
    são majoritariamente por registro, não em lote, mas a próxima coleta em
    lote (Oracle/WMS/Sapiens trazendo N registros de uma vez) segue esta
    regra em vez de repetir o risco de um erro de tipo isolado invalidar a
    leitura inteira.

**Envio (WMS, Sapiens)**

11. **Grava a intenção antes de enviar**, fora de transação de banco
    aberta.
12. **Desfecho desconhecido não reenvia** — fica pendente/erro, com um
    jeito de conferir manualmente no outro sistema. Exceções registradas pelo
    sênior, sempre que o outro lado é comprovadamente idempotente para aquela
    operação (reenviar o que já foi aplicado não duplica efeito, o sistema
    externo responde sucesso reconhecendo que não há mais o que fazer):
    - (2026-08-25) `AumentarApontamento`/`DiminuirApontamento` do Sapiens
      (regra personalizada usada por `corrigir_quantidade_lote`): falha após
      a chamada ao ERP cai em `CorrecaoLote.Status.FALHA` — uma nova correção
      do mesmo lote já é aceita sem conciliação manual
      (`producao/services/altera_apontamento.py`, `_finalizar_correcao_lote`).
      O estado `CONCILIACAO` e a tela "Registrar Conciliação" foram removidos
      nesta mesma decisão (não existiam mais razão de ser).
    Sem essa idempotência confirmada pelo sênior para a operação específica,
    o padrão continua sendo pendente/erro com conferência manual.
13. **No ERP Senior, só pelos webservices Sapiens.** Nunca gravação
    direta no schema Oracle do ERP.

**Geral**

14. Pacote novo, nunca por conta: justificativa no relatório.
15. Não toque em `.env`, `uv.lock`. Não rode `uv add` sem aprovação.
16. Integração nova (Oracle, Sapiens, WMS, telemetria HTTP, LDAP, Firebase, e-mail)
    nasce com um comando `manage.py` de diagnóstico — responde "a
    integração está de pé?" sem abrir código nem console (ex.:
    `manage.py diagnostico_sapiens`, checa credencial presente, conexão e
    um retorno mínimo do sistema externo). Retrofit em integração já
    existente é oportunidade, não obrigação retroativa — registre no
    relatório se não fez.

**Observabilidade de falha** — regras de visibilidade, frescor e saúde:

17. **Pendência de fila não pode ter o painel como único caminho até
    quem opera.** Falha que só aparece a quem abrir o painel **Status
    (Services)** autenticado não é visibilidade. Toda fonte de falha
    nova considera o relatório diário por e-mail a quem opera:
    **silêncio significa limpo**, e o gatilho é a pendência, não o dia.
    O worker que envia o relatório ainda não existe; enquanto isso, a
    regra vale como critério de desenho — fonte de falha nova nasce com
    a pendência enumerável e reprocessável que o relatório vai
    consumir, não com um registro que só o painel enxerga.
18. **Guarda de frescor**: relatório ou digesto não sai sobre dado de
    ciclo antigo do scheduler. Sem ciclo recente concluído, a resposta é
    **"não foi possível apurar"** — estado válido e lado seguro do erro:
    ficar mudo ou declarar ignorância, nunca relatar fila como saudável
    sem apuração.
19. **Nenhum número duplicado em config**: tolerância de atraso é
    múltiplo do `intervalo_segundos` que o próprio worker declara
    (atributo de classe em `producao/services/*`) — nunca um segundo
    valor copiado para variável de ambiente ou constante, que um dia
    diverge do que o worker usa de verdade.
20. **Monitor de saúde externo deriva do banco.** O registry em memória
    do painel de status (`producao/services/status.py`) não sobrevive ao
    processo — processo zumbi ou worker morto sem registrar não é
    acusado por nada externo. Todo monitor de saúde externo deriva do
    que sobrevive: `FonteTelemetria.ultima_coleta_em`, status das filas,
    `intervalo_segundos` dos workers, com payload de **lista branca de
    campos**     (só sai o que está na lista). O monitor ainda não existe; a
    exposição da rota de saúde (autenticada × anônima) é decisão de
    política do sênior — até lá, só o motor, sem rota. Desenho do motor
    em [references/jobs-e-agendamento.md](references/jobs-e-agendamento.md).
21. **Cadência é catálogo com a conta de carga.** Todo
    `intervalo_segundos` de worker que fala com sistema de fora declara
    junto, no mesmo arquivo, o **porquê** daquele intervalo e a **conta
    de carga** — quantas chamadas por hora/dia ele representa para o
    sistema externo (Sapiens, Oracle, WMS) e por que esse volume é
    aceitável. Mudar a cadência exige escrever a conta nova **antes** de
    mexer no valor: encurtar intervalo multiplica chamadas no sistema de
    terceiro, e esse custo é visto e assumido por escrito, não descoberto
    em produção. O teste que trava as cadências em `producao/tests/`
    falha quando o valor muda sem a conta revisada — a mensagem de falha
    aponta para esta regra.

---

## Referências

| Arquivo | Quando ler |
|---|---|
| [references/oracle.md](references/oracle.md) | qualquer consulta nova a `oracle_erp` ou `oracle_alchemy` |
| [references/soap-sapiens.md](references/soap-sapiens.md) | envio ou consulta ao Sapiens/Senior |
| [references/wms.md](references/wms.md) | API do WMS XC e DBLINK Oracle |
| [references/ldap-notificacoes.md](references/ldap-notificacoes.md) | Active Directory, Firebase, e-mail |
| [references/rest.md](references/rest.md) | API HTTP nova, webhook ou cliente `requests` |
| [references/jobs-e-agendamento.md](references/jobs-e-agendamento.md) | worker, lock, timeout, recuperação e scheduler |
| `docs/sigma/07-integracoes-externas.md`, `docs/sigma/03-servidor-e-hospedagem.md` §3.4.4, `docs/sigma/04-aplicativo-mobile.md` §3.6 | princípio de cada integração e variáveis de ambiente |
