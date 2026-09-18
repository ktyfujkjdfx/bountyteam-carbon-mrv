"""Detached integrity manifest for a passport and the files published beside it.

The manifest lists every artifact with its size and SHA-256 and repeats the passport
content hash. It never contains its own hash: a document that carries its own checksum
proves nothing, because anyone who edits the document can recompute the checksum. The
manifest hash is therefore kept outside — published separately, or anchored — and
`verify` needs that trusted value to say anything at all.

Without a trusted reference the check is only self-consistency: it proves the files match
the manifest they came with, which a forger can also arrange. `verify` reports that case
explicitly instead of returning a comforting "ok".

What this establishes: the bytes are the bytes that were sealed. What it does not
establish: that the estimate is correct, that the units exist in any registry, or that the
same result was not published elsewhere. Integrity is not exclusivity.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from . import canonical
from .passport import Passport

MANIFEST_FORMAT = "carbon.integrity-manifest/1"

CHECK_OK = "OK"
ARTIFACT_MISSING = "ARTIFACT_MISSING"
ARTIFACT_HASH_MISMATCH = "ARTIFACT_HASH_MISMATCH"
ARTIFACT_SIZE_MISMATCH = "ARTIFACT_SIZE_MISMATCH"
ARTIFACT_NOT_IN_MANIFEST = "ARTIFACT_NOT_IN_MANIFEST"
PASSPORT_HASH_MISMATCH = "PASSPORT_HASH_MISMATCH"
MANIFEST_HASH_MISMATCH = "MANIFEST_HASH_MISMATCH"
NO_TRUSTED_REFERENCE = "NO_TRUSTED_REFERENCE"

VERIFIED_AGAINST_TRUSTED_HASH = "VERIFIED_AGAINST_TRUSTED_HASH"
SELF_CONSISTENT_ONLY = "SELF_CONSISTENT_ONLY"
FAILED = "FAILED"


@dataclass(frozen=True)
class ArtifactRecord:
    name: str
    media_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    expected: str | int | None = None
    actual: str | int | None = None

    @property
    def ok(self) -> bool:
        return self.status == CHECK_OK


@dataclass(frozen=True)
class IntegrityReport:
    outcome: str
    checks: tuple[Check, ...]
    manifest_hash: str
    trusted_manifest_hash: str | None
    explanation: str

    @property
    def ok(self) -> bool:
        return self.outcome == VERIFIED_AGAINST_TRUSTED_HASH


def describe(name: str, data: bytes, *, media_type: str) -> ArtifactRecord:
    """Record one published file by its actual bytes."""
    return ArtifactRecord(
        name=name,
        media_type=media_type,
        size_bytes=len(data),
        sha256=canonical.HASH_PREFIX + hashlib.sha256(data).hexdigest(),
    )


def build_manifest(
    *,
    passport: Passport,
    artifacts: Sequence[ArtifactRecord],
    created_at: str,
    run_id: str,
    previous_manifest_hash: str | None = None,
) -> dict[str, Any]:
    """Build the detached manifest. It deliberately carries no hash of itself."""
    names = [artifact.name for artifact in artifacts]
    if len(set(names)) != len(names):
        raise ValueError("artifact names must be unique inside a manifest")
    return {
        "format": MANIFEST_FORMAT,
        "passport_format": passport.format,
        "passport_content_hash": passport.content_hash,
        "previous_content_hash": passport.content["previous_content_hash"],
        "previous_manifest_hash": previous_manifest_hash,
        "method_version": passport.content["method_version"],
        "artifacts": [
            {
                "name": artifact.name,
                "media_type": artifact.media_type,
                "size_bytes": artifact.size_bytes,
                "sha256": artifact.sha256,
            }
            for artifact in sorted(artifacts, key=lambda item: item.name)
        ],
        "created_at": created_at,
        "run_id": run_id,
        "note": (
            "Манифест не содержит собственного хеша. Его хеш публикуется отдельно; "
            "проверка без доверенного значения подтверждает только внутреннюю "
            "согласованность файлов и манифеста."
        ),
    }


def manifest_hash(manifest: Mapping[str, Any]) -> str:
    """Hash of the manifest as published. It is stored and compared outside the file."""
    return canonical.content_hash(dict(manifest))


def verify(
    *,
    manifest: Mapping[str, Any],
    artifacts: Mapping[str, bytes],
    trusted_manifest_hash: str | None = None,
    passport_content: Mapping[str, Any] | None = None,
) -> IntegrityReport:
    """Check downloaded files against a manifest and, if given, a trusted manifest hash."""
    checks: list[Check] = []
    computed = manifest_hash(manifest)

    if trusted_manifest_hash is None:
        checks.append(Check("manifest", NO_TRUSTED_REFERENCE, None, computed))
    elif trusted_manifest_hash != computed:
        checks.append(Check("manifest", MANIFEST_HASH_MISMATCH, trusted_manifest_hash, computed))
    else:
        checks.append(Check("manifest", CHECK_OK, trusted_manifest_hash, computed))

    declared = {entry["name"]: entry for entry in manifest.get("artifacts", [])}
    for name, entry in sorted(declared.items()):
        data = artifacts.get(name)
        if data is None:
            checks.append(Check(name, ARTIFACT_MISSING, entry["sha256"], None))
            continue
        if len(data) != entry["size_bytes"]:
            checks.append(Check(name, ARTIFACT_SIZE_MISMATCH, entry["size_bytes"], len(data)))
            continue
        actual = canonical.HASH_PREFIX + hashlib.sha256(data).hexdigest()
        status = CHECK_OK if actual == entry["sha256"] else ARTIFACT_HASH_MISMATCH
        checks.append(Check(name, status, entry["sha256"], actual))

    for name in sorted(set(artifacts) - set(declared)):
        checks.append(Check(name, ARTIFACT_NOT_IN_MANIFEST, None, None))

    if passport_content is not None:
        recomputed = canonical.content_hash(dict(passport_content))
        declared_hash = manifest.get("passport_content_hash")
        status = CHECK_OK if recomputed == declared_hash else PASSPORT_HASH_MISMATCH
        checks.append(Check("passport_content", status, declared_hash, recomputed))

    failures = [check for check in checks if check.status not in (CHECK_OK, NO_TRUSTED_REFERENCE)]
    if failures:
        outcome = FAILED
        explanation = (
            "Проверка не пройдена: содержимое не совпадает с тем, что было запечатано."
        )
    elif trusted_manifest_hash is None:
        outcome = SELF_CONSISTENT_ONLY
        explanation = (
            "Файлы согласованы с приложенным манифестом, но доверенное значение хеша "
            "манифеста не предоставлено. Подменённая копия вместе со своим манифестом "
            "прошла бы эту проверку, поэтому она не является подтверждением подлинности."
        )
    else:
        outcome = VERIFIED_AGAINST_TRUSTED_HASH
        explanation = (
            "Файлы совпадают с манифестом, а манифест — с доверенным значением хеша. "
            "Это подтверждает неизменность байтов, но не правильность оценки и "
            "не исключает публикацию того же результата в другом месте."
        )
    return IntegrityReport(
        outcome=outcome,
        checks=tuple(checks),
        manifest_hash=computed,
        trusted_manifest_hash=trusted_manifest_hash,
        explanation=explanation,
    )
