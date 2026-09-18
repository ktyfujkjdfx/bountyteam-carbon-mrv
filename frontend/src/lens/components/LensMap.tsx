import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { GeometryError, geometryBounds, toLeafletBounds } from '../../domain/geo';
import type { LensGeometry, LensLayer, LensZone } from '../types';

interface Props {
  geometry: LensGeometry | null;
  zones: LensZone[];
  layers: LensLayer[];
  visibleLayers: ReadonlySet<string>;
  selectedZoneId: string | null;
  onSelectZone: (zoneId: string) => void;
  drawing: boolean;
  onDrawn: (geometry: LensGeometry) => void;
}

function ringsOf(geometry: LensGeometry): number[][][] {
  return geometry.type === 'Polygon' ? (geometry.coordinates as number[][][]) : (geometry.coordinates as number[][][][]).flat();
}

function toLatLngs(geometry: LensGeometry): [number, number][][] {
  return ringsOf(geometry).map((ring) => ring.map(([lon, lat]) => [lat as number, lon as number] as [number, number]));
}

// A zone without geometry is anchored as a labelled marker inside the contour instead of being hidden.
function zoneAnchor(geometry: LensGeometry, index: number, total: number): [number, number] | null {
  try {
    const b = geometryBounds(geometry as never);
    const step = (b.maxLon - b.minLon) / (total + 1);
    return [(b.minLat + b.maxLat) / 2, b.minLon + step * (index + 1)];
  } catch {
    return null;
  }
}

export function LensMap({ geometry, zones, layers, visibleLayers, selectedZoneId, onSelectZone, drawing, onDrawn }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const readoutRef = useRef<HTMLDivElement | null>(null);
  const [ready, setReady] = useState(false);
  const sessionRef = useRef(0);
  const [corner, setCorner] = useState<{ session: number; point: [number, number] } | null>(null);
  const missingLayers = layers.filter((layer) => layer.availability !== 'AVAILABLE');

  // Geometry is validated during render, so an invalid contour never needs a state update from an effect.
  const geometryView = useMemo(() => {
    if (!geometry) return { latLngs: null, bounds: null, error: null as string | null };
    try {
      return {
        latLngs: ringsOf(geometry).map((ring) => ring.map(([lon, lat]) => [lat as number, lon as number] as [number, number])),
        bounds: toLeafletBounds(geometryBounds(geometry as never)),
        error: null as string | null,
      };
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
    const { latLngs, bounds } = geometryView;
    if (!map || !ready || !latLngs || !bounds) return;
    const layer = L.polygon(latLngs, { color: '#71d39b', weight: 2, fillColor: '#46b875', fillOpacity: 0.07 }).addTo(map);
    try {
      map.fitBounds(bounds, { padding: [40, 40] });
    } catch {
      map.setView([bounds[0][0], bounds[0][1]], 11);
    }
    return () => {
      layer.remove();
    };
  }, [ready, geometryView]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !geometry || zones.length === 0 || !visibleLayers.has('CHANGE_ZONES')) return;
    const drawn = zones
      .map((zone, index) => {
        const selected = zone.zone_id === selectedZoneId;
        const supported = zone.cause_status === 'SUPPORTED';
        const style = {
          color: selected ? '#edf3ef' : supported ? '#f0a06a' : '#b3bfb8',
          weight: selected ? 3 : 1.5,
          fillColor: supported ? '#f0a06a' : '#b3bfb8',
          fillOpacity: selected ? 0.4 : 0.22,
          dashArray: supported ? undefined : '4 3',
        };
        const tooltip = `${zone.label} · ${zone.area_ha.toLocaleString('ru-RU')} га · ${supported ? 'причина подтверждена продуктом' : 'причина не установлена'}`;
        const layer = zone.geometry
          ? L.polygon(toLatLngs(zone.geometry), style)
          : (() => {
              const anchor = zoneAnchor(geometry, index, zones.length);
              return anchor ? L.circleMarker(anchor, { ...style, radius: selected ? 11 : 8, fillOpacity: 0.95 }) : null;
            })();
        if (!layer) return null;
        layer.addTo(map).bindTooltip(tooltip, { direction: 'top' });
        layer.on('click', () => onSelectZone(zone.zone_id));
        return layer;
      })
      .filter((m): m is L.Polygon | L.CircleMarker => m !== null);
    return () => {
      drawn.forEach((m) => m.remove());
    };
  }, [ready, geometry, zones, visibleLayers, selectedZoneId, onSelectZone]);

  // Vector layers the result ships inline (currently the schematic gap in numeric coverage).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const drawn = layers
      .filter((layer) => layer.availability === 'AVAILABLE' && layer.geometry && visibleLayers.has(layer.layer_id))
      .map((layer) =>
        L.polygon(toLatLngs(layer.geometry as LensGeometry), {
          color: '#d8b46a',
          weight: 1,
          fillColor: '#d8b46a',
          fillOpacity: 0.18,
          dashArray: '6 4',
        })
          .addTo(map)
          .bindTooltip(`${layer.label}: ${layer.note}`, { direction: 'top' }),
      );
    return () => {
      drawn.forEach((m) => m.remove());
    };
  }, [ready, layers, visibleLayers]);

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
        {geometryView.error && (
          <div className="state state-error compact" role="alert" data-testid="lens-geometry-error">
            <strong>Геометрия отклонена</strong>
            {geometryView.error}
          </div>
        )}
        {missingLayers.length > 0 && (
          <p className="muted small" data-testid="lens-map-missing-layers">
            Не показаны на карте: {missingLayers.map((layer) => layer.label).join(', ')}. Пустая карта не означает «изменений нет» —
            причины перечислены в списке слоёв.
          </p>
        )}
      </div>
    </section>
  );
}
