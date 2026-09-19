"""The HTTP surface of /api/v2.

This is a separate ASGI application. `backend.app.main.create_app` is not touched, does
not learn about v2 and keeps serving exactly the frozen v1 contract at `/openapi.json`;
the two are composed side by side at the process entry point. That is why a v2 route can
never appear in the v1 document, and why the v1 route guard keeps meaning what it says.

Handlers validate the wire shape and delegate. They are sync `def`, so FastAPI runs them
in a threadpool and SQLite never blocks the event loop.
"""
from __future__ import annotations

import copy
import logging
import re
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict
from starlette.applications import Starlette
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Mount

from ..errors import ApiError, error_body, invalid
from . import auth, service
from .contracts import ContractViolation, openapi_v2_document
from .service import LensContext

log = logging.getLogger("backend.lens.api")

ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:+-]{0,127}$"
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                     r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

AnalysisId = Annotated[str, Path(pattern=ID_PATTERN)]
ArtifactId = Annotated[str, Path(pattern=ID_PATTERN)]
RequestId = Annotated[str, Path(pattern=ID_PATTERN)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ClaimScopeBody(_Strict):
    geometry_hash: str
    year_start: int
    year_end: int
    pool: str
    unit: str


class LoginBody(_Strict):
    username: str
    password: str


class AreaMeasureBody(_Strict):
    geometry: dict[str, Any]


class CreateRequestBody(_Strict):
    year_start: int
    year_end: int
    aoi_id: str | None = None
    geometry: dict[str, Any] | None = None
    claimed_units: int | float | None = None


class UpdateRequestBody(_Strict):
    claimed_units: int | float | None


class AnalysisRequestBody(_Strict):
    year_start: int
    year_end: int
    aoi_id: str | None = None
    geometry: dict[str, Any] | None = None
    claimed_units: int | float | None = None
    claim_origin: Literal["USER_INPUT", "DEMO_INPUT"] | None = None
    claim_scope: ClaimScopeBody | None = None
    include_optical: bool = True


def _lens(request: Request) -> LensContext:
    return request.app.state.lens


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str | None:
    """The opaque session token, or nothing. The scheme name is not case sensitive."""
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def principal(request: Request,
              authorization: Annotated[str | None, Header()] = None) -> auth.Principal:
    """Who is acting. Read from the session row, never from anything the client names."""
    return auth.resolve(request.app.state.lens.app, bearer_token(authorization))


def require_idempotency_key(idempotency_key: Annotated[str | None, Header()] = None) -> str:
    if idempotency_key is None or not 8 <= len(idempotency_key) <= 128:
        raise invalid("VALIDATION_ERROR", "Idempotency-Key header is required (8-128 characters)")
    return idempotency_key


def _uuid(value: str) -> str:
    if not UUID_RE.match(value):
        raise invalid("VALIDATION_ERROR", "analysis_id must be a UUID")
    return value.lower()


Lens = Annotated[LensContext, Depends(_lens)]
Who = Annotated[auth.Principal, Depends(principal)]
Token = Annotated[str | None, Depends(bearer_token)]
KeyHeader = Annotated[str, Depends(require_idempotency_key)]

router = APIRouter()


# -- signing in ------------------------------------------------------------------------
@router.post("/auth/login")
def login(lens: Lens, body: LoginBody):
    return auth.login(lens.app, username=body.username, password=body.password)


@router.get("/auth/me")
def whoami(who: Who):
    return who.public


@router.post("/auth/logout")
def logout(lens: Lens, token: Token, who: Who):
    auth.audit(lens.app, who.user_id, who.role, "LOGOUT", who.user_id)
    return auth.logout(lens.app, token)


# -- verification requests ---------------------------------------------------------------
@router.post("/requests", status_code=201)
def create_request(lens: Lens, who: Who, body: CreateRequestBody):
    auth.require(who, "analysis.create")
    return service.create_request(lens, who=who, body=body.model_dump())


@router.get("/requests")
def list_requests(lens: Lens, who: Who):
    auth.require(who, "catalog.read")
    return service.list_requests(lens, who=who)


@router.get("/requests/{request_id}")
def get_request(lens: Lens, who: Who, request_id: RequestId):
    return service.request_view(lens, request_id, who=who)


@router.patch("/requests/{request_id}")
def update_request(lens: Lens, who: Who, request_id: RequestId, body: UpdateRequestBody):
    return service.update_request(lens, request_id, who=who, body=body.model_dump())


@router.post("/requests/{request_id}/submit")
def submit_request(lens: Lens, who: Who, request_id: RequestId):
    return service.submit_request(lens, request_id, who=who)


@router.post("/requests/{request_id}/analysis", status_code=202)
def run_request_analysis(lens: Lens, who: Who, request_id: RequestId, key: KeyHeader):
    return service.start_request_analysis(lens, request_id, who=who, key=key)


@router.post("/requests/{request_id}/finalize")
def finalize_request(lens: Lens, who: Who, request_id: RequestId):
    return service.finalize_request(lens, request_id, who=who)


# -- the work --------------------------------------------------------------------------
@router.get("/catalog")
def get_catalog(lens: Lens, who: Who):
    auth.require(who, "catalog.read")
    return service.catalog_view(lens)


@router.post("/areas/measure")
def measure_area(lens: Lens, who: Who, body: AreaMeasureBody):
    auth.require(who, "area.measure")
    return service.measure_area(lens, body.model_dump())


@router.post("/analyses", status_code=202)
def create_analysis(lens: Lens, who: Who, body: AnalysisRequestBody, key: KeyHeader):
    auth.require(who, "analysis.create")
    return service.submit(lens, who=who, key=key,
                          body=body.model_dump(exclude_unset=False))


@router.get("/analyses/{analysis_id}")
def get_analysis(lens: Lens, who: Who, analysis_id: AnalysisId):
    return service.analysis_view(lens, _uuid(analysis_id), who=who)


@router.get("/analyses/{analysis_id}/artifacts/{artifact_id}")
def get_artifact(lens: Lens, who: Who, analysis_id: AnalysisId, artifact_id: ArtifactId):
    data, media_type = service.artifact_bytes(lens, _uuid(analysis_id), artifact_id,
                                              who=who)
    return Response(data, media_type=media_type)


@router.get("/analyses/{analysis_id}/report")
def get_report(lens: Lens, who: Who, analysis_id: AnalysisId,
               format: Annotated[Literal["json", "html"], Query()] = "json"):
    identifier = _uuid(analysis_id)
    if format == "html":
        return Response(service.report_html(lens, identifier, who=who),
                        media_type="text/html; charset=utf-8")
    return service.report_view(lens, identifier, who=who)


@router.get("/analyses/{analysis_id}/proof")
def get_proof(lens: Lens, who: Who, analysis_id: AnalysisId):
    return service.proof_view(lens, _uuid(analysis_id), who=who)


def frozen_openapi_v2() -> dict:
    """The single source of truth for the v2 HTTP shape: contracts/v2/openapi.v2.yaml."""
    return copy.deepcopy(openapi_v2_document())


def create_lens_app(lens: LensContext) -> FastAPI:
    """The Lens application. It is mounted under /api/v2 and owns nothing above it."""
    # The document is served by a route of our own rather than by the generated one:
    # under a mount FastAPI rewrites `servers` to describe where it was mounted, and the
    # published contract would then no longer be byte-for-byte what the repository holds.
    app = FastAPI(title="BountyTeam Carbon Lens", version="2.0.0",
                  openapi_url=None, docs_url=None, redoc_url=None)
    app.state.lens = lens
    app.openapi = frozen_openapi_v2  # type: ignore[method-assign]

    @app.get("/openapi.json", include_in_schema=False)
    def openapi_json():
        return frozen_openapi_v2()

    @app.get("/docs", include_in_schema=False)
    def docs():
        from fastapi.openapi.docs import get_swagger_ui_html

        return get_swagger_ui_html(openapi_url="/api/v2/openapi.json",
                                   title="BountyTeam Carbon Lens")

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    def envelope(request: Request, status: int, code: str, message: str,
                 details: dict | None = None):
        request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
        return JSONResponse(error_body(code, message, details, request_id), status_code=status)

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return envelope(request, exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(ContractViolation)
    async def contract_violation(request: Request, exc: ContractViolation):
        # A payload that does not match the contract is never served with a warning.
        log.error("v2 contract violation in %s: %s", exc.model, exc.errors)
        return envelope(request, 503, "CONTRACT_VIOLATION",
                        "Результат не соответствует контракту и не выдан",
                        {"model": exc.model})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = {"category": "REQUEST_SCHEMA",
                   "errors": [{"location": "/".join(str(part) for part in err.get("loc", ())),
                               "message": str(err.get("msg"))[:200]}
                              for err in exc.errors()[:10]]}
        return envelope(request, 422, "VALIDATION_ERROR",
                        "Request does not match the API contract", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code in (404, 405):
            return envelope(request, 404, "NOT_FOUND", "Route not found")
        return envelope(request, exc.status_code, "HTTP_ERROR", "Request failed")

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        log.exception("unhandled lens error")
        return envelope(request, 503, "SERVICE_UNAVAILABLE",
                        "Request could not be processed reliably")

    origins = lens.app.settings.cors_origins
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(origins), allow_credentials=False,
                           allow_methods=["GET", "POST"],
                           allow_headers=["Content-Type", "Idempotency-Key",
                                          "Authorization"],
                           expose_headers=["X-Request-ID"])
    app.include_router(router)
    return app


def compose(v1_app: Any, lens_app: Any) -> Starlette:
    """Serve both contracts from one port without either knowing about the other.

    /api/v2 goes to the Lens application; everything else, including /openapi.json and
    the whole of /api/v1, reaches the untouched P0 application.
    """
    return Starlette(routes=[Mount("/api/v2", app=lens_app), Mount("/", app=v1_app)],
                     lifespan=getattr(v1_app.router, "lifespan_context", None))
