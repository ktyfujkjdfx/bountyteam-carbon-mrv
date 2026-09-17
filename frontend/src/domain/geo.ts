import type { Plot } from '../api/types';

export interface LonLatBounds {
  minLon: number;
  minLat: number;
  maxLon: number;
  maxLat: number;
}

export type LeafletBoundsTuple = [[number, number], [number, number]];

export class GeometryError extends Error {
  override name = 'GeometryError';
}

function assertPosition(position: readonly number[], where: string): void {
  const [lon, lat] = position;
  if (position.length !== 2 || typeof lon !== 'number' || typeof lat !== 'number' || !Number.isFinite(lon) || !Number.isFinite(lat)) {
    throw new GeometryError(`${where}: позиция должна быть [longitude, latitude]`);
  }
  if (Math.abs(lat) > 90 && Math.abs(lon) <= 90) {
    throw new GeometryError(`${where}: похоже на перепутанный порядок [latitude, longitude] (${lon}, ${lat})`);
  }
  if (lon < -180 || lon > 180 || lat < -90 || lat > 90) {
    throw new GeometryError(`${where}: координата вне диапазона EPSG:4326 (${lon}, ${lat})`);
  }
}

function extend(bounds: LonLatBounds | null, lon: number, lat: number): LonLatBounds {
  if (!bounds) return { minLon: lon, minLat: lat, maxLon: lon, maxLat: lat };
  return {
    minLon: Math.min(bounds.minLon, lon),
    minLat: Math.min(bounds.minLat, lat),
    maxLon: Math.max(bounds.maxLon, lon),
    maxLat: Math.max(bounds.maxLat, lat),
  };
}

export function plotRings(geometry: Plot['geometry']): number[][][] {
  return geometry.type === 'Polygon' ? geometry.coordinates : geometry.coordinates.flat();
}

export function geometryBounds(geometry: Plot['geometry']): LonLatBounds {
  let bounds: LonLatBounds | null = null;
  for (const ring of plotRings(geometry)) {
    if (ring.length < 4) throw new GeometryError('Кольцо полигона должно содержать ≥ 4 позиций');
    for (const position of ring) {
      assertPosition(position, 'geometry');
      bounds = extend(bounds, position[0] as number, position[1] as number);
    }
  }
  if (!bounds) throw new GeometryError('Пустая геометрия участка');
  return bounds;
}

export function geoJsonBounds(data: GeoJSON.GeoJsonObject): LonLatBounds | null {
  let bounds: LonLatBounds | null = null;
  const visit = (coords: unknown): void => {
    if (!Array.isArray(coords)) return;
    if (coords.length >= 2 && typeof coords[0] === 'number' && typeof coords[1] === 'number') {
      assertPosition(coords as number[], 'GeoJSON');
      bounds = extend(bounds, coords[0], coords[1]);
      return;
    }
    for (const child of coords) visit(child);
  };
  const walk = (node: GeoJSON.GeoJsonObject | null): void => {
    if (!node) return;
    if (node.type === 'FeatureCollection') (node as GeoJSON.FeatureCollection).features.forEach((f) => walk(f));
    else if (node.type === 'Feature') walk((node as GeoJSON.Feature).geometry);
    else if (node.type === 'GeometryCollection') (node as GeoJSON.GeometryCollection).geometries.forEach((g) => walk(g));
    else visit((node as GeoJSON.Point).coordinates);
  };
  walk(data);
  return bounds;
}

export function artifactBounds(bounds: readonly number[] | undefined): LonLatBounds | null {
  if (!bounds || bounds.length !== 4) return null;
  const [minLon, minLat, maxLon, maxLat] = bounds as [number, number, number, number];
  assertPosition([minLon, minLat], 'bounds_wgs84');
  assertPosition([maxLon, maxLat], 'bounds_wgs84');
  if (minLon > maxLon || minLat > maxLat) throw new GeometryError('bounds_wgs84 должен быть [minLon, minLat, maxLon, maxLat]');
  return { minLon, minLat, maxLon, maxLat };
}

export function toLeafletBounds(bounds: LonLatBounds): LeafletBoundsTuple {
  return [
    [bounds.minLat, bounds.minLon],
    [bounds.maxLat, bounds.maxLon],
  ];
}

export function boundsIntersect(a: LonLatBounds, b: LonLatBounds): boolean {
  return a.minLon <= b.maxLon && b.minLon <= a.maxLon && a.minLat <= b.maxLat && b.minLat <= a.maxLat;
}

export function sameBounds(a: readonly number[] | undefined, b: readonly number[] | undefined): boolean {
  if (!a || !b || a.length !== 4 || b.length !== 4) return false;
  return a.every((value, index) => Math.abs(value - (b[index] as number)) < 1e-9);
}
