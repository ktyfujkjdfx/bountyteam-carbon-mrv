// Labels for the v2 axes. Every table is read through metaFor(), so a value the contract does not know
// yet renders as a neutral UNKNOWN badge instead of crashing or being mapped onto a known status.

import type { StatusMeta } from '../domain/status';

export const JOB_META: Record<string, StatusMeta> = {
  QUEUED: { label: 'В ОЧЕРЕДИ', tone: 'info', hint: 'Запрос принят и ждёт обработки.' },
  RUNNING: { label: 'СЧИТАЕТСЯ', tone: 'info', hint: 'Расчёт выполняется.' },
  SUCCEEDED: { label: 'ГОТОВО', tone: 'ok', hint: 'Расчёт завершён, результат получен.' },
  FAILED: { label: 'ОШИБКА РАСЧЁТА', tone: 'blocked', hint: 'Задание завершилось ошибкой; результата нет.' },
};

export const CALCULATION_META: Record<string, StatusMeta> = {
  AVAILABLE: { label: 'РАСЧЁТ ВЫПОЛНЕН', tone: 'ok', hint: 'Обязательные данные были на месте, значения рассчитаны.' },
  UNAVAILABLE: { label: 'РАСЧЁТ НЕВОЗМОЖЕН', tone: 'neutral', hint: 'Не хватает обязательных данных или покрытия. Это не ноль единиц.' },
};

export const EVIDENCE_META: Record<string, StatusMeta> = {
  SUFFICIENT: { label: 'ОБЪЯСНЕНИЕ ПОЛНОЕ', tone: 'ok', hint: 'Изменение объясняется показанными наблюдениями.' },
  REVIEW_REQUIRED: { label: 'НУЖНА ПРОВЕРКА', tone: 'review', hint: 'Часть изменений объясняется ограниченно.' },
  INSUFFICIENT: { label: 'ОБЪЯСНЕНИЕ НЕДОСТАТОЧНО', tone: 'neutral', hint: 'Наблюдений недостаточно, чтобы объяснить изменение.' },
};

export const CLAIM_META: Record<string, StatusMeta> = {
  NOT_PROVIDED: { label: 'ЗАЯВЛЕНИЕ НЕ ВВЕДЕНО', tone: 'neutral', hint: 'Заявленный объём не задан; расчёт от него не зависит.' },
  NOT_APPLICABLE: { label: 'ПОЛОЖИТЕЛЬНОГО ЗАЯВЛЕНИЯ НЕТ', tone: 'neutral', hint: 'Заявлен нулевой объём: сравнивать нечего, и это не подтверждение.' },
  NOT_COMPARABLE: { label: 'СРАВНЕНИЕ НЕВОЗМОЖНО', tone: 'review', hint: 'Контур, период, пул или единицы заявления не совпадают с запросом.' },
  UNASSESSABLE: { label: 'НЕЛЬЗЯ ОЦЕНИТЬ', tone: 'neutral', hint: 'Расчёт единиц недоступен, сравнивать не с чем.' },
  SUPPORTED_BY_CASE: { label: 'ПОДТВЕРЖДЕНО РАСЧЁТОМ', tone: 'ok', hint: 'Заявленный объём не превышает расчёт по методике кейса.' },
  PARTIALLY_SUPPORTED_BY_CASE: { label: 'ПОДТВЕРЖДЕНО ЧАСТИЧНО', tone: 'review', hint: 'Часть заявленного объёма расчётом не подтверждается.' },
  NOT_SUPPORTED_BY_CASE: { label: 'НЕ ПОДТВЕРЖДЕНО РАСЧЁТОМ', tone: 'alert', hint: 'Расчёт по методике кейса не даёт положительных единиц.' },
};

export const ZONE_FACT_META: Record<string, StatusMeta> = {
  TREE_COVER_LOSS: { label: 'ПОТЕРЯ ДРЕВЕСНОГО ПОКРОВА', tone: 'alert', hint: 'Продукт изменений отмечает год потери покрова.' },
  SPECTRAL_CHANGE_ONLY: { label: 'ТОЛЬКО СПЕКТРАЛЬНОЕ ИЗМЕНЕНИЕ', tone: 'review', hint: 'Изменение видно по отражению; потеря покрова не зарегистрирована.' },
  RECOVERY_INDICATION: { label: 'ПРИЗНАК ВОССТАНОВЛЕНИЯ', tone: 'ok', hint: 'Наблюдается прирост; вывод делается по результату периода.' },
};

export const ZONE_CAUSE_META: Record<string, StatusMeta> = {
  FIRE_SUPPORTED: { label: 'ПРИЧИНА: ПОЖАР ПО ПРОДУКТУ', tone: 'alert', hint: 'Есть внешний продукт гарей; точная площадь и дата им не измеряются.' },
  UNKNOWN: { label: 'ПРИЧИНА НЕ УСТАНОВЛЕНА', tone: 'neutral', hint: 'Изменение наблюдается, но пожар или вырубка не доказаны.' },
  NOT_APPLICABLE: { label: 'ПРИЧИНА НЕ ОПРЕДЕЛЯЕТСЯ', tone: 'neutral', hint: 'Для этой зоны вопрос причины не ставится.' },
};

export const ANCHOR_META: Record<string, StatusMeta> = {
  NOT_REQUESTED: { label: 'ЗАПИСЬ В РЕЕСТР НЕ ЗАПРАШИВАЛАСЬ', tone: 'neutral', hint: 'Якорь не запрашивался; целостность проверяется хешем файла.' },
  PENDING: { label: 'ЗАПИСЬ В ОБРАБОТКЕ', tone: 'info', hint: 'Якорь отправлен и ещё не подтверждён.' },
  CONFIRMED: { label: 'ЗАПИСЬ ПОДТВЕРЖДЕНА', tone: 'ok', hint: 'Якорь подтверждён. Он не удостоверяет истинность расчёта.' },
  FAILED: { label: 'ЗАПИСЬ НЕ УДАЛАСЬ', tone: 'blocked', hint: 'Якорь не записан; расчёт и паспорт это не меняет.' },
};

export const SEVERITY_META: Record<string, StatusMeta> = {
  INFO: { label: 'ПОЯСНЕНИЕ', tone: 'info', hint: 'Замечание, не влияющее на пригодность расчёта.' },
  WARNING: { label: 'ПРЕДУПРЕЖДЕНИЕ', tone: 'review', hint: 'Ограничение, которое влияет на интерпретацию.' },
  BLOCKING: { label: 'БЛОКИРУЕТ РАСЧЁТ', tone: 'blocked', hint: 'Ограничение, из-за которого часть результата недоступна.' },
};

export const COMPARISON_META: Record<string, StatusMeta> = {
  INITIAL: { label: 'ПЕРВОЕ НАБЛЮДЕНИЕ', tone: 'neutral', hint: 'Для этой области сравнения расчёт выполняется впервые.' },
  REVISION_OF_SAME_SCOPE: { label: 'ВЕРСИЯ ТОЙ ЖЕ ОБЛАСТИ', tone: 'info', hint: 'Повторный расчёт того же контура, периода, пула и метода.' },
  NEW_OBSERVATION: { label: 'НОВОЕ НАБЛЮДЕНИЕ', tone: 'review', hint: 'Другой период того же контура: это не списание прежних единиц.' },
  NOT_COMPARABLE: { label: 'НЕСОПОСТАВИМО', tone: 'neutral', hint: 'Область сравнения изменилась, поэтому версии нельзя сравнивать напрямую.' },
};

export const ZERO_REASON_TEXT: Record<string, string> = {
  NON_POSITIVE_RELATIVE_RESULT: 'результат периода не превышает базовую линию',
  UNCERTAINTY_TOO_HIGH: 'диапазон неопределённости перекрывает весь результат (H/R ≥ 1)',
  ROUNDED_TO_ZERO: 'после вычетов и резерва осталось меньше одной единицы',
};

export const UNAVAILABLE_REASON_TEXT: Record<string, string> = {
  MISSING_INPUT: 'не хватает обязательных входных значений',
  NON_FINITE_INPUT: 'во входных данных есть нечисловые значения',
  NON_POSITIVE_AREA: 'площадь запроса не положительна',
  NON_POSITIVE_PERIOD: 'период задан неверно',
  INVALID_UNCERTAINTY_INPUT: 'входные данные неопределённости непригодны',
  INVALID_INTERVAL: 'интервал результата построить не удалось',
  INCOMPLETE_COVERAGE: 'часть контура без обязательных числовых данных',
  BASELINE_OUT_OF_COVERAGE: 'контур выходит за таблицу базовой линии',
  BASELINE_UNKNOWN_AREA: 'для контура неизвестна площадь базовой линии',
  RASTER_ANALYSIS_UNAVAILABLE: 'растровый расчёт для этого контура недоступен',
};

export const CLAIM_REASON_TEXT: Record<string, string> = {
  INVALID_CLAIM_VALUE: 'заявленное значение недопустимо',
  NO_POSITIVE_CLAIM: 'заявлен нулевой объём: положительного заявления нет',
  GEOMETRY_MISMATCH: 'заявление относится к другому контуру',
  PERIOD_MISMATCH: 'заявление относится к другому периоду',
  POOL_MISMATCH: 'заявление относится к другому пулу углерода',
  UNIT_MISMATCH: 'заявление выражено в других единицах',
};
