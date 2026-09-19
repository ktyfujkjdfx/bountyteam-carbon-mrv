import type { ReactNode } from 'react';
import { StatusBadge, UnknownValueNote } from '../../components/common';
import { metaFor } from '../../domain/status';
import { CALCULATION_META, EVIDENCE_META, UNAVAILABLE_REASON_TEXT, ZERO_REASON_TEXT } from '../status';
import type { AnalysisResult } from '../types';
import { AlertIcon, ArrowIcon, CheckIcon, CloudIcon, CoinsIcon, DocIcon, ImageIcon, LayersIcon, LeafIcon, ListIcon, MinusIcon, ShieldIcon, TreeIcon, TrendIcon } from './icons';

export type PriceKey = 'low' | 'base' | 'high';

const PRICE_LABEL: Record<PriceKey, string> = { low: 'Низкая', base: 'Базовая', high: 'Высокая' };

/** Точная сумма: на экране проверки округлять деньги до «тысяч» нельзя. */
function money(value: number): string {
  return `${Math.round(value).toLocaleString('ru-RU')} ₽`;
}

/** Сокращённая сумма — только для диапазона «от и до», где важен порядок величины. */
function moneyShort(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} млн ₽`;
  if (value >= 10_000) return `${Math.round(value / 1000).toLocaleString('ru-RU')} тыс. ₽`;
  return money(value);
}

function num(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? '—' : value.toLocaleString('ru-RU', { maximumFractionDigits: digits });
}

function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${(value * 100).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} %`;
}

/** Одна фраза, по которой можно принять решение без знания дистанционного зондирования. */
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
  /** Карта показывается рядом с выводом, а не отдельным экраном ниже. */
  mapSlot?: ReactNode;
  /** Переход к подробному разбору: «как это посчитано». */
  onOpenDetails?: () => void;
}

/** Показатель: круглая иконка, подпись словами и число. Обозначение кейса стоит вторым. */
function Kpi({
  testId,
  icon,
  label,
  hint,
  value,
  unit,
  note,
  primary,
}: {
  testId: string;
  icon: ReactNode;
  label: string;
  hint: string;
  value: string;
  unit?: string;
  note?: ReactNode;
  primary?: boolean;
}) {
  return (
    <div className={`lens-kpi${primary ? ' primary' : ''}`} data-testid={testId}>
      <span className="lens-kpi-head">
        <span className="lens-kpi-icon" aria-hidden="true">{icon}</span>
        <span className="lens-kpi-label">
          {label}
          <span className="lens-hint" title={hint}>?</span>
        </span>
      </span>
      <span className="lens-kpi-value">
        {value}
        {unit && <span className="lens-kpi-unit">{unit}</span>}
      </span>
      {note && <span className="lens-kpi-note">{note}</span>}
    </div>
  );
}

/** Цепочка шагов расчёта: от наблюдений к подтверждённым единицам. */
const CHAIN: Array<{ icon: ReactNode; label: string }> = [
  { icon: <ImageIcon size={20} />, label: 'Наблюдения' },
  { icon: <LayersIcon size={20} />, label: 'Изменения' },
  { icon: <TreeIcon size={20} />, label: 'Углерод' },
  { icon: <ListIcon size={20} />, label: 'Базовая линия' },
  { icon: <ShieldIcon size={20} />, label: 'Неопределённость' },
  { icon: <LeafIcon size={20} />, label: 'Единицы' },
];

/**
 * Первый экран результата: заголовок, четыре показателя, карта рядом с выводом, цепочка шагов и
 * полоса качества данных. Всё техническое — на один клик глубже, в разборе результата.
 */
export function Headline({ result, priceKey, onPriceKey, customPrice, mapSlot, onOpenDetails }: Props) {
  const sentence = headlineSentence(result);
  const q = result.units.q;
  const scenario = result.scenario_values;
  const price = customPrice ?? scenario[priceKey].price_rub;
  const value = q === null ? null : q * price;
  // Величина выброса публикуется один раз — в units. Блок change на неё только ссылается.
  const eproj = result.units.eproj_tco2e;
  const coverage = result.coverage;
  const fireZones = result.zones.filter((zone) => String(zone.cause) === 'FIRE_SUPPORTED');
  const unknownCause = result.zones.filter((zone) => String(zone.cause) === 'UNKNOWN');
  const rangeLow = q === null ? null : q * scenario.low.price_rub;
  const rangeHigh = q === null ? null : q * scenario.high.price_rub;

  const facts: Array<{ icon: ReactNode; text: string }> = [
    {
      icon: result.areas.complete ? <CheckIcon size={18} /> : <AlertIcon size={18} />,
      text: result.areas.complete ? 'Обязательные данные есть на всю площадь' : `Часть площади без данных: ${num(result.areas.missing_ha, 2)} га`,
    },
    {
      icon: <ShieldIcon size={18} />,
      text: result.units.unc === null
        ? 'Неопределённость не считалась: положительного результата, к которому её применяют, нет'
        : `Вычет на неопределённость: ${percent(result.units.unc)}`,
    },
    {
      icon: <DocIcon size={18} />,
      text: result.units.ebase_tco2e === null ? 'Базовая линия не рассчитана' : 'Базовая линия кейса учтена',
    },
  ];

  return (
    <section className="lens-hero-block" data-testid="lens-headline" aria-label="Главный результат">
      <header className="lens-hero-head">
        <h2>Проверка углеродного проекта</h2>
        <p className="lens-hero-meta">
          {result.request.aoi_id ?? 'контур пользователя'} · {result.request.year_start}–{result.request.year_end} ·{' '}
          {num(result.areas.calculated_ha, 1)} га
        </p>
      </header>

      <div className="lens-kpi-row">
        <Kpi
          testId="lens-q"
          primary
          icon={<LeafIcon size={20} />}
          label="Подтверждено единиц"
          hint="Единицы по правилам кейса, а не сертифицированные кредиты. Одна единица — одна тонна CO₂-эквивалента, оставшаяся после базовой линии, неопределённости и резерва."
          value={q === null ? 'Не рассчитано' : q.toLocaleString('ru-RU')}
          note={<>в методике это <span className="term">Q</span></>}
        />
        <Kpi
          testId="lens-eproj"
          icon={<CloudIcon size={20} />}
          label="Изменение запаса углерода"
          hint="Насколько изменился учитываемый запас углерода за период, в CO₂-эквиваленте. Положительное значение — запас уменьшился, отрицательное — вырос."
          value={num(eproj)}
          unit="т CO₂-экв."
          note={
            <>
              {eproj !== null && eproj !== undefined ? (eproj < 0 ? 'запас вырос' : 'запас уменьшился') : 'нет данных'} ·{' '}
              <span className="term">Eproj</span>
            </>
          }
        />
        <Kpi
          testId="lens-r"
          icon={<TrendIcon size={20} />}
          label="Эффект сверх базовой линии"
          hint="Разница между результатом периода и базовой линией кейса — тем, что ожидалось бы без проекта. Единицы даёт только положительная разница."
          value={num(result.units.r_tco2e)}
          unit="т CO₂-экв."
          note={<span className="term">R</span>}
        />
        <Kpi
          testId="lens-value"
          icon={<CoinsIcon size={20} />}
          label="Сценарная стоимость"
          hint="Подтверждённые единицы, умноженные на цену из условий кейса. Это не прогноз рынка и не оценка дохода."
          value={value === null ? '—' : money(value)}
          note={
            rangeLow === null || rangeHigh === null
              ? 'цена задаётся условиями кейса'
              : `по ценам кейса: ${moneyShort(rangeLow)} — ${moneyShort(rangeHigh)}`
          }
        />
      </div>

      <div className="lens-hero">
        {mapSlot && <div className="lens-hero-map">{mapSlot}</div>}
        <aside className={`lens-verdict-card tone-${sentence.tone}`} data-testid="lens-verdict" data-tone={sentence.tone}>
          <span className="lens-verdict-kicker">
            <span className="lens-kpi-icon" aria-hidden="true"><LeafIcon size={18} /></span>
            Вывод
          </span>
          <div className="lens-verdict-main">
            <span className={`lens-verdict-mark tone-${sentence.tone}`} aria-hidden="true">
              {sentence.tone === 'ok' ? <CheckIcon size={22} /> : <MinusIcon size={22} />}
            </span>
            <strong>{sentence.title}</strong>
          </div>
          <p className="lens-verdict-text">{sentence.text}</p>
          <ul className="lens-verdict-facts">
            {facts.map((fact) => (
              <li key={fact.text}>
                <span className="lens-fact-icon" aria-hidden="true">{fact.icon}</span>
                <span>{fact.text}</span>
              </li>
            ))}
          </ul>
          {onOpenDetails && (
            <button type="button" className="btn lens-verdict-cta" onClick={onOpenDetails} data-testid="lens-open-details">
              Как это посчитано <ArrowIcon size={18} />
            </button>
          )}
          <div className="lens-badges">
            <StatusBadge meta={metaFor(CALCULATION_META, result.calculation_status)} testId="lens-status-calculation" />
            <StatusBadge meta={metaFor(EVIDENCE_META, result.evidence_status)} testId="lens-status-evidence" />
          </div>
          <UnknownValueNote meta={metaFor(CALCULATION_META, result.calculation_status)} />
          <UnknownValueNote meta={metaFor(EVIDENCE_META, result.evidence_status)} />
        </aside>
      </div>

      <ol className="lens-chain" data-testid="lens-chain" aria-label="Порядок расчёта">
        {CHAIN.map((step, index) => (
          <li key={step.label}>
            <span className="lens-chain-icon" aria-hidden="true">{step.icon}</span>
            <span className="lens-chain-label">{step.label}</span>
            {index < CHAIN.length - 1 && <span className="lens-chain-arrow" aria-hidden="true">→</span>}
          </li>
        ))}
      </ol>

      <div className="lens-quality-strip" data-testid="lens-quality-strip">
        <span className="lens-quality-title">
          <span className="lens-kpi-icon" aria-hidden="true"><LayersIcon size={18} /></span>
          Качество данных
        </span>
        <span className="lens-quality-item">
          <b>{percent(coverage.biomass_fraction)}</b>
          <span>покрытие биомассой</span>
        </span>
        <span className="lens-quality-item">
          <b>{percent(coverage.optical_paired_valid_fraction)}</b>
          <span>сравнимые наблюдения</span>
        </span>
        <span className="lens-quality-item">
          <b>{fireZones.length > 0 ? 'признак есть' : 'не установлен'}</b>
          <span>пожар по продукту</span>
        </span>
        <span className="lens-quality-item">
          <b>{unknownCause.length}</b>
          <span>зон с неустановленной причиной</span>
        </span>
        {onOpenDetails && (
          <button type="button" className="link-button lens-quality-link" onClick={onOpenDetails}>
            Открыть подробный разбор →
          </button>
        )}
      </div>

      <div className="lens-price-row" role="group" aria-label="Сценарий цены">
        <span className="lens-price-hint">Цена за единицу:</span>
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
        <span className="muted small">
          Стоимость — это подтверждённые единицы, умноженные на цену кейса. Не прогноз рынка и не доход.
        </span>
      </div>
    </section>
  );
}
