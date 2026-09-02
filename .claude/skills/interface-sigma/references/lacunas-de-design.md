# Lacunas de design

Lista viva de pendência de token ou decisão de design sem resposta óbvia.
Item novo entra aqui em vez de virar decisão silenciosa de quem estiver
implementando. Marque como resolvido (ou remova) quando o sênior decidir.

## Abertas

Nenhuma no momento.

## Resolvidas

- **Papel `-destaque` sem equivalente em referência externa (2026-08-26).**
  O SIGMA tem `{bg,text,border}-{sucesso,atencao,erro}-destaque` (variação
  sólida para controle/etiqueta com cor forte); a referência externa não tem
  papel equivalente (só `base`/`sutil`/`borda`/`halo`). Um valor de `-destaque`
  aceito por analogia com `borda`/`halo` da referência externa foi para produção sem
  testar contraste contra o texto real que fica em cima nos templates —
  quebrou (`atencao-destaque` no escuro caiu para 1,77:1 contra
  `texto-primario`, bem abaixo do mínimo de 4,5:1).

  Verificação completa revelou mais três problemas da mesma família, dois
  pré-existentes (não causados pela mudança do dia): `sucesso-destaque` no
  claro e no escuro, `erro-destaque` no claro, e o botão `.botao-perigo`
  (hover ligado a `erro-destaque`, quebrando contra o texto branco fixo
  desse botão no escuro). Todos corrigidos em `styles.css`, documentados em
  `Style-Guide-IPEL.md` e cobertos por par novo em
  `scripts/verificar-contraste.mjs` (que até então nunca testava nenhum par
  `-destaque` — é por isso que passou batido).

  Lição: **valor de token "herdado" por analogia de uma referência externa
  sem papel equivalente exige teste de contraste contra o uso real do
  SIGMA antes de ir para produção** — não basta o par `base sobre sutil`
  que o script já cobria; fundo sólido com texto por cima (`-destaque`,
  botão de ação) é uma categoria de par à parte.
