# Acessibilidade no SIGMA

Antes de considerar uma tela pronta, confira contraste nos dois temas,
navegação por teclado e foco visível. Rode
`node .claude/skills/interface-sigma/scripts/verificar-contraste.mjs` quando
alterar token ou cor semântica.

- Todo controle só por ícone tem `title` e `aria-label`; ícone decorativo usa
  `aria-hidden="true"`.
- Campo inválido informa erro associado por `aria-describedby` e
  `aria-invalid="true"` quando aplicável.
- Informação não depende só de cor: texto, ícone ou estado reforçam sucesso,
  alerta e erro.
- Modal preserva foco previsível, fecha por ação explícita e tem título.
- Não remova `:focus-visible`; o foco precisa se distinguir do fundo em ambos
  os temas.
