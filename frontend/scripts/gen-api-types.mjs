import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import openapiTS, { astToString } from 'openapi-typescript';

const here = dirname(fileURLToPath(import.meta.url));
const specPath = resolve(here, '../../contracts/openapi.yaml');
const outPath = resolve(here, '../src/api/generated/openapi.ts');
const check = process.argv.includes('--check');

const header =
  '/* eslint-disable */\n' +
  '// GENERATED from contracts/openapi.yaml (contracts-v1.0.0). Do not edit.\n' +
  '// Regenerate: npm run gen:api. CI/local check: npm run check:api.\n\n';

const ast = await openapiTS(pathToFileURL(specPath), { exportType: false });
const output = (header + astToString(ast)).replace(/\r\n/g, '\n');

if (check) {
  let current = '';
  try {
    current = (await readFile(outPath, 'utf8')).replace(/\r\n/g, '\n');
  } catch {
    console.error(`check:api FAILED: ${outPath} is missing. Run npm run gen:api.`);
    process.exit(1);
  }
  if (current !== output) {
    console.error('check:api FAILED: generated types differ from contracts/openapi.yaml. Run npm run gen:api.');
    process.exit(1);
  }
  console.log('check:api ok: src/api/generated/openapi.ts matches contracts/openapi.yaml');
} else {
  await mkdir(dirname(outPath), { recursive: true });
  await writeFile(outPath, output, 'utf8');
  console.log(`generated ${outPath}`);
}
