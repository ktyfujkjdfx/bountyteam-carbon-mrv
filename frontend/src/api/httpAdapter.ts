import type { ArtifactPayload, EventsQuery, MrvApiClient, MutationOptions, RequestOptions } from './client';
import { ApiError, isErrorEnvelope, toApiError } from './errors';
import {
  ARTIFACT_URL,
  JOB_STATUS_URL,
  OPERATION_STATUS_URL,
  type BuyRequest,
  type Credits,
  type DemoActor,
  type Events,
  type Health,
  type History,
  type IssueRequest,
  type Job,
  type JobAccepted,
  type Operation,
  type OperationAccepted,
  type Plot,
  type Plots,
  type Proof,
  type TransferRequest,
  type Verification,
  type VerificationEvidence,
  type VerifyRequest,
} from './types';

export interface HttpAdapterConfig {
  baseUrl: string;
  demoSession: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

interface CallInit {
  method?: 'GET' | 'POST';
  actor?: DemoActor;
  body?: unknown;
  idempotencyKey?: string;
  session?: boolean;
  accept?: string;
  signal?: AbortSignal | undefined;
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function createHttpAdapter(config: HttpAdapterConfig): MrvApiClient {
  const baseUrl = config.baseUrl.replace(/\/+$/, '');
  if (!/\/api\/v1$/.test(baseUrl)) {
    throw new ApiError({ kind: 'contract', message: `API base URL must end with /api/v1, got "${config.baseUrl}"` });
  }
  const apiRoot = baseUrl.slice(0, -'/api/v1'.length);
  const timeoutMs = config.timeoutMs ?? 15000;
  const fetchImpl = config.fetchImpl ?? globalThis.fetch.bind(globalThis);

  async function send(path: string, init: CallInit): Promise<Response> {
    const headers: Record<string, string> = { Accept: init.accept ?? 'application/json' };
    if (init.session !== false) headers['X-Demo-Session'] = config.demoSession;
    if (init.actor) headers['X-Demo-Actor'] = init.actor;
    if (init.idempotencyKey) headers['Idempotency-Key'] = init.idempotencyKey;
    if (init.body !== undefined) headers['Content-Type'] = 'application/json';

    const timeout = AbortSignal.timeout(timeoutMs);
    const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
    const url = path.startsWith('/api/v1/') ? `${apiRoot}${path}` : `${baseUrl}${path}`;

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
      if (init.signal?.aborted) throw new ApiError({ kind: 'aborted', message: 'Запрос отменён' });
      if (timeout.aborted) {
        throw new ApiError({ kind: 'timeout', message: `Backend не ответил за ${Math.round(timeoutMs / 1000)} с` });
      }
      const apiError = toApiError(error);
      throw new ApiError({ kind: 'network', message: `Backend недоступен: ${apiError.message}` });
    }

    if (!response.ok) throw await readFailure(response);
    return response;
  }

  async function json<T>(path: string, init: CallInit = {}): Promise<T> {
    const response = await send(path, init);
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw new ApiError({ kind: 'contract', status: response.status, message: 'Backend вернул не-JSON ответ' });
    }
    if (typeof payload !== 'object' || payload === null) {
      throw new ApiError({ kind: 'contract', status: response.status, message: 'Backend вернул ответ не по схеме' });
    }
    return payload as T;
  }

  function mutation(opts: MutationOptions, actor: DemoActor, body: unknown): CallInit {
    return { method: 'POST', actor, body, idempotencyKey: opts.idempotencyKey, signal: opts.signal };
  }

  function statusPath(value: string, pattern: RegExp, prefix: string): string {
    if (pattern.test(value)) return value;
    if (UUID.test(value)) return `${prefix}${value}`;
    throw new ApiError({ kind: 'contract', message: `Недопустимый status URL/ID: ${value}` });
  }

  const seg = encodeURIComponent;

  return {
    kind: 'http',
    getHealth: (opts?: RequestOptions) => json<Health>('/health', { session: false, signal: opts?.signal }),
    listPlots: (opts) => json<Plots>('/plots', { signal: opts?.signal }),
    getPlot: (plotId, actor, opts) => json<Plot>(`/plots/${seg(plotId)}`, { actor, signal: opts?.signal }),
    startVerification: (plotId, actor, body: VerifyRequest, opts) =>
      json<JobAccepted>(`/plots/${seg(plotId)}/verify`, mutation(opts, actor, body)),
    getJob: (statusUrlOrId, opts) =>
      json<Job>(statusPath(statusUrlOrId, JOB_STATUS_URL, '/api/v1/jobs/'), { signal: opts?.signal }),
    getVerification: (id, opts) => json<Verification>(`/verifications/${seg(id)}`, { signal: opts?.signal }),
    getProof: (id, opts) => json<Proof>(`/verifications/${seg(id)}/proof`, { signal: opts?.signal }),
    getCanonicalEvidence: (id, opts) =>
      json<VerificationEvidence>(`/verifications/${seg(id)}/canonical`, { signal: opts?.signal }),
    getHistory: (plotId, opts) => json<History>(`/plots/${seg(plotId)}/history`, { signal: opts?.signal }),
    getCredits: (plotId, actor, opts) => json<Credits>(`/plots/${seg(plotId)}/credits`, { actor, signal: opts?.signal }),
    issueBatch: (plotId, actor, body: IssueRequest, opts) =>
      json<OperationAccepted>(`/plots/${seg(plotId)}/issue`, mutation(opts, actor, body)),
    buyCredits: (batchId, actor, body: BuyRequest, opts) =>
      json<OperationAccepted>(`/batches/${seg(batchId)}/buy`, mutation(opts, actor, body)),
    transferCredits: (batchId, actor, body: TransferRequest, opts) =>
      json<OperationAccepted>(`/batches/${seg(batchId)}/transfer`, mutation(opts, actor, body)),
    getOperation: (statusUrlOrId, opts) =>
      json<Operation>(statusPath(statusUrlOrId, OPERATION_STATUS_URL, '/api/v1/operations/'), { signal: opts?.signal }),
    listEvents: (query: EventsQuery, opts) => {
      const params = new URLSearchParams({ plot_id: query.plotId });
      if (query.cursor) params.set('cursor', query.cursor);
      if (query.limit !== undefined) params.set('limit', String(query.limit));
      return json<Events>(`/events?${params.toString()}`, { signal: opts?.signal });
    },
    getArtifact: async (artifactUrl, mediaType, opts): Promise<ArtifactPayload> => {
      if (!ARTIFACT_URL.test(artifactUrl)) {
        throw new ApiError({ kind: 'contract', message: `Артефакт разрешён только по artifacts[].url Backend: ${artifactUrl}` });
      }
      if (mediaType === 'application/geo+json') {
        const data = await json<GeoJSON.GeoJsonObject>(artifactUrl, {
          accept: 'application/geo+json, application/json',
          signal: opts?.signal,
        });
        return { kind: 'geojson', data, mediaType, release: () => undefined };
      }
      if (mediaType === 'image/png' || mediaType === 'image/webp') {
        const response = await send(artifactUrl, { accept: mediaType, signal: opts?.signal });
        const blob = await response.blob();
        const src = URL.createObjectURL(blob);
        return { kind: 'image', src, mediaType, release: () => URL.revokeObjectURL(src) };
      }
      throw new ApiError({ kind: 'contract', message: `Браузер не загружает ${mediaType} (GeoTIFF отображается только через превью)` });
    },
  };
}

async function readFailure(response: Response): Promise<ApiError> {
  const payload: unknown = await response.json().catch(() => null);
  if (isErrorEnvelope(payload)) {
    return new ApiError({
      kind: 'http',
      status: response.status,
      code: payload.error.code,
      message: payload.error.message,
      requestId: typeof payload.request_id === 'string' ? payload.request_id : null,
      details: payload.error.details ?? {},
    });
  }
  return new ApiError({
    kind: 'http',
    status: response.status,
    message: `HTTP ${response.status} без структурированной ошибки`,
  });
}
