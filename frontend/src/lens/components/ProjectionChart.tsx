import { Empty } from '../../components/common';
import { baselineForAoi } from '../data';
import { LENS_PROJECTION_END_YEAR, type AnalysisResult } from '../types';

const W = 560;
const H = 220;
const PAD = { top: 16, right: 16, bottom: 30, left: 52 };

interface Point {
  year: number;
  stock: number | null;
  baseline: number | null;
  observed: boolean;
  inPeriod: boolean;
}

/**
 * Observed stock against the case baseline, with the scenario years after the last observation kept
 * visually apart. The projection is the baseline trajectory of the case read from data/; it is never
 * a forecast of the actual stock and never changes Q.
 */
export function ProjectionChart({ result, showProjection }: { result: AnalysisResult; showProjection: boolean }) {
  const observed: Point[] = result.timeline.map((point) => ({
    year: point.year,
    stock: point.mean_carbon_tc_ha,
    baseline: point.baseline_carbon_tc_ha,
    observed: point.mean_carbon_tc_ha !== null,
    inPeriod: point.in_period,
  }));
  const lastObserved = observed.reduce((max, point) => (point.observed ? Math.max(max, point.year) : max), 0);

  const projection: Point[] = showProjection
    ? baselineForAoi(result.request.aoi_id)
        .filter((row) => row.year_end > lastObserved && row.year_end <= LENS_PROJECTION_END_YEAR)
        .map((row) => ({ year: row.year_end, stock: null, baseline: row.baseline_stock_end_tc_ha, observed: false, inPeriod: false }))
    : [];

  const points = [...observed, ...projection].sort((a, b) => a.year - b.year);
  if (points.length === 0) {
    return (
      <Empty>
        <strong>Динамика недоступна</strong>
        <span>Сервис не вернул годовой ряд для этого запроса.</span>
      </Empty>
    );
  }

  const years = points.map((p) => p.year);
  const values = points.flatMap((p) => [p.stock, p.baseline]).filter((v): v is number => v !== null);
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  const minValue = values.length ? Math.min(...values) : 0;
  const maxValue = values.length ? Math.max(...values) : 1;
  const span = maxValue - minValue || 1;

  const x = (year: number) => PAD.left + ((year - minYear) / Math.max(1, maxYear - minYear)) * (W - PAD.left - PAD.right);
  const y = (value: number) => H - PAD.bottom - ((value - minValue) / span) * (H - PAD.top - PAD.bottom);

  // Observed stock is drawn only across consecutive observed years; a gap stays a gap.
  const segments: string[] = [];
  let current: string[] = [];
  let previousYear: number | null = null;
  for (const point of points) {
    const gap = previousYear !== null && point.year - previousYear > 1;
    if (point.stock === null || !point.observed || gap) {
      if (current.length > 1) segments.push(current.join(' '));
      current = [];
    }
    previousYear = point.year;
    if (point.stock === null || !point.observed) continue;
    current.push(`${current.length === 0 ? 'M' : 'L'}${x(point.year)},${y(point.stock)}`);
  }
  if (current.length > 1) segments.push(current.join(' '));

  const baselinePath = points
    .filter((p) => p.baseline !== null)
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.year)},${y(p.baseline as number)}`)
    .join(' ');

  const selected = points.filter((p) => p.inPeriod);
  const selStart = selected.length ? x(Math.min(...selected.map((p) => p.year))) : null;
  const selEnd = selected.length ? x(Math.max(...selected.map((p) => p.year))) : null;
  const boundary = projection.length > 0 && lastObserved > 0 ? x(lastObserved) : null;

  return (
    <div className="lens-timeline" data-testid="lens-timeline">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Годовой запас углерода, базовая линия и сценарий" className="lens-chart">
        {selStart !== null && selEnd !== null && selEnd > selStart && (
          <rect x={selStart} y={PAD.top} width={selEnd - selStart} height={H - PAD.top - PAD.bottom} className="chart-selection" />
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
        {boundary !== null && (
          <>
            <line x1={boundary} y1={PAD.top} x2={boundary} y2={H - PAD.bottom} className="chart-boundary" data-testid="lens-projection-boundary" />
            <text x={boundary + 4} y={PAD.top + 10} className="chart-label">
              сценарий →
            </text>
          </>
        )}
        {baselinePath && <path d={baselinePath} className="chart-baseline" />}
        {segments.map((d) => (
          <path key={d} d={d} className="chart-series" />
        ))}
        {points
          .filter((p) => p.stock !== null && p.observed)
          .map((p) => (
            <circle key={p.year} cx={x(p.year)} cy={y(p.stock as number)} r={3.5} className="chart-point" />
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
        Выбранный период выделен. Пропуски наблюдений не соединяются линией.
        {projection.length > 0 && (
          <>
            {' '}
            Годы после {lastObserved} — сценарная базовая линия кейса до {LENS_PROJECTION_END_YEAR} года, а не прогноз фактического запаса;
            на текущий Q она не влияет.
          </>
        )}
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
                <td className="mono">{p.stock === null ? 'нет данных' : p.stock.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}</td>
                <td className="mono">{p.baseline === null ? '—' : p.baseline.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}</td>
                <td>{p.observed ? 'наблюдение' : 'сценарий'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
