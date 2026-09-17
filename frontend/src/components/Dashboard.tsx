import { useCallback, useEffect, useMemo, useState } from 'react';
import type { MrvApiClient } from '../api/client';
import { isTerminalOperation, pollUntilTerminal } from '../api/polling';
import type { DemoActor, Events, Operation, PlotSummary } from '../api/types';
import { useResource } from '../hooks/useResource';
import { BeforeAfter } from './BeforeAfter';
import { CreditsPanel, type OperationReport } from './CreditsPanel';
import { EvidenceMap } from './EvidenceMap';
import { EvidencePanel } from './EvidencePanel';
import { JournalPanel, type ClientLogEntry } from './JournalPanel';
import { MetricsStrip } from './MetricsStrip';
import { ObservationsPanel } from './ObservationsPanel';
import { ProjectHeader } from './ProjectHeader';
import { ProofPanel } from './ProofPanel';
import { QualityPanel } from './QualityPanel';
import { StatusStrip } from './StatusStrip';
import { Empty, ErrorNotice, Section, Skeleton } from './common';

type Tab = 'evidence' | 'credits' | 'proof';

export type LedgerKind = 'fixture' | 'mock' | 'chain' | 'unknown';

interface Props {
  client: MrvApiClient;
  scope: string;
  plotId: string;
  plots: PlotSummary[];
  onSelectPlot: (plotId: string) => void;
  actor: DemoActor;
  demoAuthorizationId: string;
  ledger: LedgerKind;
}

const FREEZE_WATCH_MS = 120_000;

const TABS: ReadonlyArray<[Tab, string]> = [
  ['evidence', 'MRV evidence'],
  ['credits', 'Реестр'],
  ['proof', 'Proof'],
];

// Backend-internal operations (e.g. FREEZE by the oracle) are discovered via TX_SUBMITTED events without a terminal event.
export function openOperationIds(events: Events | null): string[] {
  if (!events) return [];
  const terminal = new Set(events.items.filter((e) => e.kind === 'TX_CONFIRMED' || e.kind === 'TX_FAILED').map((e) => e.operation_id));
  const open = events.items.filter((e) => e.kind === 'TX_SUBMITTED' && e.operation_id && !terminal.has(e.operation_id));
  return [...new Set(open.map((e) => e.operation_id as string))];
}

export function latestTransactionOperationId(events: Events | null): string | null {
  const tx = (events?.items ?? [])
    .filter((e) => e.operation_id && (e.kind === 'TX_SUBMITTED' || e.kind === 'TX_CONFIRMED' || e.kind === 'TX_FAILED'))
    .sort((a, b) => b.occurred_at.localeCompare(a.occurred_at));
  return tx[0]?.operation_id ?? null;
}

export function Dashboard({ client, scope, plotId, plots, onSelectPlot, actor, demoAuthorizationId, ledger }: Props) {
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
  const latestId = plot.data?.latest_verification_id ?? null;
  const latestVerification = useResource(latestId ? (signal) => client.getVerification(latestId, { signal }) : null, [client, latestId, refreshKey]);

  const batch = credits.data?.items[0] ?? null;
  const openOps = useMemo(() => openOperationIds(events.data), [events.data]);
  const lastTxOperationId = useMemo(() => latestTransactionOperationId(events.data), [events.data]);
  const lastTxOperation = useResource(
    lastTxOperationId ? (signal) => client.getOperation(lastTxOperationId, { signal }) : null,
    [client, lastTxOperationId, refreshKey],
  );

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
  } else if (lastTxOperation.data && lastTxOperation.data.operation_id === lastTxOperationId) {
    statusOperation = lastTxOperation.data;
    statusSource = 'последняя в журнале';
  }

  if (plot.loading && !plot.data) {
    return (
      <div className="dashboard" aria-busy="true">
        <Skeleton label="Загрузка геометрии участка…" height={88} />
        <Skeleton label="Загрузка статусов evidence, решения и реестра…" height={96} />
        <div className="skeleton-layout">
          <Skeleton label="Evidence quality" height={420} />
          <Skeleton label="Загрузка карты и превью наблюдения…" height={520} />
          <Skeleton label="Получение MRV evidence…" height={520} />
        </div>
      </div>
    );
  }
  if (plot.error && !plot.data) {
    return <ErrorNotice error={plot.error} onRetry={plot.reload} title={plot.error.status === 404 ? 'Участок не найден' : 'MRV-данные участка недоступны'} />;
  }
  if (!plot.data) return <Empty>Участок не найден.</Empty>;

  const shownVerification = verification.data && verification.data.verification_id === selectedId ? verification.data : null;
  const decision = latestVerification.data?.decision;

  return (
    <div className="dashboard">
      {plot.error && <ErrorNotice error={plot.error} onRetry={refresh} compact title="Не удалось обновить участок (показаны прошлые данные)" />}
      <ProjectHeader plot={plot.data} plots={plots} onSelectPlot={onSelectPlot} latest={latestVerification.data} />

      <StatusStrip verification={latestVerification.data} batch={batch} operation={statusOperation} operationSource={statusSource} />

      {decision === 'FREEZE_REQUESTED' && batch?.credit_status === 'ACTIVE' && (
        <div className="state state-alert" role="status" data-testid="freeze-requested-banner">
          <strong>Приостановка запрошена · {latestVerification.data?.reason}</strong>
          <span>FROZEN будет показан только после подтверждённого receipt, события и readback в /credits.</span>
        </div>
      )}

      <div className="workspace">
        <div className="rail rail-left">
          <Section title="Evidence quality" id="quality">
            <QualityPanel verification={latestVerification.data} plot={plot.data} batch={batch} />
          </Section>
          <Section title="Наблюдения" id="observations">
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
              onSelect={(id) => setPinnedId(id === latestId ? null : id)}
              onJobSucceeded={onJobSucceeded}
              onChanged={refresh}
            />
          </Section>
        </div>

        <div className="center">
          <EvidenceMap client={client} plot={plot.data} verification={shownVerification} />
          {shownVerification && !shownVerification.is_latest && (
            <div className="state state-warn compact" role="note">
              <strong>Историческая проверка</strong>
              Карта и evidence показывают выбранное наблюдение, не последнее. Статусы вверху относятся к последнему.
            </div>
          )}
          {shownVerification && <MetricsStrip verification={shownVerification} />}
          <Section title="Пара сцен до / после" id="compare">
            {verification.loading && !shownVerification && <Skeleton label="Загрузка превью наблюдения…" height={260} />}
            {verification.error && <ErrorNotice error={verification.error} onRetry={verification.reload} compact />}
            {shownVerification ? (
              <BeforeAfter client={client} verification={shownVerification} />
            ) : (
              !verification.loading && (
                <Empty>
                  <strong>Нет наблюдения</strong>
                  <span>Для участка ещё нет обработанной пары сцен. Запустите проверку в панели «Наблюдения».</span>
                </Empty>
              )
            )}
          </Section>
        </div>

        <div className="rail rail-right">
          <section className="panel" aria-label="Evidence, реестр и proof">
            <div className="tabs" role="tablist" aria-label="Разделы проверки">
              {TABS.map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  id={`tab-${key}`}
                  aria-selected={tab === key}
                  aria-controls={`tabpanel-${key}`}
                  className={`tab${tab === key ? ' active' : ''}`}
                  onClick={() => setTab(key)}
                  data-testid={`tab-${key}`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="panel-body" role="tabpanel" id={`tabpanel-${tab}`} aria-labelledby={`tab-${tab}`}>
              {tab === 'evidence' &&
                (shownVerification ? (
                  <EvidencePanel verification={shownVerification} />
                ) : verification.loading ? (
                  <Skeleton label="Получение MRV evidence…" height={320} />
                ) : (
                  <Empty>
                    <strong>Нет evidence</strong>
                    <span>Обработанного наблюдения для участка нет.</span>
                  </Empty>
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
                  ledger={ledger}
                />
              )}
              {tab === 'proof' &&
                (shownVerification ? (
                  <ProofPanel client={client} verification={shownVerification} refreshKey={refreshKey} ledger={ledger} />
                ) : (
                  <Empty>Нет proof: нет обработанного наблюдения.</Empty>
                ))}
            </div>
          </section>
        </div>
      </div>

      <Section
        title="Журнал · наблюдение → решение → транзакция → событие"
        id="journal"
        actions={
          <button type="button" className="btn btn-small btn-secondary" onClick={refresh}>
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
  );
}
