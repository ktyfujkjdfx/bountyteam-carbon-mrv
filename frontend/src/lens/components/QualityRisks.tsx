import { StatusBadge } from '../../components/common';
import { metaFor } from '../../domain/status';
import { eventsForAoi } from '../data';
import { codeRu, serviceTextRu } from '../ru';
import { SEVERITY_META } from '../status';
import type { AnalysisResult } from '../types';

type PublicCoverageKey = 'biomass_fraction' | 'uncertainty_fraction' | 'baseline_fraction' | 'optical_paired_valid_fraction';

const COVERAGE_ROWS: Array<{ key: PublicCoverageKey; label: string; note: string }> = [
  { key: 'biomass_fraction', label: 'Биомасса (CCI)', note: 'Доля площади с числовыми значениями запаса на обе даты. Без неё единицы не считаются.' },
  { key: 'uncertainty_fraction', label: 'Неопределённость (SD)', note: 'Доля площади, для которой известна погрешность оценки биомассы.' },
  { key: 'baseline_fraction', label: 'Базовая линия', note: 'Доля площади, покрытая таблицей базовой линии кейса.' },
  { key: 'optical_paired_valid_fraction', label: 'Оптика на обе даты', note: 'Доля площади с пригодными снимками. Влияет на объяснение причины, а не на расчёт запаса.' },
];

function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${Math.round(value * 100)} %`;
}

function num(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? 'нет данных' : value.toLocaleString('ru-RU', { maximumFractionDigits: digits });
}

interface RiskCard {
  id: string;
  title: string;
  level: string;
  basis: string;
  source: string;
  effect: string;
}

/**
 * Three independent cards, each with the measurement it stands on. They are deliberately not combined
 * into one score: a rating would hide which fact the reader should check.
 */
export function riskCards(result: AnalysisResult): RiskCard[] {
  const events = eventsForAoi(result.request.aoi_id);
  const fireZones = result.zones.filter((zone) => String(zone.cause) === 'FIRE_SUPPORTED');
  const lossZones = result.zones.filter((zone) => String(zone.fact) === 'TREE_COVER_LOSS');
  const lossArea = lossZones.reduce((sum, zone) => sum + zone.area_ha, 0);
  const coverage = result.coverage;
  const worstCoverage = Math.min(coverage.biomass_fraction ?? 1, coverage.uncertainty_fraction ?? 1, coverage.baseline_fraction ?? 1);

  return [
    {
      id: 'fire',
      title: 'Пожар',
      level: events.length === 0 ? 'Записей о пожаре нет' : fireZones.length > 0 ? 'Есть зона с признаком горения' : 'Есть запись о событии в границах участка',
      basis:
        events.length === 0
          ? 'В официальной таблице событий записей для этой территории нет.'
          : `Продукт гарей отмечает ${events[0]?.burned_pixel_centers_in_aoi ?? '—'} из ${events[0]?.all_pixel_centers_in_aoi ?? '—'} центров пикселей в контуре, ${events[0]?.date_min_product} — ${events[0]?.date_max_product}.`,
      source: events[0]?.source_id ?? 'data/events.csv',
      effect: 'Признак горения объясняет причину изменения. Площадь гари продуктом не измеряется и в Q напрямую не входит.',
    },
    {
      id: 'forest-loss',
      title: 'Потеря древесного покрова',
      level: lossZones.length === 0 ? 'Зон потери покрова не выделено' : `${lossZones.length} зона(ы), ${num(lossArea, 1)} га`,
      basis:
        lossZones.length === 0
          ? 'Сервис не вернул зон с зарегистрированной потерей покрова для этого запроса.'
          : `Суммарная площадь зон потери — ${num(lossArea, 1)} га; вклад в Eproj показан по каждой зоне отдельно.`,
      source: 'GFC_2025_V113 · продукт изменений покрова',
      effect: 'Год потери по продукту не равен измеренному изменению биомассы и не определяет причину.',
    },
    {
      id: 'data-quality',
      title: 'Качество данных',
      level:
        worstCoverage >= 1
          ? 'Обязательные данные полные'
          : worstCoverage > 0
            ? `Неполное покрытие: минимум ${percent(worstCoverage)}`
            : 'Обязательных числовых данных нет',
      basis: `Биомасса ${percent(coverage.biomass_fraction)}, SD ${percent(coverage.uncertainty_fraction)}, базовая линия ${percent(coverage.baseline_fraction)}, оптика ${percent(coverage.optical_paired_valid_fraction)}.`,
      source: 'CCI_V7 · S2_L2A · data/methodology/baseline.csv',
      effect:
        worstCoverage >= 1
          ? 'Ограничений покрытия для расчёта нет; оптика влияет только на объяснение причины.'
          : 'При неполном обязательном покрытии единицы не рассчитываются — показывается «не рассчитано» с причиной.',
    },
  ];
}

/** Tab 3: coverages, interval, warnings, risk cards and limitations. */
export function QualityRisks({ result }: { result: AnalysisResult }) {
  const cards = riskCards(result);
  const sensitivity = result.uncertainty.sensitivity ?? [];
  const severityRank: Record<string, number> = { BLOCKING: 0, CRITICAL: 0, WARNING: 1, INFO: 2 };
  const warnings = [...result.evidence.warnings].sort(
    (left, right) => (severityRank[String(left.severity)] ?? 3) - (severityRank[String(right.severity)] ?? 3),
  );

  return (
    <div className="lens-tab-body" data-testid="lens-quality-risks">
      <h3>Покрытие обязательными данными</h3>
      <div className="lens-coverage" data-testid="lens-coverage">
        {COVERAGE_ROWS.map((row) => {
          const value = result.coverage[row.key];
          const rawKey = row.key === 'biomass_fraction' ? 'biomass'
            : row.key === 'uncertainty_fraction' ? 'uncertainty'
              : row.key === 'baseline_fraction' ? 'baseline' : 'optical_paired_valid';
          const raw = result.coverage.coverage_fraction_raw?.[rawKey];
          return (
            <div key={row.key} className="lens-coverage-row" data-testid={`lens-coverage-${row.key}`}>
              <div className="lens-coverage-head">
                <span>{row.label}</span>
                <span className="mono">{percent(value)}</span>
              </div>
              <div className="meter" aria-hidden="true">
                <span style={{ width: `${Math.max(0, Math.min(1, value ?? 0)) * 100}%` }} />
              </div>
              <p className="muted small">{row.note}</p>
              {raw !== undefined && raw !== value && <p className="muted small mono">raw: {raw.toFixed(9)}</p>}
            </div>
          );
        })}
      </div>
      <p className="muted small">
        Четыре оси независимы: облачность не уменьшает покрытие биомассы, а полное покрытие CCI не делает объяснение причины полным.
      </p>

      <h3>Площадь запроса</h3>
      <dl className="fields" data-testid="lens-areas">
        <div className="field">
          <dt>Запрошено</dt>
          <dd className="mono">{num(result.areas.requested_ha, 4)} га</dd>
        </div>
        <div className="field">
          <dt>Рассчитано</dt>
          <dd className="mono">{num(result.areas.calculated_ha, 4)} га</dd>
        </div>
        <div className="field">
          <dt>Без обязательных данных</dt>
          <dd className="mono">{num(result.areas.missing_ha, 4)} га</dd>
        </div>
        {result.areas.area_difference_ha !== null && result.areas.area_difference_ha !== undefined && (
          <div className="field">
            <dt>Техническая разность</dt>
            <dd className="mono">
              {num(result.areas.area_difference_ha, 6)} га
              <div className="muted small">Знаковая разность «рассчитано − запрошено» из-за геодезической арифметики.</div>
            </dd>
          </div>
        )}
      </dl>

      <h3>Диапазон результата</h3>
      <dl className="fields" data-testid="lens-uncertainty">
        <div className="field">
          <dt>Нижняя и верхняя границы</dt>
          <dd className="mono">
            {num(result.uncertainty.lower_tco2e)} … {num(result.uncertainty.upper_tco2e)} т CO₂-экв.
          </dd>
        </div>
        <div className="field">
          <dt>Способ</dt>
          <dd className="mono">{result.uncertainty.method}</dd>
        </div>
        <div className="field">
          <dt>Тип интервала</dt>
          <dd>
            {String(result.uncertainty.interval_kind) === 'SCENARIO' ? 'Сценарный диапазон' : String(result.uncertainty.interval_kind)}
            <div className="muted small">Это сценарный диапазон по условиям кейса, а не вероятностный доверительный интервал.</div>
          </dd>
        </div>
      </dl>
      {sensitivity.length > 0 && (
        <div className="table-wrap">
          <table className="data-table" data-testid="lens-sensitivity">
            <thead>
              <tr>
                <th>Сценарий чувствительности</th>
                <th>Половина диапазона, т CO₂-экв.</th>
                <th>Нижняя</th>
                <th>Верхняя</th>
              </tr>
            </thead>
            <tbody>
              {sensitivity.map((variant) => (
                <tr key={variant.label}>
                  <td className="mono small">{variant.label}</td>
                  <td className="mono">{num(variant.half_width_tco2e)}</td>
                  <td className="mono">{num(variant.lower_tco2e)}</td>
                  <td className="mono">{num(variant.upper_tco2e)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small">
        Основной результат считается по одному сценарию; остальные строки показывают, насколько диапазон зависит от допущений, и в Q не
        подмешиваются.
      </p>

      <h3>На что обратить внимание</h3>
      {warnings.length === 0 ? (
        <p className="muted small" data-testid="lens-warnings-empty">
          Предупреждений нет.
        </p>
      ) : (
        <ul className="limitations small" data-testid="lens-warnings">
          {warnings.map((warning) => (
            <li key={`${warning.code}-${warning.message}`} data-testid={`lens-warning-${warning.code}`}>
              <StatusBadge meta={metaFor(SEVERITY_META, warning.severity)} />{' '}
              {codeRu(warning.code) && <b>{codeRu(warning.code)}. </b>}
              <span>{serviceTextRu(warning.message)}</span>
              {warning.code !== 'UNSTRUCTURED_WARNING' && (
                <details className="lens-tech">
                  <summary>Код предупреждения</summary>
                  <div className="lens-tech-body mono small">{warning.code}</div>
                </details>
              )}
            </li>
          ))}
        </ul>
      )}

      <h3>Риски участка</h3>
      <div className="lens-risk-grid" data-testid="lens-risks">
        {cards.map((card) => (
          <article key={card.id} className="lens-risk-card" data-testid={`lens-risk-${card.id}`}>
            <h4>{card.title}</h4>
            <p className="lens-risk-level">{card.level}</p>
            <p className="muted small">{card.basis}</p>
            <p className="muted small">Источник: {card.source}</p>
            <p className="muted small">{card.effect}</p>
          </article>
        ))}
      </div>
      <p className="muted small">Карточки независимы и намеренно не сводятся в один рейтинг.</p>

      <h3>Чего этот расчёт не утверждает</h3>
      <p className="muted small">Границы метода: их стоит прочитать до того, как принимать решение по числу.</p>
      <ul className="limitations small" data-testid="lens-limitations">
        {result.limitations.map((item) => (
          <li key={`${item.code}-${item.message}`}>
            <span>{serviceTextRu(item.message)}</span>
          </li>
        ))}
      </ul>
      <details className="lens-tech">
        <summary>Коды ограничений</summary>
        <div className="lens-tech-body">
          {result.limitations.map((item) => (
            <span key={`${item.code}-${item.message}`} className="mono small">{item.code}</span>
          ))}
        </div>
      </details>
    </div>
  );
}
