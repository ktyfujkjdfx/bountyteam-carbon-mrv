import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, toApiError } from '../api/errors';

export interface Resource<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
}

interface Settled<T> {
  data: T | null;
  error: ApiError | null;
  key: object | null;
}

// Keeps the last stable data when a refetch fails, so an error never wipes the displayed state.
export function useResource<T>(fetcher: ((signal: AbortSignal) => Promise<T>) | null, deps: readonly unknown[]): Resource<T> {
  const [nonce, setNonce] = useState(0);
  const [settled, setSettled] = useState<Settled<T>>({ data: null, error: null, key: null });
  const fetcherRef = useRef(fetcher);
  const enabled = fetcher !== null;

  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const currentDeps = [...deps, nonce, enabled];
  const [keyState, setKeyState] = useState<{ deps: unknown[]; key: object }>(() => ({ deps: currentDeps, key: {} }));
  let key = keyState.key;
  if (keyState.deps.length !== currentDeps.length || keyState.deps.some((value, i) => !Object.is(value, currentDeps[i]))) {
    key = {};
    setKeyState({ deps: currentDeps, key });
  }

  useEffect(() => {
    const run = fetcherRef.current;
    if (!run) return;
    const controller = new AbortController();
    run(controller.signal).then(
      (value) => {
        if (!controller.signal.aborted) setSettled({ data: value, error: null, key });
      },
      (err: unknown) => {
        if (controller.signal.aborted) return;
        const apiError = toApiError(err);
        if (apiError.kind !== 'aborted') setSettled((prev) => ({ data: prev.data, error: apiError, key }));
      },
    );
    return () => controller.abort();
  }, [key]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const loading = enabled && settled.key !== key;
  return { data: settled.data, error: settled.error, loading, reload };
}
