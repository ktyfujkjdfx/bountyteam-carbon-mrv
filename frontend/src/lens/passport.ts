// Passport serialisation and integrity check, shared by the adapter (which fixes the hash) and the panel
// (which verifies it). Keeping both on one function is what makes the check meaningful.

import type { LensResult } from './types';

/** Canonical content the hash covers. content_sha256 itself is excluded: a value cannot hash itself. */
export function passportContent(result: LensResult): string {
  const passport = Object.fromEntries(Object.entries(result.passport).filter(([key]) => key !== 'content_sha256'));
  return JSON.stringify(
    {
      passport,
      request: result.request,
      area_ha: result.area_ha,
      calculation_status: result.calculation_status,
      evidence_status: result.evidence_status,
      stock: result.stock,
      baseline: result.baseline,
      uncertainty: result.uncertainty,
      units: result.units,
      coverage: result.coverage,
      timeline: result.timeline,
      zones: result.zones,
      claim: result.claim,
      sources: result.sources,
      limitations: result.limitations,
      fixture: result.fixture,
      provenance: result.provenance,
    },
    null,
    2,
  );
}

/** Downloaded report: canonical content plus the integrity block it is checked against. */
export function passportPayload(result: LensResult): string {
  return JSON.stringify({ content: JSON.parse(passportContent(result)), integrity: { content_sha256: result.passport.content_sha256 } }, null, 2);
}

export async function sha256Hex(text: string): Promise<string | null> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) return null;
  const digest = await subtle.digest('SHA-256', new TextEncoder().encode(text));
  return `0x${[...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')}`;
}

/** Stamp the result with the hash of its own content, the way the service is expected to. */
export async function withContentHash(result: LensResult): Promise<LensResult> {
  const hash = await sha256Hex(passportContent(result));
  return hash === null ? result : { ...result, passport: { ...result.passport, content_sha256: hash } };
}

export type PassportFileVerdict =
  | { kind: 'invalid'; message: string }
  | { kind: 'match'; hash: string; calculationId: string }
  | { kind: 'mismatch'; hash: string; expected: string; calculationId: string };

/** Check a downloaded passport file the way an outside reader would: hash its content block. */
export async function verifyPassportFile(text: string): Promise<PassportFileVerdict> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    return { kind: 'invalid', message: `Файл не разбирается как JSON: ${error instanceof Error ? error.message : String(error)}` };
  }
  const record = parsed as { content?: unknown; integrity?: { content_sha256?: unknown } };
  if (!record.content || typeof record.integrity?.content_sha256 !== 'string') {
    return { kind: 'invalid', message: 'Это не паспорт Carbon Lens: нет блока content или integrity.content_sha256.' };
  }
  const hash = await sha256Hex(JSON.stringify(record.content, null, 2));
  if (hash === null) return { kind: 'invalid', message: 'Проверка недоступна: в этом браузере нет Web Crypto.' };
  const calculationId = String((record.content as { passport?: { calculation_id?: unknown } }).passport?.calculation_id ?? 'без идентификатора');
  const expected = record.integrity.content_sha256;
  return hash === expected ? { kind: 'match', hash, calculationId } : { kind: 'mismatch', hash, expected, calculationId };
}
