"""Use cases of /api/v2: accept an analysis, run it, read it back, serve its files.

The route handlers hold no science and no policy. They validate the wire shape and call
into here; this module validates the request, snapshots what the analysis will be run
against, calls the two ports in order, and hands the assembled result to the store.

Two hashes with two jobs, deliberately not merged:

- the **request hash** binds an Idempotency-Key to the exact request that was sent,
  including the stated claim, so replaying a key with a different body is a 409;
- the **input hash** identifies the scientific inputs — contour, period, dataset,
  parameters and method — and excludes the claim, because a stated volume never changes
  a measurement and must not force a recomputation of one.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..context import AppContext, audit
from ..contracts import digest
from ..db import utc_now
from ..errors import ApiError, invalid, not_found
from ..operations import idempotent
from . import assemble, auth as lens_auth, catalog, demo, geometry, verification
from .adapters import build_ports
from .adapters.carbon import POOL, CarbonEngineUnavailable
from .adapters.raster import RasterCoreUnavailable
from .contracts import BACKEND_METHOD_VERSION, SCHEMA_VERSION, api_validator, validate
from .ports import CarbonRequest, RasterRequest, RasterUnavailable
from .store import LensStore, artifact_record, new_id, scope_key

log = logging.getLogger("backend.lens.service")

OPERATION = "createAnalysis"
CELLS_ROLE = "cells"
CELLS_MEDIA_TYPE = "application/geo+json"


@dataclass(frozen=True)
class LensContext:
    app: AppContext
    store: LensStore
    ports: Any

    @property
    def adapters(self) -> dict[str, str]:
        return {"raster": self.ports.raster.name, "carbon": self.ports.carbon.name}


def create_lens_context(ctx: AppContext, *, engine_mode: str | None = None,
                        carbon_module_override: Any = None) -> LensContext:
    """Build the Lens for this deployment.

    If the engines this deployment needs are not installed, this raises. A deployment
    that would rather be down than approximately right sets `BACKEND_LENS_REQUIRE_REAL`
    and gets that failure at startup; otherwise the Lens is disabled and `/api/v1` keeps
    serving, which is still not the same as answering with invented numbers.
    """
    settings = ctx.settings
    return LensContext(
        app=ctx,
        store=LensStore(ctx, Path(settings.lens_artifact_store)),
        ports=build_ports(Path(settings.lens_work_dir),
                          engine_mode=engine_mode or settings.lens_engine_mode,
                          carbon_module_override=carbon_module_override))


# -- request ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResolvedRequest:
    snapshot: dict
    geometry: Any
    geometry_hash: str
    area_ha: float
    year_start: int
    year_end: int
    claim_scope: dict | None
    input_hash: str


def _inside_supplied_coverage(geom: Any) -> bool:
    """The official rasters cover only the four published AOIs."""
    return any(geometry.load(item.geometry).covers(geom) for item in catalog.areas())


def resolve(body: dict) -> ResolvedRequest:
    """Turn a validated wire request into what the analysis will actually be run against."""
    aoi_id = body.get("aoi_id")
    raw_geometry = body.get("geometry")
    if raw_geometry is None and aoi_id is None:
        raise invalid("VALIDATION_ERROR", "Either geometry or aoi_id is required")
    if raw_geometry is None:
        area = catalog.area(aoi_id)
        if area is None:
            raise not_found("Area")
        raw_geometry = area.geometry
    year_start, year_end = geometry.validate_years(body["year_start"], body["year_end"])
    geom, area_ha = geometry.validate(raw_geometry)
    canonical = geometry.canonical_geometry(geom)
    geometry_hash = geometry.geometry_hash(geom)

    claimed = body.get("claimed_units")
    if claimed is not None and (not isinstance(claimed, (int, float))
                                or isinstance(claimed, bool) or claimed < 0):
        raise invalid("INVALID_CLAIM", "claimed_units must be a non-negative number")
    origin = body.get("claim_origin")
    if claimed is not None and origin is None:
        origin = "USER_INPUT"
    if claimed is None and origin is not None:
        raise invalid("INVALID_CLAIM", "claim_origin requires claimed_units")

    snapshot = {
        "geometry": canonical,
        "aoi_id": aoi_id,
        "year_start": year_start,
        "year_end": year_end,
        "claimed_units": float(claimed) if claimed is not None else None,
        "claim_origin": origin,
        "include_optical": bool(body.get("include_optical", True)),
    }
    # The claim is not part of the scientific identity: it cannot change a measurement.
    input_hash = digest({
        "geometry_hash": geometry_hash, "year_start": year_start, "year_end": year_end,
        "include_optical": snapshot["include_optical"],
        "dataset_hash": catalog.dataset_hash(), "parameters_hash": catalog.parameters_hash(),
        "schema_version": SCHEMA_VERSION, "method_version": BACKEND_METHOD_VERSION,
    })
    return ResolvedRequest(snapshot=snapshot, geometry=geom, geometry_hash=geometry_hash,
                           area_ha=area_ha, year_start=year_start, year_end=year_end,
                           claim_scope=body.get("claim_scope"), input_hash=input_hash)


def measure_area(lens: LensContext, body: dict) -> dict:
    """Measure a contour without queueing anything.

    The same normalisation and the same geodesic area as the analysis path, so a figure
    shown before submitting cannot disagree with the figure the analysis reports. A
    contour that may not be used is a measurement with `valid: false` and named errors,
    not an exception: the caller is asking whether it may submit, and that deserves an
    answer rather than a stack trace.
    """
    errors: list[dict] = []
    area_ha: float | None = None
    geometry_hash: str | None = None
    canonical: dict | None = None
    try:
        # The limit is applied here rather than inside the validator: the caller is
        # asking how big the contour is, and "too big" is an answer that needs a number.
        geom, area_ha = geometry.validate(body["geometry"], max_area_ha=float("inf"))
        canonical = geometry.canonical_geometry(geom)
        geometry_hash = geometry.geometry_hash(geom)
        if not _inside_supplied_coverage(geom):
            errors.append(assemble.warning(
                "OUTSIDE_DATA_COVERAGE",
                "Контур находится вне четырёх AOI предоставленного набора данных.",
                "BLOCKING"))
    except ApiError as exc:
        errors.append(assemble.warning(exc.code, exc.message, "BLOCKING", **exc.details))

    within = area_ha is not None and area_ha <= geometry.MAX_AREA_HA
    if area_ha is not None and not within:
        errors.append(assemble.warning(
            "AREA_LIMIT_EXCEEDED",
            f"Площадь {area_ha:.2f} га превышает предел {geometry.MAX_AREA_HA:.0f} га "
            "для одного запроса.", "BLOCKING",
            area_ha=area_ha, max_area_ha=geometry.MAX_AREA_HA))
    measurement = {
        "valid": not errors,
        "area_ha": area_ha,
        "max_area_ha": geometry.MAX_AREA_HA,
        "within_limit": bool(within),
        "geometry_hash": geometry_hash,
        "geometry": canonical,
        "errors": errors,
    }
    return validate(api_validator("AreaMeasurement"), measurement, "AreaMeasurement")


def submit(lens: LensContext, *, who: Any, key: str, body: dict) -> dict:
    """Queue an analysis. The same key with the same request replays the stored 202."""
    resolved = resolve(body)
    analysis_id = new_id()
    actor = who.user_id
    scope = scope_key(geometry_hash=resolved.geometry_hash, year_start=resolved.year_start,
                      year_end=resolved.year_end, pool=POOL,
                      method_version=BACKEND_METHOD_VERSION)
    stored = {"geometry": resolved.snapshot["geometry"], "aoi_id": resolved.snapshot["aoi_id"],
              "year_start": resolved.year_start, "year_end": resolved.year_end,
              "claimed_units": resolved.snapshot["claimed_units"],
              "claim_origin": resolved.snapshot["claim_origin"],
              "claim_scope": resolved.claim_scope,
              "include_optical": resolved.snapshot["include_optical"]}

    def prepare():
        def write(conn):
            accepted = lens.store.queue(
                conn, analysis_id=analysis_id, actor=actor, request=stored,
                geometry_hash=resolved.geometry_hash, input_hash=resolved.input_hash,
                year_start=resolved.year_start, year_end=resolved.year_end, scope=scope)
            audit(conn, "LENS_ANALYSIS_QUEUED", analysis_id, actor=actor,
                  geometry_hash=resolved.geometry_hash, input_hash=resolved.input_hash)
            lens_auth.audit(lens.app, who.user_id, who.role, "ANALYSIS_CREATED",
                            accepted["analysis_id"], conn=conn,
                            geometry_hash=resolved.geometry_hash)
            return {"analysis_id": accepted["analysis_id"], "job_state": "QUEUED",
                    "status_url": f"/api/v2/analyses/{accepted['analysis_id']}",
                    "created_at": accepted["created_at"]}
        return write

    response = idempotent(lens.app, actor=actor, operation=OPERATION, key=key, path={},
                          body=_idempotency_body(resolved), prepare=prepare)
    return validate(api_validator("AnalysisAccepted"), response, "AnalysisAccepted")


def _idempotency_body(resolved: ResolvedRequest) -> dict:
    """What the caller asked for, claim included: a different claim is a different request."""
    return {"geometry_hash": resolved.geometry_hash, "year_start": resolved.year_start,
            "year_end": resolved.year_end,
            "claimed_units": resolved.snapshot["claimed_units"],
            "claim_origin": resolved.snapshot["claim_origin"],
            "claim_scope": resolved.claim_scope,
            "include_optical": resolved.snapshot["include_optical"]}


# -- running ---------------------------------------------------------------------------
def run_analysis(lens: LensContext, analysis_id: str) -> str:
    """Execute one claimed analysis. Returns the resulting job state."""
    row = lens.store.claim(analysis_id)
    if row is None:
        return "SKIPPED"
    from ..contracts import loads_json

    stored = loads_json(row["request_json"])
    snapshot = {"geometry": stored["geometry"], "aoi_id": stored["aoi_id"],
                "year_start": stored["year_start"], "year_end": stored["year_end"],
                "claimed_units": stored["claimed_units"],
                "claim_origin": stored["claim_origin"],
                "include_optical": stored["include_optical"]}
    created_at = utc_now()
    run_id = new_id()
    previous = lens.store.previous(row["scope_key"], before_id=analysis_id)

    try:
        result, artifacts = _compute(lens, analysis_id=analysis_id, run_id=run_id,
                                     created_at=created_at, row=row, stored=stored,
                                     snapshot=snapshot, previous=previous)
    except ApiError as exc:
        lens.store.fail(analysis_id, {"code": exc.code, "message": exc.message,
                                      "details": exc.details})
        verification.on_analysis_finished(lens.app, analysis_id, succeeded=False)
        return "FAILED"
    except (CarbonEngineUnavailable, RasterCoreUnavailable) as exc:
        # An engine that vanished mid-flight ends the job. It never ends in a number,
        # and it never quietly becomes a fixture.
        log.error("lens dependency unavailable: %s", exc)
        lens.store.fail(analysis_id, {
            "code": "DEPENDENCY_UNAVAILABLE",
            "message": "Расчётный движок недоступен, результат не формировался.",
            "details": {"dependency": type(exc).__name__}})
        verification.on_analysis_finished(lens.app, analysis_id, succeeded=False)
        return "FAILED"
    except Exception as exc:  # no stack traces, no local paths, no secrets
        log.exception("lens analysis failed")
        lens.store.fail(analysis_id, {"code": "ANALYSIS_ERROR",
                                      "message": "Анализ не удалось выполнить.",
                                      "details": {"reason": type(exc).__name__}})
        verification.on_analysis_finished(lens.app, analysis_id, succeeded=False)
        return "FAILED"

    validate(api_validator("AnalysisResult"), result, "AnalysisResult")
    report = lens.ports.report.build(result)
    if not lens.store.publish(analysis_id, result, report, artifacts):
        # Another worker published first. Its passport stands; this run is discarded.
        return "SKIPPED"
    verification.on_analysis_finished(lens.app, analysis_id, succeeded=True)
    return "SUCCEEDED"


def _compute(lens: LensContext, *, analysis_id: str, run_id: str, created_at: str, row: Any,
             stored: dict, snapshot: dict, previous: dict | None):
    geom, area_ha = geometry.validate(stored["geometry"])
    request = RasterRequest(
        geometry=geom, canonical_geometry=stored["geometry"],
        geometry_hash=row["geometry_hash"], area_ha=area_ha,
        year_start=row["year_start"], year_end=row["year_end"],
        include_optical=stored["include_optical"])

    try:
        raster = lens.ports.raster.analyse(request)
    except RasterUnavailable as exc:
        result = assemble.unavailable_result(
            analysis_id=analysis_id, run_id=run_id, created_at=created_at,
            request_snapshot=snapshot, geometry_hash=row["geometry_hash"],
            input_hash=row["input_hash"], area_ha=area_ha, reason=exc.reason,
            message=exc.message, raster_adapter=lens.ports.raster.name,
            carbon_adapter_name=lens.ports.carbon.name, previous=previous,
            claim_scope=stored.get("claim_scope"))
        return result, []

    carbon = lens.ports.carbon.assess(CarbonRequest(
        raster=raster.analysis, cells=raster.cells, geometry_hash=row["geometry_hash"],
        year_start=row["year_start"], year_end=row["year_end"],
        claimed_units=stored["claimed_units"], claim_origin=stored["claim_origin"],
        claim_scope=stored.get("claim_scope")))

    artifacts, public = _import_artifacts(lens, analysis_id, raster)
    result = assemble.build_result(
        analysis_id=analysis_id, run_id=run_id, created_at=created_at,
        request_snapshot=snapshot, geometry_hash=row["geometry_hash"],
        input_hash=row["input_hash"], raster=raster, carbon=carbon.assessment,
        artifacts=public, previous=previous, dataset_origin=raster.dataset_origin,
        raster_adapter=raster.adapter, carbon_adapter_name=carbon.adapter,
        claim_scope=stored.get("claim_scope"))
    return result, artifacts


def _import_artifacts(lens: LensContext, analysis_id: str, raster: Any):
    """Store the files the raster owner wrote, verified, and publish API urls for them."""
    rows, public = [], []
    records = list(raster.analysis.get("artifacts") or ())
    if not records and raster.artifact_files:
        # The id is derived from the bytes, never from the analysis id: the content hash
        # covers artifact ids, and an id that changed every run would make an identical
        # request produce a different passport hash.
        records = [{"id": f"{CELLS_ROLE}-{_digest_of(data)[2:14]}", "role": CELLS_ROLE,
                    "media_type": CELLS_MEDIA_TYPE, "path": name,
                    "sha256": None, "size_bytes": len(data)}
                   for name, data in raster.artifact_files.items()]
    for record in records:
        data = raster.artifact_files.get(record["path"])
        if data is None:
            continue
        expected = record.get("sha256")
        storage = lens.store.store_artifact(
            data, expected_sha256=("0x" + expected) if expected else None)
        artifact_id = _public_id(record, analysis_id)
        metadata = {key: record.get(key) for key in
                    ("crs", "resolution", "resolution_units", "bbox_native", "bbox_wgs84",
                     "unit", "provenance")}
        rows.append(artifact_record(
            artifact_id=artifact_id, role=record["role"], media_type=record["media_type"],
            sha256="0x" + expected if expected else _digest_of(data),
            size_bytes=len(data), storage_name=storage, metadata=metadata))
        public.append({
            "artifact_id": artifact_id, "role": record["role"],
            "media_type": record["media_type"],
            "sha256": "0x" + expected if expected else _digest_of(data),
            "size_bytes": len(data),
            "url": f"/api/v2/analyses/{analysis_id}/artifacts/{artifact_id}",
            "bbox_wgs84": record.get("bbox_wgs84"), "crs": record.get("crs"),
            "resolution": record.get("resolution"),
            "resolution_units": record.get("resolution_units"),
            "unit": record.get("unit"),
            "provenance": str(record.get("provenance") or raster.dataset_origin),
        })
    return rows, public


def _digest_of(data: bytes) -> str:
    from ..contracts import sha256_hex

    return sha256_hex(data)


def _public_id(record: dict, analysis_id: str) -> str:
    """Namespaced, opaque and safe in a URL path segment."""
    raw = str(record.get("id") or record.get("role") or "artifact")
    cleaned = "".join(char if char.isalnum() or char in "._-" else "_" for char in raw)
    return cleaned[:96] or "artifact"


# -- reads -----------------------------------------------------------------------------
def _readable(lens: LensContext, analysis_id: str, who: Any):
    """The analysis row, once the signed-in person is allowed to see it.

    A person who may not read an analysis is told 404 rather than 403, so that probing
    identifiers cannot be used to learn which ones exist.
    """
    row = lens.store.require(analysis_id)
    if who is None:
        return row
    if not lens_auth.may_read_analysis(who, owner_id=row["actor"],
                                       finalized=_is_finalized(lens, row)):
        raise not_found("Analysis")
    return row


def _is_finalized(lens: LensContext, row: Any) -> bool:
    """Whether a verifier pinned this analysis.

    The stored result always says DRAFT, because that is what it was when it was
    computed. Finalization is a separate record, so this asks that record rather than
    the bytes the worker wrote.
    """
    if not row["result_json"]:
        return False
    return verification.finalization_of(lens.app, row["analysis_id"]) is not None


def analysis_view(lens: LensContext, analysis_id: str, *, who: Any = None) -> dict:
    from ..contracts import loads_json

    row = _readable(lens, analysis_id, who)
    ready = row["job_state"] == "SUCCEEDED"
    view = {
        "analysis_id": row["analysis_id"],
        "job_state": row["job_state"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "attempts": row["attempts"],
        "status_url": f"/api/v2/analyses/{analysis_id}",
        "report_url": f"/api/v2/analyses/{analysis_id}/report" if ready else None,
        "proof_url": f"/api/v2/analyses/{analysis_id}/proof" if ready else None,
        "error": loads_json(row["error_json"]) if row["error_json"] else None,
        # The stored result always says DRAFT, because that is what it was when it was
        # computed. A finalization is a separate record, overlaid here at read time.
        "result": verification.apply_passport_status(
            lens.app, analysis_id, loads_json(row["result_json"]))
        if row["result_json"] else None,
    }
    return validate(api_validator("Analysis"), view, "Analysis")


def _report(lens: LensContext, analysis_id: str, who: Any):
    row = _readable(lens, analysis_id, who)
    stored = lens.store.report(analysis_id)
    if stored is None:
        raise not_found("Report")
    if who is not None:
        lens_auth.require(who, "report.read.final" if _is_finalized(lens, row)
                          else "report.read.draft")
        lens_auth.audit(lens.app, who.user_id, who.role, "REPORT_DOWNLOADED", analysis_id)
    return stored


def report_view(lens: LensContext, analysis_id: str, *, who: Any = None) -> dict:
    """The stored report, with the passport status it has now.

    The document is stored exactly as it was generated. Only the passport status is
    overlaid, and that status is outside the report hash by construction, so the
    document still identifies the same content it was published with.
    """
    document = dict(_report(lens, analysis_id, who)[0])
    document["result"] = verification.apply_passport_status(
        lens.app, analysis_id, document["result"])
    return validate(api_validator("Report"), document, "Report")


def report_html(lens: LensContext, analysis_id: str, *, who: Any = None) -> bytes:
    return _report(lens, analysis_id, who)[1]


def proof_view(lens: LensContext, analysis_id: str, *, who: Any = None) -> dict:
    _readable(lens, analysis_id, who)
    result = lens.store.result(analysis_id)
    if result is None:
        raise not_found("Result")
    result = verification.apply_passport_status(lens.app, analysis_id, result)
    proof = {
        "analysis_id": analysis_id,
        "identity": result["identity"],
        "passport": result["passport"],
        "canonical_url": f"/api/v2/analyses/{analysis_id}/report?format=json",
        "report_urls": {"json": f"/api/v2/analyses/{analysis_id}/report?format=json",
                        "html": f"/api/v2/analyses/{analysis_id}/report?format=html"},
        "artifacts": result["artifacts"],
        "anchor": {
            "status": "NOT_REQUESTED", "deployment_id": None, "tx_hash": None,
            "anchored_at": None,
            "note": ("Хеш выявляет изменение файла относительно доверенной фиксации. "
                     "Он не предотвращает двойную продажу и не удостоверяет истинность "
                     "расчёта. Запись в блокчейн для этого расчёта не запрашивалась."),
        },
        "verification_note": (
            "Повторите запрос с тем же контуром и периодом на тех же данных: хеш "
            "содержания не включает время запуска и должен совпасть."),
    }
    return validate(api_validator("Proof"), proof, "Proof")


def catalog_view(lens: LensContext) -> dict:
    document = catalog.document(raster_adapter=lens.ports.raster.name,
                                carbon_adapter=lens.ports.carbon.name,
                                schema_version=SCHEMA_VERSION,
                                method_version=BACKEND_METHOD_VERSION,
                                engine_mode=lens.app.settings.lens_engine_mode)
    return validate(api_validator("Catalog"), document, "Catalog")


def artifact_bytes(lens: LensContext, analysis_id: str, artifact_id: str, *,
                   who: Any = None) -> tuple[bytes, str]:
    _readable(lens, analysis_id, who)
    data = lens.store.artifact(analysis_id, artifact_id)
    if who is not None:
        lens_auth.audit(lens.app, who.user_id, who.role, "ARTIFACT_DOWNLOADED",
                        analysis_id, artifact_id=artifact_id)
    return data


# -- verification requests ---------------------------------------------------------------
def create_request(lens: LensContext, *, who: Any, body: dict) -> dict:
    document = verification.create(lens.app, who=who, body=body)
    return validate(api_validator("VerificationRequest"), document, "VerificationRequest")


def list_requests(lens: LensContext, *, who: Any) -> dict:
    document = verification.listing(lens.app, who=who)
    return validate(api_validator("VerificationRequestList"), document,
                    "VerificationRequestList")


def request_view(lens: LensContext, request_id: str, *, who: Any) -> dict:
    document = verification.view(lens.app, request_id, who=who)
    return validate(api_validator("VerificationRequest"), document, "VerificationRequest")


def update_request(lens: LensContext, request_id: str, *, who: Any, body: dict) -> dict:
    document = verification.update_claim(lens.app, request_id, who=who, body=body)
    return validate(api_validator("VerificationRequest"), document, "VerificationRequest")


def submit_request(lens: LensContext, request_id: str, *, who: Any) -> dict:
    document = verification.submit(lens.app, request_id, who=who)
    return validate(api_validator("VerificationRequest"), document, "VerificationRequest")


def start_request_analysis(lens: LensContext, request_id: str, *, who: Any,
                           key: str) -> dict:
    """Queue the calculation a request describes.

    The request module owns the workflow and knows nothing about how an analysis is
    submitted; this closure is the only place the two meet.
    """
    def queue(body: dict) -> str:
        return submit(lens, who=who, key=key, body=body)["analysis_id"]

    document, _analysis_id = verification.start_analysis(
        lens.app, request_id, who=who, queue=queue)
    return validate(api_validator("VerificationRequest"), document, "VerificationRequest")


def finalize_request(lens: LensContext, request_id: str, *, who: Any) -> dict:
    """A verifier pins a passport version. Nothing about the calculation moves."""
    def passport_of(analysis_id: str) -> dict | None:
        result = lens.store.result(analysis_id)
        return result["passport"] if result else None

    document = verification.finalize(lens.app, request_id, who=who,
                                     passport_of=passport_of)
    return validate(api_validator("VerificationRequest"), document, "VerificationRequest")


# -- scenario value -----------------------------------------------------------------------
VALUE_NOTE = (
    "Сценарная стоимость — это Q, умноженное на цену, и ничего больше. Это не рыночная "
    "котировка, не прогноз выручки и не гарантированная сумма. Цена, заданная "
    "пользователем, помечена как USER_SCENARIO и остаётся его допущением."
)


def value_view(lens: LensContext, analysis_id: str, *, who: Any,
               price_rub: float | None = None) -> dict:
    """q multiplied by each price. Nothing is stored and no hash moves.

    A price the caller supplies is an input, not a quotation this system stands behind,
    so it is labelled `USER_SCENARIO` and deliberately kept out of the analysis: a stated
    price must never be able to change a passport.
    """
    _readable(lens, analysis_id, who)
    result = lens.store.result(analysis_id)
    if result is None:
        raise not_found("Result")
    q = result["units"]["q"]
    scenarios = [{"id": name, "origin": "CASE_PARAMETER", "price_rub": price,
                  "value_rub": None if q is None else q * price}
                 for name, price in catalog.prices()]
    if price_rub is not None:
        if not isinstance(price_rub, (int, float)) or isinstance(price_rub, bool) \
                or price_rub < 0 or price_rub != price_rub:
            raise invalid("INVALID_PRICE", "price_rub must be a non-negative number")
        scenarios.append({"id": "user", "origin": "USER_SCENARIO",
                          "price_rub": float(price_rub),
                          "value_rub": None if q is None else q * float(price_rub)})
    document = {
        "analysis_id": analysis_id,
        "q": q,
        "unit": "RUB",
        "price_parameters_ref": assemble.PRICE_REF,
        "scenarios": scenarios,
        "note": VALUE_NOTE,
    }
    return validate(api_validator("ValueScenarios"), document, "ValueScenarios")


# -- the demonstration lifecycle -----------------------------------------------------------
def demo_view(lens: LensContext, request_id: str, *, who: Any) -> dict:
    document = demo.view(lens.app, request_id, who=who)
    return validate(api_validator("DemoUnit"), document, "DemoUnit")


def demo_issue(lens: LensContext, request_id: str, *, who: Any) -> dict:
    """Issue demonstration units, if the calculation produced any.

    The quantity comes from the published passport rather than from the caller, so a
    demonstration cannot show a number the calculation never produced.
    """
    def units_of(analysis_id: str | None) -> int | None:
        if not analysis_id:
            return None
        result = lens.store.result(analysis_id)
        return result["units"]["q"] if result else None

    document = demo.issue(lens.app, request_id, who=who, units_of=units_of)
    return validate(api_validator("DemoUnit"), document, "DemoUnit")


def demo_transfer(lens: LensContext, request_id: str, *, who: Any) -> dict:
    document = demo.accept_transfer(lens.app, request_id, who=who)
    return validate(api_validator("DemoUnit"), document, "DemoUnit")


def demo_retire(lens: LensContext, request_id: str, *, who: Any) -> dict:
    document = demo.retire(lens.app, request_id, who=who)
    return validate(api_validator("DemoUnit"), document, "DemoUnit")
