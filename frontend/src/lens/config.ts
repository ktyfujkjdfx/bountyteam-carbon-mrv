// Which client answers, and where the live service lives. The choice is configuration only: a failing
// service is reported as a failure and never replaced by the offline set behind the user's back.

import { createFixtureLensClient } from './fixtureClient';
import { createHttpLensClient, type LensAuthScheme } from './httpClient';
import type { LensApiClient } from './client';

export type LensMode = 'http' | 'fixture';

export interface LensConfig {
  mode: LensMode;
  baseUrl: string;
  source: 'env' | 'url' | 'default';
  demoAccounts: boolean;
  authScheme: LensAuthScheme;
}

interface EnvLike {
  VITE_LENS_API_MODE?: string;
  VITE_LENS_API_BASE_URL?: string;
  VITE_LENS_DEMO_ACCOUNTS?: string;
  VITE_LENS_AUTH_SCHEME?: string;
}

/**
 * The live service is the default. The offline set is entered only by an explicit `?lens=fixture`
 * or a build variable, and both are shown in the header so no one mistakes one for the other.
 */
export function resolveLensConfig(env: EnvLike, search: string): LensConfig {
  const params = new URLSearchParams(search);
  const fromUrl = params.get('lens');
  const envMode = env.VITE_LENS_API_MODE === 'fixture' ? 'fixture' : env.VITE_LENS_API_MODE === 'http' ? 'http' : null;
  const mode: LensMode = fromUrl === 'fixture' || fromUrl === 'http' ? fromUrl : (envMode ?? 'http');
  const demoFlag = env.VITE_LENS_DEMO_ACCOUNTS === '1' || params.get('demo') === '1';
  const authParam = params.get('auth');
  const authScheme: LensAuthScheme =
    authParam === 'demo' || authParam === 'demo-header'
      ? 'demo-header'
      : authParam === 'bearer'
        ? 'bearer'
        : env.VITE_LENS_AUTH_SCHEME === 'demo-header'
          ? 'demo-header'
          : 'bearer';
  return {
    mode,
    baseUrl: env.VITE_LENS_API_BASE_URL?.trim() || '/api/v2',
    source: fromUrl === 'fixture' || fromUrl === 'http' ? 'url' : envMode ? 'env' : 'default',
    // Demo accounts are offered offline, or when a deployment explicitly asks for them.
    demoAccounts: demoFlag || mode === 'fixture',
    authScheme,
  };
}

export interface ClientFactoryOptions {
  getToken: () => string;
  getActor?: (() => string) | undefined;
  fetchImpl?: typeof fetch | undefined;
}

export function createLensClient(config: LensConfig, options: ClientFactoryOptions): LensApiClient {
  if (config.mode === 'fixture') return createFixtureLensClient();
  return createHttpLensClient({
    baseUrl: config.baseUrl,
    getToken: options.getToken,
    getActor: options.getActor,
    authScheme: config.authScheme,
    fetchImpl: options.fetchImpl,
  });
}

export function switchModeHref(target: LensMode, location: Pick<Location, 'pathname' | 'search' | 'hash'>): string {
  const params = new URLSearchParams(location.search);
  params.set('lens', target);
  params.delete('token');
  return `${location.pathname}?${params.toString()}${location.hash}`;
}
