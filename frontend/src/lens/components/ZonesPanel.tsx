import { metaFor } from '../../domain/status';
import { Empty, StatusBadge } from '../../components/common';
import { CAUSE_META } from '../status';
import type { LensResult, LensZone } from '../types';

function num(value: number | null, digits = 2, unit = ''): string {
  return value === null ? 'нет данных' : `${value.toLocaleString('ru-RU', { maximumFractionDigits: digits })}${unit ? ` ${unit}` : ''}`;
}

export function ZonesPanel({
  result,
  selectedZoneId,
  onSelectZone,
}: {
  result: LensResult;
  selectedZoneId: string | null;
  onSelectZone: (zoneId: string) => void;
}) {
  const zones = result.zones;
  if (zones.length === 0) {
    return (
      <Empty>
        <strong>Зоны изменений не выделены</strong>
        <span>Для этого запроса сервис не вернул отдельных областей изменения. Это не то же самое, что «изменений нет».</span>
      </Empty>
    );
  }
  const selected: LensZone | null = zones.find((z) => z.zone_id === selectedZoneId) ?? zones[0] ?? null;
  const source = selected ? result.sources.find((s) => s.source_id === selected.evidence_source_id) ?? null : null;

  return (
    <div className="lens-zones" data-testid="lens-zones">
      <ul className="lens-zone-list">
        {zones.map((zone) => (
          <li key={zone.zone_id}>
            <button
              type="button"
              className={`lens-zone-item${zone.zone_id === selected?.zone_id ? ' selected' : ''}`}
              onClick={() => onSelectZone(zone.zone_id)}
              aria-pressed={zone.zone_id === selected?.zone_id}
              data-testid={`lens-zone-${zone.zone_id}`}
            >
              <span>{zone.label}</span>
              <span className="mono">{num(zone.area_ha, 2, 'га')}</span>
            </button>
          </li>
        ))}
      </ul>

      {selected && (
        <article className="lens-zone-card" data-testid="lens-zone-card">
          <header className="batch-header">
            <h3>{selected.label}</h3>
            <StatusBadge meta={metaFor(CAUSE_META, selected.cause_status)} testId="lens-zone-cause" />
          </header>
          <dl className="fields">
            <div className="field">
              <dt>Площадь зоны</dt>
              <dd className="mono">{num(selected.area_ha, 2, 'га')}</dd>
            </div>
            <div className="field">
              <dt>Доступный интервал дат</dt>
              <dd className="mono">
                {selected.date_min ?? 'нет данных'} … {selected.date_max ?? 'нет данных'}
              </dd>
            </div>
            <div className="field">
              <dt>Изменение запаса</dt>
              <dd className="mono">{num(selected.delta_stock_tc, 2, 'т C')}</dd>
            </div>
            <div className="field">
              <dt>Вклад в E</dt>
              <dd className="mono">{num(selected.contribution_e_tco2e, 2, 'т CO₂-экв.')}</dd>
            </div>
            <div className="field">
              <dt>Основание</dt>
              <dd>
                {selected.evidence_note}
                {source && (
                  <div className="muted small">
                    Источник: {source.title} {source.version} · {source.attribution}
                  </div>
                )}
              </dd>
            </div>
          </dl>
          <p className="muted small">
            Вклад зоны показан в изменении запаса и E. Отдельное количество Q для зоны не приводится: пороги и округление по всему запросу
            неаддитивны.
          </p>
        </article>
      )}
    </div>
  );
}
