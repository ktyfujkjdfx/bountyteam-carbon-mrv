import { useEffect, useState } from 'react';
import type { MrvApiClient } from '../api/client';
import { isTerminalOperation } from '../api/polling';
import {
  DEMO_ACTORS,
  POSITIVE_UINT_STRING,
  type BuyRequest,
  type CreditBatch,
  type Credits,
  type DemoActor,
  type IssueRequest,
  type Operation,
  type Plot,
  type TransferRequest,
} from '../api/types';
import { CREDIT_META, TRANSACTION_META, metaFor } from '../domain/status';
import { formatUintString, formatUtc } from '../domain/format';
import { useTrackedAction, type TrackedAction } from '../hooks/useTrackedAction';
import type { ApiError } from '../api/errors';
import { Empty, ErrorNotice, Field, Hash, LedgerNote, Loading, StatusBadge } from './common';
import type { LedgerKind } from './Dashboard';

export interface OperationReport {
  source: string;
  operation: Operation | null;
  active: boolean;
}

interface Props {
  client: MrvApiClient;
  scope: string;
  plot: Plot;
  actor: DemoActor;
  credits: Credits | null;
  creditsError: ApiError | null;
  creditsLoading: boolean;
  onReloadCredits: () => void;
  demoAuthorizationId: string;
  onChanged: () => void;
  onOperation: (report: OperationReport) => void;
  onRejected: (message: string) => void;
  ledger: LedgerKind;
}

function OperationStatus({ action, label }: { action: TrackedAction<unknown, Operation>; label: string }) {
  if (action.phase === 'idle') return null;
  const op = action.status;
  return (
    <div className="op-status" data-testid={`op-status-${label}`} aria-live="polite">
      {action.phase === 'submitting' && <Loading label="Отправка запроса в Backend…" />}
      {op && (
        <div>
          <StatusBadge meta={metaFor(TRANSACTION_META, op.transaction_state)} testId={`op-state-${label}`} /> {op.kind}{' '}
          <span className="mono small">{op.operation_id}</span>
          {op.transaction_state === 'SUBMITTED' && <div className="muted small">Receipt ещё не подтверждён — это не финальный результат.</div>}
          {op.tx_hash && (
            <div className="small">
              tx <Hash value={op.tx_hash} />
            </div>
          )}
          {op.receipt && (
            <div className="small">
              receipt: block {op.receipt.block_number}, status {op.receipt.status}, events {op.receipt.event_names.join(', ')}, readback{' '}
              {op.receipt.state_readback_ok ? 'ok' : 'нет'}
            </div>
          )}
          {op.error && (
            <div className="small warn">
              {op.error.code}: {op.error.message}
            </div>
          )}
        </div>
      )}
      {action.phase === 'timeout' && (
        <div className="state state-warn">
          Операция всё ещё {op?.transaction_state ?? 'в обработке'} — опрос приостановлен без изменения статуса.{' '}
          <button type="button" className="btn btn-small" onClick={action.resume}>
            Продолжить опрос
          </button>
        </div>
      )}
      {action.error && <ErrorNotice error={action.error} compact onRetry={action.statusUrl ? action.resume : undefined} />}
    </div>
  );
}

function useOperationAction<TBody>(
  client: MrvApiClient,
  intentKey: string,
  kind: 'issue' | 'buy' | 'transfer',
  submit: (body: TBody, key: string, signal: AbortSignal) => Promise<{ status_url: string }>,
  onChanged: () => void,
) {
  return useTrackedAction<TBody, Operation>({
    intentKey,
    kind,
    submit: async (body, key, signal) => ({ statusUrl: (await submit(body, key, signal)).status_url }),
    fetchStatus: (url, signal) => client.getOperation(url, { signal }),
    isTerminal: isTerminalOperation,
    onSettled: onChanged,
  });
}

function BatchCard({
  client,
  scope,
  batch,
  actor,
  onChanged,
  onOperation,
  onRejected,
}: {
  client: MrvApiClient;
  scope: string;
  batch: CreditBatch;
  actor: DemoActor;
  onChanged: () => void;
  onOperation: (report: OperationReport) => void;
  onRejected: (message: string) => void;
}) {
  const [buyAmount, setBuyAmount] = useState('10');
  const [transferAmount, setTransferAmount] = useState('1');
  const [toActor, setToActor] = useState<DemoActor>(actor === 'recipient' ? 'buyer' : 'recipient');

  const buy = useOperationAction<BuyRequest>(
    client,
    `${scope}|batch:${batch.batch_id}|buy|${actor}`,
    'buy',
    (body, key, signal) => client.buyCredits(batch.batch_id, actor, body, { idempotencyKey: key, signal }),
    onChanged,
  );
  const transfer = useOperationAction<TransferRequest>(
    client,
    `${scope}|batch:${batch.batch_id}|transfer|${actor}`,
    'transfer',
    (body, key, signal) => client.transferCredits(batch.batch_id, actor, body, { idempotencyKey: key, signal }),
    onChanged,
  );

  useEffect(() => {
    if (buy.phase !== 'idle') onOperation({ source: `buy (${actor})`, operation: buy.status, active: buy.busy });
  }, [buy.phase, buy.status, buy.busy, actor, onOperation]);
  useEffect(() => {
    if (transfer.phase !== 'idle') onOperation({ source: `transfer (${actor})`, operation: transfer.status, active: transfer.busy });
  }, [transfer.phase, transfer.status, transfer.busy, actor, onOperation]);
  useEffect(() => {
    if (transfer.phase === 'error' && transfer.error?.status) {
      onRejected(`Transfer отклонён Backend: HTTP ${transfer.error.status} ${transfer.error.code ?? ''} — ${transfer.error.message}`);
    }
  }, [transfer.phase, transfer.error, onRejected]);

  const frozen = batch.credit_status === 'FROZEN';
  const creditMeta = metaFor(CREDIT_META, batch.credit_status);
  const buyValid = POSITIVE_UINT_STRING.test(buyAmount);
  const transferValid = POSITIVE_UINT_STRING.test(transferAmount) && toActor !== actor;

  return (
    <article className={`registry-record${frozen ? ' frozen' : ''}`} data-testid={`batch-${batch.batch_id}`}>
      <header className="batch-header">
        <h3>Запись реестра · серия #{batch.batch_id}</h3>
        <StatusBadge meta={creditMeta} testId="batch-credit-status" />
      </header>
      <div className="batch-state">
        <div className="label">Credit state · readback /credits</div>
        <div className="batch-state-value" data-state={batch.credit_status}>
          {batch.credit_status}
        </div>
        {frozen ? (
          <p className="state state-blocked compact" data-testid="frozen-explainer">
            FROZEN подтверждён чтением контракта {batch.frozen_at ? `(${formatUtc(batch.frozen_at)})` : ''}. Это временное ограничение
            прототипа, не юридическое аннулирование; балансы сохранены.
          </p>
        ) : (
          <p className={creditMeta.unknown ? 'small warn' : 'small muted'} data-testid={creditMeta.unknown ? 'unknown-value-note' : undefined}>
            {creditMeta.hint}
          </p>
        )}
      </div>
      <div className="batch-body">
        <dl className="balances">
          <div>
            <dt>Total supply</dt>
            <dd>
              {formatUintString(batch.total_supply)}
              <span className="unit">ед.</span>
            </dd>
          </div>
          <div>
            <dt>Seller</dt>
            <dd>
              <span data-testid="seller-balance">{formatUintString(batch.seller_balance)}</span>
              <span className="unit">ед.</span>
            </dd>
          </div>
          <div>
            <dt>Актор · {batch.actor}</dt>
            <dd>
              <span data-testid="actor-balance">{formatUintString(batch.actor_balance)}</span>
              <span className="unit">ед.</span>
            </dd>
          </div>
        </dl>
        <dl className="fields">
          <Field label="Unit price">
            <span className="mono">{formatUintString(batch.unit_price_wei)}</span> wei · тестовая валюта, без ценности
          </Field>
          <Field label="Seller address">
            <Hash value={batch.seller} />
          </Field>
          <Field label="Выпуск / наблюдение">
            <span className="mono">
              {formatUtc(batch.issued_at)} / {formatUtc(batch.last_observed_at)}
            </span>
          </Field>
          <Field label="Evidence hash серии">
            <Hash value={batch.evidence_hash} />
            <div className="muted small">Значение Backend для серии; связь с конкретной проверкой — во вкладке Proof.</div>
          </Field>
          <Field label="Chain state checked">
            <span className="mono">{formatUtc(batch.chain_state_checked_at)}</span>
          </Field>
        </dl>
      </div>

      <div className="action-grid">
        <form
          className="action"
          onSubmit={(e) => {
            e.preventDefault();
            if (buyValid) void buy.run({ amount: buyAmount });
          }}
        >
          <h4>Тестовая покупка</h4>
          <label>
            Количество (целые единицы)
            <input value={buyAmount} onChange={(e) => setBuyAmount(e.target.value.trim())} inputMode="numeric" aria-invalid={!buyValid} />
          </label>
          <button type="submit" className="btn" disabled={!batch.can_buy || !buyValid || buy.busy} data-testid="buy-submit">
            {buy.busy ? 'Покупка в процессе…' : 'Купить'}
          </button>
          {!batch.can_buy && (
            <p className="muted small" data-testid="buy-disabled-reason">
              Backend: can_buy = false{frozen ? ' (серия FROZEN)' : actor === 'issuer' ? ' (issuer — продавец)' : ''}.
            </p>
          )}
          <OperationStatus action={buy as TrackedAction<unknown, Operation>} label="buy" />
        </form>

        <form
          className="action"
          onSubmit={(e) => {
            e.preventDefault();
            if (transferValid) void transfer.run({ to_actor: toActor, amount: transferAmount });
          }}
        >
          <h4>Передача своих единиц</h4>
          <label>
            Получатель
            <select value={toActor} onChange={(e) => setToActor(e.target.value as DemoActor)}>
              {DEMO_ACTORS.filter((a) => a !== actor).map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </label>
          <label>
            Количество
            <input
              value={transferAmount}
              onChange={(e) => setTransferAmount(e.target.value.trim())}
              inputMode="numeric"
              aria-invalid={!POSITIVE_UINT_STRING.test(transferAmount)}
            />
          </label>
          <button
            type="submit"
            className="btn"
            disabled={frozen || !batch.can_transfer_backend || !transferValid || transfer.busy}
            data-testid="transfer-submit"
          >
            {transfer.busy ? 'Передача в процессе…' : 'Передать'}
          </button>
          {frozen ? (
            <div className="small" data-testid="transfer-disabled-reason">
              <p className="warn">
                Передача отключена: серия FROZEN. Кнопка отключена только в UI — окончательный запрет обеспечивает смарт-контракт
                (BatchNotActive).
              </p>
              <button
                type="button"
                className="btn btn-small btn-ghost"
                disabled={!transferValid || transfer.busy}
                onClick={() => void transfer.run({ to_actor: toActor, amount: transferAmount })}
                data-testid="transfer-attempt-frozen"
              >
                Отправить попытку в Backend (ожидается отказ)
              </button>
            </div>
          ) : (
            !batch.can_transfer_backend && (
              <p className="muted small" data-testid="transfer-disabled-reason">
                Backend: can_transfer_backend = false.
              </p>
            )
          )}
          <OperationStatus action={transfer as TrackedAction<unknown, Operation>} label="transfer" />
        </form>
      </div>
    </article>
  );
}

export function CreditsPanel(props: Props) {
  const { client, scope, plot, actor, credits, creditsError, creditsLoading, onReloadCredits, demoAuthorizationId, onChanged, onOperation, onRejected, ledger } =
    props;
  const [authorizationId, setAuthorizationId] = useState(demoAuthorizationId);

  const issue = useOperationAction<IssueRequest>(
    client,
    `${scope}|plot:${plot.plot_id}|issue`,
    'issue',
    (body, key, signal) => client.issueBatch(plot.plot_id, actor, body, { idempotencyKey: key, signal }),
    onChanged,
  );

  useEffect(() => {
    if (issue.phase !== 'idle') onOperation({ source: 'issue', operation: issue.status, active: issue.busy });
  }, [issue.phase, issue.status, issue.busy, onOperation]);

  const items = credits?.items ?? [];
  const authValid = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$/.test(authorizationId);

  return (
    <div className="credits" data-testid="credits-panel">
      <LedgerNote ledger={ledger} />
      {creditsLoading && !credits && <Loading label="Загрузка серий и балансов…" />}
      {creditsError && (
        <ErrorNotice
          error={creditsError}
          onRetry={onReloadCredits}
          title={credits ? 'Не удалось обновить балансы (показаны последние подтверждённые)' : undefined}
        />
      )}

      <form
        className="action issue"
        onSubmit={(e) => {
          e.preventDefault();
          if (authValid) void issue.run({ demo_authorization_id: authorizationId });
        }}
      >
        <h4>Выпуск тестовой серии (demo authorization)</h4>
        <label>
          demo_authorization_id
          <input value={authorizationId} onChange={(e) => setAuthorizationId(e.target.value.trim())} aria-invalid={!authValid} />
        </label>
        <button type="submit" className="btn" disabled={!plot.can_issue || !authValid || issue.busy} data-testid="issue-submit">
          {issue.busy ? 'Выпуск в процессе…' : 'Выпустить серию'}
        </button>
        {!plot.can_issue && (
          <p className="muted small" data-testid="issue-disabled-reason">
            Backend: can_issue = false{plot.action_block_reason ? ` — ${plot.action_block_reason}` : actor !== 'issuer' ? ' (нужен актор issuer)' : ''}.
          </p>
        )}
        <OperationStatus action={issue as TrackedAction<unknown, Operation>} label="issue" />
      </form>

      {credits && items.length === 0 && (
        <Empty>
          <strong>Серия не выпущена</strong>
          <span>Записей реестра для участка нет. Количество единиц задаёт demo authorization, а не NDVI или гектары.</span>
        </Empty>
      )}
      {items.map((batch) => (
        <BatchCard
          key={batch.batch_id}
          client={client}
          scope={scope}
          batch={batch}
          actor={actor}
          onChanged={onChanged}
          onOperation={onOperation}
          onRejected={onRejected}
        />
      ))}
    </div>
  );
}
