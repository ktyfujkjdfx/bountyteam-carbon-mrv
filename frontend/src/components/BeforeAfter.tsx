import { useState } from 'react';
import type { MrvApiClient } from '../api/client';
import type { EvidenceScene, Verification } from '../api/types';
import { artifactLink, evidenceArtifactFor } from '../domain/artifacts';
import { formatDate, formatUtc } from '../domain/format';
import { sameBounds } from '../domain/geo';
import { useArtifact } from '../hooks/useArtifact';
import { Empty, ErrorNotice, Skeleton } from './common';

interface Props {
  client: MrvApiClient;
  verification: Verification;
}

const link = artifactLink;
const meta = evidenceArtifactFor;

function SceneLabel({ side, scene }: { side: string; scene: EvidenceScene }) {
  return (
    <div className="scene-label">
      <strong>{side}</strong>
      <span className="mono">{scene.scene_id}</span>
      <span>
        {formatUtc(scene.acquired_at)} · {scene.provider}
        {scene.mgrs_tile ? ` · MGRS ${scene.mgrs_tile}` : ''}
      </span>
    </div>
  );
}

export function BeforeAfter({ client, verification }: Props) {
  const [position, setPosition] = useState(50);
  const beforeLink = link(verification, 'PREVIEW_BEFORE');
  const afterLink = link(verification, 'PREVIEW_AFTER');
  const before = useArtifact(client, beforeLink);
  const after = useArtifact(client, afterLink);
  const beforeMeta = meta(verification, beforeLink);
  const afterMeta = meta(verification, afterLink);
  const { before: beforeScene, after: afterScene } = verification.evidence.observation;

  if (!beforeLink || !afterLink) {
    return (
      <Empty>
        <strong>Нет пары превью</strong>
        <span>В evidence нет превью PNG/WebP до и после — сравнение недоступно. GeoTIFF в браузере не открывается.</span>
      </Empty>
    );
  }

  const aligned =
    beforeMeta !== null &&
    afterMeta !== null &&
    sameBounds(beforeMeta.bounds_wgs84, afterMeta.bounds_wgs84) &&
    beforeMeta.width === afterMeta.width &&
    beforeMeta.height === afterMeta.height;

  const width = afterMeta?.width ?? beforeMeta?.width ?? 1;
  const height = afterMeta?.height ?? beforeMeta?.height ?? 1;

  return (
    <div className="before-after" data-testid="before-after">
      <div className="scene-labels">
        <SceneLabel side="До · T before" scene={beforeScene} />
        <SceneLabel side="После · T after" scene={afterScene} />
      </div>
      {(before.loading || after.loading) && <Skeleton label="Загрузка превью наблюдения…" height={220} />}
      {before.error && <ErrorNotice error={before.error} compact title="Превью «до» недоступно" />}
      {after.error && <ErrorNotice error={after.error} compact title="Превью «после» недоступно" />}
      {!aligned && (
        <div className="state state-warn compact" role="alert" data-testid="not-aligned">
          Превью не выровнены (bounds или размер различаются) — слайдер отключён, показ бок о бок.
        </div>
      )}
      {before.payload?.kind === 'image' &&
        after.payload?.kind === 'image' &&
        (aligned ? (
          <>
            <div className="compare" style={{ aspectRatio: `${width} / ${height}` }}>
              <img src={before.payload.src} alt={`До: ${beforeScene.scene_id}`} draggable={false} />
              <img
                src={after.payload.src}
                alt={`После: ${afterScene.scene_id}`}
                draggable={false}
                className="compare-after"
                style={{ clipPath: `inset(0 0 0 ${position}%)` }}
              />
              <div className="compare-divider" style={{ left: `${position}%` }} aria-hidden="true" />
              <span className="compare-tag left">
                <b>До</b>
                <span className="mono">{formatDate(beforeScene.acquired_at)}</span>
              </span>
              <span className="compare-tag right">
                <b>После</b>
                <span className="mono">{formatDate(afterScene.acquired_at)}</span>
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              value={position}
              onChange={(e) => setPosition(Number(e.target.value))}
              aria-label="Положение разделителя до/после"
              className="compare-range"
            />
          </>
        ) : (
          <div className="side-by-side">
            <img src={before.payload.src} alt={`До: ${beforeScene.scene_id}`} style={{ aspectRatio: `${beforeMeta?.width ?? 1} / ${beforeMeta?.height ?? 1}` }} />
            <img src={after.payload.src} alt={`После: ${afterScene.scene_id}`} style={{ aspectRatio: `${width} / ${height}` }} />
          </div>
        ))}
      <p className="muted small">
        Одинаковые bounds_wgs84, {width}×{height} px. Превью подготовлены RS и отданы Backend; GeoTIFF в браузер не загружается.
      </p>
    </div>
  );
}
