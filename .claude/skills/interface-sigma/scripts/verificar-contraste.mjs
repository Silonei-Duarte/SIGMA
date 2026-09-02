/**
 * Verifica as razoes de contraste dos tokens do SIGMA contra a WCAG 2.1 AA.
 *
 * O Style Guide (docs/sigma/Style-Guide-IPEL.md) afirma razoes especificas
 * para os pares de cor da interface. Este script existe para que essa
 * afirmacao continue sendo verdade: ele recalcula todos os pares e falha se
 * algum deles cair abaixo do minimo.
 *
 * Uso:
 *     node .claude/skills/interface-sigma/scripts/verificar-contraste.mjs
 *
 * Sai com codigo 1 se qualquer par reprovar.
 *
 * Os valores abaixo sao copiados de theme/static_src/src/styles.css
 * (primitivas e tokens semanticos). Ao alterar uma cor la, atualize aqui no
 * mesmo commit — este script nao le o CSS diretamente de proposito, para
 * nao precisar de um parser de CSS so para isso.
 */

// ---------------------------------------------------------------------------
// Calculo (formula publica da WCAG 2.1, sem nada especifico de projeto)
// ---------------------------------------------------------------------------

const canaisDe = (cor) => {
  const n = cor.replace('#', '');
  return [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16));
};

/** Luminancia relativa, conforme a definicao da WCAG 2.1. */
const luminancia = (cor) => {
  const [r, g, b] = canaisDe(cor).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

const contraste = (frente, fundo) => {
  const [claro, escuro] = [luminancia(frente), luminancia(fundo)].sort((a, b) => b - a);
  return (claro + 0.05) / (escuro + 0.05);
};

const labDe = (cor) => {
  const [r, g, b] = canaisDe(cor).map((canal) => {
    const linear = canal / 255;
    return linear <= 0.04045
      ? linear / 12.92
      : Math.pow((linear + 0.055) / 1.055, 2.4);
  });
  const xyz = [
    0.4124564 * r + 0.3575761 * g + 0.1804375 * b,
    0.2126729 * r + 0.7151522 * g + 0.072175 * b,
    0.0193339 * r + 0.119192 * g + 0.9503041 * b,
  ];
  const branco = [0.95047, 1, 1.08883];
  const ajustar = (valor) => (valor > 216 / 24389 ? Math.cbrt(valor) : (24389 / 27 * valor + 16) / 116);
  const [x, y, z] = xyz.map((valor, indice) => ajustar(valor / branco[indice]));
  return [116 * y - 16, 500 * (x - y), 200 * (y - z)];
};

const deltaE2000 = (corA, corB) => {
  const [l1, a1, b1] = labDe(corA);
  const [l2, a2, b2] = labDe(corB);
  const c1 = Math.hypot(a1, b1);
  const c2 = Math.hypot(a2, b2);
  const cMedio = (c1 + c2) / 2;
  const ganho = 0.5 * (1 - Math.sqrt(cMedio ** 7 / (cMedio ** 7 + 25 ** 7)));
  const a1Linha = (1 + ganho) * a1;
  const a2Linha = (1 + ganho) * a2;
  const c1Linha = Math.hypot(a1Linha, b1);
  const c2Linha = Math.hypot(a2Linha, b2);
  const angulo = (a, b) => {
    const graus = Math.atan2(b, a) * 180 / Math.PI;
    return graus < 0 ? graus + 360 : graus;
  };
  const h1 = c1Linha === 0 ? 0 : angulo(a1Linha, b1);
  const h2 = c2Linha === 0 ? 0 : angulo(a2Linha, b2);
  const deltaL = l2 - l1;
  const deltaC = c2Linha - c1Linha;
  let deltaHAngulo = h2 - h1;
  if (c1Linha * c2Linha === 0) deltaHAngulo = 0;
  else if (deltaHAngulo > 180) deltaHAngulo -= 360;
  else if (deltaHAngulo < -180) deltaHAngulo += 360;
  const deltaH = 2 * Math.sqrt(c1Linha * c2Linha) * Math.sin(deltaHAngulo * Math.PI / 360);
  const lMedio = (l1 + l2) / 2;
  const cLinhaMedio = (c1Linha + c2Linha) / 2;
  let hMedio = h1 + h2;
  if (c1Linha * c2Linha !== 0) {
    if (Math.abs(h1 - h2) <= 180) hMedio /= 2;
    else hMedio = (hMedio + (hMedio < 360 ? 360 : -360)) / 2;
  }
  const fatorMatiz = 1
    - 0.17 * Math.cos((hMedio - 30) * Math.PI / 180)
    + 0.24 * Math.cos(2 * hMedio * Math.PI / 180)
    + 0.32 * Math.cos((3 * hMedio + 6) * Math.PI / 180)
    - 0.2 * Math.cos((4 * hMedio - 63) * Math.PI / 180);
  const escalaL = 1 + (0.015 * (lMedio - 50) ** 2) / Math.sqrt(20 + (lMedio - 50) ** 2);
  const escalaC = 1 + 0.045 * cLinhaMedio;
  const escalaH = 1 + 0.015 * cLinhaMedio * fatorMatiz;
  const rotacao = -2 * Math.sqrt(cLinhaMedio ** 7 / (cLinhaMedio ** 7 + 25 ** 7))
    * Math.sin(60 * Math.exp(-(((hMedio - 275) / 25) ** 2)) * Math.PI / 180);
  return Math.sqrt(
    (deltaL / escalaL) ** 2
    + (deltaC / escalaC) ** 2
    + (deltaH / escalaH) ** 2
    + rotacao * (deltaC / escalaC) * (deltaH / escalaH),
  );
};

// ---------------------------------------------------------------------------
// Primitivas — copiadas de styles.css, bloco `:root`
// ---------------------------------------------------------------------------

const verde = {
  50: '#e6f4ec', 200: '#8fd2ac', 300: '#54b884', 400: '#1fa25e',
  500: '#008d36', 600: '#007a2f', 700: '#046428', 800: '#0a5022', 900: '#0b3d1b',
};

const neutro = {
  0: '#ffffff', 50: '#f7f9fa', 100: '#eef1f4', 200: '#e1e6ea', 300: '#ccd2d8',
  400: '#a7b0b9', 500: '#8e99a3', 600: '#7d868f', 700: '#5f6871', 800: '#454d55',
  850: '#363f47', 900: '#252c33', 950: '#171c21',
};

const erro = { 100: '#fee3df', 300: '#ff8271', 600: '#b01f17', 900: '#4a1310' };
const atencao = { 100: '#ffecb4', 300: '#e0b048', 600: '#7d5e08', 900: '#402a05' };
const info = { 100: '#dbebfe', 300: '#6aaeff', 600: '#164e8a', 900: '#132f4d' };
const urgencia = { 100: '#d4c3fd', 300: '#b3a1dc', 600: '#7c3aed', 700: '#7321cc', 900: '#4b2b7d' };

// Superficies de cada tema.
const claro = { base: neutro[50], elevada: neutro[0], afundada: neutro[100] };
const escuro = { base: neutro[950], elevada: neutro[900], afundada: neutro[850] };

// texto-primario/secundario/legenda no tema claro nao vem mais de um degrau
// de neutro: sao preto puro por decisao de marca (ver styles.css).
const PRETO_PURO = '#000000';

// texto-sobre-marca no tema escuro e neutro-950 (quase preto), nao branco —
// ver comentario em styles.css. sobre-perigo, ao contrario, e branco fixo
// nos dois temas (botao-perigo mantem vermelho solido sempre).
const SOBRE_MARCA_ESCURO = neutro[950];
const BRANCO = neutro[0];

// ---------------------------------------------------------------------------
// Minimos exigidos
// ---------------------------------------------------------------------------

/*
 * TEXTO_PRINCIPAL fica acima do minimo da WCAG (4,5:1) de proposito — mesmo
 * criterio que o Style Guide adota para `texto-primario`.
 *
 * NAO_TEXTUAL cobre a WCAG 1.4.11 (contorno de campo, icone com significado,
 * anel de foco). Divisoria decorativa (`borda-sutil`) nao entra: ela nao
 * identifica componente nem estado, e por isso nao tem minimo.
 */
const TEXTO_PRINCIPAL = 7;
const TEXTO = 4.5;
const NAO_TEXTUAL = 3;
const PERCEPTIVEL = 1.03;
const SEPARACAO_ESTADOS = 12;

const pares = [
  ['tema claro / texto'],
  ['texto-primario sobre superficie-base', PRETO_PURO, claro.base, TEXTO_PRINCIPAL],
  ['texto-primario sobre superficie-elevada', PRETO_PURO, claro.elevada, TEXTO_PRINCIPAL],
  ['texto-secundario sobre superficie-base', PRETO_PURO, claro.base, TEXTO],
  ['texto-legenda sobre superficie-base', PRETO_PURO, claro.base, TEXTO],
  ['texto-link sobre superficie-base', verde[700], claro.base, TEXTO],
  ['texto-link sobre superficie-elevada', verde[700], claro.elevada, TEXTO],

  ['tema claro / marca e controles'],
  ['texto-sobre-marca no botao principal (marca-base)', neutro[0], verde[600], TEXTO],
  ['texto-sobre-marca no hover (marca-hover)', neutro[0], verde[700], TEXTO],
  ['sobre-perigo no botao-perigo-fundo', neutro[0], erro[600], TEXTO],
  ['botao secundario: texto-primario sobre superficie-elevada', PRETO_PURO, claro.elevada, TEXTO],
  ['borda-padrao sobre superficie-elevada', neutro[600], claro.elevada, NAO_TEXTUAL],
  ['borda-padrao sobre superficie-base', neutro[600], claro.base, NAO_TEXTUAL],
  ['borda-foco sobre superficie-base', verde[600], claro.base, NAO_TEXTUAL],
  ['borda-foco sobre superficie-elevada', verde[600], claro.elevada, NAO_TEXTUAL],
  ['marca-identidade como icone', verde[500], claro.elevada, NAO_TEXTUAL],

  ['tema claro / estados'],
  ['sucesso-base sobre sucesso-sutil', verde[700], verde[50], TEXTO],
  ['erro-base sobre erro-sutil', erro[600], erro[100], TEXTO],
  ['atencao-base sobre atencao-sutil', atencao[600], atencao[100], TEXTO],
  ['informacao-base sobre informacao-sutil', info[600], info[100], TEXTO],
  ['urgencia-base sobre urgencia-sutil', urgencia[700], urgencia[100], TEXTO],
  ['erro-borda no campo invalido, sobre superficie-elevada', erro[600], claro.elevada, NAO_TEXTUAL],
  ['atencao-borda solta, sobre superficie-elevada', atencao[600], claro.elevada, NAO_TEXTUAL],
  ['informacao-borda solta, sobre superficie-elevada', info[600], claro.elevada, NAO_TEXTUAL],

  /*
   * -destaque e fundo solido (botao redondo, etiqueta forte, hover) com
   * texto por cima — nao e so decoracao, e texto real, e nunca foi testado
   * antes (por isso o -300 herdado por analogia de referencia externa quebrou no escuro
   * sem ninguem notar). texto-primario para atencao (uso real nos
   * templates), texto-sobre-marca/sobre-perigo para sucesso/erro.
   */
  ['atencao-destaque + texto-primario', PRETO_PURO, atencao[300], TEXTO],
  ['sucesso-destaque + texto-sobre-marca', BRANCO, verde[600], TEXTO],
  ['erro-destaque + texto-sobre-marca', BRANCO, erro[900], TEXTO],
  ['urgencia-destaque + texto-sobre-urgencia', BRANCO, urgencia[600], TEXTO],
  ['botao-perigo-hover (erro-destaque) + sobre-perigo', BRANCO, erro[900], TEXTO],

  ['tema escuro / texto'],
  ['texto-primario sobre superficie-base', neutro[100], escuro.base, TEXTO_PRINCIPAL],
  ['texto-primario sobre superficie-elevada', neutro[100], escuro.elevada, TEXTO_PRINCIPAL],
  ['texto-secundario sobre superficie-base', neutro[300], escuro.base, TEXTO],
  ['texto-legenda sobre superficie-base', neutro[400], escuro.base, TEXTO],
  ['texto-legenda sobre superficie-afundada', neutro[400], escuro.afundada, TEXTO],
  ['texto-link sobre superficie-base', verde[300], escuro.base, TEXTO],
  ['texto-link sobre superficie-elevada', verde[300], escuro.elevada, TEXTO],

  ['tema escuro / marca e controles'],
  ['texto-sobre-marca no botao principal (marca-base)', neutro[950], verde[400], TEXTO],
  ['borda-padrao sobre superficie-base', neutro[500], escuro.base, NAO_TEXTUAL],
  ['borda-padrao sobre superficie-elevada', neutro[500], escuro.elevada, NAO_TEXTUAL],
  ['borda-padrao sobre superficie-afundada', neutro[500], escuro.afundada, NAO_TEXTUAL],
  ['borda-foco sobre superficie-base', verde[300], escuro.base, NAO_TEXTUAL],
  ['marca-base como icone sobre superficie-elevada', verde[400], escuro.elevada, NAO_TEXTUAL],
  ['atencao-borda solta, sobre superficie-elevada', atencao[300], escuro.elevada, NAO_TEXTUAL],
  ['erro-borda solta, sobre superficie-elevada', erro[300], escuro.elevada, NAO_TEXTUAL],
  ['informacao-borda solta, sobre superficie-elevada', info[300], escuro.elevada, NAO_TEXTUAL],
  ['urgencia-borda solta, sobre superficie-elevada', urgencia[300], escuro.elevada, NAO_TEXTUAL],

  ['tema escuro / estados'],
  ['sucesso-base sobre sucesso-sutil', verde[50], verde[700], TEXTO],
  ['erro-base sobre erro-sutil', erro[100], erro[600], TEXTO],
  ['atencao-base sobre atencao-sutil', atencao[100], atencao[600], TEXTO],
  ['informacao-base sobre informacao-sutil', info[100], info[600], TEXTO],
  ['urgencia-base sobre urgencia-sutil', urgencia[300], urgencia[900], TEXTO],

  ['atencao-destaque + texto-primario', neutro[100], atencao[900], TEXTO],
  ['sucesso-destaque + texto-sobre-marca', SOBRE_MARCA_ESCURO, verde[300], TEXTO],
  ['erro-destaque + texto-sobre-marca', SOBRE_MARCA_ESCURO, erro[300], TEXTO],
  ['urgencia-destaque + texto-sobre-urgencia', BRANCO, urgencia[600], TEXTO],
  /* botao-perigo-hover e fixado em erro-900 no escuro (nao herda
     erro-destaque=erro-300): sobre-perigo e branco fixo, e branco contra
     erro-300 so da 2,42:1 — por isso o token foi desacoplado em styles.css. */
  ['botao-perigo-hover (fixo) + sobre-perigo', BRANCO, erro[900], TEXTO],
  ['sobre-perigo no botao-perigo-fundo/ativo', BRANCO, erro[600], TEXTO],

  /*
   * A superficie inversa e uma ilha do tema oposto: a notificacao flutuante
   * e escura dentro do claro. O conteudo dela nao pode usar os tokens
   * normais — marca-base ali daria contraste baixo demais.
   */
  ['superficie inversa'],
  ['texto-sobre-inversa no claro', neutro[100], neutro[900], TEXTO_PRINCIPAL],
  ['marca-sobre-inversa no claro', verde[300], neutro[900], TEXTO],
  ['texto-sobre-inversa no escuro', neutro[900], neutro[100], TEXTO_PRINCIPAL],
  ['marca-sobre-inversa no escuro', verde[700], neutro[100], TEXTO],

  ['separacao entre superficies'],
  ['claro: elevada sobre base', claro.elevada, claro.base, PERCEPTIVEL],
  ['claro: afundada sobre elevada', claro.afundada, claro.elevada, PERCEPTIVEL],
  ['escuro: elevada sobre base', escuro.elevada, escuro.base, PERCEPTIVEL],
  ['escuro: afundada sobre elevada', escuro.afundada, escuro.elevada, PERCEPTIVEL],
];

const conjuntosDeEstados = {
  'tema claro / estados-base': {
    sucesso: verde[700], atencao: atencao[600], erro: erro[600], informacao: info[600], urgencia: urgencia[700],
  },
  'tema claro / estados-sutil': {
    sucesso: verde[50], atencao: atencao[100], erro: erro[100], informacao: info[100], urgencia: urgencia[100],
  },
  'tema escuro / estados-base': {
    sucesso: verde[50], atencao: atencao[100], erro: erro[100], informacao: info[100], urgencia: urgencia[300],
  },
  'tema escuro / estados-sutil': {
    sucesso: verde[700], atencao: atencao[600], erro: erro[600], informacao: info[600], urgencia: urgencia[900],
  },
  // Estado do cartao de painel: um conjunto so, sem sufixo de tema, porque
  // o pigmento NAO troca entre claro e escuro. Cinco cartoes lado a lado no
  // mesmo painel e exatamente o caso que a regra de dE 12 cobre.
  'os dois temas / estado-do-cartao': {
    pendencia: erro[600], prestador: info[600], risco: atencao[300],
    travado: urgencia[600], aprovado: verde[600],
  },
};

const verificarSeparacaoDeEstados = () => {
  for (const [tema, cores] of Object.entries(conjuntosDeEstados)) {
    const titulo = `separacao perceptiva / ${tema}`;
    console.log(`\n${titulo}`);
    console.log('-'.repeat(titulo.length));

    const nomes = Object.keys(cores);
    const medidas = [];
    for (let indice = 0; indice < nomes.length; indice++) {
      for (let comparado = indice + 1; comparado < nomes.length; comparado++) {
        medidas.push({
          descricao: `${nomes[indice]} x ${nomes[comparado]}`,
          valor: deltaE2000(cores[nomes[indice]], cores[nomes[comparado]]),
        });
      }
    }
    medidas.sort((primeiro, segundo) => primeiro.valor - segundo.valor);

    for (const [indice, medida] of medidas.entries()) {
      const passou = medida.valor >= SEPARACAO_ESTADOS;
      verificados++;
      if (!passou) reprovados++;
      if (indice < 3 || !passou) {
        console.log(`${passou ? '  ok ' : 'FALHA'} ${`dE ${medida.valor.toFixed(1)}`.padStart(7)}  minimo ${SEPARACAO_ESTADOS}  ${medida.descricao}`);
      }
    }
    console.log(`       ${medidas.length - 3} pares adicionais aprovados.`);
  }
};

// ---------------------------------------------------------------------------
// Execucao
// ---------------------------------------------------------------------------

let verificados = 0;
let reprovados = 0;

for (const [descricao, frente, fundo, minimo] of pares) {
  if (frente === undefined) {
    console.log(`\n${descricao}`);
    console.log('-'.repeat(descricao.length));
    continue;
  }

  const razao = contraste(frente, fundo);
  const passou = razao >= minimo;

  verificados++;
  if (!passou) reprovados++;

  const rotulo = passou ? '  ok ' : 'FALHA';
  const valor = `${razao.toFixed(2)}:1`.padStart(7);
  console.log(`${rotulo} ${valor}  minimo ${String(minimo).padStart(4)}  ${descricao}`);
}

verificarSeparacaoDeEstados();

console.log();

if (reprovados > 0) {
  console.error(`${reprovados} de ${verificados} pares reprovaram.`);
  process.exit(1);
}

console.log(`${verificados} pares verificados, nenhum reprovado.`);
