"""Byte-level determinism for everything a bundle writes.

A bundle is hashed, so "the same inputs produce the same bytes" has to hold
across operating systems, not just across runs on one machine. Three things
broke that and are fixed here:

* **Text mode newline translation.** `Path.write_text` opens in text mode, so
  every "\\n" became "\\r\\n" on Windows and stayed "\\n" elsewhere - the same
  JSON, two different SHA-256 values. Everything is written as bytes now.
* **Serialization variance.** Key order and number formatting are pinned by
  writing JCS (RFC 8785) through the shared `tools/contract_helpers.py`, the
  same canonicalization Backend hashes with.
* **Float noise in reprojected coordinates.** PROJ can differ in the last
  ULP between builds, so coordinates are rounded to a fixed precision before
  serialization.

PNG encoding is pinned here too; see `png_bytes`.
"""
import io

from rs.contracts import canonical

# ~1.1 cm at the equator: far finer than the 20 m analysis grid, coarse enough
# to absorb last-ULP differences between PROJ builds on different platforms.
COORDINATE_DECIMALS = 7


def round_coordinates(value, decimals=COORDINATE_DECIMALS):
    """Recursively round every number in a GeoJSON coordinate structure."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return round(value, decimals)
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple)):
        return [round_coordinates(item, decimals) for item in value]
    if isinstance(value, dict):
        return {key: round_coordinates(item, decimals) for key, item in value.items()}
    return value


def round_geojson(geojson, decimals=COORDINATE_DECIMALS):
    """Round only the geometry coordinates, leaving properties untouched."""
    out = dict(geojson)
    if "features" in out:
        out["features"] = [round_geojson(feature, decimals) for feature in out["features"]]
    if isinstance(out.get("geometry"), dict):
        geometry = dict(out["geometry"])
        geometry["coordinates"] = round_coordinates(geometry.get("coordinates"), decimals)
        out["geometry"] = geometry
    if "coordinates" in out and "geometry" not in out:
        out["coordinates"] = round_coordinates(out["coordinates"], decimals)
    return out


def canonical_bytes(value):
    """JCS (RFC 8785) bytes, via the shared helper Backend also hashes with."""
    return canonical(value)


def write_json(path, value):
    """Write canonical JSON bytes: no text mode, no platform newline."""
    data = canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def png_bytes(image):
    """Encode a PIL image to PNG with every variable input pinned.

    `compress_level=0` stores the zlib stream uncompressed. That costs file
    size but removes the one remaining platform variable: the deflate stream
    is otherwise produced by whatever zlib the local Pillow wheel was built
    against, and different builds make different (equally valid) bytes for the
    same pixels. Previews here are a few hundred pixels square, so the trade
    is cheap and it makes the hashes portable. `optimize=False` keeps Pillow
    from re-deriving the palette/filters, and no `pnginfo` is passed, so no
    tIME or tEXt chunk is written.
    """
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=0)
    return buffer.getvalue()


def write_png(image, path):
    """Write a deterministic PNG and return its (width, height)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png_bytes(image))
    return image.size
