import { useState } from 'react';
import { parameterValue } from '../data';
import { UNAVAILABLE_REASON_TEXT, ZERO_REASON_TEXT } from '../status';
import type { AnalysisResult } from '../types';

function num(value: number | null | undefined, digits = 3): string {
  return value === null || value === undefined ? 'нет данных' : value.toLocaleString('ru-RU', { maximumFractionDigits: digits });
}

interface Step {
  id: string;
  title: string;
  value: string;
  formula: string;
  inputs: Array<[string, string]>;
  source: string;
}

/** Tab 2: the path from the measured change to Q, with each step able to show its own formula. */
export function HowCalculated({ result }: { result: AnalysisResult }) {
  const [open, setOpen] = useState<string | null>(null);
  const u = result.units;
  const cf = parameterValue('CF_AGB');
  const buf = parameterValue('BUF');
  const unc = parameterValue('UNC_allowance');
  const stop = parameterValue('UNC_stop_ratio');

  const steps: Step[] = [
    {
      id: 'eproj',
      title: 'Эффект проекта Eproj',
      value: `${num(u.eproj_tco2e)} т CO₂-экв.`,
      formula: 'Eproj = −ΔC × 44/12, где ΔC = запас на конец − запас на начало',
      inputs: [
        ['Запас на начало, т C', num(result.change.total_carbon_start_tc)],
        ['Запас на конец, т C', num(result.change.total_carbon_end_tc)],
        ['ΔC, т C', num(result.change.delta_carbon_tc)],
        ['CF (т C / т сухого вещества)', cf?.value ?? '0.47'],
      ],
      source: `${cf?.source_id ?? 'IPCC_FOREST_2006'} · ${cf?.locator ?? 'Таблица 4.3'}`,
    },
    {
      id: 'ebase',
      title: 'Базовая линия Ebase',
      value: `${num(u.ebase_tco2e)} т CO₂-экв.`,
      formula: 'Ebase — тот же расчёт для сценарной траектории кейса на площадь запроса',
      inputs: [
        ['Идентификатор базовой линии', result.baseline.baseline_id ?? '—'],
        ['Площадь применения, га', num(result.baseline.area_ha, 4)],
        ['Δ базовой линии, т C/га', num(result.baseline.delta_tc_ha)],
      ],
      source: 'data/methodology/baseline.csv · сценарное условие кейса, не доказанный альтернативный исход',
    },
    {
      id: 'r',
      title: 'Результат относительно базовой линии R',
      value: `${num(u.r_tco2e)} т CO₂-экв.`,
      formula: 'R = Ebase − Eproj − LK',
      inputs: [
        ['Ebase, т CO₂-экв.', num(u.ebase_tco2e)],
        ['Eproj, т CO₂-экв.', num(u.eproj_tco2e)],
        ['LK (утечка), т CO₂-экв.', num(u.lk_tco2e)],
      ],
      source: 'data/methodology/parameters.csv · LK = 0 принято сценарием кейса',
    },
    {
      id: 'ratio',
      title: 'Проверка неопределённости H/R',
      value: u.ratio === null ? 'не вычисляется при R ≤ 0' : num(u.ratio),
      formula: `H — половина сценарного диапазона; при H/R ≥ ${stop?.value ?? '1.0'} результат обнуляется`,
      inputs: [
        ['H, т CO₂-экв.', num(u.h_tco2e)],
        ['Нижняя граница, т CO₂-экв.', num(u.lower_tco2e)],
        ['Верхняя граница, т CO₂-экв.', num(u.upper_tco2e)],
        ['Порог остановки', stop?.value ?? '1.0'],
      ],
      source: 'Сценарный диапазон, а не вероятностный доверительный интервал',
    },
    {
      id: 'radj',
      title: 'Вычет за неопределённость',
      value: u.radj_tco2e === null ? 'расчёт остановлен' : `${num(u.radj_tco2e)} т CO₂-экв.`,
      formula: `UNC = min(1, max(0, H/R − ${unc?.value ?? '0.10'})); Radj = R × (1 − UNC)`,
      inputs: [
        ['H/R', num(u.ratio)],
        ['UNC', num(u.unc)],
        ['Вычет, т CO₂-экв.', num(u.uncertainty_deduction_tco2e)],
      ],
      source: `data/methodology/parameters.csv · UNC_allowance = ${unc?.value ?? '0.10'}`,
    },
    {
      id: 'buffer',
      title: 'Резерв',
      value: u.buffer_tco2e === null ? 'расчёт остановлен' : `${num(u.buffer_tco2e)} т CO₂-экв.`,
      formula: `B = Radj × ${buf?.value ?? '0.15'}`,
      inputs: [
        ['Radj, т CO₂-экв.', num(u.radj_tco2e)],
        ['Доля резерва', buf?.value ?? '0.15'],
      ],
      source: 'data/methodology/parameters.csv · фиксированный параметр сценария',
    },
    {
      id: 'q',
      title: 'Потенциальные единицы Q',
      value: u.q === null ? 'не рассчитано' : num(u.q, 0),
      formula: 'Q = floor(Radj × 0.85)',
      inputs: [
        ['Radj, т CO₂-экв.', num(u.radj_tco2e)],
        ['Остаток округления, т CO₂-экв.', num(u.rounding_residual_tco2e)],
      ],
      source: 'Правило кейса; дробный остаток в Q не включается',
    },
  ];

  const stopped = u.q === 0 || u.q === null;

  return (
    <div className="lens-tab-body" data-testid="lens-how-calculated">
      <p className="muted small">
        Значения приходят из расчёта сервиса. Интерфейс их не пересчитывает: формулы показаны, чтобы результат можно было проверить.
      </p>
      <ol className="lens-steps" data-testid="lens-steps">
        {steps.map((step) => (
          <li key={step.id} data-testid={`lens-step-${step.id}`}>
            <details open={open === step.id} onToggle={(event) => setOpen((event.currentTarget as HTMLDetailsElement).open ? step.id : null)}>
              <summary>
                <span>{step.title}</span>
                <span className="mono">{step.value}</span>
              </summary>
              <div className="lens-step-body">
                <p className="mono small">{step.formula}</p>
                <dl className="fields">
                  {step.inputs.map(([label, value]) => (
                    <div className="field" key={label}>
                      <dt>{label}</dt>
                      <dd className="mono">{value}</dd>
                    </div>
                  ))}
                </dl>
                <p className="muted small">Источник: {step.source}</p>
              </div>
            </details>
          </li>
        ))}
      </ol>

      {stopped && (
        <div className="state state-warn compact" role="status" data-testid="lens-stop-note">
          <strong>Почему единиц нет</strong>
          <span>
            {u.q === null
              ? `Расчёт недоступен: ${UNAVAILABLE_REASON_TEXT[String(u.unavailable_reason)] ?? 'не хватает обязательных данных'}.`
              : `Расчёт выполнен и дал 0: ${ZERO_REASON_TEXT[String(u.zero_reason)] ?? 'по правилам кейса единиц не образуется'}.`}
          </span>
          <span className="muted small">Ненулевой остаток при остановке не показывается как доступные единицы.</span>
        </div>
      )}
    </div>
  );
}
