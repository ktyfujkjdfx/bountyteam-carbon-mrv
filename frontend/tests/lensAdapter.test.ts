// @vitest-environment node
import { describe, expect, it } from 'vitest';
import {
  approximateAreaHa,
  areaGeometryFromData,
  createFixtureLensClient,
  LensError,
  parsedAreas,
  sampleRequestFeature,
  validateRequest,
} from '../src/lens/adapter';
import { FIXTURE_SCENARIOS, FIXTURE_SCENARIO_ORDER, SCENARIO_DEFAULTS, type FixtureScenarioId } from '../src/lens/fixtures';
import type { LensRequest } from '../src/lens/types';

const AOI = 'RU_TVER_01';

function request(overrides: Partial<LensRequest> = {}): LensRequest {
  const geometry = areaGeometryFromData(AOI);
  if (!geometry) throw new Error('AOI geometry missing');
  return { aoi_id: AOI, parent_aoi_id: null, geometry, year_start: 2019, year_end: 2020, claimed_units: null, ...overrides };
}

async function runScenario(scenario: FixtureScenarioId, req: LensRequest = request()) {
  let t = 0;
  const client = createFixtureLensClient({ now: () => t, queuedMs: 10, runningMs: 10 });
  const job = await client.submitAnalysis(req, { scenario, idempotencyKey: `key-${scenario}` });
  expect(job.state).toBe('QUEUED');
  t += 100;
  const finished = await client.getJob(job.job_id);
  expect(finished.state).toBe('SUCCEEDED');
  return client.getResult(finished.result_id as string);
}

describe('official data behind the request panel', () => {
  it('reads the four AOI from data/areas.csv', () => {
    const areas = parsedAreas();
    expect(areas.map((a) => a.aoi_id)).toEqual(['RU_TVER_01', 'RU_VOLOGDA_02', 'RU_MORDOVIA_03', 'RU_MORDOVIA_04']);
    expect(areas[0]?.area_ha).toBeCloseTo(1750.4731, 4);
    expect(areas[0]?.baseline_id).toBe('HIST-AGB-2015-2019-v1');
  });

  it('measures each AOI close to the official area_ha', () => {
    for (const area of parsedAreas()) {
      const geometry = areaGeometryFromData(area.aoi_id);
      expect(geometry, area.aoi_id).not.toBeNull();
      const measured = approximateAreaHa(geometry as never);
      expect(Math.abs(measured - area.area_ha) / area.area_ha, area.aoi_id).toBeLessThan(0.01);
    }
  });

  it('loads the official sub-request CHECK_TRANSFER_01 (~808.85 ha)', () => {
    const sample = sampleRequestFeature('CHECK_TRANSFER_01');
    expect(sample?.properties.parent_aoi_id).toBe('RU_VOLOGDA_02');
    // The stand-in area is spherical; the authoritative value comes from the service (official 808.8538 ha).
    const measured = approximateAreaHa(sample?.geometry as never);
    expect(Math.abs(measured - 808.8538) / 808.8538).toBeLessThan(0.01);
  });
});

describe('request validation', () => {
  it.each([
    ['конец не больше начала', { year_start: 2021, year_end: 2021 }, 'INVALID_PERIOD'],
    ['год вне диапазона', { year_start: 2018, year_end: 2020 }, 'INVALID_PERIOD'],
    ['год вне диапазона сверху', { year_start: 2019, year_end: 2025 }, 'INVALID_PERIOD'],
  ])('%s', (_name, patch, code) => {
    try {
      validateRequest(request(patch), 100);
      throw new Error('expected rejection');
    } catch (error) {
      expect(error).toBeInstanceOf(LensError);
      expect((error as LensError).code).toBe(code);
    }
  });

  it('rejects an area above the 2000 ha limit and a non-positive area', () => {
    expect(() => validateRequest(request(), 2500)).toThrow(/2000/);
    expect(() => validateRequest(request(), 0)).toThrow(LensError);
  });

  it('rejects a negative claim', () => {
    expect(() => validateRequest(request({ claimed_units: -5 }), 100)).toThrow(LensError);
  });
});

describe('fixture lens client', () => {
  it('moves the job QUEUED → RUNNING → SUCCEEDED and returns a labelled result', async () => {
    let t = 0;
    const client = createFixtureLensClient({ now: () => t, queuedMs: 100, runningMs: 100 });
    const job = await client.submitAnalysis(request(), { scenario: 'DOC_EXAMPLE_Q395', idempotencyKey: 'flow-key-1' });
    expect((await client.getJob(job.job_id)).state).toBe('QUEUED');
    t += 120;
    expect((await client.getJob(job.job_id)).state).toBe('RUNNING');
    t += 120;
    const done = await client.getJob(job.job_id);
    expect(done.state).toBe('SUCCEEDED');
    const result = await client.getResult(done.result_id as string);
    expect(result.fixture?.kind).toBe('DOC_EXAMPLE');
    expect(result.units.q).toBe(395);
    expect(result.request.year_start).toBe(2019);
    expect(result.area_ha).toBeGreaterThan(0);
  });

  it('reuses the same job for a repeated idempotency key', async () => {
    const client = createFixtureLensClient({ now: () => 0 });
    const first = await client.submitAnalysis(request(), { scenario: 'DOC_EXAMPLE_Q395', idempotencyKey: 'same-key' });
    const second = await client.submitAnalysis(request(), { scenario: 'DOC_EXAMPLE_Q395', idempotencyKey: 'same-key' });
    expect(second.job_id).toBe(first.job_id);
  });

  it('reports unknown jobs and results instead of inventing data', async () => {
    const client = createFixtureLensClient();
    await expect(client.getJob('missing')).rejects.toBeInstanceOf(LensError);
    await expect(client.getResult('missing')).rejects.toBeInstanceOf(LensError);
  });
});

describe('claim comparison from the adapter', () => {
  it('is NOT_PROVIDED without user input', async () => {
    const result = await runScenario('DOC_EXAMPLE_Q395');
    expect(result.claim.status).toBe('NOT_PROVIDED');
    expect(result.claim.gap_units).toBeNull();
  });

  it('is NOT_COMPARABLE when the claim period differs, and explains why', async () => {
    const result = await runScenario('DOC_EXAMPLE_Q395', request({ claimed_units: 500, year_start: 2019, year_end: 2024 }));
    expect(result.claim.status).toBe('NOT_COMPARABLE');
    expect(result.claim.comparable).toBe(false);
    expect(result.claim.reasons.join(' ')).toMatch(/период/i);
    expect(result.units.q).toBe(395);
  });

  it('splits supported, partially supported and not supported', async () => {
    const supported = await runScenario('DOC_EXAMPLE_Q395', request({ claimed_units: 100 }));
    expect(supported.claim.status).toBe('SUPPORTED_BY_CASE');
    expect(supported.claim.gap_units).toBe(0);

    const partial = await runScenario('DOC_EXAMPLE_Q395', request({ claimed_units: 1000 }));
    expect(partial.claim.status).toBe('PARTIALLY_SUPPORTED_BY_CASE');
    expect(partial.claim.gap_units).toBe(605);

    const zero = await runScenario('ZERO_NON_POSITIVE', request({ claimed_units: 250 }));
    expect(zero.claim.status).toBe('NOT_SUPPORTED_BY_CASE');
    expect(zero.claim.gap_units).toBe(250);
  });

  it('is UNASSESSABLE when the calculation itself is unavailable', async () => {
    const result = await runScenario('UNAVAILABLE_COVERAGE', request({ claimed_units: 300 }));
    expect(result.units.q).toBeNull();
    expect(result.claim.status).toBe('UNASSESSABLE');
    expect(result.claim.gap_units).toBeNull();
  });

  it('never changes the calculated Q because of a claim', async () => {
    const withoutClaim = await runScenario('DOC_EXAMPLE_Q395');
    const withClaim = await runScenario('DOC_EXAMPLE_Q395', request({ claimed_units: 9999 }));
    expect(withClaim.units.q).toBe(withoutClaim.units.q);
  });
});

describe('fixture invariants', () => {
  it('every scenario is labelled and has consistent q semantics', () => {
    for (const id of FIXTURE_SCENARIO_ORDER) {
      const scenario = FIXTURE_SCENARIOS[id];
      expect(scenario.fixture, id).not.toBeNull();
      expect(['DOC_EXAMPLE', 'UNIT_TEST_VECTOR']).toContain(scenario.fixture?.kind);
      if (scenario.units.q === null) {
        expect(scenario.units.status, id).toBe('UNAVAILABLE');
        expect(scenario.calculation_status, id).toBe('UNAVAILABLE');
        expect(scenario.units.reason, id).not.toBeNull();
      } else {
        expect(scenario.units.status, id).toBe('AVAILABLE');
        if (scenario.units.q === 0) expect(scenario.units.reason, id).not.toBeNull();
      }
      expect(SCENARIO_DEFAULTS[id].years[1]).toBeGreaterThan(SCENARIO_DEFAULTS[id].years[0]);
    }
  });

  it('keeps the doc example numbers exactly as printed in doc/Постановка_задачи', () => {
    const doc = FIXTURE_SCENARIOS.DOC_EXAMPLE_Q395;
    expect(doc.stock.e_tco2e).toBe(-689.333);
    expect(doc.baseline.e_base_tco2e).toBe(-172.333);
    expect(doc.units.r_tco2e).toBe(517);
    expect(doc.uncertainty.h_tco2e).toBe(103.4);
    expect(doc.units.h_over_r).toBe(0.2);
    expect(doc.units.unc_fraction).toBe(0.1);
    expect(doc.units.r_adj_tco2e).toBe(465.3);
    expect(doc.units.buffer_tco2e).toBe(69.795);
    expect(doc.units.q).toBe(395);
  });

  it('keeps coverage axes separate in every scenario', () => {
    for (const id of FIXTURE_SCENARIO_ORDER) {
      const ids = FIXTURE_SCENARIOS[id].coverage.map((c) => c.id);
      expect(new Set(ids).size, id).toBe(ids.length);
      expect(ids, id).toContain('BIOMASS_CCI');
      expect(ids, id).toContain('OPTICAL_PAIRED_VALID');
    }
  });

  it('weak optics keeps full CCI coverage', () => {
    const weak = FIXTURE_SCENARIOS.WEAK_OPTICS_VALID_CCI.coverage;
    expect(weak.find((c) => c.id === 'BIOMASS_CCI')?.covered_fraction).toBe(1);
    expect(weak.find((c) => c.id === 'OPTICAL_PAIRED_VALID')?.covered_fraction).toBeLessThan(0.5);
  });
});
