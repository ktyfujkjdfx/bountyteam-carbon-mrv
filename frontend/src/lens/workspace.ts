// Submissions of this browser session: what an owner sent, what a verifier finalised, what an investor
// may read. The service has no lifecycle endpoints yet, so this store is local and labelled DEMO on
// every screen that shows it. It never changes a calculated number — it only records who did what.

import type { AnalysisResult, Geometry } from './types';
import type { LensRole } from './auth';

export const WORKSPACE_STORAGE_KEY = 'carbon-lens.workspace';
export const WORKSPACE_SCHEMA = 'carbon-lens-workspace-2';

export type SubmissionStatus = 'SUBMITTED' | 'CALCULATED' | 'FINALIZED' | 'INTEGRITY_FAILED';
export type PassportStatus = 'DRAFT' | 'CALCULATED' | 'FINALIZED' | 'INTEGRITY_FAILED';
export type LifecycleStep = 'CALCULATION' | 'VERIFICATION' | 'DEMO_ISSUE' | 'DEMO_TRANSFER' | 'DEMO_RETIREMENT';

export interface VerifierNote {
  note_id: string;
  created_at: string;
  author: string;
  text: string;
}

export interface LifecycleEntry {
  step: LifecycleStep;
  at: string;
  by: string;
  note: string;
}

export interface Submission {
  submission_id: string;
  created_at: string;
  updated_at: string;
  owner_email: string;
  title: string;
  aoi_id: string | null;
  geometry: Geometry;
  year_start: number;
  year_end: number;
  claimed_units: number | null;
  status: SubmissionStatus;
  analysis_id: string | null;
  result: AnalysisResult | null;
  notes: VerifierNote[];
  finalized_by: string | null;
  finalized_at: string | null;
  lifecycle: LifecycleEntry[];
}

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

export function loadSubmissions(storage: StorageLike | null = safeStorage()): Submission[] {
  try {
    const raw = storage?.getItem(WORKSPACE_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as { schema?: string; submissions?: Submission[] };
    if (parsed.schema !== WORKSPACE_SCHEMA || !Array.isArray(parsed.submissions)) return [];
    return parsed.submissions;
  } catch {
    return [];
  }
}

export function saveSubmissions(submissions: readonly Submission[], storage: StorageLike | null = safeStorage()): void {
  try {
    storage?.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify({ schema: WORKSPACE_SCHEMA, submissions: submissions.slice(0, 12) }));
  } catch {
    /* quota or private mode: the session keeps working without persistence */
  }
}

export function clearSubmissions(storage: StorageLike | null = safeStorage()): void {
  try {
    storage?.removeItem(WORKSPACE_STORAGE_KEY);
  } catch {
    /* nothing to clean up */
  }
}

export function newSubmission(input: {
  owner_email: string;
  title: string;
  aoi_id: string | null;
  geometry: Geometry;
  year_start: number;
  year_end: number;
  claimed_units: number | null;
  now?: Date;
}): Submission {
  const now = (input.now ?? new Date()).toISOString();
  return {
    submission_id: `sub-${Math.random().toString(36).slice(2, 10)}`,
    created_at: now,
    updated_at: now,
    owner_email: input.owner_email,
    title: input.title,
    aoi_id: input.aoi_id,
    geometry: input.geometry,
    year_start: input.year_start,
    year_end: input.year_end,
    claimed_units: input.claimed_units,
    status: 'SUBMITTED',
    analysis_id: null,
    result: null,
    notes: [],
    finalized_by: null,
    finalized_at: null,
    lifecycle: [],
  };
}

export function passportStatusOf(submission: Submission): PassportStatus {
  if (submission.status === 'INTEGRITY_FAILED') return 'INTEGRITY_FAILED';
  if (submission.status === 'FINALIZED') return 'FINALIZED';
  return submission.result ? 'CALCULATED' : 'DRAFT';
}

export const PASSPORT_STATUS_TEXT: Record<PassportStatus, { label: string; tone: string; hint: string }> = {
  DRAFT: { label: 'ЧЕРНОВИК', tone: 'neutral', hint: 'Заявка подана, расчёт ещё не выполнялся.' },
  CALCULATED: { label: 'РАССЧИТАН', tone: 'info', hint: 'Расчёт выполнен; верификатор его ещё не финализировал.' },
  FINALIZED: { label: 'ФИНАЛИЗИРОВАН', tone: 'ok', hint: 'Верификатор подтвердил, что паспорт отражает этот расчёт.' },
  INTEGRITY_FAILED: { label: 'ЦЕЛОСТНОСТЬ НАРУШЕНА', tone: 'blocked', hint: 'Хеш содержания не совпал: файл или расчёт изменились после фиксации.' },
};

export const LIFECYCLE_STEPS: Array<{ step: LifecycleStep; label: string; description: string }> = [
  { step: 'CALCULATION', label: 'Расчёт', description: 'Заявка посчитана по методике кейса.' },
  { step: 'VERIFICATION', label: 'Верификация', description: 'Верификатор финализировал паспорт.' },
  { step: 'DEMO_ISSUE', label: 'Демо-выпуск', description: 'Условная запись о выпуске единиц. Не официальный выпуск.' },
  { step: 'DEMO_TRANSFER', label: 'Демо-передача', description: 'Условная передача единиц другому держателю.' },
  { step: 'DEMO_RETIREMENT', label: 'Демо-погашение', description: 'Условное погашение единиц.' },
];

export const DEMO_LIFECYCLE_NOTE =
  'Демонстрационный жизненный цикл. Не официальный выпуск и не торговая операция: записи существуют только в этой вкладке браузера.';

export interface StepAvailability {
  allowed: boolean;
  reason: string;
}

/**
 * A step of the demo lifecycle is offered only when the previous one happened and the calculation
 * actually produced units. Q = 0 is a valid result and simply has nothing to issue.
 */
export function lifecycleAvailability(submission: Submission, step: LifecycleStep): StepAvailability {
  const done = new Set(submission.lifecycle.map((entry) => entry.step));
  const q = submission.result?.units.q ?? null;
  switch (step) {
    case 'CALCULATION':
      return submission.result
        ? { allowed: false, reason: 'Расчёт уже выполнен.' }
        : { allowed: false, reason: 'Расчёт запускает верификатор.' };
    case 'VERIFICATION':
      return submission.status === 'FINALIZED'
        ? { allowed: false, reason: 'Паспорт уже финализирован.' }
        : { allowed: false, reason: 'Финализацию выполняет верификатор на своём экране.' };
    case 'DEMO_ISSUE':
      if (submission.status !== 'FINALIZED') return { allowed: false, reason: 'Сначала верификатор финализирует паспорт.' };
      if (q === null) return { allowed: false, reason: 'Единицы не рассчитаны: выпускать нечего.' };
      if (q <= 0) return { allowed: false, reason: 'Расчёт дал 0 единиц — выпускать нечего. Это корректный результат, а не ошибка.' };
      return done.has('DEMO_ISSUE') ? { allowed: false, reason: 'Демо-выпуск уже записан.' } : { allowed: true, reason: '' };
    case 'DEMO_TRANSFER':
      if (!done.has('DEMO_ISSUE')) return { allowed: false, reason: 'Сначала демо-выпуск.' };
      return done.has('DEMO_TRANSFER') ? { allowed: false, reason: 'Демо-передача уже записана.' } : { allowed: true, reason: '' };
    case 'DEMO_RETIREMENT':
    default:
      if (!done.has('DEMO_TRANSFER')) return { allowed: false, reason: 'Сначала демо-передача.' };
      return done.has('DEMO_RETIREMENT') ? { allowed: false, reason: 'Демо-погашение уже записано.' } : { allowed: true, reason: '' };
  }
}

export function recordStep(submission: Submission, step: LifecycleStep, by: string, now: Date = new Date()): Submission {
  const description = LIFECYCLE_STEPS.find((item) => item.step === step)?.description ?? '';
  return {
    ...submission,
    updated_at: now.toISOString(),
    lifecycle: [...submission.lifecycle, { step, at: now.toISOString(), by, note: description }],
  };
}

export function visibleTo(submissions: readonly Submission[], role: LensRole, email: string): Submission[] {
  if (role === 'owner') return submissions.filter((item) => item.owner_email === email);
  if (role === 'investor') return submissions.filter((item) => item.status === 'FINALIZED');
  return [...submissions];
}
