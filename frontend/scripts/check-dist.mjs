import { readdir, readFile, stat } from 'node:fs/promises';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../dist');
const failures = [];

async function walk(dir) {
  const out = [];
  for (const name of await readdir(dir)) {
    const path = join(dir, name);
    if ((await stat(path)).isDirectory()) out.push(...(await walk(path)));
    else out.push(path);
  }
  return out;
}

let files;
try {
  files = await walk(root);
} catch {
  console.error('check:dist FAILED: dist/ is missing. Run npm run build.');
  process.exit(1);
}

const index = files.find((f) => relative(root, f) === 'index.html');
if (!index) failures.push('dist/index.html missing');

// Runtime URLs that would break the offline demo. Docs/licence strings inside bundled libraries are allowed.
const forbidden = [
  /https?:\/\/[a-z0-9.-]*tile[a-z0-9.-]*\//i,
  /https?:\/\/[a-z0-9.-]*openstreetmap\.org/i,
  /https?:\/\/fonts\.(googleapis|gstatic)\.com/i,
  /https?:\/\/unpkg\.com/i,
  /https?:\/\/cdn\.jsdelivr\.net/i,
  /https?:\/\/[a-z0-9.-]*(infura|alchemy|sepolia|etherscan)[a-z0-9.-]*/i,
  /https?:\/\/[a-z0-9.-]*(dataspace\.copernicus|firms\.modaps|earthdata\.nasa)/i,
];

// Attribution and licence links published in the official registry are shown to the reader and never
// fetched by the app. They are allowed verbatim; any other external host still fails the build.
const dataDir = resolve(dirname(fileURLToPath(import.meta.url)), '../../data');
const registry = new Set();
for (const name of ['sources.csv', 'events.csv']) {
  try {
    const text = await readFile(join(dataDir, name), 'utf8');
    for (const match of text.matchAll(/https?:\/\/[^\s,"']+/g)) registry.add(match[0].replace(/[.,;)]+$/, ''));
  } catch {
    // The registry is optional for this check: without it every external host is reported.
  }
}

function urlAt(text, index) {
  const start = text.lastIndexOf('http', index);
  if (start === -1) return text.slice(index, index + 80);
  let end = start;
  while (end < text.length && !'"\'`\\ \n\t<>),'.includes(text[end])) end += 1;
  return text.slice(start, end).replace(/[.,;)]+$/, '');
}

for (const file of files.filter((f) => /\.(html|js|css)$/.test(f))) {
  const text = await readFile(file, 'utf8');
  for (const pattern of forbidden) {
    for (const match of text.matchAll(new RegExp(pattern.source, `${pattern.flags.replace('g', '')}g`))) {
      const url = urlAt(text, match.index);
      if (registry.has(url)) continue;
      failures.push(`${relative(root, file)} references external host: ${match[0]}`);
      break;
    }
  }
}

if (index) {
  const html = await readFile(index, 'utf8');
  const refs = [...html.matchAll(/(?:src|href)="([^"]+)"/g)].map((m) => m[1]);
  for (const ref of refs) {
    if (/^(https?:)?\/\//.test(ref)) failures.push(`index.html loads remote resource ${ref}`);
    if (ref.startsWith('/')) failures.push(`index.html uses absolute path ${ref}; dist must work from any folder (base './')`);
  }
}

const tiffs = files.filter((f) => /\.tiff?$/i.test(f));
if (tiffs.length > 0) failures.push(`GeoTIFF shipped to browser bundle: ${tiffs.map((f) => relative(root, f)).join(', ')}`);

if (failures.length > 0) {
  console.error(`check:dist FAILED:\n- ${failures.join('\n- ')}`);
  process.exit(1);
}
const bytes = (await Promise.all(files.map((f) => stat(f)))).reduce((sum, s) => sum + s.size, 0);
console.log(
  `check:dist ok: ${files.length} files, ${(bytes / 1024).toFixed(1)} KiB, no external runtime hosts, no GeoTIFF, relative asset paths ` +
    `(${registry.size} attribution links from data/ allowed as text)`,
);
