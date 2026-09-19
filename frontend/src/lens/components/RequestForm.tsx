import { useId, useState } from 'react';
import { Empty } from '../../components/common';
import { LensError } from '../client';
import { extractGeometry } from '../geometry';
import type { AreaMeasurement, Catalog, Geometry } from '../types';
import { LENS_MAX_AREA_HA } from '../types';

export interface RequestDraft {
  aoiId: string | null;
  geometry: Geometry | null;
  geometrySource: string;
  yearStart: number;
  yearEnd: number;
  claimedUnits: string;
}

interface Props {
  catalog: Catalog | null;
  catalogLoading: boolean;
  draft: RequestDraft;
  onDraft: (next: RequestDraft) => void;
  measurement: AreaMeasurement | null;
  measuring: boolean;
  measureError: string | null;
  drawing: boolean;
  onToggleDrawing: () => void;
  onSubmit: () => void;
  submitLabel: string;
  busy: boolean;
  allowClaim: boolean;
  error: string | null;
}

/**
 * Choosing a supplied area, drawing a contour or pasting GeoJSON, with the area the service measured
 * shown before anything is sent. A local estimate is labelled as preliminary, and a contour over the
 * limit is refused here with the reason instead of failing later with a generic message.
 */
export function RequestForm(props: Props) {
  const { catalog, catalogLoading, draft, onDraft, measurement, measuring, measureError, drawing, onToggleDrawing, onSubmit, submitLabel, busy, allowClaim, error } = props;
  const [importText, setImportText] = useState('');
  const [importError, setImportError] = useState<string | null>(null);
  const importId = useId();

  const years: number[] = [];
  const min = catalog?.year_min ?? 2019;
  const max = catalog?.year_max ?? 2024;
  for (let year = min; year <= max; year += 1) years.push(year);
  const maxArea = catalog?.max_area_ha ?? LENS_MAX_AREA_HA;
  const overLimit = measurement !== null && measurement.area_ha > maxArea;

  const chooseArea = (aoiId: string) => {
    const area = catalog?.areas.find((item) => item.aoi_id === aoiId) ?? null;
    onDraft({
      ...draft,
      aoiId,
      geometry: area?.geometry ?? null,
      geometrySource: area ? `участок ${aoiId} из каталога` : 'участок не найден',
    });
  };

  const chooseSample = (requestId: string) => {
    const sample = catalog?.sample_requests.find((item) => item.request_id === requestId) ?? null;
    if (!sample) return;
    onDraft({
      ...draft,
      aoiId: null,
      geometry: sample.geometry,
      geometrySource: `подучасток ${requestId} из каталога`,
      yearStart: sample.year_start,
      yearEnd: sample.year_end,
    });
  };

  const applyImport = () => {
    try {
      const geometry = extractGeometry(importText);
      setImportError(null);
      onDraft({ ...draft, aoiId: null, geometry, geometrySource: 'импортированный GeoJSON' });
    } catch (err) {
      setImportError(err instanceof LensError ? err.message : String(err));
    }
  };

  return (
    <div className="lens-request" data-testid="lens-request-form">
      <h3>Территория</h3>
      {catalogLoading && <div className="state state-loading compact">Каталог загружается…</div>}
      {!catalogLoading && !catalog && <Empty>Каталог участков недоступен.</Empty>}
      {catalog && catalog.areas.length > 0 && (
        <label className="lens-field">
          <span>Готовый участок</span>
          <select className="select" value={draft.aoiId ?? ''} onChange={(event) => chooseArea(event.target.value)} data-testid="lens-area-select">
            <option value="">— выберите участок —</option>
            {catalog.areas.map((area) => (
              <option key={area.aoi_id} value={area.aoi_id}>
                {area.aoi_id} · {area.region}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className="lens-actions">
        <button type="button" className={`btn btn-small ${drawing ? '' : 'btn-secondary'}`} onClick={onToggleDrawing} aria-pressed={drawing} data-testid="lens-draw-toggle">
          {drawing ? 'Завершить рисование' : 'Нарисовать контур'}
        </button>
        {catalog?.sample_requests.map((sample) => (
          <button key={sample.request_id} type="button" className="btn btn-small btn-secondary" onClick={() => chooseSample(sample.request_id)} data-testid={`lens-sample-${sample.request_id}`}>
            Подучасток {sample.request_id}
          </button>
        ))}
      </div>

      <details className="evidence-section">
        <summary>Импорт GeoJSON</summary>
        <div className="evidence-section-body">
          <label className="lens-field" htmlFor={importId}>
            <span>Feature, FeatureCollection или geometry</span>
          </label>
          <textarea id={importId} className="input lens-textarea" rows={4} value={importText} onChange={(event) => setImportText(event.target.value)} data-testid="lens-geojson-input" spellCheck={false} />
          <button type="button" className="btn btn-small btn-secondary" onClick={applyImport} data-testid="lens-geojson-apply">
            Применить контур
          </button>
          {importError && (
            <p className="small warn" data-testid="lens-geojson-error">
              {importError}
            </p>
          )}
        </div>
      </details>

      <dl className="fields">
        <div className="field">
          <dt>Источник контура</dt>
          <dd data-testid="lens-geometry-source">{draft.geometry ? draft.geometrySource : 'контур не задан'}</dd>
        </div>
        <div className="field">
          <dt>Площадь</dt>
          <dd data-testid="lens-area">
            {measuring && <span className="muted">измеряется сервисом…</span>}
            {!measuring && measurement === null && <span className="muted">—</span>}
            {!measuring && measurement !== null && (
              <>
                <span className="mono">{measurement.area_ha.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} га</span>
                <div className="muted small" data-testid="lens-area-source">
                  {measurement.source === 'SERVICE' ? 'Площадь сервиса.' : 'Предварительная оценка.'} {measurement.note}
                </div>
              </>
            )}
            <div className="muted small">Предел запроса — {maxArea.toLocaleString('ru-RU')} га.</div>
          </dd>
        </div>
      </dl>
      {measureError && (
        <div className="state state-warn compact" role="status" data-testid="lens-measure-error">
          <strong>Площадь не измерена</strong>
          <span>{measureError}</span>
        </div>
      )}
      {overLimit && (
        <div className="state state-error compact" role="alert" data-testid="lens-area-over-limit">
          <strong>Контур больше предела</strong>
          <span>
            Площадь {measurement.area_ha.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} га превышает предел {maxArea.toLocaleString('ru-RU')} га.
            Уменьшите контур и повторите: запрос не отправляется.
          </span>
        </div>
      )}

      <h3>Период</h3>
      <div className="lens-years">
        <label className="lens-field">
          <span>Начальный год</span>
          <select className="select" value={draft.yearStart} onChange={(event) => onDraft({ ...draft, yearStart: Number(event.target.value) })} data-testid="lens-year-start">
            {years.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </label>
        <label className="lens-field">
          <span>Конечный год</span>
          <select className="select" value={draft.yearEnd} onChange={(event) => onDraft({ ...draft, yearEnd: Number(event.target.value) })} data-testid="lens-year-end">
            {years.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </label>
      </div>

      {allowClaim && (
        <>
          <h3>Заявленный объём</h3>
          <label className="lens-field">
            <span>Заявлено единиц (необязательно)</span>
            <input className="input" inputMode="numeric" value={draft.claimedUnits} onChange={(event) => onDraft({ ...draft, claimedUnits: event.target.value })} data-testid="lens-claim-input" aria-describedby="lens-claim-note" />
          </label>
          <p className="muted small" id="lens-claim-note">
            Пользовательский ввод, не данные организаторов. На расчёт он не влияет; без него все основные функции работают.
          </p>
        </>
      )}

      {error && (
        <div className="state state-error compact" role="alert" data-testid="lens-request-error">
          <strong>Запрос нельзя отправить</strong>
          <span>{error}</span>
        </div>
      )}

      <button type="button" className="btn lens-run" onClick={onSubmit} disabled={busy || overLimit} data-testid="lens-submit">
        {busy ? 'Выполняется…' : submitLabel}
      </button>
    </div>
  );
}
