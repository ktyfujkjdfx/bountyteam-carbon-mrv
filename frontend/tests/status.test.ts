// @vitest-environment node
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  COMPUTATION_META,
  CREDIT_META,
  DATASET_META,
  DECISION_META,
  FIRMS_META,
  HEALTH_MODE_META,
  JOB_META,
  OUTCOME_META,
  PUBLIC_TRANSACTION_STATES,
  QUALITY_META,
  REASON_LABELS,
  TRANSACTION_META,
} from '../src/domain/status';
import { enumOf } from './schema';

const sorted = (values: string[]) => [...values].sort();

describe('status mapping covers exactly the frozen enums', () => {
  it.each([
    ['RS outcome', OUTCOME_META, enumOf('VerificationEvidence', 'outcome')],
    ['evidence quality', QUALITY_META, enumOf('Verification', 'evidence_quality')],
    ['decision', DECISION_META, enumOf('Verification', 'decision')],
    ['reason', REASON_LABELS, enumOf('Verification', 'reason')],
    ['transaction state', TRANSACTION_META, enumOf('Operation', 'transaction_state')],
    ['job state', JOB_META, enumOf('Job', 'state')],
    ['credit status', CREDIT_META, enumOf('CreditBatch', 'credit_status')],
    ['dataset kind', DATASET_META, enumOf('VerificationEvidence', 'dataset_kind')],
    ['computation mode', COMPUTATION_META, enumOf('Verification', 'computation_mode')],
    ['health mode', HEALTH_MODE_META, enumOf('Health', 'mode')],
    ['FIRMS support', FIRMS_META, enumOf('EvidenceFirms', 'support')],
  ])('%s', (_name, meta, contractEnum) => {
    expect(sorted(Object.keys(meta))).toEqual(sorted(contractEnum));
  });

  it('has no public SIGNING state', () => {
    expect(PUBLIC_TRANSACTION_STATES).toEqual(['QUEUED', 'SUBMITTED', 'CONFIRMED', 'FAILED']);
    expect(Object.keys(TRANSACTION_META)).not.toContain('SIGNING');
    expect(Object.keys(JOB_META)).not.toContain('SIGNING');
  });

  it('source code never renders a SIGNING state', () => {
    const files: string[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name);
        if (statSync(path).isDirectory()) walk(path);
        else if (/\.(ts|tsx)$/.test(name) && !path.includes('generated')) files.push(path);
      }
    };
    walk(join(import.meta.dirname, '..', 'src'));
    const offenders = files.filter((file) => readFileSync(file, 'utf8').includes('SIGNING'));
    expect(offenders).toEqual([]);
  });

  it('only a confirmed on-chain restriction or a failure is red; requests and reviews are not', () => {
    expect(CREDIT_META.FROZEN.tone).toBe('blocked');
    expect(DECISION_META.FREEZE_REQUESTED.tone).not.toBe('blocked');
    expect(TRANSACTION_META.SUBMITTED.tone).not.toBe('ok');
    expect(TRANSACTION_META.SUBMITTED.tone).not.toBe('blocked');
    expect(TRANSACTION_META.CONFIRMED.tone).toBe('ok');
    expect(TRANSACTION_META.FAILED.tone).toBe('blocked');
    for (const meta of [QUALITY_META.INSUFFICIENT, QUALITY_META.REVIEW_REQUIRED, OUTCOME_META.INSUFFICIENT_DATA, DECISION_META.REVIEW_REQUIRED]) {
      expect(['blocked', 'alert']).not.toContain(meta.tone);
    }
  });

  it('never calls EQS a probability and labels FROZEN as a temporary prototype restriction', () => {
    expect(DECISION_META.FREEZE_REQUESTED.hint).toMatch(/НЕ FROZEN/);
    expect(CREDIT_META.FROZEN.hint).toMatch(/Временное ограничение прототипа/);
    expect(CREDIT_META.FROZEN.hint).toMatch(/не юридическое аннулирование/i);
  });
});
