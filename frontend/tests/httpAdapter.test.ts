// @vitest-environment node
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../src/api/errors';
import { createFixtureBackend } from '../src/api/fixtureAdapter';
import { createHttpAdapter } from '../src/api/httpAdapter';

interface Call {
  url: string;
  init: RequestInit;
}

function mockFetch(respond: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const calls: Call[] = [];
  const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init: init ?? {} });
    return respond(url, init ?? {});
  });
  return { calls, fetchImpl: fetchImpl as unknown as typeof fetch };
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

function headersOf(call: Call | undefined): Record<string, string> {
  return (call?.init.headers ?? {}) as Record<string, string>;
}

describe('HTTP adapter', () => {
  it('implements exactly the same interface as the fixture adapter', () => {
    const http = createHttpAdapter({ baseUrl: 'http://127.0.0.1:8000/api/v1', demoSession: 's' });
    const fixture = createFixtureBackend().client;
    expect(Object.keys(http).sort()).toEqual(Object.keys(fixture).sort());
    expect(http.kind).toBe('http');
    expect(fixture.kind).toBe('fixture');
  });

  it('rejects a base URL that is not /api/v1', () => {
    expect(() => createHttpAdapter({ baseUrl: 'http://127.0.0.1:8000', demoSession: 's' })).toThrow(ApiError);
  });

  it('sends X-Demo-Session everywhere except /health, X-Demo-Actor on actor routes, Idempotency-Key on POST', async () => {
    const { calls, fetchImpl } = mockFetch((url) => {
      if (url.endsWith('/verify')) return json({ job_id: 'x', state: 'QUEUED', status_url: '/api/v1/jobs/x' }, 202);
      return json({ items: [] });
    });
    const client = createHttpAdapter({ baseUrl: 'http://127.0.0.1:8000/api/v1/', demoSession: 'demo-session', fetchImpl });

    await client.getHealth();
    await client.getPlot('SYNTHETIC-PLOT-001', 'buyer');
    await client.getCredits('SYNTHETIC-PLOT-001', 'recipient');
    await client.startVerification('SYNTHETIC-PLOT-001', 'issuer', { scenario_id: 'baseline' }, { idempotencyKey: 'idem-key-1' });
    await client.listEvents({ plotId: 'SYNTHETIC-PLOT-001', cursor: 'c1', limit: 20 });

    expect(calls[0]?.url).toBe('http://127.0.0.1:8000/api/v1/health');
    expect(headersOf(calls[0])['X-Demo-Session']).toBeUndefined();
    expect(headersOf(calls[1])).toMatchObject({ 'X-Demo-Session': 'demo-session', 'X-Demo-Actor': 'buyer' });
    expect(headersOf(calls[2])).toMatchObject({ 'X-Demo-Actor': 'recipient' });
    expect(calls[3]?.init.method).toBe('POST');
    expect(headersOf(calls[3])).toMatchObject({
      'X-Demo-Session': 'demo-session',
      'X-Demo-Actor': 'issuer',
      'Idempotency-Key': 'idem-key-1',
      'Content-Type': 'application/json',
    });
    expect(calls[3]?.init.body).toBe('{"scenario_id":"baseline"}');
    expect(calls[4]?.url).toBe('http://127.0.0.1:8000/api/v1/events?plot_id=SYNTHETIC-PLOT-001&cursor=c1&limit=20');
    expect(calls.every((c) => c.init.credentials === 'omit')).toBe(true);
  });

  it('resolves status_url and artifact url against the API root (no path duplication)', async () => {
    const { calls, fetchImpl } = mockFetch((url) =>
      url.includes('/artifacts/') ? new Response(JSON.stringify({ type: 'FeatureCollection', features: [] }), { status: 200 }) : json({}),
    );
    const client = createHttpAdapter({ baseUrl: 'http://127.0.0.1:8000/api/v1', demoSession: 's', fetchImpl });
    await client.getJob('/api/v1/jobs/30000000-0000-4000-8000-000000000001');
    await client.getOperation('40000000-0000-4000-8000-000000000001');
    await client.getArtifact('/api/v1/artifacts/fire-affected_area', 'application/geo+json');
    expect(calls.map((c) => c.url)).toEqual([
      'http://127.0.0.1:8000/api/v1/jobs/30000000-0000-4000-8000-000000000001',
      'http://127.0.0.1:8000/api/v1/operations/40000000-0000-4000-8000-000000000001',
      'http://127.0.0.1:8000/api/v1/artifacts/fire-affected_area',
    ]);
    expect(headersOf(calls[2])['X-Demo-Session']).toBe('s');
  });

  it('supports a relative same-origin base URL', async () => {
    const { calls, fetchImpl } = mockFetch(() => json({}));
    const client = createHttpAdapter({ baseUrl: '/api/v1', demoSession: 's', fetchImpl });
    await client.getOperation('/api/v1/operations/40000000-0000-4000-8000-000000000001');
    expect(calls[0]?.url).toBe('/api/v1/operations/40000000-0000-4000-8000-000000000001');
  });

  it.each([401, 403, 404, 409, 422, 503])('maps HTTP %i error envelope to ApiError', async (status) => {
    const { fetchImpl } = mockFetch(() =>
      json({ error: { code: `CODE_${status}`, message: `message ${status}`, details: { a: 1 } }, request_id: '30000000-0000-4000-8000-000000000001' }, status),
    );
    const client = createHttpAdapter({ baseUrl: 'http://h/api/v1', demoSession: 's', fetchImpl });
    const error = await client.listPlots().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      kind: 'http',
      status,
      code: `CODE_${status}`,
      message: `message ${status}`,
      requestId: '30000000-0000-4000-8000-000000000001',
      details: { a: 1 },
      retryable: status === 503,
    });
  });

  it('never treats a non-ok response without envelope as success', async () => {
    const { fetchImpl } = mockFetch(() => new Response('<html>oops</html>', { status: 500 }));
    const client = createHttpAdapter({ baseUrl: 'http://h/api/v1', demoSession: 's', fetchImpl });
    await expect(client.getHealth()).rejects.toMatchObject({ kind: 'http', status: 500, code: null });
  });

  it('reports a non-JSON 200 as a contract error', async () => {
    const { fetchImpl } = mockFetch(() => new Response('<html>index</html>', { status: 200 }));
    const client = createHttpAdapter({ baseUrl: 'http://h/api/v1', demoSession: 's', fetchImpl });
    await expect(client.getHealth()).rejects.toMatchObject({ kind: 'contract' });
  });

  it('maps network failure to a retryable network error (offline state)', async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError('Failed to fetch');
    }) as unknown as typeof fetch;
    const client = createHttpAdapter({ baseUrl: 'http://h/api/v1', demoSession: 's', fetchImpl });
    await expect(client.getHealth()).rejects.toMatchObject({ kind: 'network', retryable: true });
  });

  it('times out slow requests', async () => {
    const fetchImpl = vi.fn(
      (_url: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
        }),
    ) as unknown as typeof fetch;
    const client = createHttpAdapter({ baseUrl: 'http://h/api/v1', demoSession: 's', fetchImpl, timeoutMs: 30 });
    await expect(client.getHealth()).rejects.toMatchObject({ kind: 'timeout' });
  });

  it('distinguishes caller abort from failure', async () => {
    const controller = new AbortController();
    const fetchImpl = vi.fn(
      (_url: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
        }),
    ) as unknown as typeof fetch;
    const client = createHttpAdapter({ baseUrl: 'http://h/api/v1', demoSession: 's', fetchImpl });
    const pending = client.getHealth({ signal: controller.signal });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ kind: 'aborted' });
  });

  it('loads only Backend artifact URLs and never GeoTIFF', async () => {
    const { calls, fetchImpl } = mockFetch(() => new Response(new Uint8Array([137, 80, 78, 71]), { status: 200 }));
    const client = createHttpAdapter({ baseUrl: 'http://h/api/v1', demoSession: 's', fetchImpl });
    await expect(client.getArtifact('http://evil.example/x.png', 'image/png')).rejects.toMatchObject({ kind: 'contract' });
    await expect(client.getArtifact('/api/v1/artifacts/../../etc/passwd', 'image/png')).rejects.toMatchObject({ kind: 'contract' });
    await expect(client.getArtifact('C:\\data\\before.png', 'image/png')).rejects.toMatchObject({ kind: 'contract' });
    await expect(client.getArtifact('/api/v1/artifacts/fire-dnbr_raster', 'image/tiff')).rejects.toMatchObject({ kind: 'contract' });
    expect(calls).toHaveLength(0);

    const created = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
    const revoked = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const payload = await client.getArtifact('/api/v1/artifacts/fire-preview_after', 'image/png');
    expect(payload).toMatchObject({ kind: 'image', src: 'blob:test' });
    payload.release();
    expect(created).toHaveBeenCalledOnce();
    expect(revoked).toHaveBeenCalledWith('blob:test');
  });

  it('surfaces artifact 404 as an error state', async () => {
    const { fetchImpl } = mockFetch(() => json({ error: { code: 'ARTIFACT_NOT_FOUND', message: 'missing', details: {} }, request_id: 'r' }, 404));
    const client = createHttpAdapter({ baseUrl: 'http://h/api/v1', demoSession: 's', fetchImpl });
    await expect(client.getArtifact('/api/v1/artifacts/gone', 'image/png')).rejects.toMatchObject({ status: 404, code: 'ARTIFACT_NOT_FOUND' });
  });
});
