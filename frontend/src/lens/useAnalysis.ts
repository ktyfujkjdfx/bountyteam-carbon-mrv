import { useCallback, useRef, useState } from 'react';
import { pollUntilTerminal } from '../api/polling';
import { LensError, isTerminal, type LensApiClient } from './client';
import type { Analysis, AnalysisRequestBody, AnalysisResult } from './types';

export type AnalysisPhase = 'idle' | 'submitting' | 'polling' | 'done' | 'timeout' | 'error';

export interface AnalysisState {
  phase: AnalysisPhase;
  analysis: Analysis | null;
  result: AnalysisResult | null;
  error: { code: string; message: string; detail: string | null } | null;
}

const IDLE: AnalysisState = { phase: 'idle', analysis: null, result: null, error: null };

function toError(error: unknown): AnalysisState['error'] {
  if (error instanceof LensError) return { code: error.code, message: error.message, detail: error.detail };
  return { code: 'UNEXPECTED', message: error instanceof Error ? error.message : String(error), detail: null };
}

/**
 * Submit once per intent and poll the one analysis resource. A second click while a run is in flight
 * is ignored synchronously, responses of a superseded run are dropped, and a failure is never replaced
 * by data from somewhere else.
 */
export function useAnalysis(client: LensApiClient) {
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

  const show = useCallback((analysis: Analysis) => {
    runIdRef.current += 1;
    busyRef.current = false;
    setState({ phase: 'done', analysis, result: analysis.result, error: null });
  }, []);

  const run = useCallback(
    async (body: AnalysisRequestBody, scenario?: string): Promise<AnalysisResult | null> => {
      if (busyRef.current) return null;
      busyRef.current = true;
      runIdRef.current += 1;
      const runId = runIdRef.current;
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      const fresh = () => runId === runIdRef.current && !controller.signal.aborted;

      const intent = JSON.stringify({ body, scenario });
      let idempotencyKey = keysRef.current.get(intent);
      if (!idempotencyKey) {
        idempotencyKey = `lens-${crypto.randomUUID()}`;
        keysRef.current.set(intent, idempotencyKey);
      }

      setState({ phase: 'submitting', analysis: null, result: null, error: null });
      try {
        const accepted = await client.createAnalysis(body, { idempotencyKey, signal: controller.signal, scenario });
        if (!fresh()) return null;
        setState({ phase: 'polling', analysis: null, result: null, error: null });

        const polled = await pollUntilTerminal<Analysis>({
          fetch: (signal) => client.getAnalysis(accepted.analysis_id, signal),
          isTerminal: (value) => isTerminal(String(value.job_state)),
          onUpdate: (value) => {
            if (fresh()) setState((s) => ({ ...s, analysis: value }));
          },
          signal: controller.signal,
          initialDelayMs: 300,
          maxDurationMs: 180_000,
        });
        if (!fresh()) return null;

        if (polled.status === 'timeout') {
          setState((s) => ({ ...s, phase: 'timeout' }));
          return null;
        }
        if (polled.status === 'error') {
          setState((s) => ({ ...s, phase: 'error', error: { code: polled.error.code ?? 'POLL_FAILED', message: polled.error.message, detail: null } }));
          return null;
        }
        if (polled.status !== 'terminal') return null;

        const finished = polled.value;
        if (String(finished.job_state) === 'FAILED' || !finished.result) {
          setState({
            phase: 'error',
            analysis: finished,
            result: null,
            error: finished.error
              ? { code: finished.error.code, message: finished.error.message, detail: null }
              : { code: 'JOB_FAILED', message: 'Расчёт завершился без результата', detail: null },
          });
          return null;
        }
        setState({ phase: 'done', analysis: finished, result: finished.result, error: null });
        return finished.result;
      } catch (error) {
        if (fresh()) setState({ phase: 'error', analysis: null, result: null, error: toError(error) });
        return null;
      } finally {
        if (runId === runIdRef.current) busyRef.current = false;
      }
    },
    [client],
  );

  const busy = state.phase === 'submitting' || state.phase === 'polling';
  return { state, busy, run, reset, show };
}
