import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { MrvApiClient } from '../api/client';
import type { ArtifactLink, ArtifactRole, Plot, Verification } from '../api/types';
import {
  GeometryError,
  artifactBounds,
  boundsIntersect,
  geoJsonBounds,
  geometryBounds,
  plotRings,
  toLeafletBounds,
  type LonLatBounds,
} from '../domain/geo';
import { useArtifact } from '../hooks/useArtifact';
import { ErrorNotice } from './common';

type LayerKey = 'boundary' | 'after' | 'before' | 'dnbr' | 'affected' | 'firms';

const LAYER_ROLE: Partial<Record<LayerKey, ArtifactRole>> = {
  after: 'PREVIEW_AFTER',
  before: 'PREVIEW_BEFORE',
  dnbr: 'DNBR_PREVIEW',
  affected: 'AFFECTED_AREA',
  firms: 'FIRMS_POINTS',
};

const LAYER_LABEL: Record<LayerKey, string> = {
  boundary: 'Граница участка',
  after: 'Превью «после»',
  before: 'Превью «до»',
  dnbr: 'dNBR превью',
  affected: 'Affected area (контур изменения)',
  firms: 'FIRMS: тепловые аномалии, не периметр',
};

interface Props {
  client: MrvApiClient;
  plot: Plot;
  verification: Verification | null;
}

function findLink(verification: Verification | null, role: ArtifactRole): ArtifactLink | null {
  return verification?.artifacts.find((a) => a.role === role) ?? null;
}

export function EvidenceMap({ client, plot, verification }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [enabled, setEnabled] = useState<Record<LayerKey, boolean>>({
    boundary: true,
    after: true,
    before: false,
    dnbr: false,
    affected: true,
    firms: true,
  });

  const plotBounds = useMemo<{ bounds: LonLatBounds | null; error: GeometryError | null }>(() => {
    try {
      return { bounds: geometryBounds(plot.geometry), error: null };
    } catch (err) {
      return { bounds: null, error: err instanceof GeometryError ? err : new GeometryError(String(err)) };
    }
  }, [plot.geometry]);

  const links = useMemo(
    () => ({
      after: findLink(verification, 'PREVIEW_AFTER'),
      before: findLink(verification, 'PREVIEW_BEFORE'),
      dnbr: findLink(verification, 'DNBR_PREVIEW'),
      affected: findLink(verification, 'AFFECTED_AREA'),
      firms: findLink(verification, 'FIRMS_POINTS'),
    }),
    [verification],
  );

  const after = useArtifact(client, enabled.after ? links.after : null);
  const before = useArtifact(client, enabled.before ? links.before : null);
  const dnbr = useArtifact(client, enabled.dnbr ? links.dnbr : null);
  const affected = useArtifact(client, enabled.affected ? links.affected : null);
  const firms = useArtifact(client, enabled.firms ? links.firms : null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      zoomControl: true,
      attributionControl: true,
      preferCanvas: false,
    });
    map.attributionControl.setPrefix(false);
    map.attributionControl.addAttribution('Без внешней подложки · превью из API');
    mapRef.current = map;
    setMapReady(true);
    return () => {
      map.remove();
      mapRef.current = null;
      setMapReady(false);
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !plotBounds.bounds) return;
    try {
      map.fitBounds(toLeafletBounds(plotBounds.bounds), { padding: [24, 24] });
    } catch {
      map.setView([(plotBounds.bounds.minLat + plotBounds.bounds.maxLat) / 2, (plotBounds.bounds.minLon + plotBounds.bounds.maxLon) / 2], 13);
    }
  }, [mapReady, plotBounds.bounds]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !enabled.boundary || plotBounds.error) return;
    const latLngs = plotRings(plot.geometry).map((ring) => ring.map(([lon, lat]) => [lat, lon] as [number, number]));
    const layer = L.polygon(latLngs, { color: '#1b4332', weight: 2, fill: false, dashArray: '6 4' }).addTo(map);
    return () => {
      layer.remove();
    };
  }, [mapReady, enabled.boundary, plot.geometry, plotBounds.error]);

  const overlayWarnings: string[] = [];
  const evidenceArtifacts = verification?.evidence.artifacts ?? [];

  function overlayBounds(link: ArtifactLink | null): LonLatBounds | null {
    if (!link) return null;
    const meta = evidenceArtifacts.find((a) => a.artifact_id === link.artifact_id);
    try {
      const bounds = artifactBounds(meta?.bounds_wgs84);
      if (bounds && plotBounds.bounds && !boundsIntersect(bounds, plotBounds.bounds)) {
        overlayWarnings.push(`${link.artifact_id}: bounds не пересекаются с участком — проверьте порядок lon/lat`);
      }
      return bounds;
    } catch (err) {
      overlayWarnings.push(`${link.artifact_id}: ${err instanceof Error ? err.message : String(err)}`);
      return null;
    }
  }

  const afterBounds = overlayBounds(links.after);
  const beforeBounds = overlayBounds(links.before);
  const dnbrBounds = overlayBounds(links.dnbr);

  useImageOverlay(mapRef, mapReady, enabled.after && after.payload?.kind === 'image' ? after.payload.src : null, afterBounds, 0.9);
  useImageOverlay(mapRef, mapReady, enabled.before && before.payload?.kind === 'image' ? before.payload.src : null, beforeBounds, 0.9);
  useImageOverlay(mapRef, mapReady, enabled.dnbr && dnbr.payload?.kind === 'image' ? dnbr.payload.src : null, dnbrBounds, 0.75);

  const geoWarnings: string[] = [];
  const affectedData = affected.payload?.kind === 'geojson' ? affected.payload.data : null;
  const firmsData = firms.payload?.kind === 'geojson' ? firms.payload.data : null;
  for (const [name, data] of [
    ['affected_area', affectedData],
    ['firms_points', firmsData],
  ] as const) {
    if (!data) continue;
    try {
      geoJsonBounds(data);
    } catch (err) {
      geoWarnings.push(`${name}: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !enabled.affected || !affectedData || geoWarnings.some((w) => w.startsWith('affected_area'))) return;
    const layer = L.geoJSON(affectedData, {
      style: { color: '#b8322a', weight: 1.5, fillColor: '#f08a4b', fillOpacity: 0.35 },
    }).addTo(map);
    return () => {
      layer.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapReady, enabled.affected, affectedData]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !enabled.firms || !firmsData || geoWarnings.some((w) => w.startsWith('firms_points'))) return;
    const layer = L.geoJSON(firmsData, {
      pointToLayer: (_feature, latlng) =>
        L.circleMarker(latlng, { radius: 5, color: '#7a0019', weight: 1, fillColor: '#ffb000', fillOpacity: 0.95 }),
    }).addTo(map);
    return () => {
      layer.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapReady, enabled.firms, firmsData]);

  const artifactErrors = [
    ['after', after.error],
    ['before', before.error],
    ['dnbr', dnbr.error],
    ['affected', affected.error],
    ['firms', firms.error],
  ].filter((entry): entry is [LayerKey, NonNullable<typeof after.error>] => entry[1] !== null);

  const layerAvailable = (key: LayerKey) => key === 'boundary' || (LAYER_ROLE[key] !== undefined && links[key as Exclude<LayerKey, 'boundary'>] !== null);
  const loadingAny = after.loading || before.loading || dnbr.loading || affected.loading || firms.loading;

  return (
    <div className="map-wrap">
      {plotBounds.error && (
        <div className="state state-error" role="alert" data-testid="geometry-error">
          Геометрия участка отклонена: {plotBounds.error.message}
        </div>
      )}
      <div className="map-toolbar" role="group" aria-label="Слои карты">
        {(Object.keys(LAYER_LABEL) as LayerKey[]).map((key) => {
          const available = layerAvailable(key);
          return (
            <label key={key} className={`layer-toggle${available ? '' : ' unavailable'}`} data-testid={`layer-toggle-${key}`}>
              <input
                type="checkbox"
                checked={available && enabled[key]}
                disabled={!available}
                onChange={(e) => setEnabled((prev) => ({ ...prev, [key]: e.target.checked }))}
              />
              <span className={`swatch swatch-${key}`} aria-hidden="true" />
              {LAYER_LABEL[key]}
              {!available && <span className="muted"> — нет артефакта</span>}
            </label>
          );
        })}
      </div>
      <div className="map-canvas" ref={containerRef} data-testid="evidence-map" aria-label="Карта участка и evidence" role="region" />
      {loadingAny && <div className="muted small">Загрузка артефактов…</div>}
      {[...overlayWarnings, ...geoWarnings].map((warning) => (
        <div key={warning} className="state state-warn" role="alert">
          {warning}
        </div>
      ))}
      {artifactErrors.map(([key, error]) => (
        <ErrorNotice key={key} error={error} compact title={`Артефакт недоступен: ${LAYER_LABEL[key]}`} />
      ))}
      <p className="muted small">
        Подложка не загружается из интернета: нейтральный фон + GeoJSON и превью из Backend. Координаты GeoJSON — [longitude, latitude], EPSG:4326.
      </p>
    </div>
  );
}

function useImageOverlay(
  mapRef: RefObject<L.Map | null>,
  mapReady: boolean,
  src: string | null,
  bounds: LonLatBounds | null,
  opacity: number,
): void {
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !src || !bounds) return;
    const layer = L.imageOverlay(src, toLeafletBounds(bounds), { opacity, interactive: false }).addTo(map);
    return () => {
      layer.remove();
    };
  }, [mapRef, mapReady, src, bounds?.minLat, bounds?.minLon, bounds?.maxLat, bounds?.maxLon, opacity]); // eslint-disable-line react-hooks/exhaustive-deps
}
