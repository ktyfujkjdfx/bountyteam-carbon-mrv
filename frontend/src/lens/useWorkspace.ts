import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useResource } from '../hooks/useResource';
import type { Notify } from './notify';
import { LensError, type CreateVerificationRequest, type LensApiClient, type VerificationRequest } from './client';
import { approximateAreaHa, validateGeometry } from './geometry';
import { renderReportHtml } from './passport';
import { useAnalysis } from './useAnalysis';
import type { CellFeature, CellsState, GapLayerState } from './components/LensMapView';
import { SNAPSHOT_ROLES, type SnapshotImage, type SnapshotsState } from './components/Snapshots';
import type { PriceKey } from './components/Headline';
import type { RequestDraft } from './components/RequestForm';
import type { AnalysisResult, AreaMeasurement, Artifact, Catalog, Geometry, Proof, Zone } from './types';
import {
  loadSubmissions,
  newSubmission,
  recordStep,
  saveSubmissions,
  type LifecycleStep,
  type LifecycleEntry,
  type Submission,
  type SubmissionStatus,
} from './workspace';

const EMPTY_DRAFT: RequestDraft = {
  aoiId: null,
  geometry: null,
  geometrySource: 'контур не задан',
  yearStart: 2019,
  yearEnd: 2024,
  claimedUnits: '',
};

/**
 * Every state the service publishes, mapped one to one. Collapsing them loses the one that matters
 * most on screen: a request the service is calculating would otherwise be indistinguishable from
 * one waiting for a verifier, and the queue would offer a second run the service answers with 409.
 */
const SERVER_STATUS: Readonly<Record<string, SubmissionStatus>> = {
  DRAFT: 'DRAFT',
  SUBMITTED: 'SUBMITTED',
  ANALYSING: 'ANALYSING',
  CALCULATED: 'CALCULATED',
  FINALIZED: 'FINALIZED',
};

function serverSubmission(request: VerificationRequest, result: AnalysisResult | null): Submission {
  // A state this client does not know is shown as unknown rather than guessed into a known one.
  const status = SERVER_STATUS[request.status] ?? 'UNKNOWN';
  return {
    submission_id: request.request_id,
    created_at: request.created_at,
    updated_at: request.updated_at,
    owner_email: request.owner.username,
    title: request.aoi_id ?? 'Контур пользователя',
    aoi_id: request.aoi_id,
    geometry: request.geometry,
    geometry_hash: request.geometry_hash,
    year_start: request.year_start,
    year_end: request.year_end,
    claimed_units: request.claimed_units,
    status,
    analysis_id: request.analysis_id,
    result,
    notes: [],
    finalized_by: request.finalized_by,
    finalized_at: request.finalized_at,
    lifecycle: request.events.flatMap((event): LifecycleEntry[] => {
      if (event.to_status === 'CALCULATED') return [{ step: 'CALCULATION' as const, at: event.occurred_at, by: event.user_id ?? 'service', note: event.note }];
      if (event.to_status === 'FINALIZED') return [{ step: 'VERIFICATION' as const, at: event.occurred_at, by: event.user_id ?? 'verifier', note: event.note }];
      return [];
    }),
  };
}

/**
 * The contour as the wire contract types it, where a position is a pair.
 *
 * Written out rather than asserted: a cast would hand the compiler's blessing to a position that
 * carries an elevation or a stray third number, and the request would then be refused by the
 * service with a schema error instead of being sent in the shape the contract asks for. Everything
 * here has already survived `validateGeometry`, which rejects a non-numeric coordinate outright.
 */
function wireGeometry(geometry: Geometry): NonNullable<CreateVerificationRequest['geometry']> {
  const ring = (points: number[][]): [number, number][] =>
    points.map((point) => [point[0] ?? 0, point[1] ?? 0]);
  return geometry.type === 'Polygon'
    ? { type: 'Polygon', coordinates: geometry.coordinates.map(ring) }
    : { type: 'MultiPolygon', coordinates: geometry.coordinates.map((polygon) => polygon.map(ring)) };
}

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

function featuresFromGeoJson(data: unknown): Array<{ geometry: Geometry; properties: Record<string, unknown> }> {
  const collection = data as { type?: string; features?: Array<{ geometry?: Geometry; properties?: Record<string, unknown> }> };
  if (collection.type !== 'FeatureCollection' || !Array.isArray(collection.features)) {
    throw new LensError('CONTRACT', 'Артефакт слоя не является GeoJSON FeatureCollection.');
  }
  return collection.features
    .filter((feature): feature is { geometry: Geometry; properties?: Record<string, unknown> } => Boolean(feature.geometry))
    .map((feature) => ({ geometry: feature.geometry, properties: feature.properties ?? {} }));
}

function uniqueArtifact(result: AnalysisResult, role: string): Artifact | null {
  const candidates = result.artifacts.filter((item) => item.role === role);
  const keys = new Set(candidates.map((item) => `${item.role}:${item.sha256.toLowerCase()}`));
  if (keys.size > 1 || candidates.length > 1) {
    throw new LensError('ARTIFACT_AMBIGUOUS', `Для роли ${role} опубликовано несколько артефактов; слой не выбран автоматически.`);
  }
  return candidates[0] ?? null;
}

function mergeZoneFeatures(result: AnalysisResult, features: Array<{ geometry: Geometry; properties: Record<string, unknown> }>): AnalysisResult {
  const byId = new Map(features.map((feature) => [String(feature.properties.zone_id ?? ''), feature]));
  return {
    ...result,
    zones: result.zones.map((zone): Zone => {
      const feature = byId.get(zone.zone_id);
      if (!feature) return zone;
      const props = feature.properties;
      return {
        ...zone,
        geometry: feature.geometry,
        annex: {
          severity: typeof props.severity === 'string' ? props.severity : null,
          detection_resolution_m: typeof props.detection_resolution_m === 'number' ? props.detection_resolution_m : null,
          observed_between: typeof props.observed_between === 'object' && props.observed_between !== null
            ? (props.observed_between as { start?: unknown; end?: unknown }) : null,
          evidence_events: Array.isArray(props.evidence_events) ? props.evidence_events.map(String) : [],
          event_date_range: typeof props.event_date_range === 'object' && props.event_date_range !== null
            ? (props.event_date_range as { start?: unknown; end?: unknown }) : null,
        },
      };
    }),
  };
}

/**
 * Everything the three workspaces share: the catalog, the contour being measured, the analysis in
 * flight, the submissions of this session and the cells layer of the shown result.
 */
export function useWorkspace(client: LensApiClient, actorEmail: string, notify: Notify = () => {}) {
  const catalogResource = useResource<Catalog>((signal) => client.getCatalog(signal), [client]);
  const catalog = catalogResource.data;
  const catalogLoading = catalogResource.loading;
  const catalogError = catalogResource.error ? catalogResource.error.message : null;

  const [draft, setDraft] = useState<RequestDraft>(EMPTY_DRAFT);
  const [drawing, setDrawing] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);

  const [submissions, setSubmissions] = useState<Submission[]>(() => client.kind === 'fixture' ? loadSubmissions() : []);
  const submissionsRef = useRef<Submission[]>(submissions);
  const [activeSubmissionId, setActiveSubmissionId] = useState<string | null>(() => client.kind === 'fixture' ? loadSubmissions()[0]?.submission_id ?? null : null);
  // Пользователь мог намеренно закрыть заявку и вернуться к списку. Обновление списка не должно
  // молча открывать первую заявку снова — иначе кнопка «назад» не работает.
  const clearedRef = useRef(false);

  const [priceKey, setPriceKey] = useState<PriceKey>('base');
  const [customPrice, setCustomPrice] = useState<number | null>(null);
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null);
  const [selectedCellId, setSelectedCellId] = useState<string | null>(null);
  const [cells, setCells] = useState<CellsState>({ kind: 'hidden' });
  const [gaps, setGaps] = useState<GapLayerState>({ kind: 'hidden' });
  // Снимки принадлежат конкретному результату, и это хранится вместе с ними: иначе от прошлой
  // заявки остаётся чужая оптика, пока грузится новая.
  const [snapshots, setSnapshots] = useState<{ for: AnalysisResult | null; state: SnapshotsState }>({
    for: null,
    state: { kind: 'hidden' },
  });
  // Каждый показанный снимок держит objectURL; без освобождения вкладка копит их на каждый результат.
  const snapshotRelease = useRef<Array<() => void>>([]);
  const [zoneResult, setZoneResult] = useState<AnalysisResult | null>(null);
  const [proof, setProof] = useState<Proof | null>(null);

  const analysis = useAnalysis(client);

  const refreshRequests = useCallback(async (signal?: AbortSignal) => {
    if (client.kind !== 'http' || !client.listRequests) return;
    try {
      const requests = await client.listRequests(signal);
      const next = await Promise.all(requests.map(async (request) => {
        if (!request.analysis_id) return serverSubmission(request, null);
        try {
          const item = await client.getAnalysis(request.analysis_id, signal);
          return serverSubmission(request, item.result);
        } catch (error) {
          if (signal?.aborted) throw error;
          return serverSubmission(request, null);
        }
      }));
      if (signal?.aborted) return;
      submissionsRef.current = next;
      setSubmissions(next);
      setActiveSubmissionId((current) => {
        if (current && next.some((item) => item.submission_id === current)) return current;
        return clearedRef.current ? null : next[0]?.submission_id ?? null;
      });
      setRequestError(null);
    } catch (error) {
      if (!signal?.aborted) setRequestError(error instanceof LensError ? `${error.code}: ${error.message}` : String(error));
    }
  }, [client]);

  useEffect(() => {
    if (client.kind !== 'http') return;
    const controller = new AbortController();
    queueMicrotask(() => void refreshRequests(controller.signal));
    return () => controller.abort();
  }, [actorEmail, client.kind, refreshRequests]);

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
    if (client.kind === 'fixture') saveSubmissions(next);
    setSubmissions(next);
  }, [client.kind]);

  const activeSubmission = useMemo(
    () => submissions.find((item) => item.submission_id === activeSubmissionId) ?? null,
    [submissions, activeSubmissionId],
  );

  const rawResult: AnalysisResult | null = activeSubmission?.result ?? analysis.state.result;
  const shownResult = zoneResult?.identity.analysis_id === rawResult?.identity.analysis_id ? zoneResult : rawResult;

  useEffect(() => {
    const result = rawResult;
    if (!result) return;
    const controller = new AbortController();
    const load = async () => {
      await Promise.resolve();
      if (controller.signal.aborted) return;
      setGaps({ kind: 'loading' });
      try {
        const refs = [...new Set(result.zones.map((zone) => zone.artifact_ref).filter((item): item is string => Boolean(item)))];
        if (refs.length > 1) throw new LensError('ARTIFACT_AMBIGUOUS', 'Зоны результата ссылаются на разные геометрические артефакты.');
        const artifact = refs.length === 1 ? result.artifacts.find((item) => item.artifact_id === refs[0]) ?? null : uniqueArtifact(result, 'change_zones');
        if (result.zones.length > 0 && (!artifact || artifact.role !== 'change_zones')) {
          throw new LensError('ZONE_ARTIFACT_MISSING', 'Сервис не связал зоны с проверяемым артефактом change_zones.');
        }
        if (artifact) {
          const payload = await client.getArtifact(artifact, controller.signal);
          if (payload.integrity === 'MISMATCH') throw new LensError('ARTIFACT_INTEGRITY', `Хеш зон не совпал с ${artifact.sha256}.`);
          setZoneResult(mergeZoneFeatures(result, featuresFromGeoJson(payload.data)));
        }
        const gapArtifact = uniqueArtifact(result, 'observation_gap_zones');
        if (!gapArtifact) {
          setGaps({ kind: 'empty' });
        } else {
          const payload = await client.getArtifact(gapArtifact, controller.signal);
          if (payload.integrity === 'MISMATCH') {
            setGaps({ kind: 'integrity-failed', reason: `Хеш файла не совпал с ${gapArtifact.sha256}.` });
          } else {
            const geometries = featuresFromGeoJson(payload.data).map((feature) => feature.geometry);
            setGaps(geometries.length ? { kind: 'ready', geometries } : { kind: 'empty' });
          }
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        const reason = error instanceof LensError ? `${error.code}: ${error.message}` : String(error);
        setGaps({ kind: 'unavailable', reason });
      }
    };
    void load();
    return () => controller.abort();
  }, [client, rawResult]);

  const submitRequest = useCallback(
    async (title: string) => {
      setRequestError(null);
      const refuse = (reason: string) => {
        setRequestError(reason);
        notify({ tone: 'warn', title: 'Заявку пока нельзя отправить', text: reason });
        return null;
      };
      if (!draft.geometry) {
        return refuse('Контур не задан: выберите участок, нарисуйте его или импортируйте GeoJSON.');
      }
      const acceptedMeasurement = measureResource.data ?? (client.kind === 'fixture' ? measurement : null);
      if (!acceptedMeasurement || !acceptedMeasurement.valid || !acceptedMeasurement.within_limit ||
          acceptedMeasurement.area_ha === null || !acceptedMeasurement.geometry) {
        return refuse('Дождитесь корректного измерения контура сервисом и исправьте указанные ошибки.');
      }
      if (draft.yearEnd <= draft.yearStart) {
        return refuse('Конечный год должен быть больше начального.');
      }
      const claimed = draft.claimedUnits.trim();
      if (claimed !== '' && (!Number.isFinite(Number(claimed)) || Number(claimed) < 0)) {
        return refuse('Заявленный объём должен быть неотрицательным числом.');
      }
      if (client.kind === 'http') {
        if (!client.createRequest || !client.submitRequest) {
          // Reported, not thrown: these callbacks are invoked from a click handler, and a rejected
          // promise there becomes an unhandled page error instead of a message the user can read.
          setRequestError('CONTRACT: сервисный клиент не поддерживает заявки.');
          return null;
        }
        try {
          const created = await client.createRequest({
            aoi_id: draft.aoiId,
            geometry: wireGeometry(acceptedMeasurement.geometry),
            year_start: draft.yearStart,
            year_end: draft.yearEnd,
            claimed_units: claimed === '' ? null : Number(claimed),
          });
          const submitted = await client.submitRequest(created.request_id);
          const submission = serverSubmission(submitted, null);
          persist([submission, ...submissionsRef.current.filter((item) => item.submission_id !== submission.submission_id)]);
          setActiveSubmissionId(submission.submission_id);
          notify({
            tone: 'ok',
            title: 'Заявка отправлена на проверку',
            text: `${submission.title}, ${submission.year_start}–${submission.year_end}.`,
            hint: 'Расчёт запускает верификатор. Числа появятся здесь после его подтверждения.',
          });
          return submission;
        } catch (error) {
          const reason = error instanceof LensError ? `${error.code}: ${error.message}` : String(error);
          setRequestError(reason);
          notify({ tone: 'error', title: 'Сервис не принял заявку', text: reason });
          return null;
        }
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
      notify({
        tone: 'ok',
        title: 'Заявка создана',
        text: `${submission.title}, ${submission.year_start}–${submission.year_end}.`,
        hint: 'Дальше её проверяет верификатор.',
      });
      return submission;
    },
    [actorEmail, client, draft, measureResource.data, measurement, notify, persist],
  );

  const runAnalysis = useCallback(
    async (submission: Submission, scenario?: string) => {
      setSelectedZoneId(null);
      setSelectedCellId(null);
      setCells({ kind: 'hidden' });
      setProof(null);
      let result: AnalysisResult | null;
      let analysisId: string | null = null;
      if (client.kind === 'http') {
        if (!client.startRequestAnalysis) {
          setRequestError('CONTRACT: сервисный клиент не поддерживает lifecycle заявок.');
          return null;
        }
        notify({
          tone: 'info',
          title: 'Расчёт запущен',
          text: 'Сервис считает по спутниковым данным. Обычно это занимает до минуты.',
        });
        try {
          const accepted = await client.startRequestAnalysis(submission.submission_id, { idempotencyKey: `lens-request-${crypto.randomUUID()}` });
          analysisId = accepted.analysis_id;
          if (!analysisId) throw new LensError('CONTRACT', 'Сервис не вернул analysis_id для заявки.');
          result = await analysis.watch(analysisId);
        } catch (error) {
          const reason = error instanceof LensError ? `${error.code}: ${error.message}` : String(error);
          setRequestError(reason);
          notify({
            tone: 'error',
            title: 'Расчёт не выполнен',
            text: reason,
            hint: 'Заявка осталась в очереди: сервис сам вернул её в состояние «ждёт проверки».',
          });
          // The service owns what happened to the request: a failed run returns it to SUBMITTED,
          // and guessing that here would leave the queue showing a state the service disagrees with.
          void refreshRequests();
          return null;
        }
      } else result = await analysis.run(
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
        // The most consequential mismatch this screen can meet: the number would describe a
        // different contour than the one submitted. It is refused, and it is refused where the
        // person can read it — a thrown rejection here would reach only the console.
        setRequestError('GEOMETRY_HASH_MISMATCH: сервис рассчитал другой нормализованный контур; результат не принят.');
        notify({
          tone: 'error',
          title: 'Результат не принят',
          text: 'Сервис рассчитал другой нормализованный контур, чем был в заявке.',
          hint: 'Число описывало бы не тот участок, поэтому оно не показано.',
        });
        return null;
      }
      const updated: Submission = {
        ...submission,
        status: submission.status === 'FINALIZED' ? 'FINALIZED' : 'CALCULATED',
        analysis_id: analysisId ?? result.identity.analysis_id,
        result,
        updated_at: new Date().toISOString(),
      };
      // The lifecycle entry is recorded locally only in fixture mode. In HTTP mode the service has
      // already written the real event, with the real user id and its own timestamp; adding a
      // second one from the browser would put a fabricated row next to the recorded one.
      const shown = client.kind === 'http' ? updated : recordStep(updated, 'CALCULATION', actorEmail);
      persist(submissionsRef.current.map((item) => (item.submission_id === submission.submission_id ? shown : item)));
      setActiveSubmissionId(submission.submission_id);
      const id = updated.analysis_id;
      if (id) {
        client
          .getProof(id)
          .then(setProof)
          .catch(() => setProof(null));
      }
      // Reconcile with the service once the number is on screen: status and events are its state,
      // not a conclusion this client is entitled to draw from a finished poll.
      if (client.kind === 'http') void refreshRequests();
      const units = result.units.q;
      notify(
        units === null
          ? {
              tone: 'warn',
              title: 'Расчёт завершён: единицы не рассчитаны',
              text: 'Обязательных данных на этом участке не хватило.',
              hint: 'Это не ноль единиц: смотрите раздел «Насколько можно доверять».',
            }
          : units === 0
            ? {
                tone: 'warn',
                title: 'Расчёт завершён: подтверждённых единиц ноль',
                text: 'Результат периода не превышает базовую линию.',
                hint: 'Это полноценный результат проверки, а не ошибка.',
              }
            : {
                tone: 'ok',
                title: `Расчёт завершён: ${units.toLocaleString('ru-RU')} единиц`,
                text: 'Числа и карта ниже.',
                hint: 'Осталось подтвердить результат, чтобы его увидел инвестор.',
              },
      );
      return result;
    },
    [actorEmail, analysis, client, notify, persist, refreshRequests],
  );

  const showCells = useCallback(async () => {
    const result = shownResult;
    const artifact = result?.artifacts.find((item) => item.role === 'cci_cell_layer' || item.role === 'cells') ?? null;
    if (!result || !artifact) {
      const reason = 'Сервис не приложил к этому результату слой ячеек.';
      setCells({ kind: 'unavailable', reason });
      notify({
        tone: 'warn',
        title: 'Ячейки показать нечем',
        text: reason,
        hint: 'Файл ячеек формирует сервис при расчёте: попросите верификатора пересчитать заявку.',
      });
      return;
    }
    setCells({ kind: 'loading' });
    try {
      const payload = await client.getArtifact(artifact);
      if (payload.integrity === 'MISMATCH') {
        setCells({ kind: 'integrity-failed', reason: `Хеш файла не совпал с заявленным ${artifact.sha256.slice(0, 18)}…` });
        notify({
          tone: 'error',
          title: 'Целостность слоя не подтверждена',
          text: 'Хеш файла ячеек не совпал с заявленным.',
          hint: 'Слой не показан: выдавать непроверенные данные за доверенные нельзя.',
        });
        return;
      }
      const parsed = cellsFromGeoJson(payload.data);
      setCells(parsed.length === 0 ? { kind: 'empty' } : { kind: 'ready', cells: parsed });
      notify(
        parsed.length === 0
          ? { tone: 'warn', title: 'Слой ячеек пуст', text: 'В файле нет ни одной ячейки.' }
          : { tone: 'ok', title: `Ячейки на карте: ${parsed.length.toLocaleString('ru-RU')}`, hint: 'Нажмите ячейку, чтобы увидеть запас углерода и погрешность.' },
      );
    } catch (error) {
      const reason = error instanceof LensError ? `${error.code}: ${error.message}` : String(error);
      setCells({ kind: 'unavailable', reason });
      notify({ tone: 'error', title: 'Слой ячеек не загрузился', text: reason, hint: 'Карта и расчёт остаются на месте.' });
    }
  }, [client, notify, shownResult]);

  const showSnapshots = useCallback(async () => {
    const result = shownResult;
    if (!result) return;
    const wanted = SNAPSHOT_ROLES.map((entry) => result.artifacts.find((item) => item.role === entry.role))
      .filter((item): item is Artifact => item !== undefined);
    if (wanted.length === 0) {
      setSnapshots({ for: result, state: { kind: 'unavailable', reason: 'Сервис не приложил к этому результату ни одного снимка.' } });
      return;
    }
    snapshotRelease.current.forEach((release) => release());
    snapshotRelease.current = [];
    setSnapshots({ for: result, state: { kind: 'loading' } });
    try {
      const loaded: SnapshotImage[] = [];
      for (const artifact of wanted) {
        const payload = await client.getArtifact(artifact);
        snapshotRelease.current.push(payload.release);
        loaded.push({ role: artifact.role, artifact, src: payload.src, integrity: payload.integrity });
      }
      setSnapshots({ for: result, state: { kind: 'ready', images: loaded } });
      // Несовпавший хеш — это не мелочь фона: снимок не показан, и человек должен узнать почему.
      const refused = loaded.filter((image) => image.integrity === 'MISMATCH').length;
      if (refused > 0) {
        notify({
          tone: 'error',
          title: refused === 1 ? 'Один снимок не показан' : `Снимков не показано: ${refused}`,
          text: 'Хеш файла не совпал с заявленным в результате.',
          hint: 'Остальные снимки и расчёт остаются на месте.',
        });
      }
    } catch (error) {
      const reason = error instanceof LensError ? `${error.code}: ${error.message}` : String(error);
      setSnapshots({ for: result, state: { kind: 'unavailable', reason } });
      notify({ tone: 'warn', title: 'Снимки не загрузились', text: reason, hint: 'Карта и расчёт остаются на месте.' });
    }
  }, [client, notify, shownResult]);

  // Показывать можно только снимки того результата, который сейчас на экране: для любого другого
  // состояние снова «ничего не загружено», и блок запрашивает свою оптику сам. Ссылки прошлого
  // результата освобождает эта же загрузка, а последние — размонтирование вкладки.
  const snapshotsState: SnapshotsState = snapshots.for === shownResult ? snapshots.state : { kind: 'hidden' };
  useEffect(
    () => () => {
      snapshotRelease.current.forEach((release) => release());
      snapshotRelease.current = [];
    },
    [],
  );

  const finalize = useCallback(
    async (submission: Submission, verifier: string) => {
      if (client.kind === 'http') {
        if (!client.finalizeRequest) {
          setRequestError('CONTRACT: сервисный клиент не поддерживает финализацию.');
          return;
        }
        try {
          const finalized = await client.finalizeRequest(submission.submission_id);
          const updated = serverSubmission(finalized, submission.result);
          persist(submissionsRef.current.map((item) => item.submission_id === submission.submission_id ? updated : item));
          notify({
            tone: 'ok',
            title: 'Результат подтверждён',
            text: 'Паспорт закреплён за этой заявкой.',
            hint: 'Теперь его видит инвестор, а повторное подтверждение сервис уже не примет.',
          });
          return;
        } catch (error) {
          const reason = error instanceof LensError ? `${error.code}: ${error.message}` : String(error);
          setRequestError(reason);
          notify({ tone: 'error', title: 'Подтвердить не удалось', text: reason });
          return;
        }
      }
      const updated = recordStep(
        { ...submission, status: 'FINALIZED', finalized_by: verifier, finalized_at: new Date().toISOString() },
        'VERIFICATION',
        verifier,
      );
      persist(submissionsRef.current.map((item) => (item.submission_id === submission.submission_id ? updated : item)));
      notify({ tone: 'ok', title: 'Результат подтверждён', hint: 'Теперь его видит инвестор.' });
    },
    [client, notify, persist],
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
    const result = rawResult;
    if (!result) return;
    const html = renderReportHtml(result);
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `carbon-lens-${result.identity.input_hash.slice(2, 14)}.html`;
    link.click();
    URL.revokeObjectURL(url);
  }, [rawResult]);

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
    setActiveSubmissionId: (id: string) => {
      clearedRef.current = false;
      setActiveSubmissionId(id);
    },
    clearActiveSubmission: () => {
      clearedRef.current = true;
      setActiveSubmissionId(null);
    },
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
    gaps,
    snapshots: snapshotsState,
    showCells,
    showSnapshots,
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
