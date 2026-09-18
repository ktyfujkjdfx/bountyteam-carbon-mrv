import { metaFor } from '../../domain/status';
import { StatusBadge, UnknownValueNote } from '../../components/common';
import { CALCULATION_META, CLAIM_META, EVIDENCE_META, UNAVAILABLE_REASON_LABELS, ZERO_REASON_LABELS } from '../status';
import type { LensResult } from '../types';

function formatUnits(value: number): string {
  return value.toLocaleString('ru-RU');
}

function formatRub(value: number): string {
  return `${value.toLocaleString('ru-RU')} ₽`;
}

export function SummaryPanel({ result, priceId, onPrice }: { result: LensResult; priceId: string; onPrice: (id: string) => void }) {
  const { units, claim, prices } = result;
  const price = prices.find((p) => p.id === priceId) ?? prices[0] ?? null;
  const calculation = metaFor(CALCULATION_META, result.calculation_status);
  const evidence = metaFor(EVIDENCE_META, result.evidence_status);
  const claimMeta = metaFor(CLAIM_META, claim.status);
  const reasonText =
    units.q === null
      ? (UNAVAILABLE_REASON_LABELS[String(units.reason)] ?? units.reason_detail ?? 'причина не указана Backend')
      : (ZERO_REASON_LABELS[String(units.reason)] ?? units.reason_detail ?? 'причина не указана Backend');

  const scenarioValue = units.q !== null && price ? units.q * price.rub_per_unit : null;
  const gapValue = claim.gap_units !== null && price ? claim.gap_units * price.rub_per_unit : null;

  return (
    <div className="lens-summary" data-testid="lens-summary">
      <div className="lens-summary-grid">
        <div className="lens-headline" data-testid="lens-q-block">
          <div className="label">Потенциальные единицы · {result.request.year_start}–{result.request.year_end}</div>
          {units.q === null ? (
            <>
              <div className="lens-q unavailable" data-testid="lens-q-value">
                Недоступно
              </div>
              <p className="small" data-testid="lens-q-reason">
                {reasonText}
              </p>
            </>
          ) : (
            <>
              <div className="lens-q" data-testid="lens-q-value">
                {formatUnits(units.q)}
                <small>ед.</small>
              </div>
              {units.q === 0 ? (
                <p className="small" data-testid="lens-q-reason">
                  0: {reasonText}
                </p>
              ) : (
                <p className="muted small">1 единица = 1 т CO₂-экв. после вычетов, по условиям кейса</p>
              )}
            </>
          )}
        </div>

        <div className="lens-headline">
          <div className="label">Сценарная стоимость</div>
          <div className="lens-q secondary" data-testid="lens-scenario-value">
            {scenarioValue === null ? '—' : formatRub(scenarioValue)}
          </div>
          <div className="segmented lens-prices" role="group" aria-label="Ценовой сценарий">
            {prices.map((p) => (
              <button key={p.id} type="button" aria-pressed={p.id === priceId} onClick={() => onPrice(p.id)} data-testid={`lens-price-${p.id}`}>
                {p.rub_per_unit.toLocaleString('ru-RU')}
              </button>
            ))}
          </div>
          <p className="muted small">Q × заданная цена сценария. Не прогноз рынка и не прибыль.</p>
        </div>

        <div className="lens-headline">
          <div className="label">Неподдержанная часть заявления</div>
          <div className="lens-q secondary" data-testid="lens-gap-value">
            {gapValue === null ? '—' : formatRub(gapValue)}
          </div>
          <p className="small" data-testid="lens-gap-note">
            {claim.status === 'NOT_PROVIDED'
              ? 'Заявление не введено.'
              : claim.comparable && claim.gap_units !== null
                ? `Разрыв ${formatUnits(claim.gap_units)} ед. между заявлением и расчётом по условиям кейса.`
                : 'Сравнение недоступно, см. статус заявления.'}
          </p>
        </div>
      </div>

      <div className="badge-row lens-badges" data-testid="lens-badges">
        <StatusBadge meta={calculation} testId="lens-status-calculation" />
        <StatusBadge meta={evidence} testId="lens-status-evidence" />
        <StatusBadge meta={claimMeta} testId="lens-status-claim" />
        <span className="badge tone-neutral" title="Версия паспорта результата" data-testid="lens-status-passport">
          ПАСПОРТ {result.passport.schema_version}
        </span>
      </div>
      <UnknownValueNote meta={calculation} />
      <UnknownValueNote meta={evidence} />
      <UnknownValueNote meta={claimMeta} />
      {claim.status !== 'NOT_PROVIDED' && claim.reasons.length > 0 && (
        <ul className="limitations small" data-testid="lens-claim-reasons">
          {claim.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      {claim.status !== 'NOT_PROVIDED' && <p className="muted small">{claim.scope_note}</p>}
    </div>
  );
}
