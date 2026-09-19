"""Loading and validation of the v2 contract documents.

Hashing, canonicalization and strict JSON reading are reused from the v1 module
rather than reimplemented: a second canonicalizer would be a second answer to the
question "what are these bytes", which is the one question a passport must not
have two answers to.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from ..config import REPO_ROOT
from ..contracts import canonical, digest, read_json, schema_errors, sha256_hex

CONTRACTS_V2 = REPO_ROOT / "contracts" / "v2"
FIXTURES_V2 = REPO_ROOT / "fixtures" / "v2"

API_MODELS = "api-models.v2.schema.json"
INTERNAL_MODELS = "internal-models.v2.schema.json"
OPENAPI = "openapi.v2.yaml"

SCHEMA_VERSION = "carbon-lens-api/2.0.0"
BACKEND_METHOD_VERSION = "carbon-lens-backend/2.0.0"

__all__ = [
    "API_MODELS",
    "BACKEND_METHOD_VERSION",
    "CONTRACTS_V2",
    "ContractViolation",
    "FIXTURES_V2",
    "INTERNAL_MODELS",
    "SCHEMA_VERSION",
    "api_validator",
    "canonical",
    "digest",
    "internal_validator",
    "openapi_v2_document",
    "read_json",
    "schema_errors",
    "sha256_hex",
    "validate",
]


class ContractViolation(RuntimeError):
    """A payload crossing a v2 boundary does not match its schema."""

    def __init__(self, model: str, errors: list[dict]):
        super().__init__(f"{model} does not match the v2 contract")
        self.model = model
        self.errors = errors


@lru_cache(maxsize=None)
def _document(name: str) -> dict:
    return read_json(CONTRACTS_V2 / name)


@lru_cache(maxsize=None)
def _validator(document: str, model: str) -> Draft202012Validator:
    schema = dict(_document(document))
    schema["$ref"] = "#/components/schemas/" + model
    return Draft202012Validator(schema, format_checker=FormatChecker())


def api_validator(model: str) -> Draft202012Validator:
    return _validator(API_MODELS, model)


def internal_validator(model: str) -> Draft202012Validator:
    return _validator(INTERNAL_MODELS, model)


@lru_cache(maxsize=None)
def openapi_v2_document() -> dict:
    return yaml.safe_load((CONTRACTS_V2 / OPENAPI).read_text(encoding="utf-8"))


def validate(validator: Draft202012Validator, value: Any, model: str) -> Any:
    """Validate a payload crossing a boundary; raises ContractViolation, never a schema dump."""
    errors = schema_errors(validator, value)
    if errors:
        raise ContractViolation(model, errors)
    return value


def fixture(name: str) -> Any:
    return read_json(FIXTURES_V2 / name)


def contract_hashes() -> dict[str, str]:
    """Hash of each contract document, so a result can name the contract it was built against."""
    return {name: sha256_hex((CONTRACTS_V2 / name).read_bytes())
            for name in (API_MODELS, INTERNAL_MODELS, OPENAPI)}


def file_sha256(path: Path) -> str:
    return sha256_hex(Path(path).read_bytes())
