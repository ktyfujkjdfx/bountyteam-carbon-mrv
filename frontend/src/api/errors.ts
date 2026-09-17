import type { ErrorEnvelope } from './types';

export type ApiErrorKind = 'http' | 'network' | 'timeout' | 'contract' | 'aborted';

export interface ApiErrorInit {
  kind: ApiErrorKind;
  message: string;
  status?: number | null;
  code?: string | null;
  requestId?: string | null;
  details?: Record<string, unknown>;
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string | null;
  readonly requestId: string | null;
  readonly details: Record<string, unknown>;

  constructor(init: ApiErrorInit) {
    super(init.message);
    this.name = 'ApiError';
    this.kind = init.kind;
    this.status = init.status ?? null;
    this.code = init.code ?? null;
    this.requestId = init.requestId ?? null;
    this.details = init.details ?? {};
  }

  get retryable(): boolean {
    if (this.kind === 'network' || this.kind === 'timeout') return true;
    return this.status === 503;
  }
}

export function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== 'object' || value === null) return false;
  const error = (value as { error?: unknown }).error;
  if (typeof error !== 'object' || error === null) return false;
  const e = error as Record<string, unknown>;
  return typeof e.code === 'string' && typeof e.message === 'string';
}

const STATUS_HINTS: Record<number, string> = {
  401: 'Нет demo-сессии: проверьте X-Demo-Session в конфигурации.',
  403: 'Недостаточно прав у выбранного demo-актора.',
  404: 'Объект не найден в Backend.',
  409: 'Конфликт: действие запрещено текущим состоянием или ключ идемпотентности уже использован с другим телом.',
  422: 'Backend отклонил данные запроса (схема, диапазон или согласованность).',
  503: 'Backend временно не может надёжно принять операцию.',
};

const CODE_HINTS: Record<string, string> = {
  ARTIFACT_INTEGRITY_FAILED: 'Backend отказался отдавать файл: SHA-256 сохранённого артефакта не совпал с manifest.',
  CHAIN_UNAVAILABLE: 'Сеть блокчейна недоступна; сохранённые операции Backend не потеряны.',
  DEPLOYMENT_MISMATCH: 'Deployment контракта не совпадает с ожидаемым Backend.',
};

export function statusHint(status: number | null, code: string | null = null): string | null {
  if (code && CODE_HINTS[code]) return CODE_HINTS[code];
  return status === null ? null : (STATUS_HINTS[status] ?? null);
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (error instanceof DOMException && error.name === 'AbortError') {
    return new ApiError({ kind: 'aborted', message: 'Запрос отменён' });
  }
  const message = error instanceof Error ? error.message : String(error);
  return new ApiError({ kind: 'network', message });
}
