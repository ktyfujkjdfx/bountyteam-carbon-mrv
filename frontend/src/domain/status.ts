import type {
  ComputationMode,
  CreditStatus,
  DatasetKind,
  Decision,
  DecisionReason,
  EvidenceQuality,
  FirmsSupport,
  HealthMode,
  JobState,
  RsOutcome,
  TransactionState,
} from '../api/types';

// Tone semantics: ok=green, info=blue (in progress), review=amber, alert=orange (requested, not executed),
// blocked=red (confirmed on-chain restriction or failure), neutral=grey (no data / not applicable).
export type Tone = 'ok' | 'info' | 'review' | 'alert' | 'blocked' | 'neutral';

export interface StatusMeta {
  label: string;
  tone: Tone;
  hint: string;
  unknown?: boolean;
}

export const UNKNOWN_VALUE_HINT = 'Неизвестное значение от Backend — значение отсутствует в текущем API-контракте.';

const MAX_UNKNOWN_LABEL = 64;

export function isKnownKey<K extends string>(table: Readonly<Record<K, unknown>>, value: unknown): value is K {
  return typeof value === 'string' && Object.hasOwn(table, value);
}

// Renders a received value as plain text for display; never "undefined"/"null"/"[object Object]".
export function describeReceived(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    const text = String(value);
    return text.length > MAX_UNKNOWN_LABEL ? `${text.slice(0, MAX_UNKNOWN_LABEL)}…` : text;
  }
  return 'UNKNOWN';
}

export function unknownMeta(value: unknown): StatusMeta {
  return { label: `UNKNOWN: ${describeReceived(value)}`, tone: 'neutral', hint: UNKNOWN_VALUE_HINT, unknown: true };
}

// Contract drift must degrade to a neutral, explicit label instead of crashing the dashboard.
export function metaFor<K extends string>(table: Readonly<Record<K, StatusMeta>>, value: unknown): StatusMeta {
  return isKnownKey(table, value) ? table[value] : unknownMeta(value);
}

export function labelFor<K extends string>(table: Readonly<Record<K, string>>, value: unknown): string {
  return isKnownKey(table, value) ? table[value] : `Неизвестное значение: ${describeReceived(value)}`;
}

export function toneFor<K extends string>(table: Readonly<Record<K, Tone>>, value: unknown): Tone {
  return isKnownKey(table, value) ? table[value] : 'neutral';
}

export type StatusLayer = 'outcome' | 'quality' | 'decision' | 'operation' | 'credit' | 'job';

export const LAYER_TITLES: Record<StatusLayer, string> = {
  outcome: 'RS outcome (наблюдение)',
  quality: 'Evidence quality (Backend)',
  decision: 'Backend decision',
  operation: 'Transaction state',
  credit: 'Credit status (контракт)',
  job: 'Verification job',
};

export const OUTCOME_META: Record<RsOutcome, StatusMeta> = {
  NO_CHANGE: {
    label: 'NO_CHANGE',
    tone: 'ok',
    hint: 'Значимого изменения по методике не обнаружено. Не сертификат сохранности леса.',
  },
  DISTURBANCE_DETECTED: {
    label: 'DISTURBANCE_DETECTED',
    tone: 'alert',
    hint: 'Пространственно связный сигнал изменения. Причина требует сопоставления с дополнительными данными.',
  },
  INSUFFICIENT_DATA: {
    label: 'INSUFFICIENT_DATA',
    tone: 'neutral',
    hint: 'Недостаточно валидных данных. Это не NO_CHANGE и не обвинение владельца.',
  },
};

export const QUALITY_META: Record<EvidenceQuality, StatusMeta> = {
  SUFFICIENT: { label: 'SUFFICIENT', tone: 'ok', hint: 'Покрытие ≥ 0.85, метаданные и сетки согласованы (demo policy v1).' },
  REVIEW_REQUIRED: {
    label: 'REVIEW_REQUIRED',
    tone: 'review',
    hint: 'Покрытие 0.70–0.85 или сезоны несопоставимы. Автоматические финансовые действия закрыты.',
  },
  INSUFFICIENT: { label: 'INSUFFICIENT', tone: 'neutral', hint: 'Покрытие < 0.70 или нет обязательных данных.' },
};

export const DECISION_META: Record<Decision, StatusMeta> = {
  NO_RESTRICTION: {
    label: 'NO_RESTRICTION',
    tone: 'ok',
    hint: 'Ограничение не требуется. Это не самостоятельное разрешение на выпуск.',
  },
  REVIEW_REQUIRED: {
    label: 'REVIEW_REQUIRED',
    tone: 'review',
    hint: 'Нужна проверка человеком. Автоматической заморозки нет, новые issue/buy закрыты.',
  },
  FREEZE_REQUESTED: {
    label: 'FREEZE_REQUESTED',
    tone: 'alert',
    hint: 'Backend запросил приостановку. Это ещё НЕ FROZEN: ждём подтверждённый receipt и readback.',
  },
};

export const REASON_LABELS: Record<DecisionReason, string> = {
  NO_SIGNIFICANT_CHANGE: 'Нет значимого изменения',
  DATA_INSUFFICIENT: 'Недостаточно данных',
  DATA_REVIEW: 'Данные требуют проверки',
  DISTURBANCE_UNATTRIBUTED: 'Изменение без поддержки FIRMS',
  BELOW_POLICY_THRESHOLD: 'Ниже порога политики',
  FIRE_REVERSAL: 'Реверс из-за пожара (demo policy)',
};

export const TRANSACTION_META: Record<TransactionState, StatusMeta> = {
  QUEUED: { label: 'QUEUED', tone: 'info', hint: 'Намерение сохранено Backend; подписание и отправка ещё не завершены.' },
  SUBMITTED: {
    label: 'SUBMITTED',
    tone: 'info',
    hint: 'Транзакция отправлена, receipt ещё не подтверждён. Это не финальный результат.',
  },
  CONFIRMED: { label: 'CONFIRMED', tone: 'ok', hint: 'Receipt status 1, ожидаемое событие и readback подтверждены Backend.' },
  FAILED: { label: 'FAILED', tone: 'blocked', hint: 'Операция завершилась ошибкой.' },
};

export const JOB_META: Record<JobState, StatusMeta> = {
  QUEUED: { label: 'QUEUED', tone: 'info', hint: 'Задание сохранено и ждёт worker.' },
  RUNNING: { label: 'RUNNING', tone: 'info', hint: 'Worker обрабатывает evidence.' },
  SUCCEEDED: { label: 'SUCCEEDED', tone: 'ok', hint: 'Evidence обработан. Это не успех транзакции.' },
  FAILED: { label: 'FAILED', tone: 'blocked', hint: 'Задание завершилось ошибкой.' },
};

export const CREDIT_META: Record<CreditStatus, StatusMeta> = {
  ACTIVE: { label: 'ACTIVE', tone: 'ok', hint: 'Контракт допускает передачу и покупку при остальных условиях.' },
  FROZEN: {
    label: 'FROZEN',
    tone: 'blocked',
    hint: 'Временное ограничение прототипа: контракт запрещает передачу и покупку. Не юридическое аннулирование; балансы сохранены.',
  },
  REVOKED: { label: 'REVOKED', tone: 'neutral', hint: 'Зарезервировано; в P0 не используется.' },
};

export const DATASET_META: Record<DatasetKind, StatusMeta> = {
  REAL: { label: 'REAL', tone: 'ok', hint: 'Реальные спутниковые сцены с проверяемыми scene ID.' },
  SYNTHETIC: { label: 'SYNTHETIC', tone: 'review', hint: 'Синтетические данные для контрактных тестов. Не реальный пожар.' },
};

export const COMPUTATION_META: Record<ComputationMode, StatusMeta> = {
  COMPUTED: { label: 'COMPUTED', tone: 'ok', hint: 'Расчёт выполнен в этом запуске.' },
  CACHED_REPLAY: { label: 'CACHED_REPLAY', tone: 'review', hint: 'Сохранённый результат воспроизводимого расчёта.' },
};

export const HEALTH_MODE_META: Record<HealthMode, StatusMeta> = {
  CONTRACT_FIXTURE: { label: 'CONTRACT_FIXTURE', tone: 'review', hint: 'Backend работает на контрактных fixtures.' },
  LOCAL_DEMO: { label: 'LOCAL_DEMO', tone: 'ok', hint: 'Локальный demo-стенд Backend.' },
};

export const FIRMS_META: Record<FirmsSupport, StatusMeta> = {
  SUPPORTED: { label: 'SUPPORTED', tone: 'ok', hint: 'Есть тепловые аномалии в окне наблюдения рядом с повреждением.' },
  NOT_FOUND: { label: 'NOT_FOUND', tone: 'neutral', hint: 'Поддержка не найдена в выбранном наборе. Не означает «пожара не было».' },
  NOT_CHECKED: { label: 'NOT_CHECKED', tone: 'neutral', hint: 'Источник FIRMS не проверялся.' },
};

export const PUBLIC_TRANSACTION_STATES = Object.keys(TRANSACTION_META) as TransactionState[];

export const DNBR_LEGEND: ReadonlyArray<{ range: string; label: string; color: string }> = [
  { range: '< 0.10', label: 'Низкий/отсутствующий сигнал или восстановление; не доказательство отсутствия пожара', color: '#d9ead3' },
  { range: '0.10 – 0.27', label: 'Low', color: '#fff2a8' },
  { range: '0.27 – 0.44', label: 'Moderate-low', color: '#f9cb74' },
  { range: '0.44 – 0.66', label: 'Moderate-high', color: '#f08a4b' },
  { range: '≥ 0.66', label: 'High', color: '#b8322a' },
];
