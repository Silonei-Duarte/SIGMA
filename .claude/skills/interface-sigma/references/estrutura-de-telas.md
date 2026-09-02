# Estrutura visual de telas no SIGMA

Use esta referência junto do `Style-Guide-IPEL.md`. Ela fixa a composição
comum da IPEL sem importar marca, personagens ou elementos de outro produto.

## Tipografia, espaço e forma

- Título de página usa `titulo-pagina` e Montserrat 700; títulos de seção e
  bloco seguem a escala já definida, sem `text-*` arbitrário como substituto.
- Corpo, rótulo e tabela usam Poppins. Valor numérico de destaque usa o estilo
  `Indicador`, não tamanho ou peso inventado na tela.
- Espaçamento usa a grade de 4px: 8, 12, 16, 24, 32, 48 e 64px. Cartão recebe
  `espaco/6` (24px); seções são separadas por `espaco/8` (32px).
- Cartão/painel/modal externo usa `raio/xl` (24px); agrupamento interno usa
  `raio/lg` (16px); campo usa `raio/md` (10px). Sombra é sutil no cartão e
  cresce somente para menu, dica, modal ou gaveta.

## Composição por tipo de tela

### Listagem

Título, filtros e ações ficam no cabeçalho sobre `superficie/base`, sem cartão.
Uma borda inferior separa o cabeçalho do conteúdo. A tabela vem depois, em
cartão próprio com `mt-6`, `superficie/elevada`, `borda/sutil`, `raio/xl` e
sombra discreta. Use `<table>` real, cabeçalho `superficie/afundada`, grade
completa e rolagem horizontal no contêiner quando necessário.

### Formulário e detalhe

Use título e contexto no cabeçalho; conteúdo em cartão externo. Agrupe campos
relacionados em blocos internos, com rótulo, ajuda e erro próximos ao controle.
Campo padrão tem altura mínima de 36px; ações ficam ao final e mantêm ação
principal, secundária e destrutiva nas famílias semânticas corretas.

### Painel e estado vazio

Indicadores se organizam em cartões de mesma hierarquia, sem competir por
sombra, cor ou tamanho. Estado vazio é centralizado, com ícone neutro, título,
orientação e ação principal apenas quando houver próxima ação útil.

## Responsividade e revisão

Em tela estreita, reduza colunas e empilhe controles preservando ordem de
leitura; não reduza tipografia, alvo de toque ou padding abaixo do padrão.
Antes de encerrar, confira tema claro/escuro, foco de teclado, tabela rolável,
erro de campo, estado vazio e ações de ícone com `aria-label`.
