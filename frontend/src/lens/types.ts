// Provisional Carbon Lens v2 shapes for F1. Backend owns the real contract in G0 (feat/lens-g0-contracts);
// after G0 only src/lens/adapter.ts and generated types change, not the screen components.

export type LensJobState = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED';
export type CalculationStatus = 'AVAILABLE' | 'UNAVAILABLE';
export type EvidenceStatus = 'SUFFICIENT' | 'REVIEW_REQUIRED' | 'INSUFFICIENT';
export type ClaimStatus =
  | 'NOT_PROVIDED'
  | 'NOT_COMPARABLE'
  | 'SUPPORTED_BY_CASE'
  | 'PARTIALLY_SUPPORTED_BY_CASE'
  | 'NOT_SUPPORTED_BY_CASE'
  | 'UNASSESSABLE';

export type ZeroUnitsReason = 'NON_POSITIVE_RELATIVE_RESULT' | 'UNCERTAINTY_TOO_HIGH' | 'ROUNDED_TO_ZERO';
export type UnitsUnavailableReason =
  | 'INCOMPLETE_BIOMASS_COVERAGE'
  | 'BASELINE_NOT_COVERED'
  | 'NO_COMPARABLE_OBSERVATIONS'
  | 'INVALID_REQUEST';

export type CauseStatus = 'SUPPORTED' | 'NOT_ESTABLISHED';

export interface LensArea {
  aoi_id: string;
  name: string;
  region: string;
  area_ha: number;
  analysis_start_year: number;
  analysis_end_year: number;
  selection_role: string;
  baseline_id: string;
  bbox: [number, number, number, number];
}

export interface LensGeometry {
  type: 'Polygon' | 'MultiPolygon';
  coordinates: number[][][] | number[][][][];
}

export interface LensRequest {
  aoi_id: string | null;
  parent_aoi_id: string | null;
  geometry: LensGeometry;
  year_start: number;
  year_end: number;
  claimed_units: number | null;
}

export interface FixtureLabel {
  kind: 'DOC_EXAMPLE' | 'UNIT_TEST_VECTOR';
  label: string;
  note: string;
}

export interface CoverageAxis {
  id: 'BIOMASS_CCI' | 'BASELINE_TABLE' | 'OPTICAL_PAIRED_VALID';
  label: string;
  covered_fraction: number | null;
  missing_area_ha: number | null;
  note: string;
}

export interface StockResult {
  pool: string;
  mean_start_tc_ha: number | null;
  mean_end_tc_ha: number | null;
  total_start_tc: number | null;
  total_end_tc: number | null;
  delta_tc: number | null;
  e_tco2e: number | null;
  e_tco2e_ha_yr: number | null;
  year_start: number;
  year_end: number;
}

export interface BaselineResult {
  baseline_id: string;
  kind: string;
  e_base_tco2e: number | null;
  stock_start_tc_ha: number | null;
  stock_end_tc_ha: number | null;
  applied_to_area_ha: number | null;
  parent_aoi_id: string | null;
  note: string;
}

export interface UncertaintyResult {
  lower_tco2e: number | null;
  upper_tco2e: number | null;
  h_tco2e: number | null;
  method: string;
  is_probabilistic: boolean;
  assumptions: string[];
}

export interface UnitsResult {
  status: CalculationStatus;
  q: number | null;
  reason: ZeroUnitsReason | UnitsUnavailableReason | null;
  reason_detail: string | null;
  r_tco2e: number | null;
  h_over_r: number | null;
  unc_fraction: number | null;
  r_adj_tco2e: number | null;
  buffer_tco2e: number | null;
  leakage_tco2e: number | null;
  rounding_remainder_tco2e: number | null;
}

export interface LensZone {
  zone_id: string;
  label: string;
  area_ha: number;
  date_min: string | null;
  date_max: string | null;
  delta_stock_tc: number | null;
  contribution_e_tco2e: number | null;
  cause_status: CauseStatus;
  evidence_source_id: string | null;
  evidence_note: string;
  artifact_ids: string[];
}

export interface LensArtifact {
  artifact_id: string;
  role: string;
  media_type: string;
  sha256: string;
  url: string;
  bbox: [number, number, number, number] | null;
  crs: string;
  resolution_m: number | null;
  unit: string | null;
  provenance: string;
}

export interface LensSource {
  source_id: string;
  title: string;
  version: string;
  license: string;
  attribution: string;
  accessed: string;
}

export interface ClaimComparison {
  status: ClaimStatus;
  claimed_units: number | null;
  gap_units: number | null;
  comparable: boolean;
  reasons: string[];
  scope_note: string;
}

export interface PriceScenario {
  id: string;
  label: string;
  rub_per_unit: number;
}

export interface TimelinePoint {
  year: number;
  stock_tc_ha: number | null;
  baseline_tc_ha: number | null;
  observed: boolean;
  in_selected_period: boolean;
}

export interface LensPassport {
  calculation_id: string;
  calculated_at: string;
  content_sha256: string;
  report_url: string | null;
  schema_version: string;
  method_version: string;
  dataset_version: string;
  source_manifest_sha256: string;
}

export interface LensResult {
  fixture: FixtureLabel | null;
  request: LensRequest;
  area_ha: number;
  calculation_status: CalculationStatus;
  evidence_status: EvidenceStatus;
  stock: StockResult;
  baseline: BaselineResult;
  uncertainty: UncertaintyResult;
  units: UnitsResult;
  coverage: CoverageAxis[];
  timeline: TimelinePoint[];
  zones: LensZone[];
  artifacts: LensArtifact[];
  sources: LensSource[];
  limitations: string[];
  claim: ClaimComparison;
  prices: PriceScenario[];
  passport: LensPassport;
}

export interface LensJob {
  job_id: string;
  state: LensJobState;
  status_url: string;
  result_id: string | null;
  error: { code: string; message: string } | null;
}

export const LENS_YEAR_MIN = 2019;
export const LENS_YEAR_MAX = 2024;
export const LENS_MAX_AREA_HA = 2000;
