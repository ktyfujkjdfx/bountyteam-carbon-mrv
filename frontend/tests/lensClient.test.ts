import { describe, expect, it, vi } from 'vitest';
import { LensError, normalizeResult, normalizeWarnings } from '../src/lens/client';
import { createHttpLensClient } from '../src/lens/httpClient';
import { createFixtureLensClient } from '../src/lens/fixtureClient';
import { createLensClient, resolveLensConfig, switchModeHref } from '../src/lens/config';
import { validateGeometry, approximateAreaHa } from '../src/lens/geometry';
import type { Artifact, Geometry } from '../src/lens/types';

const BASE = { baseUrl: 'https://service.test/api/v2', getToken: () => 'runtime-token' };

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

const square: Geometry = {
  type: 'Polygon',
  coordinates: [[[32.91, 56.59], [32.94, 56.59], [32.94, 56.61], [32.91, 56.61], [32.91, 56.59]]],
};

describe('live client', () => {
  it('sends the bearer token, the idempotency key and no cookies', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ analysis_id: 'a1', job_state: 'QUEUED', status_url: '/api/v2/analyses/a1', created_at: '2026-09-19T00:00:00Z' }));
    const client = createHttpLensClient({ ...BASE, fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.createAnalysis({ aoi_id: 'RU_TVER_01', year_start: 2019, year_end: 2024 }, { idempotencyKey: 'key-1' });
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(url).toBe('https://service.test/api/v2/analyses');
    expect(headers.Authorization).toBe('Bearer runtime-token');
    expect(headers['Idempotency-Key']).toBe('key-1');
    expect(init.credentials).toBe('omit');
  });

  it.each([
    [401, 'UNAUTHORIZED'],
    [403, 'FORBIDDEN'],
    [404, 'NOT_FOUND'],
    [409, 'IDEMPOTENCY_CONFLICT'],
    [422, 'AREA_TOO_LARGE'],
    [503, 'SOURCE_UNAVAILABLE'],
  ])('turns HTTP %i into a typed error with its code', async (status, code) => {
    const fetchImpl = vi.fn(async () => jsonResponse({ error: { code, message: 'сообщение сервиса', details: { field: 'geometry' } }, request_id: 'req-1' }, status));
    const client = createHttpLensClient({ ...BASE, fetchImpl: fetchImpl as unknown as typeof fetch });
    await expect(client.getCatalog()).rejects.toMatchObject({ code, status, details: { field: 'geometry' } });
  });

  it('uses the authoritative measurement response and sends the exact geometry', async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => jsonResponse({
      valid: true,
      area_ha: 77.25,
      max_area_ha: 2000,
      within_limit: true,
      geometry_hash: `0x${'a'.repeat(64)}`,
      geometry: square,
      errors: [],
    }));
    const client = createHttpLensClient({ ...BASE, fetchImpl });
    const measurement = await client.measureArea(square);
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('https://service.test/api/v2/areas/measure');
    expect(JSON.parse(String(init.body))).toEqual({ geometry: square });
    expect(measurement).toMatchObject({ area_ha: 77.25, source: 'SERVICE', valid: true, within_limit: true });
  });

  it('does not replace a missing measurement route with a browser estimate', async () => {
    const missing = createHttpLensClient({
      ...BASE,
      fetchImpl: (async () => jsonResponse({ error: { code: 'NOT_FOUND', message: 'нет маршрута', details: {} }, request_id: 'r' }, 404)) as unknown as typeof fetch,
    });
    await expect(missing.measureArea(square)).rejects.toMatchObject({ code: 'NOT_FOUND', status: 404 });

    const failing = createHttpLensClient({
      ...BASE,
      fetchImpl: (async () => jsonResponse({ error: { code: 'SOURCE_UNAVAILABLE', message: 'нет данных', details: {} }, request_id: 'r' }, 503)) as unknown as typeof fetch,
    });
    await expect(failing.measureArea(square)).rejects.toMatchObject({ code: 'SOURCE_UNAVAILABLE' });
  });

  it('refuses an artifact url outside the service API and reports a hash mismatch', async () => {
    const artifact: Artifact = {
      artifact_id: 'a1',
      role: 'cells',
      media_type: 'application/geo+json',
      sha256: '0xdeadbeef',
      size_bytes: 10,
      url: 'https://evil.test/cells.json',
      bbox_wgs84: null,
      crs: null,
      resolution: null,
      resolution_units: null,
      unit: null,
      provenance: 'STUB_FIXTURE',
    };
    const client = createHttpLensClient({ ...BASE, fetchImpl: (async () => new Response('{}')) as unknown as typeof fetch });
    await expect(client.getArtifact(artifact)).rejects.toMatchObject({ code: 'ARTIFACT_URL_REJECTED' });

    const served = createHttpLensClient({
      ...BASE,
      fetchImpl: (async () => new Response('{"type":"FeatureCollection","features":[]}', { headers: { 'Content-Type': 'application/geo+json' } })) as unknown as typeof fetch,
    });
    const payload = await served.getArtifact({ ...artifact, url: '/api/v2/analyses/a1/artifacts/a1' });
    expect(payload.integrity).toBe('MISMATCH');
    expect(payload.data).toBeNull();
  });

  it('rejects a base url that is not the v2 API root', () => {
    expect(() => createHttpLensClient({ ...BASE, baseUrl: 'https://service.test/api/v1' })).toThrow(LensError);
  });
});

describe('payload normalisation', () => {
  it('keeps unknown enum values and fills the containers the screens iterate over', () => {
    const result = normalizeResult({
      units: { status: 'AVAILABLE', q: 5, zero_reason: 'SOMETHING_NEW' },
      evidence_status: 'PARTIALLY_OBSERVED',
      evidence: { warnings: ['простая строка'] },
      timeline: null,
      zones: undefined,
    });
    expect(result.units.zero_reason).toBe('SOMETHING_NEW');
    expect(result.evidence_status).toBe('PARTIALLY_OBSERVED');
    expect(result.timeline).toEqual([]);
    expect(result.zones).toEqual([]);
    expect(result.evidence.warnings[0]).toMatchObject({ code: 'UNSTRUCTURED_WARNING', severity: 'WARNING', message: 'простая строка' });
  });

  it('accepts both the typed warning and the bare sentence of an older deployment', () => {
    const warnings = normalizeWarnings([{ code: 'LOW_OPTICS', severity: 'BLOCKING', message: 'мало пригодной оптики', details: { fraction: 0.1 } }, 'строка']);
    expect(warnings[0]).toMatchObject({ code: 'LOW_OPTICS', severity: 'BLOCKING', details: { fraction: 0.1 } });
    expect(warnings[1]?.code).toBe('UNSTRUCTURED_WARNING');
  });

  it('normalises legacy critical severity and sorts blocking findings first', () => {
    const warnings = normalizeWarnings([
      { code: 'INFO_FIRST', severity: 'INFO', message: 'info', details: {} },
      { code: 'OLD_CRITICAL', severity: 'CRITICAL', message: 'critical', details: {} },
      { code: 'WARN', severity: 'WARNING', message: 'warning', details: {} },
    ]);
    expect(warnings.map((item) => item.code)).toEqual(['OLD_CRITICAL', 'WARN', 'INFO_FIRST']);
    expect(warnings[0]?.severity).toBe('BLOCKING');
  });
});

describe('mode selection', () => {
  it('uses the live service by default and the offline set only when asked', () => {
    expect(resolveLensConfig({}, '').mode).toBe('http');
    expect(resolveLensConfig({}, '?lens=fixture').mode).toBe('fixture');
    expect(resolveLensConfig({ VITE_LENS_API_MODE: 'fixture' }, '').mode).toBe('fixture');
    expect(resolveLensConfig({ VITE_LENS_API_MODE: 'fixture' }, '?lens=http').mode).toBe('http');
  });

  it('keeps the HTTP client after Backend failure instead of enabling fixtures', async () => {
    const config = resolveLensConfig({}, '');
    const client = createLensClient(config, {
      getToken: () => 'runtime-token',
      fetchImpl: vi.fn(async () => { throw new TypeError('connection refused'); }) as unknown as typeof fetch,
    });
    expect(client.kind).toBe('http');
    await expect(client.getCatalog()).rejects.toMatchObject({ code: 'NETWORK' });
    expect(client.kind).toBe('http');
  });

  it('never carries a credential in configuration or in the mode switch link', () => {
    const config = resolveLensConfig({ VITE_LENS_API_MODE: 'http', VITE_LENS_TOKEN: 'baked' } as Record<string, string>, '?token=secret');
    expect(JSON.stringify(config)).not.toContain('baked');
    expect(JSON.stringify(config)).not.toContain('secret');
    expect(switchModeHref('fixture', { pathname: '/lens', search: '?lens=http&token=secret', hash: '' })).not.toContain('secret');
  });
});

describe('geometry rules', () => {
  it('names the specific problem instead of failing generically', () => {
    expect(() => validateGeometry(null)).toThrow(/Контур не задан/);
    expect(() => validateGeometry({ type: 'Polygon', coordinates: [] })).toThrow(/пуст/);
    expect(() => validateGeometry({ type: 'Polygon', coordinates: [[[0, 0], [1, 1], [0, 0]]] })).toThrow(/меньше трёх вершин/);
    expect(() =>
      validateGeometry({ type: 'Polygon', coordinates: [[[3300000, 6200000], [3300100, 6200000], [3300100, 6200100], [3300000, 6200100], [3300000, 6200000]]] }),
    ).toThrow(/WGS84/);
    expect(() =>
      validateGeometry({ type: 'Polygon', coordinates: [[[32.91, 56.59], [32.94, 56.61], [32.94, 56.59], [32.91, 56.61], [32.91, 56.59]]] }),
    ).toThrow(/пересекает сам себя/);
    expect(() => validateGeometry(square)).not.toThrow();
  });

  it('estimates an area close to the official one but never claims to be the service', async () => {
    const client = createFixtureLensClient();
    const official = await client.measureArea(square);
    expect(official.source).toBe('CLIENT_ESTIMATE');
    expect(official.area_ha).not.toBeNull();
    expect(approximateAreaHa(square)).toBeCloseTo(official.area_ha as number, 6);
  });
});
