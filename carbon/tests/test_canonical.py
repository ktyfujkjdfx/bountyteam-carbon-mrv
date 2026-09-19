"""Canonical serialisation: same content, same bytes, same hash — or a refusal."""
from __future__ import annotations

import json

import pytest

from carbon import canonical


def test_key_order_does_not_change_the_hash():
    first = {"b": 1, "a": {"y": 2, "x": 3}}
    second = {"a": {"x": 3, "y": 2}, "b": 1}
    assert canonical.canonical_bytes(first) == canonical.canonical_bytes(second)
    assert canonical.content_hash(first) == canonical.content_hash(second)


def test_negative_zero_hashes_as_zero():
    assert canonical.content_hash({"x": -0.0}) == canonical.content_hash({"x": 0.0})
    assert canonical.normalise(-0.0) == 0.0


def test_floats_are_rounded_once_so_the_last_bits_cannot_move_a_hash():
    below = 1.0 + 1e-12
    assert canonical.content_hash({"x": below}) == canonical.content_hash({"x": 1.0})
    # a difference the method actually cares about still changes the hash
    assert canonical.content_hash({"x": 1.000001}) != canonical.content_hash({"x": 1.0})


def test_integers_stay_integers_and_booleans_stay_booleans():
    assert canonical.canonical_bytes({"n": 5, "flag": True}) == b'{"flag":true,"n":5}'


def test_tuples_and_lists_are_the_same_document():
    assert canonical.content_hash({"x": (1, 2)}) == canonical.content_hash({"x": [1, 2]})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_refused_not_encoded(value):
    with pytest.raises(canonical.CanonicalisationError):
        canonical.canonical_bytes({"x": value})


def test_non_string_keys_are_refused():
    with pytest.raises(canonical.CanonicalisationError):
        canonical.canonical_bytes({1: "x"})


def test_unsupported_types_are_refused_rather_than_stringified():
    with pytest.raises(canonical.CanonicalisationError):
        canonical.canonical_bytes({"x": {1, 2}})


def test_unicode_survives_a_round_trip_as_utf8():
    payload = {"название": "Мордовия — пожар", "symbol": "тCO₂-экв."}
    data = canonical.canonical_bytes(payload)
    assert json.loads(data.decode("utf-8")) == payload


def test_hash_is_the_sha256_of_the_canonical_bytes():
    payload = {"a": 1}
    assert canonical.content_hash(payload) == canonical.sha256_bytes(
        canonical.canonical_bytes(payload)
    )
    assert canonical.content_hash(payload).startswith("0x")
    assert len(canonical.content_hash(payload)) == 66


def test_the_canonical_form_matches_the_p0_reference_helper():
    """The passport must hash the way the rest of the repository already hashes."""
    helpers = pytest.importorskip("tools.contract_helpers")
    payload = {"b": [1, 2], "a": "ю"}
    assert canonical.canonical_bytes(payload) == helpers.canonical(payload)
    assert canonical.content_hash(payload) == helpers.digest(payload)
