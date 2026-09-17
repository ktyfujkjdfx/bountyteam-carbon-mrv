import { ApiError, toApiError } from './errors';
import { TERMINAL_JOB_STATES, TERMINAL_TRANSACTION_STATES, type Job, type Operation } from './types';

export interface PollOptions<T> {
  fetch: (signal: AbortSignal) => Promise<T>;
  isTerminal: (value: T) => boolean;
  onUpdate: (value: T) => void;
  signal: AbortSignal;
  initialDelayMs?: number;
  maxDelayMs?: number;
  maxDurationMs?: number;
  maxConsecutiveErrors?: number;
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
}

export type PollResult<T> =
  | { status: 'terminal'; value: T }
  | { status: 'timeout'; value: T | null }
  | { status: 'aborted'; value: T | null }
  | { status: 'error'; value: T | null; error: ApiError };

export function isTerminalJob(job: Job): boolean {
  return (TERMINAL_JOB_STATES as readonly string[]).includes(job.state);
}

export function isTerminalOperation(op: Operation): boolean {
  return (TERMINAL_TRANSACTION_STATES as readonly string[]).includes(op.transaction_state);
}

export function abortableSleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve();
    const timer = setTimeout(done, ms);
    function done() {
      clearTimeout(timer);
      signal.removeEventListener('abort', done);
      resolve();
    }
    signal.addEventListener('abort', done, { once: true });
  });
}

// Bounded backoff poll; a timeout keeps the last non-terminal value (e.g. SUBMITTED) instead of inventing FAILED.
export async function pollUntilTerminal<T>(options: PollOptions<T>): Promise<PollResult<T>> {
  const {
    fetch,
    isTerminal,
    onUpdate,
    signal,
    initialDelayMs = 500,
    maxDelayMs = 3000,
    maxDurationMs = 120_000,
    maxConsecutiveErrors = 5,
    sleep = abortableSleep,
  } = options;

  const startedAt = Date.now();
  let delay = initialDelayMs;
  let last: T | null = null;
  let consecutiveErrors = 0;

  for (;;) {
    if (signal.aborted) return { status: 'aborted', value: last };
    try {
      const value = await fetch(signal);
      if (signal.aborted) return { status: 'aborted', value: last };
      last = value;
      consecutiveErrors = 0;
      onUpdate(value);
      if (isTerminal(value)) return { status: 'terminal', value };
    } catch (error) {
      const apiError = toApiError(error);
      if (apiError.kind === 'aborted' || signal.aborted) return { status: 'aborted', value: last };
      consecutiveErrors += 1;
      if (!apiError.retryable || consecutiveErrors >= maxConsecutiveErrors) {
        return { status: 'error', value: last, error: apiError };
      }
    }
    if (Date.now() - startedAt >= maxDurationMs) return { status: 'timeout', value: last };
    await sleep(delay, signal);
    delay = Math.min(Math.round(delay * 1.5), maxDelayMs);
  }
}
