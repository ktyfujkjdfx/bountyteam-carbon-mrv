// Live Carbon Lens client behind the same LensApiClient boundary as the fixture one.
// Endpoints and field names are provisional until Backend publishes G0 (feat/lens-g0-contracts);
// every assumption is listed in frontend/docs/LENS_INTEGRATION.md. Switching modes is a config
// decision only: nothing here falls back to fixtures when the service fails.

import { LensError, buildLayers, type LensApiClient, type LensSubmitOptions } from './adapter';
import type { LensArea, LensArtifact, LensGeometry, LensJob, LensRequest, LensResult } from './types';

export interface LensHttpConfig {
  baseUrl: string;
  /** Runtime credential: entered by the operator or taken from the URL, never baked into dist. */
  token: string;
  fetchImpl?: typeof fetch | undefined;
  timeoutMs?: number | undefined;
}

export interface ArtifactPayload {
  kind: 'image' | 'geojson';
  mediaType: string;
  src: string | null;
  data: unknown;
  integrity: 'VERIFIED' | 'MISMATCH' | 'UNVERIFIABLE';
  computed_sha256: string | null;
  release: () => void;
}

const ARTIFACT_PATH = /^\/api\/v2\//;

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

/**
 * Keep the payload as the service sent it, but guarantee the arrays the screens iterate over exist.
 * Unknown enum values are passed through untouched: the UI renders them through the neutral
 * UNKNOWN fallback instead of crashing or silently mapping them to a known status.
 */
export function normalizeResult(payload: unknown): LensResult {
  const record = asRecord(payload);
  const result = {
    ...record,
    coverage: asArray(record.coverage),
    timeline: asArray(record.timeline),
    zones: asArray(record.zones).map((zone) => ({ ...asRecord(zone), artifact_ids: asArray(asRecord(zone).artifact_ids) })),
    layers: asArray(record.layers),
    artifacts: asArray(record.artifacts),
    sources: asArray(record.sources),
    limitations: asArray(record.limitations),
    prices: asArray(record.prices),
    optical: { scene_keys: asArray(asRecord(record.optical).scene_keys), note: String(asRecord(record.optical).note ?? '') },
    provenance: {
      official: asArray(asRecord(record.provenance).official),
      computed_by: 'BACKEND',
      computed_note: String(asRecord(record.provenance).computed_note ?? 'Значения рассчитаны сервисом Backend.'),
    },
    fixture: record.fixture ?? null,
  } as unknown as LensResult;
  return result.layers.length > 0 ? result : { ...result, layers: buildLayers(result, 'http') };
}

export async function sha256Hex(bytes: ArrayBuffer): Promise<string | null> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) return null;
  const digest = await subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export function createHttpLensClient(config: LensHttpConfig) {
  const baseUrl = config.baseUrl.replace(/\/+$/, '');
  if (!/\/api\/v2$/.test(baseUrl)) {
    throw new LensError('CONFIG_INVALID', `Базовый URL Carbon Lens должен оканчиваться на /api/v2, получено "${config.baseUrl}"`);
  }
  const apiRoot = baseUrl.slice(0, -'/api/v2'.length);
  const timeoutMs = config.timeoutMs ?? 20_000;
  const fetchImpl = config.fetchImpl ?? globalThis.fetch.bind(globalThis);

  async function send(path: string, init: { method?: 'GET' | 'POST'; body?: unknown; idempotencyKey?: string; accept?: string; signal?: AbortSignal | undefined }): Promise<Response> {
    const headers: Record<string, string> = { Accept: init.accept ?? 'application/json' };
    if (config.token) headers['X-Lens-Token'] = config.token;
    if (init.idempotencyKey) headers['Idempotency-Key'] = init.idempotencyKey;
    if (init.body !== undefined) headers['Content-Type'] = 'application/json';

    const timeout = AbortSignal.timeout(timeoutMs);
    const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
    const url = ARTIFACT_PATH.test(path) ? `${apiRoot}${path}` : `${baseUrl}${path}`;

    let response: Response;
    try {
      response = await fetchImpl(url, {
        method: init.method ?? 'GET',
        headers,
        body: init.body === undefined ? null : JSON.stringify(init.body),
        signal,
        credentials: 'omit',
        cache: 'no-store',
      });
    } catch (error) {
      if (init.signal?.aborted) throw new LensError('ABORTED', 'Запрос отменён');
      if (timeout.aborted) throw new LensError('TIMEOUT', `Сервис не ответил за ${Math.round(timeoutMs / 1000)} с`);
      throw new LensError('NETWORK', `Сервис недоступен: ${error instanceof Error ? error.message : String(error)}`);
    }
    if (!response.ok) {
      const payload = asRecord(await response.json().catch(() => null));
      const envelope = asRecord(payload.error);
      throw new LensError(
        String(envelope.code ?? `HTTP_${response.status}`),
        String(envelope.message ?? `Сервис ответил HTTP ${response.status}`),
        typeof envelope.details === 'string' ? envelope.details : null,
      );
    }
    return response;
  }

  async function json<T>(path: string, init: Parameters<typeof send>[1] = {}): Promise<T> {
    const response = await send(path, init);
    try {
      return (await response.json()) as T;
    } catch {
      throw new LensError('CONTRACT', 'Сервис вернул не-JSON ответ');
    }
  }

  const client: LensApiClient = {
    kind: 'http',
    async listAreas() {
      const payload = await json<{ areas?: LensArea[] }>('/areas');
      return asArray(payload.areas) as LensArea[];
    },
    async getAreaGeometry(aoiId) {
      const payload = await json<{ geometry?: LensGeometry }>(`/areas/${encodeURIComponent(aoiId)}/geometry`);
      if (!payload.geometry) throw new LensError('AOI_NOT_FOUND', `Сервис не вернул геометрию участка ${aoiId}`);
      return payload.geometry;
    },
    async measureArea(geometry) {
      const payload = await json<{ area_ha?: number }>('/areas/measure', { method: 'POST', body: { geometry } });
      if (typeof payload.area_ha !== 'number') throw new LensError('CONTRACT', 'Сервис не вернул площадь контура');
      return payload.area_ha;
    },
    async submitAnalysis(request: LensRequest, options: LensSubmitOptions) {
      return json<LensJob>('/analyses', {
        method: 'POST',
        body: { ...request, scenario_hint: options.scenario },
        idempotencyKey: options.idempotencyKey,
        signal: options.signal,
      });
    },
    async getJob(jobId, signal) {
      return json<LensJob>(`/jobs/${encodeURIComponent(jobId)}`, { signal });
    },
    async getResult(resultId, signal) {
      return normalizeResult(await json<unknown>(`/results/${encodeURIComponent(resultId)}`, { signal }));
    },
  };

  /**
   * Artifacts are fetched only through artifacts[].url and checked against the declared sha256.
   * A mismatch is reported, never rendered as a trusted layer; a 404/503 of one artifact does not
   * remove the map or the calculation, it only marks this layer as unavailable.
   */
  async function fetchArtifact(artifact: LensArtifact, signal?: AbortSignal): Promise<ArtifactPayload> {
    if (!ARTIFACT_PATH.test(artifact.url)) {
      throw new LensError('ARTIFACT_URL_REJECTED', `Артефакт разрешён только по artifacts[].url сервиса: ${artifact.url}`);
    }
    const response = await send(artifact.url, { accept: artifact.media_type, signal });
    const bytes = await response.arrayBuffer();
    const computed = await sha256Hex(bytes);
    const expected = artifact.sha256.replace(/^0x/, '').toLowerCase();
    const integrity: ArtifactPayload['integrity'] = computed === null ? 'UNVERIFIABLE' : computed === expected ? 'VERIFIED' : 'MISMATCH';

    if (artifact.media_type === 'application/geo+json') {
      const text = new TextDecoder().decode(bytes);
      let data: unknown;
      try {
        data = JSON.parse(text) as unknown;
      } catch {
        throw new LensError('CONTRACT', 'Артефакт GeoJSON не разбирается');
      }
      return { kind: 'geojson', mediaType: artifact.media_type, src: null, data, integrity, computed_sha256: computed, release: () => undefined };
    }
    if (artifact.media_type === 'image/png' || artifact.media_type === 'image/webp') {
      if (integrity === 'MISMATCH') {
        return { kind: 'image', mediaType: artifact.media_type, src: null, data: null, integrity, computed_sha256: computed, release: () => undefined };
      }
      const src = URL.createObjectURL(new Blob([bytes], { type: artifact.media_type }));
      return { kind: 'image', mediaType: artifact.media_type, src, data: null, integrity, computed_sha256: computed, release: () => URL.revokeObjectURL(src) };
    }
    throw new LensError('MEDIA_TYPE_REJECTED', `Браузер не отображает ${artifact.media_type}; нужен PNG/WebP превью или GeoJSON`);
  }

  return { ...client, fetchArtifact };
}

export type LensHttpClient = ReturnType<typeof createHttpLensClient>;
