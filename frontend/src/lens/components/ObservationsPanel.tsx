import { Empty } from '../../components/common';
import { baselineForAoi, eventById, eventsForAoi, caseScenes, sourcesByIds, type SceneRecord } from '../data';
import type { LensResult } from '../types';

function sceneQuality(scene: SceneRecord): { tone: string; label: string } {
  const valid = scene.scl_valid_fraction;
  if (valid === null) return { tone: 'neutral', label: 'нет оценки' };
  if (valid >= 0.9) return { tone: 'ok', label: 'пригодна' };
  if (valid >= 0.6) return { tone: 'review', label: 'частично пригодна' };
  return { tone: 'error', label: 'непригодна' };
}

function percent(value: number | null, digits = 0): string {
  return value === null ? '—' : `${(value * 100).toLocaleString('ru-RU', { maximumFractionDigits: digits })} %`;
}

/**
 * Everything on this panel is an official record from the data/ archive: Sentinel-2 scenes with their
 * cloud share and SCL validity, MODIS burned-area event rows, and the case baseline table. It explains
 * what the calculation could rely on — it is not a calculated result.
 */
export function ObservationsPanel({ result }: { result: LensResult }) {
  const aoiId = result.request.aoi_id ?? result.request.parent_aoi_id;
  const sceneKeys = new Set(result.optical.scene_keys);
  const scenes = caseScenes().filter((scene) => sceneKeys.has(scene.scene_key));
  const events = eventsForAoi(aoiId);
  const baselineRows = baselineForAoi(aoiId).filter(
    (row) => row.year_start >= result.request.year_start && row.year_end <= result.request.year_end,
  );
  const linkedEvents = result.zones
    .map((zone) => ({ zone, event: eventById(zone.evidence_event_id) }))
    .filter((entry): entry is { zone: (typeof result.zones)[number]; event: NonNullable<ReturnType<typeof eventById>> } => entry.event !== null);
  const eventSources = sourcesByIds(events.map((event) => event.source_id));

  return (
    <div className="lens-observations" data-testid="lens-observations">
      <p className="muted small">
        Раздел собран из официального архива <span className="mono">data/</span>: сцены, события и базовая линия. Рассчитанные величины
        сюда не попадают.
      </p>

      <h3>Сцены Sentinel-2 в периоде запроса</h3>
      {scenes.length === 0 ? (
        <Empty>
          <strong>Сцен нет</strong>
          <span data-testid="lens-scenes-empty">{result.optical.note}</span>
        </Empty>
      ) : (
        <div className="table-wrap">
          <table className="data-table" data-testid="lens-scenes-table">
            <thead>
              <tr>
                <th>Дата (UTC)</th>
                <th>Сцена</th>
                <th>Облачность сцены</th>
                <th>Пригодные пиксели (SCL 4–7)</th>
                <th>Оценка</th>
              </tr>
            </thead>
            <tbody>
              {scenes.map((scene) => {
                const quality = sceneQuality(scene);
                return (
                  <tr key={scene.scene_key} data-testid={`lens-scene-${scene.item_id}`}>
                    <td className="mono">{scene.datetime_utc.slice(0, 10)}</td>
                    <td className="mono small">{scene.item_id}</td>
                    <td className="mono">{scene.source_scene_cloud_percent === null ? '—' : `${scene.source_scene_cloud_percent.toFixed(1)} %`}</td>
                    <td className="mono">{percent(scene.scl_valid_fraction, 1)}</td>
                    <td>
                      <span className={`badge tone-${quality.tone}`}>{quality.label}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small">
        Облачность относится к исходной сцене целиком, доля пригодных пикселей — к вырезу участка. Непригодная сцена ограничивает
        объяснение изменения, но не отменяет числовое покрытие биомассы.
      </p>

      <h3>Записи о событиях</h3>
      {events.length === 0 ? (
        <Empty>
          <strong>Событий нет</strong>
          <span data-testid="lens-events-empty">
            Для этой территории в <span className="mono">data/events.csv</span> нет записей о внешних продуктах гарей. Отсутствие записи не
            означает отсутствие изменений — причина остаётся неустановленной.
          </span>
        </Empty>
      ) : (
        <ul className="limitations small" data-testid="lens-events-list">
          {events.map((event) => (
            <li key={event.event_id} data-testid={`lens-event-${event.event_id}`}>
              <strong>{event.evidence_type}</strong> · {event.date_min_product} — {event.date_max_product}
              <div className="muted">
                {event.cause_supported}. Пиксели с признаком горения: {event.burned_pixel_centers_in_aoi ?? '—'} из{' '}
                {event.all_pixel_centers_in_aoi ?? '—'} центров в контуре участка. Погрешность даты: {event.date_uncertainty_days_min ?? '—'}–
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
      {linkedEvents.length > 0 && (
        <p className="muted small" data-testid="lens-event-link-note">
          Зоны {linkedEvents.map((entry) => entry.zone.label).join(', ')} связаны с записью{' '}
          <span className="mono">{linkedEvents[0]?.event.event_id}</span>. Связь задана результатом расчёта; сама запись — официальная
          строка архива. Признак горения по продукту не равен измеренной площади гари.
        </p>
      )}

      <h3>Базовая линия в периоде</h3>
      {baselineRows.length === 0 ? (
        <Empty>
          <strong>Строк базовой линии нет</strong>
          <span>
            Для этого контура и периода в <span className="mono">data/methodology/baseline.csv</span> нет строк: расчёт относительно базовой
            линии невозможен.
          </span>
        </Empty>
      ) : (
        <div className="table-wrap">
          <table className="data-table" data-testid="lens-baseline-table">
            <thead>
              <tr>
                <th>Период</th>
                <th>Запас на начало, т C/га</th>
                <th>Запас на конец, т C/га</th>
                <th>Темп, т C/га·год</th>
              </tr>
            </thead>
            <tbody>
              {baselineRows.map((row) => (
                <tr key={`${row.year_start}-${row.year_end}`}>
                  <td className="mono">
                    {row.year_start}–{row.year_end}
                  </td>
                  <td className="mono">{row.baseline_stock_start_tc_ha?.toFixed(3) ?? '—'}</td>
                  <td className="mono">{row.baseline_stock_end_tc_ha?.toFixed(3) ?? '—'}</td>
                  <td className="mono">{row.historical_rate_tc_ha_yr?.toFixed(3) ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small">
        Базовая линия построена по истории 2015–2019 и задана как условие кейса на 2019–2029. Это сценарий без проекта, а не доказанный
        альтернативный исход и не подтверждение действий владельца.
      </p>

      {eventSources.length > 0 && (
        <>
          <h3>Продукты, использованные для событий</h3>
          <ul className="limitations small" data-testid="lens-event-sources">
            {eventSources.map((source) => (
              <li key={source.source_id}>
                <strong>{source.product}</strong> {source.version}
                <div className="muted">{source.limitations}</div>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
