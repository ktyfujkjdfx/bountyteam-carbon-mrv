// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { ApiError } from '../src/api/errors';
import { createFixtureBackend } from '../src/api/fixtureAdapter';
import type { MrvApiClient } from '../src/api/client';
import type { Operation } from '../src/api/types';
import { expectSchema } from './schema';

const PLOT = 'SYNTHETIC-PLOT-001';

function setup() {
  let t = Date.parse('2026-09-17T10:00:00Z');
  const backend = createFixtureBackend({ now: () => t });
  const advance = (ms = 10_000) => {
    t += ms;
  };
  return { ...backend, advance };
}

async function rejection(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (err) {
    if (err instanceof ApiError) return err;
    throw err;
  }
  throw new Error('expected rejection');
}

async function settleOperation(client: MrvApiClient, advance: (ms?: number) => void, statusUrl: string): Promise<Operation[]> {
  const seen: Operation[] = [];
  seen.push(await client.getOperation(statusUrl));
  advance(1000);
  seen.push(await client.getOperation(statusUrl));
  advance(10_000);
  seen.push(await client.getOperation(statusUrl));
  seen.forEach((op) => expectSchema('Operation', op));
  return seen;
}

describe('fixture adapter: contract compatibility', () => {
  it('returns schema-valid static responses copied from golden fixtures', async () => {
    const { client } = setup();
    expectSchema('Health', await client.getHealth());
    expectSchema('Plots', await client.listPlots());
    expectSchema('Plot', await client.getPlot(PLOT, 'issuer'));
    expectSchema('History', await client.getHistory(PLOT));
    expectSchema('Credits', await client.getCredits(PLOT, 'issuer'));
    expectSchema('Events', await client.listEvents({ plotId: PLOT }));
    const plot = await client.getPlot(PLOT, 'issuer');
    const verification = await client.getVerification(plot.latest_verification_id as string);
    expectSchema('Verification', verification);
    expectSchema('Proof', await client.getProof(verification.verification_id));
    expectSchema('VerificationEvidence', await client.getCanonicalEvidence(verification.verification_id));
    expect((await client.getHealth()).mode).toBe('CONTRACT_FIXTURE');
    expect(verification.evidence.dataset_kind).toBe('SYNTHETIC');
  });

  it('runs the full P0 flow with schema-valid responses and honest state transitions', async () => {
    const { client, advance } = setup();

    const issueAccepted = await client.issueBatch(PLOT, 'issuer', { demo_authorization_id: 'SYNTHETIC-AUTH-001' }, { idempotencyKey: 'issue-key-001' });
    expectSchema('OperationAccepted', issueAccepted);
    const issueStates = await settleOperation(client, advance, issueAccepted.status_url);
    expect(issueStates.map((o) => o.transaction_state)).toEqual(['QUEUED', 'SUBMITTED', 'CONFIRMED']);
    expect(issueStates[2]?.receipt?.state_readback_ok).toBe(true);

    let credits = await client.getCredits(PLOT, 'buyer');
    expectSchema('Credits', credits);
    expect(credits.items[0]?.credit_status).toBe('ACTIVE');
    expect(credits.items[0]?.can_buy).toBe(true);

    const buy = await client.buyCredits('1', 'buyer', { amount: '10' }, { idempotencyKey: 'buy-key-0001' });
    await settleOperation(client, advance, buy.status_url);
    credits = await client.getCredits(PLOT, 'buyer');
    expect(credits.items[0]?.actor_balance).toBe('10');
    expect(credits.items[0]?.seller_balance).toBe('90');

    const job = await client.startVerification(PLOT, 'issuer', { scenario_id: 'post_fire' }, { idempotencyKey: 'verify-key-01' });
    expectSchema('JobAccepted', job);
    const queued = await client.getJob(job.status_url);
    expect(queued.state).toBe('QUEUED');
    advance(1000);
    expect((await client.getJob(job.status_url)).state).toBe('RUNNING');
    advance(5000);
    const done = await client.getJob(job.status_url);
    expectSchema('Job', done);
    expect(done.state).toBe('SUCCEEDED');

    const fire = await client.getVerification(done.verification_id as string);
    expectSchema('Verification', fire);
    expect(fire.decision).toBe('FREEZE_REQUESTED');

    // FREEZE_REQUESTED is not FROZEN: batch stays ACTIVE until the freeze operation confirms.
    credits = await client.getCredits(PLOT, 'buyer');
    expect(credits.items[0]?.credit_status).toBe('ACTIVE');
    expect(credits.items[0]?.can_transfer_backend).toBe(false);
    expect(await rejection(client.transferCredits('1', 'buyer', { to_actor: 'recipient', amount: '1' }, { idempotencyKey: 'transfer-pending' }))).toMatchObject({
      status: 409,
      code: 'FREEZE_PENDING',
    });

    advance(1000);
    let events = await client.listEvents({ plotId: PLOT });
    const submitted = events.items.find((e) => e.kind === 'TX_SUBMITTED' && e.message.includes('FREEZE'));
    expect(submitted?.operation_id).toBeTruthy();
    const freezeOp = await client.getOperation(submitted?.operation_id as string);
    expect(freezeOp.kind).toBe('FREEZE');
    expect(freezeOp.transaction_state).toBe('SUBMITTED');
    expect((await client.getCredits(PLOT, 'buyer')).items[0]?.credit_status).toBe('ACTIVE');

    advance(10_000);
    const confirmed = await client.getOperation(freezeOp.operation_id);
    expectSchema('Operation', confirmed);
    expect(confirmed.transaction_state).toBe('CONFIRMED');
    credits = await client.getCredits(PLOT, 'buyer');
    expectSchema('Credits', credits);
    expect(credits.items[0]?.credit_status).toBe('FROZEN');
    expect(credits.items[0]?.frozen_at).not.toBeNull();
    expect(credits.items[0]?.actor_balance).toBe('10');

    const rejected = await rejection(client.transferCredits('1', 'buyer', { to_actor: 'recipient', amount: '1' }, { idempotencyKey: 'transfer-frozen' }));
    expect(rejected).toMatchObject({ kind: 'http', status: 409, code: 'BATCH_NOT_ACTIVE' });
    expect(rejected.requestId).toMatch(/^[0-9a-f-]{36}$/);

    const fireProof = await client.getProof(fire.verification_id);
    expectSchema('Proof', fireProof);
    expect(fireProof.anchors.map((a) => a.event_name)).toEqual(['Frozen']);
    const baselineProof = await client.getProof('20000000-0000-4000-8000-000000000001');
    expect(baselineProof.anchors.map((a) => a.event_name)).toEqual(['Issued']);

    events = await client.listEvents({ plotId: PLOT });
    expectSchema('Events', events);
    expect(events.items.some((e) => e.kind === 'TX_CONFIRMED' && e.operation_id === freezeOp.operation_id)).toBe(true);
  });

  it('insufficient evidence yields REVIEW_REQUIRED, no anchors and never unfreezes or freezes', async () => {
    const { client, advance } = setup();
    const job = await client.startVerification(PLOT, 'issuer', { scenario_id: 'insufficient' }, { idempotencyKey: 'verify-insuff' });
    advance(10_000);
    const done = await client.getJob(job.job_id);
    const verification = await client.getVerification(done.verification_id as string);
    expect(verification.evidence_quality).toBe('INSUFFICIENT');
    expect(verification.decision).toBe('REVIEW_REQUIRED');
    expect((await client.getProof(verification.verification_id)).anchors).toEqual([]);
    const plot = await client.getPlot(PLOT, 'issuer');
    expect(plot.can_issue).toBe(false);
    expect(plot.action_block_reason).toContain('REVIEW_REQUIRED');
    const history = await client.getHistory(PLOT);
    expect(history.items.filter((i) => i.is_latest)).toHaveLength(1);
  });
});

describe('fixture adapter: negative paths', () => {
  it('idempotency: same key + body returns the same operation, different body is 409', async () => {
    const { client } = setup();
    const body = { demo_authorization_id: 'SYNTHETIC-AUTH-001' };
    const first = await client.issueBatch(PLOT, 'issuer', body, { idempotencyKey: 'same-key-123' });
    const second = await client.issueBatch(PLOT, 'issuer', body, { idempotencyKey: 'same-key-123' });
    expect(second.operation_id).toBe(first.operation_id);
    const conflict = await rejection(client.issueBatch(PLOT, 'issuer', { demo_authorization_id: 'OTHER-AUTH' }, { idempotencyKey: 'same-key-123' }));
    expect(conflict).toMatchObject({ status: 409, code: 'IDEMPOTENCY_CONFLICT' });
  });

  it('wrong actor 403, unknown plot/batch/operation 404, bad body 422', async () => {
    const { client } = setup();
    expect(await rejection(client.startVerification(PLOT, 'buyer', { scenario_id: 'baseline' }, { idempotencyKey: 'k-00000001' }))).toMatchObject({ status: 403 });
    expect(await rejection(client.getPlot('NOPE', 'issuer'))).toMatchObject({ status: 404 });
    expect(await rejection(client.buyCredits('7', 'buyer', { amount: '1' }, { idempotencyKey: 'k-00000002' }))).toMatchObject({ status: 404 });
    expect(await rejection(client.getOperation('40000000-0000-4000-8000-00000000ffff'))).toMatchObject({ status: 404 });
    const invalid = await rejection(
      client.startVerification(PLOT, 'issuer', { scenario_id: 'simulate_fire' } as never, { idempotencyKey: 'k-00000003' }),
    );
    expect(invalid).toMatchObject({ status: 422, code: 'INVALID_EVIDENCE' });
    expect(await rejection(client.getArtifact('/etc/passwd', 'image/png'))).toMatchObject({ kind: 'contract' });
    expect(await rejection(client.getArtifact('/api/v1/artifacts/../../secret', 'image/png'))).toMatchObject({ kind: 'contract' });
    expect(await rejection(client.getArtifact('/api/v1/artifacts/missing-artifact', 'image/png'))).toMatchObject({ status: 404 });
    expect(await rejection(client.getArtifact('/api/v1/artifacts/no_change-dnbr_raster', 'image/tiff'))).toMatchObject({ kind: 'contract' });
  });

  it('offline and injected faults surface as ApiError without corrupting state', async () => {
    const { client, controls } = setup();
    controls.setOffline(true);
    expect(await rejection(client.getHealth())).toMatchObject({ kind: 'network', retryable: true });
    controls.setOffline(false);
    controls.failNext('getCredits', { status: 503, code: 'DB_UNAVAILABLE', message: 'db down' });
    expect(await rejection(client.getCredits(PLOT, 'issuer'))).toMatchObject({ status: 503, retryable: true });
    expectSchema('Credits', await client.getCredits(PLOT, 'issuer'));
  });

  it('a stuck SUBMITTED operation never becomes CONFIRMED or FAILED on its own', async () => {
    const { client, controls, advance } = setup();
    controls.setOperationOutcome('ISSUE', 'STUCK_SUBMITTED');
    const accepted = await client.issueBatch(PLOT, 'issuer', { demo_authorization_id: 'SYNTHETIC-AUTH-001' }, { idempotencyKey: 'stuck-key-1' });
    advance(60_000);
    const op = await client.getOperation(accepted.operation_id);
    expectSchema('Operation', op);
    expect(op.transaction_state).toBe('SUBMITTED');
    expect(op.receipt).toBeNull();
    expect((await client.getCredits(PLOT, 'issuer')).items).toEqual([]);
  });

  it('a failed operation reports FAILED with an error and no receipt', async () => {
    const { client, controls, advance } = setup();
    controls.setOperationOutcome('ISSUE', 'FAILED');
    const accepted = await client.issueBatch(PLOT, 'issuer', { demo_authorization_id: 'SYNTHETIC-AUTH-001' }, { idempotencyKey: 'failed-key-1' });
    advance(60_000);
    const op = await client.getOperation(accepted.operation_id);
    expectSchema('Operation', op);
    expect(op.transaction_state).toBe('FAILED');
    expect(op.error?.code).toBeTruthy();
    expect(op.receipt).toBeNull();
  });
});
