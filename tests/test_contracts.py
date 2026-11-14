import json
from pathlib import Path
import shutil

import pandas as pd
import pytest

from aquaclima.modeling.naive_seasonal import run_naive_benchmark
from aquaclima.modeling.seasonal import run_baseline
from aquaclima.reporting.contracts import export_contracts
from aquaclima.storage.http import checksum, write_json


@pytest.fixture
def dataset(tmp_path):
    directory = tmp_path / "input"
    directory.mkdir()
    pivots = directory / "pivots.geojson"
    write_json(pivots, {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {
        "type": "Polygon", "coordinates": [[[-47.1, -17.1], [-47.0, -17.1], [-47.0, -17.0], [-47.1, -17.1]]]},
        "properties": {"pivot_id": "001", "FID": 1, "area_ha": 30.0}}]})
    observations = pd.DataFrame([
        {"pivot_id": "001", "month": "2024-01", "date": "2024-01-03", "scene_id": "A", "status": "ok",
         "ndvi_median": 0.5, "ndmi_median": 0.1, "valid_pixel_pct": 90.0},
        {"pivot_id": "001", "month": "2024-03", "date": "2024-03-04", "scene_id": "B", "status": "ok",
         "ndvi_median": 0.6, "ndmi_median": 0.2, "valid_pixel_pct": 80.0},
        {"pivot_id": "001", "month": "2024-03", "date": "2024-03-24", "scene_id": "C", "status": "ok",
         "ndvi_median": 0.8, "ndmi_median": 0.4, "valid_pixel_pct": 90.0},
    ])
    observations.to_csv(directory / "observations.csv", index=False)
    monthly = pd.DataFrame([
        {"pivot_id": "001", "month": "2024-01", "ndvi_median": 0.5, "ndmi_median": 0.1,
         "n_accepted_scenes": 1, "valid_pixel_pct_min": 90, "valid_pixel_pct_median": 90, "monthly_status": "ok"},
        {"pivot_id": "001", "month": "2024-02", "ndvi_median": None, "ndmi_median": None,
         "n_accepted_scenes": 0, "valid_pixel_pct_min": None, "valid_pixel_pct_median": None,
         "monthly_status": "no_accepted_observation"},
        {"pivot_id": "001", "month": "2024-03", "ndvi_median": 0.7, "ndmi_median": 0.3,
         "n_accepted_scenes": 2, "valid_pixel_pct_min": 80, "valid_pixel_pct_median": 85, "monthly_status": "ok"},
    ]).assign(batch_status="complete", query_complete=True, n_attempted_scenes=lambda f: f.n_accepted_scenes,
        precip_mm=120.0, precip_status="ok", chirps_source="controlled_unit_test",
        temporal_aggregation="median_of_scene_medians_equal_weight")
    monthly.to_csv(directory / "monthly.csv", index=False)
    return pivots, directory


def read_package(manifest_path, name):
    manifest = json.loads(manifest_path.read_bytes())
    path = manifest_path.parent / manifest["files"][name]["path"]
    return path


def test_versioned_atomic_package_hashes_counts_schema_and_idempotence(dataset, tmp_path):
    pivots, directory = dataset
    output = tmp_path / "contracts"
    manifest_path = export_contracts(pivots, directory, output)
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest["contract_version"] == "1.0.0"
    assert manifest["crs"] == "EPSG:4326"
    assert manifest["coordinate_order"] == ["longitude", "latitude"]
    assert manifest["files"]["observations"]["rows"] == 3
    assert manifest["files"]["monthly"]["rows"] == 3
    for entry in manifest["files"].values():
        relative = Path(entry["path"])
        assert not relative.is_absolute() and ".." not in relative.parts
        path = output / relative
        assert path.stat().st_size == entry["bytes"]
        assert checksum(path) == entry["sha256"]
    monthly = pd.read_csv(read_package(manifest_path, "monthly"), dtype={"pivot_id": str})
    assert monthly.pivot_id.eq("001").all()
    assert "true" in read_package(manifest_path, "monthly").read_text()
    schema = json.loads(read_package(manifest_path, "schemas").read_bytes())
    assert schema["$defs"]["monthly"]["x-primary-key"] == ["pivot_id", "month"]
    provenance = json.loads(read_package(manifest_path, "provenance").read_bytes())
    assert provenance["experiment_availability"] == {"seasonal_original": "not_requested", "naive_contingency": "not_requested"}
    assert pd.read_csv(read_package(manifest_path, "models")).empty
    assert pd.read_csv(read_package(manifest_path, "events")).empty
    before = {path: path.stat().st_mtime_ns for path in output.rglob("*") if path.is_file()}
    assert export_contracts(pivots, directory, output) == manifest_path
    assert before == {path: path.stat().st_mtime_ns for path in output.rglob("*") if path.is_file()}


def test_missing_or_insufficient_models_are_explicit_and_supported(dataset, tmp_path):
    pivots, directory = dataset
    baseline = tmp_path / "baseline"
    benchmark = tmp_path / "benchmark"
    run_baseline(directory / "monthly.csv", baseline)
    run_naive_benchmark(directory / "monthly.csv", benchmark)
    manifest = export_contracts(pivots, directory, tmp_path / "contracts", model_dir=baseline, benchmark_dir=benchmark)
    provenance = json.loads(read_package(manifest, "provenance").read_bytes())
    assert provenance["experiment_availability"] == {"seasonal_original": "insufficient_data", "naive_contingency": "no_valid_pairs"}
    models = pd.read_csv(read_package(manifest, "models"))
    assert len(models) == 6 and models.mae.isna().all()
    assert models.n_valid_pairs.eq(0).all()
    predictions = pd.read_csv(read_package(manifest, "model_predictions"))
    assert len(predictions) == 36
    assert predictions["month"].str.startswith("2024-").all()
    assert predictions["experiment"].nunique() == 2
    parameters = json.loads(read_package(manifest, "model_parameters").read_bytes())
    assert parameters["seasonal_original"]["training_years"] == [2022, 2023]


def test_old_manifest_stays_consistent_when_changed_input_is_rejected(dataset, tmp_path):
    pivots, directory = dataset
    output = tmp_path / "out"
    manifest = export_contracts(pivots, directory, output)
    previous = manifest.read_bytes()
    monthly = pd.read_csv(directory / "monthly.csv", dtype={"pivot_id": str})
    monthly.loc[0, "ndvi_median"] = 0.9
    monthly.to_csv(directory / "monthly.csv", index=False)
    with pytest.raises(ValueError, match="Agregação mensal divergente"):
        export_contracts(pivots, directory, output)
    assert manifest.read_bytes() == previous


def test_metrics_from_other_dataset_are_rejected(dataset, tmp_path):
    pivots, directory = dataset
    benchmark = tmp_path / "benchmark"
    result = run_naive_benchmark(directory / "monthly.csv", benchmark)
    report = json.loads(result["report"].read_bytes())
    report["monthly_input_sha256"] = "different_dataset"
    write_json(result["report"], report)
    with pytest.raises(ValueError, match="outro conjunto mensal"):
        export_contracts(pivots, directory, tmp_path / "out", benchmark_dir=benchmark)


@pytest.mark.parametrize("problem", ["unknown_pivot", "duplicate_month", "wrong_crs", "bad_query_boolean"])
def test_contract_invalid_inputs_fail_before_publication(dataset, tmp_path, problem):
    pivots, directory = dataset
    monthly = pd.read_csv(directory / "monthly.csv", dtype={"pivot_id": str})
    if problem == "unknown_pivot":
        monthly.loc[0, "pivot_id"] = "999"
    elif problem == "duplicate_month":
        monthly = pd.concat([monthly, monthly.iloc[[0]]])
    elif problem == "bad_query_boolean":
        monthly["query_complete"] = "unknown"
    else:
        document = json.loads(pivots.read_bytes())
        document["crs"] = {"properties": {"name": "EPSG:3857"}}
        write_json(pivots, document)
    monthly.to_csv(directory / "monthly.csv", index=False)
    output = tmp_path / "contracts"
    with pytest.raises(ValueError):
        export_contracts(pivots, directory, output)
    assert not (output / "manifest.json").exists()


def test_contract_rejects_silently_omitted_month(dataset, tmp_path):
    pivots, directory = dataset
    path = directory / "monthly.csv"
    table = pd.read_csv(path, dtype={"pivot_id": str})
    table.loc[table.month.ne("2024-02")].to_csv(path, index=False)
    with pytest.raises(ValueError, match="meses consecutivos"):
        export_contracts(pivots, directory, tmp_path / "out")


@pytest.mark.parametrize("problem", ["event_values", "event_gap", "quality"])
def test_contract_validates_quality_and_event_consistency(dataset, tmp_path, problem):
    pivots, directory = dataset
    if problem == "quality":
        path = directory / "observations.csv"
        table = pd.read_csv(path, dtype={"pivot_id": str})
        table.loc[0, "valid_pixel_pct"] = 110
        table.to_csv(path, index=False)
    else:
        event = {"pivot_id": "001", "index": "ndvi_median", "from_month": "2024-01",
                 "to_month": "2024-03", "from_value": 0.5, "to_value": 0.7, "change": 0.2,
                 "absolute_change_threshold": 0.15, "elapsed_calendar_months": 2,
                 "unobserved_months_between": 1, "consecutive_calendar_months": False}
        event["change" if problem == "event_values" else "elapsed_calendar_months"] = 9
        pd.DataFrame([event]).to_csv(directory / "pronounced_changes.csv", index=False)
    with pytest.raises(ValueError, match="qualidade inválido|Evento espectral incompatível"):
        export_contracts(pivots, directory, tmp_path / "out")


def test_contract_preserves_valid_gap_event(dataset, tmp_path):
    pivots, directory = dataset
    pd.DataFrame([{"pivot_id": "001", "index": "ndvi_median", "from_month": "2024-01",
                  "to_month": "2024-03", "from_value": 0.5, "to_value": 0.7, "change": 0.2,
                  "absolute_change_threshold": 0.15, "elapsed_calendar_months": 2,
                  "unobserved_months_between": 1, "consecutive_calendar_months": False}]).to_csv(
                      directory / "pronounced_changes.csv", index=False)
    manifest = export_contracts(pivots, directory, tmp_path / "out")
    events = pd.read_csv(read_package(manifest, "events"))
    assert len(events) == 1 and events.iloc[0].unobserved_months_between == 1
    assert not bool(events.iloc[0].consecutive_calendar_months)


def test_versioned_dataset_package_is_independent_of_output_directory(dataset, tmp_path):
    pivots, directory = dataset
    write_json(directory / "dataset_manifest.json", {"dataset_version": "recovery_v1", "files": {
        name: {"path": f"{name}.csv", "sha256": checksum(directory / f"{name}.csv")}
        for name in ("observations", "monthly")}})
    copied = tmp_path / "different_folder_name"
    shutil.copytree(directory, copied)
    first = export_contracts(pivots, directory, tmp_path / "first")
    second = export_contracts(pivots, copied, tmp_path / "second")
    assert first.read_bytes() == second.read_bytes()
    assert read_package(first, "provenance").read_bytes() == read_package(second, "provenance").read_bytes()
    assert json.loads(read_package(first, "provenance").read_bytes())["dataset_name"] == "recovery_v1"


def test_versioned_dataset_manifest_must_match_exported_inputs(dataset, tmp_path):
    pivots, directory = dataset
    write_json(directory / "dataset_manifest.json", {"dataset_version": "recovery_v1", "files": {
        name: {"sha256": "modified"} for name in ("observations", "monthly")}})
    with pytest.raises(ValueError, match="manifesto do dataset diverge"):
        export_contracts(pivots, directory, tmp_path / "out")


def test_processing_baseline_version_is_preserved_as_text(dataset, tmp_path):
    pivots, directory = dataset
    path = directory / "observations.csv"
    frame = pd.read_csv(path, dtype={"pivot_id": str})
    frame["processing_baseline"] = ["03.00", "04.00", "05.10"]
    frame.to_csv(path, index=False)
    manifest = export_contracts(pivots, directory, tmp_path / "out")
    exported = pd.read_csv(read_package(manifest, "observations"), dtype={"processing_baseline": str})
    assert exported.processing_baseline.tolist() == ["03.00", "04.00", "05.10"]
    schema = json.loads(read_package(manifest, "schemas").read_bytes())
    assert schema["$defs"]["observations"]["properties"]["processing_baseline"]["type"] == "string"
