import { useState } from 'react';
import type { MrvApiClient } from '../api/client';
import type { ArtifactLink, EvidenceArtifact, EvidenceScene, Verification } from '../api/types';
import { formatUtc } from '../domain/format';
import { sameBounds } from '../domain/geo';
import { useArtifact } from '../hooks/useArtifact';
import { Empty, ErrorNotice, Loading } from './common';

interface Props {
  client: MrvApiClient;
  verification: Verification;
}

function link(verification: Verification, role: ArtifactLink['role']): ArtifactLink | null {
  return verification.artifacts.find((a) => a.role === role) ?? null;
}

function meta(verification: Verification, artifact: ArtifactLink | null): EvidenceArtifact | null {
  if (!artifact) return null;
  return verification.evidence.artifacts.find((a) => a.artifact_id === artifact.artifact_id) ?? null;
}

function SceneLabel({ side, scene }: { side: string; scene: EvidenceScene }) {
  return (
    <span className="scene-label">
      <strong>{side}</strong> {formatUtc(scene.acquired_at)} · <span className="mono">{scene.scene_id}</span> · {scene.provider}
    </span>
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
    return <Empty>Для этого наблюдения нет пары превью PNG/WebP — сравнение до/после недоступно.</Empty>;
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
        <SceneLabel side="До (T_before):" scene={beforeScene} />
        <SceneLabel side="После (T_after):" scene={afterScene} />
      </div>
      {(before.loading || after.loading) && <Loading label="Загрузка превью…" />}
      {before.error && <ErrorNotice error={before.error} compact title="Превью «до» недоступно" />}
      {after.error && <ErrorNotice error={after.error} compact title="Превью «после» недоступно" />}
      {!aligned && (
        <div className="state state-warn" role="alert" data-testid="not-aligned">
          Превью не выровнены (bounds/размер различаются) — слайдер отключён, показ бок о бок.
        </div>
      )}
      {before.payload?.kind === 'image' && after.payload?.kind === 'image' && (
        aligned ? (
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
              <span className="compare-tag left">До · {beforeScene.acquired_at.slice(0, 10)}</span>
              <span className="compare-tag right">После · {afterScene.acquired_at.slice(0, 10)}</span>
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
        )
      )}
      <p className="muted small">
        Одинаковые bounds_wgs84 и размер {width}×{height} px; превью подготовлены RS и отданы Backend. GeoTIFF в браузер не загружается.
      </p>
    </div>
  );
}
