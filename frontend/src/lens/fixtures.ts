// Labelled values for the offline set, shaped exactly like the reviewed v2 result.
//
// DOC_EXAMPLE reproduces the conditional example printed in doc/Постановка_задачи (Q = 395);
// UNIT_TEST_VECTOR entries are logic vectors for branches the UI must be able to show.
// Nothing here is a measurement of a real area: the fixture label travels with the result and is
// shown on screen. Territories, areas, the baseline table, scenes, events, coefficients, prices and
// the source registry are NOT here — they are read from the official data/ archive in ./data.ts.

import { casePrices, caseSources, scenesInPeriod } from './data';
import { bboxOf, box } from './geometry';
import type {
  AnalysisResult,
  Areas,
  Baseline,
  Change,
  Claim,
  ClaimOrigin,
  Coverage,
  Evidence,
  EvidenceWarning,
  Geometry,
  Scene,
  ScenarioValues,
  Source,
  TimelinePoint,
  Uncertainty,
  Units,
  Zone,
} from './types';

export type FixtureScenarioId =
  | 'DOC_EXAMPLE_Q395'
  | 'ZERO_NON_POSITIVE'
  | 'ZERO_UNCERTAINTY'
  | 'ZERO_ROUNDED'
  | 'UNAVAILABLE_COVERAGE'
  | 'WEAK_OPTICS_VALID_CCI'
  | 'FIRE_SUPPORTED_LOSS'
  | 'CAUSE_UNKNOWN_LOSS'
  | 'RECOVERY_AFTER_LOSS'
  | 'SUBPLOT_BASELINE'
  | 'UNKNOWN_DRIFT';

export interface ScenarioDefaults {
  years: [number, number];
  aoiId: string | null;
  sampleRequestId?: string;
  acceptance: string | null;
  acceptanceNote: string | null;
}

export const SCENARIO_DEFAULTS: Record<FixtureScenarioId, ScenarioDefaults> = {
  DOC_EXAMPLE_Q395: {
    years: [2019, 2020],
    aoiId: null,
    acceptance: null,
    acceptanceNote: 'Числовой эталон формул: R → вычет за неопределённость → резерв → округление → Q = 395.',
  },
  ZERO_NON_POSITIVE: {
    years: [2019, 2024],
    aoiId: 'RU_TVER_01',
    acceptance: 'S1',
    acceptanceNote: 'Контроль по GFC: отсутствие потерь покрова не гарантирует ни постоянную биомассу, ни положительный Q.',
  },
  ZERO_UNCERTAINTY: { years: [2019, 2020], aoiId: null, acceptance: null, acceptanceNote: null },
  ZERO_ROUNDED: { years: [2019, 2020], aoiId: null, acceptance: null, acceptanceNote: null },
  UNAVAILABLE_COVERAGE: {
    years: [2019, 2020],
    aoiId: null,
    acceptance: 'S7',
    acceptanceNote: 'Контур выходит за доступное покрытие: частичный результат и q = null, а не ноль.',
  },
  WEAK_OPTICS_VALID_CCI: {
    years: [2021, 2022],
    aoiId: 'RU_MORDOVIA_03',
    acceptance: 'S6',
    acceptanceNote: 'Облачная сцена не делает покрытие CCI неполным: оси качества разделены.',
  },
  FIRE_SUPPORTED_LOSS: {
    years: [2020, 2022],
    aoiId: 'RU_MORDOVIA_03',
    acceptance: 'S2',
    acceptanceNote: 'Изменение и свидетельства пожара августа 2021 года: площадь зоны и вклад, без выдуманной доли.',
  },
  CAUSE_UNKNOWN_LOSS: {
    years: [2019, 2024],
    aoiId: 'RU_VOLOGDA_02',
    acceptance: 'S3',
    acceptanceNote: 'Потери покрова без достаточных свидетельств: причина остаётся неустановленной.',
  },
  RECOVERY_AFTER_LOSS: {
    years: [2019, 2024],
    aoiId: 'RU_MORDOVIA_04',
    acceptance: 'S4',
    acceptanceNote: 'История и последующая динамика: восстановление объявляется только по результату.',
  },
  SUBPLOT_BASELINE: {
    years: [2020, 2024],
    aoiId: null,
    sampleRequestId: 'CHECK_TRANSFER_01',
    acceptance: 'S5',
    acceptanceNote: 'Подучасток ~808,85 га: удельная базовая линия родителя применяется к площади запроса.',
  },
  UNKNOWN_DRIFT: { years: [2019, 2020], aoiId: null, acceptance: null, acceptanceNote: null },
};

export const FIXTURE_SCENARIO_ORDER: FixtureScenarioId[] = [
  'DOC_EXAMPLE_Q395',
  'ZERO_NON_POSITIVE',
  'ZERO_UNCERTAINTY',
  'ZERO_ROUNDED',
  'UNAVAILABLE_COVERAGE',
  'WEAK_OPTICS_VALID_CCI',
  'FIRE_SUPPORTED_LOSS',
  'CAUSE_UNKNOWN_LOSS',
  'RECOVERY_AFTER_LOSS',
  'SUBPLOT_BASELINE',
  'UNKNOWN_DRIFT',
];

export const FIXTURE_LABELS: Record<FixtureScenarioId, { kind: 'DOC_EXAMPLE' | 'UNIT_TEST_VECTOR'; label: string; note: string }> = {
  DOC_EXAMPLE_Q395: {
    kind: 'DOC_EXAMPLE',
    label: 'Условный пример из постановки задачи',
    note: 'Числа взяты из doc/Постановка_задачи (100 га, один год, биомасса 100 → 104 т/га). Это не расчёт по выбранному участку data/.',
  },
  ZERO_NON_POSITIVE: {
    kind: 'UNIT_TEST_VECTOR',
    label: 'Q = 0: результат не выше базовой линии',
    note: 'Логический вектор: R ≤ 0, отношение H/R не вычисляется. Числа не относятся к выбранному участку.',
  },
  ZERO_UNCERTAINTY: {
    kind: 'UNIT_TEST_VECTOR',
    label: 'Q = 0: неопределённость слишком велика',
    note: 'Логический вектор: R > 0, но H/R ≥ 1. Числа не относятся к выбранному участку.',
  },
  ZERO_ROUNDED: {
    kind: 'UNIT_TEST_VECTOR',
    label: 'Q = 0: округление вниз',
    note: 'Логический вектор: после вычетов осталось меньше одной единицы.',
  },
  UNAVAILABLE_COVERAGE: {
    kind: 'UNIT_TEST_VECTOR',
    label: 'Q = null: контур выходит за покрытие',
    note: 'Логический вектор: часть контура без числовых данных биомассы, расчёт единиц недоступен.',
  },
  WEAK_OPTICS_VALID_CCI: {
    kind: 'UNIT_TEST_VECTOR',
    label: 'Слабая оптика при полном покрытии CCI',
    note: 'Логический вектор: облачность ограничивает объяснение, покрытие биомассы полное.',
  },
  FIRE_SUPPORTED_LOSS: {
    kind: 'UNIT_TEST_VECTOR',
    label: 'Потеря с признаком горения по продукту MODIS',
    note: 'Логический вектор: зона потери связана со строкой data/events.csv. Признак горения — продукт, а не измеренная площадь гари.',
  },
  CAUSE_UNKNOWN_LOSS: {
    kind: 'UNIT_TEST_VECTOR',
    label: 'Потеря покрова с неустановленной причиной',
    note: 'Логический вектор: изменение наблюдается, достаточных свидетельств причины нет.',
  },
  RECOVERY_AFTER_LOSS: {
    kind: 'UNIT_TEST_VECTOR',
    label: 'История потери и последующая динамика',
    note: 'Логический вектор: после потери наблюдается прирост, период в целом остаётся ниже базовой линии.',
  },
  SUBPLOT_BASELINE: {
    kind: 'UNIT_TEST_VECTOR',
    label: 'Подучасток: удельная базовая линия родителя',
    note: 'Логический вектор: базовая линия родительского участка применена к площади запроса.',
  },
  UNKNOWN_DRIFT: {
    kind: 'UNIT_TEST_VECTOR',
    label: 'Дрейф контракта: незнакомые значения',
    note: 'Логический вектор: сервис прислал значения вне текущего контракта.',
  },
};

export interface ScenarioNumbers {
  calculation_status: string;
  evidence_status: string;
  change: Partial<Change>;
  units: Partial<Units>;
  uncertainty?: Partial<Uncertainty>;
  baseline?: Partial<Baseline>;
  coverage: Coverage;
  stockSeries: Array<{ year: number; carbon: number | null; baseline: number | null; observed: boolean }>;
  zones: Array<Omit<Zone, 'geometry'> & { geometryShare?: number }>;
  warnings: EvidenceWarning[];
  limitations: string[];
  notes: string[];
}

const IPCC_ASSUMPTIONS: Record<string, unknown> = {
  cf_agb: 0.47,
  co2_per_c: 44 / 12,
  pool: 'AGB',
  grid: 'native CCI cells',
  spatial_dependence: 'INDEPENDENT_NATIVE_CELLS',
  temporal_correlation: 0,
  coverage_factor: 1,
  empirically_calibrated: false,
};

function zone(input: Partial<Zone> & { zone_id: string; area_ha: number; geometryShare?: number }): Omit<Zone, 'geometry'> & { geometryShare?: number } {
  return {
    fact: 'SPECTRAL_CHANGE_ONLY',
    cause: 'UNKNOWN',
    cause_reason: 'Изменение наблюдается, причина не установлена.',
    carbon_overlap_ha: input.area_ha,
    delta_carbon_tc: null,
    contribution_e_tco2e: null,
    date_range: null,
    evidence_refs: [],
    evidence: {},
    artifact_ref: null,
    ...input,
  } as Omit<Zone, 'geometry'> & { geometryShare?: number };
}

const DOC_EXAMPLE: ScenarioNumbers = {
  calculation_status: 'AVAILABLE',
  evidence_status: 'SUFFICIENT',
  change: {
    mean_carbon_start_tc_ha: 47,
    mean_carbon_end_tc_ha: 48.88,
    total_carbon_start_tc: 4700,
    total_carbon_end_tc: 4888,
    delta_carbon_tc: 188,
    eproj_tco2e: -689.333,
    eproj_tco2e_ha_year: -6.893,
    normalisation_area_ha: 100,
  },
  units: {
    status: 'AVAILABLE',
    eproj_tco2e: -689.333,
    ebase_tco2e: -172.333,
    lk_tco2e: 0,
    lower_tco2e: -792.733,
    upper_tco2e: -585.933,
    h_tco2e: 103.4,
    r_tco2e: 517,
    ratio: 0.2,
    unc: 0.1,
    uncertainty_deduction_tco2e: 51.7,
    radj_tco2e: 465.3,
    buffer_tco2e: 69.795,
    rounding_residual_tco2e: 0.505,
    q: 395,
    reason_codes: [],
  },
  baseline: { ebase_tco2e: -172.333, delta_tc_ha: 0.47, delta_tc: 47, area_ha: 100 },
  coverage: { biomass_fraction: 1, uncertainty_fraction: 1, baseline_fraction: 1, optical_paired_valid_fraction: 0.82 },
  stockSeries: [
    { year: 2015, carbon: 45.6, baseline: null, observed: true },
    { year: 2019, carbon: 47, baseline: 47, observed: true },
    { year: 2020, carbon: 48.88, baseline: 47.47, observed: true },
  ],
  zones: [
    zone({
      zone_id: 'DOC-EXAMPLE-ZONE-1',
      fact: 'RECOVERY_INDICATION',
      cause: 'NOT_APPLICABLE',
      cause_reason: 'В примере постановки причина изменения не устанавливается.',
      area_ha: 100,
      delta_carbon_tc: 188,
      contribution_e_tco2e: -689.333,
      date_range: { start: '2019-01-01', end: '2020-12-31', uncertainty_days_min: null, uncertainty_days_max: null },
      geometryShare: 0.6,
    }),
  ],
  warnings: [],
  limitations: [
    'Пример условный: он проверяет формулы, а не состояние конкретной территории.',
    'Положительное E — потеря учитываемого пула за период, а не мгновенный выброс всего углерода.',
    'Резерв 15 % и правило вычета за неопределённость — сценарные условия кейса.',
  ],
  notes: [],
};

function vector(overrides: Partial<ScenarioNumbers>): ScenarioNumbers {
  return { ...DOC_EXAMPLE, ...overrides };
}

const SCENARIOS: Record<FixtureScenarioId, ScenarioNumbers> = {
  DOC_EXAMPLE_Q395: DOC_EXAMPLE,

  ZERO_NON_POSITIVE: vector({
    change: { ...DOC_EXAMPLE.change, mean_carbon_end_tc_ha: 46.8, total_carbon_end_tc: 4680, delta_carbon_tc: -20, eproj_tco2e: 73.333, eproj_tco2e_ha_year: 0.733 },
    units: {
      status: 'AVAILABLE',
      eproj_tco2e: 73.333,
      ebase_tco2e: -172.333,
      lk_tco2e: 0,
      lower_tco2e: -30,
      upper_tco2e: 176.666,
      h_tco2e: 103.333,
      r_tco2e: -245.666,
      ratio: null,
      unc: null,
      uncertainty_deduction_tco2e: null,
      radj_tco2e: null,
      buffer_tco2e: null,
      rounding_residual_tco2e: null,
      q: 0,
      zero_reason: 'NON_POSITIVE_RELATIVE_RESULT',
      reason_codes: ['NON_POSITIVE_RELATIVE_RESULT'],
    },
    stockSeries: [
      { year: 2019, carbon: 47, baseline: 47, observed: true },
      { year: 2021, carbon: 46.9, baseline: 47.94, observed: true },
      { year: 2024, carbon: 46.8, baseline: 49.34, observed: true },
    ],
    zones: [],
    limitations: ['Отсутствие положительного результата относительно базовой линии — корректный итог, а не ошибка расчёта.'],
  }),

  ZERO_UNCERTAINTY: vector({
    evidence_status: 'REVIEW_REQUIRED',
    units: {
      status: 'AVAILABLE',
      eproj_tco2e: -262.333,
      ebase_tco2e: -172.333,
      lk_tco2e: 0,
      lower_tco2e: -193.5,
      upper_tco2e: 13.5,
      h_tco2e: 103.5,
      r_tco2e: 90,
      ratio: 1.15,
      unc: null,
      uncertainty_deduction_tco2e: null,
      radj_tco2e: null,
      buffer_tco2e: null,
      rounding_residual_tco2e: null,
      q: 0,
      zero_reason: 'UNCERTAINTY_TOO_HIGH',
      reason_codes: ['UNCERTAINTY_TOO_HIGH'],
    },
    limitations: ['Широкий диапазон обнуляет единицы по правилу кейса; данные при этом присутствуют.'],
  }),

  ZERO_ROUNDED: vector({
    units: {
      status: 'AVAILABLE',
      eproj_tco2e: -173.433,
      ebase_tco2e: -172.333,
      lk_tco2e: 0,
      lower_tco2e: -0.11,
      upper_tco2e: 0.11,
      h_tco2e: 0.11,
      r_tco2e: 1.1,
      ratio: 0.1,
      unc: 0,
      uncertainty_deduction_tco2e: 0,
      radj_tco2e: 1.1,
      buffer_tco2e: 0.165,
      rounding_residual_tco2e: 0.935,
      q: 0,
      zero_reason: 'ROUNDED_TO_ZERO',
      reason_codes: ['ROUNDED_TO_ZERO'],
    },
    limitations: ['Дробный остаток после округления в Q не включается.'],
  }),

  UNAVAILABLE_COVERAGE: vector({
    calculation_status: 'UNAVAILABLE',
    evidence_status: 'INSUFFICIENT',
    change: {
      mean_carbon_start_tc_ha: 47,
      mean_carbon_end_tc_ha: null,
      total_carbon_start_tc: null,
      total_carbon_end_tc: null,
      delta_carbon_tc: null,
      eproj_tco2e: null,
      eproj_tco2e_ha_year: null,
      normalisation_area_ha: null,
    },
    units: {
      status: 'UNAVAILABLE',
      unavailable_reason: 'INCOMPLETE_COVERAGE',
      eproj_tco2e: null,
      ebase_tco2e: null,
      lk_tco2e: null,
      lower_tco2e: null,
      upper_tco2e: null,
      h_tco2e: null,
      r_tco2e: null,
      ratio: null,
      unc: null,
      uncertainty_deduction_tco2e: null,
      radj_tco2e: null,
      buffer_tco2e: null,
      rounding_residual_tco2e: null,
      q: null,
      zero_reason: null,
      reason_codes: ['INCOMPLETE_COVERAGE'],
    },
    uncertainty: { status: 'UNAVAILABLE', unavailable_reason: 'INCOMPLETE_COVERAGE', lower_tco2e: null, upper_tco2e: null, sd_tco2e: null },
    baseline: { status: 'UNAVAILABLE', unavailable_reason: 'BASELINE_OUT_OF_COVERAGE', ebase_tco2e: null, area_ha: null },
    coverage: { biomass_fraction: 0.69, uncertainty_fraction: 0.69, baseline_fraction: 0.69, optical_paired_valid_fraction: 0.94 },
    stockSeries: [
      { year: 2019, carbon: 47, baseline: 47, observed: true },
      { year: 2020, carbon: null, baseline: 47.47, observed: false },
    ],
    zones: [],
    warnings: [
      {
        code: 'INCOMPLETE_BIOMASS_COVERAGE',
        severity: 'CRITICAL',
        message: 'Числовые данные биомассы отсутствуют на 31 % площади запроса.',
        details: { missing_fraction: 0.31 },
      },
    ],
    limitations: ['Недоступность расчёта — это не ноль единиц: показаны причина и рассчитанная часть.'],
  }),

  WEAK_OPTICS_VALID_CCI: vector({
    evidence_status: 'REVIEW_REQUIRED',
    coverage: { biomass_fraction: 1, uncertainty_fraction: 1, baseline_fraction: 1, optical_paired_valid_fraction: 0.18 },
    zones: [
      zone({
        zone_id: 'UNIT-ZONE-OPTICS',
        fact: 'SPECTRAL_CHANGE_ONLY',
        cause: 'UNKNOWN',
        cause_reason: 'Пригодных снимков на обе даты недостаточно, причина не установлена.',
        area_ha: 24.5,
        carbon_overlap_ha: 24.5,
        delta_carbon_tc: -310,
        contribution_e_tco2e: 1136.7,
        date_range: { start: '2021-06-01', end: '2021-09-30', uncertainty_days_min: null, uncertainty_days_max: null },
        geometryShare: 0.25,
      }),
    ],
    warnings: [
      {
        code: 'LOW_OPTICAL_PAIRED_VALID',
        severity: 'WARNING',
        message: 'Пригодная оптика есть лишь на 18 % площади: объяснение изменения ограничено, расчёт запаса не затронут.',
        details: { optical_paired_valid_fraction: 0.18 },
      },
    ],
    limitations: ['Оптическое качество и покрытие биомассы — разные оси; одно не заменяет другое.'],
  }),

  FIRE_SUPPORTED_LOSS: vector({
    evidence_status: 'REVIEW_REQUIRED',
    change: {
      mean_carbon_start_tc_ha: 47,
      mean_carbon_end_tc_ha: 41.2,
      total_carbon_start_tc: 4700,
      total_carbon_end_tc: 4120,
      delta_carbon_tc: -580,
      eproj_tco2e: 2126.667,
      eproj_tco2e_ha_year: 21.267,
      normalisation_area_ha: 100,
    },
    units: {
      status: 'AVAILABLE',
      eproj_tco2e: 2126.667,
      ebase_tco2e: -172.333,
      lk_tco2e: 0,
      lower_tco2e: 1700,
      upper_tco2e: 2553.3,
      h_tco2e: 426.633,
      r_tco2e: -2299,
      ratio: null,
      unc: null,
      uncertainty_deduction_tco2e: null,
      radj_tco2e: null,
      buffer_tco2e: null,
      rounding_residual_tco2e: null,
      q: 0,
      zero_reason: 'NON_POSITIVE_RELATIVE_RESULT',
      reason_codes: ['NON_POSITIVE_RELATIVE_RESULT'],
    },
    stockSeries: [
      { year: 2019, carbon: 47, baseline: 47, observed: true },
      { year: 2020, carbon: 47.3, baseline: 47.47, observed: true },
      { year: 2021, carbon: 42.9, baseline: 47.94, observed: true },
      { year: 2022, carbon: 41.2, baseline: 48.41, observed: true },
    ],
    zones: [
      zone({
        zone_id: 'UNIT-ZONE-FIRE',
        fact: 'TREE_COVER_LOSS',
        cause: 'FIRE_SUPPORTED',
        cause_reason: 'Связь зоны с событием задана помеченным набором; сама запись — официальная строка data/events.csv.',
        area_ha: 118.4,
        carbon_overlap_ha: 114.3,
        delta_carbon_tc: -486,
        contribution_e_tco2e: 1782,
        date_range: { start: '2021-08-05', end: '2021-08-22', uncertainty_days_min: 1, uncertainty_days_max: 7 },
        evidence_refs: ['RU_MORDOVIA_03_MODIS_FIRE_202108'],
        evidence: { source_id: 'MODIS_MCD64A1_061' },
        geometryShare: 0.3,
      }),
      zone({
        zone_id: 'UNIT-ZONE-FIRE-EDGE',
        fact: 'SPECTRAL_CHANGE_ONLY',
        cause: 'UNKNOWN',
        cause_reason: 'Изменение наблюдается, но продукт гарей не покрывает эту зону.',
        area_ha: 37.9,
        carbon_overlap_ha: 37.9,
        delta_carbon_tc: -94,
        contribution_e_tco2e: 344.7,
        date_range: { start: '2021-06-01', end: '2021-09-30', uncertainty_days_min: null, uncertainty_days_max: null },
        geometryShare: 0.18,
      }),
    ],
    warnings: [
      {
        code: 'FIRE_PRODUCT_RESOLUTION',
        severity: 'WARNING',
        message: 'Признак горения взят из продукта с шагом сетки около 463 м: точная площадь гари им не измеряется.',
        details: { source_id: 'MODIS_MCD64A1_061', grid_m: 463 },
      },
    ],
    limitations: [
      'Признак горения по MODIS не означает измеренную площадь гари.',
      'Доля сгоревшей территории и её вклад в E не выводятся из сообщения о событии.',
    ],
  }),

  CAUSE_UNKNOWN_LOSS: vector({
    evidence_status: 'REVIEW_REQUIRED',
    change: {
      mean_carbon_start_tc_ha: 47,
      mean_carbon_end_tc_ha: 44.1,
      total_carbon_start_tc: 4700,
      total_carbon_end_tc: 4410,
      delta_carbon_tc: -290,
      eproj_tco2e: 1063.333,
      eproj_tco2e_ha_year: 2.127,
      normalisation_area_ha: 100,
    },
    units: {
      status: 'AVAILABLE',
      eproj_tco2e: 1063.333,
      ebase_tco2e: -172.333,
      lk_tco2e: 0,
      lower_tco2e: 780,
      upper_tco2e: 1346.6,
      h_tco2e: 283.267,
      r_tco2e: -1235.666,
      ratio: null,
      unc: null,
      uncertainty_deduction_tco2e: null,
      radj_tco2e: null,
      buffer_tco2e: null,
      rounding_residual_tco2e: null,
      q: 0,
      zero_reason: 'NON_POSITIVE_RELATIVE_RESULT',
      reason_codes: ['NON_POSITIVE_RELATIVE_RESULT'],
    },
    stockSeries: [
      { year: 2019, carbon: 47, baseline: 47, observed: true },
      { year: 2021, carbon: 45.6, baseline: 47.94, observed: true },
      { year: 2024, carbon: 44.1, baseline: 49.34, observed: true },
    ],
    zones: [
      zone({
        zone_id: 'UNIT-ZONE-UNKNOWN',
        fact: 'TREE_COVER_LOSS',
        cause: 'UNKNOWN',
        cause_reason: 'Продукт изменений отмечает год потери, но причину не определяет; записи о событии для участка нет.',
        area_ha: 63.2,
        carbon_overlap_ha: 63.2,
        delta_carbon_tc: -207,
        contribution_e_tco2e: 759,
        date_range: { start: '2020-05-01', end: '2023-09-30', uncertainty_days_min: null, uncertainty_days_max: null },
        evidence: { source_id: 'GFC_2025_V113' },
        geometryShare: 0.22,
      }),
    ],
    warnings: [
      { code: 'CAUSE_NOT_ESTABLISHED', severity: 'INFO', message: 'Причина изменения не установлена: доказательств недостаточно.', details: {} },
    ],
    limitations: ['Год потери по GFC не равен измеренному изменению биомассы.'],
  }),

  RECOVERY_AFTER_LOSS: vector({
    evidence_status: 'REVIEW_REQUIRED',
    change: {
      mean_carbon_start_tc_ha: 47,
      mean_carbon_end_tc_ha: 45.9,
      total_carbon_start_tc: 4700,
      total_carbon_end_tc: 4590,
      delta_carbon_tc: -110,
      eproj_tco2e: 403.333,
      eproj_tco2e_ha_year: 0.807,
      normalisation_area_ha: 100,
    },
    units: {
      status: 'AVAILABLE',
      eproj_tco2e: 403.333,
      ebase_tco2e: -172.333,
      lk_tco2e: 0,
      lower_tco2e: 120,
      upper_tco2e: 686.6,
      h_tco2e: 283.267,
      r_tco2e: -575.666,
      ratio: null,
      unc: null,
      uncertainty_deduction_tco2e: null,
      radj_tco2e: null,
      buffer_tco2e: null,
      rounding_residual_tco2e: null,
      q: 0,
      zero_reason: 'NON_POSITIVE_RELATIVE_RESULT',
      reason_codes: ['NON_POSITIVE_RELATIVE_RESULT'],
    },
    stockSeries: [
      { year: 2015, carbon: 45.1, baseline: null, observed: true },
      { year: 2019, carbon: 47, baseline: 47, observed: true },
      { year: 2020, carbon: 44.2, baseline: 47.47, observed: true },
      { year: 2021, carbon: 41.8, baseline: 47.94, observed: true },
      { year: 2022, carbon: 43.6, baseline: 48.41, observed: true },
      { year: 2023, carbon: 44.8, baseline: 48.87, observed: true },
      { year: 2024, carbon: 45.9, baseline: 49.34, observed: true },
    ],
    zones: [
      zone({
        zone_id: 'UNIT-ZONE-RECOVERY',
        fact: 'RECOVERY_INDICATION',
        cause: 'UNKNOWN',
        cause_reason: 'Ранняя потеря покрова и последующая динамика; причина отдельно не подтверждена.',
        area_ha: 88.7,
        carbon_overlap_ha: 88.7,
        delta_carbon_tc: -142,
        contribution_e_tco2e: 520.7,
        date_range: { start: '2020-05-01', end: '2024-09-30', uncertainty_days_min: null, uncertainty_days_max: null },
        geometryShare: 0.28,
      }),
    ],
    limitations: [
      'Восстановление объявляется только по результатам наблюдений.',
      'Годы после 2024 в данных отсутствуют: прогноз фактического запаса не строится.',
    ],
  }),

  SUBPLOT_BASELINE: vector({
    change: {
      mean_carbon_start_tc_ha: 47,
      mean_carbon_end_tc_ha: 49.6,
      total_carbon_start_tc: 38016,
      total_carbon_end_tc: 40119,
      delta_carbon_tc: 2103,
      eproj_tco2e: -7711,
      eproj_tco2e_ha_year: -2.383,
      normalisation_area_ha: 808.8538,
    },
    units: {
      status: 'AVAILABLE',
      eproj_tco2e: -7711,
      ebase_tco2e: -4074.8,
      lk_tco2e: 0,
      lower_tco2e: -8850,
      upper_tco2e: -6572,
      h_tco2e: 1139,
      r_tco2e: 3636.2,
      ratio: 0.313,
      unc: 0.213,
      uncertainty_deduction_tco2e: 774.51,
      radj_tco2e: 2861.69,
      buffer_tco2e: 429.25,
      rounding_residual_tco2e: 0.44,
      q: 2432,
      reason_codes: [],
    },
    baseline: { ebase_tco2e: -4074.8, delta_tc_ha: 1.375, delta_tc: 1112.2, area_ha: 808.8538 },
    stockSeries: [
      { year: 2019, carbon: 47, baseline: 47, observed: true },
      { year: 2020, carbon: 47.6, baseline: 47.47, observed: true },
      { year: 2022, carbon: 48.7, baseline: 48.41, observed: true },
      { year: 2024, carbon: 49.6, baseline: 49.34, observed: true },
    ],
    zones: [],
    limitations: [
      'Площадь запроса берётся из сервиса; клиентская оценка площади приблизительна.',
      'Базовая линия подучастка — правило кейса, а не измеренный альтернативный сценарий.',
    ],
  }),

  UNKNOWN_DRIFT: vector({
    evidence_status: 'PARTIALLY_OBSERVED',
    units: { ...DOC_EXAMPLE.units, zero_reason: 'MANUAL_REVIEW_REQUIRED', reason_codes: ['MANUAL_REVIEW_REQUIRED'] },
    warnings: [{ code: 'ESCALATED_TO_REGISTRY', severity: 'ESCALATION', message: 'Незнакомая серьёзность и незнакомый код от сервиса.', details: {} }],
    limitations: ['Неизвестные значения показываются нейтрально и не выдаются за подтверждённые статусы.'],
  }),
};

export function scenarioNumbers(id: FixtureScenarioId): ScenarioNumbers {
  return SCENARIOS[id];
}

export interface FixtureContext {
  scenario: FixtureScenarioId;
  analysisId: string;
  geometry: Geometry;
  aoiId: string | null;
  areaHa: number;
  yearStart: number;
  yearEnd: number;
  claimedUnits: number | null;
  claimOrigin: ClaimOrigin | null;
  geometryHash: string;
  createdAt: string;
}

const POOL = 'AGB_LIVE_WOODY';
const UNIT = 'POTENTIAL_UNIT_OF_THE_CASE';

function sources(): Source[] {
  return caseSources().map((source) => ({
    source_id: source.source_id,
    product: source.product,
    version: source.version,
    license_url: source.license_url || null,
    attribution: source.attribution,
    access_date: source.accessed,
    role: 'reference',
  }));
}

function scenarioValues(q: number | null): ScenarioValues {
  const prices = casePrices();
  const value = (rub: number) => ({ price_rub: rub, value_rub: q === null ? 0 : q * rub });
  const [low, base, high] = [prices[0]?.rub_per_unit ?? 500, prices[1]?.rub_per_unit ?? 1500, prices[2]?.rub_per_unit ?? 4000];
  return {
    price_parameters_ref: 'data/methodology/parameters.csv#price_low,price_base,price_high',
    unit: 'RUB',
    low: value(low),
    base: value(base),
    high: value(high),
  };
}

/**
 * Comparison of a stated volume with q, following METHOD FREEZE v1 item 12: a claim of zero is not a
 * supported claim, it is NOT_APPLICABLE with the reason NO_POSITIVE_CLAIM.
 */
export function compareClaim(claimed: number | null, origin: ClaimOrigin | null, q: number | null, scope: Claim['scope'], scenarioYears: [number, number]): Claim {
  const base: Omit<Claim, 'status' | 'comparable' | 'gap_units' | 'supported_share' | 'mismatch_reasons' | 'scenario_gap_values'> = {
    origin,
    claimed_units: claimed,
    q,
    scope,
    scope_note:
      'Сравнение возможно только при совпадении контура, периода, пула и единиц. Заявленный объём — пользовательский или демонстрационный ввод, а не установленный факт.',
  };
  const none = { gap_units: null, supported_share: null, scenario_gap_values: null, comparable: false };
  if (claimed === null) return { ...base, ...none, status: 'NOT_PROVIDED', mismatch_reasons: [] };
  if (!Number.isFinite(claimed) || claimed < 0) return { ...base, ...none, status: 'NOT_COMPARABLE', mismatch_reasons: ['INVALID_CLAIM_VALUE'] };
  if (scope.year_start !== scenarioYears[0] || scope.year_end !== scenarioYears[1]) {
    return { ...base, ...none, status: 'NOT_COMPARABLE', mismatch_reasons: ['PERIOD_MISMATCH'] };
  }
  if (claimed === 0) {
    return { ...base, comparable: false, gap_units: 0, supported_share: null, scenario_gap_values: null, status: 'NOT_APPLICABLE', mismatch_reasons: ['NO_POSITIVE_CLAIM'] };
  }
  if (q === null) return { ...base, ...none, status: 'UNASSESSABLE', mismatch_reasons: [] };
  const gap = Math.max(claimed - q, 0);
  const share = Math.min(q / claimed, 1);
  const status = q >= claimed ? 'SUPPORTED_BY_CASE' : q > 0 ? 'PARTIALLY_SUPPORTED_BY_CASE' : 'NOT_SUPPORTED_BY_CASE';
  const prices = casePrices();
  const gapValue = (rub: number) => ({ price_rub: rub, value_rub: gap * rub });
  return {
    ...base,
    status,
    comparable: true,
    gap_units: gap,
    supported_share: share,
    mismatch_reasons: [],
    scenario_gap_values: {
      price_parameters_ref: 'data/methodology/parameters.csv#price_low,price_base,price_high',
      unit: 'RUB',
      low: gapValue(prices[0]?.rub_per_unit ?? 500),
      base: gapValue(prices[1]?.rub_per_unit ?? 1500),
      high: gapValue(prices[2]?.rub_per_unit ?? 4000),
    },
  };
}

/** Schematic cells of the offline set: one labelled grid inside the contour, never a measurement. */
export function buildCellsLayer(context: FixtureContext, numbers: ScenarioNumbers): { geojson: unknown; cells: number } {
  const bounds = bboxOf(context.geometry);
  const years = numbers.stockSeries.filter((point) => point.carbon !== null);
  const features: unknown[] = [];
  if (bounds) {
    const rows = 4;
    const cols = 4;
    const stepLon = (bounds.east - bounds.west) / cols;
    const stepLat = (bounds.north - bounds.south) / rows;
    for (let row = 0; row < rows; row += 1) {
      for (let col = 0; col < cols; col += 1) {
        const west = bounds.west + stepLon * col;
        const south = bounds.south + stepLat * row;
        const drift = ((row * cols + col) % 5) - 2;
        const carbon: Record<string, number | null> = {};
        const sd: Record<string, number> = {};
        for (const point of years) {
          carbon[String(point.year)] = point.carbon === null ? null : Number((point.carbon + drift).toFixed(2));
          sd[String(point.year)] = Number((Math.abs(drift) + 3).toFixed(2));
        }
        features.push({
          type: 'Feature',
          geometry: box(west, south, west + stepLon, south + stepLat),
          properties: {
            cell_id: `${context.aoiId ?? 'REQUEST'}:r${row}c${col}`,
            parent_aoi_id: context.aoiId,
            row,
            col,
            valid: numbers.coverage.biomass_fraction === 1 || (row * cols + col) % 3 !== 0,
            weight_ha: Number((context.areaHa / (rows * cols)).toFixed(4)),
            carbon_tc_ha: carbon,
            sd_tc_ha: sd,
            zone_id: numbers.zones[0]?.zone_id ?? null,
          },
        });
      }
    }
  }
  return { geojson: { type: 'FeatureCollection', features }, cells: features.length };
}

export function buildFixtureResult(context: FixtureContext, extras: { cellsArtifact: AnalysisResult['artifacts'][number] | null }): Omit<AnalysisResult, 'passport'> {
  const numbers = SCENARIOS[context.scenario];
  const label = FIXTURE_LABELS[context.scenario];
  const defaults = SCENARIO_DEFAULTS[context.scenario];
  const complete = numbers.coverage.biomass_fraction >= 1;
  const calculated = Number((context.areaHa * numbers.coverage.biomass_fraction).toFixed(4));

  const areas: Areas = {
    requested_ha: context.areaHa,
    calculated_ha: calculated,
    missing_ha: Number(Math.max(0, context.areaHa - calculated).toFixed(4)),
    area_difference_ha: Number((calculated - context.areaHa).toFixed(6)),
    complete,
    parent_parts: context.aoiId ? [{ aoi_id: context.aoiId, area_ha: calculated }] : [],
  };

  const timeline: TimelinePoint[] = numbers.stockSeries.map((point) => ({
    year: point.year,
    mean_agb_tdm_ha: point.carbon === null ? null : Number((point.carbon / 0.47).toFixed(3)),
    mean_carbon_tc_ha: point.carbon,
    total_carbon_tc: point.carbon === null ? null : Number((point.carbon * context.areaHa).toFixed(2)),
    baseline_carbon_tc_ha: point.baseline,
    area_ha: context.areaHa,
    coverage: point.observed ? numbers.coverage.biomass_fraction : 0,
    in_period: point.year >= context.yearStart && point.year <= context.yearEnd,
    source_ref: point.observed ? 'CCI_V7' : null,
  }));

  const change: Change = {
    year_start: context.yearStart,
    year_end: context.yearEnd,
    mean_carbon_start_tc_ha: null,
    mean_carbon_end_tc_ha: null,
    total_carbon_start_tc: null,
    total_carbon_end_tc: null,
    delta_carbon_tc: null,
    eproj_tco2e: null,
    eproj_tco2e_ha_year: null,
    normalisation_area_ha: context.areaHa,
    sign_convention: 'Положительное E — потеря учитываемого пула за период, отрицательное — накопление.',
    pool: POOL,
    ...numbers.change,
  };

  const units: Units = {
    status: 'AVAILABLE',
    unavailable_reason: null,
    zero_reason: null,
    eproj_tco2e: null,
    ebase_tco2e: null,
    lk_tco2e: 0,
    lower_tco2e: null,
    upper_tco2e: null,
    h_tco2e: null,
    r_tco2e: null,
    ratio: null,
    unc: null,
    uncertainty_deduction_tco2e: null,
    radj_tco2e: null,
    buffer_tco2e: null,
    rounding_residual_tco2e: null,
    q: null,
    reason_codes: [],
    ...numbers.units,
  };

  const uncertainty: Uncertainty = {
    status: 'AVAILABLE',
    unavailable_reason: null,
    lower_tco2e: units.lower_tco2e,
    upper_tco2e: units.upper_tco2e,
    sd_tco2e: units.h_tco2e,
    method: 'INDEPENDENT_NATIVE_CELLS',
    interval_kind: 'SCENARIO',
    assumptions: IPCC_ASSUMPTIONS,
    sensitivity: [
      {
        label: 'INDEPENDENT_NATIVE_CELLS_RHO_0',
        spatial_dependence: 'INDEPENDENT_NATIVE_CELLS',
        temporal_correlation: 0,
        sd_tco2e: units.h_tco2e,
        lower_tco2e: units.lower_tco2e,
        upper_tco2e: units.upper_tco2e,
        half_width_tco2e: units.h_tco2e,
      },
      {
        label: 'FULL_SPATIAL_CORRELATION_RHO_0',
        spatial_dependence: 'FULL_SPATIAL_CORRELATION',
        temporal_correlation: 0,
        sd_tco2e: units.h_tco2e === null ? null : Number((units.h_tco2e * 4).toFixed(3)),
        lower_tco2e: units.lower_tco2e === null || units.h_tco2e === null ? null : Number((units.lower_tco2e - units.h_tco2e * 3).toFixed(3)),
        upper_tco2e: units.upper_tco2e === null || units.h_tco2e === null ? null : Number((units.upper_tco2e + units.h_tco2e * 3).toFixed(3)),
        half_width_tco2e: units.h_tco2e === null ? null : Number((units.h_tco2e * 4).toFixed(3)),
      },
    ],
    ...numbers.uncertainty,
  };

  const baseline: Baseline = {
    status: 'AVAILABLE',
    unavailable_reason: null,
    baseline_id: 'HIST-AGB-2015-2019-v1',
    kind: 'сценарное допущение',
    area_ha: context.areaHa,
    delta_tc: null,
    delta_tc_ha: null,
    ebase_tco2e: units.ebase_tco2e,
    parts: context.aoiId ? [{ aoi_id: context.aoiId, area_ha: context.areaHa, stock_start_tc_ha: null, stock_end_tc_ha: null, delta_tc_ha: null, delta_tc: null, clipped_at_zero: false }] : [],
    ...numbers.baseline,
  };

  const scenes: Scene[] = scenesInPeriod(context.aoiId, context.yearStart, context.yearEnd).map((scene) => ({
    scene_key: scene.scene_key,
    aoi_id: scene.aoi_id,
    datetime_utc: scene.datetime_utc,
    year: scene.year,
    usable_fraction: scene.scl_valid_fraction,
    note: 'Метаданные сцены — официальная таблица data/scenes.csv.',
  }));

  const evidence: Evidence = {
    status: numbers.evidence_status,
    optical_paired_valid_fraction: numbers.coverage.optical_paired_valid_fraction,
    analysed_parent: context.aoiId,
    scenes,
    reconciliation: null,
    warnings: numbers.warnings,
  };

  const zones: Zone[] = numbers.zones.map((item, index) => {
    const { geometryShare, ...rest } = item;
    return {
      ...rest,
      artifact_ref: extras.cellsArtifact?.artifact_id ?? null,
      geometry: zoneGeometry(context.geometry, index, numbers.zones.length, geometryShare ?? 0.25),
    };
  });

  return {
    fixture: { ...label, kind: label.kind },
    identity: {
      analysis_id: context.analysisId,
      input_hash: context.geometryHash,
      geometry_hash: context.geometryHash,
      schema_version: 'carbon-lens-api/2.0.0',
      method_version: 'carbon-lens-frontend-offline-set/2.0.0',
      dataset_version: 'sr-data-case2/2026-09-16',
      dataset_hash: '0xd8723225a1f66f1ff1890439e6e561f3a28a94f6a81b63b5db99a73579fc22a8',
      source_manifest_hash: '0x016d27e54f3910ef4686ea11dea1b526c068ce61d4433437ea232355adeba9ec',
      parameters_hash: '0x2bca8c22e73231f4b7ae256657fba5e8e8ec4916cd934a0c4e6b92000da37ec6',
      code_sha: null,
    },
    run: {
      run_id: `offline-${context.analysisId}`,
      created_at: context.createdAt,
      dataset_origin: 'STUB_FIXTURE',
      raster_adapter: 'frontend-offline-set',
      carbon_adapter: 'frontend-offline-set',
    },
    request: {
      geometry: context.geometry,
      aoi_id: context.aoiId,
      year_start: context.yearStart,
      year_end: context.yearEnd,
      claimed_units: context.claimedUnits,
      claim_origin: context.claimOrigin,
      include_optical: true,
    },
    calculation_status: numbers.calculation_status,
    evidence_status: numbers.evidence_status,
    areas,
    coverage: numbers.coverage,
    timeline,
    change,
    uncertainty,
    baseline,
    units,
    scenario_values: scenarioValues(units.q),
    claim: compareClaim(
      context.claimedUnits,
      context.claimOrigin,
      units.q,
      { geometry_hash: context.geometryHash, year_start: context.yearStart, year_end: context.yearEnd, pool: POOL, unit: UNIT },
      defaults.years,
    ),
    zones,
    evidence,
    sources: sources(),
    artifacts: extras.cellsArtifact ? [extras.cellsArtifact] : [],
    limitations: [
      'Учитывается только живая надземная древесная биомасса; это не полный баланс экосистемы.',
      'Базовая линия задана сценарными правилами кейса по истории 2015–2019; она не доказывает дополнительность.',
      'Сценарная стоимость использует заданные кейсом цены. Это не рыночная котировка и не гарантированная выручка.',
      ...numbers.limitations,
    ],
    notes: numbers.notes,
  };
}

function zoneGeometry(geometry: Geometry, index: number, total: number, share: number): Geometry | null {
  const bounds = bboxOf(geometry);
  if (!bounds || total <= 0) return null;
  const width = bounds.east - bounds.west;
  const height = bounds.north - bounds.south;
  const step = width / (total + 1);
  const centreLon = bounds.west + step * (index + 1);
  const centreLat = bounds.south + height * (index % 2 === 0 ? 0.42 : 0.62);
  const halfLon = Math.min(step * 0.34, width * share);
  const halfLat = height * share * 0.5;
  return box(centreLon - halfLon, centreLat - halfLat, centreLon + halfLon, centreLat + halfLat);
}

export const ZONE_GEOMETRY_NOTE =
  'Контур зоны схематичен: положение задано помеченным набором, а не детекцией по растрам.';
