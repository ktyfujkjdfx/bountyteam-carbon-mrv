// Mode selection for the Carbon Lens workspace. Switching between the labelled fixture set and a live
// service is a configuration decision only — the app never substitutes one for the other by itself.

import { createFixtureLensClient, type LensApiClient } from './adapter';
import { createHttpLensClient } from './httpClient';

export type LensMode = 'fixture' | 'http';

export interface LensConfig {
  mode: LensMode;
  baseUrl: string;
  token: string;
  tokenSource: 'none' | 'session' | 'url';
  source: 'env' | 'url';
}

interface EnvLike {
  VITE_LENS_API_MODE?: string;
  VITE_LENS_API_BASE_URL?: string;
}

export const LENS_TOKEN_STORAGE_KEY = 'carbon-lens.token';

interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

function safeStorage(): StorageLike | null {
  try {
    return globalThis.sessionStorage ?? null;
  } catch {
    return null;
  }
}

/**
 * The credential is a runtime value: it comes from the URL of the session or from sessionStorage and is
 * never read from VITE_* build variables, so a published dist carries no session of its own.
 */
export function resolveLensConfig(env: EnvLike, search: string, storage: StorageLike | null = safeStorage()): LensConfig {
  const params = new URLSearchParams(search);
  const fromUrl = params.get('lensapi');
  const envMode: LensMode = env.VITE_LENS_API_MODE === 'http' ? 'http' : 'fixture';
  const mode: LensMode = fromUrl === 'http' || fromUrl === 'fixture' ? fromUrl : envMode;

  const urlToken = params.get('token')?.trim() ?? '';
  let token = '';
  let tokenSource: LensConfig['tokenSource'] = 'none';
  if (urlToken) {
    token = urlToken;
    tokenSource = 'url';
    try {
      storage?.setItem(LENS_TOKEN_STORAGE_KEY, urlToken);
    } catch {
      /* storage unavailable: the token simply stays for this page only */
    }
  } else {
    const stored = storage?.getItem(LENS_TOKEN_STORAGE_KEY)?.trim() ?? '';
    if (stored) {
      token = stored;
      tokenSource = 'session';
    }
  }

  return {
    mode,
    baseUrl: env.VITE_LENS_API_BASE_URL?.trim() || '/api/v2',
    token,
    tokenSource,
    source: fromUrl === 'http' || fromUrl === 'fixture' ? 'url' : 'env',
  };
}

export function setLensToken(value: string, storage: StorageLike | null = safeStorage()): void {
  try {
    if (value.trim() === '') storage?.removeItem(LENS_TOKEN_STORAGE_KEY);
    else storage?.setItem(LENS_TOKEN_STORAGE_KEY, value.trim());
  } catch {
    /* ignore storage failures: the workspace keeps working without a stored credential */
  }
}

export function createLensClient(config: LensConfig): LensApiClient {
  if (config.mode === 'http') {
    return createHttpLensClient({ baseUrl: config.baseUrl, token: config.token });
  }
  return createFixtureLensClient();
}

export function switchLensModeHref(target: LensMode, location: Pick<Location, 'pathname' | 'search' | 'hash'>): string {
  const params = new URLSearchParams(location.search);
  params.set('lensapi', target);
  params.delete('token');
  return `${location.pathname}?${params.toString()}${location.hash}`;
}
