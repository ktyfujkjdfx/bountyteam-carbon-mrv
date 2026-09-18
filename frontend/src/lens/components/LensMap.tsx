import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { GeometryError, geometryBounds, toLeafletBounds } from '../../domain/geo';
import type { LensGeometry, LensZone } from '../types';

interface Props {
  geometry: LensGeometry | null;
  zones: LensZone[];
  selectedZoneId: string | null;
  onSelectZone: (zoneId: string) => void;
  drawing: boolean;
  onDrawn: (geometry: LensGeometry) => void;
}

function ringsOf(geometry: LensGeometry): number[][][] {
  return geometry.type === 'Polygon' ? (geometry.coordinates as number[][][]) : (geometry.coordinates as number[][][][]).flat();
}

// Zones in F1 fixtures carry no geometry yet; they are drawn as labelled markers inside the contour.
function zoneAnchor(geometry: LensGeometry, index: number, total: number): [number, number] | null {
  try {
    const b = geometryBounds(geometry as never);
    const step = (b.maxLon - b.minLon) / (total + 1);
    return [(b.minLat + b.maxLat) / 2, b.minLon + step * (index + 1)];
  } catch {
    return null;
  }
}

export function LensMap({ geometry, zones, selectedZoneId, onSelectZone, drawing, onDrawn }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const readoutRef = useRef<HTMLDivElement | null>(null);
  const [ready, setReady] = useState(false);
  const sessionRef = useRef(0);
  const [corner, setCorner] = useState<{ session: number; point: [number, number] } | null>(null);

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
    if (!map || !ready || !geometry || zones.length === 0) return;
    const markers = zones
      .map((zone, index) => {
        const anchor = zoneAnchor(geometry, index, zones.length);
        if (!anchor) return null;
        const selected = zone.zone_id === selectedZoneId;
        const marker = L.circleMarker(anchor, {
          radius: selected ? 11 : 8,
          color: selected ? '#edf3ef' : '#3a1d00',
          weight: selected ? 2 : 1.5,
          fillColor: zone.cause_status === 'SUPPORTED' ? '#f0a06a' : '#b3bfb8',
          fillOpacity: 0.95,
        })
          .addTo(map)
          .bindTooltip(`${zone.label} · ${zone.area_ha} га`, { direction: 'top' });
        marker.on('click', () => onSelectZone(zone.zone_id));
        return marker;
      })
      .filter((m): m is L.CircleMarker => m !== null);
    return () => {
      markers.forEach((m) => m.remove());
    };
  }, [ready, geometry, zones, selectedZoneId, onSelectZone]);

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
      {geometryView.error && (
        <div className="map-notes">
          <div className="state state-error compact" role="alert" data-testid="lens-geometry-error">
            <strong>Геометрия отклонена</strong>
            {geometryView.error}
          </div>
        </div>
      )}
    </section>
  );
}
