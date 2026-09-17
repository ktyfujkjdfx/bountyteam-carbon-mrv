// @vitest-environment node
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../src/api/errors';
import { isTerminalJob, isTerminalOperation, pollUntilTerminal } from '../src/api/polling';
import type { Job, Operation } from '../src/api/types';

const op = (state: Operation['transaction_state']): Operation => ({
  operation_id: '40000000-0000-4000-8000-000000000001',
  kind: 'FREEZE',
  transaction_state: state,
  tx_hash: null,
  batch_id: '1',
  error: null,
  receipt: null,
});

const noSleep = async () => undefined;

describe('terminal states', () => {
  it('operation: only CONFIRMED and FAILED are terminal', () => {
    expect(isTerminalOperation(op('QUEUED'))).toBe(false);
    expect(isTerminalOperation(op('SUBMITTED'))).toBe(false);
    expect(isTerminalOperation(op('CONFIRMED'))).toBe(true);
    expect(isTerminalOperation(op('FAILED'))).toBe(true);
  });

  it('job: only SUCCEEDED and FAILED are terminal', () => {
    const job = (state: Job['state']): Job => ({ job_id: 'j', state, verification_id: null, error: null });
    expect(['QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED'].map((s) => isTerminalJob(job(s as Job['state'])))).toEqual([false, false, true, true]);
  });
});

describe('pollUntilTerminal', () => {
  it('stops at the first terminal state and reports every update', async () => {
    const states = [op('QUEUED'), op('SUBMITTED'), op('CONFIRMED'), op('FAILED')];
    const fetch = vi.fn(async () => states.shift() as Operation);
    const updates: string[] = [];
    const result = await pollUntilTerminal({
      fetch,
      isTerminal: isTerminalOperation,
      onUpdate: (o) => updates.push(o.transaction_state),
      signal: new AbortController().signal,
      sleep: noSleep,
    });
    expect(result).toMatchObject({ status: 'terminal', value: { transaction_state: 'CONFIRMED' } });
    expect(updates).toEqual(['QUEUED', 'SUBMITTED', 'CONFIRMED']);
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it('timeout keeps SUBMITTED instead of inventing FAILED or CONFIRMED', async () => {
    let now = 0;
    vi.spyOn(Date, 'now').mockImplementation(() => now);
    const result = await pollUntilTerminal({
      fetch: async () => op('SUBMITTED'),
      isTerminal: isTerminalOperation,
      onUpdate: () => undefined,
      signal: new AbortController().signal,
      maxDurationMs: 5000,
      sleep: async (ms) => {
        now += ms;
      },
    });
    expect(result).toMatchObject({ status: 'timeout', value: { transaction_state: 'SUBMITTED' } });
  });

  it('uses bounded exponential backoff', async () => {
    const delays: number[] = [];
    let calls = 0;
    await pollUntilTerminal({
      fetch: async () => (++calls >= 8 ? op('CONFIRMED') : op('SUBMITTED')),
      isTerminal: isTerminalOperation,
      onUpdate: () => undefined,
      signal: new AbortController().signal,
      initialDelayMs: 500,
      maxDelayMs: 3000,
      sleep: async (ms) => {
        delays.push(ms);
      },
    });
    expect(delays[0]).toBe(500);
    expect(Math.max(...delays)).toBeLessThanOrEqual(3000);
    expect(delays.at(-1)).toBe(3000);
  });

  it('stops immediately when aborted (unmount cleanup) and makes no further requests', async () => {
    const controller = new AbortController();
    const fetch = vi.fn(async () => {
      controller.abort();
      return op('SUBMITTED');
    });
    const result = await pollUntilTerminal({ fetch, isTerminal: isTerminalOperation, onUpdate: () => undefined, signal: controller.signal, sleep: noSleep });
    expect(result.status).toBe('aborted');
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('retries transient 503/network errors but stops on non-retryable 404', async () => {
    const responses: Array<Operation | ApiError> = [
      new ApiError({ kind: 'http', status: 503, message: 'db' }),
      new ApiError({ kind: 'network', message: 'offline' }),
      op('CONFIRMED'),
    ];
    const retried = await pollUntilTerminal({
      fetch: async () => {
        const next = responses.shift();
        if (next instanceof ApiError) throw next;
        return next as Operation;
      },
      isTerminal: isTerminalOperation,
      onUpdate: () => undefined,
      signal: new AbortController().signal,
      sleep: noSleep,
    });
    expect(retried.status).toBe('terminal');

    const fetch = vi.fn(async (): Promise<Operation> => {
      throw new ApiError({ kind: 'http', status: 404, message: 'gone' });
    });
    const failed = await pollUntilTerminal({ fetch, isTerminal: isTerminalOperation, onUpdate: () => undefined, signal: new AbortController().signal, sleep: noSleep });
    expect(failed).toMatchObject({ status: 'error', error: { status: 404 } });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('gives up after bounded consecutive transient errors', async () => {
    const fetch = vi.fn(async (): Promise<Operation> => {
      throw new ApiError({ kind: 'network', message: 'offline' });
    });
    const result = await pollUntilTerminal({
      fetch,
      isTerminal: isTerminalOperation,
      onUpdate: () => undefined,
      signal: new AbortController().signal,
      sleep: noSleep,
      maxConsecutiveErrors: 3,
    });
    expect(result.status).toBe('error');
    expect(fetch).toHaveBeenCalledTimes(3);
  });
});
