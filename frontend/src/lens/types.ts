// Carbon Lens v2 shapes, pinned by hand to contracts/v2/api-models.v2.schema.json as reviewed at
// backend e9817d0144569731e3a98c7af6c916cf55a510cf. The file is regenerated with openapi-typescript
// once contracts/v2 lands on main; until then this is the single place that names v2 fields.
//
// Unknown values from the service are never narrowed away: every enum is a union with `string`, and
// the screens read them through the neutral UNKNOWN fallback in src/domain/status.ts.

export type Unknowable<T extends string> = T | (string & {});

export type JobState = Unknowable<'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED'>;
export type CalculationStatus = Unknowable<'AVAILABLE' | 'UNAVAILABLE'>;
export type EvidenceStatus = Unknowable<'SUFFICIENT' | 'REVIEW_REQUIRED' | 'INSUFFICIENT'>;
export type AnchorStatus = Unknowable<'NOT_REQUESTED' | 'PENDING' | 'CONFIRMED' | 'FAILED'>;

export type ClaimStatus = Unknowable<
  | 'NOT_PROVIDED'
  | 'NOT_APPLICABLE'
  | 'NOT_COMPARABLE'
  | 'UNASSESSABLE'
  | 'SUPPORTED_BY_CASE'
  | 'PARTIALLY_SUPPORTED_BY_CASE'
  | 'NOT_SUPPORTED_BY_CASE'
>;
export type ClaimOrigin = Unknowable<'USER_INPUT' | 'DEMO_INPUT'>;
export type ClaimMismatchReason = Unknowable<
  'INVALID_CLAIM_VALUE' | 'NO_POSITIVE_CLAIM' | 'GEOMETRY_MISMATCH' | 'PERIOD_MISMATCH' | 'POOL_MISMATCH' | 'UNIT_MISMATCH'
>;

export type UnavailableReason = Unknowable<
  | 'MISSING_INPUT'
  | 'NON_FINITE_INPUT'
  | 'NON_POSITIVE_AREA'
  | 'NON_POSITIVE_PERIOD'
  | 'INVALID_UNCERTAINTY_INPUT'
  | 'INVALID_INTERVAL'
  | 'INCOMPLETE_COVERAGE'
  | 'BASELINE_OUT_OF_COVERAGE'
  | 'BASELINE_UNKNOWN_AREA'
  | 'RASTER_ANALYSIS_UNAVAILABLE'
>;
export type ZeroUnitsReason = Unknowable<'NON_POSITIVE_RELATIVE_RESULT' | 'UNCERTAINTY_TOO_HIGH' | 'ROUNDED_TO_ZERO'>;

export type ZoneFact = Unknowable<'TREE_COVER_LOSS' | 'SPECTRAL_CHANGE_ONLY' | 'RECOVERY_INDICATION'>;
export type ZoneCause = Unknowable<'FIRE_SUPPORTED' | 'UNKNOWN' | 'NOT_APPLICABLE'>;
export type DatasetOrigin = Unknowable<'COMPUTED_FROM_SUPPLIED_DATA' | 'CACHED_REPLAY' | 'EXTERNAL_RETRIEVAL' | 'STUB_FIXTURE'>;
export type FixtureKind = Unknowable<'DOC_EXAMPLE' | 'UNIT_TEST_VECTOR' | 'CONTRACT_FIXTURE'>;
export type ComparisonResult = Unknowable<'FIRST_OBSERVATION' | 'NEW_OBSERVATION' | 'UNCHANGED' | 'UPGRADED' | 'DOWNGRADED'>;
export type IntervalKind = Unknowable<'SCENARIO' | 'PROBABILISTIC'>;
export type WarningSeverity = Unknowable<'INFO' | 'WARNING' | 'CRITICAL'>;

export interface Geometry {
  type: 'Polygon' | 'MultiPolygon';
  coordinates: number[][][] | number[][][][];
}

export interface CatalogArea {
  aoi_id: string;
  name: string;
  region: string;
  area_ha: number;
  analysis_start_year: number;
  analysis_end_year: number;
  selection_role: string;
  project_status: string;
  baseline_id: string;
  bbox: [number, number, number, number];
  geometry: Geometry;
  available_years: number[];
}

export interface CatalogSampleRequest {
  request_id: string;
  parent_aoi_id: string | null;
  year_start: number;
  year_end: number;
  area_ha: number;
  purpose: string;
  baseline_rule: string;
  geometry: Geometry;
}

export interface PriceScenario {
  id: string;
  rub_per_unit: number;
}

export interface CatalogSource {
  source_id: string;
  product: string;
  version: string;
  license_url: string | null;
  attribution: string;
  access_date: string;
  role: string;
}

export interface Catalog {
  schema_version: string;
  method_version: string;
  dataset_version: string;
  dataset_hash: string;
  year_min: number;
  year_max: number;
  max_area_ha: number;
  raster_adapter: string;
  carbon_adapter: string;
  areas: CatalogArea[];
  sample_requests: CatalogSampleRequest[];
  prices: PriceScenario[];
  sources: CatalogSource[];
}

export interface ClaimScope {
  geometry_hash: string;
  year_start: number;
  year_end: number;
  pool: string;
  unit: string;
}

export interface AnalysisRequestBody {
  aoi_id?: string | null;
  geometry?: Geometry | null;
  year_start: number;
  year_end: number;
  claimed_units?: number | null;
  claim_origin?: ClaimOrigin | null;
  claim_scope?: ClaimScope | null;
  include_optical?: boolean;
}

export interface AnalysisAccepted {
  analysis_id: string;
  job_state: JobState;
  status_url: string;
  created_at: string;
}

export interface JobError {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export interface FixtureLabel {
  kind: FixtureKind;
  label: string;
  note: string;
}

export interface Identity {
  analysis_id: string;
  input_hash: string;
  geometry_hash: string;
  schema_version: string;
  method_version: string;
  dataset_version: string;
  dataset_hash: string;
  source_manifest_hash: string;
  parameters_hash: string;
  code_sha: string | null;
}

export interface Run {
  run_id: string;
  created_at: string;
  dataset_origin: DatasetOrigin;
  raster_adapter: string;
  carbon_adapter: string;
}

export interface RequestSnapshot {
  geometry: Geometry;
  aoi_id: string | null;
  year_start: number;
  year_end: number;
  claimed_units: number | null;
  claim_origin: ClaimOrigin | null;
  include_optical: boolean;
}

export interface ParentPart {
  aoi_id: string;
  area_ha: number;
}

export interface Areas {
  requested_ha: number;
  calculated_ha: number;
  missing_ha: number;
  /** Signed technical difference calculated − requested; null while the service does not send it. */
  area_difference_ha?: number | null;
  complete: boolean;
  parent_parts: ParentPart[];
}

export interface Coverage {
  biomass_fraction: number;
  uncertainty_fraction: number;
  baseline_fraction: number;
  optical_paired_valid_fraction: number;
}

export interface TimelinePoint {
  year: number;
  mean_agb_tdm_ha: number | null;
  mean_carbon_tc_ha: number | null;
  total_carbon_tc: number | null;
  baseline_carbon_tc_ha: number | null;
  area_ha: number | null;
  coverage: number | null;
  in_period: boolean;
  source_ref: string | null;
}

export interface Change {
  year_start: number;
  year_end: number;
  mean_carbon_start_tc_ha: number | null;
  mean_carbon_end_tc_ha: number | null;
  total_carbon_start_tc: number | null;
  total_carbon_end_tc: number | null;
  delta_carbon_tc: number | null;
  eproj_tco2e: number | null;
  eproj_tco2e_ha_year: number | null;
  normalisation_area_ha: number | null;
  sign_convention: string;
  pool: string;
}

export interface IntervalVariant {
  label: string;
  spatial_dependence: string;
  temporal_correlation: number | null;
  sd_tco2e: number | null;
  lower_tco2e: number | null;
  upper_tco2e: number | null;
  half_width_tco2e: number | null;
}

export interface Uncertainty {
  status: CalculationStatus;
  unavailable_reason: UnavailableReason | null;
  lower_tco2e: number | null;
  upper_tco2e: number | null;
  sd_tco2e: number | null;
  method: string;
  interval_kind: IntervalKind;
  assumptions: Record<string, unknown>;
  sensitivity: IntervalVariant[];
}

export interface BaselinePart {
  aoi_id: string;
  area_ha: number;
  stock_start_tc_ha: number | null;
  stock_end_tc_ha: number | null;
  delta_tc_ha: number | null;
  delta_tc: number | null;
  clipped_at_zero: boolean;
}

export interface Baseline {
  status: CalculationStatus;
  unavailable_reason: UnavailableReason | null;
  baseline_id: string | null;
  kind: string;
  area_ha: number | null;
  delta_tc: number | null;
  delta_tc_ha: number | null;
  ebase_tco2e: number | null;
  parts: BaselinePart[];
}

export interface Units {
  status: CalculationStatus;
  unavailable_reason: UnavailableReason | null;
  zero_reason: ZeroUnitsReason | null;
  eproj_tco2e: number | null;
  ebase_tco2e: number | null;
  lk_tco2e: number | null;
  lower_tco2e: number | null;
  upper_tco2e: number | null;
  h_tco2e: number | null;
  r_tco2e: number | null;
  ratio: number | null;
  unc: number | null;
  uncertainty_deduction_tco2e: number | null;
  radj_tco2e: number | null;
  buffer_tco2e: number | null;
  rounding_residual_tco2e: number | null;
  q: number | null;
  reason_codes: string[];
}

export interface ScenarioValue {
  price_rub: number;
  value_rub: number;
}

export interface ScenarioValues {
  price_parameters_ref: string;
  unit: string;
  low: ScenarioValue;
  base: ScenarioValue;
  high: ScenarioValue;
}

export interface Claim {
  status: ClaimStatus;
  origin: ClaimOrigin | null;
  comparable: boolean;
  claimed_units: number | null;
  q: number | null;
  gap_units: number | null;
  supported_share: number | null;
  mismatch_reasons: ClaimMismatchReason[];
  scope: ClaimScope;
  scenario_gap_values: ScenarioValues | null;
  scope_note: string;
}

export interface DateRange {
  start: string | null;
  end: string | null;
  uncertainty_days_min: number | null;
  uncertainty_days_max: number | null;
}

export interface Zone {
  zone_id: string;
  fact: ZoneFact;
  cause: ZoneCause;
  cause_reason: string;
  area_ha: number;
  carbon_overlap_ha: number;
  delta_carbon_tc: number | null;
  contribution_e_tco2e: number | null;
  date_range: DateRange | null;
  evidence_refs: string[];
  evidence: Record<string, unknown>;
  artifact_ref: string | null;
  /** Outline of the zone when the service ships one; otherwise the map anchors a labelled marker. */
  geometry?: Geometry | null;
}

export interface Scene {
  scene_key: string;
  aoi_id: string | null;
  datetime_utc: string;
  year: number;
  usable_fraction: number | null;
  note: string;
}

/** Structured warning. Older deployments send a bare string; the client normalises both. */
export interface EvidenceWarning {
  code: string;
  severity: WarningSeverity;
  message: string;
  details: Record<string, unknown>;
}

export interface Evidence {
  status: EvidenceStatus;
  optical_paired_valid_fraction: number | null;
  analysed_parent: string | null;
  scenes: Scene[];
  reconciliation: Record<string, unknown> | null;
  warnings: EvidenceWarning[];
}

export interface Passport {
  content_hash: string;
  report_hash: string | null;
  previous_hash: string | null;
  comparison_scope: string;
  comparison_result: ComparisonResult;
  comparison_note: string;
  created_at: string;
}

export interface Source {
  source_id: string;
  product: string;
  version: string;
  license_url: string | null;
  attribution: string;
  access_date: string;
  role: string;
}

export interface Artifact {
  artifact_id: string;
  role: string;
  media_type: string;
  sha256: string;
  size_bytes: number;
  url: string;
  bbox_wgs84: [number, number, number, number] | null;
  crs: string | null;
  resolution: [number, number] | null;
  resolution_units: string | null;
  unit: string | null;
  provenance: string;
}

export interface AnalysisResult {
  fixture: FixtureLabel | null;
  identity: Identity;
  run: Run;
  request: RequestSnapshot;
  calculation_status: CalculationStatus;
  evidence_status: EvidenceStatus;
  areas: Areas;
  coverage: Coverage;
  timeline: TimelinePoint[];
  change: Change;
  uncertainty: Uncertainty;
  baseline: Baseline;
  units: Units;
  scenario_values: ScenarioValues;
  claim: Claim;
  zones: Zone[];
  evidence: Evidence;
  passport: Passport;
  sources: Source[];
  artifacts: Artifact[];
  limitations: string[];
  notes: string[];
}

export interface Analysis {
  analysis_id: string;
  job_state: JobState;
  created_at: string;
  updated_at: string;
  attempts: number;
  status_url: string;
  report_url: string | null;
  proof_url: string | null;
  error: JobError | null;
  result: AnalysisResult | null;
}

export interface Anchor {
  status: AnchorStatus;
  deployment_id: string | null;
  tx_hash: string | null;
  anchored_at: string | null;
  note: string;
}

export interface Proof {
  analysis_id: string;
  identity: Identity;
  passport: Passport;
  canonical_url: string;
  report_urls: Record<string, string>;
  artifacts: Artifact[];
  anchor: Anchor;
  verification_note: string;
}

export interface Report {
  schema_version: string;
  generated_at: string;
  report_hash: string;
  result: AnalysisResult;
}

export interface AreaMeasurement {
  area_ha: number | null;
  valid: boolean;
  max_area_ha: number;
  within_limit: boolean;
  geometry_hash: string | null;
  geometry: Geometry | null;
  errors: EvidenceWarning[];
  /** Where the number came from: the service, or the client's own spherical estimate. */
  source: 'SERVICE' | 'CLIENT_ESTIMATE';
  note: string;
}

export const LENS_YEAR_MIN = 2019;
export const LENS_YEAR_MAX = 2024;
export const LENS_MAX_AREA_HA = 2000;
export const LENS_PROJECTION_END_YEAR = 2029;
