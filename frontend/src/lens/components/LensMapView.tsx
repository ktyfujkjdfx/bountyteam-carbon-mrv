import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { GeometryError, geometryBounds, toLeafletBounds } from '../../domain/geo';
import { metaFor } from '../../domain/status';
import { ZONE_CAUSE_META, ZONE_FACT_META } from '../status';
import { rings } from '../geometry';
import type { AnalysisResult, CatalogArea, Geometry } from '../types';

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

export type GapLayerState =
  | { kind: 'hidden' }
  | { kind: 'loading' }
  | { kind: 'ready'; geometries: Geometry[] }
  | { kind: 'empty' }
  | { kind: 'unavailable'; reason: string }
  | { kind: 'integrity-failed'; reason: string };

interface Props {
  geometry: Geometry | null;
  result: AnalysisResult | null;
  cells: CellsState;
  gaps: GapLayerState;
  selectedZoneId: string | null;
  onSelectZone: (zoneId: string) => void;
  selectedCellId: string | null;
  onSelectCell: (cellId: string) => void;
  drawing: boolean;
  onDrawn: (geometry: Geometry) => void;
  /** Участки каталога: показываются обзорно, пока ни один не выбран. */
  areas?: CatalogArea[];
  /** Клик по участку на обзорной карте. Без обработчика обзор только показывает, где что лежит. */
  onPickArea?: (aoiId: string) => void;
  /** Что именно делает клик — подсказка словами: «выбрать» или «открыть заявку». */
  pickHint?: string;
  /** Участки, по которым клик что-то даёт. Остальные подписаны как недоступные. */
  isAreaOpenable?: (aoiId: string) => boolean;
}

/** Цвета слоёв берутся из палитры темы, чтобы карта читалась как часть интерфейса. */
const COLOR = {
  boundary: '#2f7d5b',
  boundaryFill: '#2f7d5b',
  change: '#b4552b',
  changeFill: '#dd8436',
  quiet: '#73817a',
  cell: '#3d9a70',
  gap: '#dd8436',
  selected: '#23302b',
  grid: '#cfd8d1',
} as const;

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

/** Шаг сетки подбирается под размах участка: линий всегда немного. */
function graticuleStep(span: number): number {
  const steps = [0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5];
  return steps.find((step) => span / step <= 8) ?? 10;
}

function zoneTooltip(zone: AnalysisResult['zones'][number]): string {
  const fact = metaFor(ZONE_FACT_META, zone.fact).label;
  const cause = metaFor(ZONE_CAUSE_META, zone.cause).label;
  return `${fact} · ${zone.area_ha.toLocaleString('ru-RU')} га · ${cause.toLowerCase()}`;
}

type LayerKey = 'zones' | 'cells' | 'gaps';

/**
 * Карта участка. Внешних подложек нет — вместо них светлая поверхность и сетка WGS84, поэтому
 * карта работает офлайн и ничего не запрашивает за пределами машины. Слой, который не удалось
 * нарисовать, перечислен под картой с причиной: отказ одного слоя не отменяет результат.
 */
export function LensMapView(props: Props) {
  const { geometry, result, cells, gaps, selectedZoneId, onSelectZone, selectedCellId, onSelectCell, drawing, onDrawn, areas, onPickArea, pickHint, isAreaOpenable } = props;
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const readoutRef = useRef<HTMLDivElement | null>(null);
  const [ready, setReady] = useState(false);
  const sessionRef = useRef(0);
  const [corner, setCorner] = useState<{ session: number; point: [number, number] } | null>(null);
  const [visible, setVisible] = useState<Record<LayerKey, boolean>>({ zones: true, cells: true, gaps: true });

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
    L.control.zoom({ position: 'topright', zoomInTitle: 'Приблизить', zoomOutTitle: 'Отдалить' }).addTo(map);
    L.control.scale({ position: 'bottomleft', imperial: false, maxWidth: 140 }).addTo(map);
    map.attributionControl.setPrefix(false);
    map.attributionControl.addAttribution('Контуры из данных кейса · внешние карты не загружаются');
    map.setView([56.6, 32.94], 11);
    map.on('mousemove', (e: L.LeafletMouseEvent) => {
      if (readoutRef.current) {
        const { lat, lng } = e.latlng;
        readoutRef.current.textContent = `${Math.abs(lat).toFixed(4)}° ${lat >= 0 ? 'с.ш.' : 'ю.ш.'}  ${Math.abs(lng).toFixed(4)}° ${lng >= 0 ? 'в.д.' : 'з.д.'}`;
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

  // Сетка WGS84 вместо подложки: она двигается вместе с картой и остаётся читаемым ориентиром.
  useEffect(() => {
    const map = mapRef.current;
    const bounds = view.bounds;
    if (!map || !ready || !bounds) return;
    const [[minLat, minLon], [maxLat, maxLon]] = bounds;
    const span = Math.max(maxLon - minLon, maxLat - minLat, 0.001);
    const step = graticuleStep(span * 3);
    const pad = span * 3;
    const group = L.layerGroup();
    const style: L.PolylineOptions = { color: COLOR.grid, weight: 1, opacity: 0.9, interactive: false };
    for (let lon = Math.floor((minLon - pad) / step) * step; lon <= maxLon + pad; lon += step) {
      L.polyline([[minLat - pad, lon], [maxLat + pad, lon]], style).addTo(group);
    }
    for (let lat = Math.floor((minLat - pad) / step) * step; lat <= maxLat + pad; lat += step) {
      L.polyline([[lat, minLon - pad], [lat, maxLon + pad]], style).addTo(group);
    }
    group.addTo(map);
    return () => {
      group.remove();
    };
  }, [ready, view.bounds]);

  // Обзор: пока контур не выбран, на карте видны все участки каталога — как точки на городской
  // карте, по которым можно щёлкнуть.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || geometry || !areas || areas.length === 0) return;
    const group = L.layerGroup().addTo(map);
    const all: [number, number][] = [];
    areas.forEach((area) => {
      let rings: [number, number][][];
      try {
        rings = toLatLngs(area.geometry);
      } catch {
        return;
      }
      rings.forEach((ring) => ring.forEach((point) => all.push(point)));
      const layer = L.polygon(rings, {
        color: COLOR.boundary,
        weight: 2,
        fillColor: COLOR.boundaryFill,
        fillOpacity: 0.12,
      }).addTo(group);
      const label = `${area.region} · ${area.aoi_id} · ${area.area_ha.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} га`;
      const openable = onPickArea !== undefined && (isAreaOpenable === undefined || isAreaOpenable(area.aoi_id));
      layer.bindTooltip(
        onPickArea === undefined
          ? label
          : openable
            ? `${label} — нажмите, чтобы ${pickHint ?? 'выбрать'}`
            : `${label} — заявок по этому участку нет`,
        { direction: 'top' },
      );
      const center = layer.getBounds().getCenter();
      const pin = L.circleMarker(center, {
        radius: 9,
        color: '#ffffff',
        weight: 2.5,
        fillColor: openable || onPickArea === undefined ? COLOR.boundary : COLOR.quiet,
        fillOpacity: 1,
      }).addTo(group);
      pin.bindTooltip(`${area.region}<br><span class="map-label-sub">${area.aoi_id} · ${area.area_ha.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} га</span>`, {
        permanent: true,
        direction: 'right',
        offset: [10, 0],
        className: 'map-area-label',
      });
      // Клик принимается и по участку, по которому показывать нечего: отказ должен быть сказан
      // словами, а не тишиной в ответ на нажатие.
      if (onPickArea) {
        layer.on('click', () => onPickArea(area.aoi_id));
        pin.on('click', () => onPickArea(area.aoi_id));
      }
    });
    if (all.length > 0) {
      try {
        map.fitBounds(L.latLngBounds(all), { padding: [40, 40] });
      } catch {
        /* пустая рамка — оставляем вид как есть */
      }
    }
    return () => {
      group.remove();
    };
  }, [ready, geometry, areas, onPickArea, pickHint, isAreaOpenable]);

  useEffect(() => {
    const map = mapRef.current;
    const { latLngs, bounds } = view;
    if (!map || !ready || !latLngs || !bounds) return;
    // Контур участка: белая обводка снизу, зелёная линия сверху — читается на любом фоне.
    const halo = L.polygon(latLngs, { color: '#ffffff', weight: 6, opacity: 0.9, fill: false, interactive: false }).addTo(map);
    const layer = L.polygon(latLngs, { color: COLOR.boundary, weight: 2.5, fillColor: COLOR.boundaryFill, fillOpacity: 0.08, interactive: false }).addTo(map);
    try {
      map.fitBounds(bounds, { padding: [28, 28] });
    } catch {
      map.setView([bounds[0][0], bounds[0][1]], 11);
    }
    return () => {
      halo.remove();
      layer.remove();
    };
  }, [ready, view]);

  useEffect(() => {
    const map = mapRef.current;
    const zones = result?.zones ?? [];
    if (!map || !ready || !geometry || zones.length === 0 || !visible.zones) return;
    const drawn = zones
      .map((zone, index) => {
        const selected = zone.zone_id === selectedZoneId;
        const disturbance = String(zone.fact) !== 'RECOVERY_INDICATION';
        const style = {
          color: selected ? COLOR.selected : disturbance ? COLOR.change : COLOR.quiet,
          weight: selected ? 3 : 1.5,
          fillColor: disturbance ? COLOR.changeFill : COLOR.quiet,
          fillOpacity: selected ? 0.45 : 0.28,
        };
        const layer = zone.geometry
          ? L.polygon(toLatLngs(zone.geometry), style)
          : (() => {
              const anchor = anchorFor(geometry, index, zones.length);
              return anchor
                ? L.circleMarker(anchor, { ...style, color: '#ffffff', weight: 2, radius: selected ? 11 : 8, fillOpacity: 0.95 })
                : null;
            })();
        if (!layer) return null;
        layer.addTo(map).bindTooltip(zoneTooltip(zone), { direction: 'top' });
        layer.on('click', () => onSelectZone(zone.zone_id));
        return layer;
      })
      .filter((item): item is L.Polygon | L.CircleMarker => item !== null);
    return () => {
      drawn.forEach((item) => item.remove());
    };
  }, [ready, geometry, result, selectedZoneId, onSelectZone, visible.zones]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || gaps.kind !== 'ready' || !visible.gaps) return;
    const drawn = gaps.geometries.map((item) => L.polygon(toLatLngs(item), {
      color: COLOR.gap, weight: 1.5, fillColor: COLOR.gap, fillOpacity: 0.16, dashArray: '5 4',
    }).addTo(map).bindTooltip('Здесь две даты нельзя сравнить — это не значит, что изменений не было', { direction: 'top' }));
    return () => drawn.forEach((item) => item.remove());
  }, [ready, gaps, visible.gaps]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || cells.kind !== 'ready' || !visible.cells) return;
    const drawn = cells.cells.map((cell) => {
      const selected = cell.cell_id === selectedCellId;
      const layer = L.polygon(toLatLngs(cell.geometry), {
        color: selected ? COLOR.selected : cell.valid ? COLOR.cell : COLOR.gap,
        weight: selected ? 2 : 0.7,
        fillColor: cell.valid ? COLOR.cell : COLOR.gap,
        fillOpacity: selected ? 0.35 : 0.12,
        dashArray: cell.valid ? undefined : '3 3',
      })
        .addTo(map)
        .bindTooltip(`Ячейка ${cell.cell_id}${cell.valid ? '' : ' · без числовых данных'}`, { direction: 'top' });
      layer.on('click', () => onSelectCell(cell.cell_id));
      return layer;
    });
    return () => {
      drawn.forEach((item) => item.remove());
    };
  }, [ready, cells, selectedCellId, onSelectCell, visible.cells]);

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

  // Кнопки, которые управляют картой, стоят в форме заявки, а сама карта — ниже неё, за сгибом.
  // Поэтому «Нарисовать свой контур» и выбор участка выглядели как нажатие в пустоту: выбор
  // происходил, контур рисовался, но человек всё это время смотрел на форму. Карта подходит к
  // глазам сама — ровно в двух случаях, когда её об этом попросили.
  const broughtIntoView = useRef<Geometry | null>(null);
  useEffect(() => {
    if (!ready) return;
    const picked = onPickArea !== undefined && geometry !== null && geometry !== broughtIntoView.current;
    if (!drawing && !picked) return;
    broughtIntoView.current = geometry;
    containerRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
  }, [ready, drawing, geometry, onPickArea]);

  const fitToArea = () => {
    const map = mapRef.current;
    if (!map || !view.bounds) return;
    map.fitBounds(view.bounds, { padding: [28, 28] });
  };

  const legend: Array<{ key: LayerKey | 'aoi'; kind: string; label: string; toggle: boolean }> = [
    { key: 'aoi', kind: 'aoi', label: geometry ? 'Контур участка' : 'Участки каталога', toggle: false },
  ];
  if ((result?.zones.length ?? 0) > 0) legend.push({ key: 'zones', kind: 'change', label: 'Зоны изменений', toggle: true });
  if (cells.kind === 'ready') legend.push({ key: 'cells', kind: 'cells', label: 'Ячейки углерода', toggle: true });
  if (gaps.kind === 'ready' && gaps.geometries.length > 0) legend.push({ key: 'gaps', kind: 'gap', label: 'Нет сравнимых наблюдений', toggle: true });

  const notAvailable: string[] = [];
  if (result) {
    if (result.zones.length === 0) notAvailable.push('зоны изменений — сервис не вернул ни одной зоны');
    // Сервис называет этот слой `cci_cell_layer`; `cells` — имя из офлайн-набора. Проверять надо
    // обе роли, иначе на живом результате экран сообщает, что файла нет, тогда как кнопка ниже
    // его загружает.
    if (!result.artifacts.some((artifact) => artifact.role === 'cci_cell_layer' || artifact.role === 'cells')) {
      notAvailable.push('ячейки углерода — файл к результату не приложен');
    }
    notAvailable.push('снимки на обе даты, dNBR, маска сравнимых наблюдений и маска зон — приложены к результату как файлы, но отдельными слоями на карту пока не выводятся');
  }

  return (
    <section className="map-wrap" aria-label="Карта участка">
      <div className="map-stage">
        <div className="map-canvas" ref={containerRef} data-testid="lens-map" role="region" aria-label="Карта выбранной территории" />
        {!geometry && !drawing && areas && areas.length > 0 && (
          <div className="map-overlay map-hint" data-testid="lens-map-overview-hint">
            <span>{onPickArea ? `Нажмите на участок, чтобы ${pickHint ?? 'выбрать его для заявки'}` : 'Участки из данных кейса'}</span>
          </div>
        )}
        {drawing && (
          <div className="map-overlay map-hint" data-testid="lens-draw-hint">
            <span>{corner ? 'Щёлкните второй угол прямоугольника' : 'Щёлкните первый угол прямоугольника'}</span>
            {/* На обзоре четыре участка разнесены на сотни километров, и прямоугольник «на глаз»
                выходит и за предел 2000 га, и за покрытие данных. Сервис откажет — но сказать об
                этом до рисования дешевле, чем после. */}
            <span className="muted small">
              {geometry
                ? 'Рисуйте внутри участка: вне данных кейса расчёта не будет.'
                : 'Приблизьтесь к одному из обведённых участков: вне их данных нет, и предел — 2000 га.'}
            </span>
          </div>
        )}
        {view.bounds && (
          <button type="button" className="map-fit" onClick={fitToArea} data-testid="lens-map-fit" title="Показать весь участок">
            <span aria-hidden="true">⤢</span>
            <span className="visually-hidden">Показать весь участок</span>
          </button>
        )}
        <div className="map-legend" data-testid="lens-map-legend">
          {legend.map((item) =>
            item.toggle ? (
              <button
                key={item.key}
                type="button"
                className={`map-legend-item${visible[item.key as LayerKey] ? '' : ' off'}`}
                aria-pressed={visible[item.key as LayerKey]}
                onClick={() => setVisible((prev) => ({ ...prev, [item.key as LayerKey]: !prev[item.key as LayerKey] }))}
                title="Показать или скрыть слой"
              >
                <span className="map-legend-dot" data-kind={item.kind} aria-hidden="true" />
                <span>{item.label}</span>
              </button>
            ) : (
              <span key={item.key} className="map-legend-item static">
                <span className="map-legend-dot" data-kind={item.kind} aria-hidden="true" />
                <span>{item.label}</span>
              </span>
            ),
          )}
        </div>
        <div className="map-readout" ref={readoutRef} aria-hidden="true" />
      </div>
      <div className="map-notes">
        {view.error && (
          <div className="state state-error compact" role="alert" data-testid="lens-geometry-error">
            <strong>Контур не принят</strong>
            {view.error}
          </div>
        )}
        {cells.kind === 'loading' && <p className="muted small">Ячейки загружаются…</p>}
        {cells.kind === 'empty' && (
          <p className="muted small" data-testid="lens-cells-empty">
            Слой ячеек пуст: в файле нет ни одной ячейки.
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
            <span className="muted small">Слой не показан: выдавать непроверенные данные за доверенные нельзя.</span>
          </div>
        )}
        {gaps.kind === 'loading' && <p className="muted small">Разрывы наблюдений загружаются…</p>}
        {gaps.kind === 'ready' && gaps.geometries.length > 0 && (
          <p className="muted small" data-testid="lens-observation-gaps">
            Оранжевый пунктир — места, где две оптические даты сравнить нельзя. Это не доказательство того, что изменений не было.
          </p>
        )}
        {(gaps.kind === 'unavailable' || gaps.kind === 'integrity-failed') && (
          <div className={`state ${gaps.kind === 'integrity-failed' ? 'state-error' : 'state-warn'} compact`} role="status" data-testid="lens-gaps-unavailable">
            <strong>Слой разрывов наблюдений недоступен</strong>
            <span>{gaps.reason}</span>
            <span className="muted small">Остальные слои карты и сам результат сохранены.</span>
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
