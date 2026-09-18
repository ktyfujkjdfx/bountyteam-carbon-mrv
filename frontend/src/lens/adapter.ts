import areasCsv from '../../../data/areas.csv?raw';
import areasGeoJson from '../../../data/areas.geojson?raw';
import sampleRequests from '../../../data/sample_requests.geojson?raw';
import { parseCsv, parseGeoJsonText } from './csv';
import { eventsForAoi, scenesInPeriod } from './data';
import { withContentHash } from './passport';
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

export { parseCsv };

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
  return parseGeoJsonText<{ features?: GeoFeature[] }>(raw).features ?? [];
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

function bboxOf(geometry: LensGeometry): { west: number; south: number; east: number; north: number } | null {
  const points = rings(geometry).flat();
  if (points.length === 0) return null;
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const point of points) {
    const [lon, lat] = point;
    if (typeof lon !== 'number' || typeof lat !== 'number') continue;
    west = Math.min(west, lon);
    east = Math.max(east, lon);
    south = Math.min(south, lat);
    north = Math.max(north, lat);
  }
  return Number.isFinite(west) && Number.isFinite(south) ? { west, south, east, north } : null;
}

function box(west: number, south: number, east: number, north: number): LensGeometry {
  return {
    type: 'Polygon',
    coordinates: [
      [
        [west, south],
        [east, south],
        [east, north],
        [west, north],
        [west, south],
      ],
    ],
  };
}

/**
 * Schematic outline for a zone of a labelled fixture: a deterministic cell inside the request contour.
 * It shows where zone selection and highlighting happen; it is not a detection result and says so
 * through LensZone.geometry_note.
 */
export function schematicZoneGeometry(geometry: LensGeometry, index: number, total: number): LensGeometry | null {
  const bounds = bboxOf(geometry);
  if (!bounds || total <= 0) return null;
  const width = bounds.east - bounds.west;
  const height = bounds.north - bounds.south;
  const step = width / (total + 1);
  const centreLon = bounds.west + step * (index + 1);
  const centreLat = bounds.south + height * (index % 2 === 0 ? 0.42 : 0.62);
  const halfLon = Math.min(step * 0.34, width * 0.18);
  const halfLat = height * 0.12;
  return box(centreLon - halfLon, centreLat - halfLat, centreLon + halfLon, centreLat + halfLat);
}

/** Schematic strip standing for the part of the request without numeric biomass coverage. */
export function coverageGapGeometry(geometry: LensGeometry, missingFraction: number): LensGeometry | null {
  const bounds = bboxOf(geometry);
  if (!bounds || !(missingFraction > 0)) return null;
  const width = bounds.east - bounds.west;
  const cut = Math.min(0.9, missingFraction) * width;
  return box(bounds.east - cut, bounds.south, bounds.east, bounds.north);
}

export function opticalContextFor(request: LensRequest): LensResult['optical'] {
  const scenes = scenesInPeriod(request.aoi_id ?? request.parent_aoi_id, request.year_start, request.year_end);
  return {
    scene_keys: scenes.map((scene) => scene.scene_key),
    note:
      scenes.length === 0
        ? 'Для выбранной территории и периода в data/scenes.csv нет сцен Sentinel-2.'
        : 'Метаданные сцен — официальная таблица data/scenes.csv; пригодность оценивается по доле классов SCL 4–7.',
  };
}

/**
 * Map layers with an explicit availability per layer: a layer the service cannot supply is reported as
 * "нет данных" with a reason, never silently omitted so the map looks clean.
 */
export function buildLayers(result: LensResult, kind: 'fixture' | 'http'): LensResult['layers'] {
  const geometry = result.request.geometry;
  const zonesWithGeometry = result.zones.filter((z) => z.geometry !== null);
  const biomass = result.coverage.find((axis) => axis.id === 'BIOMASS_CCI');
  const missingFraction = biomass?.covered_fraction === null || biomass?.covered_fraction === undefined ? 0 : 1 - biomass.covered_fraction;
  const gap = missingFraction > 0.0001 ? coverageGapGeometry(geometry, missingFraction) : null;
  const optical = result.coverage.find((axis) => axis.id === 'OPTICAL_PAIRED_VALID');
  const events = eventsForAoi(result.request.aoi_id ?? result.request.parent_aoi_id);
  const preview = result.artifacts.find((artifact) => artifact.role.includes('preview')) ?? null;

  return [
    {
      layer_id: 'AOI_CONTOUR',
      label: 'Контур запроса',
      availability: 'AVAILABLE',
      unit: null,
      observed_at: null,
      resolution_m: null,
      legend: [{ swatch: 'contour', label: 'Границы запроса (WGS84)' }],
      note: 'Геометрия из data/ или заданная пользователем.',
      source_id: 'CASE_RULES_V1',
      artifact_id: null,
      geometry: null,
    },
    {
      layer_id: 'CHANGE_ZONES',
      label: 'Зоны изменений',
      availability: zonesWithGeometry.length > 0 ? 'AVAILABLE' : 'NO_DATA',
      unit: 'т C',
      observed_at: result.zones[0]?.date_max ?? null,
      resolution_m: null,
      legend: [
        { swatch: 'zone-supported', label: 'Причина подтверждена внешним продуктом' },
        { swatch: 'zone-unknown', label: 'Причина не установлена' },
      ],
      note:
        zonesWithGeometry.length > 0
          ? 'Схематические контуры из помеченного набора: положение условное, статус причины — из результата.'
          : 'Сервис не вернул зоны изменений для этого запроса.',
      source_id: null,
      artifact_id: null,
      geometry: null,
    },
    {
      layer_id: 'COVERAGE_GAP',
      label: 'Пропуски числового покрытия',
      availability: gap ? 'AVAILABLE' : 'NO_DATA',
      unit: 'доля площади',
      observed_at: null,
      resolution_m: null,
      legend: [{ swatch: 'gap', label: 'Нет числовых данных биомассы и SD' }],
      note: gap
        ? `Схематически показана площадь без числового покрытия (${biomass?.missing_area_ha ?? '—'} га).`
        : 'Пропусков числового покрытия в этом результате нет.',
      source_id: 'CCI_V7',
      artifact_id: null,
      geometry: gap,
    },
    {
      layer_id: 'OPTICAL_QUALITY',
      label: 'Оптическое качество (облака, тени, снег)',
      availability: 'NO_DATA',
      unit: 'доля пригодных пикселей',
      observed_at: null,
      resolution_m: 20,
      legend: [{ swatch: 'optics', label: 'Маска SCL по сцене' }],
      note:
        optical && optical.covered_fraction !== null
          ? `Растровая маска в этом режиме не выдаётся. Табличная пригодность: ${Math.round(optical.covered_fraction * 100)} % площади на обе даты, метаданные сцен — в разделе «Наблюдения».`
          : 'Растровая маска в этом режиме не выдаётся; метаданные сцен — в разделе «Наблюдения».',
      source_id: 'S2_L2A',
      artifact_id: null,
      geometry: null,
    },
    {
      layer_id: 'FIRE_EVIDENCE',
      label: 'Продукт гарей MODIS',
      availability: 'NO_DATA',
      unit: 'дата горения',
      observed_at: events[0]?.date_min_product ?? null,
      resolution_m: 463,
      legend: [{ swatch: 'fire', label: 'Пиксели с признаком горения' }],
      note:
        events.length > 0
          ? `Растр MCD64A1 в браузер не выдаётся. Для территории есть официальная запись события ${events[0]?.event_id ?? ''} — см. «Наблюдения».`
          : 'Записей о событиях для этой территории в data/events.csv нет.',
      source_id: 'MODIS_MCD64A1_061',
      artifact_id: null,
      geometry: null,
    },
    {
      layer_id: 'STOCK_PREVIEW',
      label: 'Превью запаса и изменения',
      availability: preview ? 'AVAILABLE' : kind === 'fixture' ? 'NOT_IN_THIS_MODE' : 'NO_DATA',
      unit: 'т C/га',
      observed_at: null,
      resolution_m: preview?.resolution_m ?? null,
      legend: [{ swatch: 'stock', label: 'Запас углерода по году' }],
      note: preview
        ? 'Превью загружается по artifacts[].url и проверяется по sha256 перед показом.'
        : kind === 'fixture'
          ? 'В режиме помеченных данных растровых превью нет: подключается вместе с Backend.'
          : 'Сервис не вернул артефакт превью для этого результата.',
      source_id: 'CCI_V7',
      artifact_id: preview?.artifact_id ?? null,
      geometry: null,
    },
  ];
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
      const zones = base.zones.map((zone, index) => ({
        ...zone,
        geometry: schematicZoneGeometry(request.geometry, index, base.zones.length),
      }));
      const withContext: LensResult = {
        ...base,
        zones,
        optical: opticalContextFor(request),
        claim: claimComparison(base, request, opts.scenario),
      };
      // The stand-in service fixes the content hash the way the real one must: over its own payload.
      const result = await withContentHash({ ...withContext, layers: buildLayers(withContext, 'fixture') });
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
