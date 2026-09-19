import { StatusBadge, UnknownValueNote } from '../../components/common';
import { metaFor } from '../../domain/status';
import { CALCULATION_META, EVIDENCE_META, UNAVAILABLE_REASON_TEXT, ZERO_REASON_TEXT } from '../status';
import type { AnalysisResult } from '../types';

export type PriceKey = 'low' | 'base' | 'high';

const PRICE_LABEL: Record<PriceKey, string> = { low: 'Низкая', base: 'Базовая', high: 'Высокая' };

function money(value: number): string {
  return `${Math.round(value).toLocaleString('ru-RU')} ₽`;
}

function num(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? '—' : value.toLocaleString('ru-RU', { maximumFractionDigits: digits });
}

/** One sentence a reader without GIS background can act on. */
export function headlineSentence(result: AnalysisResult): { tone: 'ok' | 'neutral' | 'review'; title: string; text: string } {
  const q = result.units.q;
  if (String(result.calculation_status) === 'UNAVAILABLE' || q === null) {
    const reason = result.units.unavailable_reason;
    return {
      tone: 'neutral',
      title: 'Недостаточно данных для расчёта',
      text: `Потенциальные единицы не рассчитаны: ${UNAVAILABLE_REASON_TEXT[String(reason)] ?? 'не хватает обязательных данных'}.`,
    };
  }
  if (q === 0) {
    const reason = result.units.zero_reason;
    return {
      tone: 'neutral',
      title: 'Расчёт выполнен, дополнительный эффект не подтверждён',
      text: `Потенциальные единицы равны нулю: ${ZERO_REASON_TEXT[String(reason)] ?? 'по правилам кейса единиц не образуется'}.`,
    };
  }
  return {
    tone: 'ok',
    title: 'Дополнительный эффект подтверждён',
    text: `После базовой линии, неопределённости и резерва подтверждено ${q.toLocaleString('ru-RU')} потенциальных единиц по методике кейса.`,
  };
}

interface Props {
  result: AnalysisResult;
  priceKey: PriceKey;
  onPriceKey: (key: PriceKey) => void;
  customPrice: number | null;
}

/**
 * The first screen: four numbers and one sentence. Everything else lives one click deeper, so the
 * reader is never asked to parse provenance or an internal enum to learn the outcome.
 */
export function Headline({ result, priceKey, onPriceKey, customPrice }: Props) {
  const sentence = headlineSentence(result);
  const q = result.units.q;
  const scenario = result.scenario_values;
  const price = customPrice ?? scenario[priceKey].price_rub;
  const value = q === null ? null : q * price;

  return (
    <section className="lens-headline-block" data-testid="lens-headline" aria-label="Главный результат">
      <div className={`lens-verdict tone-${sentence.tone}`} data-testid="lens-verdict" data-tone={sentence.tone}>
        <strong>{sentence.title}</strong>
        <span>{sentence.text}</span>
      </div>

      <div className="lens-headline-grid">
        <div className="lens-metric primary" data-testid="lens-q">
          <span className="lens-metric-label">
            Потенциальные единицы Q
            <span className="lens-hint" title="Единицы по правилам кейса, не сертифицированные кредиты. Одна единица — одна тонна CO₂-эквивалента после вычетов.">
              ?
            </span>
          </span>
          <span className="lens-metric-value">{q === null ? 'Не рассчитано' : q.toLocaleString('ru-RU')}</span>
          <span className="lens-metric-note">
            {result.request.year_start}–{result.request.year_end}
          </span>
        </div>

        <div className="lens-metric" data-testid="lens-eproj">
          <span className="lens-metric-label">
            Углеродный эффект Eproj
            <span className="lens-hint" title="Изменение запаса углерода за период в CO₂-эквиваленте. Положительное значение — потеря учитываемого пула.">
              ?
            </span>
          </span>
          <span className="lens-metric-value">{num(result.change.eproj_tco2e)}</span>
          <span className="lens-metric-note">т CO₂-экв. за период</span>
        </div>

        <div className="lens-metric" data-testid="lens-r">
          <span className="lens-metric-label">
            Эффект относительно baseline R
            <span className="lens-hint" title="Разница между результатом периода и базовой линией кейса. Только положительный R может дать единицы.">
              ?
            </span>
          </span>
          <span className="lens-metric-value">{num(result.units.r_tco2e)}</span>
          <span className="lens-metric-note">т CO₂-экв.</span>
        </div>

        <div className="lens-metric" data-testid="lens-value">
          <span className="lens-metric-label">Сценарная стоимость</span>
          <span className="lens-metric-value">{value === null ? '—' : money(value)}</span>
          <span className="lens-metric-note">
            {customPrice === null ? `цена кейса ${PRICE_LABEL[priceKey].toLowerCase()} · ${money(price)} за единицу` : `ваш сценарий · ${money(price)} за единицу`}
          </span>
        </div>
      </div>

      <div className="lens-price-row" role="group" aria-label="Сценарий цены">
        {(['low', 'base', 'high'] as PriceKey[]).map((key) => (
          <button
            key={key}
            type="button"
            className={`chip${priceKey === key && customPrice === null ? ' active' : ''}`}
            onClick={() => onPriceKey(key)}
            aria-pressed={priceKey === key && customPrice === null}
            data-testid={`lens-price-${key}`}
          >
            {PRICE_LABEL[key]} · {money(scenario[key].price_rub)}
          </button>
        ))}
      </div>

      <div className="lens-badges">
        <StatusBadge meta={metaFor(CALCULATION_META, result.calculation_status)} testId="lens-status-calculation" />
        <StatusBadge meta={metaFor(EVIDENCE_META, result.evidence_status)} testId="lens-status-evidence" />
      </div>
      <UnknownValueNote meta={metaFor(CALCULATION_META, result.calculation_status)} />
      <UnknownValueNote meta={metaFor(EVIDENCE_META, result.evidence_status)} />
      <p className="muted small">Сценарная стоимость — это Q, умноженное на заданную кейсом цену. Не прогноз рынка, не доход и не оценка ущерба.</p>
    </section>
  );
}
