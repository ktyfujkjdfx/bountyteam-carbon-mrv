import { Empty, StatusBadge } from '../../components/common';
import { metaFor } from '../../domain/status';
import { eventsForAoi } from '../data';
import { ZONE_CAUSE_META, ZONE_FACT_META } from '../status';
import { ZONE_EVIDENCE_RU, serviceTextRu } from '../ru';
import { ProjectionChart } from './ProjectionChart';
import type { AnalysisResult, Zone } from '../types';

function num(value: number | null | undefined, digits = 1, unit = ''): string {
  if (value === null || value === undefined) return 'нет данных';
  return `${value.toLocaleString('ru-RU', { maximumFractionDigits: digits })}${unit ? ` ${unit}` : ''}`;
}

/**
 * Измерения зоны из блока `evidence`. Контракт объявляет его свободной картой значений, поэтому
 * показываются только известные ключи, а доли переводятся в проценты — читателю нужна доля, а не
 * число с девятью знаками.
 */
function zoneEvidenceRows(evidence: Record<string, unknown>): Array<[string, string]> {
  const rows: Array<[string, string]> = [];
  for (const [key, label] of Object.entries(ZONE_EVIDENCE_RU)) {
    const value = evidence?.[key];
    if (typeof value !== 'number' || !Number.isFinite(value)) continue;
    rows.push([label, key === 'pixels' ? value.toLocaleString('ru-RU') : `${(value * 100).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} %`]);
  }
  return rows;
}

/** Вкладка 1: что показывают данные — годовой ряд, зоны изменений и записи о событиях. */
export function WhatHappened({
  result,
  selectedZoneId,
  onSelectZone,
  showProjection,
}: {
  result: AnalysisResult;
  selectedZoneId: string | null;
  onSelectZone: (zoneId: string) => void;
  showProjection: boolean;
}) {
  const zones = result.zones;
  const events = eventsForAoi(result.request.aoi_id);
  const selected: Zone | null = zones.find((zone) => zone.zone_id === selectedZoneId) ?? zones[0] ?? null;

  return (
    <div className="lens-tab-body" data-testid="lens-what-happened">
      <h3>Как менялся запас углерода по годам</h3>
      <ProjectionChart result={result} showProjection={showProjection} />

      <h3>Где именно произошли изменения</h3>
      {zones.length === 0 ? (
        <Empty>
          <strong>Отдельные зоны не выделены</strong>
          <span data-testid="lens-zones-empty">
            Для этого запроса сервис не вернул зон изменения. Это не то же самое, что «изменений нет»: смотрите годовой ряд и покрытие.
          </span>
        </Empty>
      ) : (
        <>
          <ul className="lens-zone-list" data-testid="lens-zone-list">
            {zones.map((zone) => (
              <li key={zone.zone_id}>
                <button
                  type="button"
                  className={`lens-zone-item${zone.zone_id === selected?.zone_id ? ' selected' : ''}`}
                  onClick={() => onSelectZone(zone.zone_id)}
                  aria-pressed={zone.zone_id === selected?.zone_id}
                  data-testid={`lens-zone-${zone.zone_id}`}
                >
                  <span>{metaFor(ZONE_FACT_META, zone.fact).label}</span>
                  <span className="muted small">{num(zone.area_ha, 1, 'га')}</span>
                </button>
              </li>
            ))}
          </ul>
          {selected && (
            <article className="lens-zone-card" data-testid="lens-zone-card">
              <header className="batch-header">
                <h4>Зона {selected.zone_id}</h4>
                <StatusBadge meta={metaFor(ZONE_CAUSE_META, selected.cause)} testId="lens-zone-cause" />
              </header>
              <dl className="fields">
                <div className="field">
                  <dt>Что наблюдается</dt>
                  <dd>
                    <StatusBadge meta={metaFor(ZONE_FACT_META, selected.fact)} testId="lens-zone-fact" />
                  </dd>
                </div>
                <div className="field">
                  <dt>Площадь зоны</dt>
                  <dd className="mono">{num(selected.area_ha, 2, 'га')}</dd>
                </div>
                <div className="field">
                  <dt>Пересечение с ячейками углерода</dt>
                  <dd className="mono">{num(selected.carbon_overlap_ha, 2, 'га')}</dd>
                </div>
                <div className="field">
                  <dt>Период</dt>
                  <dd className="mono">
                    {selected.date_range?.start ?? 'нет данных'} … {selected.date_range?.end ?? 'нет данных'}
                    {selected.date_range?.uncertainty_days_max !== null && selected.date_range?.uncertainty_days_max !== undefined && (
                      <div className="muted small">
                        погрешность даты {selected.date_range.uncertainty_days_min ?? '—'}–{selected.date_range.uncertainty_days_max} дней
                      </div>
                    )}
                  </dd>
                </div>
                <div className="field">
                  <dt>Изменение запаса</dt>
                  <dd className="mono">{num(selected.delta_carbon_tc, 1, 'т C')}</dd>
                </div>
                <div className="field">
                  <dt>Вклад в общее изменение</dt>
                  <dd className="mono">{num(selected.contribution_e_tco2e, 1, 'т CO₂-экв.')}</dd>
                </div>
                <div className="field">
                  <dt>Что показали наблюдения</dt>
                  <dd>
                    {zoneEvidenceRows(selected.evidence).length === 0 ? (
                      <span className="muted">сервис не приложил измерений по этой зоне</span>
                    ) : (
                      <ul className="limitations small" data-testid="lens-zone-evidence">
                        {zoneEvidenceRows(selected.evidence).map(([label, value]) => (
                          <li key={label}>
                            {label}: <b>{value}</b>
                          </li>
                        ))}
                      </ul>
                    )}
                  </dd>
                </div>
                {selected.annex && (
                  <>
                    <div className="field">
                      <dt>Официальные записи о событии</dt>
                      <dd data-testid="lens-zone-events">
                        {selected.annex.evidence_events.length > 0 ? (
                          <>
                            {selected.annex.evidence_events.join(', ')}
                            {selected.annex.event_date_range && (
                              <div className="muted small">
                                дата события: {String(selected.annex.event_date_range.start ?? 'нет данных')} … {String(selected.annex.event_date_range.end ?? 'нет данных')}
                              </div>
                            )}
                          </>
                        ) : (
                          <span className="muted">записей нет — причина осталась неустановленной</span>
                        )}
                      </dd>
                    </div>
                    <div className="field">
                      <dt>Когда наблюдали</dt>
                      <dd>
                        {selected.annex.observed_between
                          ? `${String(selected.annex.observed_between.start ?? 'нет данных')} … ${String(selected.annex.observed_between.end ?? 'нет данных')}`
                          : 'нет данных'}
                        {selected.annex.detection_resolution_m !== null && (
                          <div className="muted small">
                            контур выделен с шагом {selected.annex.detection_resolution_m} м; углерод берётся из ячеек около 100 м
                          </div>
                        )}
                      </dd>
                    </div>
                    {selected.annex.severity && (
                      <div className="field">
                        <dt>Сила изменения</dt>
                        <dd>{selected.annex.severity}</dd>
                      </div>
                    )}
                  </>
                )}
                <div className="field">
                  <dt>Почему причина такая</dt>
                  <dd data-testid="lens-zone-reason">
                    {serviceTextRu(selected.cause_reason)}
                    {selected.evidence_refs.length > 0 && (
                      <div className="muted small">Источники: {selected.evidence_refs.join(', ')}</div>
                    )}
                  </dd>
                </div>
              </dl>
              <p className="muted small">
                Вклад зоны виден в изменении запаса и в общем итоге. Отдельное число подтверждённых единиц по зоне не считается: пороги и
                округление применяются ко всему запросу сразу и не складываются из частей.
              </p>
              {selected.annex && (
                <p className="muted small">
                  Записи о событии, интервал наблюдений и сила изменения взяты из файла зон, проверенного по хешу, — контракт API их не
                  передаёт.
                </p>
              )}
            </article>
          )}
        </>
      )}

      <h3>Официальные записи о событиях</h3>
      {events.length === 0 ? (
        <Empty>
          <strong>Событий для этой территории нет</strong>
          <span data-testid="lens-events-empty">
            В официальной таблице <span className="mono">data/events.csv</span> записей нет. Отсутствие записи не означает отсутствие
            изменений — причина просто остаётся неустановленной.
          </span>
        </Empty>
      ) : (
        <ul className="limitations small" data-testid="lens-events-list">
          {events.map((event) => (
            <li key={event.event_id} data-testid={`lens-event-${event.event_id}`}>
              <strong>{event.evidence_type}</strong> · {event.date_min_product} — {event.date_max_product}
              <div className="muted">
                {event.cause_supported}. Пиксели с признаком горения: {event.burned_pixel_centers_in_aoi ?? '—'} из{' '}
                {event.all_pixel_centers_in_aoi ?? '—'}. Погрешность даты: {event.date_uncertainty_days_min ?? '—'}–
                {event.date_uncertainty_days_max ?? '—'} дней.
              </div>
              <div className="muted">{event.limitations}</div>
              {event.context_url && (
                <div className="mono small">
                  <a href={event.context_url} target="_blank" rel="noreferrer noopener">
                    сообщение о событии в регионе
                  </a>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
