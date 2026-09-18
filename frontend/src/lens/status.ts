import type { StatusMeta } from '../domain/status';

export const CALCULATION_META: Record<string, StatusMeta> = {
  AVAILABLE: { label: 'РАСЧЁТ ДОСТУПЕН', tone: 'ok', hint: 'Входные данные допустимы, результат рассчитан по условиям кейса.' },
  UNAVAILABLE: { label: 'РАСЧЁТ НЕДОСТУПЕН', tone: 'neutral', hint: 'Не хватает обязательных входных данных или покрытия; это не ноль единиц.' },
};

export const EVIDENCE_META: Record<string, StatusMeta> = {
  SUFFICIENT: { label: 'ОБЪЯСНЕНИЕ ПОЛНОЕ', tone: 'ok', hint: 'Изменения подтверждаются показанными наблюдениями.' },
  REVIEW_REQUIRED: { label: 'НУЖНА ПРОВЕРКА', tone: 'review', hint: 'Часть изменений объясняется ограниченно: качество или доступность наблюдений снижены.' },
  INSUFFICIENT: { label: 'ОБЪЯСНЕНИЕ НЕДОСТАТОЧНО', tone: 'neutral', hint: 'Наблюдений недостаточно для объяснения изменения.' },
};

export const CLAIM_META: Record<string, StatusMeta> = {
  NOT_PROVIDED: { label: 'ЗАЯВЛЕНИЕ НЕ ВВЕДЕНО', tone: 'neutral', hint: 'Пользовательское заявление не задано; расчёт от него не зависит.' },
  NOT_COMPARABLE: { label: 'НЕСОПОСТАВИМО', tone: 'review', hint: 'Контур, период, пул или единицы заявления не совпадают с запросом.' },
  UNASSESSABLE: { label: 'НЕЛЬЗЯ ОЦЕНИТЬ', tone: 'neutral', hint: 'Расчёт единиц недоступен, сравнение невозможно.' },
  SUPPORTED_BY_CASE: { label: 'ПОДДЕРЖАНО РАСЧЁТОМ', tone: 'ok', hint: 'Заявленное количество не превышает расчёт по условиям кейса.' },
  PARTIALLY_SUPPORTED_BY_CASE: { label: 'ПОДДЕРЖАНО ЧАСТИЧНО', tone: 'review', hint: 'Часть заявления не покрыта расчётом по условиям кейса.' },
  NOT_SUPPORTED_BY_CASE: { label: 'НЕ ПОДДЕРЖАНО', tone: 'alert', hint: 'Расчёт по условиям кейса не даёт положительных единиц для этого запроса.' },
};

export const JOB_META: Record<string, StatusMeta> = {
  QUEUED: { label: 'QUEUED', tone: 'info', hint: 'Запрос принят и ждёт обработки.' },
  RUNNING: { label: 'RUNNING', tone: 'info', hint: 'Расчёт выполняется.' },
  SUCCEEDED: { label: 'SUCCEEDED', tone: 'ok', hint: 'Расчёт завершён.' },
  FAILED: { label: 'FAILED', tone: 'blocked', hint: 'Расчёт завершился ошибкой.' },
};

export const CAUSE_META: Record<string, StatusMeta> = {
  SUPPORTED: { label: 'ПРИЧИНА ПОДТВЕРЖДЕНА ИСТОЧНИКОМ', tone: 'alert', hint: 'Есть внешнее подтверждение; точная площадь события им не измеряется.' },
  NOT_ESTABLISHED: { label: 'ПРИЧИНА НЕ УСТАНОВЛЕНА', tone: 'neutral', hint: 'Изменение наблюдается, но пожар или вырубка не доказаны.' },
};

export const ZERO_REASON_LABELS: Record<string, string> = {
  NON_POSITIVE_RELATIVE_RESULT: 'нет положительного результата относительно базовой линии',
  UNCERTAINTY_TOO_HIGH: 'неопределённость слишком велика (H/R ≥ 1)',
  ROUNDED_TO_ZERO: 'после вычетов осталось меньше одной единицы',
};

export const UNAVAILABLE_REASON_LABELS: Record<string, string> = {
  INCOMPLETE_BIOMASS_COVERAGE: 'неполное числовое покрытие биомассы в контуре',
  BASELINE_NOT_COVERED: 'контур выходит за таблицу базовой линии',
  NO_COMPARABLE_OBSERVATIONS: 'нет сопоставимых наблюдений на обе даты',
  INVALID_REQUEST: 'недопустимые параметры запроса',
};
