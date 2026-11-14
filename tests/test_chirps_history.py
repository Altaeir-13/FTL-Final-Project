"""Regression checks for accumulated monthly acquisition and historical exports."""

import csv
import json

import pytest

from aquaclima.ingestion.chirps import PRODUCT, chirps_url, download_precip, extract_precip, usgs_url
from aquaclima.storage.http import AcquisitionError, BudgetError, write_json
from test_chirps import FixtureHttp, _pivots, _raster


def test_incremental_month_preserves_valid_origin_without_ledger(tmp_path, monkeypatch):
    raster = _raster(tmp_path / "fixture.tif")
    http = FixtureHttp({chirps_url("2025-07"): raster})
    manifest = download_precip(http, tmp_path, ["2025-07"])
    document = json.loads(manifest.read_bytes())
    document["note"] = "Acquisition provenance from the pilot"
    document["months"]["2025-07"]["metadata"]["origin_note"] = "Preserve original metadata"
    write_json(manifest, document)
    original = json.loads(manifest.read_bytes())["months"]["2025-07"]
    http.verified.clear()
    http.calls.clear()

    def unavailable(url):
        http.calls.append(("HEAD", url))
        raise AcquisitionError("Source unavailable after retries", status_code=503)

    monkeypatch.setattr(http, "head", unavailable)
    download_precip(http, tmp_path, ["2025-07", "2025-08"])
    result = json.loads(manifest.read_bytes())
    assert result["months"]["2025-07"] == original
    assert result["months"]["2025-08"]["status"] == "download_failed"
    assert result["note"] == document["note"]
    assert http.calls == [("HEAD", chirps_url("2025-08"))]


def test_separate_manifest_reuses_shared_raw_files(tmp_path):
    raster = _raster(tmp_path / "fixture.tif")
    http = FixtureHttp({chirps_url("2025-07"): raster})
    pilot = download_precip(http, tmp_path, ["2025-07"])
    pilot_bytes = pilot.read_bytes()
    history = tmp_path / "history" / "chirps.json"
    http.calls.clear()
    assert download_precip(http, tmp_path, ["2025-07"], manifest_path=history) == history
    assert not http.calls
    assert pilot.read_bytes() == pilot_bytes
    pilot_entry = json.loads(pilot_bytes)["months"]["2025-07"]
    history_entry = json.loads(history.read_bytes())["months"]["2025-07"]
    assert history_entry["path"] == pilot_entry["path"]
    assert history_entry["sha256"] == pilot_entry["sha256"]


def test_budget_interruption_keeps_checkpoint_and_retries_only_missing_file(tmp_path, monkeypatch):
    raster = _raster(tmp_path / "fixture.tif")
    months = ["2025-07", "2025-08"]
    http = FixtureHttp({chirps_url(month): raster for month in months})
    manifest = tmp_path / "history" / "chirps.json"
    original_download = http.download
    completed = {}

    def interrupted_download(url, path, *, validate):
        if url == chirps_url("2025-08"):
            checkpoint = json.loads(manifest.read_bytes())
            assert list(checkpoint["months"]) == ["2025-07"]
            completed.update(checkpoint["months"]["2025-07"])
            raise BudgetError("Transfer interrupted at the second file")
        original_download(url, path, validate=validate)

    monkeypatch.setattr(http, "download", interrupted_download)
    with pytest.raises(BudgetError, match="second file"):
        download_precip(http, tmp_path, months, manifest_path=manifest)
    assert json.loads(manifest.read_bytes())["months"] == {"2025-07": completed}
    http.calls.clear()
    monkeypatch.setattr(http, "download", original_download)
    download_precip(http, tmp_path, months, manifest_path=manifest)
    assert http.calls == [("HEAD", chirps_url("2025-08")), ("GET", chirps_url("2025-08"))]
    assert json.loads(manifest.read_bytes())["months"]["2025-07"] == completed


def test_corrupt_local_file_failure_preserves_recorded_origin(tmp_path, monkeypatch):
    raster = _raster(tmp_path / "fixture.tif")
    http = FixtureHttp({chirps_url("2025-07"): raster})
    manifest = download_precip(http, tmp_path, ["2025-07"])
    original = json.loads(manifest.read_bytes())["months"]["2025-07"]
    raw = tmp_path / original["path"]
    raw.write_bytes(b"broken")
    monkeypatch.setattr(http, "is_verified", lambda *args, **kwargs: False)

    def unavailable(_):
        raise AcquisitionError("Source unavailable", status_code=503)

    monkeypatch.setattr(http, "head", unavailable)
    download_precip(http, tmp_path, ["2025-07"])
    failed = json.loads(manifest.read_bytes())["months"]["2025-07"]
    assert failed["status"] == "download_failed"
    for key in ("source", "path", "size_bytes", "sha256", "metadata"):
        assert failed[key] == original[key]


@pytest.mark.parametrize(
    "content",
    [
        b"{",
        b'{"product":"CHIRPS v3.0 Final monthly","months":{},"months":{}}',
        b'{"product":"other","months":{}}',
        b'{"product":"CHIRPS v3.0 Final monthly","months":[]}',
        json.dumps({"product": PRODUCT, "months": {"2025-07": {"status": "available", "source": []}}}).encode(),
        json.dumps({
            "product": PRODUCT,
            "months": {"2025-07": {"status": "available", "source": chirps_url("2025-07")}},
        }).encode(),
    ],
)
def test_corrupt_manifest_fails_before_requests_or_replacement(tmp_path, content):
    manifest = tmp_path / "history" / "chirps.json"
    manifest.parent.mkdir()
    manifest.write_bytes(content)
    http = FixtureHttp({})
    with pytest.raises(ValueError):
        download_precip(http, tmp_path, ["2025-08"], manifest_path=manifest)
    assert manifest.read_bytes() == content
    assert not http.calls


def test_selected_months_and_output_leave_pilot_intact(tmp_path):
    raster = _raster(tmp_path / "fixture.tif")
    pivots = _pivots(tmp_path / "pivots.geojson")
    http = FixtureHttp({chirps_url(month): raster for month in ("2025-07", "2025-08")})
    manifest = download_precip(http, tmp_path, ["2025-07", "2025-08"])
    pilot = extract_precip(pivots, manifest, tmp_path)
    pilot_bytes = pilot.read_bytes()
    manifest_bytes = manifest.read_bytes()
    selected = tmp_path / "history" / "processed" / "precip-2025-07_2025-09.csv"
    assert extract_precip(
        pivots, manifest, tmp_path, months=["2025-09", "2025-07"], output_path=selected,
    ) == selected
    with selected.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 6
    assert {row["month"] for row in rows} == {"2025-07", "2025-09"}
    absent = [row for row in rows if row["month"] == "2025-09"]
    assert all(row["precip_status"] == "no_monthly_data" and row["precip_mm"] == "" for row in absent)
    assert pilot.read_bytes() == pilot_bytes
    assert manifest.read_bytes() == manifest_bytes


def test_manifest_cannot_assign_another_months_raw_file(tmp_path):
    raster = _raster(tmp_path / "fixture.tif")
    http = FixtureHttp({chirps_url(month): raster for month in ("2025-07", "2025-08")})
    manifest = download_precip(http, tmp_path, ["2025-07", "2025-08"])
    document = json.loads(manifest.read_bytes())
    document["months"]["2025-07"]["path"] = document["months"]["2025-08"]["path"]
    write_json(manifest, document)
    original = manifest.read_bytes()
    http.calls.clear()
    with pytest.raises(ValueError, match="Unexpected path"):
        download_precip(http, tmp_path, ["2025-07"])
    assert manifest.read_bytes() == original
    assert not http.calls


def test_all_month_arguments_are_validated_before_acquisition(tmp_path):
    http = FixtureHttp({})
    with pytest.raises(ValueError):
        download_precip(http, tmp_path, ["2025-07", "2025-13"])
    assert not http.calls
    assert not (tmp_path / "raw" / "chirps" / "manifest.json").exists()


def test_explicit_usgs_mode_preserves_ucsb_files_and_failed_attempts(tmp_path):
    raster = _raster(tmp_path / "fixture.tif")
    http = FixtureHttp({
        chirps_url("2022-01"): raster,
        usgs_url("2022-04"): raster,
        usgs_url("2022-05"): raster,
    })
    manifest = download_precip(http, tmp_path, ["2022-01"])
    original = json.loads(manifest.read_bytes())
    available = original["months"]["2022-01"]
    failed = {
        "status": "rate_limited", "source": chirps_url("2022-04"),
        "failures": [{"source": chirps_url("2022-04"), "http_status": 429, "error": "HTTP 429 after retries"}],
    }
    skipped = {"status": "rate_limited", "source": chirps_url("2022-05"), "failures": [], "request_skipped": True}
    original["months"].update({"2022-04": failed, "2022-05": skipped})
    write_json(manifest, original)
    http.calls.clear()
    download_precip(http, tmp_path, ["2022-01", "2022-04", "2022-05"], provider="usgs")
    months = json.loads(manifest.read_bytes())["months"]
    assert months["2022-01"] == available
    assert months["2022-04"]["source_attempt_history"] == [failed]
    assert months["2022-05"]["source_attempt_history"] == [skipped]
    for month in ("2022-04", "2022-05"):
        entry = months[month]
        assert entry["status"] == "available"
        assert entry["source"] == usgs_url(month)
        assert entry["path"] == f"raw/chirps/usgs/chirps-v3.0.{month.replace('-', '.')}.tif"
        assert entry["publisher"] == "USGS EROS / FEWS NET"
        assert entry["provider"] == "usgs"
        assert entry["product_stage"] == "Final"
    assert http.calls == [
        ("HEAD", usgs_url("2022-04")), ("GET", usgs_url("2022-04")),
        ("HEAD", usgs_url("2022-05")), ("GET", usgs_url("2022-05")),
    ]
    expected = manifest.read_bytes()
    http.calls.clear()
    download_precip(http, tmp_path, ["2022-01", "2022-04", "2022-05"], provider="usgs")
    assert manifest.read_bytes() == expected
    assert not http.calls


def test_usgs_file_supports_offline_extraction_and_exact_month_binding(tmp_path):
    raster = _raster(tmp_path / "fixture.tif")
    pivots = _pivots(tmp_path / "pivots.geojson")
    http = FixtureHttp({usgs_url("2022-04"): raster})
    manifest = download_precip(http, tmp_path, ["2022-04"], provider="usgs")
    http.calls.clear()
    output = extract_precip(pivots, manifest, tmp_path)
    with output.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["precip_mm"] == "15.25"
    assert rows[0]["chirps_source"] == usgs_url("2022-04")
    assert not http.calls
    malformed = json.loads(manifest.read_bytes())
    malformed["months"]["2022-04"]["path"] = "raw/chirps/usgs/chirps-v3.0.2022.05.tif"
    write_json(manifest, malformed)
    with pytest.raises(ValueError, match="Unexpected path"):
        extract_precip(pivots, manifest, tmp_path)


def test_default_ucsb_mode_does_not_implicitly_request_usgs(tmp_path):
    http = FixtureHttp({usgs_url("2022-04"): _raster(tmp_path / "fixture.tif")})
    manifest = download_precip(http, tmp_path, ["2022-04"])
    assert json.loads(manifest.read_bytes())["months"]["2022-04"]["status"] == "not_published"
    assert http.calls == [
        ("HEAD", chirps_url("2022-04")),
        ("HEAD", chirps_url("2022-04", domain="global")),
    ]


def test_invalid_provider_fails_before_any_requests_or_write(tmp_path):
    http = FixtureHttp({})
    with pytest.raises(ValueError, match="Unknown CHIRPS provider"):
        download_precip(http, tmp_path, ["2022-04"], provider="unknown")
    assert not http.calls
    assert not (tmp_path / "raw/chirps/manifest.json").exists()
