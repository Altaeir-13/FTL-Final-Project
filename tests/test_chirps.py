import csv
import json
from pathlib import Path
from shutil import copyfile

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box, mapping

from aquaclima.ingestion.chirps import (
    chirps_url,
    download_precip,
    extract_precip,
    validate_monthly_tif,
)
from aquaclima.storage.http import AcquisitionError, BudgetError


class FixtureHttp:
    def __init__(self, urls):
        self.urls = urls
        self.calls = []
        self.verified = {}

    def head(self, url):
        self.calls.append(("HEAD", url))
        if url not in self.urls:
            raise AcquisitionError(f"Not found: {url}", status_code=404)
        return {"Content-Type": "image/tiff"}

    def download(self, url, path, *, validate):
        self.calls.append(("GET", url))
        path.parent.mkdir(parents=True, exist_ok=True)
        copyfile(self.urls[url], path)
        validate(path)
        self.verified[path] = url

    def is_verified(self, path, *, source):
        return path.is_file() and self.verified.get(path) == source


def _raster(path: Path, *, crs="EPSG:4326", units=None, nodata=-9999.0) -> Path:
    with rasterio.open(
        path, "w", driver="GTiff", width=2, height=2, count=1, dtype="float32",
        transform=from_origin(-48.0, -16.0, 0.05, 0.05),
        crs=crs, nodata=nodata,
    ) as dataset:
        dataset.write(np.array([[10, -9999], [0, 30]], dtype="float32"), 1)
        dataset.scales = (1.5,)
        dataset.offsets = (0.25,)
        if units is not None:
            dataset.set_band_unit(1, units)
    return path


def _pivots(path: Path) -> Path:
    coordinates = [(-47.98, -16.02), (-47.93, -16.02), (-47.90, -16.11)]
    features = [
        {
            "type": "Feature",
            "properties": {"pivot_id": str(index)},
            "geometry": mapping(box(lon - 0.001, lat - 0.001, lon + 0.001, lat + 0.001)),
        }
        for index, (lon, lat) in enumerate(coordinates)
    ]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    return path


@pytest.mark.parametrize("file_nodata", [-9999.0, None])
def test_months_missing_and_sampling_native_cells_offline(tmp_path, file_nodata):
    raster = _raster(tmp_path / "sample.tif", nodata=file_nodata)
    pivots = _pivots(tmp_path / "pivots.geojson")
    http = FixtureHttp({chirps_url("2025-07"): raster})
    manifest = download_precip(http, tmp_path, ["2025-08", "2025-07", "2025-07"])
    output = extract_precip(pivots, manifest, tmp_path)
    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    valid, nodata, outside, *unpublished = rows
    assert valid["precip_mm"] == "15.25"
    assert valid["precip_status"] == "ok"
    assert valid["chirps_cell_lon"] == "-47.975"
    assert valid["chirps_cell_lat"] == "-16.025"
    assert valid["chirps_units"] == "mm"
    assert nodata["precip_status"] == "nodata"
    assert outside["precip_status"] == "outside_grid"
    assert len(unpublished) == 3
    assert all(row["precip_status"] == "not_published" and row["precip_mm"] == "" for row in unpublished)
    expected = output.read_bytes()
    calls = list(http.calls)
    assert extract_precip(pivots, manifest, tmp_path).read_bytes() == expected
    assert http.calls == calls


def test_official_global_fallback_is_idempotent(tmp_path):
    month = "2025-07"
    raster = _raster(tmp_path / "sample.tif", units="mm/month")
    fallback = chirps_url(month, domain="global")
    http = FixtureHttp({fallback: raster})
    manifest = download_precip(http, tmp_path, [month])
    expected = manifest.read_bytes()
    row = json.loads(expected)["months"][month]
    assert row["source"] == fallback
    assert row["failed_alternatives"][0]["http_status"] == 404
    assert row["metadata"]["file_unit_tag"] == "mm/month"
    assert http.calls == [("HEAD", chirps_url(month)), ("HEAD", fallback), ("GET", fallback)]
    http.calls.clear()
    assert download_precip(http, tmp_path, [month]).read_bytes() == expected
    assert not http.calls


def test_offline_rejects_corrupt_cache(tmp_path):
    month = "2025-07"
    raster = _raster(tmp_path / "sample.tif")
    pivots = _pivots(tmp_path / "pivots.geojson")
    manifest = download_precip(FixtureHttp({chirps_url(month): raster}), tmp_path, [month])
    row = json.loads(manifest.read_text(encoding="utf-8"))["months"][month]
    path = tmp_path / row["path"]
    payload = path.read_bytes()
    path.write_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))
    with pytest.raises(ValueError, match="Missing or corrupt local CHIRPS"):
        extract_precip(pivots, manifest, tmp_path)


def test_source_failure_does_not_discard_other_months(tmp_path, monkeypatch):
    raster = _raster(tmp_path / "sample.tif")
    available = chirps_url("2025-08")
    http = FixtureHttp({available: raster})
    original_head = http.head

    def head(url):
        if url == chirps_url("2025-07"):
            raise AcquisitionError("Timeout after retries")
        return original_head(url)

    monkeypatch.setattr(http, "head", head)
    manifest = download_precip(http, tmp_path, ["2025-07", "2025-08"])
    months = json.loads(manifest.read_bytes())["months"]
    assert months["2025-07"]["status"] == "download_failed"
    assert months["2025-08"]["status"] == "available"


def test_budget_errors_are_not_source_failures(tmp_path, monkeypatch):
    http = FixtureHttp({})

    def head(_):
        raise BudgetError("Transfer budget exhausted")

    monkeypatch.setattr(http, "head", head)
    with pytest.raises(BudgetError, match="Transfer budget exhausted"):
        download_precip(http, tmp_path, ["2025-07"])


def test_rate_limit_stops_new_requests_and_preserves_cached_month(tmp_path, monkeypatch):
    available = chirps_url("2025-08")
    http = FixtureHttp({available: _raster(tmp_path / "sample.tif")})
    manifest = download_precip(http, tmp_path, ["2025-08"])
    http.calls.clear()

    def head(url):
        http.calls.append(("HEAD", url))
        raise AcquisitionError("HTTP 429 after retries", status_code=429)

    monkeypatch.setattr(http, "head", head)
    download_precip(http, tmp_path, ["2025-07", "2025-08", "2025-09"])
    months = json.loads(manifest.read_bytes())["months"]
    assert months["2025-07"]["status"] == "rate_limited"
    assert months["2025-08"]["status"] == "available"
    assert months["2025-09"]["request_skipped"]
    assert http.calls == [("HEAD", chirps_url("2025-07"))]


def test_changed_interval_retains_files_and_manifest(tmp_path):
    raster = _raster(tmp_path / "sample.tif")
    http = FixtureHttp({chirps_url(month): raster for month in ("2025-07", "2025-08")})
    manifest = download_precip(http, tmp_path, ["2025-07", "2025-08"])
    july = json.loads(manifest.read_bytes())["months"]["2025-07"]
    http.calls.clear()
    download_precip(http, tmp_path, ["2025-08"])
    assert list(json.loads(manifest.read_bytes())["months"]) == ["2025-07", "2025-08"]
    assert (tmp_path / july["path"]).is_file()
    assert not http.calls


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [({"crs": "EPSG:3857"}, "Unexpected CHIRPS CRS"), ({"units": "kg"}, "Unexpected CHIRPS precipitation units")],
)
def test_rejects_wrong_crs_or_units(tmp_path, kwargs, message):
    with pytest.raises(ValueError, match=message):
        validate_monthly_tif(_raster(tmp_path / "sample.tif", **kwargs))


@pytest.mark.parametrize("value", ["2025-00", "2025-13", "2025-7", "2025-07-01"])
def test_rejects_invalid_month(value):
    with pytest.raises(ValueError):
        chirps_url(value)
