import { describe, expect, it } from 'vitest';
import {
  baselineForAoi,
  baselineStockAtYear,
  caseEvents,
  caseParameters,
  casePrices,
  caseScenes,
  caseSources,
  eventById,
  eventsForAoi,
  parameterValue,
  scenesInPeriod,
  sourcesByIds,
} from '../src/lens/data';

// These assertions pin the official archive: if data/ changes, the UI must not silently keep old numbers.

describe('official case tables are read as published', () => {
  it('reads Sentinel-2 scenes with cloud share and SCL validity', () => {
    const scenes = caseScenes();
    expect(scenes.length).toBeGreaterThan(40);
    const scene = scenes.find((entry) => entry.item_id === 'S2B_38ULF_20190814_1_L2A');
    expect(scene?.aoi_id).toBe('RU_MORDOVIA_03');
    expect(scene?.source_scene_cloud_percent).toBeCloseTo(15.3151, 3);
    expect(scene?.scl_valid_fraction).toBeCloseTo(0.999815, 5);
    expect(scene?.year).toBe(2019);
  });

  it('limits scenes to the requested period', () => {
    const scenes = scenesInPeriod('RU_MORDOVIA_03', 2021, 2022);
    expect(scenes.length).toBeGreaterThan(0);
    expect(scenes.every((scene) => scene.year >= 2021 && scene.year <= 2022)).toBe(true);
    expect(scenesInPeriod(null, 2019, 2024)).toEqual([]);
  });

  it('reads the MODIS fire event rows with their stated uncertainty', () => {
    const event = eventById('RU_MORDOVIA_03_MODIS_FIRE_202108');
    expect(event?.date_min_product).toBe('2021-08-05');
    expect(event?.date_max_product).toBe('2021-08-22');
    expect(event?.burned_pixel_centers_in_aoi).toBe(60);
    expect(event?.all_pixel_centers_in_aoi).toBe(88);
    expect(event?.date_uncertainty_days_max).toBe(7);
    expect(event?.limitations).toMatch(/Точный контур пожара/);
    expect(caseEvents()).toHaveLength(2);
  });

  it('reports no event rows for areas without them instead of inventing one', () => {
    expect(eventsForAoi('RU_VOLOGDA_02')).toEqual([]);
    expect(eventsForAoi('RU_TVER_01')).toEqual([]);
    expect(eventById(null)).toBeNull();
  });

  it('reads the baseline table without interpolating between rows', () => {
    const rows = baselineForAoi('RU_TVER_01');
    expect(rows.length).toBeGreaterThan(0);
    expect(rows[0]?.historical_rate_tc_ha_yr).toBeCloseTo(0.343749779, 6);
    expect(baselineStockAtYear('RU_TVER_01', 2019)).toBeCloseTo(85.127113698, 6);
    expect(baselineStockAtYear('RU_TVER_01', 1999)).toBeNull();
  });

  it('takes prices and coefficients from parameters.csv, never from the UI', () => {
    expect(casePrices().map((price) => price.rub_per_unit)).toEqual([500, 1500, 4000]);
    expect(parameterValue('CF_AGB')?.value).toBe('0.47');
    expect(parameterValue('UNC_allowance')?.value).toBe('0.10');
    expect(parameterValue('BUF')?.value).toBe('0.15');
    expect(parameterValue('UNC_stop_ratio')?.value).toBe('1.0');
    expect(caseParameters().length).toBeGreaterThan(10);
  });

  it('carries licences and attribution for every source it shows', () => {
    const sources = caseSources();
    expect(sources.length).toBeGreaterThan(5);
    for (const source of sources) {
      expect(source.attribution.length).toBeGreaterThan(0);
      expect(source.accessed).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    }
    const modis = sourcesByIds(['MODIS_MCD64A1_061'])[0];
    expect(modis?.doi).toBe('10.5067/MODIS/MCD64A1.061');
    expect(modis?.limitations).toMatch(/463/);
  });
});
