"""FastAPI application implementing exactly the frozen /api/v1 contract (contracts/openapi.yaml).

Route handlers are sync `def`: FastAPI runs them in a threadpool, so SQLite and
web3 RPC I/O never block the asyncio event loop.
"""
from __future__ import annotations

import copy
import hmac
import logging
import re
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, StringConstraints
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import operations, views
from .config import Settings, load_settings
from .context import AppContext, create_context
from .contracts import openapi_document
from .errors import ApiError, error_body, invalid, unauthorized

log = logging.getLogger("backend.api")

PLOT_ID = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$"
UINT_DEC = r"^(0|[1-9][0-9]{0,77})$"
POSITIVE_DEC = r"^[1-9][0-9]{0,77}$"
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
ACTORS = ("issuer", "buyer", "recipient")

PlotId = Annotated[str, Path(pattern=PLOT_ID)]
BatchId = Annotated[str, Path(pattern=UINT_DEC)]
Actor = Literal["issuer", "buyer", "recipient"]


# -- request bodies: exactly the OpenAPI request schemas, no alternate DTOs -----------------------------
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class VerifyRequest(_Strict):
    scenario_id: Literal["baseline", "post_fire", "insufficient"]


class IssueRequest(_Strict):
    demo_authorization_id: Annotated[str, StringConstraints(pattern=PLOT_ID)]


class BuyRequest(_Strict):
    amount: Annotated[str, StringConstraints(pattern=POSITIVE_DEC)]


class TransferRequest(_Strict):
    to_actor: Actor
    amount: Annotated[str, StringConstraints(pattern=POSITIVE_DEC)]


# -- headers -------------------------------------------------------------------------------------------
def _ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def require_session(request: Request, x_demo_session: Annotated[str | None, Header()] = None) -> None:
    expected = request.app.state.ctx.settings.demo_session
    if not x_demo_session or not hmac.compare_digest(x_demo_session.encode(), expected.encode()):
        raise unauthorized()


def require_actor(x_demo_actor: Annotated[str | None, Header()] = None) -> str:
    if x_demo_actor not in ACTORS:
        raise invalid("VALIDATION_ERROR", "X-Demo-Actor header must be issuer, buyer or recipient")
    return x_demo_actor


def require_idempotency_key(idempotency_key: Annotated[str | None, Header()] = None) -> str:
    if idempotency_key is None or not 8 <= len(idempotency_key) <= 128:
        raise invalid("VALIDATION_ERROR", "Idempotency-Key header is required (8-128 characters)")
    return idempotency_key


def _uuid(value: str, name: str) -> str:
    if not UUID_RE.match(value):
        raise invalid("VALIDATION_ERROR", f"{name} must be a UUID")
    return value.lower()


Ctx = Annotated[AppContext, Depends(_ctx)]
ActorHeader = Annotated[str, Depends(require_actor)]
KeyHeader = Annotated[str, Depends(require_idempotency_key)]

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_session)])
public = APIRouter(prefix="/api/v1")


@public.get("/health")
def get_health(ctx: Ctx):
    return views.health(ctx)


@router.get("/plots")
def list_plots(ctx: Ctx):
    return views.plots(ctx)


@router.get("/plots/{plot_id}")
def get_plot(ctx: Ctx, plot_id: PlotId, actor: ActorHeader):
    return views.plot(ctx, plot_id, actor)


@router.post("/plots/{plot_id}/verify", status_code=202)
def start_verification(ctx: Ctx, plot_id: PlotId, body: VerifyRequest, actor: ActorHeader, key: KeyHeader):
    return operations.start_verification(ctx, actor, key, plot_id, body.model_dump())


@router.get("/jobs/{job_id}")
def get_job(ctx: Ctx, job_id: str):
    return views.job(ctx, _uuid(job_id, "job_id"))


@router.get("/verifications/{verification_id}")
def get_verification(ctx: Ctx, verification_id: str):
    return views.verification(ctx, _uuid(verification_id, "verification_id"))


@router.get("/verifications/{verification_id}/proof")
def get_proof(ctx: Ctx, verification_id: str):
    return views.proof(ctx, _uuid(verification_id, "verification_id"))


@router.get("/verifications/{verification_id}/canonical")
def get_canonical(ctx: Ctx, verification_id: str):
    # Exactly the stored JCS bytes that were hashed; no re-serialization.
    return Response(views.canonical_bytes(ctx, _uuid(verification_id, "verification_id")),
                    media_type="application/json")


@router.get("/plots/{plot_id}/history")
def get_history(ctx: Ctx, plot_id: PlotId):
    return views.history(ctx, plot_id)


@router.get("/plots/{plot_id}/credits")
def get_credits(ctx: Ctx, plot_id: PlotId, actor: ActorHeader):
    return views.credits(ctx, plot_id, actor)


@router.post("/plots/{plot_id}/issue", status_code=202)
def issue_batch(ctx: Ctx, plot_id: PlotId, body: IssueRequest, actor: ActorHeader, key: KeyHeader):
    return operations.request_issue(ctx, actor, key, plot_id, body.model_dump())


@router.post("/batches/{batch_id}/buy", status_code=202)
def buy_credits(ctx: Ctx, batch_id: BatchId, body: BuyRequest, actor: ActorHeader, key: KeyHeader):
    return operations.request_buy(ctx, actor, key, batch_id, body.model_dump())


@router.post("/batches/{batch_id}/transfer", status_code=202)
def transfer_credits(ctx: Ctx, batch_id: BatchId, body: TransferRequest, actor: ActorHeader, key: KeyHeader):
    return operations.request_transfer(ctx, actor, key, batch_id, body.model_dump())


@router.get("/operations/{operation_id}")
def get_operation(ctx: Ctx, operation_id: str):
    return views.operation(ctx, _uuid(operation_id, "operation_id"))


@router.get("/events")
def list_events(ctx: Ctx, plot_id: Annotated[str, Query(pattern=PLOT_ID)],
                cursor: Annotated[str | None, Query(min_length=1)] = None,
                limit: Annotated[int, Query(ge=1, le=100)] = 50):
    return views.events(ctx, plot_id, cursor, limit)


@router.get("/artifacts/{artifact_id}")
def get_artifact(ctx: Ctx, artifact_id: PlotId):
    data, media_type = views.artifact(ctx, artifact_id)
    return Response(data, media_type=media_type)


def frozen_openapi() -> dict:
    """The single source of truth for HTTP shape: the frozen contracts/openapi.yaml."""
    return copy.deepcopy(openapi_document())


def create_app(settings: Settings | None = None, ctx: AppContext | None = None, *,
               embedded_worker: bool = False) -> FastAPI:
    if ctx is None:
        ctx = create_context(settings or load_settings())
    worker_state: dict = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if embedded_worker:
            from .worker import start_worker_thread
            worker_state["thread"], worker_state["stop"] = start_worker_thread(ctx)
        yield
        if "stop" in worker_state:
            worker_state["stop"].set()
            worker_state["thread"].join(timeout=10)

    app = FastAPI(title="BountyTeam Backend", version="1.0.0", openapi_url="/openapi.json", docs_url="/docs",
                  redoc_url=None, lifespan=lifespan)
    app.state.ctx = ctx
    app.openapi = frozen_openapi  # type: ignore[method-assign]

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    def _envelope(request: Request, status: int, code: str, message: str, details: dict | None = None):
        request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
        return JSONResponse(error_body(code, message, details, request_id), status_code=status)

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return _envelope(request, exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [{"location": "/".join(str(p) for p in err.get("loc", ())), "message": str(err.get("msg"))[:200]}
                   for err in exc.errors()[:10]]
        return _envelope(request, 422, "VALIDATION_ERROR", "Request does not match the API contract",
                         {"errors": details})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code in (404, 405):
            return _envelope(request, 404, "NOT_FOUND", "Route not found")
        return _envelope(request, exc.status_code, "HTTP_ERROR", "Request failed")

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        log.exception("unhandled error")
        return _envelope(request, 503, "SERVICE_UNAVAILABLE", "Request could not be processed reliably")

    if ctx.settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(ctx.settings.cors_origins), allow_credentials=False,
                           allow_methods=["GET", "POST"],
                           allow_headers=["Content-Type", "Idempotency-Key", "X-Demo-Session", "X-Demo-Actor"],
                           expose_headers=["X-Request-ID"])
    app.include_router(public)
    app.include_router(router)
    return app
