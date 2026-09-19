import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import openapiTS, { astToString } from 'openapi-typescript';

const here = dirname(fileURLToPath(import.meta.url));
const check = process.argv.includes('--check');

const targets = [
  {
    source: 'contracts/openapi.yaml',
    specPath: resolve(here, '../../contracts/openapi.yaml'),
    outPath: resolve(here, '../src/api/generated/openapi.ts'),
  },
  {
    source: 'contracts/v2/openapi.v2.yaml',
    specPath: resolve(here, '../../contracts/v2/openapi.v2.yaml'),
    outPath: resolve(here, '../src/api/generated/openapi.v2.ts'),
  },
];

let failed = false;
for (const target of targets) {
  const header =
    '/* eslint-disable */\n' +
    (target.source === 'contracts/openapi.yaml'
      ? '// GENERATED from contracts/openapi.yaml (contracts-v1.0.0). Do not edit.\n'
      : `// GENERATED from ${target.source}. Do not edit.\n`) +
    '// Regenerate: npm run gen:api. CI/local check: npm run check:api.\n\n';
  const ast = await openapiTS(pathToFileURL(target.specPath), { exportType: false });
  const output = (header + astToString(ast)).replace(/\r\n/g, '\n');

  if (check) {
    let current;
    try {
      current = (await readFile(target.outPath, 'utf8')).replace(/\r\n/g, '\n');
    } catch {
      console.error(`check:api FAILED: ${target.outPath} is missing. Run npm run gen:api.`);
      failed = true;
      continue;
    }
    if (current !== output) {
      console.error(`check:api FAILED: generated types differ from ${target.source}. Run npm run gen:api.`);
      failed = true;
      continue;
    }
    console.log(`check:api ok: ${target.outPath} matches ${target.source}`);
  } else {
    await mkdir(dirname(target.outPath), { recursive: true });
    await writeFile(target.outPath, output, 'utf8');
    console.log(`generated ${target.outPath}`);
  }
}

if (failed) process.exit(1);
