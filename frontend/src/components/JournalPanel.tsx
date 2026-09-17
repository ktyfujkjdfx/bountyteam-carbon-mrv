import { useCallback, useState } from 'react';
import type { MrvApiClient } from '../api/client';
import { toApiError, type ApiError } from '../api/errors';
import type { ApiEvent, Events } from '../api/types';
import type { Tone } from '../domain/status';
import { formatUtc, shortHash } from '../domain/format';
import { Badge, Empty, ErrorNotice, Loading } from './common';

export interface ClientLogEntry {
  id: string;
  at: string;
  message: string;
}

const KIND_TONE: Record<ApiEvent['kind'], Tone> = {
  VERIFICATION: 'neutral',
  DECISION: 'review',
  TX_SUBMITTED: 'info',
  TX_CONFIRMED: 'ok',
  TX_FAILED: 'blocked',
};

interface Props {
  client: MrvApiClient;
  plotId: string;
  events: Events | null;
  eventsError: ApiError | null;
  eventsLoading: boolean;
  onReload: () => void;
  clientLog: ClientLogEntry[];
}

export function JournalPanel({ client, plotId, events, eventsError, eventsLoading, onReload, clientLog }: Props) {
  const [pages, setPages] = useState<{ base: Events | null; items: ApiEvent[]; cursor: string | null }>({
    base: null,
    items: [],
    cursor: null,
  });
  const [moreError, setMoreError] = useState<ApiError | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  const current = pages.base === events ? pages : { base: events, items: [], cursor: events?.next_cursor ?? null };
  const older = current.items;
  const cursor = current.cursor;

  const loadMore = useCallback(() => {
    if (!cursor) return;
    setLoadingMore(true);
    client
      .listEvents({ plotId, cursor })
      .then((page) => {
        setPages({ base: events, items: [...older, ...page.items], cursor: page.next_cursor });
        setMoreError(null);
      })
      .catch((err: unknown) => setMoreError(toApiError(err)))
      .finally(() => setLoadingMore(false));
  }, [client, plotId, cursor, events, older]);

  const seen = new Set<string>();
  const merged = [...(events?.items ?? []), ...older]
    .filter((e) => (seen.has(e.event_id) ? false : (seen.add(e.event_id), true)))
    .sort((a, b) => b.occurred_at.localeCompare(a.occurred_at));

  return (
    <div className="journal" data-testid="journal">
      {eventsLoading && !events && <Loading label="Загрузка журнала…" />}
      {eventsError && <ErrorNotice error={eventsError} onRetry={onReload} compact title={events ? 'Журнал не обновлён (показаны прошлые записи)' : undefined} />}
      {clientLog.length > 0 && (
        <ul className="timeline client-log" aria-label="Ответы Backend в этой сессии">
          {clientLog.map((entry) => (
            <li key={entry.id} data-testid="client-log-entry">
              <span className="timeline-time">{entry.at}</span>
              <div className="timeline-body">
                <span>
                  <Badge tone="blocked">UI: ответ Backend</Badge>
                </span>
                <span>{entry.message}</span>
                <span className="muted small">Локальная запись клиента, не событие Backend или контракта.</span>
              </div>
            </li>
          ))}
        </ul>
      )}
      {events && merged.length === 0 && (
        <Empty>
          <strong>Событий пока нет</strong>
          <span>Наблюдения, решения и транзакции появятся здесь по мере обработки Backend.</span>
        </Empty>
      )}
      {merged.length > 0 && (
        <ol className="timeline" aria-label="Журнал событий Backend">
          {merged.map((event) => (
            <li key={event.event_id} data-testid="journal-event" data-kind={event.kind}>
              <span className="timeline-time">{formatUtc(event.occurred_at)}</span>
              <div className="timeline-body">
                <span>
                  <Badge tone={KIND_TONE[event.kind]}>{event.kind}</Badge>
                </span>
                <span>{event.message}</span>
                <span className="mono">
                  {event.verification_id && `verification ${shortHash(event.verification_id, 8)} `}
                  {event.operation_id && `op ${shortHash(event.operation_id, 8)} `}
                  {event.batch_id && `batch #${event.batch_id} `}
                  {event.tx_hash && `tx ${shortHash(event.tx_hash, 8)}`}
                </span>
              </div>
            </li>
          ))}
        </ol>
      )}
      {moreError && <ErrorNotice error={moreError} compact onRetry={loadMore} />}
      {cursor && (
        <button type="button" className="btn btn-small" onClick={loadMore} disabled={loadingMore}>
          {loadingMore ? 'Загрузка…' : 'Показать более ранние'}
        </button>
      )}
    </div>
  );
}
