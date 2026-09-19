import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { GeometryError, geometryBounds, toLeafletBounds } from '../../domain/geo';
import { rings } from '../geometry';
import type { AnalysisResult, Geometry } from '../types';

export interface CellFeature {
  cell_id: string;
  zone_id: string | null;
  valid: boolean;
  weight_ha: number | null;
  carbon: Record<string, number | null>;
  sd: Record<string, number | null>;
  geometry: Geometry;
}

export type CellsState =
  | { kind: 'hidden' }
  | { kind: 'loading' }
  | { kind: 'ready'; cells: CellFeature[] }
  | { kind: 'empty' }
  | { kind: 'unavailable'; reason: string }
  | { kind: 'integrity-failed'; reason: string };

interface Props {
  geometry: Geometry | null;
  result: AnalysisResult | null;
  cells: CellsState;
  selectedZoneId: string | null;
  onSelectZone: (zoneId: string) => void;
  selectedCellId: string | null;
  onSelectCell: (cellId: string) => void;
  drawing: boolean;
  onDrawn: (geometry: Geometry) => void;
}

function toLatLngs(geometry: Geometry): [number, number][][] {
  return rings(geometry).map((ring) => ring.map(([lon, lat]) => [lat as number, lon as number] as [number, number]));
}

function anchorFor(geometry: Geometry, index: number, total: number): [number, number] | null {
  try {
    const b = geometryBounds(geometry as never);
    const step = (b.maxLon - b.minLon) / (total + 1);
    return [(b.minLat + b.maxLat) / 2, b.minLon + step * (index + 1)];
  } catch {
    return null;
  }
}

/**
 * The map never disappears because one layer failed: a layer that cannot be drawn is listed under the
 * canvas with the reason, and an artifact whose hash does not match is refused rather than trusted.
 */
export function LensMapView(props: Props) {
  const { geometry, result, cells, selectedZoneId, onSelectZone, selectedCellId, onSelectCell, drawing, onDrawn } = props;
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const readoutRef = useRef<HTMLDivElement | null>(null);
  const [ready, setReady] = useState(false);
  const sessionRef = useRef(0);
  const [corner, setCorner] = useState<{ session: number; point: [number, number] } | null>(null);

  const view = useMemo(() => {
    if (!geometry) return { latLngs: null, bounds: null, error: null as string | null };
    try {
      return { latLngs: toLatLngs(geometry), bounds: toLeafletBounds(geometryBounds(geometry as never)), error: null as string | null };
    } catch (err) {
      return { latLngs: null, bounds: null, error: err instanceof GeometryError ? err.message : String(err) };
    }
  }, [geometry]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, { zoomControl: false, attributionControl: true, zoomAnimation: false, zoomSnap: 0.25 });
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.control.scale({ position: 'bottomleft', imperial: false, maxWidth: 140 }).addTo(map);
    map.attributionControl.setPrefix(false);
    map.attributionControl.addAttribution('Без внешней подложки · геометрия из data/');
    map.setView([56.6, 32.94], 11);
    map.on('mousemove', (e: L.LeafletMouseEvent) => {
      if (readoutRef.current) {
        const { lat, lng } = e.latlng;
        readoutRef.current.textContent = `${Math.abs(lat).toFixed(4)}° ${lat >= 0 ? 'N' : 'S'}  ${Math.abs(lng).toFixed(4)}° ${lng >= 0 ? 'E' : 'W'}`;
      }
    });
    mapRef.current = map;
    setReady(true);
    return () => {
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const { latLngs, bounds } = view;
    if (!map || !ready || !latLngs || !bounds) return;
    const layer = L.polygon(latLngs, { color: '#71d39b', weight: 2, fillColor: '#46b875', fillOpacity: 0.06 }).addTo(map);
    try {
      map.fitBounds(bounds, { padding: [40, 40] });
    } catch {
      map.setView([bounds[0][0], bounds[0][1]], 11);
    }
    return () => {
      layer.remove();
    };
  }, [ready, view]);

  useEffect(() => {
    const map = mapRef.current;
    const zones = result?.zones ?? [];
    if (!map || !ready || !geometry || zones.length === 0) return;
    const drawn = zones
      .map((zone, index) => {
        const selected = zone.zone_id === selectedZoneId;
        const fire = String(zone.cause) === 'FIRE_SUPPORTED';
        const style = {
          color: selected ? '#edf3ef' : fire ? '#f0a06a' : '#b3bfb8',
          weight: selected ? 3 : 1.5,
          fillColor: fire ? '#f0a06a' : '#b3bfb8',
          fillOpacity: selected ? 0.4 : 0.2,
          dashArray: fire ? undefined : '4 3',
        };
        const label = `${String(zone.fact)} · ${zone.area_ha.toLocaleString('ru-RU')} га · ${fire ? 'причина: пожар по продукту' : 'причина не установлена'}`;
        const layer = zone.geometry
          ? L.polygon(toLatLngs(zone.geometry), style)
          : (() => {
              const anchor = anchorFor(geometry, index, zones.length);
              return anchor ? L.circleMarker(anchor, { ...style, radius: selected ? 11 : 8, fillOpacity: 0.95 }) : null;
            })();
        if (!layer) return null;
        layer.addTo(map).bindTooltip(label, { direction: 'top' });
        layer.on('click', () => onSelectZone(zone.zone_id));
        return layer;
      })
      .filter((item): item is L.Polygon | L.CircleMarker => item !== null);
    return () => {
      drawn.forEach((item) => item.remove());
    };
  }, [ready, geometry, result, selectedZoneId, onSelectZone]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || cells.kind !== 'ready') return;
    const drawn = cells.cells.map((cell) => {
      const selected = cell.cell_id === selectedCellId;
      const layer = L.polygon(toLatLngs(cell.geometry), {
        color: selected ? '#edf3ef' : cell.valid ? '#5ea9d8' : '#d8b46a',
        weight: selected ? 2 : 0.7,
        fillColor: cell.valid ? '#5ea9d8' : '#d8b46a',
        fillOpacity: selected ? 0.35 : 0.12,
        dashArray: cell.valid ? undefined : '3 3',
      })
        .addTo(map)
        .bindTooltip(`${cell.cell_id}${cell.valid ? '' : ' · без числовых данных'}`, { direction: 'top' });
      layer.on('click', () => onSelectCell(cell.cell_id));
      return layer;
    });
    return () => {
      drawn.forEach((item) => item.remove());
    };
  }, [ready, cells, selectedCellId, onSelectCell]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const container = map.getContainer();
    container.style.cursor = drawing ? 'crosshair' : '';
    if (!drawing) return;
    sessionRef.current += 1;
    const session = sessionRef.current;
    const onClick = (e: L.LeafletMouseEvent) => {
      const point: [number, number] = [e.latlng.lng, e.latlng.lat];
      setCorner((previous) => {
        if (!previous || previous.session !== session) return { session, point };
        const [lon1, lat1] = previous.point;
        const [lon2, lat2] = point;
        const west = Math.min(lon1, lon2);
        const east = Math.max(lon1, lon2);
        const south = Math.min(lat1, lat2);
        const north = Math.max(lat1, lat2);
        onDrawn({
          type: 'Polygon',
          coordinates: [
            [
              [west, south],
              [east, south],
              [east, north],
              [west, north],
              [west, south],
            ],
          ],
        });
        return null;
      });
    };
    map.on('click', onClick);
    return () => {
      map.off('click', onClick);
      container.style.cursor = '';
    };
  }, [ready, drawing, onDrawn]);

  const notAvailable: string[] = [];
  if (result) {
    if (result.zones.length === 0) notAvailable.push('зоны изменений — сервис не вернул ни одной зоны');
    if (!result.artifacts.some((artifact) => artifact.role === 'cells')) notAvailable.push('ячейки углерода — артефакт не приложен к результату');
    notAvailable.push('маска облачности и растр гарей — в браузер не выдаются, метаданные показаны в разделе «Качество и риски»');
  }

  return (
    <section className="map-wrap" aria-label="Карта участка">
      <div className="map-stage">
        <div className="map-canvas" ref={containerRef} data-testid="lens-map" role="region" aria-label="Карта выбранной территории" />
        {drawing && (
          <div className="map-overlay map-compare-toggle" data-testid="lens-draw-hint">
            <span className="small">{corner ? 'Кликните вторую вершину прямоугольника' : 'Кликните первую вершину прямоугольника'}</span>
          </div>
        )}
        <div className="map-overlay map-readout" ref={readoutRef} aria-hidden="true">
          WGS84 · наведите курсор
        </div>
      </div>
      <div className="map-notes">
        {view.error && (
          <div className="state state-error compact" role="alert" data-testid="lens-geometry-error">
            <strong>Геометрия отклонена</strong>
            {view.error}
          </div>
        )}
        {cells.kind === 'loading' && <p className="muted small">Ячейки загружаются…</p>}
        {cells.kind === 'empty' && (
          <p className="muted small" data-testid="lens-cells-empty">
            Слой ячеек пуст: в артефакте нет ни одной ячейки.
          </p>
        )}
        {cells.kind === 'unavailable' && (
          <div className="state state-warn compact" role="status" data-testid="lens-cells-unavailable">
            <strong>Слой ячеек недоступен</strong>
            <span>{cells.reason}</span>
            <span className="muted small">Карта и расчёт остаются на месте: отказ одного слоя не отменяет результат.</span>
          </div>
        )}
        {cells.kind === 'integrity-failed' && (
          <div className="state state-error compact" role="alert" data-testid="lens-cells-integrity">
            <strong>Целостность слоя не подтверждена</strong>
            <span>{cells.reason}</span>
            <span className="muted small">Слой не отображается: показывать непроверенные данные как доверенные нельзя.</span>
          </div>
        )}
        {notAvailable.length > 0 && (
          <p className="muted small" data-testid="lens-map-missing">
            Не показано на карте: {notAvailable.join('; ')}. Пустая карта не означает «изменений нет».
          </p>
        )}
      </div>
    </section>
  );
}
