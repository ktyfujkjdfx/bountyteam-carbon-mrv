import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, toApiError } from '../api/errors';
import { pollUntilTerminal } from '../api/polling';
import { attachStatusUrl, beginIntent, finishIntent, pendingIntents, type TrackedKind } from '../api/tracking';

export type ActionPhase = 'idle' | 'submitting' | 'polling' | 'terminal' | 'timeout' | 'error';

export interface TrackedActionState<TStatus> {
  phase: ActionPhase;
  status: TStatus | null;
  error: ApiError | null;
  statusUrl: string | null;
}

export interface TrackedActionConfig<TBody, TStatus> {
  intentKey: string;
  kind: TrackedKind;
  submit: (body: TBody, idempotencyKey: string, signal: AbortSignal) => Promise<{ statusUrl: string }>;
  fetchStatus: (statusUrl: string, signal: AbortSignal) => Promise<TStatus>;
  isTerminal: (status: TStatus) => boolean;
  onSettled?: (status: TStatus | null) => void;
  pollIntervalMs?: number;
  maxDurationMs?: number;
}

export interface TrackedAction<TBody, TStatus> extends TrackedActionState<TStatus> {
  busy: boolean;
  run: (body: TBody) => Promise<void>;
  resume: () => void;
  reset: () => void;
}

const IDLE = { phase: 'idle', status: null, error: null, statusUrl: null } as const;

export function useTrackedAction<TBody, TStatus>(config: TrackedActionConfig<TBody, TStatus>): TrackedAction<TBody, TStatus> {
  const [state, setState] = useState<TrackedActionState<TStatus>>(IDLE);
  const configRef = useRef(config);
  useEffect(() => {
    configRef.current = config;
  });
  const lockRef = useRef(false);
  const controllerRef = useRef<AbortController | null>(null);

  const poll = useCallback(async (statusUrl: string) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    const cfg = configRef.current;
    setState((s) => ({ ...s, phase: 'polling', statusUrl, error: null }));
    const result = await pollUntilTerminal<TStatus>({
      fetch: (signal) => cfg.fetchStatus(statusUrl, signal),
      isTerminal: cfg.isTerminal,
      onUpdate: (status) => setState((s) => ({ ...s, status })),
      signal: controller.signal,
      initialDelayMs: cfg.pollIntervalMs ?? 500,
      maxDurationMs: cfg.maxDurationMs ?? 120_000,
    });
    if (result.status === 'aborted') return;
    if (result.status === 'terminal') {
      finishIntent(cfg.intentKey);
      setState({ phase: 'terminal', status: result.value, error: null, statusUrl });
      lockRef.current = false;
      cfg.onSettled?.(result.value);
      return;
    }
    if (result.status === 'timeout') {
      setState((s) => ({ ...s, phase: 'timeout' }));
      lockRef.current = false;
      cfg.onSettled?.(result.value);
      return;
    }
    if (result.error.status === 404) finishIntent(cfg.intentKey);
    setState((s) => ({ ...s, phase: 'error', error: result.error }));
    lockRef.current = false;
    cfg.onSettled?.(result.value);
  }, []);

  const run = useCallback(
    async (body: TBody) => {
      if (lockRef.current) return;
      lockRef.current = true;
      const cfg = configRef.current;
      const intent = beginIntent(cfg.intentKey, cfg.kind, body);
      const controller = new AbortController();
      controllerRef.current?.abort();
      controllerRef.current = controller;
      setState({ phase: 'submitting', status: null, error: null, statusUrl: null });
      try {
        const accepted = await cfg.submit(body, intent.idempotencyKey, controller.signal);
        attachStatusUrl(cfg.intentKey, accepted.statusUrl);
        await poll(accepted.statusUrl);
      } catch (err) {
        const apiError = toApiError(err);
        if (apiError.kind === 'aborted') {
          lockRef.current = false;
          return;
        }
        if (!apiError.retryable) finishIntent(cfg.intentKey);
        setState({ phase: 'error', status: null, error: apiError, statusUrl: null });
        lockRef.current = false;
      }
    },
    [poll],
  );

  const resume = useCallback(() => {
    if (state.statusUrl && !lockRef.current) {
      lockRef.current = true;
      void poll(state.statusUrl);
    }
  }, [poll, state.statusUrl]);

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    lockRef.current = false;
    setState(IDLE);
  }, []);

  useEffect(() => {
    const restored = pendingIntents(config.intentKey).find((intent) => intent.intentKey === config.intentKey);
    if (restored?.statusUrl && !lockRef.current) {
      lockRef.current = true;
      void poll(restored.statusUrl);
    }
    return () => {
      controllerRef.current?.abort();
      lockRef.current = false;
    };
  }, [config.intentKey, poll]);

  const busy = state.phase === 'submitting' || state.phase === 'polling';
  return { ...state, busy, run, resume, reset };
}
