"""The raster port: areas, annual stocks, the stock change, per-cell uncertainty and zones.

The owner of these numbers is `rs/case2/`, and in the default engine mode it is the only
implementation this module will use. If it is absent the port reports itself unavailable
and analyses fail closed. Nothing here chooses a stand-in to keep a deployment answering.

A fixture mode exists and must be asked for by name. It replays a small set of labelled
vectors so the API, the jobs, the passports and the screens can be exercised without the
raster core, and everything it produces is stamped `STUB_FIXTURE` with a fixture label
that the UI is required to show. Even then it never invents a result for a request it was
not given: only the exact contour-and-period keys in `fixtures/v2/replay/index.json` are
answered, and every other request gets `RASTER_ANALYSIS_UNAVAILABLE`.
"""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from ..contracts import FIXTURES_V2, internal_validator, read_json, validate
from ..ports import RasterRequest, RasterResult, RasterUnavailable

log = logging.getLogger("backend.lens.raster")

REPLAY_ROOT = FIXTURES_V2 / "replay"
REPLAY_INDEX = REPLAY_ROOT / "index.json"
CELLS_ARTIFACT_ROLE = "cells"
UNAVAILABLE = "RASTER_ANALYSIS_UNAVAILABLE"

try:  # pragma: no cover - depends on what is merged into the branch
    from rs.case2 import analysis as _rs_analysis

    RS_AVAILABLE = True
    RS_NAME = f"rs.case2/{_rs_analysis.METHOD_VERSION}"
except ImportError:  # pragma: no cover
    _rs_analysis = None
    RS_AVAILABLE = False
    RS_NAME = ""


class RasterCoreAdapter:
    """Delegates to `rs.case2`; writes its artifacts into a directory Backend then imports."""

    name = RS_NAME or "rs.case2"

    def __init__(self, work_dir: Path):
        self.work_dir = Path(work_dir)

    def analyse(self, request: RasterRequest) -> RasterResult:  # pragma: no cover
        from rs.case2 import artifacts as rs_artifacts
        from rs.case2 import manifest as rs_manifest
        from rs.case2 import payload as rs_payload
        from rs.case2.catalog import Dataset, DatasetError
        from rs.case2.geometry import GeometryError

        out = Path(tempfile.mkdtemp(prefix="lens-rs-", dir=_ensure(self.work_dir)))
        try:
            try:
                analysis = _rs_analysis.analyse(
                    request.canonical_geometry, request.year_start, request.year_end,
                    dataset=Dataset(), include_optical=request.include_optical)
            except (DatasetError, GeometryError) as exc:
                raise RasterUnavailable(UNAVAILABLE, str(exc)) from None

            payload = rs_payload.analysis_payload(analysis)
            cells = rs_payload.cells_payload(analysis)
            prefix = (f"{'+'.join(payload['request']['parents'])}:"
                      f"{payload['request']['year_start']}-{payload['request']['year_end']}")
            records = rs_artifacts.write_cell_artifacts(
                out, prefix, cells, analysis.grids[f"cci_biomass:{analysis.parents[0]}"])
            if analysis.raw_change is not None:
                records.extend(rs_artifacts.write_change_artifacts(
                    out, prefix, analysis.raw_change, analysis.raw_change["grid"], out))
            payload["artifacts"] = records
            manifest = rs_manifest.build(analysis, payload)
            files = {record["path"]: (out / record["path"]).read_bytes()
                     for record in records if (out / record["path"]).is_file()}
            return _result(payload, cells, manifest, self.name,
                           "COMPUTED_FROM_SUPPLIED_DATA", None, files)
        finally:
            shutil.rmtree(out, ignore_errors=True)


class ReplayRasterAdapter:
    """Answers only the labelled keys it was given, and says so in every result."""

    name = "backend-replay"

    def __init__(self, root: Path = REPLAY_ROOT):
        self.root = Path(root)

    def entries(self) -> list[dict]:
        if not (self.root / "index.json").is_file():
            return []
        return read_json(self.root / "index.json")["entries"]

    def _match(self, request: RasterRequest) -> dict | None:
        for entry in self.entries():
            if (entry["geometry_hash"] == request.geometry_hash
                    and entry["year_start"] == request.year_start
                    and entry["year_end"] == request.year_end):
                return entry
        return None

    def analyse(self, request: RasterRequest) -> RasterResult:
        entry = self._match(request)
        if entry is None:
            raise RasterUnavailable(
                UNAVAILABLE,
                "The raster core is not available on this deployment and no labelled vector "
                "matches this contour and period",
                {"adapter": self.name, "year_start": request.year_start,
                 "year_end": request.year_end})
        payload = read_json(self.root / entry["analysis"])
        cells = read_json(self.root / entry["cells"])
        manifest = read_json(self.root / entry["manifest"])
        files = {CELLS_ARTIFACT_ROLE + ".geojson":
                 json.dumps(cells, ensure_ascii=False, sort_keys=True).encode("utf-8")}
        return _result(payload, cells, manifest, self.name, "STUB_FIXTURE",
                       entry.get("fixture"), files)


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _result(payload: dict, cells: dict, manifest: dict, adapter: str, origin: str,
            fixture: dict | None, files: dict[str, bytes]) -> RasterResult:
    validate(internal_validator("RasterAnalysis"), payload, "RasterAnalysis")
    validate(internal_validator("CellLayer"), cells, "CellLayer")
    validate(internal_validator("ArtifactManifest"), manifest, "ArtifactManifest")
    return RasterResult(analysis=payload, cells=cells, manifest=manifest, adapter=adapter,
                        dataset_origin=origin, fixture=fixture, artifact_files=files)


class RasterCoreUnavailable(RuntimeError):
    """The raster core is not installed on this deployment. No number is invented."""


def build(work_dir: Path, *, fixture_mode: bool = False) -> Any:
    """The raster port for this deployment.

    In the default mode there is exactly one answer: the raster core, or an error. The
    fixture mode has to be selected explicitly in the settings; it is never reached by
    falling back from a missing dependency.
    """
    if fixture_mode:
        return ReplayRasterAdapter()
    if not RS_AVAILABLE:
        raise RasterCoreUnavailable(
            "rs.case2 is not available on this deployment")
    return RasterCoreAdapter(work_dir)  # pragma: no cover - needs rs.case2 on the branch
