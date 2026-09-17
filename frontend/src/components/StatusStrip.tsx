import type { ReactNode } from 'react';
import type { CreditBatch, Operation, Verification } from '../api/types';
import {
  CREDIT_META,
  DECISION_META,
  LAYER_TITLES,
  OUTCOME_META,
  QUALITY_META,
  REASON_LABELS,
  TRANSACTION_META,
  type StatusLayer,
} from '../domain/status';
import { shortHash } from '../domain/format';
import { StatusBadge } from './common';

interface Props {
  verification: Verification | null;
  batch: CreditBatch | null;
  operation: Operation | null;
  operationSource: string | null;
}

function Card({ layer, children }: { layer: StatusLayer; children: ReactNode }) {
  return (
    <div className="status-card" data-layer={layer} data-testid={`layer-${layer}`}>
      <div className="status-card-title">{LAYER_TITLES[layer]}</div>
      {children}
    </div>
  );
}

export function StatusStrip({ verification, batch, operation, operationSource }: Props) {
  const freezeRequestedButActive = verification?.decision === 'FREEZE_REQUESTED' && batch?.credit_status === 'ACTIVE';

  return (
    <div className="status-strip" aria-label="Раздельные слои статусов">
      <Card layer="outcome">
        {verification ? (
          <>
            <StatusBadge meta={OUTCOME_META[verification.evidence.outcome]} testId="value-outcome" />
            <p className="status-hint">{OUTCOME_META[verification.evidence.outcome].hint}</p>
          </>
        ) : (
          <span className="muted">Нет наблюдения</span>
        )}
      </Card>

      <Card layer="quality">
        {verification ? (
          <>
            <StatusBadge meta={QUALITY_META[verification.evidence_quality]} testId="value-quality" />
            <p className="status-hint">
              EQS: <strong>{verification.evidence_quality_score ?? 'нет оценки'}</strong>
              {verification.evidence_quality_score !== null && ' / 100'} — индикатор полноты покрытия, не вероятность.
            </p>
          </>
        ) : (
          <span className="muted">—</span>
        )}
      </Card>

      <Card layer="decision">
        {verification ? (
          <>
            <StatusBadge meta={DECISION_META[verification.decision]} testId="value-decision" />
            <p className="status-hint">
              Причина: <span data-testid="value-reason">{verification.reason}</span> — {REASON_LABELS[verification.reason]}
            </p>
          </>
        ) : (
          <span className="muted">—</span>
        )}
      </Card>

      <Card layer="operation">
        {operation ? (
          <>
            <StatusBadge meta={TRANSACTION_META[operation.transaction_state]} testId="value-operation" />
            <p className="status-hint">
              {operation.kind}
              {operationSource ? ` · ${operationSource}` : ''}
              {operation.tx_hash ? ` · tx ${shortHash(operation.tx_hash, 6)}` : ''}
            </p>
          </>
        ) : (
          <span className="muted" data-testid="value-operation-none">
            Нет активных операций
          </span>
        )}
      </Card>

      <Card layer="credit">
        {batch ? (
          <>
            <StatusBadge meta={CREDIT_META[batch.credit_status]} testId="value-credit" />
            <p className="status-hint">
              Серия #{batch.batch_id} · источник: /credits (readback{' '}
              {batch.chain_state_checked_at.slice(11, 19)} UTC)
            </p>
            {freezeRequestedButActive && (
              <p className="status-hint warn" data-testid="freeze-pending-note">
                Приостановка запрошена Backend, но подтверждённый credit_status пока ACTIVE.
              </p>
            )}
          </>
        ) : (
          <span className="muted" data-testid="value-credit-none">
            Серия не выпущена
          </span>
        )}
      </Card>
    </div>
  );
}
