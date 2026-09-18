import { Empty } from '../../components/common';
import { relateRun, type LensRun } from '../session';

function period(run: LensRun): string {
  return `${run.request.year_start}–${run.request.year_end}`;
}

/**
 * Runs made in this session, newest first. A run of the same contour over another period is marked as a
 * new observation: it never means that earlier units were cancelled or downgraded.
 */
export function HistoryPanel({
  runs,
  activeRunId,
  onOpen,
  onClear,
}: {
  runs: readonly LensRun[];
  activeRunId: string | null;
  onOpen: (runId: string) => void;
  onClear: () => void;
}) {
  if (runs.length === 0) {
    return (
      <Empty>
        <strong>История пуста</strong>
        <span>Расчёты этой сессии появятся здесь и сохранятся при перезагрузке страницы.</span>
      </Empty>
    );
  }

  return (
    <div className="lens-history" data-testid="lens-history">
      <ul className="lens-history-list">
        {runs.map((run, index) => {
          const relation = relateRun(runs.slice(index + 1), run);
          return (
            <li key={run.run_id}>
              <button
                type="button"
                className={`lens-history-item${run.run_id === activeRunId ? ' selected' : ''}`}
                onClick={() => onOpen(run.run_id)}
                aria-pressed={run.run_id === activeRunId}
                data-testid={`lens-history-item-${run.run_id}`}
              >
                <span className="lens-history-head">
                  <span>{run.request.aoi_id ?? run.request.parent_aoi_id ?? 'контур пользователя'}</span>
                  <span className="mono small">{period(run)}</span>
                </span>
                <span className="lens-history-meta">
                  <span className={`badge tone-${relation.kind === 'NEW_OBSERVATION' ? 'review' : 'neutral'}`} data-testid={`lens-history-relation-${run.run_id}`}>
                    {relation.label}
                  </span>
                  <span className="mono small">
                    Q: {run.result.units.q === null ? 'недоступно' : run.result.units.q.toLocaleString('ru-RU')}
                  </span>
                  <span className="mono small">{run.mode === 'http' ? 'сервис' : 'помеченный набор'}</span>
                </span>
                <span className="muted small">{relation.note}</span>
              </button>
            </li>
          );
        })}
      </ul>
      <button type="button" className="btn btn-small btn-secondary" onClick={onClear} data-testid="lens-history-clear">
        Очистить историю сессии
      </button>
    </div>
  );
}
