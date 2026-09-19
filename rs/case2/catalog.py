"""Access to the supplied dataset in `data/`.

Every read goes through here so that the analysis never reaches for a file the
official catalogue does not describe, and so every file it did read can be
listed with its checksum afterwards.
"""
import csv
import hashlib
import json
from pathlib import Path

from shapely.geometry import shape

from rs.case2 import errors

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = REPO_ROOT / "data"
# CSV tables in the set are UTF-8 with a BOM; reading them as plain UTF-8 puts
# a BOM into the first column name and breaks lookups on every platform alike.
CSV_ENCODING = "utf-8-sig"


class DatasetError(errors.StructuredError, RuntimeError):
    """The supplied dataset cannot answer the request as asked."""

    default_code = errors.DATASET_FILE_MISSING


class InsufficientData(DatasetError):
    """The request is well formed; the supplied products do not reach it.

    Separated from the rest so a consumer can tell "ask for a different
    contour" from "this file is not where the catalogue says it is". Both are
    refusals; only one is about the request.
    """

    default_code = errors.NO_SOURCE_COVERAGE
    outcome = errors.INSUFFICIENT_DATA


class Dataset:
    """The official data root, read lazily and cached per instance."""

    def __init__(self, root=None):
        self.root = Path(root) if root is not None else DEFAULT_DATA_ROOT
        if not self.root.is_dir():
            raise DatasetError(f"data root not found: {self.root}")
        self._areas = None
        self._geometries = None
        self._scenes = None
        self._scene_metadata = None
        self._catalog = None

    # -- tables ---------------------------------------------------------

    def _read_csv(self, relative):
        with open(self.root / relative, encoding=CSV_ENCODING, newline="") as handle:
            return list(csv.DictReader(handle))

    @property
    def areas(self):
        if self._areas is None:
            self._areas = {row["aoi_id"]: row for row in self._read_csv("areas.csv")}
        return self._areas

    @property
    def geometries(self):
        if self._geometries is None:
            with open(self.root / "areas.geojson", encoding="utf-8") as handle:
                collection = json.load(handle)
            self._geometries = {
                feature["properties"]["aoi_id"]: shape(feature["geometry"])
                for feature in collection["features"]
            }
        return self._geometries

    @property
    def scenes(self):
        if self._scenes is None:
            self._scenes = self._read_csv("scenes.csv")
        return self._scenes

    @property
    def scene_metadata(self):
        if self._scene_metadata is None:
            with open(self.root / "scene_metadata.json", encoding="utf-8") as handle:
                document = json.load(handle)
            self._scene_metadata = {
                scene["scene_key"]: scene for scene in document["scenes"]
            }
        return self._scene_metadata

    @property
    def catalog(self):
        if self._catalog is None:
            self._catalog = {
                row["relative_path"].replace("\\", "/"): row
                for row in self._read_csv("file_catalog.csv")
            }
        return self._catalog

    # -- files ----------------------------------------------------------

    def path(self, relative):
        """Resolve a dataset-relative path, refusing anything outside the root."""
        relative = str(relative).replace("\\", "/")
        resolved = (self.root / relative).resolve()
        if not resolved.is_relative_to(self.root.resolve()):
            raise DatasetError(f"path escapes the data root: {relative}",
                               code=errors.DATASET_FILE_MISSING, path=relative)
        if not resolved.is_file():
            raise DatasetError(f"file listed but not present: {relative}",
                               code=errors.DATASET_FILE_MISSING, path=relative)
        return resolved

    def biomass_path(self, aoi_id, year):
        return self.path(f"{aoi_id}/CCI_Biomass_{year}.tif")

    def relative(self, path):
        """Path relative to the repository root, so manifests hold no machine paths."""
        return Path(path).resolve().relative_to(REPO_ROOT).as_posix()

    # -- request resolution ---------------------------------------------

    def parents_for(self, geometry):
        """AOIs whose polygon the request touches, left to right, west to east.

        The supplied AOIs are pairwise disjoint, which is what makes summing
        parts of a multi-parent request safe. If a future set overlaps, the
        overlap is reported as an error instead of being counted twice.
        """
        hits = [aoi for aoi, poly in sorted(self.geometries.items())
                if poly.intersects(geometry) and not poly.touches(geometry)]
        if not hits:
            raise InsufficientData(
                f"the request does not intersect any supplied area; the dataset "
                f"covers {', '.join(sorted(self.geometries))}",
                code=errors.NO_SOURCE_COVERAGE,
                available_areas=sorted(self.geometries),
                request_bounds=[round(value, 7) for value in geometry.bounds])
        for left in range(len(hits)):
            for right in range(left + 1, len(hits)):
                a, b = self.geometries[hits[left]], self.geometries[hits[right]]
                overlap = a.intersection(b)
                if not overlap.is_empty and overlap.area > 0:
                    raise DatasetError(
                        f"source areas {hits[left]} and {hits[right]} overlap; a "
                        f"partition policy is required before their stock can be summed",
                        code=errors.SOURCE_AREAS_OVERLAP,
                        areas=[hits[left], hits[right]])
        return hits

    def scenes_for(self, aoi_id, years=None):
        """Sentinel-2 scenes of one AOI, optionally restricted to given years."""
        rows = [row for row in self.scenes if row["aoi_id"] == aoi_id]
        if years is not None:
            wanted = {int(year) for year in years}
            rows = [row for row in rows if int(row["year"]) in wanted]
        return sorted(rows, key=lambda row: (row["datetime_utc"], row["scene_key"]))

    def reflectance_offset(self, scene_key):
        """Offset the dataset already applied to this scene's reflectance.

        Returned for the record, not to be undone: the supplied rasters are
        finished surface reflectance. Baselines from 04.00 carry -0.1, which is
        why dark targets are legitimately negative.
        """
        radiometry = self.scene_metadata[scene_key]["radiometry"]
        offsets = {float(band["source_offset"]) for band in radiometry}
        if len(offsets) != 1:
            raise DatasetError(
                f"scene {scene_key} mixes radiometric offsets {sorted(offsets)}",
                code=errors.SOURCE_OFFSETS_MIXED, scene_key=scene_key,
                offsets=sorted(offsets))
        return offsets.pop()


def sha256_file(path, chunk=1 << 20):
    """SHA-256 of a file, read in binary so the digest is platform independent."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()
