/**
 * Copia a fonte real dos tokens (src/styles.css) para dentro da skill
 * interface-sigma, para que o agente carregue o design system sem sair
 * do pacote da skill.
 *
 * src/styles.css continua a unica fonte editavel — este script so gera
 * uma copia de leitura; roda a cada `npm run build`, nunca precisa de
 * sincronizacao manual.
 */

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const aqui = dirname(fileURLToPath(import.meta.url));
const origem = join(aqui, '..', 'src', 'styles.css');
const destino = join(aqui, '..', '..', '..', '.claude', 'skills', 'interface-sigma', 'assets', 'tokens.css');

mkdirSync(dirname(destino), { recursive: true });

// A copia e so de leitura para o agente, nao uma entrada CSS. As diretivas
// abaixo fazem a IDE procurar dependencias a partir da pasta da skill, onde
// nao existe node_modules, e geram falsos avisos do Tailwind.
const conteudo = readFileSync(origem, 'utf8')
  .replace(
    /^@import\s+"tailwindcss";\s*$/m,
    '/* @import "tailwindcss" existe so na fonte real (theme/static_src/src/styles.css); */'
  )
  .replace(
    /^@plugin\s+"daisyui";\s*$/m,
    '/* @plugin "daisyui" existe so na fonte real (theme/static_src/src/styles.css); */'
  );
writeFileSync(destino, conteudo);

console.log(`tokens.css sincronizado em ${destino}`);
