// Session-scoped history of Carbon Lens runs: survives a page reload, never leaves the browser.
// Stored results are the ones the service returned; nothing is recomputed on the way in or out.

import type { LensMode } from './config';
import type { LensRequest, LensResult } from './types';

export const LENS_SESSION_KEY = 'carbon-lens.runs';
export const LENS_SESSION_SCHEMA = 'lens-session-1';
const MAX_RUNS = 8;

export interface LensRun {
  run_id: string;
  saved_at: string;
  mode: LensMode;
  request: LensRequest;
  result: LensResult;
}

export interface RunRelation {
  kind: 'FIRST' | 'REPEAT' | 'NEW_OBSERVATION' | 'OTHER_AREA';
  label: string;
  note: string;
}

interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

function safeStorage(): StorageLike | null {
  try {
    return globalThis.sessionStorage ?? null;
  } catch {
    return null;
  }
}

function scopeOf(request: LensRequest): string {
  return JSON.stringify({ aoi: request.aoi_id, parent: request.parent_aoi_id, geometry: request.geometry });
}

/**
 * A run of the same contour over another period is a new observation, not a verdict on the earlier one:
 * comparing different periods never means "N earlier units are cancelled".
 */
export function relateRun(previous: readonly LensRun[], next: LensRun): RunRelation {
  if (previous.length === 0) {
    return { kind: 'FIRST', label: 'ПЕРВЫЙ РАСЧЁТ', note: 'Первый расчёт в этой сессии.' };
  }
  const sameScope = previous.filter((run) => scopeOf(run.request) === scopeOf(next.request));
  if (sameScope.length === 0) {
    return { kind: 'OTHER_AREA', label: 'ДРУГАЯ ТЕРРИТОРИЯ', note: 'Запрос относится к другому контуру; результаты не сравниваются напрямую.' };
  }
  const samePeriod = sameScope.some((run) => run.request.year_start === next.request.year_start && run.request.year_end === next.request.year_end);
  if (samePeriod) {
    return { kind: 'REPEAT', label: 'ПОВТОР ЗАПРОСА', note: 'Тот же контур и период: результат получен повторно.' };
  }
  return {
    kind: 'NEW_OBSERVATION',
    label: 'НОВОЕ НАБЛЮДЕНИЕ',
    note: 'Тот же контур, другой период. Это новое наблюдение, а не списание ранее рассчитанных единиц.',
  };
}

export function loadRuns(storage: StorageLike | null = safeStorage()): LensRun[] {
  try {
    const raw = storage?.getItem(LENS_SESSION_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as { schema?: string; runs?: LensRun[] };
    if (parsed.schema !== LENS_SESSION_SCHEMA || !Array.isArray(parsed.runs)) return [];
    return parsed.runs;
  } catch {
    return [];
  }
}

export function saveRuns(runs: readonly LensRun[], storage: StorageLike | null = safeStorage()): void {
  try {
    storage?.setItem(LENS_SESSION_KEY, JSON.stringify({ schema: LENS_SESSION_SCHEMA, runs: runs.slice(0, MAX_RUNS) }));
  } catch {
    /* quota or private mode: history stays in memory for this page only */
  }
}

export function clearRuns(storage: StorageLike | null = safeStorage()): void {
  try {
    storage?.removeItem(LENS_SESSION_KEY);
  } catch {
    /* nothing to clean up */
  }
}

export function appendRun(runs: readonly LensRun[], run: LensRun): LensRun[] {
  return [run, ...runs].slice(0, MAX_RUNS);
}

export function makeRun(request: LensRequest, result: LensResult, mode: LensMode, now: Date = new Date()): LensRun {
  return {
    run_id: `${result.passport.calculation_id}-${now.getTime()}`,
    saved_at: now.toISOString(),
    mode,
    request,
    result,
  };
}
