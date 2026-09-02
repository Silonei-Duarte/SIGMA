# Sistema de Design IPEL — Projeto Sigma

> A interface compartilhada pelos sistemas da IPEL e a base visual do Sigma.
> Este documento é a fonte única de verdade para `styles.css`. Toda decisão de cor, tipo, espaço e componente sai daqui.

**Inventário rápido:** 33 primitivas · 67 papéis semânticos · 27 ícones · 10 estilos de texto · 2 temas (claro/escuro)

---

## Sumário

1. [Tipografia](#1-tipografia)
2. [Cores primitivas](#2-cores-primitivas)
3. [Cores semânticas (tokens)](#3-cores-semânticas-tokens)
4. [Espaçamento](#4-espaçamento)
5. [Raio de borda](#5-raio-de-borda)
6. [Traço (stroke)](#6-traço-stroke)
7. [Sombras](#7-sombras)
8. [Ícones](#8-ícones)
9. [Componentes](#9-componentes)
10. [Padrões de interface](#10-padrões-de-interface)
11. [Marca e movimento](#11-marca-e-movimento)
12. [Personagens](#12-personagens)
13. [Régua de status (jornada)](#13-régua-de-status-jornada)
14. [Responsividade](#14-responsividade)
15. [Princípios de design](#15-princípios-de-design)

---

## 1. Tipografia

Duas famílias, papéis fixos:

| Família       | Peso | Papel                        |
|---------------|------|------------------------------|
| **Montserrat** | 700 (Bold) | Todos os títulos            |
| **Poppins**    | 400 (Regular) | Corpo, tabela, legenda    |
| **Poppins**    | 500 (Medium) | Rótulos                   |
| **Poppins**    | 600 (SemiBold) | Indicadores numéricos   |

### Escala tipográfica

| Token CSS              | Família    | Peso | Tamanho | Altura de linha | Espaçamento entre letras | Uso                              |
|------------------------|------------|------|---------|-----------------|--------------------------|----------------------------------|
| `--tipo-titulo-tela`   | Montserrat | 700  | 30px    | 120%            | -1.1%                    | Título de tela / hero            |
| `--tipo-titulo-pagina` | Montserrat | 700  | 24px    | 130%            | -1.1%                    | Título de página                 |
| `--tipo-titulo-secao`  | Montserrat | 700  | 20px    | 140%            | -1.1%                    | Título de seção                  |
| `--tipo-titulo-bloco`  | Montserrat | 700  | 17px    | 150%            | 0                        | Título de bloco / card           |
| `--tipo-corpo-base`    | Poppins    | 400  | 15px    | 160%            | 0                        | Corpo do texto                   |
| `--tipo-corpo-tabela`  | Poppins    | 400  | 13px    | 150%            | 0                        | Texto de tabela                  |
| `--tipo-legenda`       | Poppins    | 400  | 12px    | 150%            | 0                        | Legenda de apoio                 |
| `--tipo-rotulo`        | Poppins    | 500  | 13px    | 150%            | 0                        | Rótulos de campo e controle      |
| `--tipo-indicador-base`| Poppins    | 600  | 20px    | 140%            | -1.1%                    | Indicador numérico padrão        |
| `--tipo-indicador-grande`| Poppins  | 600  | 30px    | 120%            | -1.1%                    | Indicador numérico grande (KPI)  |

**Regra:** Montserrat só aparece em título. Poppins faz todo o resto. Indicadores são Poppins SemiBold — "o número que o painel existe para mostrar".

---

## 2. Cores primitivas

Cores brutas que nunca são usadas diretamente na interface. Sempre consumidas via tokens semânticos.

### Verde (marca)

| Token           | HEX       | RGB                |
|-----------------|-----------|--------------------|
| `verde/50`      | `#E6F4EC` | 230, 244, 236      |
| `verde/200`     | `#8FD2AC` | 143, 210, 172      |
| `verde/300`     | `#54B884` | 84, 184, 132       |
| `verde/400`     | `#1FA25E` | 31, 162, 94        |
| `verde/500`     | `#008D36` | 0, 141, 54         |
| `verde/600`     | `#007A2F` | 0, 122, 47         |
| `verde/700`     | `#046428` | 4, 100, 40         |
| `verde/900`     | `#0B3D1B` | 11, 61, 27         |

### Neutro

| Token           | HEX       | RGB                |
|-----------------|-----------|--------------------|
| `neutro/0`      | `#FFFFFF` | 255, 255, 255      |
| `neutro/50`     | `#F7F9FA` | 247, 249, 250      |
| `neutro/100`    | `#EEF1F4` | 238, 241, 244      |
| `neutro/200`    | `#E1E6EA` | 225, 230, 234      |
| `neutro/300`    | `#CCD2D8` | 204, 210, 216      |
| `neutro/400`    | `#A7B0B9` | 167, 176, 185      |
| `neutro/500`    | `#8E99A3` | 142, 153, 163      |
| `neutro/600`    | `#7D868F` | 125, 134, 143      |
| `neutro/700`    | `#5F6871` | 95, 104, 113       |
| `neutro/800`    | `#454D55` | 69, 77, 85         |
| `neutro/850`    | `#363F47` | 54, 63, 71         |
| `neutro/900`    | `#252C33` | 37, 44, 51         |
| `neutro/950`    | `#171C21` | 23, 28, 33         |

### Erro

| Token           | HEX       | RGB                |
|-----------------|-----------|--------------------|
| `erro/100`      | `#FEE3DF` | 254, 227, 223      |
| `erro/300`      | `#FF8271` | 255, 130, 113      |
| `erro/600`      | `#B01F17` | 176, 31, 23        |
| `erro/900`      | `#4A1310` | 74, 19, 16         |

### Atenção

| Token           | HEX       | RGB                |
|-----------------|-----------|--------------------|
| `atencao/100`   | `#FFECB4` | 255, 236, 180      |
| `atencao/300`   | `#E0B048` | 224, 176, 72       |
| `atencao/600`   | `#7D5E08` | 125, 94, 8         |
| `atencao/900`   | `#402A05` | 64, 42, 5          |

### Informação

| Token           | HEX       | RGB                |
|-----------------|-----------|--------------------|
| `informacao/100`| `#DBEBFE` | 219, 235, 254      |
| `informacao/300`| `#6AAEFF` | 106, 174, 255      |
| `informacao/600`| `#164E8A` | 22, 78, 138        |
| `informacao/900`| `#132F4D` | 19, 47, 77         |

### Urgencia

| Token           | HEX       | RGB                |
|-----------------|-----------|--------------------|
| `urgencia/100`  | `#D4C3FD` | 212, 195, 253      |
| `urgencia/300`  | `#B3A1DC` | 179, 161, 220      |
| `urgencia/600`  | `#7C3AED` | 124, 58, 237       |
| `urgencia/700`  | `#7321CC` | 115, 33, 204       |
| `urgencia/900`  | `#4B2B7D` | 75, 43, 125        |

---

## 3. Cores semânticas (tokens)

Os tokens abaixo resolvem automaticamente para claro ou escuro. No CSS, use custom properties com estes nomes e alterne o valor via classe ou `prefers-color-scheme`.

### Superfícies

| Token                    | Claro (resolve para) | Escuro (resolve para) | Uso                                 |
|--------------------------|----------------------|-----------------------|-------------------------------------|
| `superficie/base`        | `neutro/50`          | `neutro/950`          | Fundo geral da aplicação            |
| `superficie/elevada`     | `neutro/0`           | `neutro/900`          | Cards, painéis, modais              |
| `superficie/afundada`    | `neutro/100`         | `neutro/850`          | Áreas recuadas, inputs              |
| `superficie/inversa`     | `neutro/900`         | `neutro/100`          | Toast / notificação flutuante       |
| `superficie/flutuante`   | `neutro/0`           | `neutro/800`          | Dropdowns, popovers                 |

### Texto

| Token                    | Claro         | Escuro        | Uso                                 |
|--------------------------|---------------|---------------|-------------------------------------|
| `texto/primario`         | `#000000`     | `#FFFFFF`     | Texto principal                     |
| `texto/secundario`       | `#000000`     | `#FFFFFF`     | Texto de apoio                      |
| `texto/legenda`          | `#000000`     | `#FFFFFF`     | Legendas e anotações                |
| `texto/marcador`         | `neutro/700`  | `#FFFFFF`     | Marcadores e bullet points          |
| `texto/desabilitado`     | `neutro/600`  | `neutro/600`  | Texto inoperante                    |
| `texto/sobre-marca`      | `neutro/0`    | `neutro/950`  | Texto sobre fundo de marca (botão primário) |
| `texto/sobre-inversa`    | `neutro/100`  | `neutro/900`  | Texto sobre superfície inversa      |
| `texto/link`             | `verde/700`   | `verde/300`   | Links e ações textuais              |

### Bordas

| Token                    | Claro          | Escuro         | Uso                                 |
|--------------------------|----------------|----------------|-------------------------------------|
| `borda/sutil`            | `neutro/200`   | `neutro/850`   | Divisores, separadores              |
| `borda/padrao`           | `neutro/600`   | `neutro/500`   | Bordas de controles (inputs, selects)|
| `borda/foco`             | `verde/600`    | `verde/300`    | Anel de foco (2px)                  |

### Marca / Ações primárias

| Token                    | Claro          | Escuro         | Uso                                 |
|--------------------------|----------------|----------------|-------------------------------------|
| `marca/identidade`       | `verde/500`    | `verde/500`    | Cor de identidade fixa              |
| `marca/base`             | `verde/600`    | `verde/400`    | Botão primário em repouso           |
| `marca/hover`            | `verde/700`    | `verde/300`    | Botão primário no hover             |
| `marca/ativo`            | `#035522`      | `#73C59A`      | Botão primário pressionado          |
| `marca/sutil`            | `verde/50`     | `verde/900`    | Fundo tênue de marca (selecionado)  |
| `marca/sobre-inversa`    | `verde/300`    | `verde/700`    | Marca sobre superfície inversa      |

### Feedback

| Grupo       | Token base       | Token sutil      | Token borda      |
|-------------|------------------|------------------|------------------|
| **Sucesso** | `verde/700` · `verde/300` | `verde/50` · `verde/900` | `verde/300` · `verde/300` |
| **Atenção** | `atencao/600` · `atencao/300` | `atencao/100` · `rgba(56,55,42)` | `atencao/300` · `atencao/300` |
| **Erro**    | `erro/600` · `erro/300` | `erro/100` · `erro/900` | `erro/600` · `erro/300` |
| **Info**    | `informacao/600` · `informacao/300` | `informacao/100` · `informacao/900` | `informacao/300` · `informacao/300` |
| **Urgencia** | `urgencia/700` · `urgencia/300` | `urgencia/100` · `urgencia/900` | `urgencia/600` · `urgencia/300` |

> Formato: `claro · escuro`

Quando três ou mais estados são exibidos lado a lado, as cores `base` e
`sutil` do conjunto precisam manter separação perceptiva mínima de `dE 12`
(CIEDE2000). O verificador de contraste mede todos os pares nos dois temas.
Essa regra complementa WCAG: legibilidade e distinção entre estados são
problemas diferentes. Cor continua acompanhada de texto, ícone, forma ou
posição.

### Estado do cartão de painel

> **Implementado, ainda sem uso.** Os tokens existem em
> `theme/static_src/src/styles.css` e passam pelo verificador de contraste,
> mas **nenhuma tela do SIGMA os aplica** (decisão do sênior, 01/09/2026).
> O padrão nasceu no SIGT (projeto irmão) e entrou aqui para que, no dia em
> que o SIGMA colorir cartões de painel — os de
> `/producao/status-recursos/` são o candidato natural —, os dois sistemas
> falem a mesma língua em vez de inventar cada um a sua.

Família à parte da de **Feedback**, e a diferença importa: Feedback responde
ao que o usuário acabou de fazer (o alerta de "salvo com sucesso"); Estado
descreve a situação de um dado que estava lá antes de ele chegar.

O eixo é **de quem é a ação**, não a gravidade solta. Dois cartões que
exigem a mesma providência recebem a mesma cor, mesmo vindo de tabelas
diferentes — é a pergunta que quem abre um painel realmente faz.

| Token              | Pigmento         | HEX       | c/ branco | Significado                             |
|--------------------|------------------|-----------|-----------|-----------------------------------------|
| `estado/pendencia` | `erro/600`       | `#B01F17` | 6,88:1    | a casa precisa agir (aprovar, conduzir) |
| `estado/prestador` | `informacao/600` | `#164E8A` | 8,43:1    | o outro lado precisa agir (enviar)      |
| `estado/risco`     | `atencao/300`    | `#E0B048` | —         | ainda válido, vence em breve            |
| `estado/travado`   | `urgencia/600`   | `#7C3AED` | 5,70:1    | vencido ou bloqueado — parou            |
| `estado/aprovado`  | `verde/600`      | `#007A2F` | 5,49:1    | em dia, nada a fazer                    |

| Tinta                | Valor      | Onde                              |
|----------------------|------------|-----------------------------------|
| `estado/sobre`       | `neutro/0` | sobre os quatro pigmentos escuros |
| `estado/sobre-risco` | `#000000`  | sobre o amarelo (10,47:1)         |

O `travado` reaproveita o `urgencia/600` que o SIGMA já tinha — não entrou
primitiva nova. O par mais apertado da família é `prestador × travado`, com
dE 22,1: quase o dobro do mínimo de 12 que a regra de separação exige. O
verificador mede os dez pares.

As regras que acompanham o padrão:

> **Regra:** o cartão é pintado com o **pigmento cheio**, não com um véu
> pastel nem com um filete de acento. Em área grande a cor lavada é o pior
> lugar para pedir distinção — no escuro os matizes não têm croma
> disponível para se separar.

> **Regra:** o pigmento **não muda entre os temas**. É a exceção à regra de
> que todo token de cor tem um valor por tema. Quem muda é a tinta, e só no
> amarelo: amarelo que aguenta texto branco a 4,5:1 deixa de ser amarelo.

> **Regra:** dentro do cartão pintado não existe hierarquia por lavagem de
> cor. A cor vai no contêiner e os filhos herdam (`color: inherit`); a
> hierarquia é por tamanho e peso. Ladrilho de ícone e trilhos usam a
> própria tinta rebaixada por `color-mix`, nunca um cinza — cinza sobre
> pigmento saturado suja.

> **Regra:** o anel de foco sobre cartão pintado é a **tinta do cartão**,
> não `borda/foco`: o verde da marca desapareceria sobre
> `estado/aprovado`.

> **Regra:** o catálogo de estados é fechado e mora no código como
> `TextChoices`. Quem decide o estado de um cartão é o service que monta o
> painel, nunca o template — o template só aplica o pigmento.

**Sobre o roxo.** O `estado/travado` usa o `urgencia/600` = `#7C3AED`, que
já estava implementado — nenhuma primitiva nova entrou. É o mesmo valor do
`roxo/500` do SIGT, do "Bloqueado" da régua da
[seção 13](#13-régua-de-status-jornada) e do roxo do Farol: um único
hexadecimal para os três sistemas.

### Interação

| Token                      | Claro          | Escuro         | Uso                                 |
|----------------------------|----------------|----------------|-------------------------------------|
| `interacao/hover`          | `neutro/100`   | `neutro/850`   | Fundo ao passar o mouse             |
| `interacao/pressionado`    | `neutro/200`   | `neutro/800`   | Fundo ao clicar                     |
| `interacao/selecionado`    | `verde/50`     | `verde/900`    | Fundo do item selecionado           |
| `interacao/desabilitado`   | `neutro/100`   | `neutro/850`   | Fundo de controle desabilitado      |

---

## 4. Espaçamento

Escala de 4px. Toda margem, padding e gap usa um múltiplo desta escala.

| Token       | Valor | Uso comum                               |
|-------------|-------|------------------------------------------|
| `espaco/1`  | 4px   | Micro espaçamento (gap entre ícone e texto) |
| `espaco/2`  | 8px   | Espaçamento interno pequeno              |
| `espaco/3`  | 12px  | Padding de controles compactos           |
| `espaco/4`  | 16px  | Padding padrão de cards, gap de grid     |
| `espaco/5`  | 20px  | Espaço intermediário da grade             |
| `espaco/6`  | 24px  | Espaçamento entre seções internas        |
| `espaco/8`  | 32px  | Espaçamento entre blocos                 |
| `espaco/12` | 48px  | Margem de seção                          |
| `espaco/16` | 64px  | Margem de prancha / margem principal     |

---

## 5. Raio de borda

| Token          | Valor   | Uso                                       |
|----------------|---------|-------------------------------------------|
| `raio/nenhum`  | 0       | Sem arredondamento                        |
| `raio/sm`      | 4px     | Controles pequenos (chips, tags)          |
| `raio/md`      | 10px    | Controles médios (inputs, botões)         |
| `raio/lg`      | 16px    | Cards, blocos, contêineres               |
| `raio/xl`      | 24px    | Contêineres maiores, painéis             |
| `raio/completo`| 9999px  | Pill / totalmente arredondado             |

> **Regra de ouro do design:** raio 10 no controle (input, botão), raio 16 no bloco (card, painel).

---

## 6. Traço (stroke)

| Token          | Valor | Uso                                  |
|----------------|-------|--------------------------------------|
| `traco/padrao` | 1px   | Bordas de controles, divisores       |
| `traco/foco`   | 2px   | Anel de foco em todos os componentes |

---

## 7. Sombras

Todas usam a cor base `rgba(23, 28, 33, ...)` (neutro/950). Nenhuma sombra colorida.

| Token                  | Camadas                                                                 | Uso                               |
|------------------------|-------------------------------------------------------------------------|------------------------------------|
| `sombra/sutil`         | `0 1px 2px rgba(23,28,33,0.06)`, `0 1px 3px rgba(23,28,33,0.10)`       | Cards em repouso                   |
| `sombra/media`         | `0 4px 6px -1px rgba(23,28,33,0.10)`, `0 2px 4px -2px rgba(23,28,33,0.10)` | Cards em hover, menus           |
| `sombra/alta`          | `0 10px 15px -3px rgba(23,28,33,0.12)`, `0 4px 6px -4px rgba(23,28,33,0.10)` | Modais, diálogos              |
| `sombra/flutuante`     | `0 2px 6px rgba(23,28,33,0.06)`, `0 22px 48px -12px rgba(23,28,33,0.22)` | Dropdowns, popovers              |
| `sombra/lateral-dialogo` | `0 6px 28px -6px rgba(23,28,33,0.14)`                                | Painéis laterais (sidebars)        |

> **Regra:** Cards usam sombra suave em vez de borda dura — "sem borda dura, que é o que dá aspecto de planilha".

### Sombra no tema escuro

Os valores da tabela são os do tema **claro**. No escuro cada token precisa
ser redeclarado com preto puro e opacidade maior — `sombra/sutil` vira
`0 1px 2px rgba(0,0,0,0.30)`, `sombra/media` vira
`0 4px 6px -1px rgba(0,0,0,0.40)` e `sombra/alta` vira
`0 10px 15px -3px rgba(0,0,0,0.50)`.

> **Regra:** sombra é sempre valor concreto vindo do token `--sombra-*`.
> Nunca derive sombra de um token de texto (`color-mix` sobre
> `texto/primario`, por exemplo): no escuro o texto é claro, e a sombra vira
> **brilho branco** — o efeito é o card parecer apagado.

> **Regra:** no escuro a elevação sobe em **luminância**, não em sombra —
> não há como escurecer o que já está escuro. A escada é `superficie/base` →
> `superficie/elevada` → `superficie/afundada` (`neutro/950` → `neutro/900`
> → `neutro/850`). Peça elevada dentro de peça elevada não tem degrau: o
> conteúdo interno de um painel usa `superficie/afundada`, não
> `superficie/elevada` de novo.

A escala está implementada em `theme/static_src/src/styles.css`: os valores
concretos ficam no `:root`, são redeclarados em `html.tema-escuro` e chegam
às utilities `shadow-*` por um mapeamento indireto
(`@theme { --shadow-sutil: var(--sombra-sutil) }`), para a tela não precisar
de variante `dark:`.

As utilities `alerta` e `cartao-indicador` consomem `var(--sombra-sutil)`.
Antes usavam `0 2px 8px color-mix(in srgb, var(--color-texto-primario) 10%,
transparent)` — que no escuro virava brilho branco, porque `texto/primario`
resolve para `neutro/100`.

A escada de superfície sempre esteve correta: o `body` é `superficie/base` e
os cards são `superficie/elevada`.

> **Dívida remanescente.** Duas coisas ficaram de fora:
>
> - A maioria dos templates ainda usa `shadow-sm` do Tailwind cru, inclusive
>   os cards de `/producao/status-recursos/`. Migrar para `shadow-sutil` é
>   trabalho de tela, uma a uma.
> - Quatro `box-shadow` da tela de login (`.login-vidro`, `.login-painel-a`,
>   `.login-entrar`) ainda derivam de `texto/primario`. São efeitos de vidro
>   sobre imagem de fundo, com regra própria — refatorá-los é demanda
>   separada.

---

## 8. Ícones

Todos em 24×24px. Dois grupos:

### Ícones do sistema (identidade do Sigma)

São os 10 assuntos que o painel organiza:

| Nome           | Descrição                  |
|----------------|----------------------------|
| Observação     | Painel executivo e alertas  |
| Indicadores    | KPIs e métricas             |
| Alertas        | Notificações de alerta      |
| Oportunidades  | Oportunidades identificadas |
| Planos de ação | Ações e follow-ups          |
| Conhecimento   | Base de conhecimento        |
| Documentos     | Gestão documental           |
| Relatórios     | Relatórios e exports        |
| Usuários       | Gestão de usuários          |
| Configurações  | Configurações do sistema    |

### Ícones de interface

O mínimo sem o qual os componentes não funcionam:

| Nome          | Uso                              |
|---------------|----------------------------------|
| Seta/baixo    | Expansão, dropdown               |
| Seta/cima     | Colapso, ordenar ascendente      |
| Seta/direita  | Navegação, avançar               |
| Seta/esquerda | Voltar                           |
| Fechar        | Fechar modal/toast               |
| Confirmar     | Check, seleção confirmada        |
| Indeterminado | Checkbox parcial                 |
| Buscar        | Campo de busca                   |
| Carregando    | Loading spinner                  |
| Adicionar     | Ação de criação (+ / novo)       |
| Atenção       | Aviso (amarelo)                  |
| Informação    | Informativo (azul)               |
| Erro          | Erro (vermelho)                  |
| Sucesso       | Sucesso (verde)                  |
| Ordenar       | Ordenação de colunas             |
| Filtrar       | Filtros de tabela                |
| Mais opções   | Menu contextual (⋯)             |
| Modo TV       | Ativar modo TV                   |

### Marcas dos personagens

Cinco marcas distintas (não variações do mesmo símbolo): Sigma (binóculos), Luna (lâmpada), Tico (raio), Nina (gráfico), Sábio (árvore).

---

## 9. Componentes

### Botão

Quatro estilos por hierarquia de ação. Todos com **36px de altura** e **anel de foco de 2px**.

| Estilo       | Fundo                  | Texto               | Uso                            |
|--------------|------------------------|----------------------|--------------------------------|
| Principal    | `marca/base`           | `texto/sobre-marca`  | Ação primária (1 por tela)     |
| Secundário   | transparente + borda   | `marca/base`         | Ação secundária                |
| Discreto     | transparente           | `marca/base`         | Ação terciária                 |
| Excluir      | `erro/base`            | branco               | Ação destrutiva                |

**Estados (valem para todo componente):**

| Estado             | Comportamento visual                           |
|--------------------|-------------------------------------------------|
| Repouso            | Estilo padrão                                   |
| Hover              | `marca/hover` (ou `interacao/hover`)             |
| Pressionado        | `marca/ativo` (ou `interacao/pressionado`)       |
| Foco (teclado)     | Anel de 2px com `borda/foco`                     |
| Carregando         | Spinner substitui o texto                        |
| Desabilitado       | `interacao/desabilitado` + `texto/desabilitado`  |

Para ações exclusivamente por ícone, use as utilities compartilhadas
`botao-informacao-icone`, `botao-sucesso-icone`, `botao-atencao-icone` e
`botao-perigo-icone` ou `botao-urgencia-icone`. Todas mantêm 36px, foco visível, formato circular e
fundo tinto semântico; o ícone deve ter `aria-label` ou `title` que explique
a ação.

Para uma ação de texto fora das quatro hierarquias, componha o botão com o
par de estado já existente — fundo `{estado}/sutil`, texto `{estado}/base`,
o mesmo par dos avisos — em vez de criar componente ou utility nova.

### Campo de texto (input)

- Rótulo acima, texto de apoio abaixo
- Altura de 36px (alinha com botão)
- Borda `borda/padrao` em repouso; `borda/foco` ao focar
- **Inválido:** borda `erro/borda`, ícone de erro + mensagem — **cor nunca é o único sinal**

**Estados do campo:**

| Estado       | Visual                                              |
|--------------|------------------------------------------------------|
| Vazio        | Placeholder em `texto/desabilitado`                   |
| Preenchido   | Valor em `texto/primario`, sufixo em `texto/legenda`  |
| Digitando    | Borda `borda/foco`, mensagem "Digitando…"             |
| Inválido     | Borda `erro/borda`, ícone erro, mensagem de erro      |
| Desabilitado | Fundo `interacao/desabilitado`, texto `texto/desabilitado` |
| Com busca    | Ícone de busca à esquerda                             |

### Seleção (select / dropdown)

- Lista aberta: contêiner com `raio/lg` (16px), fio entre linhas (não borda por item)
- Item marcado: fundo `interacao/selecionado` + ícone de check à direita — **nunca só cor**
- Gatilho de filtro selecionado: manter a superfície elevada, aplicar borda
  `informacao-borda` e texto `informacao-base` nos dois temas; não trocar o
  fundo nem usar `texto-sobre-marca`.
- Superfície: `superficie/flutuante` com `sombra/flutuante`

### Checkbox

- Desmarcado: borda `borda/padrao`
- Marcado: fundo `marca/base`, ícone Confirmar em `texto/sobre-marca`
- Indeterminado: fundo `marca/base`, ícone Indeterminado
- Foco: anel `borda/foco` de 2px

### Toggle

- Desligado: trilho `neutro/300`, botão branco
- Ligado: trilho `marca/base`, botão branco
- Foco: anel `borda/foco` de 2px

---

## 10. Padrões de interface

### Avisos (alerts)

> "A cor aparece no fundo tinto, no ícone e na borda. O texto usa o token base
> do estado para preservar contraste nos temas claro e escuro."

- Contêiner: fundo `*-sutil` com sombra sutil e raio 16px
- Ícone colorido à esquerda (sucesso/atenção/erro/info/urgencia)
- Título e descrição em `*-base` (13px, Poppins Regular)
- Ação textual à direita (link)

### Notificação flutuante (toast)

- Some sozinha em **5 segundos**
- Usa `superficie/inversa` para se destacar de qualquer tela sem depender de cor de estado
- Texto em `texto/sobre-inversa`
- Ação "Desfazer" disponível

### Blocos / Cards de indicador

Quatro anatomias, do mais seco ao mais rico:

1. **Simples:** rótulo + indicador grande + variação (↑12 / ↓3)
2. **Com unidade:** rótulo + indicador grande + sufixo de unidade
3. **Com breakdown:** rótulo + lista de sub-itens com valores
4. **Clicável:** com seta à direita e véu de hover — **nunca um botão dentro do card**

Indicadores usam `raio/lg` (16px), `superficie/elevada`, `sombra/sutil` e sem borda dura. Painéis estruturais de formulário e listagem podem usar `raio/xl` (24px) com `borda/sutil`.

### Tabela

- Cabeçalho: `texto/corpo-tabela` (13px, Poppins Regular), fundo `superficie/afundada`
- Linhas: `superficie/elevada`, borda inferior `borda/sutil`
- Hover na linha: `interacao/hover`
- Ordenação: ícone Ordenar no cabeçalho
- Responsivo (móvel): tabela vira lista de cartões

### Marcador de valor vazio

O que a tela mostra quando um valor não existe segue três faixas, escolhidas
pelo tipo de espaço:

1. **Célula densa de tabela** → `-` (hífen curto). Nunca `—` (travessão,
   que se lê como traço do desenho) e nunca célula em branco.
2. **Campo com rótulo e largura própria** (ficha, detalhe) → `não consta`.
3. **Ausência que é a resposta** → texto do que a ausência significa
   ("Sem configuração salva", "sem prazo").

A faixa 3 manda sobre as outras duas. Telas vizinhas usam o mesmo marcador
para o mesmo tipo de ausência. Valor que alimenta script (payload, cache,
`data-*`) não é exibição: mantém o valor cru, sem marcador.

### Texto de ajuda com dono único

Texto de ajuda que aparece em dois lugares na mesma tela — cópia visível e
cópia acessível (`sr-only` apontada por `aria-describedby`) — vive em um
partial único incluído duas vezes; a cópia acessível nunca é segunda
escrita à mão.

### Gráficos

Três formas, uma regra: **a cor nunca é o único sinal**.

| Tipo    | Regra                                      |
|---------|---------------------------------------------|
| Barra   | Cada barra tem rótulo de texto              |
| Linha   | Ponto marcado em cada dado                  |
| Rosca   | Legenda com valor numérico ao lado          |

### Calendário

- Hoje: contorno (`borda/foco`)
- Dia selecionado: preenchimento (`marca/base`)
- Intervalo: fundo entre as pontas (`marca/sutil`)
- Três sinais diferentes, nunca só cor

### Barra de navegação lateral (sidebar)

- Ícones do sistema + rótulo
- Item ativo: fundo `interacao/selecionado` + ícone colorido com `personagem/*`
- Badge numérico para contadores
- No tablet: vira trilho de ícones (sem rótulo)
- No móvel: desce para rodapé (tab bar)

---

## 11. Marca e movimento

### A folha

Elemento gráfico da identidade. **Sempre indica que existe inteligência preditiva trabalhando.** Nunca é marcador de lista nem enfeite.

Usos permitidos:
- Selo de funcionalidade preditiva (ex: "Previsão de gramatura")
- Indicador de carregamento (anel gira 360° em 900ms; folha fica parada no centro)
- Estado vazio (ex: "Nenhum ensaio registrado hoje")

### Movimento / Animação

A identidade pede "movimentos suaves". Uma curva e três durações:

| Token                  | Valor                        | Uso                        |
|------------------------|------------------------------|----------------------------|
| `--transicao-curva`    | `cubic-bezier(0.25, 0.1, 0.25, 1)` | Todas as transições  |
| `--transicao-rapida`   | 180ms                        | Hover, foco, feedback      |
| `--transicao-media`    | 300ms                        | Expansão, colapso, slide   |
| `--transicao-lenta`    | 500ms                        | Troca de tela, fade in/out |

> **Regra:** Todas as animações param quando o sistema pede menos movimento (`prefers-reduced-motion: reduce`), exceto a composição decorativa do login do SIGMA. Nela, as esferas, partículas e feixe continuam ativos por direção artística aprovada.

---

## 12. Personagens

<!-- Conteúdo histórico substituído pela identidade normativa do SIGMA.

Cinco personagens, cada um com sua área do sistema:

| Personagem | Elemento   | Área              | Cor (token)          | Descrição                            |
|------------|------------|--------------------|----------------------|--------------------------------------|
| **Sigma**  | Binóculos  | Painel e alertas   | `personagem/Sigma` (verde/600 · verde/400)  | O observador — olhar de longe e antes |
| **Luna**   | Lâmpada    | Ideias e oportunidades | `personagem/luna` (verde/400 · verde/200) | A inovadora — a ideia que aparece  |
| **Tito**   | Raio       | Planos de ação     | `personagem/tito` (atencao/600 · atencao/300) | O executor — velocidade e execução |
| **Nina**   | Gráfico    | Indicadores        | `personagem/nina` (informacao/600 · informacao/300) | A analista — dado em ordem      |
| **Sábio**  | Árvore     | Conhecimento       | `personagem/sabio` (neutro/800 · neutro/300) | O mentor — o que levou tempo       |

### Três regras dos personagens

1. **A cor fica na marca, nunca no texto.** O verde claro da Luna dá 3,29:1 — passa como ícone, reprova como texto. Nome e papel usam sempre tinta neutra.
2. **Cinco áreas, cinco marcas.** Onde não há área, não há personagem: documentos, relatórios e configurações usam ícone comum.
3. **O personagem acompanha o módulo.** Indicadores carregam Nina; Alertas carregam Sigma; etc.

---

-->

### Identidade do SIGMA

O SIGMA possui somente Cedro e Flora. Eles representam contexto Industrial e Conversão no dado, nunca uma tela inteira; cadastros, documentos e configurações usam ícones Lucide comuns. As regras de uso, traços, território e pendências vivem em [13 - Marca e identidade](13-marca-e-identidade.md), que é a fonte normativa desta seção.

## 13. Régua de status (jornada)

Os cinco estados de pedido em aberto — dado de negócio, não feedback de ação. **O pigmento não troca com o tema:** a cor do estado é uma só, de dia e de noite.

> **Especificação, não implementação.** Não existe família `jornada` em
> `theme/static_src/src/styles.css`; nenhuma tela aplica a régua abaixo.
> Ela permanece aqui como o desenho de referência para estados de pedido —
> quem for pintar estado de cartão hoje usa
> [`estado/*`](#estado-do-cartão-de-painel), que existe no CSS.

| Status      | Pigmento (fixo)      | Fundo claro   | Fundo escuro  | Tinta claro           | Tinta escuro          | Texto sobre pigmento |
|-------------|----------------------|---------------|---------------|-----------------------|-----------------------|----------------------|
| Bloqueado   | `urgencia/600` — `#7C3AED` | `#D4C3FD` (`urgencia/100`) | `#4B2B7D` (`urgencia/900`) | `#7321CC` (`urgencia/700`) | `#B3A1DC` (`urgencia/300`) | branco               |
| Atrasado    | `#C42F1A` (vermelho) | `#FECBCB`     | `#6C1E26`     | `erro/600`            | `erro/300`            | branco               |
| Sem prazo   | `#2E77B8` (azul)     | `#C4E0FD`     | `#023B69`     | `informacao/600`      | `informacao/300`      | branco               |
| Vence hoje  | `#FFCD43` (amarelo)  | `#FEE89B`     | `#423501`     | `atencao/600`         | `atencao/300`         | **preto** (`jornada/sobre-risco`) |
| No prazo    | `verde/600`          | `#B2FEC1`     | `#02401A`     | `verde/700`           | `verde/300`           | branco               |

- **Trilho** (progress bar fundo): `rgba(255,255,255,0.18)` — `jornada/trilho`
- **Trilho risco** (amarelo): `rgba(0,0,0,0.26)` — `jornada/trilho-risco`

> **Correção de 01/09/2026.** A linha "Bloqueado" trazia `#6C4AA6` na coluna
> de pigmento — valor que não existe em CSS nenhum, nem aqui nem no SIGT. As
> outras quatro colunas da mesma linha sempre foram a família `urgencia`
> (`100`, `900`, `700`, `300`), o que denuncia o pigmento como erro de
> transcrição: o degrau que faltava era o `urgencia/600` = `#7C3AED`. A
> tabela agora nomeia o token em vez de repetir o hexadecimal solto, para o
> erro não voltar. O SIGT alinhou o `roxo/500` dele no mesmo valor.

---

## 14. Responsividade

### Breakpoints e grade

| Dispositivo | Largura | Colunas | Sidebar                     |
|-------------|---------|---------|------------------------------|
| Desktop     | 1440px  | 12      | Completa (ícones + rótulos)  |
| Tablet      | 1024px  | 8       | Trilho de ícones (sem rótulo)|
| Móvel       | 390px   | 4       | Tab bar no rodapé            |

### Adaptações responsivas

- **Tabela → lista de cartões** no móvel (linha de dados vira card empilhado)
- **Sidebar lateral → trilho de ícones** no tablet
- **Sidebar lateral → rodapé (tab bar)** no móvel
- A grade responsiva usa tokens de espaçamento (`espaco/*`)

---

## 15. Princípios de design

Os seis princípios da identidade do Sigma — não são decoração, são o porquê das decisões:

| Princípio              | Como se materializa no sistema                              |
|------------------------|--------------------------------------------------------------|
| **Bordas arredondadas** | raio 10 no controle, 16 no bloco                            |
| **Espaço em branco**   | Escala de 4px, com margem de 64px na prancha principal       |
| **Cores naturais**     | Verde da bandeira, cinza azulado, sem saturação alta          |
| **Elementos orgânicos** | A folha marcando previsão, e as cinco marcas dos personagens |
| **Design limpo**       | Três cores na interface, dez estilos de texto                |
| **Interface acolhedora**| Texto que explica, nunca só o código do erro                 |

### Regras universais

- **Cor nunca é o único sinal.** Sempre há ícone, texto, forma ou posição acompanhando.
- **Contraste mínimo:** texto sobre fundo neutro busca 13:1; sobre fundo colorido, ícone apenas (não texto).
- **Tema claro vs. escuro:** escolha pelo ambiente (escuro onde a luz é artificial, claro onde entra sol), não pelo gosto.
- **Modo TV:** menu some, painel ocupa a parede, uma pergunta dominante — "estamos bem agora?". Font-size raiz 200%.

---

## Modo TV

Tela especial para exibição em galpão (16:9). Características:

- `font-size` da raiz em **200%**
- Sem menu/sidebar
- Um fato dominante grande (meta do turno), não quatro indicadores do mesmo tamanho
- Gráfico de gramatura ao vivo com faixa aceita visual
- Funciona em claro e escuro (escuro para luz artificial, claro para galpão com sol)

---

## Referência rápida de CSS Custom Properties

```css
:root {
  /* Tipografia */
  --font-titulo: 'Montserrat', sans-serif;
  --font-corpo: 'Poppins', sans-serif;

  /* Espaçamento (escala 4px) */
  --espaco-1: 4px;
  --espaco-2: 8px;
  --espaco-3: 12px;
  --espaco-4: 16px;
  --espaco-6: 24px;
  --espaco-8: 32px;
  --espaco-12: 48px;
  --espaco-16: 64px;

  /* Raio */
  --raio-nenhum: 0;
  --raio-sm: 4px;
  --raio-md: 10px;
  --raio-lg: 16px;
  --raio-xl: 24px;
  --raio-completo: 9999px;

  /* Traço */
  --traco-padrao: 1px;
  --traco-foco: 2px;

  /* Movimento */
  --transicao-curva: cubic-bezier(0.25, 0.1, 0.25, 1);
  --transicao-rapida: 180ms;
  --transicao-media: 300ms;
  --transicao-lenta: 500ms;

  /* Sombras */
  --sombra-sutil: 0 1px 2px rgba(23,28,33,0.06), 0 1px 3px rgba(23,28,33,0.10);
  --sombra-media: 0 4px 6px -1px rgba(23,28,33,0.10), 0 2px 4px -2px rgba(23,28,33,0.10);
  --sombra-alta: 0 10px 15px -3px rgba(23,28,33,0.12), 0 4px 6px -4px rgba(23,28,33,0.10);
  --sombra-flutuante: 0 2px 6px rgba(23,28,33,0.06), 0 22px 48px -12px rgba(23,28,33,0.22);
  --sombra-lateral: 0 6px 28px -6px rgba(23,28,33,0.14);
}

/* Tema Claro */
[data-tema="claro"], :root {
  --superficie-base: #F7F9FA;
  --superficie-elevada: #FFFFFF;
  --superficie-afundada: #EEF1F4;
  --superficie-inversa: #252C33;
  --superficie-flutuante: #FFFFFF;

  --texto-primario: #000000;
  --texto-secundario: #000000;
  --texto-legenda: #000000;
  --texto-marcador: #5F6871;
  --texto-desabilitado: #7D868F;
  --texto-sobre-marca: #FFFFFF;
  --texto-sobre-inversa: #EEF1F4;
  --texto-link: #046428;

  --borda-sutil: #E1E6EA;
  --borda-padrao: #7D868F;
  --borda-foco: #007A2F;

  --marca-identidade: #008D36;
  --marca-base: #007A2F;
  --marca-hover: #046428;
  --marca-ativo: #035522;
  --marca-sutil: #E6F4EC;

  --interacao-hover: #EEF1F4;
  --interacao-pressionado: #E1E6EA;
  --interacao-selecionado: #E6F4EC;
  --interacao-desabilitado: #EEF1F4;

  --sucesso-base: #046428;
  --sucesso-sutil: #E6F4EC;
  --sucesso-borda: #54B884;
  --atencao-base: #7D5E08;
  --atencao-sutil: #FFECB4;
  --atencao-borda: #E0B048;
  --erro-base: #B01F17;
  --erro-sutil: #FEE3DF;
  --erro-borda: #B01F17;
  --info-base: #164E8A;
  --info-sutil: #DBEBFE;
  --info-borda: #6AAEFF;
  --urgencia-base: #7321CC;
  --urgencia-sutil: #D4C3FD;
  --urgencia-borda: #7C3AED;
}

/* Tema Escuro */
[data-tema="escuro"] {
  --superficie-base: #171C21;
  --superficie-elevada: #252C33;
  --superficie-afundada: #363F47;
  --superficie-inversa: #EEF1F4;
  --superficie-flutuante: #454D55;

  --texto-primario: #FFFFFF;
  --texto-secundario: #FFFFFF;
  --texto-legenda: #FFFFFF;
  --texto-marcador: #FFFFFF;
  --texto-desabilitado: #7D868F;
  --texto-sobre-marca: #171C21;
  --texto-sobre-inversa: #252C33;
  --texto-link: #54B884;

  --borda-sutil: #363F47;
  --borda-padrao: #8E99A3;
  --borda-foco: #54B884;

  --marca-identidade: #008D36;
  --marca-base: #1FA25E;
  --marca-hover: #54B884;
  --marca-ativo: #73C59A;
  --marca-sutil: #0B3D1B;

  --interacao-hover: #363F47;
  --interacao-pressionado: #454D55;
  --interacao-selecionado: #0B3D1B;
  --interacao-desabilitado: #363F47;

  --sucesso-base: #54B884;
  --sucesso-sutil: #0B3D1B;
  --sucesso-borda: #54B884;
  --atencao-base: #E0B048;
  --atencao-sutil: rgba(56,55,42,1);
  --atencao-borda: #E0B048;
  --erro-base: #FF8271;
  --erro-sutil: #4A1310;
  --erro-borda: #FF8271;
  --info-base: #6AAEFF;
  --info-sutil: #132F4D;
  --info-borda: #6AAEFF;
  --urgencia-base: #B3A1DC;
  --urgencia-sutil: #4B2B7D;
  --urgencia-borda: #B3A1DC;
}
