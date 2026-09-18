"""Which implementation answers each port, and how a result says so.

The rule is the same for both ports: the owning package wins whenever it is importable,
and a stand-in is used only in its absence. Nothing here chooses a stand-in to make a test
pass, and every result carries the adapter name and the dataset origin, so "which code
produced this number" is answered by the response rather than by the deployment notes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import carbon as carbon_module
from . import raster as raster_module
from ..report import ReportBuilder


@dataclass(frozen=True)
class Ports:
    raster: Any
    carbon: Any
    report: Any

    @property
    def names(self) -> dict[str, str]:
        return {"raster_adapter": self.raster.name, "carbon_adapter": self.carbon.name,
                "report_adapter": self.report.name}


def raster_port(work_dir: Path, *, prefer_real: bool = True) -> Any:
    return raster_module.build(work_dir, prefer_real=prefer_real)


def carbon_port() -> Any:
    return carbon_module.CarbonAdapter()


def report_port() -> Any:
    return ReportBuilder()


def build_ports(work_dir: Path, *, prefer_real: bool = True) -> Ports:
    return Ports(raster=raster_port(work_dir, prefer_real=prefer_real),
                 carbon=carbon_port(), report=report_port())


def describe() -> dict[str, Any]:
    """What a deployment is actually running, for the catalog and the runbook."""
    return {
        "raster_core_available": raster_module.RS_AVAILABLE,
        "carbon_engine_available": not carbon_module.IS_REFERENCE_FALLBACK,
        "raster_adapter": raster_module.RS_NAME or raster_module.ReplayRasterAdapter.name,
        "carbon_adapter": carbon_module.ENGINE_NAME,
    }
