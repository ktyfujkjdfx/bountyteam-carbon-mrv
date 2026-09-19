import { useId, useState } from 'react';
import type { AnalysisResult } from '../types';
import type { PriceKey } from './Headline';

function money(value: number): string {
  return `${Math.round(value).toLocaleString('ru-RU')} ₽`;
}

/**
 * Scenario value only: Q multiplied by a price the case fixes, or by a price the reader types in and
 * which is labelled as their own scenario. Nothing here is a market quote or a forecast.
 */
export function ValueCalculator({
  result,
  priceKey,
  onPriceKey,
  customPrice,
  onCustomPrice,
}: {
  result: AnalysisResult;
  priceKey: PriceKey;
  onPriceKey: (key: PriceKey) => void;
  customPrice: number | null;
  onCustomPrice: (value: number | null) => void;
}) {
  const inputId = useId();
  const [draft, setDraft] = useState(customPrice === null ? '' : String(customPrice));
  const q = result.units.q;
  const scenario = result.scenario_values;

  const rows: Array<{ key: PriceKey; label: string; price: number }> = [
    { key: 'low', label: 'Низкая цена кейса', price: scenario.low.price_rub },
    { key: 'base', label: 'Базовая цена кейса', price: scenario.base.price_rub },
    { key: 'high', label: 'Высокая цена кейса', price: scenario.high.price_rub },
  ];

  const apply = (value: string) => {
    setDraft(value);
    const parsed = Number(value.replace(',', '.'));
    if (value.trim() === '' || !Number.isFinite(parsed) || parsed < 0) onCustomPrice(null);
    else onCustomPrice(parsed);
  };

  return (
    <section className="lens-calculator" data-testid="lens-calculator" aria-label="Сценарии стоимости">
      <h3>Сценарная стоимость</h3>
      {q === null ? (
        <div className="state state-warn compact" role="status" data-testid="lens-calculator-unavailable">
          <strong>Сумма не показывается</strong>
          <span>Единицы не рассчитаны, поэтому умножать нечего.</span>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="data-table" data-testid="lens-calculator-table">
            <thead>
              <tr>
                <th>Сценарий</th>
                <th>Цена за единицу</th>
                <th>Q × цена</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className={priceKey === row.key && customPrice === null ? 'selected' : undefined}>
                  <td>
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => {
                        onPriceKey(row.key);
                        onCustomPrice(null);
                        setDraft('');
                      }}
                      data-testid={`lens-calculator-${row.key}`}
                    >
                      {row.label}
                    </button>
                  </td>
                  <td className="mono">{money(row.price)}</td>
                  <td className="mono">{money(q * row.price)}</td>
                </tr>
              ))}
              {customPrice !== null && (
                <tr className="selected" data-testid="lens-calculator-custom-row">
                  <td>Ваш сценарий</td>
                  <td className="mono">{money(customPrice)}</td>
                  <td className="mono">{money(q * customPrice)}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <label className="lens-field" htmlFor={inputId}>
        <span>Своя цена за единицу, ₽ (необязательно)</span>
        <input id={inputId} className="input" inputMode="decimal" value={draft} onChange={(event) => apply(event.target.value)} data-testid="lens-custom-price" />
      </label>
      <p className="muted small">
        Три цены заданы условиями кейса ({scenario.price_parameters_ref}). Своя цена помечается как ваш сценарий и не становится частью
        расчёта. Ни одна из сумм не является прогнозом рыночной цены, выручкой или инвестиционным советом.
      </p>
      {q === 0 && (
        <p className="muted small" data-testid="lens-calculator-zero">
          При Q = 0 сценарная стоимость равна 0 ₽ при любой цене.
        </p>
      )}
    </section>
  );
}
