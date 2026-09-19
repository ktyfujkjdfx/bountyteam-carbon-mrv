"""Carbon Lens raster core (RS-1).

Turns a WGS84 contour and a pair of years into carbon stock, its change, the
coverage that result rests on, and the per-cell layer the carbon engine needs.

What this package deliberately does not do: baselines, uncertainty intervals,
potential units, and any investment statement. Those have other owners, and
mixing them in here would make it impossible to say which number came from a
raster and which from an assumption.
"""
from rs.case2.analysis import METHOD_VERSION, analyse
from rs.case2.catalog import Dataset, DatasetError
from rs.case2.geometry import GeometryError

__all__ = ["METHOD_VERSION", "analyse", "Dataset", "DatasetError", "GeometryError"]
