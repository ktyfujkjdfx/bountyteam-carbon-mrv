"""Canonical serialisation and content hashes of the carbon passport.

The repository already has a canonical form in P0: `rfc8785` (JCS, RFC 8785) with
`"0x" + sha256`, used by `tools/contract_helpers.py` and the backend. The passport reuses
it instead of inventing a second one, so a hash produced here means the same thing as a
hash produced there.

Two rules make the hash reproducible across platforms and runs:

1. numbers are normalised once, here, before serialisation — floats are rounded to
   `VALUE_DECIMALS` and negative zero is folded into zero, so `-0.0` and `0.0` cannot
   hash differently and the last bits of a double cannot move a hash;
2. non-finite numbers are rejected rather than encoded. `NaN` and `Infinity` are not
   JSON, and silently turning them into `null` would hide a broken calculation.

The content hash covers the scientific content only. Anything that changes between two
identical runs — a timestamp, a run identifier, a file name — is kept outside it and
travels in the envelope, so the same analysis run twice gives the same content hash.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

import rfc8785

FORMAT = "carbon.passport/1"
VALUE_DECIMALS = 9
HASH_ALGORITHM = "sha256"
HASH_PREFIX = "0x"


class CanonicalisationError(ValueError):
    """The value cannot be canonicalised: it is not representable in strict JSON."""


def normalise(value: Any) -> Any:
    """Return the value in the exact shape that is hashed.

    Mappings keep string keys only, sequences become lists, floats are rounded to
    `VALUE_DECIMALS` and non-finite numbers are refused. `bool` is checked before `int`
    because `True` is an `int` in Python and must stay a JSON boolean.
    """
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalisationError(f"non-finite number cannot be canonicalised: {value!r}")
        rounded = round(value, VALUE_DECIMALS)
        return rounded + 0.0
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise CanonicalisationError(f"object keys must be strings, got {key!r}")
        return {key: normalise(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalise(item) for item in value]
    raise CanonicalisationError(f"unsupported type in canonical payload: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    """JCS bytes of the normalised value: sorted keys, UTF-8, no insignificant space."""
    return rfc8785.dumps(normalise(value))


def sha256_bytes(data: bytes) -> str:
    """Hash of raw bytes in the same `0x…` form the rest of the repository uses."""
    return HASH_PREFIX + hashlib.sha256(data).hexdigest()


def content_hash(value: Any) -> str:
    """Stable hash of a structure: canonicalise first, then hash the bytes."""
    return sha256_bytes(canonical_bytes(value))
