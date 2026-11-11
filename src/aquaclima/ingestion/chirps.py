"""Acquire CHIRPS v3 Final monthly GeoTIFFs and sample their native cells."""

import csv
import json
import math
import re
from collections.abc import Iterable
from datetime import date
from io import StringIO
from pathlib import Path

import rasterio
from numpy.ma import is_masked
from rasterio.errors import RasterioError
from rasterio.windows import Window
from shapely.geometry import shape

from aquaclima.storage.http import AcquisitionError, HttpClient, checksum, write_atomic, write_json

BASE_URL = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/monthly"
PRODUCT = "CHIRPS v3.0 Final monthly"
UNIT_SOURCE = "https://doi.org/10.1038/s41597-026-07096-4"
NODATA_SOURCE = "https://wiki.chc.ucsb.edu/CHIRPS3_FAQ"
PRODUCT_NODATA = -9999.0
GRID_DEGREES = 0.05
MONTH_PATTERN = re.compile(r"\d{4}-\d{2}", re.ASCII)
UNIT_ALIASES = {
    "mm", "mm/month", "mm/mo", "mmmonth-1", "mmmonth^-1",
    "mmmonth−1", "mm/monthly", "millimeter", "millimeters",
    "millimetre", "millimetres",
}

PRECIP_COLUMNS = [
    "pivot_id", "month", "precip_mm", "precip_status", "chirps_source",
    "chirps_product", "chirps_units", "chirps_resolution_deg",
    "chirps_cell_row", "chirps_cell_col", "chirps_cell_lon", "chirps_cell_lat",
]


def chirps_url(month: str, *, domain: str = "latam") -> str:
    if not MONTH_PATTERN.fullmatch(month):
        raise ValueError(f"Invalid month {month!r}; expected YYYY-MM")
    date.fromisoformat(f"{month}-01")
    if domain not in {"latam", "global"}:
        raise ValueError(f"Unknown CHIRPS domain: {domain}")
    stamp = month.replace("-", ".")
    return f"{BASE_URL}/{domain}/tifs/chirps-v3.0.{stamp}.tif"


def _metadata(dataset: rasterio.DatasetReader) -> dict:
    if dataset.driver != "GTiff" or dataset.count != 1:
        raise ValueError("CHIRPS must be a single-band GeoTIFF")
    if dataset.crs is None or dataset.crs.to_epsg() != 4326:
        raise ValueError(f"Unexpected CHIRPS CRS {dataset.crs}; expected EPSG:4326")
    transform = dataset.transform
    if (
        not math.isclose(transform.a, GRID_DEGREES, abs_tol=1e-7)
        or not math.isclose(transform.e, -GRID_DEGREES, abs_tol=1e-7)
        or transform.b != 0 or transform.d != 0
    ):
        raise ValueError(f"Unexpected CHIRPS grid: {transform}")
    tags = {key.lower(): value for key, value in (dataset.tags() | dataset.tags(1)).items()}
    band_units = dataset.units[0] or tags.get("units") or tags.get("unittype")
    if band_units and band_units.lower().replace(" ", "") not in UNIT_ALIASES:
        raise ValueError(f"Unexpected CHIRPS precipitation units: {band_units}")
    scale, offset = dataset.scales[0], dataset.offsets[0]
    if not math.isfinite(scale) or scale <= 0 or not math.isfinite(offset):
        raise ValueError("Invalid CHIRPS scale or offset")
    nodata = dataset.nodata
    if nodata is not None and not math.isfinite(nodata):
        nodata = str(nodata)
    return {
        "driver": dataset.driver,
        "crs": "EPSG:4326",
        "grid_degrees": GRID_DEGREES,
        "native_resolution_degrees": list(dataset.res),
        "width": dataset.width,
        "height": dataset.height,
        "bounds": list(dataset.bounds),
        "dtype": dataset.dtypes[0],
        "nodata": nodata,
        "provider_nodata": PRODUCT_NODATA,
        "provider_nodata_reference": NODATA_SOURCE,
        "scale": scale,
        "offset": offset,
        "file_unit_tag": band_units,
        "units": "mm",
        "accumulation": "calendar month",
        "unit_reference": UNIT_SOURCE,
    }


def validate_monthly_tif(path: Path) -> None:
    """Decode every GeoTIFF block so truncated imagery fails before publication."""
    with rasterio.open(path) as dataset:
        _metadata(dataset)
        for _, window in dataset.block_windows(1):
            dataset.read(1, window=window, masked=True)


def _unique_keys(pairs: list[tuple]) -> dict:
    document = dict(pairs)
    if len(document) != len(pairs):
        raise ValueError("Duplicate keys in CHIRPS manifest")
    return document


def _months(months: Iterable[str]) -> list[str]:
    requested = sorted(set(months))
    for month in requested:
        chirps_url(month)
    return requested


def _read_manifest(path: Path, data_dir: Path) -> dict:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ValueError(f"Invalid CHIRPS manifest: {path}") from error
    if (
        not isinstance(manifest, dict) or manifest.get("product") != PRODUCT
        or not isinstance(manifest.get("months"), dict)
    ):
        raise ValueError(f"Invalid CHIRPS manifest schema: {path}")
    for month, entry in manifest["months"].items():
        sources = {chirps_url(month, domain=domain) for domain in ("latam", "global")}
        if (
            not isinstance(entry, dict) or not isinstance(entry.get("status"), str)
            or not entry["status"] or not isinstance(entry.get("source"), str)
            or entry["source"] not in sources
        ):
            raise ValueError(f"Invalid CHIRPS manifest entry for {month}: {path}")
        if entry["status"] == "available" or "sha256" in entry:
            if (
                not isinstance(entry.get("path"), str) or not entry["path"]
                or Path(entry["path"]).is_absolute()
                or type(entry.get("size_bytes")) is not int or entry["size_bytes"] <= 0
                or not isinstance(entry.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"], re.ASCII) is None
                or not isinstance(entry.get("metadata"), dict)
            ):
                raise ValueError(f"Incomplete available CHIRPS record for {month}: {path}")
            _entry_path(data_dir, entry)
    return manifest


def _entry_path(data_dir: Path, entry: dict) -> Path:
    path = data_dir / entry["path"]
    _, domain, _, filename = entry["source"].rsplit("/", 3)
    expected = data_dir / "raw" / "chirps" / domain / filename
    if path.resolve() != expected.resolve():
        raise ValueError(f"Unexpected path for CHIRPS: {path}")
    return path


def _matches_entry(data_dir: Path, entry: dict) -> bool:
    path = _entry_path(data_dir, entry)
    return (
        path.is_file() and path.stat().st_size == entry["size_bytes"]
        and checksum(path) == entry["sha256"]
    )


def download_precip(
    http: HttpClient, data_dir: Path, months: Iterable[str], manifest_path: Path | None = None,
) -> Path:
    """Merge monthly checkpoints while sharing raw files across manifests.

    `manifest_path` defaults to the pilot manifest. Existing available records
    keep their origin metadata when the local file matches their recorded hash.
    Each completed or failed month is saved atomically before the next request.
    """
    directory = data_dir / "raw" / "chirps"
    manifest = manifest_path if manifest_path is not None else directory / "manifest.json"
    document = _read_manifest(manifest, data_dir) if manifest.is_file() else {"product": PRODUCT, "months": {}}
    entries = document["months"]
    requested = _months(months)
    paused = None
    for month in requested:
        domains = ["latam", "global"]
        previous = entries.get(month, {})
        if previous.get("sha256") and _matches_entry(data_dir, previous):
            if previous["status"] != "available":
                entries[month] = previous | {"status": "available"}
                write_json(manifest, document)
            continue
        if previous.get("source") == chirps_url(month, domain="global"):
            domains.reverse()
        failures = []
        acquired = None
        failure_status = paused or "not_published"
        failed_source = previous.get("source", chirps_url(month))
        for domain in domains:
            url = chirps_url(month, domain=domain)
            target = directory / domain / url.rsplit("/", 1)[-1]
            headers = None
            try:
                if http.is_verified(target, source=url):
                    validate_monthly_tif(target)
                else:
                    if paused:
                        continue
                    headers = http.head(url)
                    http.download(url, target, validate=validate_monthly_tif)
                with rasterio.open(target) as dataset:
                    metadata = _metadata(dataset)
                acquired = {
                    "status": "available",
                    "source": url,
                    "path": target.relative_to(data_dir).as_posix(),
                    "size_bytes": target.stat().st_size,
                    "sha256": checksum(target),
                    "metadata": metadata,
                }
                if headers is not None:
                    values = {key.lower(): value for key, value in headers.items()}
                    acquired["source_http"] = {
                        key: values[key] for key in ("content-length", "etag", "last-modified")
                        if key in values
                    }
                if previous.get("sha256") and (
                    previous["sha256"] != acquired["sha256"] or previous.get("source") != url
                ):
                    acquired["previous_acquisition"] = previous
                if failures:
                    acquired["failed_alternatives"] = failures
                elif previous.get("source") == url and previous.get("failed_alternatives"):
                    acquired["failed_alternatives"] = previous["failed_alternatives"]
                break
            except AcquisitionError as error:
                failures.append({"source": url, "error": str(error), "http_status": error.status_code})
                if error.status_code in {404, 410}:
                    continue
                if error.status_code in {403, 429}:
                    paused = "rate_limited" if error.status_code == 429 else "access_denied"
                failure_status = paused or "download_failed"
                failed_source = url
                break
            except (RasterioError, ValueError) as error:
                failures.append({"source": url, "error": str(error), "http_status": None})
                failure_status = "download_failed"
                failed_source = url
                break
        if acquired is not None:
            entries[month] = acquired
        else:
            retained = previous if previous.get("sha256") else {}
            entries[month] = retained | {
                "status": failure_status,
                "source": retained.get("source", failed_source),
                "failures": failures,
            }
            if paused and not failures:
                entries[month]["request_skipped"] = True
        write_json(manifest, document)
    if not requested:
        write_json(manifest, document)
    return manifest


def _pivot_points(pivots_path: Path) -> list[tuple[str, float, float]]:
    collection = json.loads(pivots_path.read_text(encoding="utf-8"))
    if collection.get("type") != "FeatureCollection":
        raise ValueError("Expected an RFC 7946 GeoJSON FeatureCollection")
    if "crs" in collection:
        raise ValueError("Pivot GeoJSON must use implicit RFC 7946 WGS84")
    points = []
    ids = set()
    for feature in collection["features"]:
        pivot_id = str(feature["properties"]["pivot_id"])
        if pivot_id in ids:
            raise ValueError(f"Duplicate pivot_id: {pivot_id}")
        ids.add(pivot_id)
        polygon = shape(feature["geometry"])
        if polygon.geom_type not in {"Polygon", "MultiPolygon"} or polygon.is_empty or not polygon.is_valid:
            raise ValueError(f"Invalid pivot polygon: {pivot_id}")
        point = polygon.representative_point()
        if not -180 <= point.x <= 180 or not -90 <= point.y <= 90:
            raise ValueError(f"Pivot point outside WGS84 coordinates: {pivot_id}")
        points.append((pivot_id, point.x, point.y))
    return points


def _sample(dataset: rasterio.DatasetReader, lon: float, lat: float) -> dict:
    row, col = dataset.index(lon, lat)
    if not (0 <= row < dataset.height and 0 <= col < dataset.width):
        return {"precip_status": "outside_grid"}
    cell_lon, cell_lat = dataset.xy(row, col)
    sample = dataset.read(1, window=Window(col, row, 1, 1), masked=True)[0, 0]
    result = {
        "chirps_cell_row": int(row),
        "chirps_cell_col": int(col),
        "chirps_cell_lon": round(float(cell_lon), 7),
        "chirps_cell_lat": round(float(cell_lat), 7),
    }
    if is_masked(sample) or sample == PRODUCT_NODATA:
        return result | {"precip_status": "nodata"}
    value = float(sample) * dataset.scales[0] + dataset.offsets[0]
    if not math.isfinite(value) or value < 0:
        return result | {"precip_status": "invalid_value"}
    return result | {"precip_mm": value, "precip_status": "ok"}


def extract_precip(
    pivots_path: Path, manifest_path: Path, data_dir: Path,
    months: Iterable[str] | None = None, output_path: Path | None = None,
) -> Path:
    """Sample native cells for all acquired months or an explicit selection.

    Missing requested months remain explicit rows. `output_path` allows a
    historical table to coexist with the default pilot precipitation CSV.
    """
    points = _pivot_points(pivots_path)
    manifest = _read_manifest(manifest_path, data_dir)
    selected = sorted(manifest["months"]) if months is None else _months(months)
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=PRECIP_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for month in selected:
        entry = manifest["months"].get(month, {"status": "no_monthly_data", "source": chirps_url(month)})
        base = {
            "month": month,
            "chirps_source": entry["source"],
            "chirps_product": PRODUCT,
            "chirps_units": "mm",
            "chirps_resolution_deg": GRID_DEGREES,
        }
        if entry["status"] != "available":
            for pivot_id, _, _ in points:
                writer.writerow(base | {"pivot_id": pivot_id, "precip_status": entry["status"]})
            continue
        path = _entry_path(data_dir, entry)
        if not _matches_entry(data_dir, entry):
            raise ValueError(f"Missing or corrupt local CHIRPS file for {month}: {path}")
        with rasterio.open(path) as dataset:
            _metadata(dataset)
            for pivot_id, lon, lat in points:
                writer.writerow(base | {"pivot_id": pivot_id} | _sample(dataset, lon, lat))
    path = output_path if output_path is not None else data_dir / "processed" / "precip_monthly.csv"
    write_atomic(path, output.getvalue().encode("utf-8"))
    return path
