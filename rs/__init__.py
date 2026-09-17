"""RS pipeline package: produces schema-valid VerificationEvidence bundles.

Never emits FROZEN/ACTIVE/REVOKED/FREEZE_REQUESTED or a final evidence_hash;
those are Backend-owned. See docs/roles/02_RS_PLAN.md for the frozen method.
"""

PIPELINE_VERSION = "1.0.0"
