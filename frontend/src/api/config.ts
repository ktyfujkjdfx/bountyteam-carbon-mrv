import type { AdapterKind, MrvApiClient } from './client';
import { createHttpAdapter } from './httpAdapter';

export interface AppConfig {
  adapter: AdapterKind;
  baseUrl: string;
  demoSession: string;
  demoAuthorizationId: string;
  source: 'env' | 'url';
}

interface EnvLike {
  VITE_API_MODE?: string;
  VITE_API_BASE_URL?: string;
  VITE_DEMO_SESSION?: string;
  VITE_DEMO_AUTHORIZATION_ID?: string;
}

export function resolveConfig(env: EnvLike, search: string): AppConfig {
  const params = new URLSearchParams(search);
  const fromUrl = params.get('api');
  const envMode = env.VITE_API_MODE === 'http' ? 'http' : 'fixture';
  const adapter: AdapterKind = fromUrl === 'http' || fromUrl === 'fixture' ? fromUrl : envMode;
  return {
    adapter,
    baseUrl: env.VITE_API_BASE_URL?.trim() || '/api/v1',
    demoSession: env.VITE_DEMO_SESSION?.trim() || '',
    demoAuthorizationId: env.VITE_DEMO_AUTHORIZATION_ID?.trim() || 'SYNTHETIC-AUTH-001',
    source: fromUrl === 'http' || fromUrl === 'fixture' ? 'url' : 'env',
  };
}

export async function createClient(config: AppConfig): Promise<MrvApiClient> {
  if (config.adapter === 'http') {
    return createHttpAdapter({ baseUrl: config.baseUrl, demoSession: config.demoSession });
  }
  const { createFixtureBackend } = await import('./fixtureAdapter');
  return createFixtureBackend().client;
}

export function switchAdapterHref(target: AdapterKind, location: Pick<Location, 'pathname' | 'search' | 'hash'>): string {
  const params = new URLSearchParams(location.search);
  params.set('api', target);
  return `${location.pathname}?${params.toString()}${location.hash}`;
}
