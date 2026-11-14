"""Historical orchestration exercises mocked sources with real local persistence."""

import json
from datetime import date
from shutil import copyfile
from types import SimpleNamespace

import pytest
import requests
from shapely.geometry import box, mapping

from aquaclima import history
from aquaclima.cli import main
from aquaclima.ingestion.chirps import chirps_url, usgs_url
from aquaclima.storage.http import AcquisitionError, BudgetError, HttpClient, checksum, write_atomic, write_json
from test_chirps import _raster


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    root = tmp_path / "data"
    pivots = root / "processed" / "pivots.geojson"
    write_json(pivots, {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature", "properties": {"pivot_id": "0001", "area_ha": 1.55},
            "geometry": mapping(box(-47.981, -16.021, -47.979, -16.019)),
        }],
    })
    pilot = root / "processed" / "indices.csv"
    pilot.write_bytes(b"existing pilot observations\n")
    config = tmp_path / "history.toml"
    config.write_text(
        "[history]\nstart = 2022-01-01\nend = 2022-03-31\n"
        "max_scenes_per_month = 2\nmin_valid_fraction = 0.7\n"
        "[limits]\nmax_transfer_bytes = 100000000\nmax_storage_bytes = 100000000\nmax_downloads = 1000\n",
        encoding="utf-8",
    )
    rainfall = _raster(tmp_path / "rainfall.tif")
    state = SimpleNamespace(head=[], searches=[], screens=[], crops=[], estimates=[], offline=False)

    def forbidden_request(*args, **kwargs):
        pytest.fail("A real network request escaped the mocked sources")

    monkeypatch.setattr(requests.Session, "request", forbidden_request)

    class SourceHttp(HttpClient):
        def __init__(self, **kwargs):
            if state.offline:
                pytest.fail("Offline execution created an HTTP client")
            super().__init__(**kwargs)

        def head(self, url):
            state.head.append(url)
            self._log("http", method="HEAD", url=url, status=200, bytes=0, elapsed_s=0, error=None)
            return {"Content-Length": str(rainfall.stat().st_size), "ETag": '"fixture"'}

        def download(self, url, path, *, validate):
            self._reserve_transfer(rainfall.stat().st_size)
            path.parent.mkdir(parents=True, exist_ok=True)
            copyfile(rainfall, path)
            validate(path)
            self.transferred += path.stat().st_size
            self.record_file(path, source=url)
            self._log("http", method="GET", url=url, status=200, bytes=path.stat().st_size, elapsed_s=0, error=None)
            return path

    def save(http, path, document):
        write_json(path, document)
        http.record_file(path, source="https://earth-search.aws.element84.com/v1/search")
        return path

    def search(http, pivots_path, data_dir, *, start, end, max_cloud, max_scenes, plan_path, allow_empty):
        state.searches.append((start, end, max_cloud, max_scenes, allow_empty))
        assert start.year < 2025 and end.year < 2025
        candidates = [{
            "id": f"SCENE_{start:%Y%m}_{day:02}", "collection": "sentinel-2-c1-l2a",
            "properties": {"datetime": f"{start:%Y-%m}-{day:02}T12:00:00Z"},
        } for day in range(1, 6)]
        return save(http, plan_path, {
            "collection": "sentinel-2-c1-l2a", "candidate_count": len(candidates), "candidates": candidates,
            "selected": candidates, "selected_ids": [item["id"] for item in candidates],
            "request": {"datetime": f"{start}T00:00:00Z/{end}T23:59:59.999999Z"},
            "parameters": {"pivots_sha256": checksum(pivots_path), "max_cloud": max_cloud, "max_scenes": max_scenes},
            "query_complete": True,
        })

    def estimate(pivots_path, catalog_path, data_dir, *, max_scenes):
        state.estimates.append(catalog_path)
        catalog = json.loads(catalog_path.read_bytes())
        return {"estimated_transfer_bytes": 5000, "candidate_count": catalog["candidate_count"],
                "selected_scene_count_upper_bound": max_scenes}

    def screen(http, pivots_path, catalog_path, data_dir, *, output_path, max_scenes, min_valid_fraction):
        state.screens.append((catalog_path, max_scenes, min_valid_fraction))
        catalog = json.loads(catalog_path.read_bytes())
        selected = catalog["candidates"][:max_scenes]
        return save(http, output_path, {
            **catalog, "selected": selected, "selected_ids": [item["id"] for item in selected],
            "screening_complete": True, "catalog_sha256": checksum(catalog_path),
            "screening_policy": {"max_scenes": max_scenes, "min_valid_fraction": min_valid_fraction},
        })

    def crops(http, pivots_path, selected_path, data_dir, *, manifest_path):
        selected = json.loads(selected_path.read_bytes())
        state.crops.append(selected["selected_ids"])
        return save(http, manifest_path, {
            "collection": "sentinel-2-c1-l2a", "pivots_sha256": checksum(pivots_path),
            "plan_sha256": checksum(selected_path), "state": "complete",
            "scenes": [{
                "id": item["id"], "date": item["properties"]["datetime"][:10], "status": "ok",
            } for item in selected["selected"]],
        })

    def indices(pivots_path, crops_path, data_dir, *, min_valid_fraction, output_path):
        scenes = json.loads(crops_path.read_bytes())["scenes"]
        rows = "pivot_id,date,scene_id,status,ndvi_median,ndmi_median,valid_pixel_pct\n"
        rows += "".join(f"0001,{scene['date']},{scene['id']},ok,0.6,0.2,95\n" for scene in scenes)
        write_atomic(output_path, rows.encode("utf-8"))
        return output_path

    monkeypatch.setattr(history, "HttpClient", SourceHttp)
    monkeypatch.setattr(history, "search_scenes", search)
    monkeypatch.setattr(history, "estimate_acquisition", estimate)
    monkeypatch.setattr(history, "screen_scenes", screen)
    monkeypatch.setattr(history, "acquire_crops", crops)
    monkeypatch.setattr(history, "process_indices", indices)
    from aquaclima.modeling import seasonal
    from aquaclima.reporting import exploration

    monkeypatch.setattr(seasonal, "run_baseline", lambda *args: {})
    monkeypatch.setattr(exploration, "generate_exploration", lambda *args: {})

    def command(name, *extra):
        return main([name, "--config", str(config), "--data-dir", str(root), *map(str, extra)])

    def policy():
        return {"start": date(2022, 1, 1), "end": date(2022, 3, 31),
                "max_scenes_per_month": 2, "min_valid_fraction": 0.7}

    return SimpleNamespace(
        root=root, pivots=pivots, pilot=pilot, config=config, state=state, command=command,
        policy=policy, SourceHttp=SourceHttp, indices=indices,
    )


def test_history_dry_run_has_no_writes_or_source_requests(workflow, capsys):
    before = {path.relative_to(workflow.root): path.read_bytes() for path in workflow.root.rglob("*") if path.is_file()}
    assert workflow.command("history-run", "--dry-run") == 0
    assert json.loads(capsys.readouterr().out)["plan"]["status"] == "plan_required"
    after = {path.relative_to(workflow.root): path.read_bytes() for path in workflow.root.rglob("*") if path.is_file()}
    assert after == before
    assert not workflow.state.head and not workflow.state.searches


@pytest.mark.parametrize(
    "dates",
    [
        ("2025-01-01", "2025-03-31"),
        ("2021-12-01", "2022-02-28"),
        ("2022-01-02", "2022-03-31"),
        ("2022-01-01", "2022-04-30"),
    ],
)
def test_history_rejects_heldout_dates_and_ungated_expansion(workflow, dates):
    assert workflow.command("history-run", "--start", dates[0], "--end", dates[1]) == 1
    assert not workflow.state.head and not workflow.state.searches


def test_explicit_bulk_gate_allows_plan_preview(workflow, capsys):
    assert workflow.command(
        "history-run", "--start", "2022-01-01", "--end", "2022-12-31", "--allow-bulk", "--dry-run",
    ) == 0
    assert len(json.loads(capsys.readouterr().out)["plan"]["months"]) == 12
    assert not workflow.state.head and not workflow.state.searches


def test_monthly_scene_cap_and_online_offline_reproduction_preserve_pilot(workflow):
    original_pilot = workflow.pilot.read_bytes()
    assert workflow.command("history-plan") == 0
    assert len(workflow.state.searches) == 3
    assert all(call[2:] == (100, 500, True) for call in workflow.state.searches)
    assert workflow.command("history-run") == 0
    assert len(workflow.state.screens) == 3
    assert all(max_scenes == 2 for _, max_scenes, _ in workflow.state.screens)
    assert all(len(ids) == 2 for ids in workflow.state.crops)
    reports = list((workflow.root / "history/curated").glob("*/report.json"))
    assert len(reports) == 1
    output = reports[0].parent
    before = {name: (output / name).read_bytes() for name in ("monthly.csv", "observations.csv", "attempts.csv")}
    report = json.loads(reports[0].read_bytes())
    assert report["valid_observations"] == 6
    assert report["monthly_rows"] == 3
    workflow.state.offline = True
    assert workflow.command("history-run", "--offline") == 0
    assert before == {name: (output / name).read_bytes() for name in before}
    assert workflow.pilot.read_bytes() == original_pilot
    assert json.loads(reports[0].read_bytes())["requests"] == 0


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra"])
def test_plan_requires_exact_months_before_any_acquisition(workflow, mutation):
    assert workflow.command("history-plan") == 0
    policy = workflow.policy()
    plan_path = history._plan_path(workflow.root, policy, history.policy_key(policy, workflow.pivots))
    plan = json.loads(plan_path.read_bytes())
    if mutation == "missing":
        plan["months"].pop()
    elif mutation == "duplicate":
        plan["months"][1] = plan["months"][0]
    else:
        plan["months"].append(plan["months"][0] | {"month": "2025-01"})
    write_json(plan_path, plan)
    assert workflow.command("history-run") == 1
    assert not workflow.state.screens and not workflow.state.crops


def test_offline_recomputation_mismatch_keeps_original_indices(workflow, monkeypatch):
    assert workflow.command("history-plan") == 0
    assert workflow.command("history-run") == 0
    policy = workflow.policy()
    paths = history._paths(workflow.root, history.policy_key(policy, workflow.pivots), "2022-01")
    original = paths["indices"].read_bytes()

    def changed(*args, output_path, **kwargs):
        write_atomic(output_path, b"changed processing output\n")
        return output_path

    monkeypatch.setattr(history, "process_indices", changed)
    workflow.state.offline = True
    assert workflow.command("history-run", "--offline") == 1
    assert paths["indices"].read_bytes() == original


def test_plan_uses_full_catalog_after_interrupted_screening(workflow):
    assert workflow.command("history-plan") == 0
    policy = workflow.policy()
    key = history.policy_key(policy, workflow.pivots)
    selected = history._paths(workflow.root, key, "2022-01")["selected"]
    write_json(selected, {"screening": [], "screening_complete": False, "selected": []})
    workflow.state.estimates.clear()
    assert workflow.command("history-plan") == 0
    assert all(path.name == "catalog.json" for path in workflow.state.estimates)


def test_climate_failure_returns_incomplete_after_successful_spectral_batches(workflow, monkeypatch):
    assert workflow.command("history-plan") == 0
    real_download = history.download_precip

    def incomplete(http, root, months, *, manifest_path, provider="ucsb"):
        first = real_download(http, root, [months[0]], manifest_path=manifest_path, provider=provider)
        return first

    monkeypatch.setattr(history, "download_precip", incomplete)
    assert workflow.command("history-run") == 1
    report_path = next((workflow.root / "history/curated").glob("*/report.json"))
    report = json.loads(report_path.read_bytes())
    assert set(report["batch_status"].values()) == {"complete"}
    assert report["climate_month_status"]["2022-02"] == "not_acquired"


def test_interrupted_second_month_resumes_without_reacquiring_completed_month(workflow, monkeypatch):
    assert workflow.command("history-plan") == 0
    original_screen = history.screen_scenes

    def interrupted(http, pivots, catalog, root, **kwargs):
        if catalog.parent.name == "2022-02":
            raise BudgetError("SCL transfer allowance exhausted")
        return original_screen(http, pivots, catalog, root, **kwargs)

    monkeypatch.setattr(history, "screen_scenes", interrupted)
    assert workflow.command("history-run") == 1
    policy = workflow.policy()
    key = history.policy_key(policy, workflow.pivots)
    january = history._paths(workflow.root, key, "2022-01")
    original = january["indices"].read_bytes()
    assert json.loads(january["batch"].read_bytes())["status"] == "complete"
    assert not (workflow.root / "history/chirps.json").exists()
    monkeypatch.setattr(history, "screen_scenes", original_screen)
    assert workflow.command("history-run") == 0
    assert january["indices"].read_bytes() == original
    assert [catalog.parent.name for catalog, _, _ in workflow.state.screens].count("2022-01") == 1


def test_lowered_budget_rejects_plan_before_acquisition(workflow):
    assert workflow.command("history-plan") == 0
    prior_heads = list(workflow.state.head)
    workflow.config.write_text(
        workflow.config.read_text(encoding="utf-8").replace("max_transfer_bytes = 100000000", "max_transfer_bytes = 1000"),
        encoding="utf-8",
    )
    assert workflow.command("history-run") == 1
    assert not workflow.state.screens and not workflow.state.crops
    assert workflow.state.head == prior_heads


def test_missing_climate_budget_remains_required_when_spectral_batches_complete(workflow):
    assert workflow.command("history-plan") == 0
    assert workflow.command("history-run") == 0
    rain_manifest = json.loads((workflow.root / "history/chirps.json").read_bytes())
    (workflow.root / rain_manifest["months"]["2022-01"]["path"]).unlink()
    prior_heads = list(workflow.state.head)
    workflow.config.write_text(
        workflow.config.read_text(encoding="utf-8").replace("max_transfer_bytes = 100000000", "max_transfer_bytes = 1"),
        encoding="utf-8",
    )
    assert workflow.command("history-run") == 1
    assert workflow.state.head == prior_heads


def test_planning_stops_new_chirps_requests_after_persistent_rate_limit(workflow, monkeypatch):
    class RateLimitedHttp(workflow.SourceHttp):
        def head(self, url):
            workflow.state.head.append(url)
            raise AcquisitionError("HTTP 429 after retries", status_code=429)

    monkeypatch.setattr(history, "HttpClient", RateLimitedHttp)
    assert workflow.command("history-plan") == 0
    assert len(workflow.state.head) == 1
    assert len(workflow.state.searches) == 3
    plan = next((workflow.root / "history/plans").glob("*.json"))
    assert all(row["chirps"]["status"] == "unverified" for row in json.loads(plan.read_bytes())["months"])


@pytest.mark.parametrize("field", ["request", "candidate"])
def test_catalog_from_2025_is_rejected_even_with_updated_plan_checksum(workflow, field):
    assert workflow.command("history-plan") == 0
    policy = workflow.policy()
    plan_path = history._plan_path(workflow.root, policy, history.policy_key(policy, workflow.pivots))
    plan = json.loads(plan_path.read_bytes())
    entry = plan["months"][0]
    catalog_path = workflow.root / entry["catalog_path"]
    catalog = json.loads(catalog_path.read_bytes())
    if field == "request":
        catalog["request"]["datetime"] = "2025-01-01T00:00:00Z/2025-01-31T23:59:59.999999Z"
    else:
        catalog["candidates"][0]["properties"]["datetime"] = "2025-01-01T12:00:00Z"
    write_json(catalog_path, catalog)
    entry["catalog_sha256"] = checksum(catalog_path)
    write_json(plan_path, plan)
    assert workflow.command("history-run") == 1
    assert not workflow.state.screens and not workflow.state.crops


@pytest.mark.parametrize(
    ("field", "value"),
    [("schema_version", 2), ("max_scenes_per_month", 10), ("min_valid_fraction", 0.5)],
)
def test_incompatible_plan_schema_or_scientific_policy_is_rejected(workflow, field, value):
    assert workflow.command("history-plan") == 0
    policy = workflow.policy()
    plan_path = history._plan_path(workflow.root, policy, history.policy_key(policy, workflow.pivots))
    plan = json.loads(plan_path.read_bytes())
    plan[field] = value
    write_json(plan_path, plan)
    assert workflow.command("history-run") == 1
    assert not workflow.state.screens and not workflow.state.crops


def test_dry_run_applies_same_existing_plan_validation_without_writes(workflow):
    assert workflow.command("history-plan") == 0
    policy = workflow.policy()
    plan_path = history._plan_path(workflow.root, policy, history.policy_key(policy, workflow.pivots))
    plan = json.loads(plan_path.read_bytes())
    plan["schema_version"] = 2
    write_json(plan_path, plan)
    before = {path.relative_to(workflow.root): path.read_bytes() for path in workflow.root.rglob("*") if path.is_file()}
    heads = list(workflow.state.head)
    assert workflow.command("history-run", "--dry-run") == 1
    after = {path.relative_to(workflow.root): path.read_bytes() for path in workflow.root.rglob("*") if path.is_file()}
    assert after == before
    assert workflow.state.head == heads


def test_explicit_usgs_provider_reuses_spectral_batches_and_prior_ucsb_climate(workflow, monkeypatch):
    assert workflow.command("history-plan") == 0
    policy = workflow.policy()
    key = history.policy_key(policy, workflow.pivots)
    primary_plan = history._plan_path(workflow.root, policy, key)
    primary_plan_bytes = primary_plan.read_bytes()
    real_download = history.download_precip

    def first_month(http, root, months, *, manifest_path, provider="ucsb"):
        return real_download(http, root, [months[0]], manifest_path=manifest_path, provider=provider)

    monkeypatch.setattr(history, "download_precip", first_month)
    assert workflow.command("history-run") == 1
    original = json.loads((workflow.root / "history/chirps.json").read_bytes())["months"]["2022-01"]
    prior_screen_calls = list(workflow.state.screens)
    workflow.config.write_text(
        workflow.config.read_text(encoding="utf-8").replace(
            "max_scenes_per_month = 2", 'max_scenes_per_month = 2\nchirps_provider = "usgs"',
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(history, "download_precip", real_download)
    workflow.state.head.clear()
    assert workflow.command("history-plan") == 0
    mirror_plan = history._plan_path(workflow.root, policy | {"chirps_provider": "usgs"}, key)
    assert mirror_plan != primary_plan and mirror_plan.name.endswith("_usgs.json")
    assert primary_plan.read_bytes() == primary_plan_bytes
    mirror_document = json.loads(mirror_plan.read_bytes())
    write_json(mirror_plan, mirror_document | {"chirps_provider": "ucsb"})
    heads_before_rejection = list(workflow.state.head)
    assert workflow.command("history-run") == 1
    assert workflow.state.head == heads_before_rejection
    write_json(mirror_plan, mirror_document)
    assert workflow.command("history-run") == 0
    manifest = json.loads((workflow.root / "history/chirps.json").read_bytes())
    assert manifest["months"]["2022-01"] == original
    assert manifest["months"]["2022-02"]["source"] == usgs_url("2022-02")
    assert manifest["months"]["2022-03"]["source"] == usgs_url("2022-03")
    assert all(url.startswith("https://edcintl.cr.usgs.gov/") for url in workflow.state.head)
    assert workflow.state.screens == prior_screen_calls
    output = next((workflow.root / "history/curated").glob("*/monthly.csv")).parent
    datasets = {name: (output / name).read_bytes() for name in ("monthly.csv", "observations.csv", "attempts.csv")}
    workflow.state.offline = True
    assert workflow.command("history-run", "--offline") == 0
    assert datasets == {name: (output / name).read_bytes() for name in datasets}
