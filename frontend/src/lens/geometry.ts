// Geometry helpers shared by both clients. The spherical area here is a preview only: the
// authoritative area is the geodesic one the service returns (METHOD FREEZE v1, item 13).

import { LensError } from './client';
import type { Geometry } from './types';

export function rings(geometry: Geometry): number[][][] {
  return geometry.type === 'Polygon' ? geometry.coordinates : geometry.coordinates.flat();
}

export function bboxOf(geometry: Geometry): { west: number; south: number; east: number; north: number } | null {
  const points = rings(geometry).flat();
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const point of points) {
    const [lon, lat] = point;
    if (typeof lon !== 'number' || typeof lat !== 'number') continue;
    west = Math.min(west, lon);
    east = Math.max(east, lon);
    south = Math.min(south, lat);
    north = Math.max(north, lat);
  }
  return Number.isFinite(west) && Number.isFinite(south) ? { west, south, east, north } : null;
}

export function box(west: number, south: number, east: number, north: number): Geometry {
  return {
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
  };
}

/** Spherical polygon area in hectares — a preview of the geodesic area the service computes. */
export function approximateAreaHa(geometry: Geometry): number {
  const R = 6378137;
  let total = 0;
  for (const ring of rings(geometry)) {
    let sum = 0;
    for (let i = 0; i < ring.length - 1; i += 1) {
      const [lon1 = 0, lat1 = 0] = ring[i] ?? [];
      const [lon2 = 0, lat2 = 0] = ring[i + 1] ?? [];
      sum += (((lon2 - lon1) * Math.PI) / 180) * (2 + Math.sin((lat1 * Math.PI) / 180) + Math.sin((lat2 * Math.PI) / 180));
    }
    total += Math.abs((sum * R * R) / 2);
  }
  return total / 10_000;
}

function segmentsIntersect(a: number[], b: number[], c: number[], d: number[]): boolean {
  const cross = (p: number[], q: number[], r: number[]) =>
    ((q[0] ?? 0) - (p[0] ?? 0)) * ((r[1] ?? 0) - (p[1] ?? 0)) - ((q[1] ?? 0) - (p[1] ?? 0)) * ((r[0] ?? 0) - (p[0] ?? 0));
  const d1 = cross(c, d, a);
  const d2 = cross(c, d, b);
  const d3 = cross(a, b, c);
  const d4 = cross(a, b, d);
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
}

/**
 * Reject a contour the service would reject anyway, with the reason the user needs: an empty ring,
 * coordinates outside WGS84, or an outline that crosses itself. A generic "что-то пошло не так" is
 * never an acceptable answer to a fixable geometry problem.
 */
export function validateGeometry(geometry: Geometry | null): void {
  if (!geometry) throw new LensError('GEOMETRY_MISSING', 'Контур не задан: выберите участок, нарисуйте его или импортируйте GeoJSON.');
  // Pasted GeoJSON reaches this function before anything has confirmed its type tag, so the tag is
  // read as a plain string: the static type admits only two values, and the whole point here is to
  // catch the value that arrived claiming to be one of them.
  const tag: string = geometry.type;
  if (tag !== 'Polygon' && tag !== 'MultiPolygon') {
    throw new LensError('GEOMETRY_TYPE', `Поддерживаются только Polygon и MultiPolygon, получено «${tag}».`);
  }
  const allRings = rings(geometry);
  if (allRings.length === 0 || allRings.every((ring) => ring.length === 0)) {
    throw new LensError('GEOMETRY_EMPTY', 'Контур пуст: в нём нет ни одной вершины.');
  }
  for (const ring of allRings) {
    if (ring.length < 4) {
      throw new LensError('GEOMETRY_TOO_FEW_POINTS', 'В контуре меньше трёх вершин: замкнутый многоугольник построить нельзя.');
    }
    for (const point of ring) {
      const [lon, lat] = point;
      if (typeof lon !== 'number' || typeof lat !== 'number' || !Number.isFinite(lon) || !Number.isFinite(lat)) {
        throw new LensError('GEOMETRY_NOT_NUMERIC', 'В координатах контура есть нечисловые значения.');
      }
      if (lon < -180 || lon > 180 || lat < -90 || lat > 90) {
        throw new LensError(
          'GEOMETRY_CRS',
          `Координаты вне WGS84 (${lon.toFixed(1)}, ${lat.toFixed(1)}). Ожидаются градусы долготы и широты, а не метры проекции.`,
        );
      }
    }
    const first = ring[0];
    const last = ring[ring.length - 1];
    if (first && last && (first[0] !== last[0] || first[1] !== last[1])) {
      throw new LensError('GEOMETRY_NOT_CLOSED', 'Контур не замкнут: первая и последняя вершины различаются.');
    }
    for (let i = 0; i < ring.length - 1; i += 1) {
      for (let j = i + 2; j < ring.length - 1; j += 1) {
        if (i === 0 && j === ring.length - 2) continue;
        const a = ring[i];
        const b = ring[i + 1];
        const c = ring[j];
        const d = ring[j + 1];
        if (a && b && c && d && segmentsIntersect(a, b, c, d)) {
          throw new LensError('GEOMETRY_SELF_INTERSECTION', 'Контур пересекает сам себя: исправьте вершины и повторите.');
        }
      }
    }
  }
}

export function extractGeometry(text: string): Geometry {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new LensError('GEOMETRY_NOT_JSON', `Это не JSON: ${error instanceof Error ? error.message : String(error)}`);
  }
  const node = parsed as { type?: string; geometry?: Geometry; features?: Array<{ geometry?: Geometry }> };
  if (node.type === 'FeatureCollection') {
    const geometry = node.features?.[0]?.geometry;
    if (!geometry) throw new LensError('GEOMETRY_EMPTY', 'В FeatureCollection нет геометрии.');
    return geometry;
  }
  if (node.type === 'Feature') {
    if (!node.geometry) throw new LensError('GEOMETRY_EMPTY', 'В Feature нет геометрии.');
    return node.geometry;
  }
  if (node.type === 'Polygon' || node.type === 'MultiPolygon') return parsed as Geometry;
  throw new LensError('GEOMETRY_TYPE', 'Ожидается Polygon, MultiPolygon, Feature или FeatureCollection.');
}
