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


def download_precip(http: HttpClient, data_dir: Path, months: Iterable[str]) -> Path:
    """Record availability, provenance, and integrity for each requested month."""
    directory = data_dir / "raw" / "chirps"
    manifest = directory / "manifest.json"
    previous_entries = json.loads(manifest.read_text(encoding="utf-8"))["months"] if manifest.is_file() else {}
    requested = sorted(set(months))
    entries = {month: previous_entries[month] for month in requested if month in previous_entries}
    paused = None
    for month in requested:
        domains = ["latam", "global"]
        previous = entries.get(month, {})
        if previous.get("status") == "available" and previous.get("source") == chirps_url(month, domain="global"):
            domains.reverse()
        failures = []
        for domain in domains:
            url = chirps_url(month, domain=domain)
            target = directory / domain / url.rsplit("/", 1)[-1]
            try:
                if http.is_verified(target, source=url):
                    if previous.get("status") != "available" or previous.get("source") != url:
                        validate_monthly_tif(target)
                else:
                    if paused:
                        continue
                    http.head(url)
                    http.download(url, target, validate=validate_monthly_tif)
                with rasterio.open(target) as dataset:
                    metadata = _metadata(dataset)
                entries[month] = {
                    "status": "available",
                    "source": url,
                    "path": target.relative_to(data_dir).as_posix(),
                    "size_bytes": target.stat().st_size,
                    "sha256": checksum(target),
                    "metadata": metadata,
                }
                if failures:
                    entries[month]["failed_alternatives"] = failures
                elif previous.get("source") == url and previous.get("failed_alternatives"):
                    entries[month]["failed_alternatives"] = previous["failed_alternatives"]
                break
            except AcquisitionError as error:
                failures.append({"source": url, "error": str(error), "http_status": error.status_code})
                if error.status_code in {404, 410}:
                    continue
                if error.status_code in {403, 429}:
                    paused = "rate_limited" if error.status_code == 429 else "access_denied"
                entries[month] = {"status": paused or "download_failed", "source": url, "failures": failures}
                break
            except (RasterioError, ValueError) as error:
                failures.append({"source": url, "error": str(error), "http_status": None})
                entries[month] = {"status": "download_failed", "source": url, "failures": failures}
                break
        else:
            entries[month] = {
                "status": paused or "not_published",
                "source": chirps_url(month),
                "failures": failures,
            }
            if paused:
                entries[month]["request_skipped"] = True
        write_json(manifest, {"product": PRODUCT, "months": entries})
    if not requested:
        write_json(manifest, {"product": PRODUCT, "months": entries})
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


def extract_precip(pivots_path: Path, manifest_path: Path, data_dir: Path) -> Path:
    """Sample the cell containing a polygon's interior representative point."""
    points = _pivot_points(pivots_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=PRECIP_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for month, entry in sorted(manifest["months"].items()):
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
        path = data_dir / entry["path"]
        if not path.resolve().is_relative_to((data_dir / "raw" / "chirps").resolve()):
            raise ValueError(f"Unexpected path for CHIRPS {month}: {path}")
        if not path.is_file() or path.stat().st_size != entry["size_bytes"] or checksum(path) != entry["sha256"]:
            raise ValueError(f"Missing or corrupt local CHIRPS file for {month}: {path}")
        with rasterio.open(path) as dataset:
            _metadata(dataset)
            for pivot_id, lon, lat in points:
                writer.writerow(base | {"pivot_id": pivot_id} | _sample(dataset, lon, lat))
    path = data_dir / "processed" / "precip_monthly.csv"
    write_atomic(path, output.getvalue().encode("utf-8"))
    return path
