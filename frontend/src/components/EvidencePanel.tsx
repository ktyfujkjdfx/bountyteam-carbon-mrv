import type { ReactNode } from 'react';
import type { EvidenceScene, Verification } from '../api/types';
import {
  COMPUTATION_META,
  DATASET_META,
  DECISION_META,
  DNBR_LEGEND,
  FIRMS_META,
  OUTCOME_META,
  QUALITY_META,
  REASON_LABELS,
} from '../domain/status';
import { formatCount, formatHa, formatNumber, formatRatio, formatUtc } from '../domain/format';
import { Badge, Field, Hash, StatusBadge } from './common';

// ESA Sentinel-2 L2A Scene Classification Layer class names (product specification).
const SCL_CLASSES: Record<number, string> = {
  0: 'No data',
  1: 'Saturated / defective',
  2: 'Dark area pixels',
  3: 'Cloud shadows',
  4: 'Vegetation',
  5: 'Not vegetated',
  6: 'Water',
  7: 'Unclassified',
  8: 'Cloud, medium probability',
  9: 'Cloud, high probability',
  10: 'Thin cirrus',
  11: 'Snow / ice',
};

function Group({ title, summary, open, children, testId }: { title: string; summary?: ReactNode; open?: boolean; children: ReactNode; testId?: string }) {
  return (
    <details className="evidence-section" open={open} data-testid={testId}>
      <summary>
        {title}
        {summary !== undefined && <span className="summary-value">{summary}</span>}
      </summary>
      <div className="evidence-section-body">{children}</div>
    </details>
  );
}

function SceneBlock({ label, scene }: { label: string; scene: EvidenceScene }) {
  return (
    <div className="scene-block">
      <span className="label">{label}</span>
      <span className="mono">{scene.scene_id}</span>
      <span className="muted">
        {formatUtc(scene.acquired_at)} · {scene.provider} / {scene.collection}
      </span>
      <span className="muted">
        baseline {scene.processing_baseline ?? 'нет данных'} · MGRS {scene.mgrs_tile ?? 'нет данных'} · {scene.assets.map((a) => a.band).join(' ') || 'без assets'}
      </span>
    </div>
  );
}

export function EvidencePanel({ verification }: { verification: Verification }) {
  const { evidence } = verification;
  const { quality, metrics, firms, method } = evidence;

  return (
    <div className="evidence" data-testid="evidence-panel">
      <div className="badge-row" style={{ marginBottom: 12 }}>
        <StatusBadge meta={DATASET_META[evidence.dataset_kind]} testId="evidence-dataset-kind" />
        <StatusBadge meta={COMPUTATION_META[verification.computation_mode]} testId="evidence-computation-mode" />
        <Badge tone="neutral" title="Исторический replay, не текущее наблюдение">
          {verification.observation_mode}
        </Badge>
        {!verification.is_latest && (
          <Badge tone="review" title="Выбрана не последняя проверка">
            Историческая проверка (не latest)
          </Badge>
        )}
      </div>

      <div className="evidence-headline">
        <div>
          <div className="label">RS outcome</div>
          <StatusBadge meta={OUTCOME_META[evidence.outcome]} />
        </div>
        <div>
          <div className="label">Evidence quality (Backend)</div>
          <StatusBadge meta={QUALITY_META[verification.evidence_quality]} />
        </div>
        <div>
          <div className="label">Решение Backend</div>
          <StatusBadge meta={DECISION_META[verification.decision]} />
        </div>
        <div>
          <div className="label">Причина</div>
          <span className="small">{REASON_LABELS[verification.reason]}</span>
        </div>
      </div>

      <Group title="Спутниковые сцены" summary={`${evidence.observation.before.acquired_at.slice(0, 10)} → ${evidence.observation.after.acquired_at.slice(0, 10)}`} open>
        <div className="evidence-headline" style={{ paddingBottom: 0 }}>
          <SceneBlock label="До" scene={evidence.observation.before} />
          <SceneBlock label="После" scene={evidence.observation.after} />
        </div>
      </Group>

      <Group title="Качество наблюдения" summary={verification.evidence_quality_score === null ? 'нет оценки' : `EQS ${verification.evidence_quality_score}/100`}>
        <dl className="fields">
          <Field label="Evidence Quality Score">
            <span data-testid="eqs-value">
              {verification.evidence_quality_score === null ? 'нет оценки' : `${verification.evidence_quality_score} / 100`}
            </span>
            <div className="muted small">
              Индикатор полноты пригодного покрытия (round(100 × paired_valid_forest_ratio)). Не вероятность и не confidence модели; не
              заменяет остальные quality gates.
            </div>
          </Field>
          <Field label="Paired-valid forest">{formatRatio(quality.paired_valid_forest_ratio)}</Field>
          <Field label="Paired-valid AOI">{formatRatio(quality.paired_valid_aoi_ratio)}</Field>
          <Field label="Облачность AOI до / после">
            {formatRatio(quality.aoi_cloud_ratio_before)} / {formatRatio(quality.aoi_cloud_ratio_after)}
          </Field>
          <Field label="Метаданные / сетка">
            {quality.metadata_complete ? 'полные' : 'неполные'} / {quality.grid_aligned ? 'совпадает' : 'не совпадает'}
          </Field>
          <Field label="Сезонная сопоставимость">
            {quality.temporal_comparability} <span className="muted small">— {quality.temporal_note}</span>
          </Field>
        </dl>
      </Group>

      <Group title="Маска качества · SCL" summary={formatRatio(quality.paired_valid_forest_ratio)}>
        <p className="small muted">Sentinel-2 Scene Classification Layer. Исключённые классы (method.parameters.excluded_scl_classes):</p>
        <ul className="legend" style={{ marginTop: 8 }}>
          {method.parameters.excluded_scl_classes.map((cls) => (
            <li key={cls}>
              <span className="mono">{String(cls).padStart(2, '0')}</span> {SCL_CLASSES[cls] ?? 'класс не описан'}
            </li>
          ))}
        </ul>
        <p className="small muted" style={{ marginTop: 8 }}>
          Ресэмплинг: непрерывные — {method.parameters.resampling_continuous}, категориальные — {method.parameters.resampling_categorical}.
        </p>
      </Group>

      <Group title="Метрики леса" summary={formatHa(metrics.affected_area_ha)}>
        <dl className="fields">
          <Field label="Площадь участка (evidence)">{formatHa(metrics.plot_area_ha)}</Field>
          <Field label="Baseline forest">{formatHa(metrics.baseline_forest_area_ha)}</Field>
          <Field label="Analysed forest">{formatHa(metrics.analysed_forest_area_ha)}</Field>
          <Field label="Affected area">
            <span data-testid="affected-area">{formatHa(metrics.affected_area_ha)}</span>
          </Field>
          <Field label="Доля baseline forest">{formatRatio(metrics.affected_fraction_of_baseline_forest)}</Field>
          <Field label="NDVI до / после">
            {formatNumber(metrics.ndvi_before_mean, 3)} / {formatNumber(metrics.ndvi_after_mean, 3)}
            <div className="muted small">Normalized Difference Vegetation Index ({method.parameters.ndvi_bands.join(', ')})</div>
          </Field>
          <Field label="dNBR mean">
            {formatNumber(metrics.dnbr_mean, 3)}
            <div className="muted small">
              Normalized Burn Ratio ({method.parameters.nbr_bands.join(', ')}), scope {metrics.dnbr_mean_scope}
            </div>
          </Field>
          <Field label="Пиксели baseline / valid / affected">
            {formatCount(metrics.baseline_forest_pixel_count, '')} / {formatCount(metrics.paired_valid_forest_pixel_count, '')} /{' '}
            {formatCount(metrics.affected_pixel_count)}
          </Field>
        </dl>
      </Group>

      <Group title="dNBR · порог и легенда" summary={`≥ ${method.parameters.disturbance_dnbr_min}`}>
        <p className="small">
          Порог disturbance: dNBR ≥ <strong>{method.parameters.disturbance_dnbr_min}</strong>, компоненты ≥ {method.parameters.min_component_area_ha} га,
          связность {method.parameters.connectivity}. Порог — demo policy, не универсальная калибровка.
        </p>
        <ul className="legend" aria-label="Легенда dNBR" style={{ marginTop: 10 }}>
          {DNBR_LEGEND.map((row) => (
            <li key={row.range}>
              <span className="legend-swatch" style={{ background: row.color }} aria-hidden="true" />
              <span className="mono">{row.range}</span> {row.label}
            </li>
          ))}
        </ul>
      </Group>

      <Group title="FIRMS · тепловые аномалии" summary={`${firms.support} · ${firms.hotspot_count}`}>
        <StatusBadge meta={FIRMS_META[firms.support]} testId="firms-support" />
        <dl className="fields" style={{ marginTop: 8 }}>
          <Field label="Hotspots">{firms.hotspot_count}</Field>
          <Field label="Окно">
            {formatUtc(firms.window_start)} → {formatUtc(firms.window_end)}
          </Field>
          <Field label="Product / допуск">
            {firms.product} / {firms.spatial_tolerance_m} м
          </Field>
          <Field label="Source refs">
            {firms.source_refs.length === 0
              ? '—'
              : firms.source_refs.map((ref) => (
                  <div key={ref} className="mono small">
                    {ref}
                  </div>
                ))}
          </Field>
        </dl>
        <p className="muted small">FIRMS-точки — тепловые аномалии, не периметр пожара и не ground truth.</p>
      </Group>

      <Group title="Метод и воспроизводимость" summary={method.pipeline_version}>
        <dl className="fields">
          <Field label="Pipeline / code commit" mono>
            {method.pipeline_version} / {method.code_commit ?? 'null'}
          </Field>
          <Field label="Config SHA-256">
            <Hash value={method.config_sha256} />
          </Field>
          <Field label="Сетка">{method.grid ? `EPSG:${method.grid.epsg}, ${method.grid.resolution_m} м, ${method.grid.width}×${method.grid.height}` : 'нет данных'}</Field>
          <Field label="Маска леса">
            {method.forest_mask
              ? `${method.forest_mask.source} (${method.forest_mask.version}, ${method.forest_mask.reference_year}) — ${method.forest_mask.interpretation_note}`
              : 'нет данных'}
          </Field>
        </dl>
      </Group>

      <Group title="Ограничения" summary={String(evidence.limitations.length)} open>
        <ul className="limitations" data-testid="limitations">
          {evidence.limitations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </Group>

      <Group title="Артефакты" summary={String(verification.artifacts.length)}>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Role</th>
                <th>Media</th>
                <th>SHA-256</th>
              </tr>
            </thead>
            <tbody>
              {verification.artifacts.map((artifact) => (
                <tr key={artifact.artifact_id}>
                  <td className="mono">{artifact.role}</td>
                  <td>{artifact.media_type === 'image/tiff' ? 'GeoTIFF · не открывается в браузере' : artifact.media_type}</td>
                  <td>
                    <Hash value={artifact.sha256} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">Загрузка только по artifacts[].url Backend; целостность проверяет Backend.</p>
      </Group>

      <Group title={`Решение Backend · policy ${verification.decision_record.policy_version}`} summary={verification.reason}>
        <dl className="fields">
          <Field label="Decision / reason">
            {verification.decision} / {verification.reason}
          </Field>
          <Field label="Effective observed at">{formatUtc(verification.decision_record.effective_observed_at)}</Field>
          <Field label="Replay as of">{formatUtc(verification.decision_record.replay_as_of)}</Field>
          <Field label="Processed at">{formatUtc(verification.processed_at)}</Field>
          <Field label="Policy parameters hash">
            <Hash value={verification.decision_record.policy_parameters_hash} />
          </Field>
        </dl>
      </Group>
    </div>
  );
}
