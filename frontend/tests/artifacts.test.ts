// @vitest-environment node
import { describe, expect, it } from 'vitest';
import httpExamples from '../../fixtures/http_examples.json';
import type { Verification } from '../src/api/types';
import { artifactLink, evidenceArtifactFor } from '../src/domain/artifacts';

const fire = structuredClone(httpExamples.cases.find((c) => c.name === 'verification_fire')?.body) as unknown as Verification;

describe('artifact link ↔ evidence metadata', () => {
  it('matches by artifact_id when Backend publishes the RS id unchanged', () => {
    const link = artifactLink(fire, 'PREVIEW_AFTER');
    expect(evidenceArtifactFor(fire, link)?.bounds_wgs84).toHaveLength(4);
  });

  it('matches a Backend-namespaced id (<rs id>.<sha prefix>) by role + sha256', () => {
    const namespaced: Verification = {
      ...fire,
      artifacts: fire.artifacts.map((a) => ({ ...a, artifact_id: `${a.artifact_id}.${a.sha256.slice(2, 14)}`, url: `/api/v1/artifacts/${a.artifact_id}.${a.sha256.slice(2, 14)}` })),
    };
    const link = artifactLink(namespaced, 'PREVIEW_AFTER');
    expect(link?.artifact_id).toMatch(/^fire-preview_after\.[0-9a-f]{12}$/);
    const meta = evidenceArtifactFor(namespaced, link);
    expect(meta?.artifact_id).toBe('fire-preview_after');
    expect(meta?.width).toBe(400);
  });

  it('never pairs metadata of a different file', () => {
    const link = artifactLink(fire, 'PREVIEW_AFTER');
    const tampered = link ? { ...link, artifact_id: 'other-id', sha256: `0x${'a'.repeat(64)}` } : null;
    expect(evidenceArtifactFor(fire, tampered)).toBeNull();
    expect(evidenceArtifactFor(null, link)).toBeNull();
  });
});
