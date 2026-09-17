import { useEffect, useState } from 'react';
import type { ArtifactPayload, MrvApiClient } from '../api/client';
import { ApiError, toApiError } from '../api/errors';
import type { ArtifactLink } from '../api/types';

export interface ArtifactState {
  payload: ArtifactPayload | null;
  error: ApiError | null;
  loading: boolean;
}

interface Loaded {
  requestKey: string;
  payload: ArtifactPayload | null;
  error: ApiError | null;
}

export function useArtifact(client: MrvApiClient, link: ArtifactLink | null | undefined): ArtifactState {
  const url = link?.url ?? null;
  const mediaType = link?.media_type ?? null;
  const requestKey = url && mediaType ? `${client.kind}|${url}|${mediaType}` : null;
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    if (!url || !mediaType || !requestKey) return;
    const controller = new AbortController();
    let payloadToRelease: ArtifactPayload | null = null;
    client.getArtifact(url, mediaType, { signal: controller.signal }).then(
      (payload) => {
        if (controller.signal.aborted) {
          payload.release();
          return;
        }
        payloadToRelease = payload;
        setLoaded({ requestKey, payload, error: null });
      },
      (err: unknown) => {
        if (!controller.signal.aborted) setLoaded({ requestKey, payload: null, error: toApiError(err) });
      },
    );
    return () => {
      controller.abort();
      payloadToRelease?.release();
    };
  }, [client, url, mediaType, requestKey]);

  if (!requestKey) return { payload: null, error: null, loading: false };
  if (loaded?.requestKey !== requestKey) return { payload: null, error: null, loading: true };
  return { payload: loaded.payload, error: loaded.error, loading: false };
}
