import type { LayerAvailability, LensLayer } from '../types';

const AVAILABILITY: Record<LayerAvailability, { tone: string; label: string }> = {
  AVAILABLE: { tone: 'ok', label: 'есть данные' },
  NO_DATA: { tone: 'review', label: 'нет данных' },
  NOT_IN_THIS_MODE: { tone: 'neutral', label: 'нет в этом режиме' },
};

interface Props {
  layers: LensLayer[];
  visible: ReadonlySet<string>;
  onToggle: (layerId: string) => void;
}

/**
 * Every layer the service can describe is listed, including the ones it cannot supply: a missing layer is
 * stated as "нет данных" with a reason instead of leaving a clean map that looks like "всё в порядке".
 */
export function LayersPanel({ layers, visible, onToggle }: Props) {
  return (
    <div className="lens-layers" data-testid="lens-layers">
      <ul className="layer-list">
        {layers.map((layer) => {
          const availability = AVAILABILITY[layer.availability] ?? AVAILABILITY.NO_DATA;
          const toggleable = layer.availability === 'AVAILABLE' && layer.layer_id !== 'AOI_CONTOUR';
          return (
            <li key={layer.layer_id} className="layer-item" data-testid={`lens-layer-${layer.layer_id}`} data-availability={layer.availability}>
              <div className="layer-head">
                {toggleable ? (
                  <label className="layer-toggle">
                    <input
                      type="checkbox"
                      checked={visible.has(layer.layer_id)}
                      onChange={() => onToggle(layer.layer_id)}
                      data-testid={`lens-layer-toggle-${layer.layer_id}`}
                    />
                    <span>{layer.label}</span>
                  </label>
                ) : (
                  <span className="layer-name">{layer.label}</span>
                )}
                <span className={`badge tone-${availability.tone}`} data-testid={`lens-layer-availability-${layer.layer_id}`}>
                  {availability.label}
                </span>
              </div>
              <div className="muted small">{layer.note}</div>
              <div className="layer-meta mono small">
                {layer.unit && <span>единица: {layer.unit}</span>}
                {layer.resolution_m !== null && <span>шаг сетки: {layer.resolution_m} м</span>}
                {layer.observed_at && <span>дата: {layer.observed_at}</span>}
                {layer.source_id && <span>источник: {layer.source_id}</span>}
              </div>
              {layer.availability === 'AVAILABLE' && layer.legend.length > 0 && (
                <ul className="legend small">
                  {layer.legend.map((entry) => (
                    <li key={entry.label}>
                      <span className={`legend-swatch legend-${entry.swatch}`} aria-hidden="true" /> {entry.label}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
      <p className="muted small">
        Слой без данных не рисуется и не заменяется другим: оптическое качество и числовое покрытие биомассы — разные оси, одна не
        восполняет другую.
      </p>
    </div>
  );
}
