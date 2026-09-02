---
titulo: Arquitetura técnica
ordem: 2
---

## 3. Arquitetura técnica e infraestrutura

O SIGMA é uma aplicação web server-side. Isso significa que a maior parte das regras de negócio roda no servidor, dentro do Django, e o navegador atua como interface para o usuário. Algumas telas usam JavaScript para melhorar a operação, mas a decisão de salvar, integrar, validar permissão e chamar sistemas externos fica no backend.

As tecnologias foram escolhidas para atender três necessidades principais:

1. Manter uma aplicação web com usuários, permissões, telas e formulários.
2. Conversar com bancos e sistemas industriais diferentes, como PostgreSQL, Oracle ERP, Alchemy, WMS e telemetria HTTP.
3. Executar tarefas automáticas em segundo plano, como envio de filas, importação de paletes e consolidação de OEE.

### 3.1 Backend

O backend é escrito em Python e usa Django como estrutura principal. O Django organiza as telas, rotas, modelos de banco, autenticação, permissões e formulários. A aplicação roda em ASGI por meio do Daphne, permitindo HTTP normal e WebSocket no mesmo processo.

O PostgreSQL é o banco operacional local. Ele guarda usuários, cadastros, filas, logs, parâmetros e histórico operacional. O acesso normal da aplicação a esse banco é feito pelo ORM do Django, ou seja, os modelos Python representam as tabelas locais e concentram as operações de gravação, consulta e atualização. O Oracle não substitui o PostgreSQL; ele entra como sistema éxterno consultado para OPs, estoque, lote, movimentos e operadores.

As chamadas HTTP externas usam `requests` nas chamadas SOAP ao Sapiens, nas chamadas JSON ao WMS e na coleta de telemetria dos recursos.

Para documentos e saídas auxiliares, o sistema usa bibliotecas como `pandas`, `reportlab` e `qrcode`, permitindo exportacão de Excel, geracao de PDF/etiquetas e QR Codes.

### 3.2 Frontend

O frontend é composto por templates renderizados pelo Django. Isso quer dizer que as páginas são montadas no servidor e entregues prontas ao navegador. O estilo visual usa Tailwind com tema local baseado em tokens semânticos; os ícones de interface usam exclusivamente a biblioteca Lucide.

O JavaScript é usado principalmente onde há interação operacional mais dinâmica: sequenciamento por arrastar/organizar, atualização de balança em tempo real, troca de OP e filtros de tela. O WebSocket permite que certas informações cheguem ao navegador sem recarregar a página.

O cabeçalho possui seletor de tema claro/escuro. A escolha é salva no navegador e aplicada novamente ao abrir outra tela. O tema escuro ajusta fundos, textos, bordas, campos, tabelas, modais, links e estados de seleção para manter contraste; as telas que não usam o template base, como Rastreamento de Lote, aplicam a mesma classe de tema e, portanto, usam os mesmos tokens visuais.

#### 3.2.1 Arquitetura obrigatória de tema visual

O tema do SIGMA é baseado em **tokens semânticos**, definidos em `theme/static_src/src/styles.css`. Um token descreve a função visual de um elemento, e não uma cor fixa. Por exemplo, `bg-superficie-elevada` significa fundo de card/painel, `text-texto-primario` significa texto principal e `border-borda-sutil` significa borda padrão. O mesmo token recebe um valor claro no tema normal e um valor escuro dentro de `html.tema-escuro`.

O fluxo é:

```text
botão de tema -> classe html.tema-escuro -> variáveis CSS dos tokens -> utilities Tailwind -> tela renderizada
```

Assim, uma tela não precisa saber qual tom usar no modo escuro. Ela declara somente o papel visual do elemento e recebe automaticamente a cor correta nos dois temas.

Os principais grupos de tokens são:

| Papel | Exemplos de utility Tailwind | Uso |
|---|---|---|
| Estrutura neutra | `bg-superficie-base`, `bg-superficie-elevada`, `bg-superficie-afundada`, `bg-superficie-inversa` | Página, cards e modais, cabeçalhos de tabela e notificações/contexto. |
| Texto e borda | `text-texto-primario`, `text-texto-secundario`, `text-texto-legenda`, `border-borda-sutil`, `border-borda-padrao` | Hierarquia de leitura e contornos. |
| Estados de negócio | `bg-sucesso-sutil`, `bg-atencao-sutil`, `bg-informacao-sutil`, `bg-erro-sutil`, `bg-erro-destaque`, `text-sucesso-base`, `text-atencao-base`, `text-informacao-base`, `text-erro-base` | Sucesso, pendência, informação, erro e bloqueio. |
| Composição própria | `bg-hero`, `bg-hero-superficie`, `border-hero-borda`, `text-hero-texto` | Página inicial com gradiente e transparência próprios. |

Os nomes de token usam o papel semântico completo (renomeados em 2026-08-19 a partir da forma abreviada anterior, ex.: `text-principal` virou `text-texto-primario`). Não existe hoje token de "operação industrial" (`bg-operacao-sutil`, `bg-selecao`) — versão anterior deste documento os citava, mas eles nunca chegaram a existir em `styles.css`; se a necessidade voltar, o token nasce em `theme/static_src/src/styles.css` antes de ser citado aqui.

Essa arquitetura foi escolhida porque evita dois problemas: listas globais de sobrescritas que precisam conhecer todas as classes Tailwind usadas nas telas e duplicação de `tema-escuro:*` em cada template. Ambos são frágeis: uma tela nova poderia esquecer uma cor, ficar ilegível no modo escuro e exigir uma correção isolada. Com tokens, a alteração de uma paleta é centralizada, revisável e aplicada de forma consistente a todo o sistema.

**Regra para novas telas e alterações:** não usar cores neutras cruas como `bg-white`, `bg-gray-100`, `text-gray-700` ou `border-gray-300` para elementos que acompanham o tema. Deve-se usar o token equivalente. Também não criar utilities `tema-escuro:*`; elas não fazem parte da arquitetura atual. Se faltar uma função visual, criar um novo token semântico em `styles.css`, com valor nos dois temas, antes de usá-lo no template.

As exceções são deliberadas: cores de marca e navegação, cores que expressam estado específico de negócio, elementos de biblioteca que exigem seletor próprio (como FullCalendar), efeitos visuais da página inicial e regras de impressão de etiqueta. Mesmo nesses casos, a preferência é criar um token; uma cor fixa só deve permanecer quando o elemento não precisa acompanhar o tema ou quando representa uma informação visual intencionalmente fixa.

O arquivo `styles.css` é a única fonte de verdade. O bloco `@theme` declara os tokens e gera as utilities Tailwind; `html.tema-escuro` redefine seus valores; e `@layer base` aplica os tokens aos campos `input`, `select` e `textarea`. O CSS compilado em `theme/static/css/dist/styles.css` é gerado e não deve ser editado manualmente.

O documento `docs/Style-Guide-IPEL.md` complementa esta seção como manual normativo de interface: define os papéis de cor, componentes, botões, ícones, foco, alertas, tabelas e comportamento nos temas claro e escuro. Este documento explica a arquitetura e a razão técnica; o Style Guide define como a interface deve ser construída na prática.

Depois de qualquer alteração em token ou classe Tailwind, executar localmente:

```bash
cd theme/static_src
npm run build
```

Antes de publicar, validar ao menos `manage.py check`, a renderização dos templates afetados e contraste nos dois temas. Em produção, enviar primeiro o `styles.css` atualizado, executar o build Tailwind e `collectstatic`, pois o SIGMA usa arquivos estáticos com hash.

### 3.2.2 Validação de telas

Os testes Django cobrem regra de negócio, autorização e integrações isoladas.
Alterações de telas ou fluxos também usam Playwright com Chromium contra o
servidor de testes local: o navegador percorre o formulário real e não acessa
LDAP, ERP, WMS ou outro serviço externo. O navegador e o adaptador
`pytest-playwright` pertencem somente ao ambiente de desenvolvimento.

O teste de navegador é opt-in na esteira local, para que uma mudança apenas de
backend não dependa do Chromium. Em telas alteradas, ele é obrigatório. Em
alterações visuais críticas — componentes compartilhados, tokens, tema,
tipografia, cards, tabelas, layout ou responsividade — a validação inclui
screenshots desktop e mobile determinísticos, revisados junto do diff. Em
falhas, traces e screenshots são preservados localmente para diagnóstico e não
entram no repositório.

### 3.3 Rede dos equipamentos

Os equipamentos precisam de acesso HTTPS ao SIGMA para abrir a aplicação e carregar todos os estilos, ícones e recursos do calendário. Esses arquivos são distribuídos localmente pelo próprio servidor, sem dependência de CDN ou de acesso externo.

| Endereço | Finalidade |
|---|---|
| `app.suaempresa.com.br` | Aplicação SIGMA e seus arquivos estáticos locais, incluindo o CSS principal. |

Quando os equipamentos tiverem bloqueio de acesso externo, não é necessária nenhuma liberação para bibliotecas visuais. O acesso a `app.suaempresa.com.br` é suficiente para a interface completa.

### 3.5 Arquitetura lógica

```text
Usuários
  |
  | HTTP / WebSocket
  v
SIGMA / Django / Daphne / Channels
  |
  +--> PostgreSQL local: dados operacionais, filas, parâmetros, status
  |
  +--> Oracle ERP: consultas ao ERP
  |
  +--> Sapiens SOAP: efetivação de apontamentos e movimentos
  |
  +--> WMS XC API: envio de novo lote e ajuste de estoque
  |
  +--> WMS via DBLINK no Oracle: consulta de paletes/local/saldo
  |
  +--> Oracle Alchemy: análises de bobina
  |
  +--> Telemetria HTTP: leitura de recursos e balança
  |
  +--> SMTP: notificações de manutenção
```

---

*Verificado contra o código em 2026-08-24.*
