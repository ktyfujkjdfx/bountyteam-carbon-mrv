import { useCallback, useMemo, useRef, useState } from 'react';
import { useResource } from '../hooks/useResource';
import { LensError, type LensApiClient } from './client';
import { approximateAreaHa, validateGeometry } from './geometry';
import { renderReportHtml } from './passport';
import { useAnalysis } from './useAnalysis';
import type { CellFeature, CellsState } from './components/LensMapView';
import type { PriceKey } from './components/Headline';
import type { RequestDraft } from './components/RequestForm';
import type { AnalysisResult, AreaMeasurement, Catalog, Geometry, Proof } from './types';
import {
  loadSubmissions,
  newSubmission,
  recordStep,
  saveSubmissions,
  type LifecycleStep,
  type Submission,
} from './workspace';

const EMPTY_DRAFT: RequestDraft = {
  aoiId: null,
  geometry: null,
  geometrySource: 'контур не задан',
  yearStart: 2019,
  yearEnd: 2024,
  claimedUnits: '',
};

function cellsFromGeoJson(data: unknown): CellFeature[] {
  const collection = data as { features?: Array<{ geometry?: Geometry; properties?: Record<string, unknown> }> };
  return (collection.features ?? [])
    .map((feature) => {
      const props = feature.properties ?? {};
      const carbon = (props.carbon_tc_ha ?? props.agb_t_ha ?? {}) as Record<string, number | null>;
      const sd = (props.sd_tc_ha ?? props.agb_sd_t_ha ?? {}) as Record<string, number | null>;
      if (!feature.geometry) return null;
      return {
        cell_id: String(props.cell_id ?? 'без идентификатора'),
        zone_id: props.zone_id === undefined || props.zone_id === null ? null : String(props.zone_id),
        valid: props.valid !== false,
        weight_ha: typeof props.weight_ha === 'number' ? props.weight_ha : null,
        carbon,
        sd,
        geometry: feature.geometry,
      } satisfies CellFeature;
    })
    .filter((cell): cell is CellFeature => cell !== null);
}

/**
 * Everything the three workspaces share: the catalog, the contour being measured, the analysis in
 * flight, the submissions of this session and the cells layer of the shown result.
 */
export function useWorkspace(client: LensApiClient, actorEmail: string) {
  const catalogResource = useResource<Catalog>((signal) => client.getCatalog(signal), [client]);
  const catalog = catalogResource.data;
  const catalogLoading = catalogResource.loading;
  const catalogError = catalogResource.error ? catalogResource.error.message : null;

  const [draft, setDraft] = useState<RequestDraft>(EMPTY_DRAFT);
  const [drawing, setDrawing] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);

  const [submissions, setSubmissions] = useState<Submission[]>(() => loadSubmissions());
  const submissionsRef = useRef<Submission[]>(submissions);
  const [activeSubmissionId, setActiveSubmissionId] = useState<string | null>(() => loadSubmissions()[0]?.submission_id ?? null);

  const [priceKey, setPriceKey] = useState<PriceKey>('base');
  const [customPrice, setCustomPrice] = useState<number | null>(null);
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null);
  const [selectedCellId, setSelectedCellId] = useState<string | null>(null);
  const [cells, setCells] = useState<CellsState>({ kind: 'hidden' });
  const [proof, setProof] = useState<Proof | null>(null);

  const analysis = useAnalysis(client);

  // A contour is checked in the browser before anything is sent, so a fixable mistake gets its own
  // message instead of a generic failure from the service.
  const geometry = draft.geometry;
  const geometryError = useMemo(() => {
    if (!geometry) return null;
    try {
      validateGeometry(geometry);
      return null;
    } catch (error) {
      return error instanceof LensError ? error.message : String(error);
    }
  }, [geometry]);

  // The area itself always comes from the service, including for a contour drawn by hand.
  const measureResource = useResource<AreaMeasurement>(geometry && !geometryError ? (signal) => client.measureArea(geometry, signal) : null, [client, geometry, geometryError]);
  const measuring = measureResource.loading;
  const measurement = useMemo(() => {
    if (!geometry || geometryError) return null;
    if (measureResource.data) return measureResource.data;
    const area = approximateAreaHa(geometry);
    return {
      area_ha: area,
      valid: true,
      max_area_ha: catalog?.max_area_ha ?? 2000,
      within_limit: area <= (catalog?.max_area_ha ?? 2000),
      geometry_hash: null,
      geometry,
      errors: [],
      source: 'CLIENT_ESTIMATE' as const,
      note: 'Предварительная сферическая оценка в браузере; отправка ждёт ответ сервиса.',
    };
  }, [catalog?.max_area_ha, geometry, geometryError, measureResource.data]);
  const measurementErrors = measureResource.data?.errors.map((item) => item.message).join(' ') || null;
  const measureError = geometryError ?? measurementErrors ?? (measureResource.error ? measureResource.error.message : null);

  const persist = useCallback((next: Submission[]) => {
    submissionsRef.current = next;
    saveSubmissions(next);
    setSubmissions(next);
  }, []);

  const activeSubmission = useMemo(
    () => submissions.find((item) => item.submission_id === activeSubmissionId) ?? null,
    [submissions, activeSubmissionId],
  );

  const shownResult: AnalysisResult | null = activeSubmission?.result ?? analysis.state.result;

  const submitRequest = useCallback(
    (title: string) => {
      setRequestError(null);
      if (!draft.geometry) {
        setRequestError('Контур не задан: выберите участок, нарисуйте его или импортируйте GeoJSON.');
        return null;
      }
      const acceptedMeasurement = measureResource.data ?? (client.kind === 'fixture' ? measurement : null);
      if (!acceptedMeasurement || !acceptedMeasurement.valid || !acceptedMeasurement.within_limit ||
          acceptedMeasurement.area_ha === null || !acceptedMeasurement.geometry) {
        setRequestError('Дождитесь корректного измерения контура сервисом и исправьте указанные ошибки.');
        return null;
      }
      if (draft.yearEnd <= draft.yearStart) {
        setRequestError('Конечный год должен быть больше начального.');
        return null;
      }
      const claimed = draft.claimedUnits.trim();
      if (claimed !== '' && (!Number.isFinite(Number(claimed)) || Number(claimed) < 0)) {
        setRequestError('Заявленный объём должен быть неотрицательным числом.');
        return null;
      }
      const submission = newSubmission({
        owner_email: actorEmail,
        title,
        aoi_id: draft.aoiId,
        geometry: acceptedMeasurement.geometry,
        geometry_hash: acceptedMeasurement.geometry_hash,
        year_start: draft.yearStart,
        year_end: draft.yearEnd,
        claimed_units: claimed === '' ? null : Number(claimed),
      });
      persist([submission, ...submissionsRef.current]);
      setActiveSubmissionId(submission.submission_id);
      return submission;
    },
    [actorEmail, client.kind, draft, measureResource.data, measurement, persist],
  );

  const runAnalysis = useCallback(
    async (submission: Submission, scenario?: string) => {
      setSelectedZoneId(null);
      setSelectedCellId(null);
      setCells({ kind: 'hidden' });
      setProof(null);
      const result = await analysis.run(
        {
          aoi_id: submission.aoi_id,
          geometry: submission.geometry,
          year_start: submission.year_start,
          year_end: submission.year_end,
          claimed_units: submission.claimed_units,
          claim_origin: submission.claimed_units === null ? null : 'USER_INPUT',
          claim_scope: submission.claimed_units === null || submission.geometry_hash === null
            ? null
            : {
                geometry_hash: submission.geometry_hash,
                year_start: submission.year_start,
                year_end: submission.year_end,
                pool: 'AGB_LIVE_WOODY',
                unit: 'POTENTIAL_UNIT_OF_THE_CASE',
              },
        },
        scenario,
      );
      if (!result) return null;
      if (submission.geometry_hash && result.identity.geometry_hash !== submission.geometry_hash) {
        throw new LensError('GEOMETRY_HASH_MISMATCH', 'Сервис рассчитал другой нормализованный контур; результат не принят.');
      }
      const updated: Submission = {
        ...submission,
        status: submission.status === 'FINALIZED' ? 'FINALIZED' : 'CALCULATED',
        analysis_id: analysis.state.analysis?.analysis_id ?? result.identity.analysis_id,
        result,
        updated_at: new Date().toISOString(),
      };
      persist(submissionsRef.current.map((item) => (item.submission_id === submission.submission_id ? recordStep(updated, 'CALCULATION', actorEmail) : item)));
      setActiveSubmissionId(submission.submission_id);
      const id = updated.analysis_id;
      if (id) {
        client
          .getProof(id)
          .then(setProof)
          .catch(() => setProof(null));
      }
      return result;
    },
    [actorEmail, analysis, client, persist],
  );

  const showCells = useCallback(async () => {
    const result = shownResult;
    const artifact = result?.artifacts.find((item) => item.role === 'cells') ?? null;
    if (!result || !artifact) {
      setCells({ kind: 'unavailable', reason: 'Сервис не приложил к этому результату слой ячеек.' });
      return;
    }
    setCells({ kind: 'loading' });
    try {
      const payload = await client.getArtifact(artifact);
      if (payload.integrity === 'MISMATCH') {
        setCells({ kind: 'integrity-failed', reason: `Хеш файла не совпал с заявленным ${artifact.sha256.slice(0, 18)}…` });
        return;
      }
      const parsed = cellsFromGeoJson(payload.data);
      setCells(parsed.length === 0 ? { kind: 'empty' } : { kind: 'ready', cells: parsed });
    } catch (error) {
      setCells({
        kind: 'unavailable',
        reason: error instanceof LensError ? `${error.code}: ${error.message}` : String(error),
      });
    }
  }, [client, shownResult]);

  const finalize = useCallback(
    (submission: Submission, verifier: string) => {
      const updated = recordStep(
        { ...submission, status: 'FINALIZED', finalized_by: verifier, finalized_at: new Date().toISOString() },
        'VERIFICATION',
        verifier,
      );
      persist(submissionsRef.current.map((item) => (item.submission_id === submission.submission_id ? updated : item)));
    },
    [persist],
  );

  const addNote = useCallback(
    (submission: Submission, author: string, text: string) => {
      const note = { note_id: `note-${Math.random().toString(36).slice(2, 8)}`, created_at: new Date().toISOString(), author, text };
      const updated = { ...submission, notes: [...submission.notes, note], updated_at: note.created_at };
      persist(submissionsRef.current.map((item) => (item.submission_id === submission.submission_id ? updated : item)));
    },
    [persist],
  );

  const markIntegrityFailed = useCallback(
    (submission: Submission) => {
      const updated: Submission = { ...submission, status: 'INTEGRITY_FAILED', updated_at: new Date().toISOString() };
      persist(submissionsRef.current.map((item) => (item.submission_id === submission.submission_id ? updated : item)));
    },
    [persist],
  );

  const recordLifecycle = useCallback(
    (submission: Submission, step: LifecycleStep, by: string) => {
      const updated = recordStep(submission, step, by);
      persist(submissionsRef.current.map((item) => (item.submission_id === submission.submission_id ? updated : item)));
    },
    [persist],
  );

  const downloadReport = useCallback(() => {
    const result = shownResult;
    if (!result) return;
    const html = renderReportHtml(result);
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `carbon-lens-${result.identity.input_hash.slice(2, 14)}.html`;
    link.click();
    URL.revokeObjectURL(url);
  }, [shownResult]);

  return {
    catalog,
    catalogLoading,
    catalogError,
    draft,
    setDraft,
    measurement,
    measuring,
    measureError,
    drawing,
    setDrawing,
    requestError,
    setRequestError,
    submissions,
    activeSubmission,
    setActiveSubmissionId,
    analysis,
    shownResult,
    proof,
    priceKey,
    setPriceKey,
    customPrice,
    setCustomPrice,
    selectedZoneId,
    setSelectedZoneId,
    selectedCellId,
    setSelectedCellId,
    cells,
    showCells,
    submitRequest,
    runAnalysis,
    finalize,
    addNote,
    markIntegrityFailed,
    recordLifecycle,
    downloadReport,
  };
}

export type WorkspaceState = ReturnType<typeof useWorkspace>;
