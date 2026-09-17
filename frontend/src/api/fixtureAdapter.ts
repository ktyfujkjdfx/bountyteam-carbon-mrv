import httpExamples from '../../../fixtures/http_examples.json';
import demoAuthorizations from '../../../config/demo-authorizations.json';
import type { ArtifactPayload, EventsQuery, MrvApiClient, MutationOptions, RequestOptions } from './client';
import { ApiError } from './errors';
import {
  ARTIFACT_URL,
  JOB_STATUS_URL,
  OPERATION_STATUS_URL,
  POSITIVE_UINT_STRING,
  type Anchor,
  type ApiEvent,
  type CreditBatch,
  type CreditStatus,
  type Decision,
  type DemoActor,
  type Events,
  type Health,
  type HistoryItem,
  type Job,
  type JobAccepted,
  type Operation,
  type OperationAccepted,
  type OperationKind,
  type Plot,
  type ScenarioId,
  type Verification,
  type VerificationEvidence,
} from './types';

// Contract-shaped emulation of Backend over golden SYNTHETIC fixtures. No chain, no RS, no policy computation:
// decisions and hashes are copied from fixtures; only operation gates from docs/common/status-machine.md are emulated.

const pngAssets = import.meta.glob('../../../fixtures/assets/**/*.png', {
  query: '?url',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const geojsonAssets = import.meta.glob('../../../fixtures/assets/**/*.geojson', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const canonicalAssets = import.meta.glob('../../../fixtures/verification_*.canonical.json', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

interface ExampleCase {
  name: string;
  body: unknown;
}

const cases = (httpExamples as { cases: ExampleCase[] }).cases;

function exampleBody<T>(name: string): T {
  const found = cases.find((c) => c.name === name);
  if (!found) throw new Error(`fixtures/http_examples.json has no case "${name}"`);
  return structuredClone(found.body) as T;
}

const SCENARIO_CASE: Record<ScenarioId, { example: string; canonical: string }> = {
  baseline: { example: 'verification_no_change', canonical: 'verification_no_change' },
  post_fire: { example: 'verification_fire', canonical: 'verification_fire' },
  insufficient: { example: 'verification_insufficient', canonical: 'verification_insufficient' },
};

export const FIXTURE_SELLER_ADDRESS = '0x00000000000000000000000000000000000000a1';

export interface FixtureTimings {
  jobQueuedMs: number;
  jobRunningMs: number;
  opQueuedMs: number;
  opSubmittedMs: number;
}

export const DEFAULT_FIXTURE_TIMINGS: FixtureTimings = {
  jobQueuedMs: 700,
  jobRunningMs: 1300,
  opQueuedMs: 800,
  opSubmittedMs: 3000,
};

export interface FixtureOptions {
  timings?: Partial<FixtureTimings>;
  now?: () => number;
}

type MethodName = Exclude<keyof MrvApiClient, 'kind'>;

export interface FixtureFault {
  status: number;
  code: string;
  message: string;
}

export interface FixtureControls {
  failNext(method: MethodName, fault: FixtureFault): void;
  setOffline(offline: boolean): void;
  setOperationOutcome(kind: OperationKind, outcome: 'CONFIRMED' | 'FAILED' | 'STUCK_SUBMITTED'): void;
  callCount(method: MethodName): number;
}

interface StoredVerification {
  body: Verification;
  scenario: ScenarioId;
  observedAt: string;
}

interface StoredJob {
  job: Job;
  createdAt: number;
  scenario: ScenarioId;
  settled: boolean;
}

interface StoredOperation {
  op: Operation;
  createdAt: number;
  submittedLogged: boolean;
  settled: boolean;
  effect: () => void;
  plannedOutcome: 'CONFIRMED' | 'FAILED' | 'STUCK_SUBMITTED';
}

interface BatchState {
  batchId: string;
  totalSupply: bigint;
  unitPriceWei: string;
  balances: Record<DemoActor, bigint>;
  creditStatus: CreditStatus;
  issuedAt: string;
  frozenAt: string | null;
  evidenceHash: string;
  decisionHash: string;
}

const PLOT_ID = 'SYNTHETIC-PLOT-001';

export function createFixtureBackend(options: FixtureOptions = {}): { client: MrvApiClient; controls: FixtureControls } {
  const timings: FixtureTimings = { ...DEFAULT_FIXTURE_TIMINGS, ...options.timings };
  const now = options.now ?? (() => Date.now());

  const plotTemplate = exampleBody<Plot>('plot');
  const authorization = demoAuthorizations.authorizations.find((a) => a.plot_id === PLOT_ID);

  const verifications = new Map<string, StoredVerification>();
  const order: string[] = [];
  let latestId: string | null = null;
  const jobs = new Map<string, StoredJob>();
  const operations = new Map<string, StoredOperation>();
  const events: ApiEvent[] = [];
  const anchors = new Map<string, Anchor[]>();
  const idempotency = new Map<string, { bodyKey: string; response: JobAccepted | OperationAccepted }>();
  const faults = new Map<MethodName, FixtureFault>();
  const calls = new Map<MethodName, number>();
  const plannedOutcome = new Map<OperationKind, 'CONFIRMED' | 'FAILED' | 'STUCK_SUBMITTED'>();
  let offline = false;
  let batch: BatchState | null = null;
  let authorizationUsed = false;
  let counter = 0;

  const nextId = (prefix: string) => {
    counter += 1;
    return `${prefix}-0000-4000-8000-${counter.toString(16).padStart(12, '0')}`;
  };
  const txHash = () => {
    counter += 1;
    return `0x${counter.toString(16).padStart(64, '0')}`;
  };
  const iso = (ms: number) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, 'Z');

  function importVerification(scenario: ScenarioId, processedAtMs: number): string {
    const body = exampleBody<Verification>(SCENARIO_CASE[scenario].example);
    if (!verifications.has(body.verification_id)) {
      body.processed_at = iso(processedAtMs);
      verifications.set(body.verification_id, {
        body,
        scenario,
        observedAt: body.decision_record.effective_observed_at,
      });
      order.push(body.verification_id);
      latestId = body.verification_id;
      pushEvent(processedAtMs, {
        kind: 'VERIFICATION',
        verification_id: body.verification_id,
        message: `[fixture] Evidence импортирован: outcome ${body.evidence.outcome}, quality ${body.evidence_quality}`,
      });
      pushEvent(processedAtMs, {
        kind: 'DECISION',
        verification_id: body.verification_id,
        message: `[fixture] Решение Backend: ${body.decision} / ${body.reason}`,
      });
      if (body.decision === 'FREEZE_REQUESTED') requestFreeze(body, Math.max(processedAtMs, now()));
    }
    return body.verification_id;
  }

  function latest(): StoredVerification | null {
    return latestId ? (verifications.get(latestId) ?? null) : null;
  }

  function pendingFreeze(): StoredOperation | null {
    for (const stored of operations.values()) {
      if (stored.op.kind === 'FREEZE' && !stored.settled) return stored;
    }
    return null;
  }

  function requestFreeze(verification: Verification, atMs: number): void {
    const current = batch;
    if (!current || current.creditStatus !== 'ACTIVE' || pendingFreeze()) return;
    createOperation('FREEZE', current.batchId, atMs, () => {
      current.creditStatus = 'FROZEN';
      current.frozenAt = iso(now());
      addAnchor(verification.verification_id, 'Frozen', current.batchId, verification.evidence_hash, verification.decision_hash);
    });
  }

  function addAnchor(verificationId: string, eventName: Anchor['event_name'], batchId: string, evidenceHash: string, decisionHash: string | null) {
    const op = [...operations.values()].reverse().find((o) => o.op.batch_id === batchId && o.op.tx_hash);
    const list = anchors.get(verificationId) ?? [];
    list.push({
      event_name: eventName,
      batch_id: batchId,
      tx_hash: op?.op.tx_hash ?? txHash(),
      evidence_hash: evidenceHash,
      decision_hash: decisionHash,
      confirmed: true,
    });
    anchors.set(verificationId, list);
  }

  function pushEvent(atMs: number, partial: Partial<ApiEvent> & Pick<ApiEvent, 'kind' | 'message'>): void {
    events.push({
      event_id: nextId('60000000'),
      occurred_at: iso(atMs),
      plot_id: PLOT_ID,
      verification_id: null,
      operation_id: null,
      tx_hash: null,
      batch_id: null,
      ...partial,
    });
  }

  function createOperation(kind: OperationKind, batchId: string | null, atMs: number, effect: () => void): Operation {
    const op: Operation = {
      operation_id: nextId('40000000'),
      kind,
      transaction_state: 'QUEUED',
      tx_hash: null,
      batch_id: batchId,
      error: null,
      receipt: null,
    };
    operations.set(op.operation_id, {
      op,
      createdAt: atMs,
      submittedLogged: false,
      settled: false,
      effect,
      plannedOutcome: plannedOutcome.get(kind) ?? 'CONFIRMED',
    });
    return op;
  }

  const EVENT_NAME: Record<OperationKind, string> = {
    ISSUE: 'Issued',
    BUY: 'Purchased',
    TRANSFER: 'Transferred',
    FREEZE: 'Frozen',
  };

  function settle(): void {
    const t = now();
    for (const stored of jobs.values()) {
      if (stored.settled) continue;
      const elapsed = t - stored.createdAt;
      if (elapsed >= timings.jobQueuedMs + timings.jobRunningMs) {
        const verificationId = importVerification(stored.scenario, stored.createdAt + timings.jobQueuedMs + timings.jobRunningMs);
        stored.job = { job_id: stored.job.job_id, state: 'SUCCEEDED', verification_id: verificationId, error: null };
        stored.settled = true;
      } else if (elapsed >= timings.jobQueuedMs) {
        stored.job = { ...stored.job, state: 'RUNNING' };
      }
    }
    for (const stored of operations.values()) {
      if (stored.settled) continue;
      const elapsed = t - stored.createdAt;
      const submitAt = stored.createdAt + timings.opQueuedMs;
      const finishAt = submitAt + timings.opSubmittedMs;
      if (elapsed >= timings.opQueuedMs && !stored.submittedLogged) {
        stored.op = { ...stored.op, transaction_state: 'SUBMITTED', tx_hash: txHash() };
        stored.submittedLogged = true;
        pushEvent(submitAt, {
          kind: 'TX_SUBMITTED',
          operation_id: stored.op.operation_id,
          tx_hash: stored.op.tx_hash,
          batch_id: stored.op.batch_id,
          message: `[fixture] ${stored.op.kind}: транзакция отправлена (эмуляция, без сети)`,
        });
      }
      if (t >= finishAt && stored.plannedOutcome !== 'STUCK_SUBMITTED') {
        const hash = stored.op.tx_hash ?? txHash();
        if (stored.plannedOutcome === 'FAILED') {
          stored.op = {
            ...stored.op,
            transaction_state: 'FAILED',
            tx_hash: hash,
            error: { code: 'TX_REVERTED', message: '[fixture] receipt status 0', details: {} },
            receipt: null,
          };
          pushEvent(finishAt, {
            kind: 'TX_FAILED',
            operation_id: stored.op.operation_id,
            tx_hash: hash,
            batch_id: stored.op.batch_id,
            message: `[fixture] ${stored.op.kind}: транзакция отклонена`,
          });
        } else {
          stored.effect();
          const batchId = stored.op.batch_id ?? batch?.batchId ?? '0';
          stored.op = {
            ...stored.op,
            transaction_state: 'CONFIRMED',
            tx_hash: hash,
            batch_id: batchId,
            error: null,
            receipt: {
              transaction_hash: hash,
              block_number: String(100 + counter),
              status: 1,
              event_names: [EVENT_NAME[stored.op.kind]],
              state_readback_ok: true,
            },
          };
          pushEvent(finishAt, {
            kind: 'TX_CONFIRMED',
            operation_id: stored.op.operation_id,
            tx_hash: hash,
            batch_id: batchId,
            message: `[fixture] ${stored.op.kind}: receipt + событие ${EVENT_NAME[stored.op.kind]} + readback (эмуляция)`,
          });
        }
        stored.settled = true;
      }
    }
  }

  function fail(status: number, code: string, message: string): never {
    throw new ApiError({ kind: 'http', status, code, message, requestId: nextId('70000000'), details: {} });
  }

  async function guard(method: MethodName, signal?: AbortSignal): Promise<void> {
    calls.set(method, (calls.get(method) ?? 0) + 1);
    await Promise.resolve();
    if (signal?.aborted) throw new ApiError({ kind: 'aborted', message: 'Запрос отменён' });
    if (offline) throw new ApiError({ kind: 'network', message: 'Backend недоступен: fixture adapter в режиме offline' });
    const fault = faults.get(method);
    if (fault) {
      faults.delete(method);
      fail(fault.status, fault.code, fault.message);
    }
    settle();
  }

  function assertPlot(plotId: string): void {
    if (plotId !== PLOT_ID) fail(404, 'PLOT_NOT_FOUND', `Участок ${plotId} не найден`);
  }

  function gates(actor: DemoActor): { canIssue: boolean; canBuy: boolean; canTransfer: boolean; reason: string | null } {
    const decision: Decision | null = latest()?.body.decision ?? null;
    const freezePending = pendingFreeze() !== null;
    const active = batch?.creditStatus === 'ACTIVE';
    const allowedByDecision = decision === 'NO_RESTRICTION';
    const canIssue =
      actor === 'issuer' && allowedByDecision && batch === null && !freezePending && !authorizationUsed && authorization !== undefined;
    const trading = allowedByDecision && active && !freezePending;
    const canBuy = trading && actor !== 'issuer' && (batch?.balances.issuer ?? 0n) > 0n;
    const canTransfer = trading && (batch?.balances[actor] ?? 0n) > 0n;

    let reason: string | null = null;
    if (batch?.creditStatus === 'FROZEN') reason = 'Серия FROZEN: передача и покупка запрещены контрактом.';
    else if (freezePending) reason = 'Запрошена приостановка (freeze pending): Backend закрыл новые операции.';
    else if (decision !== null && decision !== 'NO_RESTRICTION') reason = `Последнее решение Backend: ${decision}. Финансовые действия закрыты.`;
    else if (decision === null) reason = 'Нет обработанного наблюдения.';
    return { canIssue, canBuy, canTransfer, reason };
  }

  function idempotent<T extends JobAccepted | OperationAccepted>(
    actor: DemoActor,
    kind: string,
    key: string,
    body: unknown,
    create: () => T,
  ): T {
    if (key.length < 8 || key.length > 128) fail(422, 'INVALID_IDEMPOTENCY_KEY', 'Idempotency-Key должен быть 8–128 символов');
    const scope = `${actor}|${kind}|${key}`;
    const bodyKey = JSON.stringify(body);
    const existing = idempotency.get(scope);
    if (existing) {
      if (existing.bodyKey !== bodyKey) fail(409, 'IDEMPOTENCY_CONFLICT', 'Тот же Idempotency-Key с другим телом запроса');
      return structuredClone(existing.response) as T;
    }
    const response = create();
    idempotency.set(scope, { bodyKey, response });
    return structuredClone(response);
  }

  function operationAccepted(op: Operation): OperationAccepted {
    return { operation_id: op.operation_id, transaction_state: 'QUEUED', status_url: `/api/v1/operations/${op.operation_id}` };
  }

  function batchFor(batchId: string): BatchState {
    if (!POSITIVE_UINT_STRING.test(batchId) && batchId !== '0') fail(422, 'INVALID_BATCH_ID', 'batch_id должен быть десятичной строкой');
    if (!batch || batch.batchId !== batchId) fail(404, 'BATCH_NOT_FOUND', `Серия ${batchId} не найдена`);
    return batch;
  }

  function requireAmount(amount: unknown): bigint {
    if (typeof amount !== 'string' || !POSITIVE_UINT_STRING.test(amount)) {
      fail(422, 'INVALID_AMOUNT', 'amount должен быть положительной десятичной строкой');
    }
    return BigInt(amount);
  }

  function idFrom(value: string, pattern: RegExp): string {
    return pattern.test(value) ? (value.split('/').pop() ?? value) : value;
  }

  importVerification('baseline', Date.parse('2026-09-16T12:00:00Z'));

  const client: MrvApiClient = {
    kind: 'fixture',

    async getHealth(opts?: RequestOptions): Promise<Health> {
      await guard('getHealth', opts?.signal);
      return exampleBody<Health>('health');
    },

    async listPlots(opts) {
      await guard('listPlots', opts?.signal);
      const current = latest();
      return {
        items: [
          {
            plot_id: plotTemplate.plot_id,
            name: plotTemplate.name,
            latest_verification_id: current?.body.verification_id ?? null,
            evidence_quality: current?.body.evidence_quality ?? null,
            latest_decision: current?.body.decision ?? null,
          },
        ],
      };
    },

    async getPlot(plotId, actor, opts) {
      await guard('getPlot', opts?.signal);
      assertPlot(plotId);
      const current = latest();
      const g = gates(actor);
      return {
        ...structuredClone(plotTemplate),
        latest_verification_id: current?.body.verification_id ?? null,
        evidence_quality: current?.body.evidence_quality ?? null,
        latest_decision: current?.body.decision ?? null,
        can_issue: g.canIssue,
        can_buy: g.canBuy,
        can_transfer_backend: g.canTransfer,
        action_block_reason: g.canIssue || g.canBuy || g.canTransfer ? null : g.reason,
      };
    },

    async startVerification(plotId, actor, body, opts: MutationOptions) {
      await guard('startVerification', opts.signal);
      assertPlot(plotId);
      if (actor !== 'issuer') fail(403, 'FORBIDDEN_ACTOR', 'Запуск проверки разрешён только demo-актору issuer');
      if (!body || !(body.scenario_id in SCENARIO_CASE)) fail(422, 'INVALID_EVIDENCE', 'Неверная схема');
      return idempotent(actor, 'verify', opts.idempotencyKey, body, () => {
        const job: Job = { job_id: nextId('30000000'), state: 'QUEUED', verification_id: null, error: null };
        jobs.set(job.job_id, { job, createdAt: now(), scenario: body.scenario_id, settled: false });
        return { job_id: job.job_id, state: 'QUEUED', status_url: `/api/v1/jobs/${job.job_id}` };
      });
    },

    async getJob(statusUrlOrId, opts) {
      await guard('getJob', opts?.signal);
      const stored = jobs.get(idFrom(statusUrlOrId, JOB_STATUS_URL));
      if (!stored) fail(404, 'JOB_NOT_FOUND', 'Задание не найдено');
      return structuredClone(stored.job);
    },

    async getVerification(id, opts) {
      await guard('getVerification', opts?.signal);
      const stored = verifications.get(id);
      if (!stored) fail(404, 'VERIFICATION_NOT_FOUND', 'Проверка не найдена');
      return { ...structuredClone(stored.body), is_latest: id === latestId };
    },

    async getProof(id, opts) {
      await guard('getProof', opts?.signal);
      const stored = verifications.get(id);
      if (!stored) fail(404, 'VERIFICATION_NOT_FOUND', 'Проверка не найдена');
      return {
        evidence_hash: stored.body.evidence_hash,
        recomputed_hash: stored.body.evidence_hash,
        decision_hash: stored.body.decision_hash,
        canonical_url: `/api/v1/verifications/${id}/canonical`,
        anchors: structuredClone(anchors.get(id) ?? []),
        integrity_ok: true,
      };
    },

    async getCanonicalEvidence(id, opts) {
      await guard('getCanonicalEvidence', opts?.signal);
      const stored = verifications.get(id);
      if (!stored) fail(404, 'VERIFICATION_NOT_FOUND', 'Проверка не найдена');
      const name = SCENARIO_CASE[stored.scenario].canonical;
      const raw = canonicalAssets[`../../../fixtures/${name}.canonical.json`];
      if (raw === undefined) fail(404, 'CANONICAL_NOT_FOUND', 'Канонические байты не найдены');
      return JSON.parse(raw) as VerificationEvidence;
    },

    async getHistory(plotId, opts) {
      await guard('getHistory', opts?.signal);
      assertPlot(plotId);
      const items: HistoryItem[] = order
        .map((id) => verifications.get(id))
        .filter((v): v is StoredVerification => v !== undefined)
        .map((v) => ({
          verification_id: v.body.verification_id,
          observed_at: v.observedAt,
          processed_at: v.body.processed_at,
          outcome: v.body.evidence.outcome,
          evidence_quality: v.body.evidence_quality,
          decision: v.body.decision,
          is_latest: v.body.verification_id === latestId,
        }));
      return { items };
    },

    async getCredits(plotId, actor, opts) {
      await guard('getCredits', opts?.signal);
      assertPlot(plotId);
      if (!batch) return { items: [] };
      const g = gates(actor);
      const item: CreditBatch = {
        batch_id: batch.batchId,
        plot_id: PLOT_ID,
        seller: FIXTURE_SELLER_ADDRESS,
        actor,
        total_supply: batch.totalSupply.toString(),
        seller_balance: batch.balances.issuer.toString(),
        actor_balance: batch.balances[actor].toString(),
        unit_price_wei: batch.unitPriceWei,
        credit_status: batch.creditStatus,
        evidence_hash: batch.evidenceHash,
        decision_hash: batch.decisionHash,
        issued_at: batch.issuedAt,
        frozen_at: batch.frozenAt,
        last_observed_at: latest()?.observedAt ?? batch.issuedAt,
        chain_state_checked_at: iso(now()),
        can_buy: g.canBuy,
        can_transfer_backend: g.canTransfer,
      };
      return { items: [item] };
    },

    async issueBatch(plotId, actor, body, opts) {
      await guard('issueBatch', opts.signal);
      assertPlot(plotId);
      if (actor !== 'issuer') fail(403, 'FORBIDDEN_ACTOR', 'Выпуск разрешён только demo-актору issuer');
      return idempotent(actor, 'issue', opts.idempotencyKey, body, () => {
        if (!authorization || body.demo_authorization_id !== authorization.demo_authorization_id) {
          fail(404, 'AUTHORIZATION_NOT_FOUND', 'Demo authorization не найдена');
        }
        if (!gates(actor).canIssue) fail(409, 'ISSUE_NOT_ALLOWED', gates(actor).reason ?? 'Выпуск запрещён текущим состоянием');
        const baseline = latest();
        if (!baseline) fail(409, 'ISSUE_NOT_ALLOWED', 'Нет baseline evidence');
        authorizationUsed = true;
        const op = createOperation('ISSUE', null, now(), () => {
          batch = {
            batchId: '1',
            totalSupply: BigInt(authorization.amount),
            unitPriceWei: authorization.unit_price_wei,
            balances: { issuer: BigInt(authorization.amount), buyer: 0n, recipient: 0n },
            creditStatus: 'ACTIVE',
            issuedAt: iso(now()),
            frozenAt: null,
            evidenceHash: baseline.body.evidence_hash,
            decisionHash: baseline.body.decision_hash,
          };
          addAnchor(baseline.body.verification_id, 'Issued', '1', baseline.body.evidence_hash, null);
        });
        return operationAccepted(op);
      });
    },

    async buyCredits(batchId, actor, body, opts) {
      await guard('buyCredits', opts.signal);
      const target = batchFor(batchId);
      if (actor === 'issuer') fail(403, 'FORBIDDEN_ACTOR', 'Покупка разрешена demo-акторам buyer/recipient');
      const amount = requireAmount(body?.amount);
      return idempotent(actor, 'buy', opts.idempotencyKey, body, () => {
        if (target.creditStatus !== 'ACTIVE') fail(409, 'BATCH_NOT_ACTIVE', `Серия ${target.creditStatus}: покупка запрещена`);
        if (!gates(actor).canBuy) fail(409, 'BUY_NOT_ALLOWED', gates(actor).reason ?? 'Покупка запрещена текущим состоянием');
        if (amount > target.balances.issuer) fail(409, 'INSUFFICIENT_BALANCE', 'У продавца недостаточно единиц');
        const op = createOperation('BUY', target.batchId, now(), () => {
          target.balances.issuer -= amount;
          target.balances[actor] += amount;
        });
        return operationAccepted(op);
      });
    },

    async transferCredits(batchId, actor, body, opts) {
      await guard('transferCredits', opts.signal);
      const target = batchFor(batchId);
      const amount = requireAmount(body?.amount);
      if (!body || !['issuer', 'buyer', 'recipient'].includes(body.to_actor)) fail(422, 'INVALID_RECIPIENT', 'Неверный to_actor');
      if (body.to_actor === actor) fail(422, 'INVALID_RECIPIENT', 'Нельзя передать единицы самому себе');
      return idempotent(actor, 'transfer', opts.idempotencyKey, body, () => {
        if (target.creditStatus !== 'ACTIVE') {
          fail(409, 'BATCH_NOT_ACTIVE', `Серия ${target.creditStatus}: передача отклонена (контракт BatchNotActive)`);
        }
        if (pendingFreeze()) fail(409, 'FREEZE_PENDING', 'Запрошена приостановка: Backend закрыл новые операции');
        if (amount > target.balances[actor]) fail(409, 'INSUFFICIENT_BALANCE', 'Недостаточно единиц у отправителя');
        if (!gates(actor).canTransfer) fail(409, 'TRANSFER_NOT_ALLOWED', gates(actor).reason ?? 'Передача запрещена');
        const op = createOperation('TRANSFER', target.batchId, now(), () => {
          target.balances[actor] -= amount;
          target.balances[body.to_actor] += amount;
        });
        return operationAccepted(op);
      });
    },

    async getOperation(statusUrlOrId, opts) {
      await guard('getOperation', opts?.signal);
      const stored = operations.get(idFrom(statusUrlOrId, OPERATION_STATUS_URL));
      if (!stored) fail(404, 'OPERATION_NOT_FOUND', 'Операция не найдена');
      return structuredClone(stored.op);
    },

    async listEvents(query: EventsQuery, opts): Promise<Events> {
      await guard('listEvents', opts?.signal);
      assertPlot(query.plotId);
      const limit = query.limit ?? 50;
      if (!Number.isInteger(limit) || limit < 1 || limit > 100) fail(422, 'INVALID_LIMIT', 'limit должен быть 1–100');
      const sorted = [...events].sort((a, b) => b.occurred_at.localeCompare(a.occurred_at));
      const start = query.cursor ? Number.parseInt(query.cursor, 10) : 0;
      if (!Number.isInteger(start) || start < 0) fail(422, 'INVALID_CURSOR', 'Неверный cursor');
      const items = structuredClone(sorted.slice(start, start + limit));
      const next = start + limit < sorted.length ? String(start + limit) : null;
      return { items, next_cursor: next };
    },

    async getArtifact(artifactUrl, mediaType, opts): Promise<ArtifactPayload> {
      await guard('getArtifact', opts?.signal);
      if (!ARTIFACT_URL.test(artifactUrl)) {
        throw new ApiError({ kind: 'contract', message: `Артефакт разрешён только по artifacts[].url Backend: ${artifactUrl}` });
      }
      const artifactId = artifactUrl.slice('/api/v1/artifacts/'.length);
      let relativePath: string | undefined;
      for (const stored of verifications.values()) {
        relativePath ??= stored.body.evidence.artifacts.find((a) => a.artifact_id === artifactId)?.relative_path;
      }
      if (!relativePath) fail(404, 'ARTIFACT_NOT_FOUND', `Артефакт ${artifactId} не найден`);
      const key = `../../../fixtures/${relativePath}`;
      if (mediaType === 'application/geo+json') {
        const raw = geojsonAssets[key];
        if (raw === undefined) fail(404, 'ARTIFACT_NOT_FOUND', `Файл артефакта ${artifactId} отсутствует`);
        return { kind: 'geojson', data: JSON.parse(raw) as GeoJSON.GeoJsonObject, mediaType, release: () => undefined };
      }
      if (mediaType === 'image/png' || mediaType === 'image/webp') {
        const src = pngAssets[key];
        if (src === undefined) fail(404, 'ARTIFACT_NOT_FOUND', `Файл артефакта ${artifactId} отсутствует`);
        return { kind: 'image', src, mediaType, release: () => undefined };
      }
      throw new ApiError({ kind: 'contract', message: `Браузер не загружает ${mediaType} (GeoTIFF отображается только через превью)` });
    },
  };

  const controls: FixtureControls = {
    failNext: (method, fault) => {
      faults.set(method, fault);
    },
    setOffline: (value) => {
      offline = value;
    },
    setOperationOutcome: (kind, outcome) => {
      plannedOutcome.set(kind, outcome);
    },
    callCount: (method) => calls.get(method) ?? 0,
  };

  return { client, controls };
}
