// Русский текст для всего, что сервис присылает кодом или английской строкой.
//
// Часть сообщений приходит из растрового ядра по-английски (`RASTER_LIMITATION`, `cause_reason`,
// provenance артефактов). Переводить их на стороне сервиса нельзя — это контракт, который читают и
// тесты RS. Поэтому перевод живёт здесь: по коду, когда код есть, и по шаблону текста, когда сервис
// присылает прозу. Неизвестный текст возвращается как есть — показать английскую строку честнее,
// чем выдумать русскую.

/** Короткое русское имя предупреждения по его коду. Префикс `RS_` необязателен. */
const WARNING_RU: Record<string, string> = {
  INCOMPLETE_COVERAGE: 'Покрытие неполное',
  ZERO_AGB_CELLS: 'Есть ячейки с нулевым запасом',
  INVALID_CELLS: 'Есть ячейки без значения',
  CELL_WEIGHT_SUM_DIFFERS: 'Сумма весов ячеек расходится',
  MODEL_YEARS_NOT_OBSERVATIONS: 'Годы продукта — модельные оценки',
  OPTICAL_DISABLED: 'Оптика отключена для этого расчёта',
  NO_SCENE_PAIR: 'Нет пары снимков на период',
  LOW_PAIRED_COVERAGE: 'Мало сравнимых наблюдений',
  LOW_OPTICAL_PAIRED_VALID: 'Мало сравнимых наблюдений',
  SCENE_REJECTED: 'Снимок отклонён отбором',
  SEASONAL_GAP: 'Снимки из разных сезонов',
  RADIOMETRIC_BASELINE_DIFFERS: 'Разные версии обработки снимков',
  RADIOMETRIC_OFFSET_MIXED: 'Снимки на разных радиометрических соглашениях',
  CHANGE_EVIDENCE_UNAVAILABLE: 'Зоны изменений не построены',
  CHANGE_EXTENT_UNIFORM: 'Изменение покрывает почти весь участок',
  FIRE_PRODUCT_ABSENT: 'Продукт гарей не выдан',
  ZONE_CAUSE_UNKNOWN: 'У части зон причина не установлена',
  RECOVERY_NOT_RECOVERED_CARBON: 'Признак восстановления — не восстановленный углерод',
  ZONE_ATTRIBUTION_RESOLUTION: 'Зоны и ячейки углерода разного размера',
  ZONES_FIRST_PARENT_ONLY: 'Учтена только первая родительская зона',
  OBSERVATION_GAP_ZONES: 'Есть участки без сравнимых наблюдений',
  UNSTRUCTURED_WARNING: 'Предупреждение сервиса',
  // Углеродный движок
  AREA_NOT_FULLY_COVERED: 'Площадь покрыта не полностью',
  BASELINE_DECLINING: 'Базовая линия убывает',
  BASELINE_FIXED: 'Базовая линия закреплена',
  BASELINE_PROJECTION: 'Базовая линия продолжена сценарно',
  CANONICAL_E_DISAGREES: 'Расхождение с канонической величиной E',
  CASE_UNITS: 'Единицы — по правилам кейса',
  CELLS_EXCLUDED: 'Часть ячеек исключена',
  CLAIM_GAP_SCENARIO: 'Разрыв заявления оценён сценарно',
  CLAIM_INPUT_LABEL: 'Заявленный объём — ввод пользователя',
  CLAIM_ZERO: 'Заявлен нулевой объём',
  COVERAGE_INCOMPLETE: 'Покрытие неполное',
  NON_POSITIVE_RESULT: 'Результат не положителен',
  OPTICAL_QUALITY_SEPARATE: 'Качество оптики считается отдельно',
  PASSPORT_NEW_OBSERVATION: 'Это новое наблюдение, а не пересчёт',
  POOL_LIMITED: 'Учитывается один пул углерода',
  PROJECTION_CLIPPED: 'Сценарий обрезан по правилам кейса',
  PROVISIONAL_INPUT: 'Предварительные входные данные',
  RESEARCH_VARIANT: 'Исследовательский вариант',
  RESULT_FROM_DECLINING_BASELINE: 'Результат получен на убывающей базовой линии',
  ROUNDED_BELOW_ONE_UNIT: 'После вычетов осталось меньше одной единицы',
  SCENARIO_INTERVAL: 'Интервал — сценарный',
  SCENARIO_PRICES: 'Цены — сценарные',
  STOP_RULE_APPLIED: 'Применено правило остановки',
  UNCERTAINTY_COVERAGE_NOT_REPORTED: 'Покрытие неопределённости не сообщено',
  USER_PRICE_SCENARIO: 'Цена задана читателем',
  VALUE_WITHOUT_UNITS: 'Стоимость без подтверждённых единиц',
  POOL_SCOPE: 'Границы учитываемого пула',
  SIGN_CONVENTION: 'Соглашение о знаке',
  BASELINE_IS_A_SCENARIO: 'Базовая линия — сценарий',
  SCENARIO_VALUE_ONLY: 'Стоимость только сценарная',
  RASTER_LIMITATION: 'Ограничение наблюдений',
};

/** Русское имя кода. `RS_ZONE_CAUSE_UNKNOWN` и `ZONE_CAUSE_UNKNOWN` — один и тот же код. */
export function codeRu(code: string | null | undefined): string | null {
  if (!code) return null;
  const bare = code.replace(/^RS_/, '').replace(/^CARBON_/, '');
  return WARNING_RU[bare] ?? WARNING_RU[code] ?? null;
}

type Rule = [RegExp, (match: RegExpMatchArray) => string];

/** Проценты и числа сервиса переносятся в русский текст как есть, без пересчёта. */
const RULES: Rule[] = [
  [/^partial coverage: ([\d.]+) ha of the request has no biomass map/i,
    (m) => `Покрытие неполное: на ${m[1]} га запроса нет карты биомассы. Для частичного запроса потенциальные единицы не считаются.`],
  [/^optical reading was switched off for this run/i,
    () => 'Оптическое чтение для этого расчёта было отключено: покрытие оптики отсутствует, а не равно нулю; на результат по биомассе это не влияет.'],
  [/^no Sentinel-2 pair spans the requested years/i,
    () => 'Ни одна пара снимков Sentinel-2 не покрывает запрошенные годы: покрытие оптики показано как нулевое, о покрытии биомассы это ничего не говорит.'],
  [/^paired-valid optical coverage is only ([\d.,]+%)/i,
    (m) => `Сравнимых оптических наблюдений всего ${m[1]}: читать изменение по снимкам на этом запросе можно лишь ограниченно.`],
  [/^(\d+) of (\d+) cells carry a published AGB of zero/i,
    (m) => `${m[1]} из ${m[2]} ячеек имеют опубликованный нулевой запас хотя бы на одну дату. Ноль — это значение продукта: он суммируется как ноль, а не отбрасывается.`],
  [/^(\d+) of (\d+) cells have no biomass value in both requested years/i,
    (m) => `${m[1]} из ${m[2]} ячеек не имеют значения биомассы ни на один из запрошенных годов и помечены как непригодные: они исключены из запаса, а не учтены нулём.`],
  [/^CCI years are annual model estimates/i,
    () => 'Годы CCI — это годовые модельные оценки, а не наблюдения на дату; даты съёмки Sentinel приводятся отдельно.'],
  [/^timeline covers (\d+)-(\d+) on the support of the requested period/i,
    (m) => `История ${m[1]}–${m[2]} построена на носителе запрошенного периода, поэтому любой год сопоставим с любым другим.`],
  [/^MODIS MCD64A1 was not supplied for ([A-Z0-9_]+)/i,
    (m) => `Продукт гарей MODIS MCD64A1 для участка ${m[1]} не выдан. Это отсутствие продукта, а не доказательство того, что ничего не горело.`],
  [/^(\d+) of (\d+) disturbance zones have no established cause/i,
    (m) => `У ${m[1]} из ${m[2]} зон нарушений причина не установлена — они помечены как «причина не установлена».`],
  [/^recovery zones are a spectral indication of regrowth/i,
    () => 'Зоны восстановления — это спектральный признак повторного роста, а не доказательство того, что углерод восстановился.'],
  [/^the two scenes are (\d+) days apart in the season/i,
    (m) => `Между снимками ${m[1]} дней внутри сезона: часть разницы индексов — фенология, а не нарушение.`],
  [/^change zones cover ([\d.,]+%) of the request/i,
    (m) => `Зоны изменений покрывают ${m[1]} запроса. Настолько однородное изменение чаще означает разницу между двумя наблюдениями, чем нарушение на земле.`],
  [/^the two scenes come from different processing baselines on the same radiometric offset convention/i,
    () => 'Снимки сделаны разными версиями обработки при одном радиометрическом соглашении: часть однородной разницы индекса — разница обработчика, а не изменение на земле. Крупного артефакта смещения здесь нет.'],
  [/^the two scenes straddle the 04\.00 offset change/i,
    () => 'Снимки лежат по разные стороны смены соглашения 04.00, и пары на одном соглашении не нашлось. На контрольном участке это само по себе даёт медианный dNBR около −0,86 и помечает всю площадь как восстановление, поэтому такое сравнение читать как изменение нельзя.'],
  [/^zones are detected on the 20 m Sentinel grid/i,
    () => 'Зоны выделяются на сетке Sentinel 20 м, а углерод берётся из ячеек CCI около 100 м: предполагается, что изменение внутри ячейки распределено равномерно.'],
  [/^change zones were not produced: (.+)$/i,
    (m) => `Зоны изменений не построены: ${serviceTextRu(m[1])}`],
  [/^([\d.,]+%) of the request could not be compared between the two dates/i,
    (m) => `${m[1]} запроса нельзя сравнить между двумя датами; эта часть опубликована отдельным слоем. Это не площадь, где ничего не произошло.`],
  [/is published as its own layer; it is not an area where nothing happened/i,
    () => 'Часть запроса нельзя сравнить между двумя датами; она опубликована отдельным слоем. Это не площадь, где ничего не произошло.'],
  [/^native ESA CCI model cells, not a resampled surface/i,
    () => 'Родные модельные ячейки ESA CCI, а не пересчитанная поверхность; разрешение записано так, как его даёт продукт — в градусах.'],
  [/^t\/ha for AGB and AGB_SD; ha for weight$/i,
    () => 'т/га для запаса и его погрешности; га для веса ячейки.'],
  [/^ha for areas; t CO2e for contributions$/i,
    () => 'га для площадей; т CO₂-экв. для вкладов.'],
  [/^Key & Benson severity classes$/i,
    () => 'Классы силы изменения по Key & Benson.'],
  [/^WGS84 outlines detected on the 20 m grid/i,
    () => 'Контуры в WGS84, выделенные на сетке 20 м. Факт и причина — разные свойства: зона без установленной причины не называет события.'],
  [/^WGS84 outlines of the request the two dates could not be compared over/i,
    () => 'Контуры в WGS84 для частей запроса, которые нельзя сравнить между двумя датами, разделённые по причине. Это не площади, где ничего не произошло.'],
  [/^zone contributions and the remainder are parts of one stock difference/i,
    () => 'Вклады зон и остаток — части одной разницы запаса. Их никогда не складывают с отдельно посчитанным выбросом от пожара: это был бы двойной учёт.'],
];

/** Перевод английской строки сервиса. Незнакомый текст возвращается без изменений. */
export function serviceTextRu(text: string | null | undefined): string {
  if (!text) return '';
  const value = text.trim();
  for (const [pattern, render] of RULES) {
    const match = value.match(pattern);
    if (match) return render(match);
  }
  return value;
}

/** Ключи блока `evidence` зоны. */
export const ZONE_EVIDENCE_RU: Record<string, string> = {
  pixels: 'Пикселей в зоне',
  gfc_loss_fraction: 'Доля потери покрова (GFC)',
  spectral_change_fraction: 'Доля спектрального изменения',
  paired_valid_fraction: 'Доля сравнимых наблюдений',
  fire_fraction: 'Доля признака горения (MODIS)',
  gap_fraction: 'Доля без сравнимых наблюдений',
};

/** Роли артефактов результата. */
export const ARTIFACT_ROLE_RU: Record<string, string> = {
  cci_cell_layer: 'Ячейки углерода CCI',
  cells: 'Ячейки углерода',
  change_zones: 'Зоны изменений',
  observation_gap_zones: 'Разрывы наблюдений',
  severity_classes: 'Классы силы изменения',
  dnbr: 'Разностный индекс гари (dNBR)',
  timeline: 'История запаса по годам',
  manifest: 'Манифест источников',
};

/** Технические значения контракта, которые иначе попали бы на экран латиницей. */
export const VALUE_RU: Record<string, string> = {
  AGB_LIVE_WOODY: 'живая надземная древесная биомасса',
  POSITIVE_E_MEANS_POOL_LOSS: 'положительное E — потеря пула',
  POTENTIAL_UNIT_OF_THE_CASE: 'потенциальная единица кейса',
  INDEPENDENT_NATIVE_CELLS: 'независимые родные ячейки',
  FULL_SPATIAL_CORRELATION: 'полная пространственная корреляция',
  COMPUTED_FROM_SUPPLIED_DATA: 'рассчитано по выданным данным',
  STUB_FIXTURE: 'подставленный набор значений',
  PROVISIONAL_INPUT: 'предварительные входные данные',
  USER_INPUT: 'ввод пользователя',
  DEMO_INPUT: 'демонстрационный ввод',
  SERVICE: 'сервис',
  DEMO: 'демонстрация',
  HISTORICAL_REPLAY: 'воспроизведение истории',
};

export function valueRu(value: string | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return VALUE_RU[value] ?? value;
}

/** Коды ошибок API и клиента — человеческим языком. */
const ERROR_RU: Record<string, string> = {
  UNAUTHORIZED: 'Нужно войти заново',
  FORBIDDEN: 'Это действие недоступно вашей роли',
  NOT_FOUND: 'Запись не найдена',
  VALIDATION_ERROR: 'Сервис не принял запрос',
  TOO_MANY_ATTEMPTS: 'Слишком много попыток входа',
  AREA_TOO_LARGE: 'Контур больше допустимого предела',
  INVALID_GEOMETRY: 'Контур задан неверно',
  GEOMETRY_REQUIRED: 'Не задан контур',
  ACTION_NOT_ALLOWED: 'Сейчас это действие невозможно',
  IDEMPOTENCY_CONFLICT: 'Повторный запрос с тем же ключом',
  SERVICE_UNAVAILABLE: 'Сервис недоступен',
  ARTIFACT_INTEGRITY: 'Целостность файла не подтверждена',
  ARTIFACT_INTEGRITY_FAILED: 'Целостность файла не подтверждена',
  ARTIFACT_AMBIGUOUS: 'Сервис прислал несогласованные ссылки на файлы',
  ZONE_ARTIFACT_MISSING: 'Сервис не приложил геометрию зон',
  NETWORK: 'Сеть недоступна',
  TIMEOUT: 'Сервис не ответил за отведённое время',
  ANALYSIS_FAILED: 'Расчёт завершился ошибкой',
};

export function errorRu(code: string | null | undefined): string | null {
  if (!code) return null;
  return ERROR_RU[code] ?? null;
}

/** Подпись ошибки для экрана: русское объяснение, код — отдельно и мелко. */
export function errorTitleRu(code: string | null | undefined, fallback: string): string {
  return errorRu(code) ?? fallback;
}
