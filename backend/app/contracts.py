"""Frozen contracts-v1.0.0 artifacts: JSON Schemas, OpenAPI, ABI, JCS/SHA-256 hashing."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import rfc8785
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from .config import REPO_ROOT

CONTRACTS = REPO_ROOT / "contracts"
ZERO_HASH = "0x" + "0" * 64


def _reject_constant(name: str):
    raise ValueError("Non-finite JSON number: " + name)


def loads_json(data: bytes | str) -> Any:
    """Strict JSON: NaN/Infinity literals are rejected, never coerced."""
    return json.loads(data, parse_constant=_reject_constant)


def read_json(path: Path) -> Any:
    return loads_json(Path(path).read_bytes().decode("utf-8"))


def canonical(value: Any) -> bytes:
    """RFC 8785 (JCS) canonical bytes."""
    return rfc8785.dumps(value)


def sha256_hex(data: bytes) -> str:
    return "0x" + hashlib.sha256(data).hexdigest()


def digest(value: Any) -> str:
    return sha256_hex(canonical(value))


def hash_to_bytes32(value: str) -> bytes:
    """Raw 32 digest bytes for Solidity bytes32; never keccak(text=hex)."""
    if not (isinstance(value, str) and len(value) == 66 and value.startswith("0x")):
        raise ValueError("Expected 0x-prefixed 32-byte hex hash")
    return bytes.fromhex(value[2:])


def bytes32_to_hash(value: bytes) -> str:
    return "0x" + bytes(value).hex()


@lru_cache(maxsize=None)
def _schema(name: str) -> dict:
    return read_json(CONTRACTS / name)


@lru_cache(maxsize=None)
def evidence_validator() -> Draft202012Validator:
    return Draft202012Validator(_schema("verification.schema.json"), format_checker=FormatChecker())


@lru_cache(maxsize=None)
def api_validator(model: str) -> Draft202012Validator:
    schema = dict(_schema("api-models.schema.json"))
    schema["$ref"] = "#/components/schemas/" + model
    return Draft202012Validator(schema, format_checker=FormatChecker())


@lru_cache(maxsize=None)
def deployment_validator() -> Draft202012Validator:
    return Draft202012Validator(_schema("deployment.schema.json"), format_checker=FormatChecker())


@lru_cache(maxsize=None)
def openapi_document() -> dict:
    return yaml.safe_load((CONTRACTS / "openapi.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def abi() -> list:
    return read_json(CONTRACTS / "contract-abi.json")


def abi_sha256() -> str:
    return sha256_hex((CONTRACTS / "contract-abi.json").read_bytes())


def schema_errors(validator: Draft202012Validator, value: Any, limit: int = 10) -> list[dict]:
    errors = sorted(validator.iter_errors(value), key=lambda e: list(e.absolute_path))
    return [{"path": "/".join(str(p) for p in err.absolute_path) or "$", "message": err.message[:300]}
            for err in errors[:limit]]
