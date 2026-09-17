"""Versioned policy v1: evidence quality and decision in the frozen rule order.

All thresholds come from config/policy.v1.json; area/coverage gates use integer
pixel counts with exact Decimal arithmetic, never rounded display values.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .contracts import digest, read_json

PIXEL_AREA_HA = Decimal("0.04")


@dataclass(frozen=True)
class Policy:
    document: dict

    @classmethod
    def load(cls, path: Path) -> "Policy":
        document = read_json(path)
        for key in ("policy_version", "minimum_valid_forest_ratio", "sufficient_valid_forest_ratio",
                    "freeze_min_area_ha", "freeze_min_forest_fraction", "reason_code_fire_reversal"):
            if key not in document:
                raise ValueError("Policy is missing " + key)
        if document["automatic_unfreeze"] or document["automatic_revoke"]:
            raise ValueError("Policy v1 forbids automatic unfreeze/revoke")
        return cls(document)

    @property
    def version(self) -> str:
        return self.document["policy_version"]

    @property
    def parameters_hash(self) -> str:
        return digest(self.document)

    @property
    def fire_reversal_reason_code(self) -> int:
        return int(self.document["reason_code_fire_reversal"])

    def _dec(self, key: str) -> Decimal:
        return Decimal(str(self.document[key]))

    def evaluate(self, evidence: dict) -> dict:
        """Classify ONE evidence. No authorisation, transaction or state mutation here."""
        q = evidence["quality"]
        m = evidence["metrics"]
        n = m["baseline_forest_pixel_count"]
        v = m["paired_valid_forest_pixel_count"]
        k = m["affected_pixel_count"]
        ratio = None if n is None or n == 0 or v is None else Decimal(v) / Decimal(n)
        score = None if ratio is None else math.floor(100 * ratio + Decimal("0.5"))
        insufficient = (ratio is None or ratio < self._dec("minimum_valid_forest_ratio")
                        or not q["metadata_complete"] or not q["grid_aligned"]
                        or evidence["method"]["grid"] is None or evidence["method"]["forest_mask"] is None)
        if insufficient:
            quality, decision, reason = "INSUFFICIENT", "REVIEW_REQUIRED", "DATA_INSUFFICIENT"
        elif ratio < self._dec("sufficient_valid_forest_ratio") or q["temporal_comparability"] != "YES":
            quality, decision, reason = "REVIEW_REQUIRED", "REVIEW_REQUIRED", "DATA_REVIEW"
        elif evidence["outcome"] == "NO_CHANGE":
            quality, decision, reason = "SUFFICIENT", "NO_RESTRICTION", "NO_SIGNIFICANT_CHANGE"
        elif k is None:
            raise ValueError("Missing affected pixel count")
        elif (Decimal(k) * PIXEL_AREA_HA < self._dec("freeze_min_area_ha")
              or Decimal(k) / Decimal(n) < self._dec("freeze_min_forest_fraction")):
            quality, decision, reason = "SUFFICIENT", "REVIEW_REQUIRED", "BELOW_POLICY_THRESHOLD"
        elif self.document.get("require_firms_support", True) and evidence["firms"]["support"] != "SUPPORTED":
            quality, decision, reason = "SUFFICIENT", "REVIEW_REQUIRED", "DISTURBANCE_UNATTRIBUTED"
        else:
            quality, decision, reason = "SUFFICIENT", "FREEZE_REQUESTED", "FIRE_REVERSAL"
        return {"evidence_quality": quality, "evidence_quality_score": score,
                "decision": decision, "reason": reason}

    def decision_record(self, evidence: dict, evidence_hash: str, replay_as_of: str) -> dict:
        observed = evidence["observation"]["after"]["acquired_at"]
        if _utc(replay_as_of) < _utc(observed):
            raise ValueError("Cannot use future evidence in replay")
        result = self.evaluate(evidence)
        return {
            "evidence_hash": evidence_hash,
            "plot_id": evidence["plot_id"],
            "policy_version": self.version,
            "policy_parameters_hash": self.parameters_hash,
            "decision": result["decision"],
            "reason": result["reason"],
            "effective_observed_at": observed,
            "replay_as_of": replay_as_of,
        }


def _utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def action_flags(credit_status: str | None, latest_decision: str | None, *, is_latest: bool,
                 demo_authorized: bool, pending_freeze: bool = False) -> dict:
    """API gating identical to the reference helper. Direct ACTIVE transfers stay possible until freeze confirms."""
    gate = is_latest and latest_decision == "NO_RESTRICTION" and not pending_freeze
    return {
        "can_issue": gate and demo_authorized and credit_status is None,
        "can_buy": gate and credit_status == "ACTIVE",
        "can_transfer_backend": gate and credit_status == "ACTIVE",
    }
