import type { ReactNode } from 'react';
import type { ApiError } from '../api/errors';
import { statusHint } from '../api/errors';
import type { StatusMeta, Tone } from '../domain/status';

export function Badge({ tone, children, title }: { tone: Tone; children: ReactNode; title?: string }) {
  return (
    <span className={`badge tone-${tone}`} title={title}>
      {children}
    </span>
  );
}

export function StatusBadge({ meta, testId }: { meta: StatusMeta; testId?: string }) {
  return (
    <span className={`badge tone-${meta.tone}`} title={meta.hint} data-testid={testId} data-tone={meta.tone}>
      {meta.label}
    </span>
  );
}

export function Loading({ label = 'Загрузка…' }: { label?: string }) {
  return (
    <div className="state state-loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {label}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="state state-empty">{children}</div>;
}

export function ErrorNotice({
  error,
  onRetry,
  title,
  compact,
}: {
  error: ApiError;
  onRetry?: (() => void) | undefined;
  title?: string | undefined;
  compact?: boolean | undefined;
}) {
  const offline = error.kind === 'network' || error.kind === 'timeout';
  const hint = statusHint(error.status, error.code);
  return (
    <div className={`state state-error${compact ? ' compact' : ''}`} role="alert" data-testid="error-notice" data-status={error.status ?? error.kind}>
      <strong>
        {title ?? (offline ? 'Backend недоступен' : 'Ошибка API')}
        {error.status !== null ? ` · HTTP ${error.status}` : ''}
        {error.code ? ` · ${error.code}` : ''}
      </strong>
      <span>{error.message}</span>
      {hint && <span className="muted">{hint}</span>}
      {error.requestId && <span className="muted mono">request_id: {error.requestId}</span>}
      {onRetry && (
        <button type="button" className="btn btn-small" onClick={onRetry}>
          Повторить
        </button>
      )}
    </div>
  );
}

export function Field({ label, children, mono }: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <div className="field">
      <dt>{label}</dt>
      <dd className={mono ? 'mono' : undefined}>{children}</dd>
    </div>
  );
}

export function Section({ title, children, actions, id }: { title: string; children: ReactNode; actions?: ReactNode; id?: string }) {
  return (
    <section className="panel" aria-labelledby={id ? `${id}-title` : undefined} id={id}>
      <header className="panel-header">
        <h2 id={id ? `${id}-title` : undefined}>{title}</h2>
        {actions}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function LedgerNote({ ledger }: { ledger: 'fixture' | 'mock' | 'chain' | 'unknown' }) {
  if (ledger === 'chain') return null;
  const text =
    ledger === 'fixture'
      ? 'FIXTURE adapter: балансы, receipts, tx hashes и anchors — синтетическая эмуляция в браузере; блокчейн не вызывался.'
      : ledger === 'mock'
        ? 'Backend CONTRACT_FIXTURE: receipts, tx hashes и anchors получены от mock ledger Backend — не on-chain доказательство.'
        : 'Режим ledger Backend неизвестен (/health недоступен): не считайте receipts on-chain доказательством.';
  return (
    <p className="muted small" data-testid="ledger-note" data-ledger={ledger}>
      <Badge tone="review">{ledger === 'fixture' ? 'FIXTURE' : ledger === 'mock' ? 'MOCK LEDGER' : 'LEDGER ?'}</Badge> {text}
    </p>
  );
}

export function Hash({ value, label }: { value: string | null | undefined; label?: string }) {
  if (!value) return <span className="muted">—</span>;
  return (
    <code className="hash" title={value} aria-label={label ?? value}>
      {value}
    </code>
  );
}
