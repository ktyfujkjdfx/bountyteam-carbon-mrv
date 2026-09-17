// @vitest-environment node
import { describe, expect, it } from 'vitest';
import httpExamples from '../../fixtures/http_examples.json';
import { resolveConfig, switchAdapterHref } from '../src/api/config';
import type { Plot } from '../src/api/types';
import { formatHa, formatRatio, formatUintString, formatUtc } from '../src/domain/format';
import {
  GeometryError,
  artifactBounds,
  boundsIntersect,
  geoJsonBounds,
  geometryBounds,
  sameBounds,
  toLeafletBounds,
} from '../src/domain/geo';

const plot = (httpExamples.cases.find((c) => c.name === 'plot')?.body ?? null) as unknown as Plot;

describe('geometry', () => {
  it('reads golden plot geometry as [longitude, latitude] and converts to Leaflet [lat, lon]', () => {
    const bounds = geometryBounds(plot.geometry);
    expect(bounds.minLon).toBeCloseTo(91.8714782, 6);
    expect(bounds.minLat).toBeCloseTo(56.2007891, 6);
    expect(toLeafletBounds(bounds)[0]).toEqual([bounds.minLat, bounds.minLon]);
  });

  it('detects swapped latitude/longitude order', () => {
    const swapped: Plot['geometry'] = {
      type: 'Polygon',
      coordinates: [
        [
          [56.2, 91.87],
          [56.2, 91.88],
          [56.21, 91.88],
          [56.2, 91.87],
        ],
      ],
    };
    expect(() => geometryBounds(swapped)).toThrow(GeometryError);
    expect(() => geoJsonBounds({ type: 'Point', coordinates: [41.1, 126.2] } as GeoJSON.Point)).toThrow(/перепутанный/);
  });

  it('handles MultiPolygon and FeatureCollection without simplifying area', () => {
    const multi: Plot['geometry'] = {
      type: 'MultiPolygon',
      coordinates: [
        [
          [
            [26.19, 41.11],
            [26.24, 41.11],
            [26.24, 41.15],
            [26.19, 41.11],
          ],
        ],
        [
          [
            [26.3, 41.2],
            [26.31, 41.2],
            [26.31, 41.21],
            [26.3, 41.2],
          ],
        ],
      ],
    };
    expect(geometryBounds(multi)).toEqual({ minLon: 26.19, minLat: 41.11, maxLon: 26.31, maxLat: 41.21 });
    const collection: GeoJSON.FeatureCollection = {
      type: 'FeatureCollection',
      features: [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [26.2, 41.12] } }],
    };
    expect(geoJsonBounds(collection)).toEqual({ minLon: 26.2, minLat: 41.12, maxLon: 26.2, maxLat: 41.12 });
    expect(geoJsonBounds({ type: 'FeatureCollection', features: [] } as GeoJSON.FeatureCollection)).toBeNull();
  });

  it('validates artifact bounds_wgs84 order and alignment', () => {
    const b = [91.8714782379942, 56.20078912424207, 91.88785656310161, 56.209918037389];
    const bounds = artifactBounds(b);
    expect(bounds && boundsIntersect(bounds, geometryBounds(plot.geometry))).toBe(true);
    expect(() => artifactBounds([91.88, 56.2, 91.87, 56.21])).toThrow(GeometryError);
    expect(artifactBounds(undefined)).toBeNull();
    expect(sameBounds(b, [...b])).toBe(true);
    expect(sameBounds(b, [91.8, 56.2, 91.88, 56.2])).toBe(false);
  });
});

describe('formatting', () => {
  it('keeps units and unknown values explicit', () => {
    expect(formatHa(null)).toBe('нет данных');
    expect(formatRatio(0.2)).toMatch(/20.*%/);
    expect(formatUtc('2024-08-01T05:00:00Z')).toBe('2024-08-01 05:00 UTC');
  });

  it('formats uint256 decimal strings without Number precision loss', () => {
    const huge = '115792089237316195423570985008687907853269984665640564039457584007913129639935';
    expect(formatUintString(huge).replace(/\D/g, '')).toBe(huge);
  });
});

describe('adapter configuration', () => {
  it('defaults to fixture only when env does not request http', () => {
    expect(resolveConfig({}, '').adapter).toBe('fixture');
    expect(resolveConfig({ VITE_API_MODE: 'http' }, '').adapter).toBe('http');
  });

  it('URL ?api= overrides env explicitly and visibly', () => {
    const config = resolveConfig({ VITE_API_MODE: 'http', VITE_API_BASE_URL: 'http://127.0.0.1:8000/api/v1' }, '?api=fixture');
    expect(config).toMatchObject({ adapter: 'fixture', source: 'url', baseUrl: 'http://127.0.0.1:8000/api/v1' });
    expect(resolveConfig({}, '?api=bogus').adapter).toBe('fixture');
  });

  it('builds a switch link preserving other query params', () => {
    expect(switchAdapterHref('fixture', { pathname: '/', search: '?api=http&x=1', hash: '#j' })).toBe('/?api=fixture&x=1#j');
  });
});
