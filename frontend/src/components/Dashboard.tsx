import { useCallback, useEffect, useMemo, useState } from 'react';
import type { MrvApiClient } from '../api/client';
import { isTerminalOperation, pollUntilTerminal } from '../api/polling';
import type { DemoActor, Events, Operation } from '../api/types';
import { useResource } from '../hooks/useResource';
import { BeforeAfter } from './BeforeAfter';
import { CreditsPanel, type OperationReport } from './CreditsPanel';
import { EvidenceMap } from './EvidenceMap';
import { EvidencePanel } from './EvidencePanel';
import { JournalPanel, type ClientLogEntry } from './JournalPanel';
import { ObservationsPanel } from './ObservationsPanel';
import { ProofPanel } from './ProofPanel';
import { StatusStrip } from './StatusStrip';
import { Badge, Empty, ErrorNotice, Loading, Section, StatusBadge } from './common';
import { COMPUTATION_META, DATASET_META } from '../domain/status';
import { formatHa, formatUtc, shortHash } from '../domain/format';

type Tab = 'evidence' | 'credits' | 'proof';

interface Props {
  client: MrvApiClient;
  scope: string;
  plotId: string;
  actor: DemoActor;
  demoAuthorizationId: string;
}

const FREEZE_WATCH_MS = 120_000;

// Backend-internal operations (e.g. FREEZE by the oracle) are discovered via TX_SUBMITTED events without a terminal event.
export function openOperationIds(events: Events | null): string[] {
  if (!events) return [];
  const terminal = new Set(events.items.filter((e) => e.kind === 'TX_CONFIRMED' || e.kind === 'TX_FAILED').map((e) => e.operation_id));
  const open = events.items.filter((e) => e.kind === 'TX_SUBMITTED' && e.operation_id && !terminal.has(e.operation_id));
  return [...new Set(open.map((e) => e.operation_id as string))];
}

export function Dashboard({ client, scope, plotId, actor, demoAuthorizationId }: Props) {
  const [refreshKey, setRefreshKey] = useState(0);
  const [tab, setTab] = useState<Tab>('evidence');
  const [pinnedId, setPinnedId] = useState<string | null>(null);
  const [report, setReport] = useState<OperationReport | null>(null);
  const [watched, setWatched] = useState<Record<string, Operation>>({});
  const [clientLog, setClientLog] = useState<ClientLogEntry[]>([]);

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  const plot = useResource((signal) => client.getPlot(plotId, actor, { signal }), [client, plotId, actor, refreshKey]);
  const history = useResource((signal) => client.getHistory(plotId, { signal }), [client, plotId, refreshKey]);
  const credits = useResource((signal) => client.getCredits(plotId, actor, { signal }), [client, plotId, actor, refreshKey]);
  const events = useResource((signal) => client.listEvents({ plotId, limit: 50 }, { signal }), [client, plotId, refreshKey]);

  const selectedId = pinnedId ?? plot.data?.latest_verification_id ?? null;
  const verification = useResource(
    selectedId ? (signal) => client.getVerification(selectedId, { signal }) : null,
    [client, selectedId, refreshKey],
  );
  const latestVerification = useResource(
    plot.data?.latest_verification_id ? (signal) => client.getVerification(plot.data?.latest_verification_id as string, { signal }) : null,
    [client, plot.data?.latest_verification_id, refreshKey],
  );

  const batch = credits.data?.items[0] ?? null;
  const openOps = useMemo(() => openOperationIds(events.data), [events.data]);

  useEffect(() => {
    if (openOps.length === 0) return;
    const controller = new AbortController();
    for (const operationId of openOps) {
      void pollUntilTerminal<Operation>({
        fetch: (signal) => client.getOperation(operationId, { signal }),
        isTerminal: isTerminalOperation,
        onUpdate: (op) => setWatched((prev) => ({ ...prev, [op.operation_id]: op })),
        signal: controller.signal,
        maxDurationMs: FREEZE_WATCH_MS,
      }).then((result) => {
        if (result.status === 'terminal') refresh();
      });
    }
    return () => controller.abort();
  }, [client, openOps, refresh]);

  const freezeAwaitingChain = latestVerification.data?.decision === 'FREEZE_REQUESTED' && batch?.credit_status === 'ACTIVE';
  useEffect(() => {
    if (!freezeAwaitingChain) return;
    const startedAt = Date.now();
    const timer = setInterval(() => {
      if (Date.now() - startedAt > FREEZE_WATCH_MS) {
        clearInterval(timer);
        return;
      }
      events.reload();
      credits.reload();
    }, 1000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [freezeAwaitingChain]);

  const onOperation = useCallback((next: OperationReport) => setReport(next), []);
  const onRejected = useCallback((message: string) => {
    setClientLog((prev) => [{ id: `${Date.now()}-${prev.length}`, at: new Date().toISOString().slice(11, 19) + ' UTC', message }, ...prev].slice(0, 10));
  }, []);
  const onJobSucceeded = useCallback(() => {
    setPinnedId(null);
    refresh();
  }, [refresh]);

  const watchedOps = Object.values(watched);
  const activeWatched = watchedOps.find((op) => !isTerminalOperation(op)) ?? null;
  const lastWatched = watchedOps.at(-1) ?? null;
  let statusOperation: Operation | null = null;
  let statusSource: string | null = null;
  if (report?.active && report.operation) {
    statusOperation = report.operation;
    statusSource = report.source;
  } else if (activeWatched) {
    statusOperation = activeWatched;
    statusSource = 'Backend oracle';
  } else if (report?.operation) {
    statusOperation = report.operation;
    statusSource = report.source;
  } else if (lastWatched) {
    statusOperation = lastWatched;
    statusSource = 'Backend oracle';
  }

  if (plot.loading && !plot.data) return <Loading label="Загрузка участка…" />;
  if (plot.error && !plot.data) return <ErrorNotice error={plot.error} onRetry={plot.reload} />;
  if (!plot.data) return <Empty>Участок не найден.</Empty>;

  const shownVerification = verification.data && verification.data.verification_id === selectedId ? verification.data : null;

  return (
    <div className="dashboard">
      {plot.error && <ErrorNotice error={plot.error} onRetry={refresh} compact title="Не удалось обновить участок (показаны прошлые данные)" />}
      <div className="plot-meta" data-testid="plot-meta">
        <span>
          ID <span className="mono">{plot.data.plot_id}</span>
        </span>
        <span data-testid="plot-area">Площадь {formatHa(plot.data.area_ha)}</span>
        <span>
          Geometry hash <span className="mono">{shortHash(plot.data.geometry_hash)}</span>
        </span>
        {latestVerification.data && (
          <>
            <span>
              Последнее наблюдение: {formatUtc(latestVerification.data.evidence.observation.after.acquired_at)} ·{' '}
              <span className="mono">{latestVerification.data.evidence.observation.after.scene_id}</span> ·{' '}
              {latestVerification.data.evidence.observation.after.provider}
            </span>
            <span className="badge-row" data-testid="data-mode-badges">
              <StatusBadge meta={DATASET_META[latestVerification.data.evidence.dataset_kind]} testId="dataset-kind" />
              <StatusBadge meta={COMPUTATION_META[latestVerification.data.computation_mode]} testId="computation-mode" />
              <Badge tone="neutral">{latestVerification.data.observation_mode}</Badge>
            </span>
          </>
        )}
      </div>
      <StatusStrip verification={latestVerification.data} batch={batch} operation={statusOperation} operationSource={statusSource} />
      {latestVerification.data?.decision === 'FREEZE_REQUESTED' && batch?.credit_status === 'ACTIVE' && (
        <div className="state state-alert" role="status" data-testid="freeze-requested-banner">
          Приостановка запрошена Backend ({latestVerification.data.reason}). FROZEN будет показан только после подтверждённого receipt,
          события и readback в /credits.
        </div>
      )}

      <div className="layout">
        <div className="col-left">
          <Section title="Карта и evidence" id="map">
            <EvidenceMap client={client} plot={plot.data} verification={shownVerification} />
          </Section>
          <Section title="До / после" id="compare">
            {verification.loading && !shownVerification && <Loading />}
            {verification.error && <ErrorNotice error={verification.error} onRetry={verification.reload} compact />}
            {shownVerification ? <BeforeAfter client={client} verification={shownVerification} /> : !verification.loading && <Empty>Нет выбранного наблюдения.</Empty>}
          </Section>
        </div>

        <div className="col-right">
          <section className="panel">
            <div className="tabs" role="tablist" aria-label="Разделы дашборда">
              {(
                [
                  ['evidence', 'Evidence'],
                  ['credits', 'Credits'],
                  ['proof', 'Proof'],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={tab === key}
                  className={`tab${tab === key ? ' active' : ''}`}
                  onClick={() => setTab(key)}
                  data-testid={`tab-${key}`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="panel-body" role="tabpanel">
              {tab === 'evidence' &&
                (shownVerification ? (
                  <EvidencePanel verification={shownVerification} />
                ) : verification.loading ? (
                  <Loading />
                ) : (
                  <Empty>Нет обработанного наблюдения.</Empty>
                ))}
              {tab === 'credits' && (
                <CreditsPanel
                  client={client}
                  scope={scope}
                  plot={plot.data}
                  actor={actor}
                  credits={credits.data}
                  creditsError={credits.error}
                  creditsLoading={credits.loading}
                  onReloadCredits={credits.reload}
                  demoAuthorizationId={demoAuthorizationId}
                  onChanged={refresh}
                  onOperation={onOperation}
                  onRejected={onRejected}
                />
              )}
              {tab === 'proof' && (shownVerification ? <ProofPanel client={client} verification={shownVerification} refreshKey={refreshKey} /> : <Empty>Нет proof.</Empty>)}
            </div>
          </section>
        </div>
      </div>

      <div className="layout bottom">
        <Section title="Наблюдения и проверка" id="observations">
          <ObservationsPanel
            client={client}
            scope={scope}
            plotId={plotId}
            actor={actor}
            history={history.data}
            historyError={history.error}
            historyLoading={history.loading}
            onReloadHistory={history.reload}
            selectedId={selectedId}
            onSelect={(id) => setPinnedId(id === plot.data?.latest_verification_id ? null : id)}
            onJobSucceeded={onJobSucceeded}
            onChanged={refresh}
          />
        </Section>
        <Section
          title="Журнал: observation → decision → transaction → event"
          id="journal"
          actions={
            <button type="button" className="btn btn-small" onClick={refresh}>
              Обновить
            </button>
          }
        >
          <JournalPanel
            client={client}
            plotId={plotId}
            events={events.data}
            eventsError={events.error}
            eventsLoading={events.loading}
            onReload={events.reload}
            clientLog={clientLog}
          />
        </Section>
      </div>
    </div>
  );
}
