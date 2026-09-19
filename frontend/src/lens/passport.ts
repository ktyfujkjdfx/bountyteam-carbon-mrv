// Passport content, report rendering and the integrity check an outside reader can repeat.
//
// The content view mirrors what the service hashes: the scientific content without the passport
// itself, without ids and without run time. A value cannot hash itself, and a file that changes only
// because it was fetched at another moment is not a changed result.
//
// Two forms of the same object, for two different jobs:
//
// - `passportContent` is the readable one, indented, and it is what goes into the downloaded file.
// - `canonicalJson` is RFC 8785 (JCS) — sorted keys, no whitespace — and it is the only form whose
//   hash can be compared with the service's. The service computes `sha256(rfc8785.dumps(view))`, so
//   hashing a pretty-printed rendering instead produces a number that matches nothing and quietly
//   reports every genuine passport as altered.

import type { AnalysisResult } from './types';

/** Must equal the service's REPORT_SCHEMA_VERSION; it is part of the report hash preimage. */
export const REPORT_SCHEMA_VERSION = 'carbon-lens-report/2.0.0';

/**
 * RFC 8785 canonical JSON.
 *
 * JCS was specified against ECMAScript, so `JSON.stringify` already produces the required form for
 * every primitive; all this adds is sorted keys and no whitespace. Keys sort by UTF-16 code unit,
 * which is what `<` does on JavaScript strings.
 */
export function canonicalJson(value: unknown): string {
  if (value === null) return 'null';
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error(`не сериализуемое число в паспорте: ${String(value)}`);
    return JSON.stringify(value);
  }
  if (typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => item !== undefined)
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0));
    return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`).join(',')}}`;
  }
  throw new Error(`не сериализуемое значение в паспорте: ${typeof value}`);
}

/** The scientific content, exactly the fields the service hashes and only those. */
export function contentView(result: Omit<AnalysisResult, 'passport'> | AnalysisResult): Record<string, unknown> {
  const record = result as AnalysisResult & Record<string, unknown>;
  const identity = { ...record.identity };
  delete (identity as { analysis_id?: string }).analysis_id;
  const request = { ...record.request };
  delete (request as { aoi_id?: string | null }).aoi_id;
  return {
    identity,
    request,
    calculation_status: record.calculation_status,
    evidence_status: record.evidence_status,
    areas: record.areas,
    coverage: record.coverage,
    timeline: record.timeline,
    change: record.change,
    uncertainty: record.uncertainty,
    baseline: record.baseline,
    units: record.units,
    scenario_values: record.scenario_values,
    claim: record.claim,
    zones: record.zones,
    // Risks and the projection are part of what the service hashes. Leaving them out was the
    // difference between a check that verifies the passport and one that always refuses it.
    risks: record.risks,
    projection: record.projection,
    evidence: record.evidence,
    sources: record.sources,
    // Written out rather than picked by key list: the service hashes exactly these eleven fields,
    // and naming them here is what makes a field added to Artifact fail to compile instead of
    // silently changing the hash.
    artifacts: record.artifacts.map(({ artifact_id, role, media_type, sha256, size_bytes, bbox_wgs84, crs, resolution, resolution_units, unit, provenance }) => ({
      artifact_id, role, media_type, sha256, size_bytes, bbox_wgs84, crs, resolution, resolution_units, unit, provenance,
    })),
    limitations: record.limitations,
    notes: record.notes,
    fixture: record.fixture,
  };
}

/** The readable rendering that goes into the downloaded file. Never the hash preimage. */
export function passportContent(result: Omit<AnalysisResult, 'passport'> | AnalysisResult): string {
  return JSON.stringify(contentView(result), null, 2);
}

/** The scientific content hash, computed the way the service computes it. */
export function contentHashOf(result: Omit<AnalysisResult, 'passport'> | AnalysisResult): Promise<string | null> {
  return sha256HexOfText(canonicalJson(contentView(result)));
}

/** The report hash: the same content view inside the wrapper the service hashes. */
export function reportHashOf(result: Omit<AnalysisResult, 'passport'> | AnalysisResult): Promise<string | null> {
  return sha256HexOfText(canonicalJson({ report: REPORT_SCHEMA_VERSION, content: contentView(result) }));
}

/** Downloaded passport: canonical content plus the integrity block it is checked against. */
export function passportPayload(result: AnalysisResult): string {
  return JSON.stringify(
    {
      content: JSON.parse(passportContent(result)),
      integrity: { content_sha256: result.passport.content_hash, report_sha256: result.passport.report_hash },
    },
    null,
    2,
  );
}

export async function sha256HexOfText(text: string): Promise<string | null> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) return null;
  const digest = await subtle.digest('SHA-256', new TextEncoder().encode(text));
  return `0x${[...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')}`;
}

export type PassportFileVerdict =
  | { kind: 'invalid'; message: string }
  | { kind: 'match'; hash: string; analysis: string }
  | { kind: 'mismatch'; hash: string; expected: string; analysis: string };

/** Check a downloaded passport the way an outside reader would: hash its content block. */
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
  // The file is readable JSON; the hash is taken over its canonical form, so reformatting the file
  // is not reported as tampering while any change to a value still is.
  const hash = await sha256HexOfText(canonicalJson(record.content));
  if (hash === null) return { kind: 'invalid', message: 'Проверка недоступна: в этом браузере нет Web Crypto.' };
  const content = record.content as { identity?: { input_hash?: unknown } };
  const analysis = String(content.identity?.input_hash ?? 'без идентификатора');
  const expected = record.integrity.content_sha256;
  return hash === expected ? { kind: 'match', hash, analysis } : { kind: 'mismatch', hash, expected, analysis };
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char] ?? char);
}

function fmt(value: number | null | undefined, digits = 3): string {
  return value === null || value === undefined ? '—' : value.toLocaleString('ru-RU', { maximumFractionDigits: digits });
}

/** Readable report with exactly the values on screen; nothing is recomputed while rendering it. */
export function renderReportHtml(result: AnalysisResult): string {
  const rows: Array<[string, string]> = [
    ['Контур', result.request.aoi_id ?? 'контур пользователя'],
    ['Период', `${result.request.year_start}–${result.request.year_end}`],
    ['Площадь запроса, га', fmt(result.areas.requested_ha, 4)],
    ['Рассчитанная площадь, га', fmt(result.areas.calculated_ha, 4)],
    ['Изменение запаса, т C', fmt(result.change.delta_carbon_tc)],
    ['Eproj, т CO₂-экв.', fmt(result.change.eproj_tco2e)],
    ['Ebase, т CO₂-экв.', fmt(result.units.ebase_tco2e)],
    ['R, т CO₂-экв.', fmt(result.units.r_tco2e)],
    ['H, т CO₂-экв.', fmt(result.units.h_tco2e)],
    ['H/R', fmt(result.units.ratio)],
    ['Вычет за неопределённость, т CO₂-экв.', fmt(result.units.uncertainty_deduction_tco2e)],
    ['Radj, т CO₂-экв.', fmt(result.units.radj_tco2e)],
    ['Резерв, т CO₂-экв.', fmt(result.units.buffer_tco2e)],
    ['Q, потенциальные единицы', result.units.q === null ? 'Не рассчитано' : String(result.units.q)],
    ['Причина', String(result.units.zero_reason ?? result.units.unavailable_reason ?? '—')],
    ['Статус расчёта', String(result.calculation_status)],
    ['Статус объяснения', String(result.evidence_status)],
    ['Статус заявления', String(result.claim.status)],
    ['Версия схемы', result.identity.schema_version],
    ['Версия методики', result.identity.method_version],
    ['Версия данных', result.identity.dataset_version],
    ['Хеш содержания', result.passport.content_hash],
  ];
  const origin = result.fixture
    ? `${result.fixture.kind === 'DOC_EXAMPLE' ? 'Условный пример постановки' : 'Логический вектор'}: ${result.fixture.note}`
    : `Значения рассчитаны сервисом (${result.run.raster_adapter}, ${result.run.carbon_adapter}).`;
  return `<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Паспорт расчёта Carbon Lens</title>
<style>body{font-family:system-ui,sans-serif;max-width:52rem;margin:2rem auto;padding:0 1rem;line-height:1.5}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:.4rem .6rem;text-align:left;vertical-align:top}
.note{background:#fff6e5;border:1px solid #e3c98a;padding:.75rem;border-radius:.4rem}code{word-break:break-all}</style></head><body>
<h1>Паспорт расчёта Carbon Lens</h1>
<p class="note">${escapeHtml(origin)}</p>
<table><tbody>${rows.map(([key, value]) => `<tr><th>${escapeHtml(key)}</th><td><code>${escapeHtml(value)}</code></td></tr>`).join('')}</tbody></table>
<h2>Источники</h2><ul>${result.sources.map((s) => `<li>${escapeHtml(s.product)} ${escapeHtml(s.version)} — ${escapeHtml(s.attribution)}</li>`).join('')}</ul>
<h2>Ограничения</h2><ul>${result.limitations.map((item) => `<li>${escapeHtml(item.message)} <code>${escapeHtml(item.code)}</code></li>`).join('')}</ul>
<p>Хеш подтверждает неизменность содержания относительно зафиксированного значения. Он не удостоверяет истинность расчёта и не предотвращает повторную продажу.</p>
</body></html>`;
}
