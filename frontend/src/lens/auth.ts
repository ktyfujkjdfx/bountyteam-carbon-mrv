// Session and roles for the Carbon Lens workspaces.
//
// The token lives in memory and, for a reload, in sessionStorage of this tab only. It is never read
// from a build variable, never written into the URL and never logged. HTTP mode authenticates only
// through /auth/login, /auth/me and /auth/logout. Fixture mode uses a labelled local account list
// and says so on screen.

import { LensError, asRecord } from './client';
import type { components as LensApiComponents } from '../api/generated/openapi.v2';

type LoginRequest = LensApiComponents['schemas']['LoginRequest'];
type ServiceRole = LensApiComponents['schemas']['Role'];

export type LensRole = 'owner' | 'verifier' | 'investor';

export const ROLE_LABELS: Record<LensRole, string> = {
  owner: 'Владелец проекта',
  verifier: 'Верификатор',
  investor: 'Инвестор',
};

export interface LensSession {
  token: string;
  role: LensRole;
  username: string;
  display_name: string;
  /** SERVICE — the service authenticated it; DEMO — a labelled local account of the offline mode. */
  source: 'SERVICE' | 'DEMO';
}

export const LENS_SESSION_STORAGE_KEY = 'carbon-lens.session';

export interface DemoAccount {
  email: string;
  password: string;
  role: LensRole;
  display_name: string;
  hint: string;
}

/**
 * Demo accounts exist only so a reviewer can open every workspace offline. They are not credentials of
 * any service: the password is the same visible word, and the cards are hidden unless demo mode is on.
 */
export const DEMO_ACCOUNTS: DemoAccount[] = [
  { email: 'owner@demo.local', password: 'demo', role: 'owner', display_name: 'Владелец демо-участка', hint: 'Подаёт заявку и вводит заявленный объём.' },
  { email: 'verifier@demo.local', password: 'demo', role: 'verifier', display_name: 'Верификатор демо-очереди', hint: 'Анализирует заявку и финализирует паспорт.' },
  { email: 'investor@demo.local', password: 'demo', role: 'investor', display_name: 'Инвестор демо-портфеля', hint: 'Читает финализированные паспорта и сценарии стоимости.' },
];

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

export function isRole(value: unknown): value is LensRole {
  return value === 'owner' || value === 'verifier' || value === 'investor';
}

function serviceRole(value: ServiceRole | unknown): LensRole | null {
  if (value === 'PROJECT_OWNER') return 'owner';
  if (value === 'VERIFIER') return 'verifier';
  if (value === 'INVESTOR') return 'investor';
  return null;
}

export function readStoredSession(storage: StorageLike | null = safeStorage()): LensSession | null {
  try {
    const raw = storage?.getItem(LENS_SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = asRecord(JSON.parse(raw));
    if (typeof parsed.token !== 'string' || typeof parsed.username !== 'string' || !isRole(parsed.role)) return null;
    return {
      token: parsed.token,
      role: parsed.role,
      username: String(parsed.username ?? ''),
      display_name: String(parsed.display_name ?? ''),
      source: parsed.source === 'SERVICE' ? 'SERVICE' : 'DEMO',
    };
  } catch {
    return null;
  }
}

export function writeStoredSession(session: LensSession | null, storage: StorageLike | null = safeStorage()): void {
  try {
    if (session === null) storage?.removeItem(LENS_SESSION_STORAGE_KEY);
    else storage?.setItem(LENS_SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch {
    /* private mode: the session simply does not survive a reload */
  }
}

export interface AuthTransport {
  baseUrl: string;
  fetchImpl?: typeof fetch | undefined;
}

async function call(transport: AuthTransport, path: string, init: RequestInit): Promise<Response> {
  const fetchImpl = transport.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const base = transport.baseUrl.replace(/\/+$/, '');
  return fetchImpl(`${base}${path}`, { ...init, credentials: 'omit', cache: 'no-store' });
}

/**
 * Sign in against the service. A deployment without /auth/login answers 404/405, and the caller falls
 * back to the labelled demo accounts instead of pretending someone was authenticated.
 */
export async function login(transport: AuthTransport, username: string, password: string): Promise<LensSession> {
  const body: LoginRequest = { username, password };
  let response: Response;
  try {
    response = await call(transport, '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (error) {
    throw new LensError('NETWORK', `Сервис недоступен: ${error instanceof Error ? error.message : String(error)}`);
  }
  if (response.status === 404 || response.status === 405) {
    throw new LensError('AUTH_NOT_DEPLOYED', 'Сервис пока не принимает вход по паролю.', { status: response.status });
  }
  if (response.status === 401) {
    throw new LensError('AUTH_REJECTED', 'Логин или пароль не подошли.', { status: response.status });
  }
  if (response.status === 429) {
    throw new LensError('AUTH_RATE_LIMITED', 'Слишком много попыток входа. Повторите позже.', { status: response.status });
  }
  if (!response.ok) {
    throw new LensError('AUTH_FAILED', `Вход не выполнен: сервис ответил HTTP ${response.status}.`, { status: response.status });
  }
  return sessionFrom(await response.json().catch(() => null));
}

/** Сессия из ответа сервиса. Один разбор на вход по паролю и на вход по роли. */
function sessionFrom(raw: unknown): LensSession {
  const payload = asRecord(raw);
  const user = asRecord(payload.user);
  const token = typeof payload.token === 'string' ? payload.token : typeof payload.access_token === 'string' ? payload.access_token : '';
  const role = serviceRole(user.role);
  if (!token || !role || typeof user.username !== 'string') throw new LensError('CONTRACT', 'Сервис не вернул токен и пользователя сессии.');
  return {
    token,
    role,
    username: user.username,
    display_name: String(user.display_name ?? user.username),
    source: 'SERVICE',
  };
}

/** Роль, в которую можно войти одним нажатием. Пароля здесь нет и быть не может. */
export interface ServiceDemoAccount {
  username: string;
  display_name: string;
  role: LensRole;
}

/**
 * Какие роли сервис разрешает открыть одним нажатием. Пустой список — обычный ответ: в таком
 * развёртывании быстрый вход просто не существует, и экран показывает обычную форму.
 */
export async function fetchDemoAccounts(transport: AuthTransport): Promise<ServiceDemoAccount[]> {
  let response: Response;
  try {
    response = await call(transport, '/auth/demo-accounts', { headers: { Accept: 'application/json' } });
  } catch {
    return [];
  }
  if (!response.ok) return [];
  const payload = asRecord(await response.json().catch(() => null));
  const accounts = Array.isArray(payload.accounts) ? payload.accounts : [];
  return accounts.flatMap((item) => {
    const account = asRecord(item);
    const role = serviceRole(account.role);
    if (!role || typeof account.username !== 'string') return [];
    return [{ username: account.username, display_name: String(account.display_name ?? account.username), role }];
  });
}

/**
 * Вход в демонстрационную роль без пароля: пароль сервис берёт из своего окружения, поэтому в
 * браузер он не попадает и в сборку тоже. Сессия возвращается обычная.
 */
export async function demoServiceLogin(transport: AuthTransport, username: string): Promise<LensSession> {
  let response: Response;
  try {
    response = await call(transport, '/auth/demo-login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ username }),
    });
  } catch (error) {
    throw new LensError('NETWORK', `Сервис недоступен: ${error instanceof Error ? error.message : String(error)}`);
  }
  if (response.status === 404) {
    throw new LensError('DEMO_NOT_CONFIGURED', 'Быстрый вход на этом сервисе не настроен: войдите по имени и паролю.', { status: response.status });
  }
  if (response.status === 429) {
    throw new LensError('AUTH_RATE_LIMITED', 'Слишком много попыток входа. Повторите позже.', { status: response.status });
  }
  if (!response.ok) {
    throw new LensError('AUTH_FAILED', `Вход не выполнен: сервис ответил HTTP ${response.status}.`, { status: response.status });
  }
  return sessionFrom(await response.json().catch(() => null));
}

/** Restore a session on reload. Returns null when the service has no /auth/me yet. */
export async function fetchMe(transport: AuthTransport, token: string): Promise<LensSession | null> {
  let response: Response;
  try {
    response = await call(transport, '/auth/me', { headers: { Accept: 'application/json', Authorization: `Bearer ${token}` } });
  } catch {
    return null;
  }
  if (response.status === 401 || response.status === 403) throw new LensError('AUTH_EXPIRED', 'Сессия истекла, войдите снова.', { status: response.status });
  if (!response.ok) return null;
  const payload = asRecord(await response.json().catch(() => null));
  const role = serviceRole(payload.role);
  if (!role || typeof payload.username !== 'string') return null;
  return { token, role, username: payload.username, display_name: String(payload.display_name ?? payload.username), source: 'SERVICE' };
}

/** Revoke the current server session. The caller clears local state even if the service is unavailable. */
export async function logout(transport: AuthTransport, token: string): Promise<void> {
  let response: Response;
  try {
    response = await call(transport, '/auth/logout', {
      method: 'POST',
      headers: { Accept: 'application/json', Authorization: `Bearer ${token}` },
    });
  } catch (error) {
    throw new LensError('NETWORK', `Сервис недоступен: ${error instanceof Error ? error.message : String(error)}`);
  }
  if (response.status === 401) return;
  if (!response.ok) {
    throw new LensError('AUTH_LOGOUT_FAILED', `Сервис не завершил сессию: HTTP ${response.status}.`, { status: response.status });
  }
}

/** Sign in offline against a labelled demo account. */
export function demoLogin(email: string, password: string): LensSession {
  const account = DEMO_ACCOUNTS.find((item) => item.email.toLowerCase() === email.trim().toLowerCase());
  if (!account || account.password !== password) {
    throw new LensError('AUTH_REJECTED', 'Почта или пароль не подошли. В демо-режиме доступны только перечисленные учётные записи.');
  }
  return {
    token: `demo-${account.role}-${Math.random().toString(36).slice(2, 10)}`,
    role: account.role,
    username: account.email,
    display_name: account.display_name,
    source: 'DEMO',
  };
}

export interface RolePermissions {
  canSubmitRequest: boolean;
  canEditClaim: boolean;
  canRunAnalysis: boolean;
  canFinalize: boolean;
  canSeeQueue: boolean;
  canSeeFinalizedOnly: boolean;
  canSeeValueScenarios: boolean;
}

/** One table so a screen never invents a permission of its own. */
export function permissionsFor(role: LensRole): RolePermissions {
  switch (role) {
    case 'owner':
      return {
        canSubmitRequest: true,
        canEditClaim: true,
        canRunAnalysis: false,
        canFinalize: false,
        canSeeQueue: false,
        canSeeFinalizedOnly: false,
        canSeeValueScenarios: true,
      };
    case 'verifier':
      return {
        canSubmitRequest: false,
        canEditClaim: false,
        canRunAnalysis: true,
        canFinalize: true,
        canSeeQueue: true,
        canSeeFinalizedOnly: false,
        canSeeValueScenarios: true,
      };
    case 'investor':
    default:
      return {
        canSubmitRequest: false,
        canEditClaim: false,
        canRunAnalysis: false,
        canFinalize: false,
        canSeeQueue: false,
        canSeeFinalizedOnly: true,
        canSeeValueScenarios: true,
      };
  }
}

export const FORBIDDEN_NOTE =
  'Этот экран доступен другой роли. Клиент скрывает действие, но решение принимает сервис: запрос без права завершится ответом 403.';
