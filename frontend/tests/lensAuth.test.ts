import { describe, expect, it, vi } from 'vitest';
import { DEMO_ACCOUNTS, demoLogin, fetchMe, login, permissionsFor, readStoredSession, writeStoredSession } from '../src/lens/auth';
import { getActor, getToken, resetSessionStore, setSession } from '../src/lens/sessionStore';
import { lifecycleAvailability, loadSubmissions, newSubmission, passportStatusOf, recordStep, saveSubmissions, visibleTo, type Submission } from '../src/lens/workspace';
import type { AnalysisResult, Geometry } from '../src/lens/types';

const geometry: Geometry = { type: 'Polygon', coordinates: [[[32.91, 56.59], [32.94, 56.59], [32.94, 56.61], [32.91, 56.61], [32.91, 56.59]]] };

function submission(overrides: Partial<Submission> = {}): Submission {
  return {
    ...newSubmission({ owner_email: 'owner@demo.local', title: 'RU_TVER_01', aoi_id: 'RU_TVER_01', geometry, year_start: 2019, year_end: 2024, claimed_units: null }),
    ...overrides,
  };
}

function resultWithQ(q: number | null): AnalysisResult {
  return { units: { q } } as unknown as AnalysisResult;
}

describe('sign-in', () => {
  it('accepts a labelled demo account and refuses a wrong password', () => {
    const session = demoLogin('verifier@demo.local', 'demo');
    expect(session.role).toBe('verifier');
    expect(session.source).toBe('DEMO');
    expect(() => demoLogin('verifier@demo.local', 'wrong')).toThrow(/не подошли/);
    expect(() => demoLogin('stranger@demo.local', 'demo')).toThrow(/не подошли/);
    expect(DEMO_ACCOUNTS.map((account) => account.role).sort()).toEqual(['investor', 'owner', 'verifier']);
  });

  it('reports a service that has no password route yet, instead of pretending', async () => {
    const fetchImpl = vi.fn(async () => new Response('', { status: 404 }));
    await expect(login({ baseUrl: 'https://service.test/api/v2', fetchImpl: fetchImpl as unknown as typeof fetch }, 'a@b.c', 'x')).rejects.toMatchObject({
      code: 'AUTH_NOT_DEPLOYED',
    });
  });

  it('passes a rejected password through as a rejection, not as an outage', async () => {
    const fetchImpl = vi.fn(async () => new Response('', { status: 401 }));
    await expect(login({ baseUrl: 'https://service.test/api/v2', fetchImpl: fetchImpl as unknown as typeof fetch }, 'a@b.c', 'x')).rejects.toMatchObject({
      code: 'AUTH_REJECTED',
    });
  });

  it('restores a session from the service and signs out on a rejected token', async () => {
    const ok = vi.fn(async () => new Response(JSON.stringify({ role: 'owner', email: 'o@x.y', display_name: 'O' }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    const restored = await fetchMe({ baseUrl: 'https://service.test/api/v2', fetchImpl: ok as unknown as typeof fetch }, 'tok');
    expect(restored).toMatchObject({ role: 'owner', source: 'SERVICE' });

    const expired = vi.fn(async () => new Response('', { status: 401 }));
    await expect(fetchMe({ baseUrl: 'https://service.test/api/v2', fetchImpl: expired as unknown as typeof fetch }, 'tok')).rejects.toMatchObject({ code: 'AUTH_EXPIRED' });
  });

  it('keeps the token in the tab session only and clears it on sign-out', () => {
    const session = demoLogin('owner@demo.local', 'demo');
    writeStoredSession(session);
    expect(readStoredSession()?.token).toBe(session.token);
    expect(window.location.href).not.toContain(session.token);
    writeStoredSession(null);
    expect(readStoredSession()).toBeNull();
  });

  it('exposes the current token to the client through the store, not through a ref in render', () => {
    resetSessionStore(null);
    expect(getToken()).toBe('');
    setSession(demoLogin('investor@demo.local', 'demo'), false);
    expect(getToken()).not.toBe('');
    expect(getActor()).toBe('buyer');
    resetSessionStore(null);
  });
});

describe('role permissions', () => {
  it('gives each role different actions', () => {
    expect(permissionsFor('owner')).toMatchObject({ canSubmitRequest: true, canRunAnalysis: false, canFinalize: false, canSeeQueue: false });
    expect(permissionsFor('verifier')).toMatchObject({ canSubmitRequest: false, canRunAnalysis: true, canFinalize: true, canSeeQueue: true });
    expect(permissionsFor('investor')).toMatchObject({ canSubmitRequest: false, canRunAnalysis: false, canFinalize: false, canSeeFinalizedOnly: true });
  });

  it('shows an owner only their own requests and an investor only finalised ones', () => {
    const mine = submission();
    const other = submission({ owner_email: 'someone@else.local' });
    const finalized = submission({ status: 'FINALIZED' });
    const all = [mine, other, finalized];
    expect(visibleTo(all, 'owner', 'owner@demo.local').map((item) => item.submission_id).sort()).toEqual([mine.submission_id, finalized.submission_id].sort());
    expect(visibleTo(all, 'investor', 'investor@demo.local')).toEqual([finalized]);
    expect(visibleTo(all, 'verifier', 'verifier@demo.local')).toHaveLength(3);
  });
});

describe('submissions and the demo lifecycle', () => {
  it('survives a reload and ignores another schema version', () => {
    const one = submission();
    saveSubmissions([one]);
    expect(loadSubmissions()).toHaveLength(1);
    sessionStorage.setItem('carbon-lens.workspace', JSON.stringify({ schema: 'older', submissions: [one] }));
    expect(loadSubmissions()).toEqual([]);
    sessionStorage.clear();
  });

  it('tracks the passport status through the lifecycle', () => {
    const draft = submission();
    expect(passportStatusOf(draft)).toBe('DRAFT');
    const calculated = { ...draft, result: resultWithQ(10), status: 'CALCULATED' as const };
    expect(passportStatusOf(calculated)).toBe('CALCULATED');
    expect(passportStatusOf({ ...calculated, status: 'FINALIZED' })).toBe('FINALIZED');
    expect(passportStatusOf({ ...calculated, status: 'INTEGRITY_FAILED' })).toBe('INTEGRITY_FAILED');
  });

  it('offers a demo issue only after finalisation and only when units exist', () => {
    const calculated = submission({ status: 'CALCULATED', result: resultWithQ(10) });
    expect(lifecycleAvailability(calculated, 'DEMO_ISSUE')).toMatchObject({ allowed: false });

    const zero = submission({ status: 'FINALIZED', result: resultWithQ(0) });
    expect(lifecycleAvailability(zero, 'DEMO_ISSUE').reason).toMatch(/0 единиц/);

    const missing = submission({ status: 'FINALIZED', result: resultWithQ(null) });
    expect(lifecycleAvailability(missing, 'DEMO_ISSUE').reason).toMatch(/не рассчитаны/);

    const ready = submission({ status: 'FINALIZED', result: resultWithQ(10) });
    expect(lifecycleAvailability(ready, 'DEMO_ISSUE').allowed).toBe(true);
    expect(lifecycleAvailability(ready, 'DEMO_TRANSFER').allowed).toBe(false);

    const issued = recordStep(ready, 'DEMO_ISSUE', 'investor@demo.local');
    expect(lifecycleAvailability(issued, 'DEMO_TRANSFER').allowed).toBe(true);
    const transferred = recordStep(issued, 'DEMO_TRANSFER', 'investor@demo.local');
    expect(lifecycleAvailability(transferred, 'DEMO_RETIREMENT').allowed).toBe(true);
  });
});
