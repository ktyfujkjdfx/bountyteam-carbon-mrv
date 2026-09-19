// The session as an external store: the HTTP client reads the current token through a getter, and
// React subscribes to changes. Keeping it outside the component tree is what lets a client created
// once still pick up a re-login without reading a ref during render.

import { readStoredSession, writeStoredSession, type LensSession } from './auth';

type Listener = () => void;

let current: LensSession | null = null;
let loaded = false;
const listeners = new Set<Listener>();

function emit(): void {
  for (const listener of listeners) listener();
}

export function subscribeSession(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getSession(): LensSession | null {
  if (!loaded) {
    current = readStoredSession();
    loaded = true;
  }
  return current;
}

export function setSession(session: LensSession | null, persist = true): void {
  loaded = true;
  current = session;
  if (persist) writeStoredSession(session);
  emit();
}

export function getToken(): string {
  return getSession()?.token ?? '';
}

/** The legacy demo header needs an actor label; the calculation itself does not depend on it. */
/** Tests and previews start from a known session without touching browser storage. */
export function resetSessionStore(session: LensSession | null = null): void {
  loaded = true;
  current = session;
  emit();
}
