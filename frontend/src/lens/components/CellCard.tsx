import type { CellFeature } from './LensMapView';
import type { AnalysisResult } from '../types';

function num(value: number | null | undefined, digits = 2, unit = ''): string {
  if (value === null || value === undefined) return 'нет данных';
  return `${value.toLocaleString('ru-RU', { maximumFractionDigits: digits })}${unit ? ` ${unit}` : ''}`;
}

/** The deepest level of disclosure: one native CCI cell with its own values on both dates. */
export function CellCard({ cell, result }: { cell: CellFeature; result: AnalysisResult }) {
  const years = Object.keys(cell.carbon).sort();
  const first = years[0];
  const last = years[years.length - 1];
  const start = first ? cell.carbon[first] : null;
  const end = last ? cell.carbon[last] : null;
  const delta = start === null || start === undefined || end === null || end === undefined ? null : end - start;
  const artifact = result.artifacts.find((item) => item.role === 'cells') ?? null;

  return (
    <article className="lens-zone-card" data-testid="lens-cell-card">
      <header className="batch-header">
        <h4>Ячейка {cell.cell_id}</h4>
        <span className={`badge tone-${cell.valid ? 'ok' : 'review'}`} data-testid="lens-cell-valid">
          {cell.valid ? 'ЕСТЬ ЧИСЛОВЫЕ ДАННЫЕ' : 'БЕЗ ЧИСЛОВЫХ ДАННЫХ'}
        </span>
      </header>
      <dl className="fields">
        <div className="field">
          <dt>Площадь пересечения с запросом</dt>
          <dd className="mono">{num(cell.weight_ha, 4, 'га')}</dd>
        </div>
        <div className="field">
          <dt>Запас углерода по годам</dt>
          <dd className="mono" data-testid="lens-cell-series">
            {years.length === 0
              ? 'нет данных'
              : years.map((year) => `${year}: ${num(cell.carbon[year], 2)} т C/га`).join(' · ')}
          </dd>
        </div>
        <div className="field">
          <dt>Погрешность оценки (SD)</dt>
          <dd className="mono">
            {years.length === 0 ? 'нет данных' : years.map((year) => `${year}: ±${num(cell.sd[year], 2)}`).join(' · ')}
          </dd>
        </div>
        <div className="field">
          <dt>Изменение за период</dt>
          <dd className="mono">{num(delta, 2, 'т C/га')}</dd>
        </div>
        <div className="field">
          <dt>Зона</dt>
          <dd className="mono">{cell.zone_id ?? 'вне выделенных зон'}</dd>
        </div>
        <div className="field">
          <dt>Источник и разрешение</dt>
          <dd>
            {artifact ? `${artifact.provenance} · ${artifact.media_type}` : 'артефакт не приложен'}
            <div className="muted small">
              {artifact?.resolution ? `шаг ${artifact.resolution.join(' × ')} ${artifact.resolution_units ?? ''}` : 'сетка продукта биомассы'}
              {artifact?.crs ? ` · ${artifact.crs}` : ''}
            </div>
          </dd>
        </div>
      </dl>
      <p className="muted small">
        Значения относятся к ячейке продукта биомассы целиком. Распределение внутри ячейки — модельное допущение: снимок с шагом 20 м не
        превращается в углерод с шагом 20 м.
      </p>
    </article>
  );
}
