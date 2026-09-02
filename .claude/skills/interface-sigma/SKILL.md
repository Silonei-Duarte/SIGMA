---
name: interface-sigma
description: O padrão de interface do SIGMA — tokens semânticos de cor/tema, tipografia, componentes e build do Tailwind, no padrão de identidade visual da IPEL. Aponta para `docs/sigma/Style-Guide-IPEL.md` (normativo) e para `docs/sigma/02-arquitetura-tecnica.md` (arquitetura) em vez de duplicá-los. Use ao criar ou alterar template, tela nova, cor, tema claro/escuro, ou ao migrar tela antiga para o padrão. Dispara em "tela", "template", "cor", "tema escuro", "contraste", "token", "componente", "Tailwind", "botão", "tabela", "modal", "refatorar interface", "identidade visual", "padrão IPEL".
paths: "templates/** theme/**"
---

# Interface do SIGMA

O SIGMA segue a identidade visual da IPEL: paleta, tipografia e papéis
semânticos são da empresa. Os tokens de cor usam o nome completo do papel
semântico (`text-texto-primario`, `border-borda-sutil`, `bg-erro-base`,
`bg-informacao-sutil`...), não abreviações locais.

Este skill não recria o manual — ele garante que quem for tocar template
pare e leia:

- [`docs/sigma/Style-Guide-IPEL.md`](../../../docs/sigma/Style-Guide-IPEL.md) —
  manual normativo: papéis de cor, componentes, botões, ícones, foco,
  alertas, tabelas, comportamento nos temas claro e escuro. **Fonte da
  verdade de "como construir a interface na prática".**
- `docs/sigma/02-arquitetura-tecnica.md`, seção 3.2 (e 3.2.1) — a arquitetura
  técnica: por que o tema é baseado em tokens semânticos definidos em
  `theme/static_src/src/styles.css`, e por que não existem utilities
  `tema-escuro:*` no projeto.

## Grupos de token

| Papel | Utility |
|---|---|
| Superfícies | `bg-superficie-base/elevada/afundada/inversa` |
| Texto | `text-texto-primario/secundario/legenda/desabilitado/sobre-marca/link/sobre-inversa` |
| Borda | `border-borda-sutil`, `border-borda-padrao`, `border-borda-foco` |
| Marca | `bg`/`text`/`border-marca-identidade/base/hover/ativo/sutil/sobre-inversa` |
| Estados | `bg`/`text`/`border-{sucesso,atencao,erro,informacao,urgencia}-base/sutil/borda` |
| Interação | `bg-interacao-hover/pressionado/selecionado/desabilitado` |
| Raio | `rounded-sm/md/lg/xl/full` |
| Extensões do sistema | `{bg,text,border}-{sucesso,atencao,erro}-destaque` (variação sólida para controle/etiqueta com cor forte), `botao-perigo-fundo/hover/ativo` + `sobre-perigo` (botão de ação destrutiva), `hero-borda/superficie/texto` + `bg-hero` (efeito decorativo da tela inicial), `color-logo-sigt` |

## As três regras que valem para qualquer template novo

1. **Nunca cor neutra crua** (`bg-white`, `bg-gray-100`, `text-gray-700`,
   `border-gray-300`) em elemento que acompanha o tema. Use o token
   semântico equivalente.
2. **Nunca crie `tema-escuro:*` novo.** Se falta um papel visual, o token
   novo nasce em `styles.css` (bloco `@theme` + redefinição em
   `html.tema-escuro`), com valor nos dois temas, antes de usar no
   template. Nomeie pelo papel semântico completo (`texto-`, `borda-`,
   `-base`/`-sutil`/`-borda`), não com uma abreviação nova.
3. **`theme/static/css/dist/styles.css` é gerado — nunca edite à mão.**
   Depois de mexer em token ou classe Tailwind:

   ```bash
   cd theme/static_src
   npm run build
   ```

   Antes de publicar: `manage.py check`, renderizar os templates
   afetados, e conferir contraste nos dois temas.

## Estrutura visual comum

Além de tokens, toda tela segue uma mesma composição: tipografia Poppins e
Montserrat, grade de 4px, raio maior no cartão externo, bloco interno menor,
elevação discreta e estados consistentes. Leia
[references/estrutura-de-telas.md](references/estrutura-de-telas.md) antes
de criar ou revisar cartão, formulário, tabela, painel ou página de listagem.
Essa referência usa a identidade e os tokens do SIGMA; não importa marca,
personagens ou componentes exclusivos de outro sistema.

## Componentes compartilhados

Antes de criar variantes locais, reutilize as utilities de `styles.css`:
`cartao` para painel estrutural, `cartao-bloco` para agrupamento interno,
`cartao-indicador` para KPI, `tabela-padrao`/`tabela-cabecalho`/
`tabela-linha` para tabelas, e os controles globais para input, select,
textarea, checkbox e radio. Cartão indicador usa raio de 16px e sombra suave;
painel estrutural usa raio de 24px e borda sutil. Checkbox e radio têm 16px,
cor semântica e foco visível. Ações exclusivamente por ícone usam as
utilities semânticas `botao-informacao-icone`, `botao-sucesso-icone`,
`botao-atencao-icone`, `botao-perigo-icone` ou `botao-urgencia-icone`, sempre com rótulo acessível.

## Ícones

Exclusivamente **Lucide** — não misturar outra biblioteca de ícone numa
tela nova.

## Marcador de valor vazio

O que a tela mostra quando um valor não existe tem três faixas, escolhidas
pelo **tipo de espaço**, não pelo gosto da tela:

1. **Célula densa de tabela** → `-` (hífen curto). Nunca `—` (travessão —
   parece traço do desenho, não dado ausente) e nunca célula em branco.
2. **Campo com rótulo e largura própria** (ficha, painel de detalhe) →
   `não consta`.
3. **Ausência que é a resposta** → o texto do que a ausência significa
   ("Sem configuração salva", "sem motivo registrado", "sem prazo").

A faixa 3 **manda sobre as outras duas**: quando o vazio é informação,
escreva o que ele significa em vez de usar marcador. Telas vizinhas usam
o mesmo marcador para o mesmo tipo de ausência — a escolha é conferida no
mesmo commit.

**Exceção obrigatória — valor que alimenta dado:** se a célula, atributo
ou texto é lido por script (JS que monta `key`, cache ou payload, campo
`data-*`), ele não é exibição — mantenha o valor cru, **sem** marcador.
Marcador de exibição corrompe o dado que segue para o backend.

## Texto de ajuda com dono único

Texto de ajuda que aparece em **dois lugares na mesma tela** — a cópia
visível e a cópia acessível apontada por `aria-describedby` — tem **um
dono só**: partial incluído duas vezes (`{% include %}`), ou bloco com
`{% block %}` quando for hierarquia de template. A cópia `sr-only` nunca
é segunda escrita à mão: duas cópias escritas à mão é o defeito em si —
elas divergem na primeira manutenção. Dica que aparece uma única vez pode
ficar inline.

## Verificar contraste

```bash
node .claude/skills/interface-sigma/scripts/verificar-contraste.mjs
```

Recalcula a razão de contraste WCAG 2.1 AA de cada par de token (texto,
borda, estado) e a separação perceptiva CIEDE2000 entre cores de estado nos
dois temas; sai com código 1 se algum reprovar. Rode sempre que mexer em valor
de token — os valores do script são copiados de `styles.css`, não lidos
automaticamente; atualize os dois juntos. Os pares atuais passam; uma
reprovação é bloqueio da mudança de token.

## Tokens dentro da skill

`assets/tokens.css` é uma cópia gerada de `theme/static_src/src/styles.css`,
com as diretivas de entrada `@import "tailwindcss"` e `@plugin "daisyui"`
comentadas porque a cópia não é uma entrada CSS da aplicação. Nunca edite esse arquivo à mão, ele é sobrescrito a cada
`npm run build` (script `sync:skill-tokens` em `theme/static_src/package.json`).
A fonte editável continua sendo só `styles.css`; a cópia existe para que
o agente carregue os tokens reais sem sair do pacote da skill. Se os dois
arquivos divergirem fora de uma janela entre editar e rodar `npm run
build`, é bug do script de sincronização, não motivo para editar a cópia.

[references/lacunas-de-design.md](references/lacunas-de-design.md) — lista
viva de pendência de token/decisão de design que ainda não tem resposta
(ex.: papel sem equivalente numa referência externa). Adicione um item ali
em vez de decidir sozinho quando a resposta certa não é óbvia.

## Acessibilidade

Leia [references/acessibilidade.md](references/acessibilidade.md) antes de
entregar componente, formulário, modal ou botão de ícone. Contraste é só uma
parte: semântica, foco e teclado também são critério de aceite.

## Migrar uma tela que ainda usa cor fora do padrão

Se encontrar `bg-white`, hexadecimal solto, ou `dark:` por cor numa tela
antiga, o roteiro é: inventariar (grep por cor literal), mapear cada cor
para o papel semântico certo pela função (não pela aparência), migrar a
tela **inteira** de uma vez (nunca pela metade), depois tipografia e
espaçamento, depois verificar contraste nos dois temas. Isso é
exatamente o trabalho da futura auditoria de telas existentes do SIGMA —
quando ela começar, peça o roteiro completo em sete passos; este skill
não o antecipa aqui porque ele é longo e só vale a pena carregar quando a
demanda for essa.

## O que este skill não faz

Não repete tabela de tokens, nem paleta de cor, nem exemplo de componente
em prosa — isso já existe e está mantido em `Style-Guide-IPEL.md`.
`assets/tokens.css` não é exceção a essa regra: é cópia gerada do CSS
real (ver seção acima), exceto pelas diretivas de entrada comentadas para a IDE,
não documentação escrita à mão — por isso não pode divergir da fonte. Se o manual e o código divergirem, é achado para
o agente `revisor`/`documentador`, não motivo para duplicar conteúdo aqui.
