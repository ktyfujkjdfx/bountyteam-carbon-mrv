// The one boundary the Carbon Lens screens know. Both the live service and the labelled offline set
// implement it, and nothing above this line knows which one answered.

import type {
  Analysis,
  AnalysisAccepted,
  AnalysisRequestBody,
  AnalysisResult,
  AreaMeasurement,
  Artifact,
  Catalog,
  EvidenceWarning,
  Geometry,
  Proof,
  Report,
} from './types';

export class LensError extends Error {
  readonly code: string;
  readonly status: number | null;
  readonly detail: string | null;
  readonly details: Record<string, unknown>;
  constructor(code: string, message: string, options: { status?: number | null; detail?: string | null; details?: Record<string, unknown> } = {}) {
    super(message);
    this.name = 'LensError';
    this.code = code;
    this.status = options.status ?? null;
    this.detail = options.detail ?? null;
    this.details = options.details ?? {};
  }
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

export interface SubmitOptions {
  idempotencyKey: string;
  signal?: AbortSignal | undefined;
  /** Offline set only: which labelled vector to answer with. Ignored by the live service. */
  scenario?: string | undefined;
}

export interface LensApiClient {
  readonly kind: 'fixture' | 'http';
  getCatalog(signal?: AbortSignal): Promise<Catalog>;
  measureArea(geometry: Geometry, signal?: AbortSignal): Promise<AreaMeasurement>;
  createAnalysis(body: AnalysisRequestBody, options: SubmitOptions): Promise<AnalysisAccepted>;
  getAnalysis(analysisId: string, signal?: AbortSignal): Promise<Analysis>;
  getProof(analysisId: string, signal?: AbortSignal): Promise<Proof>;
  getReport(analysisId: string, format: 'json', signal?: AbortSignal): Promise<Report>;
  getReportHtml(analysisId: string, signal?: AbortSignal): Promise<string>;
  getArtifact(artifact: Artifact, signal?: AbortSignal): Promise<ArtifactPayload>;
}

export function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

export function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

/**
 * Warnings arrive either as the reviewed object or, on a deployment that has not shipped the typed
 * form yet, as a bare sentence. Both are shown; a sentence simply has no code and no severity of its
 * own, and the UI says so rather than inventing one.
 */
export function normalizeWarnings(value: unknown): EvidenceWarning[] {
  return asArray(value).map((entry) => {
    if (typeof entry === 'string') {
      return { code: 'UNSTRUCTURED_WARNING', severity: 'WARNING', message: entry, details: {} };
    }
    const record = asRecord(entry);
    return {
      code: typeof record.code === 'string' ? record.code : 'UNSTRUCTURED_WARNING',
      severity: typeof record.severity === 'string' ? record.severity : 'WARNING',
      message: typeof record.message === 'string' ? record.message : JSON.stringify(record),
      details: asRecord(record.details),
    };
  });
}

/**
 * Keep the payload as the service sent it and only guarantee that the containers the screens iterate
 * over exist. Unknown enum values are passed through untouched so they reach the neutral UNKNOWN
 * fallback instead of being mapped onto a known status.
 */
export function normalizeResult(payload: unknown): AnalysisResult {
  const record = asRecord(payload);
  const evidence = asRecord(record.evidence);
  return {
    ...record,
    timeline: asArray(record.timeline),
    zones: asArray(record.zones).map((zone) => ({ ...asRecord(zone), evidence_refs: asArray(asRecord(zone).evidence_refs) })),
    sources: asArray(record.sources),
    artifacts: asArray(record.artifacts),
    limitations: asArray(record.limitations).filter((item): item is string => typeof item === 'string'),
    notes: asArray(record.notes).filter((item): item is string => typeof item === 'string'),
    evidence: {
      ...evidence,
      scenes: asArray(evidence.scenes),
      warnings: normalizeWarnings(evidence.warnings),
    },
    claim: { ...asRecord(record.claim), mismatch_reasons: asArray(asRecord(record.claim).mismatch_reasons) },
    uncertainty: { ...asRecord(record.uncertainty), sensitivity: asArray(asRecord(record.uncertainty).sensitivity) },
  } as unknown as AnalysisResult;
}

export function normalizeAnalysis(payload: unknown): Analysis {
  const record = asRecord(payload);
  const result = record.result === null || record.result === undefined ? null : normalizeResult(record.result);
  return { ...record, result } as unknown as Analysis;
}

export function isTerminal(state: string): boolean {
  return state === 'SUCCEEDED' || state === 'FAILED';
}
