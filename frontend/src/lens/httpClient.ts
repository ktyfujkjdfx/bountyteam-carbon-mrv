// Live Carbon Lens client for /api/v2 as reviewed on backend e9817d0 (PR #15).
//
// Credentials are runtime values, never build variables: the session token is held in memory by
// src/lens/auth.ts and passed in through a getter. Nothing here falls back to the offline set when
// the service fails — a failure is reported as a failure.
//
// `measureArea` calls POST /areas/measure and, on 404/405, falls back to the client's own
//     spherical estimate, clearly marked as an estimate rather than the authoritative area.

import { LensError, normalizeAnalysis, normalizeResult, type ArtifactPayload, type LensApiClient, type SubmitOptions, asRecord } from './client';
import { approximateAreaHa } from './geometry';
import type { Analysis, AnalysisAccepted, AnalysisRequestBody, AreaMeasurement, Artifact, Catalog, Geometry, Proof, Report } from './types';

export interface LensHttpConfig {
  baseUrl: string;
  /** Runtime token; read at call time so a re-login is picked up without rebuilding the client. */
  getToken: () => string;
  fetchImpl?: typeof fetch | undefined;
  timeoutMs?: number | undefined;
}

const API_PATH = /^\/api\/v2\//;

export async function sha256Hex(bytes: ArrayBuffer): Promise<string | null> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) return null;
  const digest = await subtle.digest('SHA-256', bytes);
  return `0x${[...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')}`;
}

export function createHttpLensClient(config: LensHttpConfig): LensApiClient {
  const baseUrl = config.baseUrl.replace(/\/+$/, '');
  if (!/\/api\/v2$/.test(baseUrl)) {
    throw new LensError('CONFIG_INVALID', `Базовый URL Carbon Lens должен оканчиваться на /api/v2, получено "${config.baseUrl}"`);
  }
  const apiRoot = baseUrl.slice(0, -'/api/v2'.length);
  const timeoutMs = config.timeoutMs ?? 30_000;
  const fetchImpl = config.fetchImpl ?? globalThis.fetch.bind(globalThis);

  async function send(
    path: string,
    init: { method?: 'GET' | 'POST'; body?: unknown; idempotencyKey?: string; accept?: string; signal?: AbortSignal | undefined },
  ): Promise<Response> {
    const token = config.getToken();
    const headers: Record<string, string> = { Accept: init.accept ?? 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;
    if (init.idempotencyKey) headers['Idempotency-Key'] = init.idempotencyKey;
    if (init.body !== undefined) headers['Content-Type'] = 'application/json';

    const timeout = AbortSignal.timeout(timeoutMs);
    const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
    const url = API_PATH.test(path) ? `${apiRoot}${path}` : `${baseUrl}${path}`;

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
    if (!response.ok) throw await failure(response);
    return response;
  }

  async function failure(response: Response): Promise<LensError> {
    const payload = asRecord(await response.json().catch(() => null));
    const envelope = asRecord(payload.error);
    const details = asRecord(envelope.details);
    const requestId = typeof payload.request_id === 'string' ? payload.request_id : null;
    return new LensError(String(envelope.code ?? `HTTP_${response.status}`), String(envelope.message ?? `Сервис ответил HTTP ${response.status}`), {
      status: response.status,
      detail: requestId ? `request_id: ${requestId}` : null,
      details,
    });
  }

  async function json<T>(path: string, init: Parameters<typeof send>[1] = {}): Promise<T> {
    const response = await send(path, init);
    try {
      return (await response.json()) as T;
    } catch {
      throw new LensError('CONTRACT', 'Сервис вернул не-JSON ответ');
    }
  }

  return {
    kind: 'http',

    getCatalog(signal) {
      return json<Catalog>('/catalog', { signal });
    },

    async measureArea(geometry: Geometry, signal?: AbortSignal): Promise<AreaMeasurement> {
      try {
        const payload = await json<{ area_ha?: number }>('/areas/measure', { method: 'POST', body: { geometry }, signal });
        if (typeof payload.area_ha !== 'number' || !Number.isFinite(payload.area_ha)) {
          throw new LensError('CONTRACT', 'Сервис не вернул площадь контура');
        }
        return { area_ha: payload.area_ha, source: 'SERVICE', note: 'Геодезическая площадь, рассчитанная сервисом.' };
      } catch (error) {
        const missing = error instanceof LensError && (error.status === 404 || error.status === 405);
        if (!missing) throw error;
        return {
          area_ha: approximateAreaHa(geometry),
          source: 'CLIENT_ESTIMATE',
          note: 'Предварительная оценка в браузере: сервис пока не измеряет произвольный контур. Точную площадь вернёт расчёт.',
        };
      }
    },

    createAnalysis(body: AnalysisRequestBody, options: SubmitOptions) {
      return json<AnalysisAccepted>('/analyses', {
        method: 'POST',
        body,
        idempotencyKey: options.idempotencyKey,
        signal: options.signal,
      });
    },

    async getAnalysis(analysisId: string, signal?: AbortSignal): Promise<Analysis> {
      return normalizeAnalysis(await json<unknown>(`/analyses/${encodeURIComponent(analysisId)}`, { signal }));
    },

    getProof(analysisId: string, signal?: AbortSignal) {
      return json<Proof>(`/analyses/${encodeURIComponent(analysisId)}/proof`, { signal });
    },

    async getReport(analysisId: string, _format: 'json', signal?: AbortSignal): Promise<Report> {
      const payload = await json<Record<string, unknown>>(`/analyses/${encodeURIComponent(analysisId)}/report?format=json`, { signal });
      return { ...(payload as unknown as Report), result: normalizeResult(payload.result) };
    },

    async getReportHtml(analysisId: string, signal?: AbortSignal): Promise<string> {
      const response = await send(`/analyses/${encodeURIComponent(analysisId)}/report?format=html`, { accept: 'text/html', signal });
      return response.text();
    },

    /**
     * Artifacts are fetched only through artifacts[].url and checked against the declared sha256.
     * A mismatch is reported, never rendered as a trusted layer, and a failure of one artifact leaves
     * the rest of the result — and the map — in place.
     */
    async getArtifact(artifact: Artifact, signal?: AbortSignal): Promise<ArtifactPayload> {
      if (!API_PATH.test(artifact.url)) {
        throw new LensError('ARTIFACT_URL_REJECTED', `Артефакт разрешён только по artifacts[].url сервиса: ${artifact.url}`);
      }
      const response = await send(artifact.url, { accept: artifact.media_type, signal });
      const bytes = await response.arrayBuffer();
      const computed = await sha256Hex(bytes);
      const expected = artifact.sha256.startsWith('0x') ? artifact.sha256.toLowerCase() : `0x${artifact.sha256.toLowerCase()}`;
      const integrity: ArtifactPayload['integrity'] = computed === null ? 'UNVERIFIABLE' : computed === expected ? 'VERIFIED' : 'MISMATCH';

      if (artifact.media_type.includes('json')) {
        if (integrity === 'MISMATCH') {
          return { kind: 'geojson', mediaType: artifact.media_type, src: null, data: null, integrity, computed_sha256: computed, release: () => undefined };
        }
        let data: unknown;
        try {
          data = JSON.parse(new TextDecoder().decode(bytes)) as unknown;
        } catch {
          throw new LensError('CONTRACT', 'Артефакт GeoJSON не разбирается');
        }
        return { kind: 'geojson', mediaType: artifact.media_type, src: null, data, integrity, computed_sha256: computed, release: () => undefined };
      }
      if (artifact.media_type.startsWith('image/')) {
        if (integrity === 'MISMATCH') {
          return { kind: 'image', mediaType: artifact.media_type, src: null, data: null, integrity, computed_sha256: computed, release: () => undefined };
        }
        const src = URL.createObjectURL(new Blob([bytes], { type: artifact.media_type }));
        return { kind: 'image', mediaType: artifact.media_type, src, data: null, integrity, computed_sha256: computed, release: () => URL.revokeObjectURL(src) };
      }
      throw new LensError('MEDIA_TYPE_REJECTED', `Браузер не отображает ${artifact.media_type}; нужен PNG/WebP или GeoJSON`);
    },
  };
}
