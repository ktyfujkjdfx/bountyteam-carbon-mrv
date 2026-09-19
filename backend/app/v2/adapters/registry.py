"""Which implementation answers each port, and what happens when none can.

There are exactly two engine modes and a deployment is in one of them by configuration,
never by accident:

- `REAL` is the default. The owning packages answer, or nothing does. A missing
  dependency is a failure, not an invitation to substitute.
- `FIXTURE` has to be asked for by name. It replays labelled vectors, stamps every result
  `STUB_FIXTURE`, and is refused outright on a deployment that has declared it serves a
  demo of real data.

The rule this file exists to enforce is that no code path leads from "the engine is
missing" to "here is a number". A reader of a passport cannot tell a plausible stub from
a measurement, so the system must never be in a position to offer one.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import carbon as carbon_module
from . import raster as raster_module
from ..report import ReportBuilder

REAL = "REAL"
FIXTURE = "FIXTURE"
ENGINE_MODES = (REAL, FIXTURE)


class EnginesUnavailable(RuntimeError):
    """The real engines were required and at least one of them is not installed."""

    def __init__(self, missing: tuple[str, ...]):
        super().__init__("the real Carbon Lens engines are not available: "
                         + ", ".join(missing))
        self.missing = missing


@dataclass(frozen=True)
class Ports:
    raster: Any
    carbon: Any
    report: Any

    @property
    def names(self) -> dict[str, str]:
        return {"raster_adapter": self.raster.name, "carbon_adapter": self.carbon.name,
                "report_adapter": self.report.name}


def missing_engines() -> tuple[str, ...]:
    """Which owning packages are not importable here."""
    absent = []
    if not raster_module.RS_AVAILABLE:
        absent.append("rs.case2")
    if not carbon_module.CARBON_AVAILABLE:
        absent.append("carbon")
    return tuple(absent)


def report_port() -> Any:
    """The report builder. Trust's is preferred when it is on the branch.

    A report is presentation rather than science, so a builder of our own is a legitimate
    default rather than a second source of numbers. It formats the values of the result
    and computes none of them.
    """
    if carbon_module.CARBON_AVAILABLE:  # pragma: no cover - needs carbon/ on the branch
        engine = carbon_module.engine()
        builder = getattr(getattr(engine, "report", None), "ReportBuilder", None)
        if builder is not None:
            return builder()
    return ReportBuilder()


def build_ports(work_dir: Path, *, engine_mode: str = REAL,
                carbon_module_override: Any = None) -> Ports:
    """The ports for one deployment, or an error naming what is missing."""
    if engine_mode not in ENGINE_MODES:
        raise ValueError(f"engine_mode must be one of {ENGINE_MODES}")
    fixture_mode = engine_mode == FIXTURE
    absent = missing_engines()
    if fixture_mode:
        # Fixture mode replays a raster payload; it does not replay the carbon engine,
        # because a recorded Q would be a second source of the numbers the engine owns.
        if carbon_module_override is None and not carbon_module.CARBON_AVAILABLE:
            raise EnginesUnavailable(("carbon",))
    elif absent:
        raise EnginesUnavailable(absent)
    return Ports(
        raster=raster_module.build(work_dir, fixture_mode=fixture_mode),
        carbon=carbon_module.CarbonAdapter(module=carbon_module_override),
        report=report_port())


def describe(engine_mode: str = REAL) -> dict[str, Any]:
    """What a deployment is actually running, for the catalog and the runbook."""
    return {
        "engine_mode": engine_mode,
        "raster_core_available": raster_module.RS_AVAILABLE,
        "carbon_engine_available": carbon_module.CARBON_AVAILABLE,
        "missing_engines": list(missing_engines()),
    }
