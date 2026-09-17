import type { ArtifactLink, ArtifactRole, EvidenceArtifact, Verification } from '../api/types';

export function artifactLink(verification: Verification | null, role: ArtifactRole): ArtifactLink | null {
  return verification?.artifacts.find((a) => a.role === role) ?? null;
}

// Backend may namespace a published id (`<rs id>.<sha prefix>`); role + sha256 identify the same file across both lists.
export function evidenceArtifactFor(verification: Verification | null, link: ArtifactLink | null): EvidenceArtifact | null {
  if (!verification || !link) return null;
  const artifacts = verification.evidence.artifacts;
  return (
    artifacts.find((a) => a.artifact_id === link.artifact_id) ??
    artifacts.find((a) => a.role === link.role && a.sha256 === link.sha256) ??
    null
  );
}
