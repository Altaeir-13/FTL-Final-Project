import json
import os

import pandas as pd
import pytest

from aquaclima.features.historical import build_dataset
from aquaclima.reporting.exploration import _changes, generate_exploration
from aquaclima.storage.http import checksum, write_json


@pytest.fixture
def inventory(tmp_path):
    pivots = tmp_path / "data" / "processed" / "pivots.geojson"
    write_json(pivots, {"type": "FeatureCollection", "features": [
        {"properties": {"pivot_id": str(value), "area_ha": 30.0 + value}} for value in (1, 2)
    ]})
    return pivots


def batch(inventory, month, rows=None, *, status="complete", selected=None):
    root = inventory.parent.parent
    directory = root / "history" / "batches" / "policy" / month
    directory.mkdir(parents=True, exist_ok=True)
    document = {
        "month": month, "status": status, "query_complete": status == "complete",
        "data_root": os.path.relpath(root, directory), "pivots_sha256": checksum(inventory),
        "catalog_candidate_count": 6, "selected_scene_ids": selected or [],
    }
    if rows is not None:
        table = directory / "indices.csv"
        pd.DataFrame(rows).to_csv(table, index=False)
        document.update(indices_path=table.relative_to(root).as_posix(), indices_sha256=checksum(table))
    manifest = directory / "batch.json"
    write_json(manifest, document)
    return manifest


def row(pivot, scene, day, ndvi, ndmi, *, status="ok", quality=90):
    return {"pivot_id": str(pivot), "scene_id": scene, "date": day, "status": status,
            "ndvi_median": ndvi, "ndmi_median": ndmi, "valid_pixel_pct": quality}


def test_monthly_equal_scene_weights_missing_slots_and_rejected_attempts(inventory, tmp_path):
    rows = [
        row(1, "A", "2022-01-04", 0.4, 0.2, quality=75),
        row(1, "B", "2022-01-24", 0.8, 0.6, quality=100),
        row(1, "C", "2022-01-14", None, None, status="insufficient_valid_pixels", quality=20),
        row(2, "A", "2022-01-04", None, None, status="insufficient_valid_pixels", quality=0),
        row(2, "B", "2022-01-24", 0.5, 0.1),
        row(2, "C", "2022-01-14", None, None, status="insufficient_valid_pixels", quality=10),
    ]
    january = batch(inventory, "2022-01", rows, selected=["A", "B", "C"])
    february = batch(inventory, "2022-02", selected=[])
    rain_path = tmp_path / "rain.csv"
    pd.DataFrame([{"pivot_id": "1", "month": "2022-01", "precip_mm": 125,
                   "precip_status": "ok", "chirps_source": "controlled test"}]).to_csv(rain_path, index=False)
    paths = build_dataset(inventory, [january, february], rain_path, ["2022-01", "2022-02", "2022-03"], tmp_path / "out")
    monthly = pd.read_csv(paths["monthly"], dtype={"pivot_id": str})
    assert len(pd.read_csv(paths["attempts"])) == 6
    assert len(pd.read_csv(paths["observations"])) == 3
    assert len(monthly) == 6
    jan = monthly.loc[monthly["pivot_id"].eq("1") & monthly["month"].eq("2022-01")].iloc[0]
    assert jan["ndvi_median"] == pytest.approx(0.6)
    assert jan["ndmi_median"] == pytest.approx(0.4)
    assert jan["n_accepted_scenes"] == 2
    assert jan["n_attempted_scenes"] == 3
    assert jan["valid_pixel_pct_median"] == 87.5
    assert jan["valid_pixel_pct_min"] == 75
    assert jan["observation_day_span"] == 20
    assert json.loads(jan["accepted_scene_ids"]) == ["A", "B"]
    assert jan["precip_mm"] == 125
    assert monthly.loc[monthly["month"].eq("2022-02"), "monthly_status"].eq("no_accepted_observation").all()
    missing = monthly.loc[monthly["month"].eq("2022-03")]
    assert missing["monthly_status"].eq("not_queried").all()
    assert missing["ndvi_median"].isna().all()
    assert missing["n_accepted_scenes"].eq(0).all()
    assert missing["precip_status"].eq("no_monthly_data").all()
    repeated = build_dataset(inventory, [january, february], rain_path,
                             ["2022-01", "2022-02", "2022-03"], tmp_path / "repeat")
    assert paths["monthly"].read_bytes() == repeated["monthly"].read_bytes()


def test_partial_batch_retains_accepted_observations_and_completion_state(inventory, tmp_path):
    manifest = batch(inventory, "2022-01", [row(1, "A", "2022-01-01", 0.5, 0.1)],
                     status="partial", selected=["A"])
    paths = build_dataset(inventory, [manifest], None, ["2022-01"], tmp_path / "out")
    monthly = pd.read_csv(paths["monthly"])
    assert monthly["batch_status"].eq("partial").all()
    assert not monthly["query_complete"].any()
    assert sorted(monthly["monthly_status"].tolist()) == ["incomplete_batch", "ok"]


def test_queried_in_progress_batch_keeps_zero_observations(inventory, tmp_path):
    manifest = batch(inventory, "2022-01", status="in_progress")
    document = json.loads(manifest.read_bytes())
    document["query_complete"] = True
    write_json(manifest, document)
    paths = build_dataset(inventory, [manifest], None, ["2022-01"], tmp_path / "out")
    monthly = pd.read_csv(paths["monthly"])
    assert monthly["query_complete"].all()
    assert monthly["monthly_status"].eq("incomplete_batch").all()
    assert monthly["n_accepted_scenes"].eq(0).all()


@pytest.mark.parametrize("problem", ["checksum", "pivot_hash", "wrong_month", "duplicate", "missing_pair", "bad_index"])
def test_invalid_batch_evidence_is_rejected(inventory, tmp_path, problem):
    rows = [row(pivot, "A", "2022-01-04", 0.5, 0.1) for pivot in (1, 2)]
    if problem == "wrong_month":
        rows[0]["date"] = "2022-02-04"
    elif problem == "duplicate":
        rows[1] = rows[0]
    elif problem == "missing_pair":
        rows.pop()
    elif problem == "bad_index":
        rows[0]["ndmi_median"] = float("inf")
    manifest = batch(inventory, "2022-01", rows, selected=["A"])
    if problem in {"checksum", "pivot_hash"}:
        document = json.loads(manifest.read_bytes())
        document["indices_sha256" if problem == "checksum" else "pivots_sha256"] = "broken"
        write_json(manifest, document)
    with pytest.raises(ValueError):
        build_dataset(inventory, [manifest], None, ["2022-01"], tmp_path / "out")


def test_explicit_month_selection_rejects_duplicate_policies(inventory, tmp_path):
    manifest = batch(inventory, "2022-01", selected=[])
    with pytest.raises(ValueError, match="um manifesto"):
        build_dataset(inventory, [manifest, manifest], None, ["2022-01"], tmp_path / "out")


def test_empty_history_keeps_every_requested_pivot_month(inventory, tmp_path):
    paths = build_dataset(inventory, [], None, ["2022-01", "2022-02"], tmp_path / "out")
    monthly = pd.read_csv(paths["monthly"])
    assert len(monthly) == 4 and monthly["monthly_status"].eq("not_queried").all()
    assert pd.read_csv(paths["observations"]).empty
    assert pd.read_csv(paths["attempts"]).empty


def test_descriptive_changes_record_unobserved_calendar_gap():
    rows = pd.DataFrame([
        {"pivot_id": "1", "month": "2022-01", "ndvi_median": 0.8, "ndmi_median": 0.5,
         "monthly_status": "ok", "batch_status": "complete", "n_accepted_scenes": 2},
        {"pivot_id": "1", "month": "2022-02", "ndvi_median": None, "ndmi_median": None,
         "monthly_status": "no_accepted_observation", "batch_status": "complete", "n_accepted_scenes": 0},
        {"pivot_id": "1", "month": "2022-03", "ndvi_median": 0.3, "ndmi_median": 0.2,
         "monthly_status": "ok", "batch_status": "complete", "n_accepted_scenes": 1},
    ])
    changes = _changes(rows)
    assert len(changes) == 2
    assert changes["unobserved_months_between"].eq(1).all()
    assert not changes["consecutive_calendar_months"].any()


def test_exploration_reports_absence_and_calendar_coverage(inventory, tmp_path):
    paths = build_dataset(inventory, [], None, ["2022-01", "2022-02"], tmp_path / "data-out")
    artifacts = generate_exploration(paths["monthly"], paths["observations"], tmp_path / "figures")
    coverage = pd.read_csv(artifacts["seasonal_coverage"])
    assert coverage["expected_pivot_months"].eq(2).all()
    assert coverage["observed_pivot_months"].eq(0).all()
    assert len(pd.read_csv(artifacts["low_quality"])) == 4
    report = json.loads(artifacts["report"].read_bytes())
    assert report["accepted_scene_observations"] == 0
    assert report["monthly_coverage_fraction"] == 0
    assert report["low_quality_pixel_pct_threshold_analyst_parameter"] == 80
    assert all(path.is_file() and path.stat().st_size > 0 for path in artifacts.values())
