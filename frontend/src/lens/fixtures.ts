import { caseSources, casePrices } from './data';
import type { LensResult, LensRequest, LensZone, PriceScenario } from './types';

// Labelled preview values for the Carbon Lens workspace. Nothing here is a computed result for a real AOI:
// DOC_EXAMPLE reproduces the conditional example printed in doc/Постановка_задачи (Q = 395);
// UNIT_TEST_VECTOR entries are logic vectors for branches the UI must be able to show.
// Every scientific number is supplied ready-made; the screen never recomputes them.
// Territories, scenes, fire events, the baseline table, prices and the source registry are NOT here:
// they are read from the official data/ archive through src/lens/data.ts.

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

/** Price scenarios come from data/methodology/parameters.csv, not from this file. */
export const PRICES: PriceScenario[] = casePrices();

const SOURCES: LensResult['sources'] = caseSources().map((source) => ({
  source_id: source.source_id,
  title: source.product,
  version: source.version,
  license: source.license_url || source.license,
  attribution: source.attribution,
  accessed: source.accessed,
}));

const IPCC_ASSUMPTIONS = [
  'CF = 0.47 т C/т сухого вещества (IPCC 2006, том 4, таблица 4.3).',
  'Перевод в CO₂-эквивалент по отношению 44/12.',
  'Учитывается только живая надземная древесная биомасса.',
];

type Scenario = Omit<LensResult, 'request' | 'area_ha' | 'layers'>;

export interface ScenarioDefaults {
  areaHa: number;
  years: [number, number];
  /** AOI the guided demo selects for this vector; the numbers still belong to the vector, not to the AOI. */
  aoiId: string | null;
  sampleRequestId?: string;
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

const FIXTURE_PROVENANCE: LensResult['provenance'] = {
  official: [
    'Территории, контуры и площади — data/areas.csv и data/areas.geojson',
    'Базовая линия — data/methodology/baseline.csv',
    'Сцены Sentinel-2, облачность и доля пригодных пикселей — data/scenes.csv',
    'События и продукты гарей — data/events.csv',
    'Коэффициенты, вычеты, резерв и цены — data/methodology/parameters.csv',
    'Источники, лицензии и ограничения — data/sources.csv',
  ],
  computed_by: 'FIXTURE',
  computed_note:
    'Запас, E, R, неопределённость, покрытие и Q взяты из помеченного набора, а не рассчитаны по растрам выбранного участка.',
};

function zone(input: Omit<LensZone, 'geometry' | 'geometry_note'>): LensZone {
  return {
    ...input,
    geometry: null,
    geometry_note: 'Контур зоны схематичен: положение задано помеченным набором, а не детекцией по растрам.',
  };
}

const DOC_EXAMPLE: Scenario = {
  fixture: {
    kind: 'DOC_EXAMPLE',
    label: 'Условный пример из постановки задачи',
    note: 'Числа взяты из doc/Постановка_задачи (100 га, один год, биомасса 100 → 104 т/га). Это не расчёт по выбранному участку data/.',
    acceptance_id: null,
    acceptance_note: 'Числовой эталон формул: R → вычет за неопределённость → резерв → округление → Q = 395.',
  },
  provenance: FIXTURE_PROVENANCE,
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
    zone({
      zone_id: 'DOC-EXAMPLE-ZONE-1',
      label: 'Условная зона прироста',
      area_ha: 100,
      date_min: '2019-01-01',
      date_max: '2020-12-31',
      delta_stock_tc: 188,
      contribution_e_tco2e: -689.333,
      cause_status: 'NOT_ESTABLISHED',
      evidence_source_id: null,
      evidence_event_id: null,
      evidence_note: 'В примере постановки причина изменения не устанавливается.',
      artifact_ids: [],
    }),
  ],
  optical: { scene_keys: [], note: 'Условный пример не привязан к конкретным сценам Sentinel-2.' },
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
  acceptance: { id: string | null; note: string | null } = { id: null, note: null },
): Scenario {
  const base: Scenario = {
    ...DOC_EXAMPLE,
    fixture: { kind: 'UNIT_TEST_VECTOR', label, note, acceptance_id: acceptance.id, acceptance_note: acceptance.note },
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
  {
    id: 'S1',
    note: 'Контроль по GFC: отсутствие зарегистрированных потерь покрова не гарантирует ни постоянную биомассу, ни положительный Q.',
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
    zones: [],
    limitations: ['Недоступность расчёта — это не ноль единиц: показана причина и рассчитанная часть.'],
  },
  {
    id: 'S7',
    note: 'Контур выходит за доступное покрытие: частичный результат и q = null. Это проверка границ, а не подмена растра.',
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
      zone({
        zone_id: 'UNIT-ZONE-OPTICS',
        label: 'Зона изменения без пригодной оптики',
        area_ha: 24.5,
        date_min: '2021-06-01',
        date_max: '2021-09-30',
        delta_stock_tc: -310,
        contribution_e_tco2e: 1136.7,
        cause_status: 'NOT_ESTABLISHED',
        evidence_source_id: null,
        evidence_event_id: null,
        evidence_note: 'Причина не установлена: пригодных снимков на обе даты недостаточно.',
        artifact_ids: [],
      }),
    ],
    optical: {
      scene_keys: [],
      note: 'Пригодность сцен на обе даты ограничена; метаданные доступных сцен показаны из data/scenes.csv.',
    },
    limitations: ['Оптическое качество и покрытие биомассы — разные оси; одно не заменяет другое.'],
  },
  {
    id: 'S6',
    note: 'Облачная сцена не делает покрытие CCI неполным: оси качества разделены, альтернативные сцены видны в таблице наблюдений.',
  },
);

const FIRE_SUPPORTED_LOSS = unitVector(
  'FIRE_SUPPORTED_LOSS',
  'Потеря с признаком горения по продукту MODIS',
  'Логический вектор: зона потери связана со строкой data/events.csv; признак горения — продукт, а не измеренная площадь гари.',
  {
    evidence_status: 'REVIEW_REQUIRED',
    stock: { ...DOC_EXAMPLE.stock, mean_start_tc_ha: 47, mean_end_tc_ha: 41.2, total_start_tc: 4700, total_end_tc: 4120, delta_tc: -580, e_tco2e: 2126.667, e_tco2e_ha_yr: 21.267 },
    uncertainty: { ...DOC_EXAMPLE.uncertainty, lower_tco2e: 1700, upper_tco2e: 2553.3, h_tco2e: 426.633 },
    units: {
      status: 'AVAILABLE',
      q: 0,
      reason: 'NON_POSITIVE_RELATIVE_RESULT',
      reason_detail: 'Период закончился ниже базовой линии: единицы по условиям кейса не образуются.',
      r_tco2e: -2299,
      h_over_r: null,
      unc_fraction: null,
      r_adj_tco2e: null,
      buffer_tco2e: null,
      leakage_tco2e: 0,
      rounding_remainder_tco2e: null,
    },
    timeline: [
      { year: 2019, stock_tc_ha: 47, baseline_tc_ha: 47, observed: true, in_selected_period: true },
      { year: 2020, stock_tc_ha: 47.3, baseline_tc_ha: 47.47, observed: true, in_selected_period: true },
      { year: 2021, stock_tc_ha: 42.9, baseline_tc_ha: 47.94, observed: true, in_selected_period: true },
      { year: 2022, stock_tc_ha: 41.2, baseline_tc_ha: 48.41, observed: true, in_selected_period: true },
    ],
    zones: [
      zone({
        zone_id: 'UNIT-ZONE-FIRE',
        label: 'Зона потери с признаком горения',
        area_ha: 118.4,
        date_min: '2021-08-05',
        date_max: '2021-08-22',
        delta_stock_tc: -486,
        contribution_e_tco2e: 1782,
        cause_status: 'SUPPORTED',
        evidence_source_id: 'MODIS_MCD64A1_061',
        evidence_event_id: 'RU_MORDOVIA_03_MODIS_FIRE_202108',
        evidence_note: 'Связь зоны с событием задана помеченным набором; сама запись события — официальная строка data/events.csv.',
        artifact_ids: [],
      }),
      zone({
        zone_id: 'UNIT-ZONE-FIRE-EDGE',
        label: 'Смежная зона без подтверждения причины',
        area_ha: 37.9,
        date_min: '2021-06-01',
        date_max: '2021-09-30',
        delta_stock_tc: -94,
        contribution_e_tco2e: 344.7,
        cause_status: 'NOT_ESTABLISHED',
        evidence_source_id: null,
        evidence_event_id: null,
        evidence_note: 'Изменение наблюдается, но продукт гарей не покрывает эту зону.',
        artifact_ids: [],
      }),
    ],
    limitations: [
      'Признак горения по MODIS не означает измеренную площадь гари: шаг сетки около 463 м, дата имеет погрешность.',
      'Доля сгоревшей территории и её вклад в E не выводятся из сообщения МЧС.',
    ],
  },
  {
    id: 'S2',
    note: 'Изменение и свидетельства пожара августа 2021 года: показаны площадь зоны и вклад в E, без выдуманной доли «половина леса».',
  },
);

const CAUSE_UNKNOWN_LOSS = unitVector(
  'CAUSE_UNKNOWN_LOSS',
  'Потеря покрова с неустановленной причиной',
  'Логический вектор: изменение наблюдается, но достаточных свидетельств причины нет.',
  {
    evidence_status: 'REVIEW_REQUIRED',
    stock: { ...DOC_EXAMPLE.stock, mean_end_tc_ha: 44.1, total_end_tc: 4410, delta_tc: -290, e_tco2e: 1063.333, e_tco2e_ha_yr: 10.633 },
    uncertainty: { ...DOC_EXAMPLE.uncertainty, lower_tco2e: 780, upper_tco2e: 1346.6, h_tco2e: 283.267 },
    units: {
      status: 'AVAILABLE',
      q: 0,
      reason: 'NON_POSITIVE_RELATIVE_RESULT',
      reason_detail: 'Результат периода ниже базовой линии.',
      r_tco2e: -1235.666,
      h_over_r: null,
      unc_fraction: null,
      r_adj_tco2e: null,
      buffer_tco2e: null,
      leakage_tco2e: 0,
      rounding_remainder_tco2e: null,
    },
    zones: [
      zone({
        zone_id: 'UNIT-ZONE-UNKNOWN',
        label: 'Мозаика потерь покрова',
        area_ha: 63.2,
        date_min: '2020-05-01',
        date_max: '2023-09-30',
        delta_stock_tc: -207,
        contribution_e_tco2e: 759,
        cause_status: 'NOT_ESTABLISHED',
        evidence_source_id: 'GFC_2025_V113',
        evidence_event_id: null,
        evidence_note: 'Продукт изменений отмечает год потери, но причину не определяет; записи о событии для участка нет.',
        artifact_ids: [],
      }),
    ],
    limitations: [
      'Причина не установлена: наблюдается изменение, пожар или вырубка не доказаны.',
      'Год потери по GFC не равен измеренному изменению биомассы.',
    ],
  },
  { id: 'S3', note: 'Потери покрова без достаточных свидетельств: статус причины остаётся «не установлена».' },
);

const RECOVERY_AFTER_LOSS = unitVector(
  'RECOVERY_AFTER_LOSS',
  'История потери и последующая динамика',
  'Логический вектор: после потери наблюдается прирост, но период в целом остаётся ниже базовой линии.',
  {
    evidence_status: 'REVIEW_REQUIRED',
    stock: { ...DOC_EXAMPLE.stock, mean_start_tc_ha: 47, mean_end_tc_ha: 45.9, total_end_tc: 4590, delta_tc: -110, e_tco2e: 403.333, e_tco2e_ha_yr: 0.807 },
    uncertainty: { ...DOC_EXAMPLE.uncertainty, lower_tco2e: 120, upper_tco2e: 686.6, h_tco2e: 283.267 },
    units: {
      status: 'AVAILABLE',
      q: 0,
      reason: 'NON_POSITIVE_RELATIVE_RESULT',
      reason_detail: 'Прирост после потери не вывел период выше базовой линии.',
      r_tco2e: -1097.333,
      h_over_r: null,
      unc_fraction: null,
      r_adj_tco2e: null,
      buffer_tco2e: null,
      leakage_tco2e: 0,
      rounding_remainder_tco2e: null,
    },
    timeline: [
      { year: 2015, stock_tc_ha: 45.1, baseline_tc_ha: null, observed: true, in_selected_period: false },
      { year: 2019, stock_tc_ha: 47, baseline_tc_ha: 47, observed: true, in_selected_period: true },
      { year: 2020, stock_tc_ha: 44.2, baseline_tc_ha: 47.47, observed: true, in_selected_period: true },
      { year: 2021, stock_tc_ha: 41.8, baseline_tc_ha: 47.94, observed: true, in_selected_period: true },
      { year: 2022, stock_tc_ha: 43.6, baseline_tc_ha: 48.41, observed: true, in_selected_period: true },
      { year: 2023, stock_tc_ha: 44.8, baseline_tc_ha: 48.87, observed: true, in_selected_period: true },
      { year: 2024, stock_tc_ha: 45.9, baseline_tc_ha: 49.34, observed: true, in_selected_period: true },
    ],
    zones: [
      zone({
        zone_id: 'UNIT-ZONE-RECOVERY',
        label: 'Зона ранней потери с последующим приростом',
        area_ha: 88.7,
        date_min: '2020-05-01',
        date_max: '2024-09-30',
        delta_stock_tc: -142,
        contribution_e_tco2e: 520.7,
        cause_status: 'NOT_ESTABLISHED',
        evidence_source_id: 'GFC_2025_V113',
        evidence_event_id: null,
        evidence_note: 'Ранняя потеря покрова и последующая динамика; причина отдельно не подтверждена.',
        artifact_ids: [],
      }),
    ],
    limitations: [
      'Восстановление объявляется только по результатам наблюдений, а не по ожиданию.',
      'Годы после 2024 в данных отсутствуют: прогноз фактического запаса не строится.',
    ],
  },
  { id: 'S4', note: 'История и последующая динамика: прирост виден, но восстановление не объявляется без результата выше базовой линии.' },
);

const SUBPLOT_BASELINE = unitVector(
  'SUBPLOT_BASELINE',
  'Подучасток: удельная базовая линия родителя',
  'Логический вектор: базовая линия родительского участка применена к площади запроса.',
  {
    evidence_status: 'SUFFICIENT',
    stock: { ...DOC_EXAMPLE.stock, mean_start_tc_ha: 47, mean_end_tc_ha: 49.6, delta_tc: 2103, total_start_tc: 38016, total_end_tc: 40119, e_tco2e: -7711, e_tco2e_ha_yr: -2.383 },
    baseline: {
      baseline_id: 'HIST-AGB-2015-2019-v1',
      kind: 'сценарное допущение',
      e_base_tco2e: -4074.8,
      stock_start_tc_ha: 47,
      stock_end_tc_ha: 48.88,
      applied_to_area_ha: 808.8538,
      parent_aoi_id: 'RU_VOLOGDA_02',
      note: 'Удельная базовая линия родительского участка применена к площади запроса (правило из data/sample_requests.geojson).',
    },
    uncertainty: { ...DOC_EXAMPLE.uncertainty, lower_tco2e: -8850, upper_tco2e: -6572, h_tco2e: 1139 },
    units: {
      status: 'AVAILABLE',
      q: 2455,
      reason: null,
      reason_detail: null,
      r_tco2e: 3636.2,
      h_over_r: 0.313,
      unc_fraction: 0.1,
      r_adj_tco2e: 3272.58,
      buffer_tco2e: 490.887,
      leakage_tco2e: 0,
      rounding_remainder_tco2e: 0.693,
    },
    limitations: [
      'Площадь запроса берётся из сервиса; клиентская оценка площади приблизительна.',
      'Базовая линия подучастка — правило кейса, а не измеренный альтернативный сценарий.',
    ],
  },
  {
    id: 'S5',
    note: 'Подучасток ~808,85 га: удельная базовая линия родителя применяется к реальной площади запроса; нарисованный допустимый контур обрабатывается так же.',
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
  FIRE_SUPPORTED_LOSS,
  CAUSE_UNKNOWN_LOSS,
  RECOVERY_AFTER_LOSS,
  SUBPLOT_BASELINE,
  UNKNOWN_DRIFT,
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

export const SCENARIO_DEFAULTS: Record<FixtureScenarioId, ScenarioDefaults> = {
  DOC_EXAMPLE_Q395: { areaHa: 100, years: [2019, 2020], aoiId: null },
  ZERO_NON_POSITIVE: { areaHa: 100, years: [2019, 2024], aoiId: 'RU_TVER_01' },
  ZERO_UNCERTAINTY: { areaHa: 100, years: [2019, 2020], aoiId: null },
  ZERO_ROUNDED: { areaHa: 100, years: [2019, 2020], aoiId: null },
  UNAVAILABLE_COVERAGE: { areaHa: 100, years: [2019, 2020], aoiId: null },
  WEAK_OPTICS_VALID_CCI: { areaHa: 100, years: [2021, 2022], aoiId: 'RU_MORDOVIA_03' },
  FIRE_SUPPORTED_LOSS: { areaHa: 100, years: [2020, 2022], aoiId: 'RU_MORDOVIA_03' },
  CAUSE_UNKNOWN_LOSS: { areaHa: 100, years: [2019, 2024], aoiId: 'RU_VOLOGDA_02' },
  RECOVERY_AFTER_LOSS: { areaHa: 100, years: [2019, 2024], aoiId: 'RU_MORDOVIA_04' },
  SUBPLOT_BASELINE: { areaHa: 808.8538, years: [2020, 2024], aoiId: null, sampleRequestId: 'CHECK_TRANSFER_01' },
  UNKNOWN_DRIFT: { areaHa: 100, years: [2019, 2020], aoiId: null },
};

export function buildFixtureResult(id: FixtureScenarioId, request: LensRequest, areaHa: number): LensResult {
  const rest = FIXTURE_SCENARIOS[id];
  return {
    ...structuredClone(rest),
    layers: [],
    request: structuredClone(request),
    area_ha: areaHa,
    stock: { ...structuredClone(rest.stock), year_start: request.year_start, year_end: request.year_end },
  };
}
