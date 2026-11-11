"""Bounded public STAC comparison; catalog availability is not radiometric approval."""

from __future__ import annotations

import calendar
import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from shapely import union_all
from shapely.geometry import mapping, shape

from aquaclima.ingestion.sentinel import _cache_json, read_pivots
from aquaclima.storage.http import HttpClient, checksum, write_json

PROVIDERS = {
    "earth-c1": ("https://earth-search.aws.element84.com/v1", "sentinel-2-c1-l2a"),
    "earth-legacy": ("https://earth-search.aws.element84.com/v1", "sentinel-2-l2a"),
    "planetary": ("https://planetarycomputer.microsoft.com/api/stac/v1", "sentinel-2-l2a"),
    "copernicus": ("https://stac.dataspace.copernicus.eu/v1", "sentinel-2-l2a"),
}
ASSET_NAMES = {
    "earth-c1": {"B04": "red", "B08": "nir", "B11": "swir16", "SCL": "scl"},
    "earth-legacy": {"B04": "red", "B08": "nir", "B11": "swir16", "SCL": "scl"},
    "planetary": {name: name for name in ("B04", "B08", "B11", "SCL")},
    "copernicus": {"B04": "B04_10m", "B08": "B08_10m", "B11": "B11_20m", "SCL": "SCL_20m"},
}
ACCESS = {
    "earth-c1": "Anonymous STAC/HTTPS COG Range; no account",
    "earth-legacy": "Anonymous STAC/HTTPS COG Range; JP2 alternatives; calibration requires audit",
    "planetary": "Anonymous STAC; free temporary read-only SAS signing for Azure COGs; no persistent token",
    "copernicus": "Anonymous STAC; S3 asset access requires free CDSE account and S3 credentials",
}
PRODUCT = re.compile(r"(S2[ABCD])_MSIL2A_(\d{8}T\d{6})_N\d{4}_R(\d{3})_T([A-Z0-9]{5})_")


def product_acquisition(item: dict) -> str:
    """Use the SAFE sensing event, excluding generation date and baseline."""
    match = PRODUCT.search(item["properties"].get("s2:product_uri", item["id"]))
    if match:
        return "_".join(match.groups())
    # A fallback is explicit: catalogs differ in granule versus datatake time.
    properties = item["properties"]
    tile = properties.get("s2:mgrs_tile", properties.get("grid:code", "unknown"))
    return f"date_tile_fallback:{properties.get('platform')}:{properties['datetime'][:10]}:{tile}"


def _request(pivots, month: str, collection: str) -> dict:
    first = date.fromisoformat(month if len(month) == 10 else f"{month}-01")
    last = first if len(month) == 10 else first.replace(day=calendar.monthrange(first.year, first.month)[1])
    return {"collections": [collection], "intersects": mapping(union_all([geometry for _, geometry in pivots])),
            "datetime": f"{first}T00:00:00Z/{last}T23:59:59.999999Z", "limit": 100}


def _fetch(http: HttpClient, provider: str, request: dict, path: Path) -> dict:
    endpoint, collection = PROVIDERS[provider]
    method, url, payload = "POST", f"{endpoint}/search", request
    seen, items = set(), {}
    first, last = (datetime.fromisoformat(value) for value in request["datetime"].split("/"))
    for page_number in range(1, 101):
        identity = (method, url, json.dumps(payload, sort_keys=True))
        if identity in seen:
            raise ValueError("Repeated STAC diagnostic page")
        seen.add(identity)
        page = http.get_json(url, method=method, payload=payload,
                             path=path.with_name(f"{path.stem}-page-{page_number:03d}.json"))
        if page.get("type") != "FeatureCollection":
            raise ValueError("Expected a STAC FeatureCollection")
        for item in page["features"]:
            if item.get("collection") != collection or not first <= datetime.fromisoformat(item["properties"]["datetime"]) <= last:
                raise ValueError("Item outside requested collection or period")
            previous = items.setdefault(item["id"], item)
            if previous != item:
                raise ValueError("Conflicting duplicate STAC item")
            if len(items) > 500:
                raise ValueError("Diagnostic exceeds 500 products; reduce the requested interval")
        following = next((link for link in page.get("links", []) if link["rel"] == "next"), None)
        if following is None:
            matched = page.get("numberMatched", page.get("context", {}).get("matched"))
            if isinstance(matched, int) and matched != len(items):
                raise ValueError("STAC diagnostic result count mismatch")
            return {"provider": provider, "collection": collection, "source": endpoint, "request": request,
                    "query_complete": True, "candidate_count": len(items), "candidates": list(items.values())}
        url = urljoin(endpoint + "/", following["href"])
        if urlsplit(url).scheme != "https" or urlsplit(url).netloc != urlsplit(endpoint).netloc:
            raise ValueError("Unexpected STAC pagination domain")
        method = following.get("method", "GET").upper()
        if method not in {"GET", "POST"}:
            raise ValueError("Unexpected STAC pagination method")
        body = following.get("body", {})
        payload = ((request | body) if following.get("merge") else body) if method == "POST" else None
    raise ValueError("Excessive STAC diagnostic pagination")


def summarize_catalog(document: dict, pivots) -> dict:
    provider = document["provider"]
    endpoint, collection = PROVIDERS[provider]
    if (document.get("source") != endpoint or document.get("collection") != collection
            or document.get("candidate_count") != len(document["candidates"])
            or document.get("query_complete") is not True):
        raise ValueError("Incomplete or inconsistent catalog snapshot")
    if len({item["id"] for item in document["candidates"]}) != len(document["candidates"]):
        raise ValueError("Duplicate catalog item identifier")
    first, last = (datetime.fromisoformat(value) for value in document["request"]["datetime"].split("/"))
    rows = []
    for item in document["candidates"]:
        if item.get("collection") != collection or not first <= datetime.fromisoformat(item["properties"]["datetime"]) <= last:
            raise ValueError("Item outside requested collection or period")
        footprint = shape(item["geometry"])
        if footprint.is_empty or not footprint.is_valid:
            raise ValueError("Invalid catalog footprint")
        assets = {}
        for band, key in ASSET_NAMES[provider].items():
            asset = item["assets"].get(key)
            assets[band] = None if asset is None else {
                "key": key, "type": asset.get("type"), "href": asset["href"],
                "gsd": asset.get("gsd"), "raster_bands": asset.get("raster:bands"),
                "proj_shape": asset.get("proj:shape"), "proj_transform": asset.get("proj:transform"),
            }
        rows.append({"id": item["id"], "date": item["properties"]["datetime"][:10],
                     "datetime": item["properties"]["datetime"], "acquisition_key": product_acquisition(item),
                     "processing_baseline": item["properties"].get("s2:processing_baseline",
                         item["properties"].get("processing:version")),
                     "offset_applied": item["properties"].get("earthsearch:boa_offset_applied"),
                     "bbox": item["bbox"], "covered_pivots": [pivot for pivot, geom in pivots if footprint.covers(geom)],
                     "intersecting_pivots": [pivot for pivot, geom in pivots if footprint.intersection(geom).area > 0],
                     "all_required_assets": all(value is not None for value in assets.values()), "assets": assets})
    return {"provider": provider, "collection": document["collection"], "source": document["source"],
            "query_complete": document["query_complete"], "candidate_count": len(rows),
            "distinct_acquisitions": len({row["acquisition_key"] for row in rows}),
            "dates": sorted({row["date"] for row in rows}), "access": ACCESS[provider], "items": rows}


def run_catalog_diagnostic(http: HttpClient, pivots_path: Path, output_dir: Path, *,
                           months=("2022-01", "2022-07"), providers=tuple(PROVIDERS), offline=False) -> Path:
    """Query small monthly windows, retaining all versions and verified raw pages.

    Existing snapshots are immutable and must match their ledger, geometry and
    request. Failures remain explicit and do not suppress the other catalogs.
    """
    pivots = read_pivots(pivots_path)
    results = []
    for provider in providers:
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider {provider}")
        endpoint, collection = PROVIDERS[provider]
        for month in months:
            request = _request(pivots, month, collection)
            path = output_dir / "catalogs" / provider / f"{month}.json"
            try:
                if path.is_file():
                    if not http.is_verified(path, source=f"{endpoint}/search"):
                        raise ValueError(f"Unverified existing catalog {path}")
                    document = json.loads(path.read_bytes())
                    if (json.dumps(document["request"], sort_keys=True) != json.dumps(request, sort_keys=True)
                            or not document.get("query_complete")):
                        raise ValueError(f"Catalog configuration mismatch {path}")
                elif offline:
                    raise FileNotFoundError(f"Catalog unavailable offline: {path}")
                else:
                    document = _fetch(http, provider, request, path)
                    _cache_json(http, path, document, f"{endpoint}/search")
                result = summarize_catalog(document, pivots) | {"month": month, "status": "ok", "catalog_sha256": checksum(path)}
            except (OSError, ValueError, RuntimeError) as error:
                result = {"provider": provider, "collection": collection, "month": month, "status": "failed",
                          "error": str(error), "access": ACCESS[provider]}
            results.append(result)
    target = output_dir / "catalog_comparison.json"
    write_json(target, {"pivots_sha256": checksum(pivots_path), "months": list(months), "results": results,
                        "warning": "Metadata availability does not establish radiometric compatibility or local clear-sky quality."})
    return target
