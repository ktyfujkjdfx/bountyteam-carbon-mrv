import { useCallback, useRef, useState } from 'react';
import { pollUntilTerminal } from '../api/polling';
import { LensError, type LensApiClient } from './adapter';
import type { FixtureScenarioId } from './fixtures';
import type { LensJob, LensRequest, LensResult } from './types';

export type AnalysisPhase = 'idle' | 'submitting' | 'polling' | 'done' | 'timeout' | 'error';

export interface AnalysisState {
  phase: AnalysisPhase;
  job: LensJob | null;
  result: LensResult | null;
  error: { code: string; message: string; detail: string | null } | null;
}

const IDLE: AnalysisState = { phase: 'idle', job: null, result: null, error: null };

function toError(error: unknown): AnalysisState['error'] {
  if (error instanceof LensError) return { code: error.code, message: error.message, detail: error.detail };
  return { code: 'UNEXPECTED', message: error instanceof Error ? error.message : String(error), detail: null };
}

// Submit once per intent, poll with the shared bounded backoff, and ignore responses of superseded runs.
export function useLensAnalysis(client: LensApiClient) {
  const [state, setState] = useState<AnalysisState>(IDLE);
  const runIdRef = useRef(0);
  const busyRef = useRef(false);
  const controllerRef = useRef<AbortController | null>(null);
  const keysRef = useRef(new Map<string, string>());

  const reset = useCallback(() => {
    runIdRef.current += 1;
    controllerRef.current?.abort();
    busyRef.current = false;
    setState(IDLE);
  }, []);

  const run = useCallback(
    async (request: LensRequest, scenario: FixtureScenarioId) => {
      if (busyRef.current) return;
      busyRef.current = true;
      runIdRef.current += 1;
      const runId = runIdRef.current;
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      const fresh = () => runId === runIdRef.current && !controller.signal.aborted;

      const intent = JSON.stringify({ request, scenario });
      let idempotencyKey = keysRef.current.get(intent);
      if (!idempotencyKey) {
        idempotencyKey = `lens-${crypto.randomUUID()}`;
        keysRef.current.set(intent, idempotencyKey);
      }

      setState({ phase: 'submitting', job: null, result: null, error: null });
      try {
        const job = await client.submitAnalysis(request, { scenario, idempotencyKey, signal: controller.signal });
        if (!fresh()) return;
        setState({ phase: 'polling', job, result: null, error: null });

        const polled = await pollUntilTerminal<LensJob>({
          fetch: (signal) => client.getJob(job.job_id, signal),
          isTerminal: (value) => value.state === 'SUCCEEDED' || value.state === 'FAILED',
          onUpdate: (value) => {
            if (fresh()) setState((s) => ({ ...s, job: value }));
          },
          signal: controller.signal,
          initialDelayMs: 300,
          maxDurationMs: 60_000,
        });
        if (!fresh()) return;

        if (polled.status === 'timeout') {
          setState((s) => ({ ...s, phase: 'timeout' }));
          return;
        }
        if (polled.status === 'error') {
          setState((s) => ({ ...s, phase: 'error', error: { code: polled.error.code ?? 'POLL_FAILED', message: polled.error.message, detail: null } }));
          return;
        }
        if (polled.status !== 'terminal') return;

        const finished = polled.value;
        if (finished.state === 'FAILED' || !finished.result_id) {
          setState({ phase: 'error', job: finished, result: null, error: finished.error ? { ...finished.error, detail: null } : { code: 'JOB_FAILED', message: 'Расчёт завершился ошибкой', detail: null } });
          return;
        }
        const result = await client.getResult(finished.result_id, controller.signal);
        if (!fresh()) return;
        setState({ phase: 'done', job: finished, result, error: null });
      } catch (error) {
        if (fresh()) setState({ phase: 'error', job: null, result: null, error: toError(error) });
      } finally {
        if (runId === runIdRef.current) busyRef.current = false;
      }
    },
    [client],
  );

  const busy = state.phase === 'submitting' || state.phase === 'polling';
  return { state, busy, run, reset };
}
