import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Empty, ErrorNotice, Section, Skeleton } from '../components/common';
import { MethodologyDialog } from '../components/MethodologyDialog';
import { useResource } from '../hooks/useResource';
import { LensError, approximateAreaHa, createFixtureLensClient, sampleRequestFeature, validateRequest, type LensApiClient } from './adapter';
import { createLensClient, resolveLensConfig, setLensToken, switchLensModeHref, type LensConfig } from './config';
import { DEMO_STEPS, type DemoStep } from './demo';
import type { FixtureScenarioId } from './fixtures';
import { ComparisonPanel } from './components/ComparisonPanel';
import { CoveragePanel } from './components/CoveragePanel';
import { DemoPanel } from './components/DemoPanel';
import { HistoryPanel } from './components/HistoryPanel';
import { LayersPanel } from './components/LayersPanel';
import { LensMap } from './components/LensMap';
import { ObservationsPanel } from './components/ObservationsPanel';
import { PassportPanel } from './components/PassportPanel';
import { RequestPanel } from './components/RequestPanel';
import { SummaryPanel } from './components/SummaryPanel';
import { TimelinePanel } from './components/TimelinePanel';
import { WaterfallPanel } from './components/WaterfallPanel';
import { ZonesPanel } from './components/ZonesPanel';
import { appendRun, clearRuns, loadRuns, makeRun, relateRun, saveRuns, type LensRun } from './session';
import { useLensAnalysis } from './useLensAnalysis';
import type { LensGeometry, LensRequest } from './types';

type Tab = 'calculation' | 'coverage' | 'observations' | 'zones' | 'comparison' | 'passport';

const TABS: ReadonlyArray<[Tab, string]> = [
  ['calculation', 'Разбор расчёта'],
  ['coverage', 'Покрытие'],
  ['observations', 'Наблюдения'],
  ['zones', 'Зоны'],
  ['comparison', 'Сравнение'],
  ['passport', 'Паспорт'],
];

function extractGeometry(text: string): LensGeometry {
  const parsed: unknown = JSON.parse(text);
  const node = parsed as { type?: string; geometry?: LensGeometry; features?: Array<{ geometry?: LensGeometry }> };
  if (node.type === 'FeatureCollection') {
    const geometry = node.features?.[0]?.geometry;
    if (!geometry) throw new LensError('INVALID_GEOMETRY', 'В FeatureCollection нет геометрии');
    return geometry;
  }
  if (node.type === 'Feature') {
    if (!node.geometry) throw new LensError('INVALID_GEOMETRY', 'В Feature нет геометрии');
    return node.geometry;
  }
  if (node.type === 'Polygon' || node.type === 'MultiPolygon') return parsed as LensGeometry;
  throw new LensError('INVALID_GEOMETRY', 'Ожидается Polygon, MultiPolygon, Feature или FeatureCollection');
}

function defaultConfig(): LensConfig {
  const search = typeof window === 'undefined' ? '' : window.location.search;
  const env = (import.meta as unknown as { env?: Record<string, string> }).env ?? {};
  return resolveLensConfig(env, search);
}

export function LensApp({ client: injected, config: injectedConfig }: { client?: LensApiClient; config?: LensConfig }) {
  const [config] = useState<LensConfig>(() => injectedConfig ?? defaultConfig());
  const client = useMemo(() => {
    if (injected) return injected;
    try {
      return createLensClient(config);
    } catch {
      // A misconfigured live URL must not leave the workspace blank; the banner explains the fallback to
      // the labelled set, and nothing pretends the service answered.
      return createFixtureLensClient();
    }
  }, [injected, config]);
  const clientKind = client.kind;
  const methodologyRef = useRef<HTMLDialogElement | null>(null);

  // Session history is read once, synchronously: a reload shows the saved result instead of an empty screen.
  const [storedRuns] = useState<LensRun[]>(() => loadRuns());
  const restoredRun = storedRuns[0] ?? null;
  const [runs, setRuns] = useState<LensRun[]>(storedRuns);
  const runsRef = useRef<LensRun[]>(storedRuns);
  const [restoredVisible, setRestoredVisible] = useState(restoredRun !== null);
  const [viewRunId, setViewRunId] = useState<string | null>(restoredRun?.run_id ?? null);

  const areas = useResource((signal) => client.listAreas().then((value) => (signal.aborted ? [] : value)), [client]);
  const [aoiId, setAoiId] = useState<string | null>(restoredRun?.request.aoi_id ?? null);
  const [customGeometry, setCustomGeometry] = useState(restoredRun !== null && restoredRun.request.aoi_id === null);
  const [geometry, setGeometry] = useState<LensGeometry | null>(restoredRun?.request.geometry ?? null);
  const [geometrySource, setGeometrySource] = useState(restoredRun ? 'контур восстановленного запроса' : 'участок из набора data/');
  const [parentAoiId, setParentAoiId] = useState<string | null>(restoredRun?.request.parent_aoi_id ?? null);
  const [yearStart, setYearStart] = useState(restoredRun?.request.year_start ?? 2019);
  const [yearEnd, setYearEnd] = useState(restoredRun?.request.year_end ?? 2020);
  const [claimedUnits, setClaimedUnits] = useState(restoredRun?.request.claimed_units === null || restoredRun === null ? '' : String(restoredRun.request.claimed_units));
  const [scenario, setScenario] = useState<FixtureScenarioId>('DOC_EXAMPLE_Q395');
  const [drawing, setDrawing] = useState(false);
  const [priceId, setPriceId] = useState('price_base');
  const [tab, setTab] = useState<Tab>('calculation');
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [hiddenLayers, setHiddenLayers] = useState<ReadonlySet<string>>(new Set());
  const [notice, setNotice] = useState<{ label: string; note: string } | null>(null);
  const [demoStepId, setDemoStepId] = useState<string | null>(null);
  const [token, setToken] = useState(config.token);

  const { state, busy, run } = useLensAnalysis(client);

  const firstAoi = areas.data?.[0]?.aoi_id ?? null;
  // The first area is a derived default; a drawn or imported contour switches the request to a custom geometry.
  const effectiveAoiId = customGeometry ? null : (aoiId ?? firstAoi);

  const selectAoi = useCallback((id: string) => {
    setCustomGeometry(false);
    setAoiId(id);
    setValidationError(null);
  }, []);

  useEffect(() => {
    if (!effectiveAoiId) return;
    let cancelled = false;
    client
      .getAreaGeometry(effectiveAoiId)
      .then((value) => {
        if (cancelled) return;
        setGeometry(value);
        setGeometrySource(`участок ${effectiveAoiId} из data/areas.geojson`);
        setParentAoiId(null);
      })
      .catch(() => {
        if (cancelled) return;
        setGeometry(null);
        setGeometrySource(`геометрия участка ${effectiveAoiId} не получена`);
      });
    return () => {
      cancelled = true;
    };
  }, [client, effectiveAoiId]);

  const areaHa = geometry ? Number(approximateAreaHa(geometry).toFixed(2)) : null;

  const request: LensRequest = useMemo(
    () => ({
      aoi_id: effectiveAoiId,
      parent_aoi_id: parentAoiId,
      geometry: geometry ?? { type: 'Polygon', coordinates: [] },
      year_start: yearStart,
      year_end: yearEnd,
      claimed_units: claimedUnits.trim() === '' ? null : Number(claimedUnits),
    }),
    [effectiveAoiId, parentAoiId, geometry, yearStart, yearEnd, claimedUnits],
  );

  const execute = useCallback(
    async (nextRequest: LensRequest, nextScenario: FixtureScenarioId) => {
      setValidationError(null);
      if (nextRequest.geometry.coordinates.length === 0) {
        setValidationError('Контур не задан: выберите участок, импортируйте GeoJSON или нарисуйте прямоугольник.');
        return;
      }
      if (nextRequest.claimed_units !== null && !Number.isFinite(nextRequest.claimed_units)) {
        setValidationError('Заявленные единицы должны быть числом.');
        return;
      }
      try {
        validateRequest(nextRequest, approximateAreaHa(nextRequest.geometry));
      } catch (error) {
        setValidationError(error instanceof LensError ? error.message : String(error));
        return;
      }
      setSelectedZoneId(null);
      setRestoredVisible(false);
      const result = await run(nextRequest, nextScenario);
      if (!result) return;
      const entry = makeRun(nextRequest, result, clientKind === 'http' ? 'http' : 'fixture');
      const relation = relateRun(runsRef.current, entry);
      const next = appendRun(runsRef.current, entry);
      runsRef.current = next;
      saveRuns(next);
      setRuns(next);
      setNotice({ label: relation.label, note: relation.note });
      setViewRunId(entry.run_id);
    },
    [run, clientKind],
  );

  const onRun = useCallback(() => {
    void execute(request, scenario);
  }, [execute, request, scenario]);

  const onDrawn = useCallback((drawn: LensGeometry) => {
    setGeometry(drawn);
    setGeometrySource('нарисованный контур');
    setCustomGeometry(true);
    setAoiId(null);
    setParentAoiId(null);
    setDrawing(false);
  }, []);

  const onImportGeoJson = useCallback((text: string) => {
    try {
      const imported = extractGeometry(text);
      setGeometry(imported);
      setGeometrySource('импортированный GeoJSON');
      setCustomGeometry(true);
      setAoiId(null);
      setValidationError(null);
    } catch (error) {
      setValidationError(error instanceof LensError ? error.message : String(error));
    }
  }, []);

  const loadSampleRequest = useCallback((requestId: string): LensGeometry | null => {
    const sample = sampleRequestFeature(requestId);
    if (!sample) {
      setValidationError(`Запрос ${requestId} не найден в data/sample_requests.geojson.`);
      return null;
    }
    setGeometry(sample.geometry);
    setGeometrySource(`подучасток ${requestId} из data/sample_requests.geojson`);
    setCustomGeometry(true);
    setAoiId(null);
    setParentAoiId(String(sample.properties.parent_aoi_id ?? ''));
    setYearStart(Number(sample.properties.year_start ?? 2020));
    setYearEnd(Number(sample.properties.year_end ?? 2024));
    return sample.geometry;
  }, []);

  const onLoadSampleRequest = useCallback(() => {
    loadSampleRequest('CHECK_TRANSFER_01');
  }, [loadSampleRequest]);

  /** A walkthrough step sets the same controls a user would set, then runs the request it describes. */
  const applyDemoStep = useCallback(
    (step: DemoStep) => {
      setDemoStepId(step.id);
      if (step.setup.tab) setTab(step.setup.tab);
      if (step.setup.scenario) setScenario(step.setup.scenario);
      if (step.setup.claimedUnits !== undefined) setClaimedUnits(step.setup.claimedUnits);

      let nextGeometry = geometry;
      let nextAoi = effectiveAoiId;
      let nextParent = parentAoiId;
      if (step.setup.sampleRequestId) {
        const sample = sampleRequestFeature(step.setup.sampleRequestId);
        nextGeometry = loadSampleRequest(step.setup.sampleRequestId) ?? nextGeometry;
        nextAoi = null;
        nextParent = String(sample?.properties.parent_aoi_id ?? '');
      } else if (step.setup.aoiId) {
        selectAoi(step.setup.aoiId);
        nextAoi = step.setup.aoiId;
        nextParent = null;
        nextGeometry = null;
      }
      const [start, end] = step.setup.years ?? [yearStart, yearEnd];
      if (step.setup.years) {
        setYearStart(start);
        setYearEnd(end);
      }
      if (!step.setup.run) return;

      const geometryForRun =
        nextGeometry ?? (step.setup.aoiId ? null : geometry);
      const claimed = step.setup.claimedUnits ?? claimedUnits;
      const submit = (geo: LensGeometry) =>
        void execute(
          {
            aoi_id: step.setup.aoiId ?? nextAoi,
            parent_aoi_id: nextParent,
            geometry: geo,
            year_start: start,
            year_end: end,
            claimed_units: claimed.trim() === '' ? null : Number(claimed),
          },
          step.setup.scenario ?? scenario,
        );

      if (geometryForRun) {
        submit(geometryForRun);
        return;
      }
      if (step.setup.aoiId) {
        void client
          .getAreaGeometry(step.setup.aoiId)
          .then(submit)
          .catch(() => setValidationError(`Геометрия участка ${step.setup.aoiId ?? ''} не получена.`));
      }
    },
    [client, claimedUnits, effectiveAoiId, execute, geometry, selectAoi, loadSampleRequest, parentAoiId, scenario, yearEnd, yearStart],
  );

  const activeRun = useMemo(() => (viewRunId ? runs.find((entry) => entry.run_id === viewRunId) ?? null : null), [viewRunId, runs]);
  const liveResult = state.result;
  const result = useMemo(() => activeRun?.result ?? liveResult ?? null, [activeRun, liveResult]);
  const zones = useMemo(() => result?.zones ?? [], [result]);
  const layers = useMemo(() => result?.layers ?? [], [result]);
  const visibleLayers = useMemo(
    () => new Set(layers.filter((layer) => layer.availability === 'AVAILABLE' && !hiddenLayers.has(layer.layer_id)).map((layer) => layer.layer_id)),
    [layers, hiddenLayers],
  );
  const showingSavedRun = restoredVisible && activeRun !== null;

  const toggleLayer = useCallback((layerId: string) => {
    setHiddenLayers((previous) => {
      const next = new Set(previous);
      if (next.has(layerId)) next.delete(layerId);
      else next.add(layerId);
      return next;
    });
  }, []);

  return (
    <div className="app lens">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">CARBON LENS</span>
          <span className="brand-descriptor">Рабочее место верификатора</span>
        </div>
        <nav className="topnav" aria-label="Разделы">
          <button type="button" className="topnav-item" aria-current="page">
            Анализ
          </button>
          <button type="button" className="topnav-item" onClick={() => methodologyRef.current?.showModal()} data-testid="lens-open-methodology">
            Методология
          </button>
          <a className="topnav-item" href="/" data-testid="lens-p0-link">
            MRV P0
          </a>
        </nav>
        <div className="topbar-right">
          <span className={`badge ${clientKind === 'http' ? 'tone-ok' : 'tone-review'}`} data-testid="lens-mode">
            {clientKind === 'http' ? 'ЖИВОЙ СЕРВИС' : 'ПОМЕЧЕННЫЙ НАБОР'}
          </span>
          <a className="topnav-item small" href={switchLensModeHref(clientKind === 'http' ? 'fixture' : 'http', window.location)} data-testid="lens-mode-switch">
            {clientKind === 'http' ? 'к помеченному набору' : 'к живому сервису'}
          </a>
        </div>
      </header>

      <div className={`source-bar ${clientKind === 'http' ? '' : 'tone-review-bar'}`} role="note" data-testid="lens-source-bar">
        <span className="dot" aria-hidden="true" />
        {clientKind === 'http' ? (
          <>
            <strong>Живой сервис.</strong>
            <span>
              Значения приходят от Backend по <span className="mono">{config.baseUrl}</span>. Доступ выдаётся во время сессии и не входит в
              опубликованную сборку.
            </span>
          </>
        ) : (
          <>
            <strong>Помеченные значения.</strong>
            <span>
              Территории, площади, базовая линия, сцены, события и источники — из официального <span className="mono">data/</span>.
              Рассчитанные величины приходят из помеченного набора: условный пример постановки и логические векторы. Контракт Backend G0
              ещё не опубликован.
            </span>
          </>
        )}
      </div>

      <main id="main">
        <div className="lens-layout">
          <aside className="rail rail-left">
            <Section title="Запрос" id="lens-request">
              <RequestPanel
                areas={areas.data ?? []}
                areasLoading={areas.loading}
                aoiId={effectiveAoiId}
                onSelectAoi={selectAoi}
                geometrySource={geometrySource}
                areaHa={areaHa}
                yearStart={yearStart}
                yearEnd={yearEnd}
                onYears={(start, end) => {
                  setYearStart(start);
                  setYearEnd(end);
                }}
                claimedUnits={claimedUnits}
                onClaimedUnits={setClaimedUnits}
                scenario={scenario}
                onScenario={setScenario}
                scenarioSelectable={clientKind !== 'http'}
                drawing={drawing}
                onToggleDrawing={() => setDrawing((d) => !d)}
                onImportGeoJson={onImportGeoJson}
                onLoadSampleRequest={onLoadSampleRequest}
                onRun={onRun}
                busy={busy}
                validationError={validationError}
              />
            </Section>
            {areas.error && <ErrorNotice error={areas.error} onRetry={areas.reload} title="Участки не загружены" compact />}

            {clientKind === 'http' && (
              <Section title="Доступ к сервису" id="lens-access">
                <label className="lens-field">
                  <span>Токен сессии</span>
                  <input
                    className="input"
                    type="password"
                    value={token}
                    onChange={(event) => {
                      setToken(event.target.value);
                      setLensToken(event.target.value);
                    }}
                    data-testid="lens-token-input"
                  />
                </label>
                <p className="muted small">
                  Значение хранится только в этой вкладке браузера и не попадает в сборку. Источник текущего значения:{' '}
                  {config.tokenSource === 'none' ? 'не задан' : config.tokenSource === 'url' ? 'адрес страницы' : 'сессия браузера'}.
                </p>
              </Section>
            )}

            <Section title="Сценарий показа" id="lens-demo-section">
              <DemoPanel activeStepId={demoStepId} onApply={applyDemoStep} busy={busy} />
            </Section>

            <Section title="История сессии" id="lens-history-section">
              <HistoryPanel
                runs={runs}
                activeRunId={viewRunId}
                onOpen={(runId) => {
                  setViewRunId(runId);
                  setRestoredVisible(false);
                  setSelectedZoneId(null);
                }}
                onClear={() => {
                  clearRuns();
                  runsRef.current = [];
                  setRuns([]);
                  setViewRunId(null);
                  setRestoredVisible(false);
                }}
              />
            </Section>
          </aside>

          <div className="center">
            <LensMap
              geometry={geometry}
              zones={zones}
              layers={layers}
              visibleLayers={visibleLayers}
              selectedZoneId={selectedZoneId}
              onSelectZone={(id) => {
                setSelectedZoneId(id);
                setTab('zones');
              }}
              drawing={drawing}
              onDrawn={onDrawn}
            />
            <Section title="Слои карты" id="lens-layers-section">
              {layers.length === 0 ? (
                <Empty>
                  <strong>Слоёв пока нет</strong>
                  <span>Список слоёв и причины их отсутствия появятся после расчёта.</span>
                </Empty>
              ) : (
                <LayersPanel layers={layers} visible={visibleLayers} onToggle={toggleLayer} />
              )}
            </Section>
            <Section title="Годовая динамика запаса" id="lens-dynamics">
              {result ? (
                <TimelinePanel result={result} />
              ) : (
                <Empty>
                  <strong>Динамика появится после расчёта</strong>
                  <span>Задайте территорию и период, затем нажмите «Рассчитать».</span>
                </Empty>
              )}
            </Section>
          </div>

          <div className="rail rail-right">
            {showingSavedRun && (
              <div className="state state-warn compact" role="status" data-testid="lens-restored-note">
                <strong>Показан сохранённый расчёт этой сессии</strong>
                <span>
                  Запрос от {new Date(activeRun.saved_at).toLocaleString('ru-RU')}. Это не новый расчёт: чтобы получить свежий результат,
                  нажмите «Рассчитать».
                </span>
              </div>
            )}
            {notice && (
              <div className="state state-ok compact" role="status" data-testid="lens-notice">
                <strong>{notice.label}</strong>
                <span>{notice.note}</span>
                <span>
                  <button type="button" className="btn btn-small btn-secondary" onClick={() => setNotice(null)}>
                    Скрыть
                  </button>
                </span>
              </div>
            )}

            <Section title="Краткий результат" id="lens-summary-section">
              {state.phase === 'submitting' && <Skeleton label="Отправка запроса…" height={160} />}
              {state.phase === 'polling' && <Skeleton label={`Расчёт: ${state.job?.state ?? 'QUEUED'}…`} height={160} />}
              {state.phase === 'timeout' && (
                <div className="state state-warn" role="status" data-testid="lens-timeout">
                  <strong>Расчёт ещё выполняется</strong>
                  <span>Опрос приостановлен, состояние задания не изменено. Запустите расчёт снова, чтобы продолжить наблюдение.</span>
                </div>
              )}
              {state.phase === 'error' && state.error && (
                <div className="state state-error" role="alert" data-testid="lens-error">
                  <strong>Расчёт недоступен · {state.error.code}</strong>
                  <span>{state.error.message}</span>
                  {state.error.detail && <span className="muted small">{state.error.detail}</span>}
                  <span className="muted small">Помеченный набор не подставляется автоматически вместо ответа сервиса.</span>
                  <span>
                    <button type="button" className="btn btn-small btn-secondary" onClick={onRun}>
                      Повторить
                    </button>
                  </span>
                </div>
              )}
              {state.phase === 'idle' && !result && (
                <Empty>
                  <strong>Расчёт не запускался</strong>
                  <span>Выберите территорию и период, при необходимости введите заявление и нажмите «Рассчитать».</span>
                </Empty>
              )}
              {result && <SummaryPanel result={result} priceId={priceId} onPrice={setPriceId} />}
            </Section>

            <section className="panel" aria-label="Разбор расчёта, покрытие, наблюдения, зоны, сравнение и паспорт">
              <div className="tabs" role="tablist" aria-label="Разделы результата">
                {TABS.map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    role="tab"
                    id={`lens-tab-${key}`}
                    aria-selected={tab === key}
                    aria-controls={`lens-tabpanel-${key}`}
                    className={`tab${tab === key ? ' active' : ''}`}
                    onClick={() => setTab(key)}
                    data-testid={`lens-tab-${key}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="panel-body" role="tabpanel" id={`lens-tabpanel-${tab}`} aria-labelledby={`lens-tab-${tab}`}>
                {tab === 'comparison' && <ComparisonPanel runs={runs} priceId={priceId} />}
                {tab !== 'comparison' && !result && (
                  <Empty>
                    <strong>Нет результата</strong>
                    <span>Разбор расчёта, покрытие, наблюдения, зоны и паспорт появятся после расчёта.</span>
                  </Empty>
                )}
                {result && tab === 'calculation' && <WaterfallPanel result={result} />}
                {result && tab === 'coverage' && <CoveragePanel result={result} />}
                {result && tab === 'observations' && <ObservationsPanel result={result} />}
                {result && tab === 'zones' && <ZonesPanel result={result} selectedZoneId={selectedZoneId} onSelectZone={setSelectedZoneId} />}
                {result && tab === 'passport' && <PassportPanel result={result} />}
              </div>
            </section>

            {result?.fixture && (
              <div className="state state-warn compact" role="note" data-testid="lens-fixture-note">
                <strong>{result.fixture.kind === 'DOC_EXAMPLE' ? 'Условный пример постановки' : 'Логический вектор'}</strong>
                <span>{result.fixture.note}</span>
                {result.fixture.acceptance_id && (
                  <span className="muted small">
                    Сценарий приёмки {result.fixture.acceptance_id}: {result.fixture.acceptance_note}
                  </span>
                )}
              </div>
            )}
            {result && !result.fixture && (
              <div className="state state-ok compact" role="note" data-testid="lens-service-note">
                <strong>Значения рассчитаны сервисом</strong>
                <span>{result.provenance.computed_note}</span>
              </div>
            )}
          </div>
        </div>
      </main>
      <MethodologyDialog ref={methodologyRef} />
    </div>
  );
}

export { DEMO_STEPS };
