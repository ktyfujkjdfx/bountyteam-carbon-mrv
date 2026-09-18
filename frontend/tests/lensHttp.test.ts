import { describe, expect, it, vi } from 'vitest';
import { LensError } from '../src/lens/adapter';
import { createLensClient, resolveLensConfig, switchLensModeHref, LENS_TOKEN_STORAGE_KEY } from '../src/lens/config';
import { createHttpLensClient, normalizeResult } from '../src/lens/httpClient';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function memoryStorage(seed: Record<string, string> = {}) {
  const map = new Map(Object.entries(seed));
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => void map.set(key, value),
    removeItem: (key: string) => void map.delete(key),
    snapshot: () => Object.fromEntries(map),
  };
}

describe('live client configuration', () => {
  it('defaults to the labelled set and switches only on explicit configuration', () => {
    expect(resolveLensConfig({}, '', memoryStorage()).mode).toBe('fixture');
    expect(resolveLensConfig({ VITE_LENS_API_MODE: 'http' }, '', memoryStorage()).mode).toBe('http');
    expect(resolveLensConfig({}, '?lensapi=http', memoryStorage()).mode).toBe('http');
    expect(resolveLensConfig({ VITE_LENS_API_MODE: 'http' }, '?lensapi=fixture', memoryStorage()).mode).toBe('fixture');
  });

  it('never takes the credential from build variables', () => {
    const env = { VITE_LENS_API_MODE: 'http', VITE_LENS_TOKEN: 'baked-into-dist' } as Record<string, string>;
    const config = resolveLensConfig(env, '', memoryStorage());
    expect(config.token).toBe('');
    expect(config.tokenSource).toBe('none');
    expect(JSON.stringify(config)).not.toContain('baked-into-dist');
  });

  it('accepts a runtime credential from the URL and keeps it in the session only', () => {
    const storage = memoryStorage();
    const config = resolveLensConfig({}, '?lensapi=http&token=runtime-secret', storage);
    expect(config.token).toBe('runtime-secret');
    expect(config.tokenSource).toBe('url');
    expect(storage.snapshot()[LENS_TOKEN_STORAGE_KEY]).toBe('runtime-secret');

    const restored = resolveLensConfig({}, '?lensapi=http', storage);
    expect(restored.tokenSource).toBe('session');
  });

  it('drops the credential from the mode switch link', () => {
    const href = switchLensModeHref('fixture', { pathname: '/lens', search: '?lensapi=http&token=secret', hash: '' });
    expect(href).toContain('lensapi=fixture');
    expect(href).not.toContain('secret');
  });

  it('refuses a base URL that is not the v2 API root', () => {
    expect(() => createHttpLensClient({ baseUrl: 'https://example.test/api/v1', token: '' })).toThrow(LensError);
  });

  it('builds a fixture client without touching the network', () => {
    expect(createLensClient({ mode: 'fixture', baseUrl: '/api/v2', token: '', tokenSource: 'none', source: 'env' }).kind).toBe('fixture');
  });
});

describe('live client calls', () => {
  const base = { baseUrl: 'https://service.test/api/v2', token: 'runtime-token' };

  it('sends the runtime credential and the idempotency key, and omits cookies', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ job_id: 'j1', state: 'QUEUED', status_url: '/api/v2/jobs/j1', result_id: null, error: null }));
    const client = createHttpLensClient({ ...base, fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.submitAnalysis(
      { aoi_id: 'RU_TVER_01', parent_aoi_id: null, geometry: { type: 'Polygon', coordinates: [] }, year_start: 2019, year_end: 2020, claimed_units: null },
      { scenario: 'DOC_EXAMPLE_Q395', idempotencyKey: 'key-1' },
    );
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('https://service.test/api/v2/analyses');
    expect((init.headers as Record<string, string>)['X-Lens-Token']).toBe('runtime-token');
    expect((init.headers as Record<string, string>)['Idempotency-Key']).toBe('key-1');
    expect(init.credentials).toBe('omit');
  });

  it('turns a service error envelope into a LensError instead of a blank screen', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ error: { code: 'AREA_TOO_LARGE', message: 'Площадь превышает предел' } }, 422));
    const client = createHttpLensClient({ ...base, fetchImpl: fetchImpl as unknown as typeof fetch });
    await expect(client.listAreas()).rejects.toMatchObject({ code: 'AREA_TOO_LARGE' });
  });

  it('keeps unknown enum values and fills the arrays the screens iterate over', () => {
    const result = normalizeResult({
      units: { status: 'AVAILABLE', q: 12, reason: 'SOMETHING_NEW' },
      evidence_status: 'PARTIALLY_OBSERVED',
      request: { aoi_id: 'RU_TVER_01', geometry: { type: 'Polygon', coordinates: [] }, year_start: 2019, year_end: 2020 },
      coverage: null,
    });
    expect(result.units.reason).toBe('SOMETHING_NEW');
    expect(result.evidence_status).toBe('PARTIALLY_OBSERVED');
    expect(result.coverage).toEqual([]);
    expect(result.zones).toEqual([]);
    expect(result.provenance.computed_by).toBe('BACKEND');
    expect(result.layers.length).toBeGreaterThan(0);
  });

  it('rejects artifact URLs outside the service API', async () => {
    const client = createHttpLensClient({ ...base, fetchImpl: (async () => jsonResponse({})) as unknown as typeof fetch });
    await expect(
      client.fetchArtifact({
        artifact_id: 'a1',
        role: 'stock_preview',
        media_type: 'image/png',
        sha256: '00',
        url: 'https://evil.test/preview.png',
        bbox: null,
        crs: 'EPSG:4326',
        resolution_m: 100,
        unit: null,
        provenance: '',
      }),
    ).rejects.toMatchObject({ code: 'ARTIFACT_URL_REJECTED' });
  });

  it('reports a hash mismatch instead of showing the artifact as trusted', async () => {
    const bytes = new TextEncoder().encode('not the declared bytes');
    const fetchImpl = vi.fn(async () => new Response(bytes, { status: 200, headers: { 'Content-Type': 'image/png' } }));
    const client = createHttpLensClient({ ...base, fetchImpl: fetchImpl as unknown as typeof fetch });
    const payload = await client.fetchArtifact({
      artifact_id: 'a1',
      role: 'stock_preview',
      media_type: 'image/png',
      sha256: '0xdeadbeef',
      url: '/api/v2/artifacts/a1',
      bbox: null,
      crs: 'EPSG:4326',
      resolution_m: 100,
      unit: 'т C/га',
      provenance: 'CCI_V7',
    });
    expect(payload.integrity).toBe('MISMATCH');
    expect(payload.src).toBeNull();
  });
});
