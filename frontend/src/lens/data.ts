// Official case data from data/ — the only authoritative input the UI reads directly.
// Everything here is a metadata record shipped by the organisers (areas, scenes, fire events,
// baseline table, source registry, scenario parameters). Computed scientific values
// (stock, E, R, H, Q) never come from this module; they arrive through the adapter.

import areasCsv from '../../../data/areas.csv?raw';
import areasGeoJson from '../../../data/areas.geojson?raw';
import sampleRequestsGeoJson from '../../../data/sample_requests.geojson?raw';
import eventsCsv from '../../../data/events.csv?raw';
import scenesCsv from '../../../data/scenes.csv?raw';
import baselineCsv from '../../../data/methodology/baseline.csv?raw';
import parametersCsv from '../../../data/methodology/parameters.csv?raw';
import sourcesCsv from '../../../data/sources.csv?raw';
import { parseCsv, parseGeoJsonText } from './csv';
import type { CatalogArea, CatalogSampleRequest, Geometry, PriceScenario } from './types';

export interface SceneRecord {
  scene_key: string;
  aoi_id: string;
  item_id: string;
  datetime_utc: string;
  year: number;
  collection: string;
  processing_baseline: string;
  source_scene_cloud_percent: number | null;
  scl_valid_fraction: number | null;
  selection_role: string;
  source_id: 'S2_L2A';
}

export interface EventRecord {
  event_id: string;
  aoi_id: string;
  evidence_type: string;
  cause_supported: string;
  date_min_product: string;
  date_max_product: string;
  burned_pixel_centers_in_aoi: number | null;
  all_pixel_centers_in_aoi: number | null;
  date_uncertainty_days_min: number | null;
  date_uncertainty_days_max: number | null;
  source_id: string;
  context_url: string;
  limitations: string;
}

export interface BaselineRow {
  baseline_id: string;
  aoi_id: string;
  year_start: number;
  year_end: number;
  pool: string;
  historical_rate_tc_ha_yr: number | null;
  baseline_stock_start_tc_ha: number | null;
  baseline_stock_end_tc_ha: number | null;
  baseline_delta_tc_ha: number | null;
  kind: string;
  history_product: string;
}

export interface ParameterRow {
  parameter: string;
  value: string;
  unit: string;
  kind: string;
  source_id: string;
  locator: string;
  applicability: string;
}

export interface SourceRecord {
  source_id: string;
  title: string;
  version: string;
  license: string;
  attribution: string;
  accessed: string;
  product: string;
  primary_url: string;
  doi: string;
  license_url: string;
  limitations: string;
}

function num(value: string | undefined): number | null {
  if (value === undefined) return null;
  const trimmed = value.trim();
  if (trimmed === '') return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

let scenesCache: SceneRecord[] | null = null;
export function caseScenes(): SceneRecord[] {
  scenesCache ??= parseCsv(scenesCsv).map((row) => ({
    scene_key: row.scene_key ?? '',
    aoi_id: row.aoi_id ?? '',
    item_id: row.item_id ?? '',
    datetime_utc: row.datetime_utc ?? '',
    year: num(row.year) ?? 0,
    collection: row.collection ?? '',
    processing_baseline: row.processing_baseline ?? '',
    source_scene_cloud_percent: num(row.source_scene_cloud_percent),
    scl_valid_fraction: num(row.scl_4_5_6_7_fraction_crop),
    selection_role: row.selection_role ?? '',
    source_id: 'S2_L2A' as const,
  }));
  return scenesCache;
}

export function scenesForAoi(aoiId: string | null): SceneRecord[] {
  if (!aoiId) return [];
  return caseScenes()
    .filter((scene) => scene.aoi_id === aoiId)
    .sort((a, b) => a.datetime_utc.localeCompare(b.datetime_utc));
}

/** Scenes inside the requested period, so the optical panel never shows dates outside the request. */
export function scenesInPeriod(aoiId: string | null, yearStart: number, yearEnd: number): SceneRecord[] {
  return scenesForAoi(aoiId).filter((scene) => scene.year >= yearStart && scene.year <= yearEnd);
}

let eventsCache: EventRecord[] | null = null;
export function caseEvents(): EventRecord[] {
  eventsCache ??= parseCsv(eventsCsv).map((row) => ({
    event_id: row.event_id ?? '',
    aoi_id: row.aoi_id ?? '',
    evidence_type: row.evidence_type ?? '',
    cause_supported: row.cause_supported ?? '',
    date_min_product: row.date_min_product ?? '',
    date_max_product: row.date_max_product ?? '',
    burned_pixel_centers_in_aoi: num(row.burned_pixel_centers_in_aoi),
    all_pixel_centers_in_aoi: num(row.all_pixel_centers_in_aoi),
    date_uncertainty_days_min: num(row.date_uncertainty_days_min),
    date_uncertainty_days_max: num(row.date_uncertainty_days_max),
    source_id: row.source_id ?? '',
    context_url: row.context_url ?? '',
    limitations: row.limitations ?? '',
  }));
  return eventsCache;
}

export function eventById(eventId: string | null): EventRecord | null {
  if (!eventId) return null;
  return caseEvents().find((event) => event.event_id === eventId) ?? null;
}

export function eventsForAoi(aoiId: string | null): EventRecord[] {
  if (!aoiId) return [];
  return caseEvents().filter((event) => event.aoi_id === aoiId);
}

let baselineCache: BaselineRow[] | null = null;
export function caseBaseline(): BaselineRow[] {
  baselineCache ??= parseCsv(baselineCsv).map((row) => ({
    baseline_id: row.baseline_id ?? '',
    aoi_id: row.aoi_id ?? '',
    year_start: num(row.year_start) ?? 0,
    year_end: num(row.year_end) ?? 0,
    pool: row.pool ?? '',
    historical_rate_tc_ha_yr: num(row.historical_rate_tc_ha_yr),
    baseline_stock_start_tc_ha: num(row.baseline_stock_start_tc_ha),
    baseline_stock_end_tc_ha: num(row.baseline_stock_end_tc_ha),
    baseline_delta_tc_ha: num(row.baseline_delta_tc_ha),
    kind: row.kind ?? '',
    history_product: row.history_product ?? '',
  }));
  return baselineCache;
}

export function baselineForAoi(aoiId: string | null): BaselineRow[] {
  if (!aoiId) return [];
  return caseBaseline()
    .filter((row) => row.aoi_id === aoiId)
    .sort((a, b) => a.year_start - b.year_start);
}

/** Baseline stock per hectare for a year, straight from the official table (no interpolation). */
export function baselineStockAtYear(aoiId: string | null, year: number): number | null {
  const rows = baselineForAoi(aoiId);
  const start = rows.find((row) => row.year_start === year);
  if (start) return start.baseline_stock_start_tc_ha;
  const end = rows.find((row) => row.year_end === year);
  return end ? end.baseline_stock_end_tc_ha : null;
}

let parametersCache: ParameterRow[] | null = null;
export function caseParameters(): ParameterRow[] {
  parametersCache ??= parseCsv(parametersCsv).map((row) => ({
    parameter: row.parameter ?? '',
    value: row.value ?? '',
    unit: row.unit ?? '',
    kind: row.kind ?? '',
    source_id: row.source_id ?? '',
    locator: row.locator ?? '',
    applicability: row.applicability ?? '',
  }));
  return parametersCache;
}

export function parameterValue(name: string): ParameterRow | null {
  return caseParameters().find((row) => row.parameter === name) ?? null;
}

/** Price scenarios are case parameters, not market data: they are read, never invented. */
export function casePrices(): PriceScenario[] {
  const labels: Record<string, string> = { price_low: 'Низкая', price_base: 'Базовая', price_high: 'Высокая' };
  return caseParameters()
    .filter((row) => row.parameter.startsWith('price_'))
    .map((row) => ({
      id: row.parameter,
      label: labels[row.parameter] ?? row.parameter,
      rub_per_unit: num(row.value) ?? 0,
    }));
}

let sourcesCache: SourceRecord[] | null = null;
export function caseSources(): SourceRecord[] {
  sourcesCache ??= parseCsv(sourcesCsv).map((row) => ({
    source_id: row.source_id ?? '',
    title: row.product ?? '',
    product: row.product ?? '',
    version: row.version ?? '',
    license: row.license_url ?? row.redistribution_basis ?? '',
    attribution: row.required_attribution ?? '',
    accessed: row.access_date ?? '',
    primary_url: row.primary_url ?? '',
    doi: row.doi ?? '',
    license_url: row.license_url ?? '',
    limitations: row.limitations ?? '',
  }));
  return sourcesCache;
}

export function sourcesByIds(ids: readonly string[]): SourceRecord[] {
  const wanted = new Set(ids);
  return caseSources().filter((source) => wanted.has(source.source_id));
}

interface GeoFeature {
  id?: string;
  properties?: Record<string, unknown>;
  geometry?: Geometry;
}

function features(raw: string): GeoFeature[] {
  return parseGeoJsonText<{ features?: GeoFeature[] }>(raw).features ?? [];
}

export function geometryForAoi(aoiId: string): Geometry | null {
  for (const feature of features(areasGeoJson)) {
    const props = feature.properties ?? {};
    if (props.aoi_id === aoiId || feature.id === aoiId) return feature.geometry ?? null;
  }
  return null;
}

/** Supplied areas exactly as the catalog of the service describes them, read from data/. */
export function parsedAreas(): CatalogArea[] {
  return parseCsv(areasCsv).map((row) => {
    const aoiId = row.aoi_id ?? '';
    const start = num(row.analysis_start_year) ?? 2019;
    const end = num(row.analysis_end_year) ?? 2024;
    const years: number[] = [];
    for (let year = start; year <= end; year += 1) years.push(year);
    return {
      aoi_id: aoiId,
      name: row.name ?? '',
      region: row.region ?? '',
      area_ha: num(row.area_ha) ?? 0,
      analysis_start_year: start,
      analysis_end_year: end,
      selection_role: row.selection_role ?? '',
      project_status: row.project_status ?? '',
      baseline_id: row.baseline_id ?? '',
      bbox: [num(row.bbox_west) ?? 0, num(row.bbox_south) ?? 0, num(row.bbox_east) ?? 0, num(row.bbox_north) ?? 0],
      geometry: geometryForAoi(aoiId) ?? { type: 'Polygon', coordinates: [] },
      available_years: years,
    };
  });
}

export function sampleRequests(): CatalogSampleRequest[] {
  return features(sampleRequestsGeoJson).map((feature) => {
    const props = feature.properties ?? {};
    return {
      request_id: String(props.request_id ?? feature.id ?? ''),
      parent_aoi_id: props.parent_aoi_id === undefined ? null : String(props.parent_aoi_id),
      year_start: Number(props.year_start ?? 2020),
      year_end: Number(props.year_end ?? 2024),
      area_ha: Number(props.area_ha ?? 0),
      purpose: String(props.purpose ?? ''),
      baseline_rule: String(props.baseline_rule ?? ''),
      geometry: feature.geometry ?? { type: 'Polygon', coordinates: [] },
    };
  });
}
