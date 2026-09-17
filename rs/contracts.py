"""Re-export the shared reference validator (tools/contract_helpers.py).

RS must use the SAME canonicalization/hash implementation as the shared tests
and Backend, not a second one, so `plot_geometry_hash` and `config_sha256`
agree bit-for-bit with what Backend recomputes. This module only imports;
it does not modify shared contracts.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "tools"))

from contract_helpers import (  # noqa: E402  (path setup must precede this import)
    canonical,
    check_schema,
    digest,
    read_json,
    safe_path,
    sha_bytes,
    validate_evidence,
    validate_geometry,
)

__all__ = [
    "canonical",
    "check_schema",
    "digest",
    "read_json",
    "safe_path",
    "sha_bytes",
    "validate_evidence",
    "validate_geometry",
]
