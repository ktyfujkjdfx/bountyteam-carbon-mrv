import type { LensResult, LensRequest, PriceScenario } from './types';

// Labelled preview data for F1. Nothing here is a computed result for a real AOI:
// DOC_EXAMPLE reproduces the conditional example printed in doc/Постановка_задачи (Q = 395);
// UNIT_TEST_VECTOR entries are logic vectors for branches that must exist in the UI.
// Every scientific number is supplied ready-made; the screen never recomputes them.

export type FixtureScenarioId =
  | 'DOC_EXAMPLE_Q395'
  | 'ZERO_NON_POSITIVE'
  | 'ZERO_UNCERTAINTY'
  | 'ZERO_ROUNDED'
  | 'UNAVAILABLE_COVERAGE'
  | 'WEAK_OPTICS_VALID_CCI'
  | 'UNKNOWN_DRIFT';

export const PRICES: PriceScenario[] = [
  { id: 'price_low', label: 'Низкая', rub_per_unit: 500 },
  { id: 'price_base', label: 'Базовая', rub_per_unit: 1500 },
  { id: 'price_high', label: 'Высокая', rub_per_unit: 4000 },
];

const SOURCES: LensResult['sources'] = [
  {
    source_id: 'CCI_V7',
    title: 'ESA Biomass CCI',
    version: 'v7.0',
    license: 'ESA CCI terms',
    attribution: 'Santoro M.; Cartus O. (2026), NERC EDS CEDA, DOI 10.5285/6429d1aafe1e43b9b414e4a5a7f8b903',
    accessed: '2026-09-18',
  },
  {
    source_id: 'S2_L2A',
    title: 'Sentinel-2 L2A (Element 84 Earth Search)',
    version: '2019–2024',
    license: 'Copernicus',
    attribution: 'Contains modified Copernicus Sentinel data 2019–2024',
    accessed: '2026-09-18',
  },
  {
    source_id: 'GFC_2025_V113',
    title: 'Hansen Global Forest Change',
    version: '2025 v1.13',
    license: 'CC BY 4.0',
    attribution: 'Hansen et al. (2013), University of Maryland / GLAD',
    accessed: '2026-09-18',
  },
  {
    source_id: 'MODIS_MCD64A1_061',
    title: 'MODIS Burned Area MCD64A1',
    version: 'v6.1',
    license: 'NASA LP DAAC terms',
    attribution: 'Giglio, Justice, Boschetti, Roy; DOI 10.5067/MODIS/MCD64A1.061',
    accessed: '2026-09-18',
  },
  {
    source_id: 'CASE_RULES_V1',
    title: 'Сценарные правила кейса (baseline, вычеты, резерв, цены)',
    version: 'v1',
    license: 'Материалы кейса',
    attribution: 'SR Data, data/methodology/parameters.csv',
    accessed: '2026-09-18',
  },
];

const IPCC_ASSUMPTIONS = [
  'CF = 0.47 т C/т сухого вещества (IPCC 2006, том 4, таблица 4.3).',
  'Перевод в CO₂-эквивалент по отношению 44/12.',
  'Учитывается только живая надземная древесная биомасса.',
];

type Scenario = Omit<LensResult, 'request' | 'area_ha'>;

export interface ScenarioDefaults {
  areaHa: number;
  years: [number, number];
}

function passport(id: string, hash: string): LensResult['passport'] {
  return {
    calculation_id: id,
    calculated_at: '2026-09-18T09:00:00Z',
    content_sha256: hash,
    report_url: null,
    schema_version: 'lens-2.0.0-draft',
    method_version: 'case-rules-v1',
    dataset_version: 'data.zip d8723225',
    source_manifest_sha256: '0xd8723225a1f66f1ff1890439e6e561f3a28a94f6a81b63b5db99a73579fc22a8',
  };
}

const DOC_EXAMPLE: Scenario = {
  fixture: {
    kind: 'DOC_EXAMPLE',
    label: 'Условный пример из постановки задачи',
    note: 'Числа взяты из doc/Постановка_задачи (100 га, один год, биомасса 100 → 104 т/га). Это не расчёт по выбранному участку data/.',
  },
  calculation_status: 'AVAILABLE',
  evidence_status: 'SUFFICIENT',
  stock: {
    pool: 'Живая надземная древесная биомасса',
    mean_start_tc_ha: 47,
    mean_end_tc_ha: 48.88,
    total_start_tc: 4700,
    total_end_tc: 4888,
    delta_tc: 188,
    e_tco2e: -689.333,
    e_tco2e_ha_yr: -6.893,
    year_start: 2019,
    year_end: 2020,
  },
  baseline: {
    baseline_id: 'HIST-AGB-2015-2019-v1',
    kind: 'сценарное допущение',
    e_base_tco2e: -172.333,
    stock_start_tc_ha: 47,
    stock_end_tc_ha: 47.47,
    applied_to_area_ha: 100,
    parent_aoi_id: null,
    note: 'Базовая линия — условие кейса (прирост 0,47 т C/га), а не доказанный альтернативный исход.',
  },
  uncertainty: {
    lower_tco2e: -792.733,
    upper_tco2e: -585.933,
    h_tco2e: 103.4,
    method: 'Сценарный диапазон примера постановки',
    is_probabilistic: false,
    assumptions: [...IPCC_ASSUMPTIONS, 'H — расстояние до наиболее удалённой границы диапазона.'],
  },
  units: {
    status: 'AVAILABLE',
    q: 395,
    reason: null,
    reason_detail: null,
    r_tco2e: 517,
    h_over_r: 0.2,
    unc_fraction: 0.1,
    r_adj_tco2e: 465.3,
    buffer_tco2e: 69.795,
    leakage_tco2e: 0,
    rounding_remainder_tco2e: 0.505,
  },
  coverage: [
    { id: 'BIOMASS_CCI', label: 'Покрытие биомассы и SD (CCI)', covered_fraction: 1, missing_area_ha: 0, note: 'Числовые значения доступны на обе даты.' },
    { id: 'BASELINE_TABLE', label: 'Покрытие базовой линии', covered_fraction: 1, missing_area_ha: 0, note: 'Участок присутствует в baseline.csv.' },
    {
      id: 'OPTICAL_PAIRED_VALID',
      label: 'Оптика на обе даты (paired-valid)',
      covered_fraction: 0.82,
      missing_area_ha: 18,
      note: 'Качество оптики влияет на объяснение изменения, но не на покрытие CCI.',
    },
  ],
  timeline: [
    { year: 2015, stock_tc_ha: 45.6, baseline_tc_ha: null, observed: true, in_selected_period: false },
    { year: 2019, stock_tc_ha: 47, baseline_tc_ha: 47, observed: true, in_selected_period: true },
    { year: 2020, stock_tc_ha: 48.88, baseline_tc_ha: 47.47, observed: true, in_selected_period: true },
    { year: 2021, stock_tc_ha: null, baseline_tc_ha: 47.94, observed: false, in_selected_period: false },
    { year: 2022, stock_tc_ha: null, baseline_tc_ha: 48.41, observed: false, in_selected_period: false },
  ],
  zones: [
    {
      zone_id: 'DOC-EXAMPLE-ZONE-1',
      label: 'Условная зона прироста',
      area_ha: 100,
      date_min: '2019-01-01',
      date_max: '2020-12-31',
      delta_stock_tc: 188,
      contribution_e_tco2e: -689.333,
      cause_status: 'NOT_ESTABLISHED',
      evidence_source_id: null,
      evidence_note: 'В примере постановки причина изменения не устанавливается.',
      artifact_ids: [],
    },
  ],
  artifacts: [],
  sources: SOURCES,
  limitations: [
    'Пример условный: он проверяет формулы, а не состояние конкретной территории.',
    'Положительное E означает потерю учитываемого пула, отрицательное — накопление.',
    'Резерв 15 % и вычет за неопределённость 10 % — сценарные условия кейса.',
  ],
  claim: {
    status: 'NOT_PROVIDED',
    claimed_units: null,
    gap_units: null,
    comparable: false,
    reasons: [],
    scope_note: 'Заявление не введено. Все основные функции работают без него.',
  },
  prices: PRICES,
  passport: passport('FIXTURE-DOC-EXAMPLE-Q395', '0x4c2fbb3f2b3f6f7b0a1a5e5b6f2a7d0f2c9f64a1f8b5c2a0d7e3b1c4a9f0e8d2'),
};

function unitVector(
  id: FixtureScenarioId,
  label: string,
  note: string,
  overrides: Partial<Scenario>,
): Scenario {
  const base: Scenario = {
    ...DOC_EXAMPLE,
    fixture: { kind: 'UNIT_TEST_VECTOR', label, note },
    passport: passport(`FIXTURE-${id}`, `0x${id.toLowerCase().replace(/[^a-z0-9]/g, '').padEnd(64, '0').slice(0, 64)}`),
  };
  return { ...base, ...overrides };
}

const ZERO_NON_POSITIVE = unitVector(
  'ZERO_NON_POSITIVE',
  'Q = 0: результат не выше базовой линии',
  'Логический вектор: R ≤ 0, поэтому отношение H/R не вычисляется.',
  {
    evidence_status: 'SUFFICIENT',
    stock: { ...DOC_EXAMPLE.stock, mean_end_tc_ha: 46.8, total_end_tc: 4680, delta_tc: -20, e_tco2e: 73.333, e_tco2e_ha_yr: 0.733 },
    baseline: { ...DOC_EXAMPLE.baseline, e_base_tco2e: -172.333 },
    uncertainty: { ...DOC_EXAMPLE.uncertainty, lower_tco2e: -30, upper_tco2e: 176.666, h_tco2e: 103.333 },
    units: {
      status: 'AVAILABLE',
      q: 0,
      reason: 'NON_POSITIVE_RELATIVE_RESULT',
      reason_detail: 'R ≤ 0: результат периода не превышает базовую линию.',
      r_tco2e: -245.666,
      h_over_r: null,
      unc_fraction: null,
      r_adj_tco2e: null,
      buffer_tco2e: null,
      leakage_tco2e: 0,
      rounding_remainder_tco2e: null,
    },
    limitations: ['Отсутствие положительного результата относительно базовой линии — корректный итог, а не ошибка расчёта.'],
  },
);

const ZERO_UNCERTAINTY = unitVector('ZERO_UNCERTAINTY', 'Q = 0: неопределённость слишком велика', 'Логический вектор: R > 0, но H/R ≥ 1.', {
  evidence_status: 'REVIEW_REQUIRED',
  units: {
    status: 'AVAILABLE',
    q: 0,
    reason: 'UNCERTAINTY_TOO_HIGH',
    reason_detail: 'H/R ≥ 1: диапазон перекрывает весь результат.',
    r_tco2e: 90,
    h_over_r: 1.15,
    unc_fraction: null,
    r_adj_tco2e: null,
    buffer_tco2e: null,
    leakage_tco2e: 0,
    rounding_remainder_tco2e: null,
  },
  uncertainty: { ...DOC_EXAMPLE.uncertainty, lower_tco2e: -193.5, upper_tco2e: 13.5, h_tco2e: 103.5 },
  limitations: ['Широкий диапазон обнуляет единицы по правилу кейса; данные при этом присутствуют.'],
});

const ZERO_ROUNDED = unitVector('ZERO_ROUNDED', 'Q = 0: округление вниз', 'Логический вектор: после вычетов остаётся меньше одной единицы.', {
  units: {
    status: 'AVAILABLE',
    q: 0,
    reason: 'ROUNDED_TO_ZERO',
    reason_detail: 'После вычета за неопределённость и резерва осталось 0,72 т CO₂-экв.',
    r_tco2e: 1.1,
    h_over_r: 0.1,
    unc_fraction: 0.1,
    r_adj_tco2e: 0.99,
    buffer_tco2e: 0.1485,
    leakage_tco2e: 0,
    rounding_remainder_tco2e: 0.8415,
  },
  uncertainty: { ...DOC_EXAMPLE.uncertainty, lower_tco2e: -0.11, upper_tco2e: 0.11, h_tco2e: 0.11 },
  limitations: ['Дробный остаток после округления в Q не включается.'],
});

const UNAVAILABLE_COVERAGE = unitVector(
  'UNAVAILABLE_COVERAGE',
  'Q = null: контур выходит за покрытие',
  'Логический вектор: часть контура без числовых данных биомассы, расчёт единиц недоступен.',
  {
    calculation_status: 'UNAVAILABLE',
    evidence_status: 'INSUFFICIENT',
    stock: { ...DOC_EXAMPLE.stock, total_start_tc: null, total_end_tc: null, delta_tc: null, e_tco2e: null, e_tco2e_ha_yr: null },
    baseline: { ...DOC_EXAMPLE.baseline, e_base_tco2e: null, applied_to_area_ha: null, note: 'Часть запроса вне таблицы базовой линии.' },
    uncertainty: { ...DOC_EXAMPLE.uncertainty, lower_tco2e: null, upper_tco2e: null, h_tco2e: null },
    units: {
      status: 'UNAVAILABLE',
      q: null,
      reason: 'INCOMPLETE_BIOMASS_COVERAGE',
      reason_detail: 'Числовые данные биомассы отсутствуют на 31 % площади запроса.',
      r_tco2e: null,
      h_over_r: null,
      unc_fraction: null,
      r_adj_tco2e: null,
      buffer_tco2e: null,
      leakage_tco2e: null,
      rounding_remainder_tco2e: null,
    },
    coverage: [
      { id: 'BIOMASS_CCI', label: 'Покрытие биомассы и SD (CCI)', covered_fraction: 0.69, missing_area_ha: 31, note: 'Пропуски числового покрытия показаны на карте штриховкой.' },
      { id: 'BASELINE_TABLE', label: 'Покрытие базовой линии', covered_fraction: 0.69, missing_area_ha: 31, note: 'За пределами таблицы расчёт единиц недоступен.' },
      { id: 'OPTICAL_PAIRED_VALID', label: 'Оптика на обе даты (paired-valid)', covered_fraction: 0.94, missing_area_ha: 6, note: 'Хорошая оптика не восполняет отсутствующее покрытие CCI.' },
    ],
    timeline: [
      { year: 2019, stock_tc_ha: 47, baseline_tc_ha: 47, observed: true, in_selected_period: true },
      { year: 2020, stock_tc_ha: null, baseline_tc_ha: 47.47, observed: false, in_selected_period: true },
    ],
    limitations: ['Недоступность расчёта — это не ноль единиц: показана причина и рассчитанная часть.'],
  },
);

const WEAK_OPTICS = unitVector(
  'WEAK_OPTICS_VALID_CCI',
  'Слабая оптика при полном покрытии CCI',
  'Логический вектор: облачность ухудшает объяснение изменения, покрытие биомассы при этом полное.',
  {
    evidence_status: 'REVIEW_REQUIRED',
    coverage: [
      { id: 'BIOMASS_CCI', label: 'Покрытие биомассы и SD (CCI)', covered_fraction: 1, missing_area_ha: 0, note: 'Числовые данные доступны полностью.' },
      { id: 'BASELINE_TABLE', label: 'Покрытие базовой линии', covered_fraction: 1, missing_area_ha: 0, note: 'Участок присутствует в baseline.csv.' },
      { id: 'OPTICAL_PAIRED_VALID', label: 'Оптика на обе даты (paired-valid)', covered_fraction: 0.18, missing_area_ha: 82, note: 'Облака и тени: объяснение изменения ограничено, расчёт запаса не затронут.' },
    ],
    zones: [
      {
        zone_id: 'UNIT-ZONE-OPTICS',
        label: 'Зона изменения без пригодной оптики',
        area_ha: 24.5,
        date_min: '2021-06-01',
        date_max: '2021-09-30',
        delta_stock_tc: -310,
        contribution_e_tco2e: 1136.7,
        cause_status: 'NOT_ESTABLISHED',
        evidence_source_id: null,
        evidence_note: 'Причина не установлена: пригодных снимков на обе даты недостаточно.',
        artifact_ids: [],
      },
    ],
    limitations: ['Оптическое качество и покрытие биомассы — разные оси; одно не заменяет другое.'],
  },
);

const UNKNOWN_DRIFT = unitVector('UNKNOWN_DRIFT', 'Дрейф контракта: незнакомые значения', 'Логический вектор: Backend прислал значения вне текущего контракта.', {
  evidence_status: 'PARTIALLY_OBSERVED' as never,
  units: {
    ...DOC_EXAMPLE.units,
    reason: 'MANUAL_REVIEW_REQUIRED' as never,
    reason_detail: 'Незнакомая причина от Backend.',
  },
  claim: {
    status: 'ESCALATED_TO_REGISTRY' as never,
    claimed_units: 500,
    gap_units: null,
    comparable: false,
    reasons: ['Статус сравнения отсутствует в текущем контракте.'],
    scope_note: 'Значение получено от Backend и показано как неизвестное.',
  },
  limitations: ['Неизвестные значения показываются нейтрально и не выдаются за подтверждённые статусы.'],
});

export const FIXTURE_SCENARIOS: Record<FixtureScenarioId, Scenario> = {
  DOC_EXAMPLE_Q395: DOC_EXAMPLE,
  ZERO_NON_POSITIVE,
  ZERO_UNCERTAINTY,
  ZERO_ROUNDED,
  UNAVAILABLE_COVERAGE,
  WEAK_OPTICS_VALID_CCI: WEAK_OPTICS,
  UNKNOWN_DRIFT,
};

export const FIXTURE_SCENARIO_ORDER: FixtureScenarioId[] = [
  'DOC_EXAMPLE_Q395',
  'ZERO_NON_POSITIVE',
  'ZERO_UNCERTAINTY',
  'ZERO_ROUNDED',
  'UNAVAILABLE_COVERAGE',
  'WEAK_OPTICS_VALID_CCI',
  'UNKNOWN_DRIFT',
];

export const SCENARIO_DEFAULTS: Record<FixtureScenarioId, ScenarioDefaults> = {
  DOC_EXAMPLE_Q395: { areaHa: 100, years: [2019, 2020] },
  ZERO_NON_POSITIVE: { areaHa: 100, years: [2019, 2020] },
  ZERO_UNCERTAINTY: { areaHa: 100, years: [2019, 2020] },
  ZERO_ROUNDED: { areaHa: 100, years: [2019, 2020] },
  UNAVAILABLE_COVERAGE: { areaHa: 100, years: [2019, 2020] },
  WEAK_OPTICS_VALID_CCI: { areaHa: 100, years: [2019, 2020] },
  UNKNOWN_DRIFT: { areaHa: 100, years: [2019, 2020] },
};

export function buildFixtureResult(id: FixtureScenarioId, request: LensRequest, areaHa: number): LensResult {
  const rest = FIXTURE_SCENARIOS[id];
  return {
    ...structuredClone(rest),
    request: structuredClone(request),
    area_ha: areaHa,
    stock: { ...structuredClone(rest.stock), year_start: request.year_start, year_end: request.year_end },
  };
}
