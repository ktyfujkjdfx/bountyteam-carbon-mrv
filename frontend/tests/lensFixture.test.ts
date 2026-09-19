import { describe, expect, it } from 'vitest';
import { createFixtureLensClient } from '../src/lens/fixtureClient';
import { compareClaim } from '../src/lens/fixtures';
import { passportPayload, verifyPassportFile } from '../src/lens/passport';
import { parsedAreas, sampleRequests } from '../src/lens/data';
import type { AnalysisResult } from '../src/lens/types';

const fast = () => createFixtureLensClient({ queuedMs: 0, runningMs: 0 });

async function settle(scenario: string, body: Record<string, unknown> = {}): Promise<AnalysisResult> {
  const client = fast();
  const accepted = await client.createAnalysis(
    { aoi_id: 'RU_TVER_01', year_start: 2019, year_end: 2024, ...body },
    { idempotencyKey: `key-${Math.random()}`, scenario },
  );
  const analysis = await client.getAnalysis(accepted.analysis_id);
  expect(analysis.job_state).toBe('SUCCEEDED');
  if (!analysis.result) throw new Error('no result');
  return analysis.result;
}

describe('offline set answers in the shape of the service', () => {
  it('serves the catalog from the official archive', async () => {
    const catalog = await fast().getCatalog();
    expect(catalog.areas.map((area) => area.aoi_id)).toEqual(parsedAreas().map((area) => area.aoi_id));
    expect(catalog.sample_requests[0]?.request_id).toBe(sampleRequests()[0]?.request_id);
    expect(catalog.prices.map((price) => price.rub_per_unit)).toEqual([500, 1500, 4000]);
    expect(catalog.max_area_ha).toBe(2000);
  });

  it('returns the official area for a supplied contour and an estimate for a drawn one', async () => {
    const client = fast();
    const area = parsedAreas()[0];
    if (!area) throw new Error('no areas');
    const supplied = await client.measureArea(area.geometry);
    expect(supplied.source).toBe('SERVICE');
    expect(supplied.area_ha).toBeCloseTo(area.area_ha, 6);

    const drawn = await client.measureArea({ type: 'Polygon', coordinates: [[[32.92, 56.6], [32.93, 56.6], [32.93, 56.61], [32.92, 56.61], [32.92, 56.6]]] });
    expect(drawn.source).toBe('CLIENT_ESTIMATE');
  });

  it('reuses one analysis for a repeated idempotency key', async () => {
    const client = fast();
    const body = { aoi_id: 'RU_TVER_01', year_start: 2019, year_end: 2024 };
    const first = await client.createAnalysis(body, { idempotencyKey: 'same-key' });
    const second = await client.createAnalysis(body, { idempotencyKey: 'same-key' });
    expect(second.analysis_id).toBe(first.analysis_id);
  });

  it('refuses a period and an area the service would refuse, with the reason', async () => {
    const client = fast();
    await expect(client.createAnalysis({ aoi_id: 'RU_TVER_01', year_start: 2024, year_end: 2019 }, { idempotencyKey: 'k1' })).rejects.toMatchObject({ code: 'INVALID_PERIOD' });
    await expect(
      client.createAnalysis({ geometry: { type: 'Polygon', coordinates: [[[32, 56], [33, 56], [33, 57], [32, 57], [32, 56]]] }, year_start: 2019, year_end: 2024 }, { idempotencyKey: 'k2' }),
    ).rejects.toMatchObject({ code: 'AREA_TOO_LARGE' });
  });

  it('separates q = 0 with its reason from q = null with its own', async () => {
    const zero = await settle('ZERO_NON_POSITIVE');
    expect(zero.units.q).toBe(0);
    expect(zero.units.zero_reason).toBe('NON_POSITIVE_RELATIVE_RESULT');
    expect(zero.units.unavailable_reason).toBeNull();
    expect(zero.calculation_status).toBe('AVAILABLE');

    const none = await settle('UNAVAILABLE_COVERAGE');
    expect(none.units.q).toBeNull();
    expect(none.units.unavailable_reason).toBe('INCOMPLETE_COVERAGE');
    expect(none.units.zero_reason).toBeNull();
    expect(none.calculation_status).toBe('UNAVAILABLE');
  });

  it('reproduces the conditional example of the statement exactly', async () => {
    const doc = await settle('DOC_EXAMPLE_Q395', { year_start: 2019, year_end: 2020 });
    expect(doc.fixture?.kind).toBe('DOC_EXAMPLE');
    expect(doc.units.r_tco2e).toBe(517);
    expect(doc.units.h_tco2e).toBe(103.4);
    expect(doc.units.radj_tco2e).toBe(465.3);
    expect(doc.units.buffer_tco2e).toBe(69.795);
    expect(doc.units.q).toBe(395);
    expect(doc.scenario_values.base.value_rub).toBe(395 * 1500);
  });

  it('ships four coverages and a signed area difference', async () => {
    const result = await settle('UNAVAILABLE_COVERAGE');
    expect(Object.keys(result.coverage).sort()).toEqual(['baseline_fraction', 'biomass_fraction', 'coverage_fraction_raw', 'optical_paired_valid_fraction', 'uncertainty_fraction']);
    expect(result.coverage.coverage_fraction_raw.biomass).toBe(result.coverage.biomass_fraction);
    expect(result.areas.missing_ha).toBeGreaterThan(0);
    expect(result.areas.area_difference_ha).toBeLessThan(0);
  });

  it('serves a CCI cell artifact whose hash matches its bytes', async () => {
    const client = fast();
    const accepted = await client.createAnalysis({ aoi_id: 'RU_TVER_01', year_start: 2019, year_end: 2024 }, { idempotencyKey: 'cells-1', scenario: 'FIRE_SUPPORTED_LOSS' });
    const analysis = await client.getAnalysis(accepted.analysis_id);
    const artifact = analysis.result?.artifacts.find((item) => item.role === 'cci_cell_layer');
    if (!artifact) throw new Error('the offline set must ship a CCI cell artifact');
    const payload = await client.getArtifact(artifact);
    expect(payload.integrity).toBe('VERIFIED');
    const collection = payload.data as { features: Array<{ properties: Record<string, unknown> }> };
    expect(collection.features.length).toBeGreaterThan(0);
    expect(collection.features[0]?.properties.cell_id).toBeTruthy();
  });

  it('links every published zone to a verified change-zones artifact', async () => {
    const client = fast();
    const accepted = await client.createAnalysis(
      { aoi_id: 'RU_MORDOVIA_03', year_start: 2020, year_end: 2022 },
      { idempotencyKey: 'zones-1', scenario: 'FIRE_SUPPORTED_LOSS' },
    );
    const analysis = await client.getAnalysis(accepted.analysis_id);
    const result = analysis.result;
    if (!result) throw new Error('the offline analysis must finish');
    const artifact = result.artifacts.find((item) => item.role === 'change_zones');
    if (!artifact) throw new Error('the offline set must ship a change-zones artifact');
    expect(new Set(result.zones.map((zone) => zone.artifact_ref))).toEqual(new Set([artifact.artifact_id]));
    const payload = await client.getArtifact(artifact);
    expect(payload.integrity).toBe('VERIFIED');
    const collection = payload.data as { features: Array<{ properties: Record<string, unknown> }> };
    expect(collection.features.map((feature) => feature.properties.zone_id)).toEqual(result.zones.map((zone) => zone.zone_id));
  });

  it('stamps a passport that a reader can verify and a tampered copy fails', async () => {
    const result = await settle('DOC_EXAMPLE_Q395', { year_start: 2019, year_end: 2020 });
    expect(result.passport.content_hash).toMatch(/^0x[0-9a-f]{64}$/);
    const payload = passportPayload(result);
    expect(await verifyPassportFile(payload)).toMatchObject({ kind: 'match' });
    expect(await verifyPassportFile(payload.replace('"q": 395', '"q": 9999'))).toMatchObject({ kind: 'mismatch' });
    expect(await verifyPassportFile('{"nope":1}')).toMatchObject({ kind: 'invalid' });
  });
});

describe('claim comparison follows the method freeze', () => {
  const scope = { geometry_hash: '0xabc', year_start: 2019, year_end: 2024, pool: 'AGB_LIVE_WOODY', unit: 'POTENTIAL_UNIT_OF_THE_CASE' };

  it('never calls a zero claim supported', () => {
    const claim = compareClaim(0, 'USER_INPUT', 400, scope, [2019, 2024]);
    expect(claim.status).toBe('NOT_APPLICABLE');
    expect(claim.reason).toBe('NO_POSITIVE_CLAIM');
    expect(claim.mismatch_reasons).toEqual([]);
    expect(claim.supported_share).toBeNull();
    expect(claim.unsupported_gap).toBe(0);
  });

  it('splits supported, partially supported and unsupported', () => {
    expect(compareClaim(100, 'USER_INPUT', 400, scope, [2019, 2024]).status).toBe('SUPPORTED_BY_CASE');
    const partial = compareClaim(1000, 'USER_INPUT', 400, scope, [2019, 2024]);
    expect(partial.status).toBe('PARTIALLY_SUPPORTED_BY_CASE');
    expect(partial.unsupported_gap).toBe(600);
    expect(partial.supported_share).toBeCloseTo(0.4, 6);
    expect(compareClaim(1000, 'USER_INPUT', 0, scope, [2019, 2024]).status).toBe('NOT_SUPPORTED_BY_CASE');
  });

  it('refuses to compare another period and cannot assess a missing q', () => {
    expect(compareClaim(100, 'USER_INPUT', 400, { ...scope, year_end: 2022 }, [2019, 2024]).status).toBe('NOT_COMPARABLE');
    expect(compareClaim(100, 'USER_INPUT', null, scope, [2019, 2024]).status).toBe('UNASSESSABLE');
    expect(compareClaim(null, null, 400, scope, [2019, 2024]).status).toBe('NOT_PROVIDED');
    expect(compareClaim(-5, 'USER_INPUT', 400, scope, [2019, 2024]).mismatch_reasons).toEqual(['INVALID_CLAIM_VALUE']);
  });

  it('never changes q because of what was claimed', async () => {
    const without = await settle('DOC_EXAMPLE_Q395', { year_start: 2019, year_end: 2020 });
    const with_ = await settle('DOC_EXAMPLE_Q395', { year_start: 2019, year_end: 2020, claimed_units: 99999 });
    expect(with_.units.q).toBe(without.units.q);
  });
});
