import { useEffect } from 'react';
import type { MrvApiClient } from '../api/client';
import type { ApiError } from '../api/errors';
import { isTerminalJob } from '../api/polling';
import type { DemoActor, History, Job, ScenarioId, VerifyRequest } from '../api/types';
import { DECISION_META, JOB_META, OUTCOME_META, QUALITY_META, metaFor } from '../domain/status';
import { formatUtc } from '../domain/format';
import { useTrackedAction } from '../hooks/useTrackedAction';
import { Empty, ErrorNotice, Loading, StatusBadge } from './common';

const SCENARIOS: ReadonlyArray<{ id: ScenarioId; label: string; note: string }> = [
  { id: 'baseline', label: 'Historical replay · T0 → T1', note: 'Базовое сравнение до изменения' },
  { id: 'post_fire', label: 'Historical replay · T1 → T2', note: 'Наблюдение после события' },
  { id: 'insufficient', label: 'Quality check', note: 'Явно маркированный тест качества' },
];

interface Props {
  client: MrvApiClient;
  scope: string;
  plotId: string;
  actor: DemoActor;
  history: History | null;
  historyError: ApiError | null;
  historyLoading: boolean;
  onReloadHistory: () => void;
  selectedId: string | null;
  onSelect: (verificationId: string) => void;
  onJobSucceeded: (verificationId: string) => void;
  onChanged: () => void;
}

export function ObservationsPanel(props: Props) {
  const { client, scope, plotId, actor, history, historyError, historyLoading, onReloadHistory, selectedId, onSelect, onJobSucceeded, onChanged } =
    props;

  const verify = useTrackedAction<VerifyRequest, Job>({
    intentKey: `${scope}|plot:${plotId}|verify`,
    kind: 'verify',
    submit: async (body, key, signal) => ({
      statusUrl: (await client.startVerification(plotId, actor, body, { idempotencyKey: key, signal })).status_url,
    }),
    fetchStatus: (url, signal) => client.getJob(url, { signal }),
    isTerminal: isTerminalJob,
    onSettled: onChanged,
  });

  const job = verify.status;
  const succeededId = job?.state === 'SUCCEEDED' ? job.verification_id : null;
  useEffect(() => {
    if (succeededId) onJobSucceeded(succeededId);
  }, [succeededId, onJobSucceeded]);

  const items = [...(history?.items ?? [])].sort((a, b) => b.processed_at.localeCompare(a.processed_at));

  return (
    <div className="observations" data-testid="observations-panel">
      <div className="scenario-buttons" role="group" aria-label="Запуск проверки">
        {SCENARIOS.map((s) => (
          <button
            key={s.id}
            type="button"
            className="btn btn-secondary"
            disabled={verify.busy}
            onClick={() => void verify.run({ scenario_id: s.id })}
            title={s.note}
            data-testid={`verify-${s.id}`}
          >
            <span>{s.label}</span>
            <span className="mono">{s.id}</span>
          </button>
        ))}
      </div>
      <p className="muted small" style={{ marginTop: 8 }}>
        Ключи серверного manifest сценариев — исторический replay, не симуляция события. Запуск разрешён только demo-актору issuer
        {actor !== 'issuer' ? ` — сейчас выбран ${actor}, Backend вернёт 403` : ''}.
      </p>

      {verify.phase !== 'idle' && (
        <div className="job-status" aria-live="polite" data-testid="job-status">
          {verify.phase === 'submitting' && <Loading label="Отправка задания…" />}
          {job && (
            <div>
              <StatusBadge meta={metaFor(JOB_META, job.state)} testId="job-state" /> <span className="mono small">{job.job_id}</span>
              {job.state !== 'SUCCEEDED' && job.state !== 'FAILED' && <span className="muted small"> — 202 принят, это ещё не результат</span>}
              {job.error && (
                <div className="warn small">
                  {job.error.code}: {job.error.message}
                </div>
              )}
            </div>
          )}
          {verify.phase === 'timeout' && (
            <div className="state state-warn">
              Задание ещё выполняется, опрос приостановлен.{' '}
              <button type="button" className="btn btn-small" onClick={verify.resume}>
                Продолжить опрос
              </button>
            </div>
          )}
          {verify.error && <ErrorNotice error={verify.error} compact onRetry={verify.statusUrl ? verify.resume : undefined} />}
        </div>
      )}

      <h3>История проверок</h3>
      {historyLoading && !history && <Loading />}
      {historyError && <ErrorNotice error={historyError} onRetry={onReloadHistory} compact />}
      {history && items.length === 0 && (
        <Empty>
          <strong>Наблюдений ещё нет</strong>
          <span>История пополняется после обработки evidence Backend.</span>
        </Empty>
      )}
      {items.length > 0 && (
        <ol className="history" data-testid="history">
          {items.map((item) => (
            <li key={item.verification_id} className={item.verification_id === selectedId ? 'selected' : undefined}>
              <button type="button" className="history-item" onClick={() => onSelect(item.verification_id)} aria-pressed={item.verification_id === selectedId}>
                <span className="history-date">
                  <span>{formatUtc(item.observed_at)}</span>
                  {item.is_latest && <span className="muted">LATEST</span>}
                </span>
                <span className="small muted">обработано {formatUtc(item.processed_at)}</span>
                <span className="badge-row">
                  <StatusBadge meta={metaFor(OUTCOME_META, item.outcome)} />
                  <StatusBadge meta={metaFor(QUALITY_META, item.evidence_quality)} />
                  <StatusBadge meta={metaFor(DECISION_META, item.decision)} />
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
