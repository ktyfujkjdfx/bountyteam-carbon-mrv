import type { CreditBatch, Plot, Verification } from '../api/types';
import { QUALITY_META, metaFor } from '../domain/status';
import { formatRatio } from '../domain/format';
import { StatusBadge } from './common';

interface Props {
  verification: Verification | null;
  plot: Plot;
  batch: CreditBatch | null;
}

function Gate({ plot, batch }: { plot: Plot; batch: CreditBatch | null }) {
  if (batch?.credit_status === 'FROZEN') {
    return (
      <div className="gate frozen" data-testid="gate" data-gate="frozen">
        <strong>Операции заблокированы · FROZEN</strong>
        {plot.action_block_reason ?? 'Серия заморожена по подтверждённому состоянию контракта.'}
      </div>
    );
  }
  const open = plot.can_issue || plot.can_buy || plot.can_transfer_backend;
  if (open) {
    const allowed = [plot.can_issue && 'выпуск', plot.can_buy && 'покупка', plot.can_transfer_backend && 'передача'].filter(Boolean).join(', ');
    return (
      <div className="gate open" data-testid="gate" data-gate="open">
        <strong>Операции доступны</strong>
        Backend разрешает для текущего актора: {allowed}.
      </div>
    );
  }
  return (
    <div className="gate closed" data-testid="gate" data-gate="closed">
      <strong>Финансовые операции закрыты</strong>
      {plot.action_block_reason ?? 'Backend не разрешает действий для текущего актора.'}
    </div>
  );
}

export function QualityPanel({ verification, plot, batch }: Props) {
  if (!verification) {
    return (
      <div data-testid="quality-panel">
        <div className="label">Evidence quality</div>
        <p className="small muted" style={{ marginTop: 8 }}>
          Для участка ещё нет обработанного наблюдения — качество не оценивалось.
        </p>
        <Gate plot={plot} batch={batch} />
      </div>
    );
  }

  const { quality } = verification.evidence;
  const score = verification.evidence_quality_score;
  const meta = metaFor(QUALITY_META, verification.evidence_quality);

  return (
    <div data-testid="quality-panel">
      <div className="quality-score">
        <div>
          <div className="label">Evidence Quality Score</div>
          <div className="quality-number" aria-label={score === null ? 'Нет оценки' : `${score} из 100`}>
            {score === null ? '—' : score}
            <small>/100</small>
          </div>
        </div>
        <StatusBadge meta={meta} />
      </div>
      {score !== null && (
        <div className="quality-bar" aria-hidden="true">
          <div className="quality-bar-fill" data-tone={meta.tone} style={{ width: `${score}%` }} />
          <div className="quality-tick" style={{ left: '70%' }}>
            <span>70</span>
          </div>
          <div className="quality-tick" style={{ left: '85%' }}>
            <span>85</span>
          </div>
        </div>
      )}
      <p className="small muted" style={{ marginTop: 18 }}>
        Полнота пригодного покрытия, не вероятность и не confidence модели. Пороги 70 / 85 — demo policy v1.
      </p>
      <ul className="checklist" aria-label="Показатели качества наблюдения">
        <li>
          <span>Paired-valid forest</span>
          <span>{formatRatio(quality.paired_valid_forest_ratio)}</span>
        </li>
        <li>
          <span>Paired-valid AOI</span>
          <span>{formatRatio(quality.paired_valid_aoi_ratio)}</span>
        </li>
        <li>
          <span>Облачность AOI до / после</span>
          <span>
            {formatRatio(quality.aoi_cloud_ratio_before)} / {formatRatio(quality.aoi_cloud_ratio_after)}
          </span>
        </li>
        <li>
          <span>Метаданные · сетка</span>
          <span>
            {quality.metadata_complete ? 'полные' : 'неполные'} · {quality.grid_aligned ? 'совпадает' : 'не совпадает'}
          </span>
        </li>
        <li>
          <span>Сезонная сопоставимость</span>
          <span>{quality.temporal_comparability}</span>
        </li>
      </ul>
      <Gate plot={plot} batch={batch} />
    </div>
  );
}
