import { NotAvailable } from '../../components/common';
import type { LensResult } from '../types';

function percent(value: number | null): string {
  return value === null ? '—' : `${(value * 100).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} %`;
}

export function CoveragePanel({ result }: { result: LensResult }) {
  return (
    <div className="lens-coverage" data-testid="lens-coverage">
      {result.coverage.map((axis) => (
        <div key={axis.id} className="lens-coverage-row" data-testid={`lens-coverage-${axis.id}`}>
          <div className="lens-coverage-head">
            <span className="label">{axis.label}</span>
            <span className="mono">{percent(axis.covered_fraction)}</span>
          </div>
          <div className="quality-bar" aria-hidden="true">
            <div
              className="quality-bar-fill"
              data-tone={axis.covered_fraction === null ? 'neutral' : axis.covered_fraction >= 0.85 ? 'ok' : 'review'}
              style={{ width: `${Math.round((axis.covered_fraction ?? 0) * 100)}%` }}
            />
          </div>
          <p className="muted small">
            {axis.note}
            {axis.missing_area_ha !== null && axis.missing_area_ha > 0 ? ` Пропуск: ${axis.missing_area_ha.toLocaleString('ru-RU')} га.` : ''}
          </p>
        </div>
      ))}
      <p className="muted small">
        Покрытие биомассы и оптическое paired-valid — разные оси. Хороший снимок не восполняет отсутствующие числовые данные, а облачность
        не делает покрытие CCI неполным.
      </p>
      {result.coverage.length === 0 && <NotAvailable reason="сервис не вернул покрытия" />}
    </div>
  );
}
