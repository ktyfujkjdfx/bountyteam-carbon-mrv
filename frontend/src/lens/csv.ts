// Minimal CSV reader for the official data/ tables: BOM-safe, quote-aware, header-keyed.

function stripBom(text: string): string {
  return text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
}

export function parseCsv(text: string): Record<string, string>[] {
  const lines = stripBom(text).trim().split(/\r?\n/);
  const header = (lines.shift() ?? '').split(',');
  return lines.map((line) => {
    const cells: string[] = [];
    let cell = '';
    let quoted = false;
    for (const char of line) {
      if (char === '"') quoted = !quoted;
      else if (char === ',' && !quoted) {
        cells.push(cell);
        cell = '';
      } else cell += char;
    }
    cells.push(cell);
    return Object.fromEntries(header.map((name, i) => [name, cells[i] ?? '']));
  });
}

export function parseGeoJsonText<T>(raw: string): T {
  return JSON.parse(stripBom(raw)) as T;
}
