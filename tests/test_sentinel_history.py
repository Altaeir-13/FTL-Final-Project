"""Monthly history tests use small synthetic rasters only as controlled fixtures."""

import copy
import json
from datetime import date, datetime

import numpy as np
import pytest
from rasterio.io import MemoryFile

from aquaclima.ingestion import sentinel
from aquaclima.processing.indices import process_indices
from aquaclima.storage.http import AcquisitionError, BudgetError, write_json
from test_sentinel import LocalStac, stac_case


class MonthlyStac(LocalStac):
    def __init__(self, root, items, assets):
        super().__init__(root, items[0] if items else None, assets)
        self.items = items
        self.blocked_url = None
        self.page_size = 50
        self.omit_next = False

    def get_json(self, url, *, method="GET", payload=None, path=None):
        source = self._identity(url, None, payload)
        if path is not None and self.is_verified(path, source=source):
            return json.loads(path.read_bytes())
        self.calls.append((method, url, payload))
        first, last = (datetime.fromisoformat(value) for value in payload["datetime"].split("/"))
        matches = [item for item in self.items if first <= datetime.fromisoformat(item["properties"]["datetime"]) <= last]
        page = {"type": "FeatureCollection", "features": matches[:self.page_size], "links": [], "numberMatched": len(matches)}
        if len(matches) > self.page_size and not self.omit_next:
            page["links"] = [{"rel": "next", "href": f"{sentinel.STAC_ROOT}/search", "method": "POST",
                              "body": payload | {"next": "unread-page"}}]
        if path is not None:
            self._save(path, (json.dumps(page) + "\n").encode(), source)
        return page

    def head(self, url):
        if url == self.blocked_url:
            raise AcquisitionError("Transient SCL service failure", status_code=503)
        return super().head(url)


@pytest.fixture
def monthly_case(stac_case, tmp_path):
    original, pivots = stac_case
    definitions = [
        ("S2_LOW_SCENE_CLOUD", "2025-07-01T12:00:00Z", 0.0, 9),
        ("S2_HIGH_SCENE_CLOUD", "2025-07-02T12:00:00Z", 95.0, 4),
        ("S2_DUPLICATE_DATE", "2025-07-02T12:00:01Z", 0.0, None),
        ("S2_SECOND_CLEAR", "2025-07-03T12:00:00Z", 90.0, 4),
    ]
    assets, items = {}, []
    for scene_id, timestamp, cloud, classification in definitions:
        item = copy.deepcopy(original.item)
        item["id"] = scene_id
        item["properties"].update(datetime=timestamp, **{"eo:cloud_cover": cloud})
        for name, asset in item["assets"].items():
            blob = original.assets[asset["href"]]
            if name == "scl" and classification is not None:
                with MemoryFile(blob) as memory, memory.open() as source:
                    values, profile = source.read(1), source.profile
                values[:] = classification
                with MemoryFile() as memory:
                    with memory.open(**profile) as destination:
                        destination.write(values, 1)
                    blob = memory.read()
            asset["href"] = f"https://example.invalid/{scene_id}/{name}.tif"
            asset["file:size"] = len(blob)
            assets[asset["href"]] = blob
        items.append(item)
    return MonthlyStac(tmp_path, items, assets), pivots


def _catalog(http, pivots, root, *, start=date(2025, 7, 1), end=date(2025, 7, 31)):
    return sentinel.search_scenes(http, pivots, root, start=start, end=end, max_cloud=100, max_scenes=500,
                                  plan_path=root / "history/batches/policy/2025-07/catalog.json", allow_empty=True)


def _screen(http, pivots, catalog, root, *, max_scenes=2):
    return sentinel.screen_scenes(http, pivots, catalog, root, output_path=catalog.with_name("selected.json"),
                                  max_scenes=max_scenes, min_valid_fraction=0.5)


def test_local_scl_selects_high_global_cloud_and_preserves_pilot(monthly_case, tmp_path):
    http, pivots = monthly_case
    pilot_catalog = tmp_path / "raw/sentinel/scenes.json"
    pilot_crops = pilot_catalog.with_name("crops.json")
    write_json(pilot_catalog, {"pilot": "preserve this catalog"})
    write_json(pilot_crops, {"scenes": []})
    pilot_indices = tmp_path / "processed/indices.csv"
    pilot_indices.parent.mkdir(parents=True, exist_ok=True)
    pilot_indices.write_bytes(b"pilot-indices\n")
    preserved = {path: path.read_bytes() for path in (pilot_catalog, pilot_crops, pilot_indices)}

    catalog = _catalog(http, pivots, tmp_path)
    assert list(catalog.parent.glob("catalog-pages/*/*.json"))
    selection = _screen(http, pivots, catalog, tmp_path)
    document = json.loads(selection.read_bytes())
    assert document["screening_complete"] and document["state"] == "complete"
    assert document["selected_ids"] == ["S2_HIGH_SCENE_CLOUD", "S2_SECOND_CLEAR"]
    decisions = {entry["id"]: entry for entry in document["screening"]}
    assert decisions["S2_LOW_SCENE_CLOUD"]["reason"] == "no_pivot_above_scl_threshold"
    assert decisions["S2_HIGH_SCENE_CLOUD"]["pivots"]["A"]["valid_fraction"] == 1
    assert decisions["S2_HIGH_SCENE_CLOUD"]["pivots"]["B"]["status"] == "no_intersection"
    assert decisions["S2_DUPLICATE_DATE"]["selection_reason"] == "lower_local_quality_or_duplicate_date"
    assert all(call[1].endswith("scl.tif") for call in http.calls if call[0] in {"HEAD", "GET"})
    calls, before = list(http.calls), selection.read_bytes()
    assert _catalog(http, pivots, tmp_path) == catalog
    assert _screen(http, pivots, catalog, tmp_path) == selection
    assert http.calls == calls and selection.read_bytes() == before

    with pytest.raises(ValueError, match="política"):
        _screen(http, pivots, catalog, tmp_path, max_scenes=1)
    with pytest.raises(ValueError, match="configuração"):
        _catalog(http, pivots, tmp_path, start=date(2025, 7, 2))
    crops = sentinel.acquire_crops(http, pivots, selection, tmp_path, manifest_path=catalog.with_name("crops.json"))
    assert json.loads(crops.read_bytes())["state"] == "complete"
    custom_indices = catalog.with_name("indices.csv")
    assert process_indices(pivots, crops, tmp_path, min_valid_fraction=0.5, output_path=custom_indices) == custom_indices
    assert all(path.read_bytes() == expected for path, expected in preserved.items())
    estimate = sentinel.estimate_acquisition(pivots, selection, tmp_path, max_scenes=2)
    assert estimate["estimated_transfer_bytes"] == 0
    assert estimate["declared_full_cog_bytes"] > 0
    assert not estimate["estimate_is_hard_cap"]


def test_screen_checkpoint_resumes_and_distinguishes_service_failure(monthly_case, tmp_path):
    http, pivots = monthly_case
    catalog = _catalog(http, pivots, tmp_path)
    interrupted_url = http.items[1]["assets"]["scl"]["href"]
    read_range = http.range_bytes

    def interrupt(url, *args, **kwargs):
        if url == interrupted_url:
            raise BudgetError("Controlled transfer limit")
        return read_range(url, *args, **kwargs)

    http.range_bytes = interrupt
    selected = catalog.with_name("selected.json")
    with pytest.raises(BudgetError):
        _screen(http, pivots, catalog, tmp_path)
    partial = json.loads(selected.read_bytes())
    assert not partial["screening_complete"]
    assert partial["screening"][0]["id"] == "S2_LOW_SCENE_CLOUD"
    assert partial["failures"][-1]["reason"] == "budget_interrupted"
    first_url = http.items[0]["assets"]["scl"]["href"]
    first_reads = sum(call[0] == "GET" and call[1] == first_url for call in http.calls)

    http.range_bytes = read_range
    http.blocked_url = interrupted_url
    _screen(http, pivots, catalog, tmp_path)
    partial = json.loads(selected.read_bytes())
    assert not partial["screening_complete"]
    assert any(entry["status"] == "failed" and entry["reason"] == "scl_acquisition_failed" for entry in partial["screening"])
    crops = catalog.with_name("crops.json")
    sentinel.acquire_crops(http, pivots, selected, tmp_path, manifest_path=crops)
    partial_ids = json.loads(crops.read_bytes())["selected_ids"]
    assert "S2_DUPLICATE_DATE" in partial_ids
    http.blocked_url = None
    _screen(http, pivots, catalog, tmp_path)
    resumed = json.loads(selected.read_bytes())
    assert resumed["screening_complete"]
    assert {entry["reason"] for entry in resumed["failures"]} == {"budget_interrupted", "scl_acquisition_failed"}
    assert sum(call[0] == "GET" and call[1] == first_url for call in http.calls) == first_reads
    sentinel.acquire_crops(http, pivots, selected, tmp_path, manifest_path=crops)
    final_crops = json.loads(crops.read_bytes())
    assert final_crops["selected_ids"] == resumed["selected_ids"]
    assert final_crops["attempt_history"][-1]["selected_ids"] == partial_ids


def test_crop_checkpoint_is_durable_before_next_asset(monthly_case, tmp_path):
    http, pivots = monthly_case
    catalog = _catalog(http, pivots, tmp_path)
    selection = _screen(http, pivots, catalog, tmp_path)
    first = next(item for item in http.items if item["id"] == "S2_HIGH_SCENE_CLOUD")
    read_range = http.range_bytes

    def interrupt(url, *args, **kwargs):
        if url == first["assets"]["nir"]["href"]:
            raise BudgetError("Controlled transfer limit")
        return read_range(url, *args, **kwargs)

    http.range_bytes = interrupt
    crops = catalog.with_name("crops.json")
    with pytest.raises(BudgetError):
        sentinel.acquire_crops(http, pivots, selection, tmp_path, manifest_path=crops)
    partial = json.loads(crops.read_bytes())
    assert partial["state"] == "incomplete"
    assert partial["scenes"][0]["assets"]["red"]["status"] == "ok"
    assert partial["scenes"][0]["status"] == "budget_interrupted"
    red_url = first["assets"]["red"]["href"]
    red_reads = sum(call[0] == "GET" and call[1] == red_url for call in http.calls)
    http.range_bytes = read_range
    sentinel.acquire_crops(http, pivots, selection, tmp_path, manifest_path=crops)
    complete = json.loads(crops.read_bytes())
    assert complete["state"] == "complete" and complete["attempt_history"]
    assert sum(call[0] == "GET" and call[1] == red_url for call in http.calls) == red_reads
    calls, content = list(http.calls), crops.read_bytes()
    sentinel.acquire_crops(http, pivots, selection, tmp_path, manifest_path=crops)
    assert http.calls == calls and crops.read_bytes() == content


def test_empty_month_is_complete_with_no_downloads(monthly_case, tmp_path):
    http, pivots = monthly_case
    http.items = []
    catalog = _catalog(http, pivots, tmp_path)
    assert json.loads(catalog.read_bytes())["query_complete"]
    selection = _screen(http, pivots, catalog, tmp_path)
    assert json.loads(selection.read_bytes())["screening_complete"]
    assert json.loads(selection.read_bytes())["selected"] == []
    assert all(call[0] == "POST" for call in http.calls)
    estimate = sentinel.estimate_acquisition(pivots, catalog, tmp_path)
    assert estimate["candidate_count"] == estimate["estimated_transfer_bytes"] == 0


def test_item_cap_subdivides_and_caches_all_raw_pages(monthly_case, tmp_path, monkeypatch):
    http, pivots = monthly_case
    monkeypatch.setattr(sentinel, "MAX_STAC_ITEMS", 2)
    http.page_size = 2
    catalog = _catalog(http, pivots, tmp_path)
    document = json.loads(catalog.read_bytes())
    assert document["candidate_count"] == 4 and document["query_complete"]
    assert len({item["id"] for item in document["candidates"]}) == 4
    assert len(list(catalog.parent.glob("catalog-pages/*/*.json"))) > 1
    before = list(http.calls)
    _catalog(http, pivots, tmp_path)
    assert http.calls == before
    http.omit_next = True
    missing_link_catalog = sentinel.search_scenes(
        http, pivots, tmp_path, start=date(2025, 7, 1), end=date(2025, 7, 31), max_cloud=100, max_scenes=500,
        plan_path=catalog.with_name("missing-next.json"), allow_empty=True,
    )
    assert json.loads(missing_link_catalog.read_bytes())["candidate_count"] == 4
    simultaneous = [copy.deepcopy(http.items[0]) for _ in range(3)]
    for i, item in enumerate(simultaneous):
        item["id"] = f"SIMULTANEOUS_{i}"
    http.items = simultaneous
    request = {"datetime": "2025-07-01T12:00:00+00:00/2025-07-01T12:00:00+00:00"}
    with pytest.raises(ValueError, match="menor intervalo"):
        sentinel._stac_items(http, request, subdivide=True)


def test_estimate_separates_full_cogs_from_partial_forecast(monthly_case, tmp_path):
    http, pivots = monthly_case
    catalog = _catalog(http, pivots, tmp_path)
    document = json.loads(catalog.read_bytes())
    for item in document["candidates"]:
        for asset in item["assets"].values():
            asset["file:size"] = 200_000_000
    write_json(catalog.with_name("estimate.json"), document)
    before = list(http.calls)
    estimate = sentinel.estimate_acquisition(pivots, catalog.with_name("estimate.json"), tmp_path, max_scenes=2)
    assert estimate["selected_scene_count_upper_bound"] == 2
    assert estimate["declared_full_cog_bytes"] == 3_200_000_000
    assert 0 < estimate["estimated_transfer_bytes"] < estimate["declared_full_cog_bytes"]
    assert estimate["estimated_transfer_bytes"] == estimate["estimated_scl_transfer_bytes"] + estimate["estimated_band_transfer_bytes"]
    assert http.calls == before
