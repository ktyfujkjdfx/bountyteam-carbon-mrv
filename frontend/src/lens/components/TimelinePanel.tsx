import { Empty } from '../../components/common';
import type { LensResult } from '../types';

const W = 520;
const H = 190;
const PAD = { top: 16, right: 16, bottom: 28, left: 48 };

export function TimelinePanel({ result }: { result: LensResult }) {
  const points = result.timeline;
  if (points.length === 0) {
    return (
      <Empty>
        <strong>Динамика недоступна</strong>
        <span>Сервис не вернул годовой ряд для этого запроса.</span>
      </Empty>
    );
  }

  const years = points.map((p) => p.year);
  const values = points.flatMap((p) => [p.stock_tc_ha, p.baseline_tc_ha]).filter((v): v is number => v !== null);
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  const minValue = values.length ? Math.min(...values) : 0;
  const maxValue = values.length ? Math.max(...values) : 1;
  const span = maxValue - minValue || 1;

  const x = (year: number) => PAD.left + ((year - minYear) / Math.max(1, maxYear - minYear)) * (W - PAD.left - PAD.right);
  const y = (value: number) => H - PAD.bottom - ((value - minValue) / span) * (H - PAD.top - PAD.bottom);

  // Observed stock is drawn only across consecutive observed years; gaps stay gaps.
  const segments: string[] = [];
  let current: string[] = [];
  let previousYear: number | null = null;
  for (const point of points) {
    const missingYears = previousYear !== null && point.year - previousYear > 1;
    if (point.stock_tc_ha === null || !point.observed || missingYears) {
      if (current.length > 1) segments.push(current.join(' '));
      current = [];
    }
    previousYear = point.year;
    if (point.stock_tc_ha === null || !point.observed) continue;
    current.push(`${current.length === 0 ? 'M' : 'L'}${x(point.year)},${y(point.stock_tc_ha)}`);
  }
  if (current.length > 1) segments.push(current.join(' '));

  const baselinePath = points
    .filter((p) => p.baseline_tc_ha !== null)
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.year)},${y(p.baseline_tc_ha as number)}`)
    .join(' ');

  const selected = points.filter((p) => p.in_selected_period);
  const selectionStart = selected.length ? x(Math.min(...selected.map((p) => p.year))) : null;
  const selectionEnd = selected.length ? x(Math.max(...selected.map((p) => p.year))) : null;

  return (
    <div className="lens-timeline" data-testid="lens-timeline">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Годовой запас углерода и базовая линия" className="lens-chart">
        {selectionStart !== null && selectionEnd !== null && selectionEnd > selectionStart && (
          <rect x={selectionStart} y={PAD.top} width={selectionEnd - selectionStart} height={H - PAD.top - PAD.bottom} className="chart-selection" />
        )}
        <line x1={PAD.left} y1={H - PAD.bottom} x2={W - PAD.right} y2={H - PAD.bottom} className="chart-axis" />
        <line x1={PAD.left} y1={PAD.top} x2={PAD.left} y2={H - PAD.bottom} className="chart-axis" />
        {[minValue, (minValue + maxValue) / 2, maxValue].map((value) => (
          <text key={value} x={PAD.left - 8} y={y(value) + 4} textAnchor="end" className="chart-label">
            {value.toLocaleString('ru-RU', { maximumFractionDigits: 1 })}
          </text>
        ))}
        {points.map((p) => (
          <text key={p.year} x={x(p.year)} y={H - PAD.bottom + 16} textAnchor="middle" className="chart-label">
            {p.year}
          </text>
        ))}
        {baselinePath && <path d={baselinePath} className="chart-baseline" />}
        {segments.map((d) => (
          <path key={d} d={d} className="chart-series" />
        ))}
        {points
          .filter((p) => p.stock_tc_ha !== null && p.observed)
          .map((p) => (
            <circle key={p.year} cx={x(p.year)} cy={y(p.stock_tc_ha as number)} r={3.5} className="chart-point" />
          ))}
      </svg>
      <ul className="legend" aria-label="Легенда динамики">
        <li>
          <span className="legend-swatch legend-series" aria-hidden="true" /> Наблюдаемый запас, т C/га
        </li>
        <li>
          <span className="legend-swatch legend-baseline" aria-hidden="true" /> Базовая линия по условиям кейса, т C/га
        </li>
      </ul>
      <p className="muted small">
        Годы до {result.request.year_start} — история, выбранный период выделен. Пропуски не соединяются линией; сценарий после 2024 года —
        допущение кейса, а не наблюдение.
      </p>
      <div className="table-wrap">
        <table className="data-table" data-testid="lens-timeline-table">
          <thead>
            <tr>
              <th>Год</th>
              <th>Запас, т C/га</th>
              <th>Базовая линия, т C/га</th>
              <th>Тип</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.year}>
                <td className="mono">{p.year}</td>
                <td className="mono">{p.stock_tc_ha === null ? 'нет данных' : p.stock_tc_ha.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}</td>
                <td className="mono">{p.baseline_tc_ha === null ? '—' : p.baseline_tc_ha.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}</td>
                <td>{p.observed ? 'наблюдение' : 'сценарий'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
