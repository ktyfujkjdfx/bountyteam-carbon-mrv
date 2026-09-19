"""Shared fixtures for the raster core tests.

Analyses are session scoped because each one reads real rasters; the tests then
interrogate the same result from many angles instead of recomputing it.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rs.case2.analysis import analyse  # noqa: E402
from rs.case2.catalog import Dataset  # noqa: E402

SUPPLIED_AOIS = (
    "RU_TVER_01",
    "RU_VOLOGDA_02",
    "RU_MORDOVIA_03",
    "RU_MORDOVIA_04",
)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "synthetic_test_only: exercises a logical case that the supplied rasters "
        "do not contain; its arrays are constructed and must never be presented "
        "as an observation of a real area",
    )


@pytest.fixture(scope="session")
def dataset():
    return Dataset()


@pytest.fixture(scope="session")
def sample_request(dataset):
    with open(dataset.root / "sample_requests.geojson", encoding="utf-8") as handle:
        return json.load(handle)["features"][0]


@pytest.fixture(scope="session")
def tver(dataset):
    return analyse(dataset.geometries["RU_TVER_01"], 2019, 2024, dataset=dataset)


@pytest.fixture(scope="session")
def mordovia_03(dataset):
    return analyse(dataset.geometries["RU_MORDOVIA_03"], 2020, 2022, dataset=dataset)


@pytest.fixture(scope="session")
def mordovia_cloudy(dataset):
    """2021 to 2022: the window that contains the heavily clouded September scene."""
    return analyse(dataset.geometries["RU_MORDOVIA_03"], 2021, 2022, dataset=dataset)


@pytest.fixture(scope="session")
def analyses(dataset):
    """One analysis per supplied AOI over its full 2019-2024 period."""
    return {
        aoi: analyse(dataset.geometries[aoi], 2019, 2024,
                     dataset=dataset, include_optical=False)
        for aoi in SUPPLIED_AOIS
    }
