import { NotAvailable } from '../../components/common';
import type { LensResult } from '../types';

function tco2e(value: number | null, digits = 3): string {
  return value === null ? '—' : value.toLocaleString('ru-RU', { maximumFractionDigits: digits });
}

function signNote(value: number | null): string {
  if (value === null) return 'нет данных';
  if (value > 0) return 'потеря учитываемого пула';
  if (value < 0) return 'накопление';
  return 'изменение не зафиксировано';
}

export function WaterfallPanel({ result }: { result: LensResult }) {
  const { stock, baseline, units, uncertainty } = result;
  const steps: Array<{ id: string; label: string; value: number | null; formula: string; note: string }> = [
    {
      id: 'r',
      label: 'R — результат относительно базовой линии',
      value: units.r_tco2e,
      formula: 'R = Ebase − Eproj − LK',
      note: `LK = ${tco2e(units.leakage_tco2e, 0)} т CO₂-экв. по условию кейса`,
    },
    {
      id: 'unc',
      label: 'Вычет за неопределённость',
      value: units.unc_fraction === null || units.r_tco2e === null ? null : -(units.r_tco2e * units.unc_fraction),
      formula: 'UNC = max(0.10, H / R)',
      note: units.h_over_r === null ? 'H/R не вычисляется при R ≤ 0' : `H/R = ${units.h_over_r.toLocaleString('ru-RU', { maximumFractionDigits: 4 })}`,
    },
    {
      id: 'radj',
      label: 'Radj — после вычета',
      value: units.r_adj_tco2e,
      formula: 'Radj = R × (1 − UNC)',
      note: 'Промежуточные значения не округляются до целых тонн',
    },
    {
      id: 'buffer',
      label: 'Резерв',
      value: units.buffer_tco2e === null ? null : -units.buffer_tco2e,
      formula: 'B = Radj × 0.15',
      note: 'Фиксированный резерв сценария кейса',
    },
    {
      id: 'rounding',
      label: 'Округление вниз',
      value: units.rounding_remainder_tco2e === null ? null : -units.rounding_remainder_tco2e,
      formula: 'Q = floor(Radj − B)',
      note: 'Дробный остаток в Q не включается',
    },
  ];

  return (
    <div className="lens-waterfall" data-testid="lens-waterfall">
      <h3>Сравнение с базовой линией</h3>
      <dl className="fields">
        <div className="field">
          <dt>Eproj · результат периода</dt>
          <dd>
            {stock.e_tco2e === null ? <NotAvailable reason="значение не рассчитано" /> : `${tco2e(stock.e_tco2e)} т CO₂-экв.`}
            <div className="muted small">{signNote(stock.e_tco2e)}</div>
          </dd>
        </div>
        <div className="field">
          <dt>Ebase · базовая линия</dt>
          <dd>
            {baseline.e_base_tco2e === null ? <NotAvailable reason="базовая линия не покрывает запрос" /> : `${tco2e(baseline.e_base_tco2e)} т CO₂-экв.`}
            <div className="muted small">{baseline.note}</div>
          </dd>
        </div>
        <div className="field">
          <dt>Диапазон результата</dt>
          <dd>
            {uncertainty.lower_tco2e === null || uncertainty.upper_tco2e === null ? (
              <NotAvailable reason="диапазон не рассчитан" />
            ) : (
              `${tco2e(uncertainty.lower_tco2e)} … ${tco2e(uncertainty.upper_tco2e)} т CO₂-экв.`
            )}
            <div className="muted small">
              H = {tco2e(uncertainty.h_tco2e)} · {uncertainty.method}
              {uncertainty.is_probabilistic ? '' : ' · сценарный диапазон, не эмпирически откалиброванный интервал'}
            </div>
          </dd>
        </div>
      </dl>

      <h3>От R к Q</h3>
      <ol className="lens-steps">
        {steps.map((step) => (
          <li key={step.id} data-testid={`lens-step-${step.id}`}>
            <details>
              <summary>
                <span>{step.label}</span>
                <span className="summary-value">{step.value === null ? '—' : `${tco2e(step.value)} т CO₂-экв.`}</span>
              </summary>
              <div className="evidence-section-body small">
                <code className="mono">{step.formula}</code>
                <div className="muted">{step.note}</div>
              </div>
            </details>
          </li>
        ))}
        <li className="lens-step-total" data-testid="lens-step-q">
          <span>Q — потенциальные единицы</span>
          <span className="summary-value">{units.q === null ? 'недоступно' : units.q.toLocaleString('ru-RU')}</span>
        </li>
      </ol>
      {units.q === 0 && <p className="small warn">Расчёт остановлен на нуле: ненулевой остаток как доступные единицы не показывается.</p>}
      <p className="muted small">
        Значения приходят из расчёта сервиса. Интерфейс их не пересчитывает: формулы показаны для проверки, а не для вычисления.
      </p>
    </div>
  );
}
