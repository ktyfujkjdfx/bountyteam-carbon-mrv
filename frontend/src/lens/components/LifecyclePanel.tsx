import { DEMO_LIFECYCLE_NOTE, LIFECYCLE_STEPS, lifecycleAvailability, type LifecycleStep, type Submission } from '../workspace';

/**
 * A demonstration of the lifecycle around a calculation, recorded locally and labelled as such on
 * every state. No blockchain call is made anywhere in this panel.
 */
export function LifecyclePanel({
  submission,
  canAct,
  onStep,
}: {
  submission: Submission;
  canAct: boolean;
  onStep: (step: LifecycleStep) => void;
}) {
  const done = new Map(submission.lifecycle.map((entry) => [entry.step, entry]));

  return (
    <section className="lens-lifecycle" data-testid="lens-lifecycle" aria-label="Демонстрационный жизненный цикл">
      <div className="state state-warn compact" role="note" data-testid="lens-lifecycle-note">
        <strong>Демонстрационный жизненный цикл</strong>
        <span>{DEMO_LIFECYCLE_NOTE}</span>
      </div>
      <ol className="lens-lifecycle-list">
        {LIFECYCLE_STEPS.map((item) => {
          const entry = done.get(item.step);
          const availability = lifecycleAvailability(submission, item.step);
          const completed =
            entry !== undefined ||
            (item.step === 'CALCULATION' && submission.result !== null) ||
            (item.step === 'VERIFICATION' && submission.status === 'FINALIZED');
          return (
            <li key={item.step} data-testid={`lens-lifecycle-${item.step}`} data-state={completed ? 'done' : availability.allowed ? 'ready' : 'blocked'}>
              <div className="lens-lifecycle-head">
                <span className={`badge tone-${completed ? 'ok' : availability.allowed ? 'info' : 'neutral'}`}>{completed ? 'ВЫПОЛНЕНО' : availability.allowed ? 'ДОСТУПНО' : 'НЕДОСТУПНО'}</span>
                <strong>{item.label}</strong>
              </div>
              <p className="muted small">{item.description}</p>
              {entry && (
                <p className="mono small">
                  {new Date(entry.at).toLocaleString('ru-RU')} · {entry.by}
                </p>
              )}
              {!completed && !availability.allowed && (
                <p className="muted small" data-testid={`lens-lifecycle-reason-${item.step}`}>
                  {availability.reason}
                </p>
              )}
              {!completed && availability.allowed && canAct && (
                <button type="button" className="btn btn-small btn-secondary" onClick={() => onStep(item.step)} data-testid={`lens-lifecycle-act-${item.step}`}>
                  Записать шаг
                </button>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
