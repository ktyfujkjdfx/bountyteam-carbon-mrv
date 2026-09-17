import type { Plot, PlotSummary, Verification } from '../api/types';
import { COMPUTATION_META, DATASET_META } from '../domain/status';
import { formatNumber, formatUtc, shortHash } from '../domain/format';
import { GeometryError, geometryBounds } from '../domain/geo';
import { Badge, StatusBadge } from './common';

interface Props {
  plot: Plot;
  plots: PlotSummary[];
  onSelectPlot: (plotId: string) => void;
  latest: Verification | null;
}

function centroidLabel(plot: Plot): string | null {
  try {
    const b = geometryBounds(plot.geometry);
    const lat = (b.minLat + b.maxLat) / 2;
    const lon = (b.minLon + b.maxLon) / 2;
    return `${Math.abs(lat).toFixed(3)}° ${lat >= 0 ? 'N' : 'S'} · ${Math.abs(lon).toFixed(3)}° ${lon >= 0 ? 'E' : 'W'}`;
  } catch (err) {
    if (err instanceof GeometryError) return null;
    throw err;
  }
}

export function ProjectHeader({ plot, plots, onSelectPlot, latest }: Props) {
  const centroid = centroidLabel(plot);
  const after = latest?.evidence.observation.after ?? null;

  return (
    <header className="project-header" data-testid="plot-meta">
      <div className="project-title">
        <div className="project-eyebrow">
          {plots.length > 1 ? (
            <label className="field-inline">
              <span className="visually-hidden">Участок мониторинга</span>
              <select className="select" value={plot.plot_id} onChange={(e) => onSelectPlot(e.target.value)} data-testid="plot-select">
                {plots.map((p) => (
                  <option key={p.plot_id} value={p.plot_id}>
                    {p.plot_id}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <span className="label mono">{plot.plot_id}</span>
          )}
          {latest && (
            <span className="badge-row" data-testid="data-mode-badges">
              <StatusBadge meta={DATASET_META[latest.evidence.dataset_kind]} testId="dataset-kind" />
              <StatusBadge meta={COMPUTATION_META[latest.computation_mode]} testId="computation-mode" />
              <Badge tone="neutral" title="Исторический replay, не текущее наблюдение">
                {latest.observation_mode}
              </Badge>
            </span>
          )}
        </div>
        <h1 className="project-name" data-testid="plot-name">
          {plot.name}
        </h1>
        <div className="project-sub">
          {centroid && <span className="mono">{centroid}</span>}
          <span className="mono" title={plot.geometry_hash}>
            geometry {shortHash(plot.geometry_hash, 8)}
          </span>
        </div>
      </div>

      <dl className="project-facts">
        <div className="fact">
          <dt>Площадь</dt>
          <dd data-testid="plot-area">
            {formatNumber(plot.area_ha, 1)} <span className="unit">га</span>
          </dd>
        </div>
        <div className="fact">
          <dt>Последнее наблюдение</dt>
          <dd className="mono">{after ? formatUtc(after.acquired_at) : 'нет наблюдения'}</dd>
        </div>
        <div className="fact">
          <dt>Источник</dt>
          <dd>
            {after ? (
              <>
                {after.provider} <span className="unit mono">{after.collection}</span>
              </>
            ) : (
              '—'
            )}
          </dd>
        </div>
        <div className="fact">
          <dt>Обработано</dt>
          <dd className="mono">{latest ? formatUtc(latest.processed_at) : '—'}</dd>
        </div>
      </dl>
    </header>
  );
}
