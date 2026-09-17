export type TrackedKind = 'verify' | 'issue' | 'buy' | 'transfer';

export interface TrackedIntent {
  intentKey: string;
  kind: TrackedKind;
  idempotencyKey: string;
  body: unknown;
  statusUrl: string | null;
  createdAt: string;
}

const STORAGE_KEY = 'bountyteam.frontend.intents.v1';

function storage(): Storage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

function readAll(): Record<string, TrackedIntent> {
  const store = storage();
  if (!store) return {};
  try {
    const parsed: unknown = JSON.parse(store.getItem(STORAGE_KEY) ?? '{}');
    return typeof parsed === 'object' && parsed !== null ? (parsed as Record<string, TrackedIntent>) : {};
  } catch {
    return {};
  }
}

function writeAll(all: Record<string, TrackedIntent>): void {
  try {
    storage()?.setItem(STORAGE_KEY, JSON.stringify(all));
  } catch {
    // Persistence is best effort; the in-memory key still protects the current session.
  }
}

export function newIdempotencyKey(): string {
  return `fe-${crypto.randomUUID()}`;
}

// Same intent + same body reuses the stored key, so a retry after refresh cannot create a second operation.
export function beginIntent(intentKey: string, kind: TrackedKind, body: unknown): TrackedIntent {
  const all = readAll();
  const existing = all[intentKey];
  if (existing && existing.statusUrl === null && JSON.stringify(existing.body) === JSON.stringify(body)) {
    return existing;
  }
  const intent: TrackedIntent = {
    intentKey,
    kind,
    idempotencyKey: newIdempotencyKey(),
    body,
    statusUrl: null,
    createdAt: new Date().toISOString(),
  };
  all[intentKey] = intent;
  writeAll(all);
  return intent;
}

export function attachStatusUrl(intentKey: string, statusUrl: string): void {
  const all = readAll();
  const intent = all[intentKey];
  if (!intent) return;
  all[intentKey] = { ...intent, statusUrl };
  writeAll(all);
}

export function finishIntent(intentKey: string): void {
  const all = readAll();
  if (!(intentKey in all)) return;
  writeAll(Object.fromEntries(Object.entries(all).filter(([key]) => key !== intentKey)));
}

export function pendingIntents(prefix: string): TrackedIntent[] {
  return Object.values(readAll()).filter((intent) => intent.intentKey.startsWith(prefix) && intent.statusUrl !== null);
}
