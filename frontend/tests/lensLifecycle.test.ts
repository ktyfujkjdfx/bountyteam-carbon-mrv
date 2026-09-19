// The request lifecycle in HTTP mode, where the service owns the state.
//
// Two mistakes are worth a test each. The first is collapsing the service's states into fewer of
// them: a request being calculated then looks exactly like one waiting for a verifier, and the
// queue offers a second run the service answers with 409. The second is keeping server state in
// sessionStorage, where a stale tab can outlive the session and contradict the service.

import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, beforeEach } from 'vitest';
import type { LensApiClient, VerificationRequest } from '../src/lens/client';
import { useWorkspace } from '../src/lens/useWorkspace';
import { WORKSPACE_STORAGE_KEY, passportStatusOf, type Submission } from '../src/lens/workspace';
import type { Catalog } from '../src/lens/types';

const CATALOG: Catalog = {
  areas: [],
  max_area_ha: 2000,
  generated_at: '2026-09-19T00:00:00Z',
} as unknown as Catalog;

function request(status: string, over: Partial<VerificationRequest> = {}): VerificationRequest {
  return {
    request_id: `vr-${status.toLowerCase()}`,
    status,
    owner: { user_id: 'u-1', username: 'owner', display_name: 'Owner', role: 'PROJECT_OWNER' },
    aoi_id: 'RU_TVER_01',
    geometry: { type: 'Polygon', coordinates: [[[32.9, 56.5], [32.95, 56.5], [32.95, 56.55], [32.9, 56.55], [32.9, 56.5]]] },
    geometry_hash: 'sha256:' + '0'.repeat(64),
    area_ha: 1750.4731,
    year_start: 2019,
    year_end: 2024,
    claimed_units: 1000,
    claim_pool: 'AGB_LIVE_WOODY',
    claim_unit: 'POTENTIAL_UNIT_OF_THE_CASE',
    analysis_id: null,
    analysis_url: null,
    passport_hash: null,
    finalized_by: null,
    finalized_at: null,
    created_at: '2026-09-19T00:00:00Z',
    updated_at: '2026-09-19T00:00:00Z',
    events: [],
    ...over,
  } as unknown as VerificationRequest;
}

function httpClient(requests: VerificationRequest[]): LensApiClient {
  return {
    kind: 'http',
    getCatalog: async () => CATALOG,
    measureArea: async () => {
      throw new Error('not used');
    },
    createAnalysis: async () => {
      throw new Error('not used');
    },
    getAnalysis: async () => {
      throw new Error('no analysis was attached to these requests');
    },
    getProof: async () => {
      throw new Error('not used');
    },
    getReport: async () => {
      throw new Error('not used');
    },
    getReportHtml: async () => {
      throw new Error('not used');
    },
    getArtifact: async () => {
      throw new Error('not used');
    },
    listRequests: async () => requests,
  } as unknown as LensApiClient;
}

async function submissionsFor(requests: VerificationRequest[]): Promise<Submission[]> {
  // One client for the whole render tree, as `LensApp` memoizes it: a fresh object per render would
  // invalidate every callback that depends on it and spin the effect that reloads the queue.
  const client = httpClient(requests);
  const { result } = renderHook(() => useWorkspace(client, 'owner'));
  await waitFor(() => expect(result.current.submissions.length).toBe(requests.length));
  return result.current.submissions;
}

describe('request state comes from the service', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('keeps every state the service publishes distinct', async () => {
    const statuses = ['DRAFT', 'SUBMITTED', 'ANALYSING', 'CALCULATED', 'FINALIZED'];
    const submissions = await submissionsFor(statuses.map((status) => request(status)));
    expect(submissions.map((item) => item.status)).toEqual(statuses);
  });

  it('shows a state it does not know as unknown rather than guessing a known one', async () => {
    const [submission] = await submissionsFor([request('WITHDRAWN')]);
    expect(submission?.status).toBe('UNKNOWN');
    // The failure this guards against is the silent one: a state read as SUBMITTED would put a
    // withdrawn request back in the queue as work to do.
    expect(submission?.status).not.toBe('SUBMITTED');
  });

  it('does not put server state into sessionStorage', async () => {
    await submissionsFor([request('CALCULATED')]);
    expect(sessionStorage.getItem(WORKSPACE_STORAGE_KEY)).toBeNull();
  });

  it('ignores a workspace left in sessionStorage by an earlier fixture session', async () => {
    sessionStorage.setItem(
      WORKSPACE_STORAGE_KEY,
      JSON.stringify({ schema: 'carbon-lens-workspace-3', submissions: [{ submission_id: 'sub-stale', title: 'СТАРАЯ ЗАЯВКА' }] }),
    );
    const submissions = await submissionsFor([request('SUBMITTED')]);
    expect(submissions.map((item) => item.submission_id)).toEqual(['vr-submitted']);
  });
});

describe('the passport badge follows the request', () => {
  const base = { result: null, status: 'SUBMITTED' } as unknown as Submission;

  it('names a run in flight instead of calling it a draft', () => {
    expect(passportStatusOf({ ...base, status: 'ANALYSING' })).toBe('ANALYSING');
  });

  it('keeps a finished run on screen while the service still reports ANALYSING', () => {
    // A recalculation of an already calculated request: the number on screen is real, so the badge
    // must not fall back to the empty state while the service catches up.
    const withResult = { ...base, status: 'ANALYSING', result: {} } as unknown as Submission;
    expect(passportStatusOf(withResult)).toBe('CALCULATED');
  });

  it('does not claim a state for a request whose state it cannot read', () => {
    expect(passportStatusOf({ ...base, status: 'UNKNOWN' })).toBe('UNKNOWN');
  });

  it('keeps an integrity failure ahead of every service state', () => {
    expect(passportStatusOf({ ...base, status: 'INTEGRITY_FAILED' })).toBe('INTEGRITY_FAILED');
  });
});
