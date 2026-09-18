import { DEMO_STEPS, type DemoStep } from '../demo';

interface Props {
  activeStepId: string | null;
  onApply: (step: DemoStep) => void;
  busy: boolean;
}

/**
 * The walkthrough presses the same controls an operator would press. It selects requests and the labelled
 * result set; it never injects numbers of its own, so what the audience sees is what the adapter returned.
 */
export function DemoPanel({ activeStepId, onApply, busy }: Props) {
  const index = DEMO_STEPS.findIndex((step) => step.id === activeStepId);
  const next = DEMO_STEPS[index + 1] ?? DEMO_STEPS[0];

  return (
    <div className="lens-demo" data-testid="lens-demo">
      <p className="muted small">
        Сценарий показа: {DEMO_STEPS.length} шагов. Каждый шаг задаёт территорию, период и набор значений, затем запускает расчёт. Числа на
        экране остаются теми, что вернул адаптер.
      </p>
      <ol className="lens-demo-list">
        {DEMO_STEPS.map((step, position) => (
          <li key={step.id}>
            <button
              type="button"
              className={`lens-demo-item${step.id === activeStepId ? ' selected' : ''}`}
              onClick={() => onApply(step)}
              disabled={busy}
              aria-current={step.id === activeStepId ? 'step' : undefined}
              data-testid={`lens-demo-step-${step.id}`}
            >
              <span className="lens-demo-head">
                <span className="mono small">{position + 1}</span>
                <span>{step.title}</span>
                {step.acceptance && <span className="badge tone-neutral">{step.acceptance}</span>}
              </span>
              <span className="muted small">{step.narration}</span>
            </button>
          </li>
        ))}
      </ol>
      <button type="button" className="btn btn-small" onClick={() => next && onApply(next)} disabled={busy || !next} data-testid="lens-demo-next">
        {index === -1 ? 'Начать показ' : `Следующий шаг: ${next?.title ?? ''}`}
      </button>
    </div>
  );
}
