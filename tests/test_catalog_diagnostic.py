import copy
import json
from pathlib import Path

import pytest
from shapely.geometry import box, mapping

from aquaclima.ingestion.catalog_diagnostic import (
    PROVIDERS, _fetch, _request, product_acquisition, run_catalog_diagnostic, summarize_catalog,
)
from aquaclima.ingestion.sentinel import _cache_json
from aquaclima.storage.http import HttpClient


def item(identifier="S2A_MSIL2A_20220728T132241_N0400_R038_T23KKA_20220729T211106"):
    return {"id": identifier, "collection": "sentinel-2-l2a", "bbox": [0, 0, 4, 4],
            "geometry": mapping(box(0, 0, 4, 4)), "properties": {
                "datetime": "2022-07-28T13:22:41.024Z", "s2:processing_baseline": "04.00"},
            "assets": {key: {"href": f"s3://eodata/{key}.jp2", "type": "image/jp2"}
                       for key in ("B04_10m", "B08_10m", "B11_20m", "SCL_20m")}}


def snapshot(items):
    endpoint, collection = PROVIDERS["copernicus"]
    return {"provider": "copernicus", "source": endpoint, "collection": collection,
            "candidate_count": len(items), "candidates": items, "query_complete": True,
            "request": _request([("P", box(1, 1, 2, 2))], "2022-07", collection)}


def test_versions_are_preserved_and_acquisitions_counted_once():
    original = item()
    reprocessed = item("S2A_MSIL2A_20220728T132241_N0510_R038_T23KKA_20240709T005945")
    assert product_acquisition(original) == product_acquisition(reprocessed)
    summary = summarize_catalog(snapshot([original, reprocessed]), [("P", box(1, 1, 2, 2))])
    assert summary["candidate_count"] == 2
    assert summary["distinct_acquisitions"] == 1
    assert summary["items"][0]["covered_pivots"] == ["P"]
    assert summary["items"][0]["all_required_assets"]
    assert summary["items"][0]["assets"]["B08"]["key"] == "B08_10m"


def test_missing_asset_and_partial_coverage_are_explicit():
    source = item()
    del source["assets"]["B11_20m"]
    summary = summarize_catalog(snapshot([source]), [("P", box(3, 3, 5, 5))])
    row = summary["items"][0]
    assert not row["all_required_assets"]
    assert row["assets"]["B11"] is None
    assert row["covered_pivots"] == []
    assert row["intersecting_pivots"] == ["P"]


@pytest.mark.parametrize("mutation", ["count", "duplicate", "period", "collection"])
def test_corrupt_snapshots_are_rejected(mutation):
    document = snapshot([item()])
    if mutation == "count": document["candidate_count"] = 2
    if mutation == "duplicate": document["candidates"] *= 2; document["candidate_count"] = 2
    if mutation == "period": document["candidates"][0]["properties"]["datetime"] = "2023-07-28T13:22:41Z"
    if mutation == "collection": document["candidates"][0]["collection"] = "wrong"
    with pytest.raises(ValueError):
        summarize_catalog(document, [("P", box(1, 1, 2, 2))])


class Pages:
    def __init__(self, pages):
        self.pages = iter(pages)

    def get_json(self, *args, **kwargs):
        return next(self.pages)


def test_fetch_detects_truncation_and_unexpected_pagination(tmp_path):
    request = snapshot([])["request"]
    page = {"type": "FeatureCollection", "features": [item()], "links": [], "numberMatched": 2}
    with pytest.raises(ValueError, match="count"):
        _fetch(Pages([page]), "copernicus", request, tmp_path / "catalog.json")
    page["links"] = [{"rel": "next", "href": "https://other.invalid/search"}]
    with pytest.raises(ValueError, match="domain"):
        _fetch(Pages([page]), "copernicus", request, tmp_path / "catalog.json")


def test_pagination_preserves_different_processing_versions(tmp_path):
    first, second = item(), item("S2A_MSIL2A_20220728T132241_N0510_R038_T23KKA_20240709T005945")
    pages = [
        {"type": "FeatureCollection", "features": [first], "links": [{"rel": "next", "href": "/v1/search?next=2"}]},
        {"type": "FeatureCollection", "features": [second], "links": [], "numberMatched": 2},
    ]
    document = _fetch(Pages(pages), "copernicus", snapshot([])["request"], tmp_path / "catalog.json")
    assert document["candidate_count"] == 2


def test_existing_verified_snapshot_replays_offline_and_is_immutable(tmp_path, monkeypatch):
    pivots = tmp_path / "pivots.geojson"
    pivots.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"pivot_id": "P"}, "geometry": mapping(box(1, 1, 2, 2))}]}))
    http = HttpClient(ledger=tmp_path / "http.jsonl")
    document = snapshot([item()])
    target = tmp_path / "catalogs/copernicus/2022-07.json"
    _cache_json(http, target, document, f"{PROVIDERS['copernicus'][0]}/search")
    monkeypatch.setattr(http.session, "request", lambda *a, **k: pytest.fail("Network access in offline mode"))
    result = run_catalog_diagnostic(http, pivots, tmp_path, months=("2022-07",), providers=("copernicus",), offline=True)
    assert json.loads(result.read_bytes())["results"][0]["status"] == "ok"
    assert http.transferred == http.downloads == 0
    original = target.read_bytes()
    result = run_catalog_diagnostic(http, pivots, tmp_path, months=("2022-01",), providers=("copernicus",), offline=True)
    assert json.loads(result.read_bytes())["results"][0]["status"] == "failed"
    assert target.read_bytes() == original
def test_single_day_comparison_keeps_exact_daily_interval():
    from aquaclima.ingestion.catalog_diagnostic import _request
    from shapely.geometry import box

    request = _request([("8087", box(-47.2, -17.6, -47.1, -17.5))], "2022-03-20", "sentinel-2-l2a")
    assert request["datetime"] == "2022-03-20T00:00:00Z/2022-03-20T23:59:59.999999Z"

