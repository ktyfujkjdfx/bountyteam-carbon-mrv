import areasCsv from '../../../data/areas.csv?raw';
import areasGeoJson from '../../../data/areas.geojson?raw';
import sampleRequests from '../../../data/sample_requests.geojson?raw';
import { buildFixtureResult, SCENARIO_DEFAULTS, type FixtureScenarioId } from './fixtures';
import {
  LENS_MAX_AREA_HA,
  LENS_YEAR_MAX,
  LENS_YEAR_MIN,
  type LensArea,
  type LensGeometry,
  type LensJob,
  type LensRequest,
  type LensResult,
} from './types';

export class LensError extends Error {
  readonly code: string;
  readonly detail: string | null;
  constructor(code: string, message: string, detail: string | null = null) {
    super(message);
    this.name = 'LensError';
    this.code = code;
    this.detail = detail;
  }
}

export interface LensSubmitOptions {
  scenario: FixtureScenarioId;
  idempotencyKey: string;
  signal?: AbortSignal | undefined;
}

// The only Carbon Lens boundary the screens know about. G0 replaces the implementation, not this shape.
export interface LensApiClient {
  readonly kind: 'fixture' | 'http';
  listAreas(): Promise<LensArea[]>;
  getAreaGeometry(aoiId: string): Promise<LensGeometry>;
  measureArea(geometry: LensGeometry): Promise<number>;
  submitAnalysis(request: LensRequest, options: LensSubmitOptions): Promise<LensJob>;
  getJob(jobId: string, signal?: AbortSignal): Promise<LensJob>;
  getResult(resultId: string, signal?: AbortSignal): Promise<LensResult>;
}

function stripBom(text: string): string {
  return text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
}

export function parseCsv(text: string): Record<string, string>[] {
  const lines = stripBom(text).trim().split(/\r?\n/);
  const header = (lines.shift() ?? '').split(',');
  return lines.map((line) => {
    const cells: string[] = [];
    let cell = '';
    let quoted = false;
    for (const char of line) {
      if (char === '"') quoted = !quoted;
      else if (char === ',' && !quoted) {
        cells.push(cell);
        cell = '';
      } else cell += char;
    }
    cells.push(cell);
    return Object.fromEntries(header.map((name, i) => [name, cells[i] ?? '']));
  });
}

export function parsedAreas(): LensArea[] {
  return parseCsv(areasCsv).map((row) => ({
    aoi_id: row.aoi_id ?? '',
    name: row.name ?? '',
    region: row.region ?? '',
    area_ha: Number(row.area_ha),
    analysis_start_year: Number(row.analysis_start_year),
    analysis_end_year: Number(row.analysis_end_year),
    selection_role: row.selection_role ?? '',
    baseline_id: row.baseline_id ?? '',
    bbox: [Number(row.bbox_west), Number(row.bbox_south), Number(row.bbox_east), Number(row.bbox_north)],
  }));
}

interface GeoFeature {
  properties?: Record<string, unknown>;
  id?: string;
  geometry?: LensGeometry;
}

function featureCollection(raw: string): GeoFeature[] {
  const parsed = JSON.parse(stripBom(raw)) as { features?: GeoFeature[] };
  return parsed.features ?? [];
}

export function areaGeometryFromData(aoiId: string): LensGeometry | null {
  for (const feature of featureCollection(areasGeoJson)) {
    const props = feature.properties ?? {};
    if (props.aoi_id === aoiId || feature.id === aoiId) return feature.geometry ?? null;
  }
  return null;
}

export function sampleRequestFeature(requestId: string): { geometry: LensGeometry; properties: Record<string, unknown> } | null {
  for (const feature of featureCollection(sampleRequests)) {
    const props = feature.properties ?? {};
    if (props.request_id === requestId || feature.id === requestId) {
      return feature.geometry ? { geometry: feature.geometry, properties: props } : null;
    }
  }
  return null;
}

function rings(geometry: LensGeometry): number[][][] {
  return geometry.type === 'Polygon' ? (geometry.coordinates as number[][][]) : (geometry.coordinates as number[][][][]).flat();
}

// Spherical polygon area; the stand-in for the server-side area the real contract returns.
export function approximateAreaHa(geometry: LensGeometry): number {
  const R = 6378137;
  let total = 0;
  for (const ring of rings(geometry)) {
    let sum = 0;
    for (let i = 0; i < ring.length - 1; i += 1) {
      const [lon1 = 0, lat1 = 0] = ring[i] ?? [];
      const [lon2 = 0, lat2 = 0] = ring[i + 1] ?? [];
      sum += ((lon2 - lon1) * Math.PI) / 180 * (2 + Math.sin((lat1 * Math.PI) / 180) + Math.sin((lat2 * Math.PI) / 180));
    }
    total += Math.abs((sum * R * R) / 2);
  }
  return total / 10_000;
}

export function validateRequest(request: LensRequest, areaHa: number): void {
  const { year_start: start, year_end: end } = request;
  if (!Number.isInteger(start) || !Number.isInteger(end)) throw new LensError('INVALID_PERIOD', 'Годы должны быть целыми числами');
  if (start < LENS_YEAR_MIN || end > LENS_YEAR_MAX) {
    throw new LensError('INVALID_PERIOD', `Период вне диапазона данных ${LENS_YEAR_MIN}–${LENS_YEAR_MAX}`);
  }
  if (end <= start) throw new LensError('INVALID_PERIOD', 'Конечный год должен быть больше начального');
  if (!(areaHa > 0)) throw new LensError('INVALID_GEOMETRY', 'Площадь контура должна быть больше нуля');
  if (areaHa > LENS_MAX_AREA_HA) {
    throw new LensError('AREA_TOO_LARGE', `Площадь ${areaHa.toFixed(1)} га превышает предел ${LENS_MAX_AREA_HA} га`);
  }
  if (request.claimed_units !== null && (!Number.isFinite(request.claimed_units) || request.claimed_units < 0)) {
    throw new LensError('INVALID_CLAIM', 'Заявленные единицы должны быть неотрицательным числом');
  }
}

function claimComparison(result: LensResult, request: LensRequest, scenario: FixtureScenarioId): LensResult['claim'] {
  const claimed = request.claimed_units;
  if (claimed === null) {
    return { status: 'NOT_PROVIDED', claimed_units: null, gap_units: null, comparable: false, reasons: [], scope_note: 'Заявление не введено.' };
  }
  if (scenario === 'UNKNOWN_DRIFT') return { ...result.claim, claimed_units: claimed };
  const [defaultStart, defaultEnd] = SCENARIO_DEFAULTS[scenario].years;
  const scopeNote = 'Сравнение возможно только при совпадении контура, периода, пула и единиц.';
  if (request.year_start !== defaultStart || request.year_end !== defaultEnd) {
    return {
      status: 'NOT_COMPARABLE',
      claimed_units: claimed,
      gap_units: null,
      comparable: false,
      reasons: [`Заявление относится к периоду ${defaultStart}–${defaultEnd}, запрос — к ${request.year_start}–${request.year_end}.`],
      scope_note: scopeNote,
    };
  }
  const q = result.units.q;
  if (q === null) {
    return {
      status: 'UNASSESSABLE',
      claimed_units: claimed,
      gap_units: null,
      comparable: false,
      reasons: ['Расчёт единиц недоступен, сравнивать не с чем.'],
      scope_note: scopeNote,
    };
  }
  const gap = Math.max(0, claimed - q);
  if (q === 0) {
    return { status: 'NOT_SUPPORTED_BY_CASE', claimed_units: claimed, gap_units: gap, comparable: true, reasons: ['Расчёт по условиям кейса даёт 0 единиц.'], scope_note: scopeNote };
  }
  if (claimed <= q) {
    return { status: 'SUPPORTED_BY_CASE', claimed_units: claimed, gap_units: 0, comparable: true, reasons: [], scope_note: scopeNote };
  }
  return {
    status: 'PARTIALLY_SUPPORTED_BY_CASE',
    claimed_units: claimed,
    gap_units: gap,
    comparable: true,
    reasons: [`Заявлено ${claimed}, расчёт по условиям кейса даёт ${q}.`],
    scope_note: scopeNote,
  };
}

export interface FixtureLensOptions {
  now?: () => number;
  queuedMs?: number;
  runningMs?: number;
}

interface StoredJob {
  job: LensJob;
  createdAt: number;
  result: LensResult;
}

export function createFixtureLensClient(options: FixtureLensOptions = {}): LensApiClient {
  const now = options.now ?? (() => Date.now());
  const queuedMs = options.queuedMs ?? 500;
  const runningMs = options.runningMs ?? 1200;
  const jobs = new Map<string, StoredJob>();
  const results = new Map<string, LensResult>();
  const idempotency = new Map<string, string>();
  let counter = 0;

  const settle = () => {
    const t = now();
    for (const stored of jobs.values()) {
      if (stored.job.state === 'SUCCEEDED' || stored.job.state === 'FAILED') continue;
      const elapsed = t - stored.createdAt;
      if (elapsed >= queuedMs + runningMs) {
        stored.job = { ...stored.job, state: 'SUCCEEDED', result_id: stored.result.passport.calculation_id };
      } else if (elapsed >= queuedMs) {
        stored.job = { ...stored.job, state: 'RUNNING' };
      }
    }
  };

  const tick = async (signal?: AbortSignal) => {
    await Promise.resolve();
    if (signal?.aborted) throw new LensError('ABORTED', 'Запрос отменён');
    settle();
  };

  return {
    kind: 'fixture',
    async listAreas() {
      await tick();
      return parsedAreas();
    },
    async getAreaGeometry(aoiId) {
      await tick();
      const geometry = areaGeometryFromData(aoiId);
      if (!geometry) throw new LensError('AOI_NOT_FOUND', `Геометрия участка ${aoiId} не найдена в data/areas.geojson`);
      return geometry;
    },
    async measureArea(geometry) {
      await tick();
      return approximateAreaHa(geometry);
    },
    async submitAnalysis(request, opts) {
      await tick(opts.signal);
      const areaHa = approximateAreaHa(request.geometry);
      validateRequest(request, areaHa);
      const existing = idempotency.get(opts.idempotencyKey);
      if (existing) {
        const stored = jobs.get(existing);
        if (stored) return structuredClone(stored.job);
      }
      counter += 1;
      const jobId = `fixture-job-${counter}`;
      const base = buildFixtureResult(opts.scenario, request, Number(areaHa.toFixed(4)));
      const result: LensResult = { ...base, claim: claimComparison(base, request, opts.scenario) };
      results.set(result.passport.calculation_id, result);
      const job: LensJob = { job_id: jobId, state: 'QUEUED', status_url: `/api/v2/lens/jobs/${jobId}`, result_id: null, error: null };
      jobs.set(jobId, { job, createdAt: now(), result });
      idempotency.set(opts.idempotencyKey, jobId);
      return structuredClone(job);
    },
    async getJob(jobId, signal) {
      await tick(signal);
      const stored = jobs.get(jobId);
      if (!stored) throw new LensError('JOB_NOT_FOUND', 'Задание не найдено');
      return structuredClone(stored.job);
    },
    async getResult(resultId, signal) {
      await tick(signal);
      const result = results.get(resultId);
      if (!result) throw new LensError('RESULT_NOT_FOUND', 'Результат не найден');
      return structuredClone(result);
    },
  };
}
