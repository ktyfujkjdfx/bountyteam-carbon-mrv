import type { ReactNode } from 'react';
import type { Verification } from '../api/types';
import { formatNumber, formatRatio } from '../domain/format';
import { NotAvailable } from './common';

function Metric({ label, title, children, sub, testId }: { label: string; title?: string; children: ReactNode; sub?: ReactNode; testId?: string }) {
  return (
    <div className="metric" title={title} data-testid={testId}>
      <dt>{label}</dt>
      <dd>
        <span className="metric-value">{children}</span>
        {sub && <span className="metric-sub">{sub}</span>}
      </dd>
    </div>
  );
}

function num(value: number | null, digits: number, unit?: string) {
  if (value === null) return <NotAvailable reason="значение null в evidence (недостаточно данных)" />;
  return (
    <>
      {formatNumber(value, digits)}
      {unit && <> <span className="unit">{unit}</span></>}
    </>
  );
}

function signed(value: number, digits: number): string {
  const text = Math.abs(value).toLocaleString('ru-RU', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${value < 0 ? '−' : value > 0 ? '+' : '±'}${text}`;
}

export function MetricsStrip({ verification }: { verification: Verification }) {
  const { metrics, firms } = verification.evidence;
  const ndviDelta =
    metrics.ndvi_before_mean !== null && metrics.ndvi_after_mean !== null ? metrics.ndvi_after_mean - metrics.ndvi_before_mean : null;

  return (
    <dl className="metrics-strip" aria-label="Ключевые метрики наблюдения" data-testid="metrics-strip">
      <Metric label="Baseline forest" title="Площадь исходного леса по маске, по числу пикселей 20 м">
        {num(metrics.baseline_forest_area_ha, 1, 'га')}
      </Metric>
      <Metric label="Affected area" title="Суммарная площадь связных компонент dNBR ≥ порога" testId="metric-affected" sub={
        metrics.affected_fraction_of_baseline_forest !== null ? `${formatRatio(metrics.affected_fraction_of_baseline_forest)} baseline forest` : undefined
      }>
        {num(metrics.affected_area_ha, 2, 'га')}
      </Metric>
      <Metric
        label="NDVI после"
        title="Normalized Difference Vegetation Index (B08, B04), среднее по парно-валидному лесу"
        sub={ndviDelta !== null && metrics.ndvi_before_mean !== null ? `до ${formatNumber(metrics.ndvi_before_mean, 3)} · Δ ${signed(ndviDelta, 3)}` : undefined}
      >
        {num(metrics.ndvi_after_mean, 3)}
      </Metric>
      <Metric label="dNBR mean" title="Разность Normalized Burn Ratio (B8A, B12) до − после, среднее по парно-валидному baseline forest" sub={`порог ≥ ${verification.evidence.method.parameters.disturbance_dnbr_min}`}>
        {num(metrics.dnbr_mean, 3)}
      </Metric>
      <Metric label="Valid forest" title="Paired-valid forest ratio" sub={metrics.paired_valid_forest_pixel_count !== null ? `${metrics.paired_valid_forest_pixel_count.toLocaleString('ru-RU')} пикс.` : undefined}>
        {verification.evidence.quality.paired_valid_forest_ratio === null ? (
          <NotAvailable reason="доля не рассчитана" />
        ) : (
          <>
            {formatNumber(verification.evidence.quality.paired_valid_forest_ratio * 100, 1)} <span className="unit">%</span>
          </>
        )}
      </Metric>
      <Metric label="FIRMS hotspots" title="Тепловые аномалии VIIRS в окне наблюдения; не периметр пожара" sub={firms.support}>
        {firms.hotspot_count}
      </Metric>
    </dl>
  );
}
