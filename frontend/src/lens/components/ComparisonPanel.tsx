import { Empty, StatusBadge } from '../../components/common';
import { metaFor } from '../../domain/status';
import { CALCULATION_META, EVIDENCE_META, UNAVAILABLE_REASON_LABELS, ZERO_REASON_LABELS } from '../status';
import type { LensRun } from '../session';
import type { LensResult } from '../types';

function num(value: number | null | undefined, digits = 2, unit = ''): string {
  if (value === null || value === undefined) return '—';
  return `${value.toLocaleString('ru-RU', { maximumFractionDigits: digits })}${unit ? ` ${unit}` : ''}`;
}

function periodOf(result: LensResult): string {
  return `${result.request.year_start}–${result.request.year_end}`;
}

function qText(result: LensResult): string {
  if (result.units.q === null) return 'Недоступно';
  return result.units.q.toLocaleString('ru-RU');
}

function coverageOf(result: LensResult, id: string): string {
  const axis = result.coverage.find((entry) => entry.id === id);
  if (!axis || axis.covered_fraction === null) return '—';
  return `${Math.round(axis.covered_fraction * 100)} %`;
}

/**
 * Side-by-side reading of runs already made in this session. Values are the ones each result carried;
 * the only arithmetic here is Q × the selected scenario price, which the case defines as a scenario value.
 * There is no ranking and no recommendation: different areas, periods or method versions are reported as
 * limits of the comparison instead of being averaged away.
 */
export function ComparisonPanel({ runs, priceId }: { runs: readonly LensRun[]; priceId: string }) {
  const selected = runs.slice(0, 4);
  if (selected.length < 2) {
    return (
      <Empty>
        <strong>Сравнивать пока нечего</strong>
        <span data-testid="lens-comparison-empty">
          Выполните хотя бы два расчёта в этой сессии — сравнение строится только по полученным результатам, без подстановки значений.
        </span>
      </Empty>
    );
  }

  const periods = new Set(selected.map((run) => periodOf(run.result)));
  const methods = new Set(selected.map((run) => run.result.passport.method_version));
  const areas = selected.map((run) => run.result.area_ha);
  const minArea = Math.min(...areas);
  const maxArea = Math.max(...areas);
  const areasDiffer = minArea > 0 && maxArea / minArea > 1.05;

  return (
    <div className="lens-comparison" data-testid="lens-comparison">
      <div className="table-wrap">
        <table className="data-table" data-testid="lens-comparison-table">
          <thead>
            <tr>
              <th scope="col">Показатель</th>
              {selected.map((run) => (
                <th key={run.run_id} scope="col">
                  {run.request.aoi_id ?? run.request.parent_aoi_id ?? 'контур пользователя'}
                  <div className="muted small mono">{periodOf(run.result)}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Q, потенциальные единицы</th>
              {selected.map((run) => (
                <td key={run.run_id} className="mono" data-testid={`lens-compare-q-${run.run_id}`}>
                  {qText(run.result)}
                  {run.result.units.reason && (
                    <div className="muted small">
                      {ZERO_REASON_LABELS[run.result.units.reason] ?? UNAVAILABLE_REASON_LABELS[run.result.units.reason] ?? run.result.units.reason}
                    </div>
                  )}
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row">Сценарная стоимость</th>
              {selected.map((run) => {
                const price = run.result.prices.find((entry) => entry.id === priceId) ?? run.result.prices[0] ?? null;
                const q = run.result.units.q;
                return (
                  <td key={run.run_id} className="mono">
                    {q === null || price === null ? '—' : `${(q * price.rub_per_unit).toLocaleString('ru-RU')} ₽`}
                  </td>
                );
              })}
            </tr>
            <tr>
              <th scope="row">Площадь</th>
              {selected.map((run) => (
                <td key={run.run_id} className="mono">
                  {num(run.result.area_ha, 2, 'га')}
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row">E за период</th>
              {selected.map((run) => (
                <td key={run.run_id} className="mono">
                  {num(run.result.stock.e_tco2e, 1, 'т CO₂-экв.')}
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row">E на гектар в год</th>
              {selected.map((run) => (
                <td key={run.run_id} className="mono" data-testid={`lens-compare-e-ha-${run.run_id}`}>
                  {num(run.result.stock.e_tco2e_ha_yr, 3, 'т CO₂-экв./га·год')}
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row">Диапазон результата (H)</th>
              {selected.map((run) => (
                <td key={run.run_id} className="mono">
                  {num(run.result.uncertainty.h_tco2e, 1, 'т CO₂-экв.')}
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row">Покрытие CCI · оптика</th>
              {selected.map((run) => (
                <td key={run.run_id} className="mono">
                  {coverageOf(run.result, 'BIOMASS_CCI')} · {coverageOf(run.result, 'OPTICAL_PAIRED_VALID')}
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row">Расчёт · объяснение</th>
              {selected.map((run) => (
                <td key={run.run_id}>
                  <StatusBadge meta={metaFor(CALCULATION_META, run.result.calculation_status)} />{' '}
                  <StatusBadge meta={metaFor(EVIDENCE_META, run.result.evidence_status)} />
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row">Источник значений</th>
              {selected.map((run) => (
                <td key={run.run_id} className="small">
                  {run.result.fixture ? run.result.fixture.label : 'расчёт сервиса'}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <ul className="limitations small" data-testid="lens-comparison-limits">
        {periods.size > 1 && (
          <li>
            Периоды различаются ({[...periods].join(', ')}): числа относятся к разным интервалам и не складываются в один вывод.
          </li>
        )}
        {areasDiffer && (
          <li>
            Площади различаются ({num(minArea, 0, 'га')} … {num(maxArea, 0, 'га')}): сопоставляйте удельные величины, а не Q напрямую.
          </li>
        )}
        {methods.size > 1 && <li>Версии методики различаются ({[...methods].join(', ')}): сравнение некорректно до пересчёта на одной версии.</li>}
        <li>Сравнение не является рейтингом и не содержит рекомендации покупать, продавать или инвестировать.</li>
        <li>Q нелинеен: пороги, вычеты и округление применяются ко всему запросу, поэтому Q разных участков не суммируются.</li>
      </ul>
    </div>
  );
}
