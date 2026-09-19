// The offline set behind the same port as the live service: a stand-in, never a silent substitute.
// It is selected only by explicit configuration and says so in every result it returns.

import { LensError, type ArtifactPayload, type LensApiClient, type SubmitOptions } from './client';
import { caseSources, casePrices, parsedAreas, sampleRequests } from './data';
import { approximateAreaHa, validateGeometry } from './geometry';
import { buildCellsLayer, buildFixtureResult, scenarioNumbers, FIXTURE_SCENARIO_ORDER, type FixtureContext, type FixtureScenarioId } from './fixtures';
import { passportContent, sha256HexOfText } from './passport';
import type { Analysis, AnalysisAccepted, AnalysisRequestBody, AnalysisResult, AreaMeasurement, Artifact, Catalog, Geometry, Proof, Report } from './types';
import { LENS_MAX_AREA_HA, LENS_YEAR_MAX, LENS_YEAR_MIN } from './types';

export interface FixtureClientOptions {
  now?: () => number;
  queuedMs?: number;
  runningMs?: number;
  scenario?: FixtureScenarioId;
}

interface StoredAnalysis {
  analysis: Analysis;
  createdAt: number;
  result: AnalysisResult;
  artifacts: Map<string, { bytes: Uint8Array; mediaType: string }>;
  proof: Proof;
}

function textBytes(text: string): Uint8Array {
  return new TextEncoder().encode(text);
}

function isScenario(value: string | undefined): value is FixtureScenarioId {
  return value !== undefined && (FIXTURE_SCENARIO_ORDER as string[]).includes(value);
}

export function validateRequest(body: AnalysisRequestBody, areaHa: number): void {
  const { year_start: start, year_end: end } = body;
  if (!Number.isInteger(start) || !Number.isInteger(end)) throw new LensError('INVALID_PERIOD', 'Годы должны быть целыми числами');
  if (start < LENS_YEAR_MIN || end > LENS_YEAR_MAX) {
    throw new LensError('INVALID_PERIOD', `Период вне диапазона данных ${LENS_YEAR_MIN}–${LENS_YEAR_MAX}`, { status: 422 });
  }
  if (end <= start) throw new LensError('INVALID_PERIOD', 'Конечный год должен быть больше начального', { status: 422 });
  if (!(areaHa > 0)) throw new LensError('NON_POSITIVE_AREA', 'Площадь контура должна быть больше нуля', { status: 422 });
  if (areaHa > LENS_MAX_AREA_HA) {
    throw new LensError('AREA_TOO_LARGE', `Площадь ${areaHa.toFixed(1)} га превышает предел ${LENS_MAX_AREA_HA} га`, {
      status: 422,
      details: { area_ha: areaHa, max_area_ha: LENS_MAX_AREA_HA },
    });
  }
  if (body.claimed_units !== null && body.claimed_units !== undefined && (!Number.isFinite(body.claimed_units) || body.claimed_units < 0)) {
    throw new LensError('INVALID_CLAIM_VALUE', 'Заявленные единицы должны быть неотрицательным числом', { status: 422 });
  }
}

export function createFixtureLensClient(options: FixtureClientOptions = {}): LensApiClient & { setScenario: (id: FixtureScenarioId) => void } {
  const now = options.now ?? (() => Date.now());
  const queuedMs = options.queuedMs ?? 400;
  const runningMs = options.runningMs ?? 900;
  const analyses = new Map<string, StoredAnalysis>();
  const idempotency = new Map<string, string>();
  let scenario: FixtureScenarioId = options.scenario ?? 'DOC_EXAMPLE_Q395';
  let counter = 0;

  const settle = () => {
    const t = now();
    for (const stored of analyses.values()) {
      const state = stored.analysis.job_state;
      if (state === 'SUCCEEDED' || state === 'FAILED') continue;
      const elapsed = t - stored.createdAt;
      if (elapsed >= queuedMs + runningMs) {
        stored.analysis = {
          ...stored.analysis,
          job_state: 'SUCCEEDED',
          updated_at: new Date(t).toISOString(),
          result: stored.result,
          report_url: `/api/v2/analyses/${stored.analysis.analysis_id}/report`,
          proof_url: `/api/v2/analyses/${stored.analysis.analysis_id}/proof`,
        };
      } else if (elapsed >= queuedMs) {
        stored.analysis = { ...stored.analysis, job_state: 'RUNNING', updated_at: new Date(t).toISOString() };
      }
    }
  };

  const tick = async (signal?: AbortSignal) => {
    await Promise.resolve();
    if (signal?.aborted) throw new LensError('ABORTED', 'Запрос отменён');
    settle();
  };

  const find = (analysisId: string): StoredAnalysis => {
    const stored = analyses.get(analysisId);
    if (!stored) throw new LensError('NOT_FOUND', 'Расчёт не найден', { status: 404 });
    return stored;
  };

  return {
    kind: 'fixture',

    setScenario(id: FixtureScenarioId) {
      scenario = id;
    },

    async getCatalog(signal?: AbortSignal): Promise<Catalog> {
      await tick(signal);
      return {
        schema_version: 'carbon-lens-api/2.0.0',
        method_version: 'carbon-lens-frontend-offline-set/2.0.0',
        dataset_version: 'sr-data-case2/2026-09-16',
        dataset_hash: '0xd8723225a1f66f1ff1890439e6e561f3a28a94f6a81b63b5db99a73579fc22a8',
        year_min: LENS_YEAR_MIN,
        year_max: LENS_YEAR_MAX,
        max_area_ha: LENS_MAX_AREA_HA,
        raster_adapter: 'frontend-offline-set',
        carbon_adapter: 'frontend-offline-set',
        areas: parsedAreas(),
        sample_requests: sampleRequests(),
        prices: casePrices(),
        sources: caseSources().map((source) => ({
          source_id: source.source_id,
          product: source.product,
          version: source.version,
          license_url: source.license_url || null,
          attribution: source.attribution,
          access_date: source.accessed,
          role: 'reference',
        })),
      };
    },

    /**
     * The offline set knows the official area of a supplied contour and returns it verbatim; for a
     * contour drawn by hand it returns its own spherical estimate and labels it as an estimate.
     */
    async measureArea(geometry: Geometry, signal?: AbortSignal): Promise<AreaMeasurement> {
      await tick(signal);
      validateGeometry(geometry);
      const key = JSON.stringify(geometry.coordinates);
      for (const area of parsedAreas()) {
        if (JSON.stringify(area.geometry.coordinates) === key) {
          return { area_ha: area.area_ha, valid: true, max_area_ha: 2000, within_limit: area.area_ha <= 2000, geometry_hash: null, geometry, errors: [], source: 'SERVICE', note: 'Площадь участка из data/areas.csv.' };
        }
      }
      for (const sample of sampleRequests()) {
        if (JSON.stringify(sample.geometry.coordinates) === key) {
          return { area_ha: sample.area_ha, valid: true, max_area_ha: 2000, within_limit: sample.area_ha <= 2000, geometry_hash: null, geometry, errors: [], source: 'SERVICE', note: 'Площадь подучастка из data/sample_requests.geojson.' };
        }
      }
      return {
        area_ha: approximateAreaHa(geometry),
        valid: true,
        max_area_ha: 2000,
        within_limit: approximateAreaHa(geometry) <= 2000,
        geometry_hash: null,
        geometry,
        errors: [],
        source: 'CLIENT_ESTIMATE',
        note: 'Предварительная сферическая оценка офлайн-набора: геодезическую площадь считает сервис.',
      };
    },

    async createAnalysis(body: AnalysisRequestBody, options_: SubmitOptions): Promise<AnalysisAccepted> {
      await tick(options_.signal);
      if (isScenario(options_.scenario)) scenario = options_.scenario;

      const geometry = body.geometry ?? parsedAreas().find((area) => area.aoi_id === body.aoi_id)?.geometry ?? null;
      validateGeometry(geometry);
      const measured = await this.measureArea(geometry as Geometry);
      if (measured.area_ha === null) throw new LensError('INVALID_GEOMETRY', 'Площадь контура не рассчитана.');
      validateRequest(body, measured.area_ha);

      const existing = idempotency.get(options_.idempotencyKey);
      if (existing) {
        const stored = analyses.get(existing);
        if (stored) {
          const same = JSON.stringify(stored.result.request) === JSON.stringify({ ...stored.result.request });
          if (!same) throw new LensError('IDEMPOTENCY_CONFLICT', 'Ключ уже использован с другим запросом', { status: 409 });
          return {
            analysis_id: stored.analysis.analysis_id,
            job_state: stored.analysis.job_state,
            status_url: stored.analysis.status_url,
            created_at: stored.analysis.created_at,
          };
        }
      }

      counter += 1;
      const analysisId = `offline-${counter}-${Math.abs(hash(options_.idempotencyKey)).toString(16)}`;
      const createdAt = new Date(now()).toISOString();
      const context: FixtureContext = {
        scenario,
        analysisId,
        geometry: geometry as Geometry,
        aoiId: body.aoi_id ?? null,
        areaHa: measured.area_ha,
        yearStart: body.year_start,
        yearEnd: body.year_end,
        claimedUnits: body.claimed_units ?? null,
        claimOrigin: body.claim_origin ?? (body.claimed_units === null || body.claimed_units === undefined ? null : 'USER_INPUT'),
        geometryHash: `0x${Math.abs(hash(JSON.stringify(geometry))).toString(16).padStart(64, '0').slice(0, 64)}`,
        createdAt,
      };

      const cells = buildCellsLayer(context, scenarioNumbers(context.scenario));
      const cellsText = JSON.stringify(cells.geojson);
      const cellsHash = (await sha256HexOfText(cellsText)) ?? '0x00';
      const cellsArtifact: Artifact = {
        artifact_id: `cells-${cellsHash.slice(2, 14)}`,
        role: 'cci_cell_layer',
        media_type: 'application/geo+json',
        sha256: cellsHash,
        size_bytes: textBytes(cellsText).byteLength,
        url: `/api/v2/analyses/${analysisId}/artifacts/cells-${cellsHash.slice(2, 14)}`,
        bbox_wgs84: null,
        crs: 'EPSG:4326',
        resolution: null,
        resolution_units: null,
        unit: 'т C/га',
        provenance: 'STUB_FIXTURE',
      };

      const built = buildFixtureResult(context, { cellsArtifact });
      const zonesDocument = {
        type: 'FeatureCollection',
        name: 'change_zones',
        features: built.zones.filter((zone) => zone.geometry).map((zone) => ({
          type: 'Feature', geometry: zone.geometry, properties: {
            zone_id: zone.zone_id, fact: zone.fact, cause: zone.cause,
            cause_reason: zone.cause_reason, severity: 'FIXTURE',
            evidence_events: [], event_date_range: zone.date_range,
            observed_between: { start: `${context.yearStart}-01-01`, end: `${context.yearEnd}-12-31` },
            detected_area_ha: zone.area_ha, cci_overlap_ha: zone.carbon_overlap_ha,
            delta_tc: zone.delta_carbon_tc, contribution_tco2e: zone.contribution_e_tco2e,
            detection_resolution_m: 20, evidence: zone.evidence,
          },
        })),
      };
      const zonesText = JSON.stringify(zonesDocument);
      const zonesHash = (await sha256HexOfText(zonesText)) ?? '0x00';
      const zonesArtifact: Artifact = {
        artifact_id: `zones-${zonesHash.slice(2, 14)}`,
        role: 'change_zones', media_type: 'application/geo+json', sha256: zonesHash,
        size_bytes: textBytes(zonesText).byteLength,
        url: `/api/v2/analyses/${analysisId}/artifacts/zones-${zonesHash.slice(2, 14)}`,
        bbox_wgs84: null, crs: 'EPSG:4326', resolution: [20, 20],
        resolution_units: 'm', unit: 'ha; t CO2e', provenance: 'STUB_FIXTURE',
      };
      const withoutPassport = {
        ...built,
        zones: built.zones.map((zone) => ({ ...zone, artifact_ref: zonesArtifact.artifact_id })),
        artifacts: [cellsArtifact, zonesArtifact],
      };
      const contentHash = (await sha256HexOfText(passportContent(withoutPassport as AnalysisResult))) ?? '0x00';
      const result: AnalysisResult = {
        ...withoutPassport,
        passport: {
          status: 'DRAFT',
          finalized_at: null,
          content_hash: contentHash,
          report_hash: null,
          previous_hash: null,
          comparison_scope: 'geometry_hash+year_start+year_end+pool+method_version',
          comparison_result: 'INITIAL',
          comparison_direction: 'NOT_COMPARED',
          comparison_note: 'Первое наблюдение в этой области сравнения.',
          created_at: createdAt,
        },
      };
      const reportHash = (await sha256HexOfText(JSON.stringify({ report: 'carbon-lens-report/2.0.0', content: passportContent(result) }))) ?? '0x00';
      result.passport = { ...result.passport, report_hash: reportHash };

      const analysis: Analysis = {
        analysis_id: analysisId,
        job_state: 'QUEUED',
        created_at: createdAt,
        updated_at: createdAt,
        attempts: 1,
        status_url: `/api/v2/analyses/${analysisId}`,
        report_url: null,
        proof_url: null,
        error: null,
        result: null,
      };

      const proof: Proof = {
        analysis_id: analysisId,
        identity: result.identity,
        passport: result.passport,
        canonical_url: `/api/v2/analyses/${analysisId}/report?format=json`,
        report_urls: {
          json: `/api/v2/analyses/${analysisId}/report?format=json`,
          html: `/api/v2/analyses/${analysisId}/report?format=html`,
        },
        artifacts: result.artifacts,
        anchor: {
          status: 'NOT_REQUESTED',
          deployment_id: null,
          tx_hash: null,
          anchored_at: null,
          note: 'Хеш выявляет изменение файла относительно доверенной фиксации. Он не предотвращает двойную продажу и не удостоверяет истинность расчёта. Запись в блокчейн не запрашивалась.',
        },
        verification_note: 'Проверка целостности сравнивает хеш содержимого с зафиксированным значением.',
      };

      analyses.set(analysisId, {
        analysis,
        createdAt: now(),
        result,
        artifacts: new Map([
          [cellsArtifact.artifact_id, { bytes: textBytes(cellsText), mediaType: cellsArtifact.media_type }],
          [zonesArtifact.artifact_id, { bytes: textBytes(zonesText), mediaType: zonesArtifact.media_type }],
        ]),
        proof,
      });
      idempotency.set(options_.idempotencyKey, analysisId);
      return { analysis_id: analysisId, job_state: 'QUEUED', status_url: analysis.status_url, created_at: createdAt };
    },

    async getAnalysis(analysisId: string, signal?: AbortSignal): Promise<Analysis> {
      await tick(signal);
      return structuredClone(find(analysisId).analysis);
    },

    async getProof(analysisId: string, signal?: AbortSignal): Promise<Proof> {
      await tick(signal);
      return structuredClone(find(analysisId).proof);
    },

    async getReport(analysisId: string, _format: 'json', signal?: AbortSignal): Promise<Report> {
      await tick(signal);
      const stored = find(analysisId);
      return {
        schema_version: 'carbon-lens-report/2.0.0',
        generated_at: new Date(now()).toISOString(),
        report_hash: stored.result.passport.report_hash ?? '0x00',
        result: structuredClone(stored.result),
      };
    },

    async getReportHtml(analysisId: string, signal?: AbortSignal): Promise<string> {
      await tick(signal);
      const { renderReportHtml } = await import('./passport');
      return renderReportHtml(find(analysisId).result);
    },

    async getArtifact(artifact: Artifact, signal?: AbortSignal): Promise<ArtifactPayload> {
      await tick(signal);
      for (const stored of analyses.values()) {
        const found = stored.artifacts.get(artifact.artifact_id);
        if (!found) continue;
        const text = new TextDecoder().decode(found.bytes);
        const computed = await sha256HexOfText(text);
        const integrity = computed === null ? 'UNVERIFIABLE' : computed === artifact.sha256 ? 'VERIFIED' : 'MISMATCH';
        return {
          kind: 'geojson',
          mediaType: found.mediaType,
          src: null,
          data: integrity === 'MISMATCH' ? null : (JSON.parse(text) as unknown),
          integrity,
          computed_sha256: computed,
          release: () => undefined,
        };
      }
      throw new LensError('NOT_FOUND', 'Артефакт не найден', { status: 404 });
    },
  };
}

function hash(text: string): number {
  let value = 0;
  for (let i = 0; i < text.length; i += 1) {
    value = (value * 31 + text.charCodeAt(i)) | 0;
  }
  return value;
}
