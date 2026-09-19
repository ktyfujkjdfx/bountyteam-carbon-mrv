// Passport content, report rendering and the integrity check an outside reader can repeat.
//
// The canonical content mirrors what the service hashes: the scientific content without the passport
// itself, without ids and without run time. A value cannot hash itself, and a file that changes only
// because it was fetched at another moment is not a changed result.

import type { AnalysisResult } from './types';

export function passportContent(result: Omit<AnalysisResult, 'passport'> | AnalysisResult): string {
  const record = result as AnalysisResult;
  const identity = { ...record.identity };
  delete (identity as { analysis_id?: string }).analysis_id;
  const request = { ...record.request };
  delete (request as { aoi_id?: string | null }).aoi_id;
  return JSON.stringify(
    {
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
      evidence: record.evidence,
      sources: record.sources,
      artifacts: record.artifacts.map(({ artifact_id, role, media_type, sha256, size_bytes, bbox_wgs84, crs, resolution, resolution_units, unit, provenance }) => ({
        artifact_id,
        role,
        media_type,
        sha256,
        size_bytes,
        bbox_wgs84,
        crs,
        resolution,
        resolution_units,
        unit,
        provenance,
      })),
      limitations: record.limitations,
      notes: record.notes,
      fixture: record.fixture,
    },
    null,
    2,
  );
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
  const hash = await sha256HexOfText(JSON.stringify(record.content, null, 2));
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
<h2>Ограничения</h2><ul>${result.limitations.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>
<p>Хеш подтверждает неизменность содержания относительно зафиксированного значения. Он не удостоверяет истинность расчёта и не предотвращает повторную продажу.</p>
</body></html>`;
}
