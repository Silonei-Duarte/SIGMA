# Procedimento de revisão de segurança

1. **Delimitar**: o que a demanda aponta — diff, commit, branch ou
   arquivos nomeados. Sem apontamento, o diff não commitado; vazio, o
   último commit.
2. **Mapear pontos de entrada** de cada arquivo tocado, numa tabela:

   | Quem chama | O que entra | O que valida | O que autoriza | O que grava | O que sai |
   |---|---|---|---|---|---|

   Preencha uma linha por view/endpoint tocado antes de julgar qualquer
   coisa — a maior parte dos achados aparece só de preencher essa tabela
   com honestidade.
3. **Grep dos padrões que denunciam** (tabela em `../SKILL.md`) no(s)
   arquivo(s) tocado(s) e no que eles chamam. Além da tabela: caçar
   texto de erro cru com credencial vazando em log, tela ou e-mail —
   retorno de SMTP, Oracle, LDAP, Firebase, exceção de banco, SOAP ou
   HTTP interpolado em mensagem sem passar por máscara (regra do bloco
   "Segredo" em `../SKILL.md`).
4. **Leitura camada por camada**: view → form → service → query/chamada
   externa → template. Leia o arquivo inteiro, não só o diff — a checagem
   de autorização pode estar fora das linhas alteradas.
5. **Conferir autenticação/permissão sempre que o diff tocar login ou
   tela restrita**: abra `accounts/views/auth.py` e o
   `AUTHENTICATION_BACKENDS`/`AUTH_PASSWORD_VALIDATORS` de
   `SIGMA/settings.py`, mesmo que não estejam no diff.
6. **Classificar** cada achado pela escala de severidade da skill, sem
   inflar nem rebaixar.
7. **Escrever o relatório** no formato do agente `seguranca`: veredito,
   achados (`arquivo:linha` · o que · impacto concreto neste ambiente ·
   correção · teste que prova), o que foi verificado sem achado, pedidos
   ao sênior, encaminhamento.

Regra de ouro: impacto sempre concreto e neste ambiente — "qualquer
usuário autenticado consegue [ação] via [rota], porque [causa]" — nunca
"possível problema de autorização". Segredo exposto vai ao topo do
relatório, com instrução de rotacionar na origem, e nunca é repetido no
texto do relatório.
