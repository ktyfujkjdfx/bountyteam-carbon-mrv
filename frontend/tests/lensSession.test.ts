import { describe, expect, it } from 'vitest';
import { createFixtureLensClient } from '../src/lens/adapter';
import { appendRun, loadRuns, makeRun, relateRun, saveRuns, LENS_SESSION_KEY } from '../src/lens/session';
import type { LensRequest, LensResult } from '../src/lens/types';

function memoryStorage(seed: Record<string, string> = {}) {
  const map = new Map(Object.entries(seed));
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => void map.set(key, value),
    removeItem: (key: string) => void map.delete(key),
    snapshot: () => Object.fromEntries(map),
  };
}

function request(overrides: Partial<LensRequest> = {}): LensRequest {
  return {
    aoi_id: 'RU_TVER_01',
    parent_aoi_id: null,
    geometry: { type: 'Polygon', coordinates: [[[32.91, 56.59], [32.974, 56.59], [32.974, 56.63], [32.91, 56.63], [32.91, 56.59]]] },
    year_start: 2019,
    year_end: 2020,
    claimed_units: null,
    ...overrides,
  };
}

async function resultFor(req: LensRequest): Promise<LensResult> {
  const client = createFixtureLensClient({ queuedMs: 0, runningMs: 0 });
  const job = await client.submitAnalysis(req, { scenario: 'DOC_EXAMPLE_Q395', idempotencyKey: `key-${Math.random()}` });
  const settled = await client.getJob(job.job_id);
  return client.getResult(settled.result_id ?? '');
}

describe('session history', () => {
  it('marks another period of the same contour as a new observation, not a cancellation', async () => {
    const first = makeRun(request(), await resultFor(request()), 'fixture', new Date('2026-09-19T10:00:00Z'));
    const later = makeRun(request({ year_end: 2024 }), await resultFor(request({ year_end: 2024 })), 'fixture', new Date('2026-09-19T10:05:00Z'));

    expect(relateRun([], first).kind).toBe('FIRST');
    const relation = relateRun([first], later);
    expect(relation.kind).toBe('NEW_OBSERVATION');
    expect(relation.note).toMatch(/не списание/i);
    expect(relation.note).not.toMatch(/аннулир/i);
  });

  it('distinguishes a repeat of the same request from another territory', async () => {
    const base = makeRun(request(), await resultFor(request()), 'fixture');
    const repeat = makeRun(request(), await resultFor(request()), 'fixture');
    expect(relateRun([base], repeat).kind).toBe('REPEAT');

    const other = request({ aoi_id: 'RU_VOLOGDA_02', geometry: { type: 'Polygon', coordinates: [[[40.67, 59.43], [40.73, 59.43], [40.73, 59.47], [40.67, 59.47], [40.67, 59.43]]] } });
    const otherRun = makeRun(other, await resultFor(other), 'fixture');
    expect(relateRun([base], otherRun).kind).toBe('OTHER_AREA');
  });

  it('survives a reload and ignores a payload of another schema version', async () => {
    const storage = memoryStorage();
    const run = makeRun(request(), await resultFor(request()), 'fixture');
    saveRuns(appendRun([], run), storage);
    const restored = loadRuns(storage);
    expect(restored).toHaveLength(1);
    expect(restored[0]?.result.units.q).toBe(395);
    expect(restored[0]?.mode).toBe('fixture');

    const stale = memoryStorage({ [LENS_SESSION_KEY]: JSON.stringify({ schema: 'lens-session-0', runs: [run] }) });
    expect(loadRuns(stale)).toEqual([]);
    expect(loadRuns(memoryStorage({ [LENS_SESSION_KEY]: 'not json' }))).toEqual([]);
  });

  it('keeps at most eight runs, newest first', async () => {
    let runs = [] as ReturnType<typeof makeRun>[];
    for (let i = 0; i < 10; i += 1) {
      const req = request({ year_end: 2020 + (i % 4) });
      runs = appendRun(runs, makeRun(req, await resultFor(req), 'fixture', new Date(1_800_000_000_000 + i)));
    }
    expect(runs).toHaveLength(8);
    expect(new Date(runs[0]?.saved_at ?? 0).getTime()).toBeGreaterThan(new Date(runs[7]?.saved_at ?? 0).getTime());
  });
});
