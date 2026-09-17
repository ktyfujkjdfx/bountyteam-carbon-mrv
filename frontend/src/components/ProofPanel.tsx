import { useState } from 'react';
import type { MrvApiClient } from '../api/client';
import { toApiError, type ApiError } from '../api/errors';
import type { Verification, VerificationEvidence } from '../api/types';
import { useResource } from '../hooks/useResource';
import { Badge, Empty, ErrorNotice, Field, Hash, LedgerNote, Loading } from './common';
import type { LedgerKind } from './Dashboard';

interface Props {
  client: MrvApiClient;
  verification: Verification;
  refreshKey: number;
  ledger: LedgerKind;
}

export function ProofPanel({ client, verification, refreshKey, ledger }: Props) {
  const id = verification.verification_id;
  const proof = useResource((signal) => client.getProof(id, { signal }), [client, id, refreshKey]);
  const [canonical, setCanonical] = useState<{ data: VerificationEvidence | null; error: ApiError | null; loading: boolean }>({
    data: null,
    error: null,
    loading: false,
  });

  const loadCanonical = () => {
    setCanonical({ data: null, error: null, loading: true });
    client
      .getCanonicalEvidence(id)
      .then((data) => setCanonical({ data, error: null, loading: false }))
      .catch((err: unknown) => setCanonical({ data: null, error: toApiError(err), loading: false }));
  };

  if (proof.loading && !proof.data) return <Loading label="Загрузка proof…" />;
  if (proof.error && !proof.data) return <ErrorNotice error={proof.error} onRetry={proof.reload} />;
  if (!proof.data) return <Empty>Нет proof.</Empty>;
  const data = proof.data;

  return (
    <div className="proof" data-testid="proof-panel">
      {proof.error && <ErrorNotice error={proof.error} onRetry={proof.reload} compact title="Не удалось обновить proof (показаны прошлые данные)" />}
      <dl className="fields">
        <Field label="Проверка">
          <span className="mono">{id}</span> {verification.is_latest ? <Badge tone="info">latest</Badge> : <Badge tone="review">историческая</Badge>}
        </Field>
        <Field label="Evidence hash (сохранён Backend)">
          <Hash value={data.evidence_hash} />
        </Field>
        <Field label="Recomputed hash (Backend)">
          <Hash value={data.recomputed_hash} />
        </Field>
        <Field label="Integrity (Backend)">
          <Badge tone={data.integrity_ok ? 'ok' : 'blocked'}>{data.integrity_ok ? 'integrity_ok: true' : 'integrity_ok: false'}</Badge>
          <span className="muted small"> Хеш вычисляет Backend (SHA-256 JCS); UI его не пересчитывает.</span>
        </Field>
        <Field label="Decision hash">
          <Hash value={data.decision_hash} />
        </Field>
        <Field label="Canonical">
          <span className="mono small">{data.canonical_url}</span>{' '}
          <button type="button" className="btn btn-small" onClick={loadCanonical} disabled={canonical.loading}>
            {canonical.loading ? 'Загрузка…' : 'Загрузить canonical evidence'}
          </button>
        </Field>
      </dl>
      {canonical.error && <ErrorNotice error={canonical.error} compact onRetry={loadCanonical} />}
      {canonical.data && (
        <p className="small" data-testid="canonical-loaded">
          Canonical evidence получен: dataset_kind {canonical.data.dataset_kind}, outcome {canonical.data.outcome}, plot {canonical.data.plot_id}.
        </p>
      )}

      <h3>On-chain anchors этого evidence</h3>
      {data.anchors.length === 0 ? (
        <Empty>
          <span data-testid="no-anchors">
            Для этого evidence нет подтверждённого on-chain anchor. Anchors других проверок ему не приписываются.
          </span>
        </Empty>
      ) : (
        <ul className="anchors" data-testid="anchors">
          {data.anchors.map((anchor) => (
            <li key={`${anchor.event_name}-${anchor.tx_hash}`}>
              <Badge tone={anchor.event_name === 'Frozen' ? 'blocked' : 'ok'}>{anchor.event_name}</Badge> batch #{anchor.batch_id}
              {anchor.confirmed && <Badge tone="ok">confirmed</Badge>}
              <div className="small">
                tx <Hash value={anchor.tx_hash} />
              </div>
              <div className="small">
                evidence <Hash value={anchor.evidence_hash} />
              </div>
              {anchor.decision_hash && (
                <div className="small">
                  decision <Hash value={anchor.decision_hash} />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <LedgerNote ledger={ledger} />

    </div>
  );
}
