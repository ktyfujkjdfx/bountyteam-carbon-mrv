import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Empty, ErrorNotice, Section, Skeleton } from '../components/common';
import { MethodologyDialog } from '../components/MethodologyDialog';
import { useResource } from '../hooks/useResource';
import { LensError, approximateAreaHa, createFixtureLensClient, sampleRequestFeature, validateRequest, type LensApiClient } from './adapter';
import type { FixtureScenarioId } from './fixtures';
import { CoveragePanel } from './components/CoveragePanel';
import { LensMap } from './components/LensMap';
import { PassportPanel } from './components/PassportPanel';
import { RequestPanel } from './components/RequestPanel';
import { SummaryPanel } from './components/SummaryPanel';
import { TimelinePanel } from './components/TimelinePanel';
import { WaterfallPanel } from './components/WaterfallPanel';
import { ZonesPanel } from './components/ZonesPanel';
import { useLensAnalysis } from './useLensAnalysis';
import type { LensGeometry, LensRequest } from './types';

type Tab = 'calculation' | 'coverage' | 'zones' | 'passport';

const TABS: ReadonlyArray<[Tab, string]> = [
  ['calculation', 'Разбор расчёта'],
  ['coverage', 'Покрытие'],
  ['zones', 'Зоны'],
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

export function LensApp({ client: injected }: { client?: LensApiClient }) {
  const client = useMemo(() => injected ?? createFixtureLensClient(), [injected]);
  const methodologyRef = useRef<HTMLDialogElement | null>(null);

  const areas = useResource((signal) => client.listAreas().then((value) => (signal.aborted ? [] : value)), [client]);
  const [aoiId, setAoiId] = useState<string | null>(null);
  const [customGeometry, setCustomGeometry] = useState(false);
  const [geometry, setGeometry] = useState<LensGeometry | null>(null);
  const [geometrySource, setGeometrySource] = useState('участок из набора data/');
  const [parentAoiId, setParentAoiId] = useState<string | null>(null);
  const [yearStart, setYearStart] = useState(2019);
  const [yearEnd, setYearEnd] = useState(2020);
  const [claimedUnits, setClaimedUnits] = useState('');
  const [scenario, setScenario] = useState<FixtureScenarioId>('DOC_EXAMPLE_Q395');
  const [drawing, setDrawing] = useState(false);
  const [priceId, setPriceId] = useState('price_base');
  const [tab, setTab] = useState<Tab>('calculation');
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const { state, busy, run } = useLensAnalysis(client);

  const firstAoi = areas.data?.[0]?.aoi_id ?? null;
  // The first area is a derived default; a drawn or imported contour switches the request to a custom geometry.
  const effectiveAoiId = customGeometry ? null : (aoiId ?? firstAoi);

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
        if (!cancelled) setGeometry(null);
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

  const onRun = useCallback(() => {
    setValidationError(null);
    if (!geometry) {
      setValidationError('Контур не задан: выберите участок, импортируйте GeoJSON или нарисуйте прямоугольник.');
      return;
    }
    if (claimedUnits.trim() !== '' && !Number.isFinite(Number(claimedUnits))) {
      setValidationError('Заявленные единицы должны быть числом.');
      return;
    }
    try {
      validateRequest(request, approximateAreaHa(geometry));
    } catch (error) {
      setValidationError(error instanceof LensError ? error.message : String(error));
      return;
    }
    setSelectedZoneId(null);
    void run(request, scenario);
  }, [geometry, claimedUnits, request, run, scenario]);

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

  const onLoadSampleRequest = useCallback(() => {
    const sample = sampleRequestFeature('CHECK_TRANSFER_01');
    if (!sample) {
      setValidationError('Запрос CHECK_TRANSFER_01 не найден в data/sample_requests.geojson.');
      return;
    }
    setGeometry(sample.geometry);
    setGeometrySource('подучасток CHECK_TRANSFER_01 из data/sample_requests.geojson');
    setCustomGeometry(true);
    setAoiId(null);
    setParentAoiId(String(sample.properties.parent_aoi_id ?? ''));
    setYearStart(Number(sample.properties.year_start ?? 2020));
    setYearEnd(Number(sample.properties.year_end ?? 2024));
  }, []);

  const result = state.result;
  const zones = result?.zones ?? [];

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
          <span className="badge tone-review" data-testid="lens-mode">
            FIXTURE ADAPTER · F1
          </span>
        </div>
      </header>

      <div className="source-bar tone-review-bar" role="note" data-testid="lens-source-bar">
        <span className="dot" aria-hidden="true" />
        <strong>Помеченные данные F1.</strong>
        <span>
          Территории, площади и базовая линия — из официального <span className="mono">data/</span>. Числовые результаты приходят из
          помеченного набора: условный пример постановки и логические векторы. Backend-контракт G0 ещё не опубликован.
        </span>
      </div>

      <main id="main">
        <div className="lens-layout">
          <aside className="rail rail-left">
            <Section title="Запрос" id="lens-request">
              <RequestPanel
                areas={areas.data ?? []}
                areasLoading={areas.loading}
                aoiId={effectiveAoiId}
                onSelectAoi={(id) => {
                  setCustomGeometry(false);
                  setAoiId(id);
                  setValidationError(null);
                }}
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
          </aside>

          <div className="center">
            <LensMap
              geometry={geometry}
              zones={zones}
              selectedZoneId={selectedZoneId}
              onSelectZone={(id) => {
                setSelectedZoneId(id);
                setTab('zones');
              }}
              drawing={drawing}
              onDrawn={onDrawn}
            />
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
                  <span>
                    <button type="button" className="btn btn-small btn-secondary" onClick={onRun}>
                      Повторить
                    </button>
                  </span>
                </div>
              )}
              {state.phase === 'idle' && (
                <Empty>
                  <strong>Расчёт не запускался</strong>
                  <span>Выберите территорию и период, при необходимости введите заявление и нажмите «Рассчитать».</span>
                </Empty>
              )}
              {result && <SummaryPanel result={result} priceId={priceId} onPrice={setPriceId} />}
            </Section>

            <section className="panel" aria-label="Разбор расчёта, покрытие, зоны и паспорт">
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
                {!result && (
                  <Empty>
                    <strong>Нет результата</strong>
                    <span>Разбор расчёта, покрытие, зоны и паспорт появятся после расчёта.</span>
                  </Empty>
                )}
                {result && tab === 'calculation' && <WaterfallPanel result={result} />}
                {result && tab === 'coverage' && <CoveragePanel result={result} />}
                {result && tab === 'zones' && <ZonesPanel result={result} selectedZoneId={selectedZoneId} onSelectZone={setSelectedZoneId} />}
                {result && tab === 'passport' && <PassportPanel result={result} />}
              </div>
            </section>

            {result?.fixture && (
              <div className="state state-warn compact" role="note" data-testid="lens-fixture-note">
                <strong>{result.fixture.kind === 'DOC_EXAMPLE' ? 'Условный пример постановки' : 'Логический вектор'}</strong>
                <span>{result.fixture.note}</span>
              </div>
            )}
          </div>
        </div>
      </main>
      <MethodologyDialog ref={methodologyRef} />
    </div>
  );
}
