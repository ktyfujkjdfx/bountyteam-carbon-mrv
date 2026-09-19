"""Role integrity: who may act, what a read cannot change, and two separate axes."""
from __future__ import annotations

import json

import pytest

from carbon import build_passport
from carbon.workflow import (
    ACTOR_REF_PREFIX,
    ANCHOR_STATUSES,
    CALCULATED,
    CONFIRMED,
    DRAFT,
    FAILED,
    FINALIZED,
    INTEGRITY_FAILED,
    INVESTOR,
    NOT_REQUESTED,
    PASSPORT_STATUSES,
    PENDING,
    PROJECT_OWNER,
    VERIFIER,
    VIEWER,
    Actor,
    Lifecycle,
    WorkflowError,
    finalize,
    opaque_actor_ref,
    passport_workflow_block,
    record_calculation,
    record_integrity_failure,
    record_read,
    set_anchor_status,
    submit,
)

OWNER = Actor(PROJECT_OWNER, opaque_actor_ref("owner-1"))
AUDITOR = Actor(VERIFIER, opaque_actor_ref("verifier-1"))
BUYER = Actor(INVESTOR, opaque_actor_ref("investor-1"))
HASH = "0x" + "ab" * 32


def calculated() -> Lifecycle:
    state = submit(Lifecycle(), actor=OWNER, at="2026-09-19T10:00:00Z")
    return record_calculation(state, content_hash=HASH, at="2026-09-19T10:01:00Z")


# -- no personal data ----------------------------------------------------------------------


def test_an_actor_reference_is_opaque_and_stable():
    first = opaque_actor_ref("owner@example.com")
    assert first == opaque_actor_ref("owner@example.com")
    assert first.startswith(ACTOR_REF_PREFIX)
    assert "owner" not in first and "@" not in first
    assert opaque_actor_ref("someone-else") != first


def test_a_reference_that_still_looks_like_a_contact_detail_is_refused():
    with pytest.raises(ValueError, match="opaque"):
        Actor(PROJECT_OWNER, "owner@example.com")
    with pytest.raises(ValueError, match="personal data"):
        Actor(PROJECT_OWNER, ACTOR_REF_PREFIX + "a b@c")


def test_an_unknown_role_is_refused():
    with pytest.raises(ValueError, match="role must be one of"):
        Actor("ADMIN", opaque_actor_ref("x"))


def test_the_published_block_carries_roles_and_no_identity():
    state = finalize(calculated(), actor=AUDITOR, at="2026-09-19T11:00:00Z")
    block = passport_workflow_block(state)
    assert block["submitted_by_role"] == PROJECT_OWNER
    assert block["verified_by_role"] == VERIFIER
    serialised = json.dumps(block, ensure_ascii=False)
    assert "owner-1" not in serialised and "verifier-1" not in serialised
    assert "@" not in serialised
    assert "Персональные данные и секреты" in block["note"]


# -- who may do what -----------------------------------------------------------------------


def test_the_project_owner_submits():
    state = submit(Lifecycle(), actor=OWNER, at="2026-09-19T10:00:00Z")
    assert state.submitted_by_role == PROJECT_OWNER
    assert state.passport_status == DRAFT


@pytest.mark.parametrize("actor", [AUDITOR, BUYER, Actor(VIEWER, opaque_actor_ref("v"))])
def test_nobody_else_submits(actor):
    with pytest.raises(WorkflowError, match="only the project owner"):
        submit(Lifecycle(), actor=actor, at="2026-09-19T10:00:00Z")


def test_a_verifier_finalizes():
    state = finalize(calculated(), actor=AUDITOR, at="2026-09-19T11:00:00Z")
    assert state.passport_status == FINALIZED
    assert state.verified_by_role == VERIFIER
    assert state.finalized_content_hash == HASH


def test_the_project_owner_cannot_finalize_their_own_verification():
    """The whole point of a verifier is that the owner is not one."""
    with pytest.raises(WorkflowError, match="only a verifier"):
        finalize(calculated(), actor=OWNER, at="2026-09-19T11:00:00Z")


def test_an_investor_can_change_nothing():
    state = calculated()
    with pytest.raises(WorkflowError):
        submit(state, actor=BUYER, at="2026-09-19T12:00:00Z")
    with pytest.raises(WorkflowError):
        finalize(state, actor=BUYER, at="2026-09-19T12:00:00Z")
    after_reading = record_read(state, actor=BUYER, at="2026-09-19T12:00:00Z")
    assert after_reading.content_hash == state.content_hash
    assert after_reading.passport_status == state.passport_status
    assert after_reading.version == state.version


def test_an_uncalculated_passport_cannot_be_finalized():
    state = submit(Lifecycle(), actor=OWNER, at="2026-09-19T10:00:00Z")
    with pytest.raises(WorkflowError, match="only a calculated passport"):
        finalize(state, actor=AUDITOR, at="2026-09-19T11:00:00Z")


def test_a_finalized_passport_is_read_only():
    state = finalize(calculated(), actor=AUDITOR, at="2026-09-19T11:00:00Z")
    with pytest.raises(WorkflowError, match="read-only"):
        record_calculation(state, content_hash="0x" + "cd" * 32, at="2026-09-19T12:00:00Z")
    with pytest.raises(WorkflowError, match="cannot be resubmitted"):
        submit(state, actor=OWNER, at="2026-09-19T12:00:00Z")


def test_finalizing_fixes_the_version_that_was_verified():
    state = finalize(calculated(), actor=AUDITOR, at="2026-09-19T11:00:00Z")
    assert state.version == 1
    assert state.finalized_content_hash == state.content_hash == HASH


# -- reading changes nothing that is hashed ------------------------------------------------


@pytest.mark.parametrize("downloaded", [False, True])
def test_reading_is_recorded_and_moves_no_status(downloaded):
    state = calculated()
    after = record_read(state, actor=BUYER, at="2026-09-19T12:00:00Z", downloaded=downloaded)
    assert after.passport_status == state.passport_status == CALCULATED
    assert after.version == state.version
    assert after.content_hash == state.content_hash
    assert after.events[-1].is_passive is True


def test_many_reads_do_not_touch_the_scientific_hash(case):
    """The hash identifies the science; a hundred views cannot move it by one bit."""
    _, _, analysis, provenance = case("RU_TVER_01")
    passport = build_passport(analysis, provenance=provenance)
    state = record_calculation(
        submit(Lifecycle(), actor=OWNER, at="t0"),
        content_hash=passport.content_hash, at="t1",
    )
    for index in range(100):
        state = record_read(state, actor=BUYER, at=f"t{index}", downloaded=index % 2 == 0)
    assert state.content_hash == passport.content_hash
    assert len(state.events) == 102
    # nothing about the reads appears in the hashed content
    assert "VIEWED" not in json.dumps(passport.content, ensure_ascii=False)


# -- the two axes --------------------------------------------------------------------------


def test_the_passport_and_anchor_axes_are_separate():
    state = finalize(calculated(), actor=AUDITOR, at="2026-09-19T11:00:00Z")
    assert state.anchor_status == NOT_REQUESTED
    assert state.is_final is True
    assert state.is_anchored is False

    pending = set_anchor_status(state, PENDING)
    assert pending.passport_status == FINALIZED
    assert pending.is_anchored is False, "pending is not confirmed"

    failed = set_anchor_status(state, FAILED)
    assert failed.passport_status == FINALIZED, "a failed anchor is not a failed verification"
    assert failed.is_anchored is False

    confirmed = set_anchor_status(state, CONFIRMED)
    assert confirmed.is_anchored is True


def test_an_unknown_anchor_status_is_refused():
    with pytest.raises(ValueError, match="anchor status"):
        set_anchor_status(Lifecycle(), "ANCHORED_MAYBE")


def test_the_status_vocabularies_are_exactly_those_of_the_roadmap():
    assert PASSPORT_STATUSES == {"DRAFT", "CALCULATED", "FINALIZED", "INTEGRITY_FAILED"}
    assert ANCHOR_STATUSES == {"NOT_REQUESTED", "PENDING", "CONFIRMED", "FAILED"}
    assert PASSPORT_STATUSES & ANCHOR_STATUSES == set()


def test_a_failed_integrity_check_is_a_recorded_state():
    state = record_integrity_failure(
        calculated(), at="2026-09-19T13:00:00Z", detail="report.html hash mismatch"
    )
    assert state.passport_status == INTEGRITY_FAILED
    assert state.events[-1].detail == "report.html hash mismatch"
