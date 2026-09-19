"""One adapter per source, and the manifest that records what was used.

Four products go into a result and they are not interchangeable. Each has its
own provider, its own version, its own licence and its own way of being
reached, so each gets its own adapter rather than a single "fetch" that hides
the differences. Only one of them - Sentinel-2 L2A - is retrievable from an
open catalogue by this package; the other three arrive with the case. That is
recorded as a property of the adapter, not left to be discovered when a fetch
fails.

The manifest is what makes a run checkable by somebody who was not there. For
every input it records the identifier or URL, the product and its version, when
it was accessed, the licence, the checksum, the cache key and whether it was
served over the network, replayed from cache, or read from the supplied
dataset. Nothing in it is a path from the machine that produced it, and nothing
in it is a credential.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

MANIFEST_SCHEMA = "rs.case2.source-manifest/1"

# How an input reached the run. A replay is distinguishable from an acquisition
# on purpose: they are different claims about where the bytes came from.
MODE_ONLINE = "ONLINE"
MODE_OFFLINE_REPLAY = "OFFLINE_REPLAY"
MODE_SUPPLIED_DATASET = "SUPPLIED_DATASET"

SENTINEL_LICENSE = (
    "https://sentinels.copernicus.eu/documents/247904/690755/"
    "Sentinel_Data_Legal_Notice")


@dataclass(frozen=True)
class SourceAdapter:
    """What one product is, who publishes it, and how this package reaches it."""

    key: str
    product: str
    version: str
    provider: str
    license: str
    attribution: str
    # True only where this package can obtain the product itself. Where it is
    # False the reason says how the data arrives instead, so an absent fetch is
    # never mistaken for a failed one.
    retrievable: bool
    access: str
    note: str = ""

    def entry(self, **fields):
        """One manifest row for this source, with the product fields filled in."""
        row = {
            "source": self.key,
            "product": self.product,
            "version": self.version,
            "provider": self.provider,
            "license": self.license,
            "attribution": self.attribution,
            "identifier": None,
            "url": None,
            "access_date": None,
            "checksum_sha256": None,
            "cache_key": None,
            "mode": MODE_SUPPLIED_DATASET,
        }
        row.update(fields)
        if row["access_date"] is None and row["mode"] == MODE_OFFLINE_REPLAY:
            # Saying "we do not know when this was fetched" is the only honest
            # thing to write when the cache entry did not record it. Inventing
            # a plausible date would make the manifest worse than empty.
            row["access_date_note"] = (
                "the cache entry that served this read was written before the "
                "access date was recorded; it is unknown, not assumed")
        return row


SENTINEL2_L2A = SourceAdapter(
    key="sentinel2_l2a",
    product="Sentinel-2 L2A surface reflectance",
    version="Collection 1, processing baseline recorded per item",
    provider="Element84 Earth Search (AWS Open Data), ESA Copernicus",
    license=SENTINEL_LICENSE,
    attribution="Contains modified Copernicus Sentinel data 2019-2024",
    retrievable=True,
    access="STAC search and a windowed read of the item's own asset",
    note=("the catalogue serves the same acquisition at more than one "
          "processing baseline, and from 04.00 the product carries a -0.1 "
          "radiometric offset; the item is therefore chosen explicitly"),
)

CCI_BIOMASS = SourceAdapter(
    key="cci_biomass",
    product="ESA CCI Biomass above-ground biomass and its standard deviation",
    version="v7.0",
    provider="ESA Climate Change Initiative",
    license="ESA CCI data policy; free for any use with attribution",
    attribution="ESA Climate Change Initiative Biomass project",
    retrievable=False,
    access="supplied with the case under data/<aoi>/CCI_Biomass_<year>.tif",
    note=("the competition set is the only source of analysis numbers; "
          "substituting another version of this product would change every "
          "published reference value"),
)

GFC_LOSSYEAR = SourceAdapter(
    key="gfc_lossyear",
    product="Global Forest Change tree cover, loss year and data mask",
    version="2025 v1.13",
    provider="Hansen / UMD / Google / USGS / NASA",
    license="CC BY 4.0",
    attribution="Hansen/UMD/Google/USGS/NASA Global Forest Change",
    retrievable=False,
    access="supplied with the case under data/<aoi>/GFC_2025_v1_13.tif",
)

MODIS_BURN_DATE = SourceAdapter(
    key="modis_burn_date",
    product="MODIS MCD64A1 burned area: burn date, QA and date uncertainty",
    version="Collection 6.1",
    provider="NASA LP DAAC",
    license="NASA Earth science data are open and free of charge",
    attribution="NASA MCD64A1 Collection 6.1",
    retrievable=False,
    access="supplied with the case under data/<aoi>/MODIS/",
    note=("supplied for the two Mordovia areas only; elsewhere the correct "
          "statement is that the product was not provided"),
)

ADAPTERS = {
    adapter.key: adapter for adapter in
    (SENTINEL2_L2A, CCI_BIOMASS, GFC_LOSSYEAR, MODIS_BURN_DATE)
}


def adapter_for(role):
    """The adapter behind a source role, or None when the role is not a product."""
    if role in ("sentinel2_reflectance", "sentinel2_scl"):
        return SENTINEL2_L2A
    return ADAPTERS.get(role)


def now_utc():
    """Access time, to the second, in UTC. Never enters a content hash."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def manifest(entries, *, generated_at=None):
    """The source manifest for one run.

    Ordered by source and identifier so two runs that used the same inputs
    produce the same list, and the only field that moves between them is the
    time - which is why it sits outside every hash in this package.
    """
    rows = sorted(entries, key=lambda row: (row["source"],
                                            row["identifier"] or "",
                                            row["cache_key"] or ""))
    return {
        "schema": MANIFEST_SCHEMA,
        "generated_at": generated_at if generated_at is not None else now_utc(),
        "adapters": [
            {
                "source": adapter.key,
                "product": adapter.product,
                "version": adapter.version,
                "provider": adapter.provider,
                "license": adapter.license,
                "attribution": adapter.attribution,
                "retrievable_by_this_package": adapter.retrievable,
                "access": adapter.access,
                "note": adapter.note,
            }
            for adapter in ADAPTERS.values()
        ],
        "inputs": rows,
        "modes": {
            MODE_ONLINE: "fetched from the open catalogue during this run",
            MODE_OFFLINE_REPLAY: (
                "served from a cache entry fetched earlier; a replay, and "
                "labelled as one rather than as an acquisition"),
            MODE_SUPPLIED_DATASET: (
                "read from the competition dataset in data/, which is the only "
                "source of analysis numbers"),
        },
        "note": (
            "no credential and no path from the producing machine appears in "
            "this document; asset hrefs are recorded without their query string"
        ),
    }


def supplied_entries(sources):
    """Manifest rows for the files a run read out of the supplied dataset."""
    rows = []
    for source in sources:
        adapter = adapter_for(source.role)
        if adapter is None:
            continue
        rows.append(adapter.entry(
            identifier=source.relative_path,
            checksum_sha256=source.sha256,
            mode=MODE_SUPPLIED_DATASET,
        ))
    return rows
