---
titulo: Marca e identidade
ordem: 13
---

# 13 — Marca e identidade

A identidade própria do SIGMA: os dois personagens que representam a
jornada do produto dentro da fábrica, o que cada um cuida e onde
aparecem.

> Este documento responde *"quem são os personagens do SIGMA e o que cada
> um representa"*. [12 — Sistema de design](Style-Guide-IPEL.md) responde
> *"como isso vira interface"* — cor, ícone, contraste. Quando os dois
> falarem da mesma coisa, o sistema de design manda, porque é ele que o
> código consulta.

---

## Por que dois companheiros, e por que Industrial e Conversão

Na hierarquia do SIGMA (Empresa → Filial → Departamento → **Setor** →
Centro de Recurso → Recurso), é no **Setor** que a fábrica se divide:
`Industrial`, que produz a matéria-prima e a bobina, e `Conversão`, que
transforma essa bobina no produto acabado. Existem ainda dois setores que
não entram na jornada como um terceiro personagem: `Geral` (o que fica
fora do processo — cadastro, apoio, nada que produza) e `Preparo de
Massa` (a etapa anterior ao Industrial, ainda parte do mesmo início da
jornada — entra no território do Cedro, não pede personagem próprio). O
SIGMA existe para acompanhar essa jornada de ponta a ponta.

**Os dois departamentos não têm telas próprias — compartilham as mesmas.**
Apontamento, qualidade, área vermelha, manutenção, logística de
movimentação, OEE: a tela é a mesma para os dois; o que muda é o recurso,
a máquina e o dado que passam por ela. Uma liberação de lote da bobina do
Industrial e uma liberação de lote do produto acabado da Conversão
acontecem na mesma tela de qualidade, cada uma no contexto do seu
departamento. Por isso Cedro e Flora não são donos de tela nenhuma — são
donos de **contexto**: qual recurso, qual máquina, qual etapa da jornada
aquele dado representa.

Cedro e Flora são **companheiros de jornada**, não um casal — colegas que
cuidam de pontas diferentes do mesmo processo e se encontram exatamente
onde a bobina vira produto. Nenhum dos dois é secundário ao outro.

### O território não é a personalidade

`Industrial` e `Conversão` dizem **onde** cada personagem atua. Não dizem
**quem** ele é. No SIGMA, o personagem tem um epíteto de comportamento e a
interface registra separadamente a área representada:

| Personagem | Epíteto | Temperamento | Território operacional |
|---|---|---|---|
| **Cedro** | **o pioneiro** | iniciativa, firmeza, método e confiança | **Industrial**, incluindo Preparo de Massa |
| **Flora** | **a transformadora** | resolutiva, precisa, aberta e dinâmica | **Conversão** |

O epíteto aparece na apresentação do mascote. O território aparece como
contexto do dado na interface. Um não substitui o outro: `CEDRO — O
PIONEIRO` pode trazer `CONTEXTO INDUSTRIAL` abaixo; `FLORA — A
TRANSFORMADORA` pode trazer `CONTEXTO CONVERSÃO`.

**Assinatura proposta:** ***"Da bobina ao produto pronto, sem perder o
fio da história."***

---

## Os dois

### Cedro — o pioneiro

> Cedro é aquele que chega primeiro na sequência produtiva, abre o caminho e
> dá início a tudo. Trabalha com iniciativa e método, sustenta o ritmo e deixa
> cada etapa pronta para a seguinte. Cuida da matéria-prima e da bobina saindo
> das máquinas certas, no tempo certo, com o apontamento e a qualidade em dia
> antes de seguir para a Conversão.

`Pioneiro` indica a primeira etapa da jornada, nunca maior importância ou
hierarquia sobre Flora. Cedro abre o caminho; Flora o completa pela
transformação. Os dois continuam no mesmo nível.

Frase: *"O que começa bem, sustenta o resto da jornada."*

Território operacional: **Industrial**, incluindo Preparo de Massa.

Três detalhes visuais permanentes identificam Cedro e não podem ser
alterados:

1. **Franja de origem:** faixa clara estreita que sobe do focinho ao centro
   da testa e se abre discretamente no alto, sem formar um redemoinho.
2. **Tufos compactos:** tufos brancos laterais mais curtos, arredondados e
   controlados, formando uma silhueta firme.
3. **Cauda de base:** cauda espessa, com anéis escuros largos e curva baixa;
   em repouso, toca ou acompanha o solo.

Sua silhueta é mais larga no tronco, com centro de gravidade baixo. A
expressão neutra é concentrada, serena e segura — nunca zangada. Mesmo sem
cor, emblema, cenário ou movimento, precisa continuar reconhecível como
Cedro.

Representa: o contexto **Industrial** dentro de qualquer tela do
sistema — sequenciamento, apontamento de OP e de componente, tempos de
produção e paradas, OEE, qualidade da bobina, manutenção dos recursos
industriais, logística de movimentação e a integração que registra tudo
isso no ERP.

Onde aparece: não tem tela própria — aparece como marca de contexto
dentro de `/producao/`, `/setores/qualidade/`, `/setores/manutencao/`,
`/setores/logistica/` sempre que o recurso, a máquina ou o lote em
questão pertencer ao Industrial. Na mesma lista de liberação de lote, por
exemplo, cada linha do Industrial leva a marca do Cedro; cada linha da
Conversão leva a da Flora.

Cor proposta: `marca-base` (o verde do SIGMA).

Ícone proposto (Lucide): `tree-pine` — a origem, a base, o tronco que
sustenta.

### Flora — a transformadora

> Flora transforma trabalho concluído em resultado que pode seguir para o
> mundo. Recebe o que Cedro entrega e leva até o produto pronto. É dela a
> palavra final sobre liberar, reclassificar ou refugar — e o cuidado de
> garantir que o que sai da fábrica chega certo para quem espera.

Frase: *"O resultado é o que fica depois que a jornada termina."*

Território operacional: **Conversão**.

Três detalhes visuais permanentes identificam Flora e não podem ser
alterados:

1. **Máscara em arco:** área clara do rosto se abre sobre os olhos e fecha
   suavemente nas laterais, sugerindo um ciclo completo sem virar um símbolo
   desenhado na pelagem.
2. **Tufos em leque:** exatamente dois tufos brancos, pequenos e leves,
   presos simetricamente atrás das orelhas, na altura das orelhas. Nunca no
   topo da cabeça, testa, bochechas ou pescoço; têm contorno diferente dos
   tufos compactos de Cedro.
3. **Cauda de ciclo:** cauda um pouco mais leve, com anéis escuros mais
   estreitos e ponta que termina numa curva ascendente, sem formar um círculo
   perfeito.

Sua silhueta é mais esguia e vertical, com linhas abertas nos ombros. A
expressão neutra é atenta, acolhedora, resolutiva e queridinha, com olhos
grandes de mascote toon infantil.
Mesmo sem cor, emblema, cenário ou movimento, precisa continuar reconhecível
como Flora.

Representa: o contexto **Conversão** dentro de qualquer tela do
sistema — apontamento e tempos das máquinas de conversão, OEE, liberação
de lote e destinação de qualidade, manutenção dos recursos de conversão,
logística de movimentação e integração com WMS do produto pronto.

Onde aparece: as mesmas telas do Cedro — `/producao/`,
`/setores/qualidade/`, `/setores/manutencao/`, `/setores/logistica/` —
como marca de contexto sempre que o recurso, a máquina ou o lote em
questão pertencer à Conversão.

Cor proposta: `sucesso-base` (o mesmo verde, um tom adiante — o par de
Cedro, não uma família à parte).

Ícone proposto (Lucide): `package` — o produto pronto, fechado, saindo
para o mundo.

---

## Regras de uso (propostas, valem quando os dois forem implementados)

1. **A cor mora na marca (ícone/filete), nunca no corpo do texto** — nome
   e descrição usam `texto-secundario`, como qualquer texto de apoio.
   Confirmar contraste de cada par antes de usar em produção (skill
   `interface-sigma`).
2. **A marca segue o dado, não a tela.** Cedro e Flora nunca são
   escolhidos pela URL ou pelo módulo — são escolhidos pelo recurso/
   máquina/lote que a linha, o cartão ou o registro representa. Uma tela
   que lista os dois departamentos juntos (ex.: uma fila de qualidade)
   mostra as duas marcas lado a lado, uma por linha. Onde o dado não tem
   departamento (cadastro geral, configuração, usuário), não força
   nenhum dos dois; usa ícone comum.
3. **O mascote ilustrado (corpo inteiro) e a marca (ícone Lucide colorido)
   seguem regras opostas:**

   | O mascote ilustrado aparece | A marca (ícone colorido) aparece |
   |---|---|
   | tela de login | ao lado do dado/linha/cartão daquele contexto |
   | estado vazio de uma lista | cartão de indicador daquele contexto |
   | página inicial, se o SIGMA ganhar uma | filete/borda de destaque |
   | conclusão de uma tarefa longa | — |

   Onde não há dado para ler, o mascote acolhe; onde há dado, ele
   atrapalha — a marca (só o ícone, com a cor) já diz de qual
   departamento é aquele registro. Um sagui renderizado dentro de uma
   tabela é ruído; num estado vazio, é a diferença entre uma tela
   quebrada e uma tela que explica.
4. **Nenhuma cor nova.** As duas cores propostas já existem no sistema
   (`marca-base`, `sucesso-base`) — a identidade reaproveita, não
   inventa primitiva.
5. **Movimento visual.** No login, três esferas, partículas e brilho amplo diagonal difuso
   translúcido usam CSS; cada ciclo retorna ao estado inicial, inclusive com
   `prefers-reduced-motion`.
6. **Identidade não depende de cor ou pose.** Em silhueta, escala de cinza,
   recorte de rosto e turnaround neutro, Cedro e Flora precisam continuar
   diferentes. Cor, luz, emblema e movimento reforçam uma identidade que já
   existe na anatomia visual; não podem ser a única diferença.

---

## Estado atual e pendências

**Login concluído:** a entrada usa somente uma composição abstrata em CSS,
com três esferas verdes nítidas, partículas e brilho amplo diagonal difuso nos temas claro e escuro. Nenhum PNG de
fundo ou outro asset visual decorativo é carregado. Todos os ciclos retornam ao estado inicial;
os efeitos permanecem ativos com `prefers-reduced-motion`.

> **Contrato visual atual:** Cedro e Flora são personagens próprios do SIGMA.
> A floresta é a casa dos dois, mas nenhum objeto físico do sistema define a
> identidade. Cedro representa o começo e Flora o resultado por
> **silhueta + traços permanentes + postura + movimento + cor + emblema
> abstrato**. Ver `docs/marca/brief-seguir-prancha.md`.

**Primeira prancha rejeitada:** os PNGs gerados em 2026-08-22 provaram que a
definição anterior era insuficiente: os dois turnarounds ficaram praticamente
idênticos e a prancha comunicou departamentos, não personalidades. Essa
versão era rascunho técnico, não identidade aprovada, e foi substituída antes
da implementação da animação atual. A segunda geração, produzida depois da
aprovação da prova visual v2, obedece aos epítetos e aos seis detalhes
permanentes definidos acima. Foi aprovada visualmente e orienta os assets
animados atuais.

**Estado de implementação:**

| Item | Depende de |
|---|---|
| Nova prancha e turnarounds de Cedro e Flora | **concluído e aprovado** na segunda geração, com Cedro = **o pioneiro** e Flora = **a transformadora**, usando silhueta, face, tufos e cauda distintos. A primeira geração continua rejeitada |
| Cena de login | **concluída:** composição abstrata clara/escura em CSS, com três esferas, partículas e brilho amplo diagonal difuso contínuos. Não usa PNG de fundo, mascotes, galhos ou WebM; os efeitos permanecem ativos com `prefers-reduced-motion`. |
| Tokens de cor `personagem/cedro` e `personagem/flora` em `theme/static_src/src/styles.css` | decisão de adotar esta identidade — hoje nenhum template usa esses tokens |
| Ícones de marca (`tree-pine`, `package`) aplicados em tela real | primeira tela a marcar contexto Industrial/Conversão por linha ou cartão |
| Como o código sabe se um recurso/máquina é Industrial ou Conversão | a divisão já existe no banco (`setores.descricao`: `Geral`, `Industrial`, `Preparo de Massa`, `Conversão` — `CentroRecurso.setor` liga a esse registro), mas é texto livre, não um catálogo. Decisão de modelagem: continuar comparando pela `descricao` (frágil — não há garantia de escrita consistente entre filiais) ou promover para `TextChoices` antes de qualquer marca depender disso. `Preparo de Massa` conta como território do Cedro; `Geral` não usa nenhum dos dois. |
| Catálogo do código (enum Python com nome, cor, ícone, departamento) | a decisão de modelagem acima |

Nomes, epítetos, cores, ícones e traços permanentes definidos aqui governam a
segunda geração visual aprovada. As pendências são aplicar os ícones de contexto
em dados reais e decidir o catálogo que liga setor a personagem.
