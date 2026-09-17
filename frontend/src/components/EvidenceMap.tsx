import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent, type RefObject } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { MrvApiClient } from '../api/client';
import type { ArtifactLink, Plot, Verification } from '../api/types';
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
import { artifactLink as findLink, evidenceArtifactFor } from '../domain/artifacts';
import { formatDate } from '../domain/format';
import { useArtifact } from '../hooks/useArtifact';
import { ErrorNotice } from './common';

type LayerKey = 'boundary' | 'after' | 'before' | 'dnbr' | 'affected' | 'firms';
type ViewMode = 'single' | 'compare';

const LAYER_LABEL: Record<LayerKey, string> = {
  boundary: 'Граница участка',
  after: 'Превью «после»',
  before: 'Превью «до»',
  dnbr: 'dNBR превью',
  affected: 'Affected area (контур изменения)',
  firms: 'FIRMS: тепловые аномалии, не периметр',
};

const LAYER_GROUPS: ReadonlyArray<[string, LayerKey[]]> = [
  ['Геометрия', ['boundary']],
  ['Спутниковые превью', ['after', 'before', 'dnbr']],
  ['Сигналы изменения', ['affected', 'firms']],
];

interface Props {
  client: MrvApiClient;
  plot: Plot;
  verification: Verification | null;
}

function graticuleStep(span: number): number {
  const steps = [0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5];
  return steps.find((s) => span / s <= 8) ?? 10;
}

export function EvidenceMap({ client, plot, verification }: Props) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const readoutRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const afterOverlayRef = useRef<L.ImageOverlay | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [mode, setMode] = useState<ViewMode>('single');
  const [layersOpenByDefault] = useState(() => typeof window.matchMedia !== 'function' || window.matchMedia('(min-width: 901px)').matches);
  const [divider, setDivider] = useState(50);
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

  const compareAvailable = links.after !== null && links.before !== null;
  const comparing = mode === 'compare' && compareAvailable;
  const showAfter = comparing || enabled.after;
  const showBefore = comparing || enabled.before;

  const after = useArtifact(client, showAfter ? links.after : null);
  const before = useArtifact(client, showBefore ? links.before : null);
  const dnbr = useArtifact(client, enabled.dnbr && !comparing ? links.dnbr : null);
  const affected = useArtifact(client, enabled.affected ? links.affected : null);
  const firms = useArtifact(client, enabled.firms ? links.firms : null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      zoomControl: false,
      attributionControl: true,
      zoomAnimation: false,
      zoomSnap: 0.25,
    });
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.control.scale({ position: 'bottomleft', imperial: false, maxWidth: 140 }).addTo(map);
    map.attributionControl.setPrefix(false);
    map.attributionControl.addAttribution('Без внешней подложки · превью Sentinel-2 из API');
    map.on('mousemove', (e: L.LeafletMouseEvent) => {
      if (readoutRef.current) {
        const { lat, lng } = e.latlng;
        readoutRef.current.textContent = `${Math.abs(lat).toFixed(4)}° ${lat >= 0 ? 'N' : 'S'}  ${Math.abs(lng).toFixed(4)}° ${lng >= 0 ? 'E' : 'W'}`;
      }
    });
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
      const wide = (containerRef.current?.clientWidth ?? 0) > 720;
      map.fitBounds(toLeafletBounds(plotBounds.bounds), {
        paddingTopLeft: wide ? [284, 40] : [24, 64],
        paddingBottomRight: wide ? [64, 48] : [24, 48],
      });
    } catch {
      map.setView([(plotBounds.bounds.minLat + plotBounds.bounds.maxLat) / 2, (plotBounds.bounds.minLon + plotBounds.bounds.maxLon) / 2], 13);
    }
  }, [mapReady, plotBounds.bounds]);

  // Real WGS84 graticule around the plot; purely a reading aid, no basemap data.
  useEffect(() => {
    const map = mapRef.current;
    const b = plotBounds.bounds;
    if (!map || !mapReady || !b) return;
    const span = Math.max(b.maxLon - b.minLon, b.maxLat - b.minLat, 0.001);
    const step = graticuleStep(span * 3);
    const pad = span * 3;
    const group = L.layerGroup();
    const style: L.PolylineOptions = { color: '#bedcc8', opacity: 0.09, weight: 1, interactive: false };
    const lonStart = Math.floor((b.minLon - pad) / step) * step;
    const latStart = Math.floor((b.minLat - pad) / step) * step;
    for (let lon = lonStart; lon <= b.maxLon + pad; lon += step) {
      L.polyline([[b.minLat - pad, lon], [b.maxLat + pad, lon]], style).addTo(group);
    }
    for (let lat = latStart; lat <= b.maxLat + pad; lat += step) {
      L.polyline([[lat, b.minLon - pad], [lat, b.maxLon + pad]], style).addTo(group);
    }
    group.addTo(map);
    return () => {
      group.remove();
    };
  }, [mapReady, plotBounds.bounds]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !enabled.boundary || plotBounds.error) return;
    const latLngs = plotRings(plot.geometry).map((ring) => ring.map(([lon, lat]) => [lat, lon] as [number, number]));
    const halo = L.polygon(latLngs, { color: '#07110d', weight: 5, opacity: 0.6, fill: false, interactive: false }).addTo(map);
    const line = L.polygon(latLngs, { color: '#71d39b', weight: 2, fill: true, fillColor: '#46b875', fillOpacity: 0.04, interactive: false }).addTo(map);
    return () => {
      halo.remove();
      line.remove();
    };
  }, [mapReady, enabled.boundary, plot.geometry, plotBounds.error]);

  const overlayWarnings: string[] = [];

  function overlayBounds(link: ArtifactLink | null): LonLatBounds | null {
    if (!link) return null;
    const meta = evidenceArtifactFor(verification, link);
    if (!meta?.bounds_wgs84) {
      overlayWarnings.push(`${link.artifact_id}: в evidence нет bounds_wgs84 для этого превью — наложение на карту невозможно`);
      return null;
    }
    try {
      const bounds = artifactBounds(meta.bounds_wgs84);
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

  useImageOverlay(mapRef, mapReady, showBefore && before.payload?.kind === 'image' ? before.payload.src : null, beforeBounds, comparing ? 1 : 0.9);
  useImageOverlay(
    mapRef,
    mapReady,
    showAfter && after.payload?.kind === 'image' ? after.payload.src : null,
    afterBounds,
    comparing ? 1 : 0.9,
    afterOverlayRef,
  );
  useImageOverlay(mapRef, mapReady, enabled.dnbr && !comparing && dnbr.payload?.kind === 'image' ? dnbr.payload.src : null, dnbrBounds, 0.8);

  const applyClip = useCallback(() => {
    const img = afterOverlayRef.current?.getElement();
    const container = containerRef.current;
    if (!img || !container) return;
    if (!comparing) {
      img.style.clipPath = '';
      return;
    }
    const containerRect = container.getBoundingClientRect();
    const imgRect = img.getBoundingClientRect();
    const dividerX = containerRect.left + (containerRect.width * divider) / 100;
    const scale = imgRect.width > 0 ? img.offsetWidth / imgRect.width : 1;
    const inset = Math.max(0, Math.min(img.offsetWidth, (dividerX - imgRect.left) * scale));
    img.style.clipPath = `inset(0 0 0 ${inset}px)`;
  }, [comparing, divider]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    applyClip();
    map.on('move zoom zoomend resize viewreset', applyClip);
    return () => {
      map.off('move zoom zoomend resize viewreset', applyClip);
    };
  }, [mapReady, applyClip, after.payload]);

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
      style: { color: '#f4887c', weight: 1.5, fillColor: '#e8925a', fillOpacity: 0.38 },
      interactive: false,
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
      pointToLayer: (_feature, latlng) => L.circleMarker(latlng, { radius: 4.5, color: '#3a1d00', weight: 1.5, fillColor: '#ffc857', fillOpacity: 1 }),
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

  const layerAvailable = (key: LayerKey) => key === 'boundary' || links[key as Exclude<LayerKey, 'boundary'>] !== null;
  const loadingAny = after.loading || before.loading || dnbr.loading || affected.loading || firms.loading;

  const dragDivider = (clientX: number) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return;
    setDivider(Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100)));
  };
  const onHandlePointerDown = (e: PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    dragDivider(e.clientX);
  };
  const onHandlePointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) dragDivider(e.clientX);
  };
  const onHandleKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? 10 : 2;
    if (e.key === 'ArrowLeft') setDivider((d) => Math.max(0, d - step));
    else if (e.key === 'ArrowRight') setDivider((d) => Math.min(100, d + step));
    else if (e.key === 'Home') setDivider(0);
    else if (e.key === 'End') setDivider(100);
    else return;
    e.preventDefault();
  };

  const scenes = verification?.evidence.observation ?? null;

  return (
    <section className="map-wrap" ref={wrapRef} aria-label="Карта участка и спутниковое evidence">
      <div className="map-stage">
      <div className="map-canvas" ref={containerRef} data-testid="evidence-map" role="region" aria-label="Карта участка" />

      <details className="map-overlay map-layers" open={layersOpenByDefault}>
        <summary>Слои карты</summary>
        <div className="map-toolbar" role="group" aria-label="Слои карты">
          {LAYER_GROUPS.map(([title, keys]) => (
            <div key={title}>
              <div className="map-group-title">{title}</div>
              {keys.map((key) => {
                const available = layerAvailable(key);
                const lockedByCompare = comparing && (key === 'after' || key === 'before' || key === 'dnbr');
                return (
                  <label key={key} className={`layer-toggle${available ? '' : ' unavailable'}`} data-testid={`layer-toggle-${key}`}>
                    <input
                      type="checkbox"
                      checked={available && (lockedByCompare ? key !== 'dnbr' : enabled[key])}
                      disabled={!available || lockedByCompare}
                      onChange={(e) => setEnabled((prev) => ({ ...prev, [key]: e.target.checked }))}
                    />
                    <span className={`swatch swatch-${key}`} aria-hidden="true" />
                    <span>{LAYER_LABEL[key]}</span>
                    {!available && <span className="na">нет артефакта в evidence</span>}
                  </label>
                );
              })}
            </div>
          ))}
        </div>
      </details>

      <div className="map-overlay map-compare-toggle segmented" role="group" aria-label="Режим просмотра превью">
        <button type="button" aria-pressed={!comparing} onClick={() => setMode('single')}>
          Слои
        </button>
        <button
          type="button"
          aria-pressed={comparing}
          disabled={!compareAvailable}
          onClick={() => setMode('compare')}
          title={compareAvailable ? 'Сравнить превью до и после на карте' : 'Нет пары превью PNG/WebP в evidence'}
          data-testid="map-compare"
        >
          До / после
        </button>
      </div>

      {comparing && scenes && (
        <div className="compare-layer" data-testid="map-compare-layer">
          <div className="compare-line" style={{ left: `${divider}%` }} />
          <span className="compare-tag left" style={{ left: `${divider}%` }}>
            <b>До</b>
            <span className="mono">{formatDate(scenes.before.acquired_at)}</span>
          </span>
          <span className="compare-tag right" style={{ left: `${divider}%` }}>
            <b>После</b>
            <span className="mono">{formatDate(scenes.after.acquired_at)}</span>
          </span>
          <div
            className="compare-handle"
            style={{ left: `${divider}%` }}
            role="slider"
            tabIndex={0}
            aria-label="Разделитель до / после"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(divider)}
            aria-valuetext={`${Math.round(divider)} % — слева до, справа после`}
            onPointerDown={onHandlePointerDown}
            onPointerMove={onHandlePointerMove}
            onKeyDown={onHandleKey}
            data-testid="map-compare-handle"
          />
        </div>
      )}

      <div className="map-overlay map-readout" ref={readoutRef} aria-hidden="true">
        WGS84 · наведите курсор
      </div>
      </div>

      {(plotBounds.error || loadingAny || overlayWarnings.length > 0 || geoWarnings.length > 0 || artifactErrors.length > 0) && (
        <div className="map-notes">
          {plotBounds.error && (
            <div className="state state-error compact" role="alert" data-testid="geometry-error">
              <strong>Геометрия участка отклонена</strong>
              {plotBounds.error.message}
            </div>
          )}
          {loadingAny && <div className="state state-loading compact">Загрузка спутниковых превью и слоёв…</div>}
          {[...overlayWarnings, ...geoWarnings].map((warning) => (
            <div key={warning} className="state state-warn compact" role="alert">
              {warning}
            </div>
          ))}
          {artifactErrors.map(([key, error]) => (
            <ErrorNotice key={key} error={error} compact title={`Артефакт недоступен: ${LAYER_LABEL[key]}`} />
          ))}
        </div>
      )}
    </section>
  );
}

function useImageOverlay(
  mapRef: RefObject<L.Map | null>,
  mapReady: boolean,
  src: string | null,
  bounds: LonLatBounds | null,
  opacity: number,
  overlayRef?: RefObject<L.ImageOverlay | null>,
): void {
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !src || !bounds) return;
    const layer = L.imageOverlay(src, toLeafletBounds(bounds), { opacity, interactive: false }).addTo(map);
    if (overlayRef) overlayRef.current = layer;
    return () => {
      if (overlayRef?.current === layer) overlayRef.current = null;
      layer.remove();
    };
  }, [mapRef, mapReady, src, bounds?.minLat, bounds?.minLon, bounds?.maxLat, bounds?.maxLon, opacity, overlayRef]); // eslint-disable-line react-hooks/exhaustive-deps
}
