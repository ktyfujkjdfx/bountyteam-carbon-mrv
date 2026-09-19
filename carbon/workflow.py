"""Who did what to a passport, recorded without learning who they are.

Authorization belongs to Backend. This module holds the methodological half of the same
question: which role acted, in what order, and what that means for the record. It stores a
role and an opaque reference, never a name, an address or a secret, so an audit trail can
be kept without the passport becoming personal data.

Three separations do the work.

The scientific content is immutable. Viewing, downloading, finalizing and anchoring are
recorded beside it and are absent from `scientific_passport_content_hash`, so reading a
passport a hundred times cannot change its identity by one bit.

A role cannot do another role's job. The owner of a project submits it and can never
finalize its verification; a verifier finalizes it; an investor reads it and can change
nothing at all. The rule is enforced here, not merely described.

`passport_status` and `anchor_status` are separate axes. A passport can be FINALIZED with
nothing anchored, and an anchor can be PENDING while the science is already fixed. A
pending anchor is not a confirmed one and a failed one is not a verification.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace

# Roles. They describe a capability, never a person.
PROJECT_OWNER = "PROJECT_OWNER"
VERIFIER = "VERIFIER"
INVESTOR = "INVESTOR"
VIEWER = "VIEWER"
ROLES = frozenset({PROJECT_OWNER, VERIFIER, INVESTOR, VIEWER})

# Where the passport is in its life.
DRAFT = "DRAFT"
CALCULATED = "CALCULATED"
FINALIZED = "FINALIZED"
INTEGRITY_FAILED = "INTEGRITY_FAILED"
PASSPORT_STATUSES = frozenset({DRAFT, CALCULATED, FINALIZED, INTEGRITY_FAILED})

# Whether its hash has been anchored. A separate axis on purpose.
NOT_REQUESTED = "NOT_REQUESTED"
PENDING = "PENDING"
CONFIRMED = "CONFIRMED"
FAILED = "FAILED"
ANCHOR_STATUSES = frozenset({NOT_REQUESTED, PENDING, CONFIRMED, FAILED})

# Events. The first three change the status; the last two never do.
SUBMITTED = "SUBMITTED"
CALCULATED_EVENT = "CALCULATED"
FINALIZED_EVENT = "FINALIZED"
VIEWED = "VIEWED"
DOWNLOADED = "DOWNLOADED"
INTEGRITY_CHECK_FAILED = "INTEGRITY_CHECK_FAILED"
PASSIVE_EVENTS = frozenset({VIEWED, DOWNLOADED})

ACTOR_REF_PREFIX = "actor:"


class WorkflowError(PermissionError):
    """A role tried to do something the workflow does not allow it to do."""


def opaque_actor_ref(identifier: str, *, salt: str = "carbon-lens") -> str:
    """A stable, non-reversible reference to an actor.

    The passport must be able to say "the same verifier acted twice" without carrying an
    address or a name. Hashing with a deployment salt gives that and nothing more.
    """
    if not identifier:
        raise ValueError("an actor identifier is required to build a reference")
    digest = hashlib.sha256(f"{salt}:{identifier}".encode("utf-8")).hexdigest()
    return ACTOR_REF_PREFIX + digest[:32]


@dataclass(frozen=True)
class Actor:
    role: str
    ref: str

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"role must be one of {sorted(ROLES)}")
        if not self.ref.startswith(ACTOR_REF_PREFIX):
            raise ValueError(
                "an actor reference must be opaque; build it with opaque_actor_ref"
            )
        # A reference that still looks like a contact detail is not opaque.
        if "@" in self.ref or " " in self.ref:
            raise ValueError("an actor reference must carry no personal data")


@dataclass(frozen=True)
class Event:
    kind: str
    role: str
    actor_ref: str
    at: str
    detail: str | None = None

    @property
    def is_passive(self) -> bool:
        return self.kind in PASSIVE_EVENTS


@dataclass(frozen=True)
class Lifecycle:
    """The mutable half of a passport: status, version and who acted."""

    passport_status: str = DRAFT
    anchor_status: str = NOT_REQUESTED
    version: int = 0
    content_hash: str | None = None
    finalized_content_hash: str | None = None
    submitted_by_role: str | None = None
    verified_by_role: str | None = None
    events: tuple[Event, ...] = field(default_factory=tuple)

    @property
    def is_final(self) -> bool:
        return self.passport_status == FINALIZED

    @property
    def is_anchored(self) -> bool:
        return self.anchor_status == CONFIRMED

    def _add(self, event: Event, **changes: object) -> "Lifecycle":
        return replace(self, events=(*self.events, event), **changes)


def submit(lifecycle: Lifecycle, *, actor: Actor, at: str) -> Lifecycle:
    """The project owner submits an area for analysis."""
    if actor.role != PROJECT_OWNER:
        raise WorkflowError("only the project owner submits an area for analysis")
    if lifecycle.is_final:
        raise WorkflowError("a finalized passport cannot be resubmitted")
    return lifecycle._add(
        Event(SUBMITTED, actor.role, actor.ref, at),
        submitted_by_role=actor.role,
    )


def record_calculation(lifecycle: Lifecycle, *, content_hash: str, at: str) -> Lifecycle:
    """The engine produced a result. No role is needed: the calculation is not an opinion."""
    if lifecycle.is_final:
        raise WorkflowError(
            "a finalized passport is read-only; a new calculation is a new version"
        )
    return lifecycle._add(
        Event(CALCULATED_EVENT, lifecycle.submitted_by_role or VIEWER,
              lifecycle.events[-1].actor_ref if lifecycle.events else ACTOR_REF_PREFIX + "0" * 32,
              at, detail=content_hash),
        passport_status=CALCULATED,
        content_hash=content_hash,
        version=lifecycle.version + 1,
    )


def finalize(lifecycle: Lifecycle, *, actor: Actor, at: str) -> Lifecycle:
    """A verifier fixes the version. The owner of the project can never do this."""
    if actor.role != VERIFIER:
        raise WorkflowError("only a verifier finalizes a verification")
    if lifecycle.passport_status != CALCULATED:
        raise WorkflowError("only a calculated passport can be finalized")
    if lifecycle.content_hash is None:
        raise WorkflowError("a passport without a content hash cannot be finalized")
    return lifecycle._add(
        Event(FINALIZED_EVENT, actor.role, actor.ref, at, detail=lifecycle.content_hash),
        passport_status=FINALIZED,
        verified_by_role=actor.role,
        finalized_content_hash=lifecycle.content_hash,
    )


def record_read(lifecycle: Lifecycle, *, actor: Actor, at: str, downloaded: bool = False) -> Lifecycle:
    """Reading is recorded and changes nothing that is hashed."""
    return lifecycle._add(Event(DOWNLOADED if downloaded else VIEWED, actor.role, actor.ref, at))


def record_integrity_failure(lifecycle: Lifecycle, *, at: str, detail: str) -> Lifecycle:
    """A failed check is a state of the record, not a silent condition."""
    return lifecycle._add(
        Event(INTEGRITY_CHECK_FAILED, VIEWER, ACTOR_REF_PREFIX + "0" * 32, at, detail=detail),
        passport_status=INTEGRITY_FAILED,
    )


def set_anchor_status(lifecycle: Lifecycle, status: str) -> Lifecycle:
    """Move the anchor axis. It never moves the passport axis."""
    if status not in ANCHOR_STATUSES:
        raise ValueError(f"anchor status must be one of {sorted(ANCHOR_STATUSES)}")
    return replace(lifecycle, anchor_status=status)


def passport_workflow_block(lifecycle: Lifecycle) -> dict[str, object]:
    """The workflow as it appears beside a passport — roles only, no identities."""
    return {
        "passport_status": lifecycle.passport_status,
        "anchor_status": lifecycle.anchor_status,
        "version": lifecycle.version,
        "submitted_by_role": lifecycle.submitted_by_role,
        "verified_by_role": lifecycle.verified_by_role,
        "finalized_content_hash": lifecycle.finalized_content_hash,
        "events": [
            {"kind": event.kind, "role": event.role, "actor_ref": event.actor_ref,
             "at": event.at, "detail": event.detail}
            for event in lifecycle.events
        ],
        "note": (
            "Роли и непрозрачные ссылки на участников. Персональные данные и секреты "
            "не хранятся. Просмотр и скачивание не входят в научный хеш паспорта."
        ),
    }
