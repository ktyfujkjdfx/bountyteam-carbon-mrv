import type { EvidenceScene, Verification } from '../api/types';
import {
  COMPUTATION_META,
  DATASET_META,
  DNBR_LEGEND,
  FIRMS_META,
  QUALITY_META,
  OUTCOME_META,
} from '../domain/status';
import { formatCount, formatHa, formatNumber, formatRatio, formatUtc } from '../domain/format';
import { Badge, Field, Hash, StatusBadge } from './common';

function SceneRow({ label, scene }: { label: string; scene: EvidenceScene }) {
  return (
    <tr>
      <th scope="row">{label}</th>
      <td className="mono">{scene.scene_id}</td>
      <td>{formatUtc(scene.acquired_at)}</td>
      <td>
        {scene.provider} / {scene.collection}
      </td>
      <td>{scene.processing_baseline ?? 'нет данных'}</td>
      <td>{scene.mgrs_tile ?? 'нет данных'}</td>
      <td>{scene.assets.map((a) => a.band).join(', ') || '—'}</td>
    </tr>
  );
}

export function EvidencePanel({ verification }: { verification: Verification }) {
  const { evidence } = verification;
  const { quality, metrics, firms, method } = evidence;

  return (
    <div className="evidence" data-testid="evidence-panel">
      <div className="badge-row">
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

      <h3>Источники сцен</h3>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th />
              <th>Scene ID</th>
              <th>Съёмка</th>
              <th>Provider / collection</th>
              <th>Processing baseline</th>
              <th>MGRS</th>
              <th>Bands</th>
            </tr>
          </thead>
          <tbody>
            <SceneRow label="До" scene={evidence.observation.before} />
            <SceneRow label="После" scene={evidence.observation.after} />
          </tbody>
        </table>
      </div>

      <div className="grid-2">
        <div>
          <h3>RS outcome</h3>
          <StatusBadge meta={OUTCOME_META[evidence.outcome]} />
          <h3>Evidence quality (Backend)</h3>
          <StatusBadge meta={QUALITY_META[verification.evidence_quality]} />
          <dl className="fields">
            <Field label="Evidence Quality Score">
              <span data-testid="eqs-value">
                {verification.evidence_quality_score === null ? 'нет оценки' : `${verification.evidence_quality_score} / 100`}
              </span>
              <div className="muted small">
                Индикатор полноты пригодного покрытия (round(100 × paired_valid_forest_ratio)). Не вероятность и не confidence модели;
                не заменяет остальные quality gates.
              </div>
            </Field>
            <Field label="Paired valid forest ratio">{formatRatio(quality.paired_valid_forest_ratio)}</Field>
            <Field label="Paired valid AOI ratio">{formatRatio(quality.paired_valid_aoi_ratio)}</Field>
            <Field label="AOI cloud ratio до / после">
              {formatRatio(quality.aoi_cloud_ratio_before)} / {formatRatio(quality.aoi_cloud_ratio_after)}
            </Field>
            <Field label="Metadata complete / grid aligned">
              {quality.metadata_complete ? 'да' : 'нет'} / {quality.grid_aligned ? 'да' : 'нет'}
            </Field>
            <Field label="Temporal comparability">
              {quality.temporal_comparability} <span className="muted small">— {quality.temporal_note}</span>
            </Field>
          </dl>
        </div>

        <div>
          <h3>Метрики (площадь по пикселям 20 м)</h3>
          <dl className="fields">
            <Field label="Площадь участка">{formatHa(metrics.plot_area_ha)}</Field>
            <Field label="Baseline forest">{formatHa(metrics.baseline_forest_area_ha)}</Field>
            <Field label="Analysed forest">{formatHa(metrics.analysed_forest_area_ha)}</Field>
            <Field label="Affected area">
              <span data-testid="affected-area">{formatHa(metrics.affected_area_ha)}</span>
            </Field>
            <Field label="Доля baseline forest">{formatRatio(metrics.affected_fraction_of_baseline_forest)}</Field>
            <Field label="NDVI до / после (mean)">
              {formatNumber(metrics.ndvi_before_mean, 3)} / {formatNumber(metrics.ndvi_after_mean, 3)}
            </Field>
            <Field label="dNBR mean">
              {formatNumber(metrics.dnbr_mean, 3)} <span className="muted small">scope: {metrics.dnbr_mean_scope}</span>
            </Field>
            <Field label="Пиксели: baseline / valid / affected">
              {formatCount(metrics.baseline_forest_pixel_count, '')} / {formatCount(metrics.paired_valid_forest_pixel_count, '')} /{' '}
              {formatCount(metrics.affected_pixel_count)}
            </Field>
          </dl>
        </div>
      </div>

      <div className="grid-2">
        <div>
          <h3>dNBR: порог и легенда</h3>
          <p className="small">
            Порог disturbance: dNBR ≥ <strong>{method.parameters.disturbance_dnbr_min}</strong>, компоненты ≥{' '}
            {method.parameters.min_component_area_ha} га, связность {method.parameters.connectivity}. Порог — demo policy, не
            универсальная калибровка.
          </p>
          <ul className="legend" aria-label="Легенда dNBR">
            {DNBR_LEGEND.map((row) => (
              <li key={row.range}>
                <span className="legend-swatch" style={{ background: row.color }} aria-hidden="true" />
                <span className="mono">{row.range}</span> {row.label}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3>FIRMS</h3>
          <StatusBadge meta={FIRMS_META[firms.support]} testId="firms-support" />
          <dl className="fields">
            <Field label="Hotspots">{firms.hotspot_count}</Field>
            <Field label="Окно">
              {formatUtc(firms.window_start)} → {formatUtc(firms.window_end)}
            </Field>
            <Field label="Product / tolerance">
              {firms.product} / {firms.spatial_tolerance_m} м
            </Field>
            <Field label="Source refs">
              {firms.source_refs.length === 0 ? '—' : firms.source_refs.map((ref) => <div key={ref} className="mono small">{ref}</div>)}
            </Field>
          </dl>
          <p className="muted small">FIRMS-точки — тепловые аномалии, не периметр пожара и не ground truth.</p>
        </div>
      </div>

      <h3>Метод</h3>
      <dl className="fields">
        <Field label="Pipeline / code commit" mono>
          {method.pipeline_version} / {method.code_commit ?? 'null'}
        </Field>
        <Field label="Grid">{method.grid ? `EPSG:${method.grid.epsg}, ${method.grid.resolution_m} м, ${method.grid.width}×${method.grid.height}` : 'нет данных'}</Field>
        <Field label="Forest mask">
          {method.forest_mask ? `${method.forest_mask.source} (${method.forest_mask.version}, ${method.forest_mask.reference_year}) — ${method.forest_mask.interpretation_note}` : 'нет данных'}
        </Field>
      </dl>

      <h3>Ограничения</h3>
      <ul className="limitations" data-testid="limitations">
        {evidence.limitations.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>

      <h3>Артефакты (только artifacts[].url Backend)</h3>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Role</th>
              <th>Media</th>
              <th>SHA-256</th>
              <th>Браузер</th>
            </tr>
          </thead>
          <tbody>
            {verification.artifacts.map((artifact) => (
              <tr key={artifact.artifact_id}>
                <td>{artifact.role}</td>
                <td>{artifact.media_type}</td>
                <td>
                  <Hash value={artifact.sha256} />
                </td>
                <td>{artifact.media_type === 'image/tiff' ? 'GeoTIFF: не открывается в браузере' : 'отображается'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Решение Backend (policy {verification.decision_record.policy_version})</h3>
      <dl className="fields">
        <Field label="Decision / reason">
          {verification.decision} / {verification.reason}
        </Field>
        <Field label="Effective observed at / replay as of">
          {formatUtc(verification.decision_record.effective_observed_at)} / {formatUtc(verification.decision_record.replay_as_of)}
        </Field>
        <Field label="Processed at">{formatUtc(verification.processed_at)}</Field>
        <Field label="Policy parameters hash">
          <Hash value={verification.decision_record.policy_parameters_hash} />
        </Field>
      </dl>
    </div>
  );
}
