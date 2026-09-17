"""Contract error envelope: {"error": {code, message, details}, "request_id": uuid}. No stack traces or secrets."""
from __future__ import annotations

import uuid
from typing import Any


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def error_body(code: str, message: str, details: dict | None = None, request_id: str | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}},
            "request_id": request_id or str(uuid.uuid4())}


def unauthorized(message: str = "Demo session required") -> ApiError:
    return ApiError(401, "UNAUTHORIZED", message)


def forbidden(message: str) -> ApiError:
    return ApiError(403, "FORBIDDEN", message)


def not_found(what: str) -> ApiError:
    return ApiError(404, "NOT_FOUND", what + " not found")


def conflict(code: str, message: str, **details: Any) -> ApiError:
    return ApiError(409, code, message, details)


def invalid(code: str, message: str, **details: Any) -> ApiError:
    return ApiError(422, code, message, details)


def unavailable(code: str, message: str, **details: Any) -> ApiError:
    return ApiError(503, code, message, details)
