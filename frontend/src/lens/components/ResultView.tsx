import { useState } from 'react';
import { Headline, type PriceKey } from './Headline';
import { HowCalculated } from './HowCalculated';
import { QualityRisks } from './QualityRisks';
import { WhatHappened } from './WhatHappened';
import { ClaimStressTest } from './ClaimStressTest';
import { ValueCalculator } from './ValueCalculator';
import { CellCard } from './CellCard';
import type { CellsState } from './LensMapView';
import type { AnalysisResult } from '../types';

type Tab = 'what' | 'how' | 'quality';

const TABS: ReadonlyArray<[Tab, string]> = [
  ['what', 'Что произошло'],
  ['how', 'Как рассчитано'],
  ['quality', 'Качество и риски'],
];

interface Props {
  result: AnalysisResult;
  priceKey: PriceKey;
  onPriceKey: (key: PriceKey) => void;
  customPrice: number | null;
  onCustomPrice: (value: number | null) => void;
  selectedZoneId: string | null;
  onSelectZone: (zoneId: string) => void;
  cells: CellsState;
  selectedCellId: string | null;
  onShowCells: () => void;
  showClaim: boolean;
  showValue: boolean;
  onDownloadReport: () => void;
}

/**
 * The shared reading of one result: the headline first, then three tabs, then the claim and the value
 * scenarios. Everything technical stays one click away from the outcome.
 */
export function ResultView(props: Props) {
  const { result, priceKey, onPriceKey, customPrice, onCustomPrice, selectedZoneId, onSelectZone, cells, selectedCellId, onShowCells, showClaim, showValue, onDownloadReport } = props;
  const [tab, setTab] = useState<Tab>('what');
  const selectedCell = cells.kind === 'ready' ? cells.cells.find((cell) => cell.cell_id === selectedCellId) ?? null : null;

  return (
    <div className="lens-result" data-testid="lens-result">
      <Headline result={result} priceKey={priceKey} onPriceKey={onPriceKey} customPrice={customPrice} />

      <div className="lens-actions">
        <button type="button" className="btn" onClick={onDownloadReport} data-testid="lens-download-report">
          Скачать отчёт
        </button>
        <button type="button" className="btn btn-small btn-secondary" onClick={onShowCells} data-testid="lens-show-cells">
          {cells.kind === 'ready' ? 'Обновить ячейки' : 'Показать ячейки'}
        </button>
      </div>

      {result.fixture && (
        <div className="state state-warn compact" role="note" data-testid="lens-fixture-note">
          <strong>{String(result.fixture.kind) === 'DOC_EXAMPLE' ? 'Условный пример постановки' : 'Помеченный набор значений'}</strong>
          <span>{result.fixture.note}</span>
        </div>
      )}

      {selectedCell && <CellCard cell={selectedCell} result={result} />}

      <section className="panel" aria-label="Разбор результата">
        <div className="tabs" role="tablist" aria-label="Разделы результата">
          {TABS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              id={`lens-tab-${key}`}
              aria-selected={tab === key}
              aria-controls={`lens-tabpanel-${key}`}
              className={`tab${tab === key ? ' active' : ''}`}
              onClick={() => setTab(key)}
              data-testid={`lens-tab-${key}`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="panel-body" role="tabpanel" id={`lens-tabpanel-${tab}`} aria-labelledby={`lens-tab-${tab}`}>
          {tab === 'what' && <WhatHappened result={result} selectedZoneId={selectedZoneId} onSelectZone={onSelectZone} showProjection={showValue} />}
          {tab === 'how' && <HowCalculated result={result} />}
          {tab === 'quality' && <QualityRisks result={result} />}
        </div>
      </section>

      {showClaim && <ClaimStressTest result={result} priceKey={priceKey} />}
      {showValue && <ValueCalculator result={result} priceKey={priceKey} onPriceKey={onPriceKey} customPrice={customPrice} onCustomPrice={onCustomPrice} />}
    </div>
  );
}
