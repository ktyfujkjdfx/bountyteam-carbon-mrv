import { StatusBadge, UnknownValueNote } from '../../components/common';
import { metaFor } from '../../domain/status';
import { CLAIM_META, CLAIM_REASON_TEXT } from '../status';
import type { AnalysisResult } from '../types';
import type { PriceKey } from './Headline';

function money(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${Math.round(value).toLocaleString('ru-RU')} ₽`;
}

const CLAIM_SENTENCE: Record<string, string> = {
  NOT_PROVIDED: 'Заявленный объём не введён. Расчёт от него не зависит.',
  NOT_APPLICABLE: 'Положительное заявление отсутствует: заявлен нулевой объём, сравнивать нечего.',
  NOT_COMPARABLE: 'Сравнение невозможно: заявление относится к другому контуру, периоду, пулу или единицам.',
  UNASSESSABLE: 'Оценить заявление нельзя: единицы не рассчитаны.',
  SUPPORTED_BY_CASE: 'Подтверждено расчётом в рамках методики.',
  PARTIALLY_SUPPORTED_BY_CASE: 'Подтверждено частично: часть заявленного объёма расчёт не покрывает.',
  NOT_SUPPORTED_BY_CASE: 'Заявленный объём не подтверждён расчётом.',
};

/**
 * Claimed against calculated, with the gap shown as evidence rather than as an accusation. A zero
 * claim is never called supported, and the calculated Q never moves because of what was claimed.
 */
export function ClaimStressTest({ result, priceKey }: { result: AnalysisResult; priceKey: PriceKey }) {
  const claim = result.claim;
  const meta = metaFor(CLAIM_META, claim.status);
  const gapValue = claim.scenario_gap_values ? claim.scenario_gap_values[priceKey].value_rub : null;
  const share = claim.supported_share;
  const zeroClaim = claim.claimed_units === 0;
  const zeroButSupported = zeroClaim && String(claim.status) === 'SUPPORTED_BY_CASE';

  return (
    <section className="lens-claim" data-testid="lens-claim" aria-label="Проверка заявленного объёма">
      <header className="batch-header">
        <h3>Заявлено и подтверждено</h3>
        <StatusBadge meta={meta} testId="lens-claim-status" />
      </header>
      <UnknownValueNote meta={meta} />

      <p data-testid="lens-claim-sentence">{CLAIM_SENTENCE[String(claim.status)] ?? meta.hint}</p>

      {zeroButSupported && (
        <div className="state state-warn compact" role="status" data-testid="lens-claim-zero-warning">
          <strong>Заявлен нулевой объём</strong>
          <span>
            Сервис прислал статус «подтверждено расчётом» для заявления в 0 единиц. Нулевое заявление не является подтверждённым: считайте
            его отсутствующим до исправления на стороне сервиса.
          </span>
        </div>
      )}

      <div className="lens-claim-grid">
        <div className="lens-metric" data-testid="lens-claim-claimed">
          <span className="lens-metric-label">Заявлено владельцем</span>
          <span className="lens-metric-value">{claim.claimed_units === null ? '—' : claim.claimed_units.toLocaleString('ru-RU')}</span>
          <span className="lens-metric-note">{String(claim.origin) === 'DEMO_INPUT' ? 'демонстрационный ввод' : 'пользовательский ввод, не данные организаторов'}</span>
        </div>
        <div className="lens-metric" data-testid="lens-claim-q">
          <span className="lens-metric-label">Рассчитано Q</span>
          <span className="lens-metric-value">{claim.q === null ? 'не рассчитано' : claim.q.toLocaleString('ru-RU')}</span>
          <span className="lens-metric-note">по методике кейса</span>
        </div>
        <div className="lens-metric" data-testid="lens-claim-share">
          <span className="lens-metric-label">Подтверждённая доля</span>
          <span className="lens-metric-value">{share === null ? '—' : `${Math.round(share * 100)} %`}</span>
          <span className="lens-metric-note">доля заявления, покрытая расчётом</span>
        </div>
        <div className="lens-metric" data-testid="lens-claim-gap">
          <span className="lens-metric-label">Неподтверждённый разрыв</span>
          <span className="lens-metric-value">{claim.gap_units === null ? '—' : claim.gap_units.toLocaleString('ru-RU')}</span>
          <span className="lens-metric-note">{gapValue === null ? 'сценарная стоимость не вычисляется' : `сценарная стоимость ${money(gapValue)}`}</span>
        </div>
      </div>

      {share !== null && (
        <div className="lens-claim-bar" aria-hidden="true">
          <span className="supported" style={{ width: `${Math.round(share * 100)}%` }} />
        </div>
      )}

      {claim.mismatch_reasons.length > 0 && (
        <ul className="limitations small" data-testid="lens-claim-reasons">
          {claim.mismatch_reasons.map((reason) => (
            <li key={String(reason)}>{CLAIM_REASON_TEXT[String(reason)] ?? String(reason)}</li>
          ))}
        </ul>
      )}

      <dl className="fields" data-testid="lens-claim-scope">
        <div className="field">
          <dt>Контур сравнения</dt>
          <dd className="mono small">{claim.scope.geometry_hash.slice(0, 18)}…</dd>
        </div>
        <div className="field">
          <dt>Период сравнения</dt>
          <dd className="mono">
            {claim.scope.year_start}–{claim.scope.year_end}
          </dd>
        </div>
        <div className="field">
          <dt>Пул и единицы</dt>
          <dd className="mono small">
            {claim.scope.pool} · {claim.scope.unit}
          </dd>
        </div>
      </dl>
      <p className="muted small">{claim.scope_note}</p>
      <p className="muted small">
        Разрыв — это разница между заявленным объёмом и расчётом по методике кейса. Это не доказанный ущерб, не вероятностная оценка риска
        и не доказательство недобросовестности.
      </p>
    </section>
  );
}
