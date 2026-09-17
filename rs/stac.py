"""Minimal STAC client. Kept separate from core processing so indices/masks/
grid code never import a specific provider (manifest 4: "не связывай core
processing напрямую с конкретным STAC provider").
"""
import json
import urllib.request

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1/search"

# STAC common-name -> our frozen band code. Works for both Element84 Earth
# Search collections used here (sentinel-2-l2a, sentinel-2-c1-l2a).
ASSET_KEY_BY_BAND = {
    "B04": "red",
    "B08": "nir",
    "B8A": "nir08",
    "B12": "swir22",
    "SCL": "scl",
}


def search(collection, bbox, datetime_range, limit=30, cloud_lt=None):
    body = {
        "collections": [collection],
        "bbox": list(bbox),
        "datetime": datetime_range,
        "limit": limit,
    }
    if cloud_lt is not None:
        body["query"] = {"eo:cloud_cover": {"lt": cloud_lt}}
    request = urllib.request.Request(
        EARTH_SEARCH,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return payload.get("features", [])


def get_item(collection, scene_id, bbox_hint, datetime_range):
    """Fetch one known item by id via a scoped search (no per-id STAC endpoint
    is assumed available on every mirror)."""
    for feature in search(collection, bbox_hint, datetime_range, limit=50):
        if feature["id"] == scene_id:
            return feature
    raise LookupError(f"STAC item not found: {scene_id}")


def asset_href(item, band):
    key = ASSET_KEY_BY_BAND[band]
    return item["assets"][key]["href"]
