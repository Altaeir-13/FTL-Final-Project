"""Recovery contracts exercise local persistence without remote requests."""

import json
import os
import calendar
from types import SimpleNamespace

import pandas as pd
import pytest
import requests
from shapely.geometry import box, mapping

from aquaclima import recovery
from aquaclima.features.historical import build_dataset
from aquaclima.storage.http import HttpClient, checksum, write_atomic, write_json


def scene(name, day, baseline="05.10"):
    observed = day.replace("-", "") + "T132241"
    return {"id": name, "collection": "sentinel-2-l2a", "properties": {
        "datetime": day + "T13:22:41Z", "s2:processing_baseline": baseline,
        "s2:product_uri": f"S2A_MSIL2A_{observed}_N{baseline.replace('.', '')}_R038_T23KKA_20240601T152534.SAFE"}}


def rows(name, day, *, second_ok=False):
    return [{"pivot_id": str(number), "date": day, "scene_id": name,
             "status": "ok" if number == 1 or second_ok else "insufficient_valid_pixels",
             "ndvi_median": 0.7 if number == 1 or second_ok else None,
             "ndmi_median": 0.3 if number == 1 or second_ok else None,
             "valid_pixel_pct": 95 if number == 1 or second_ok else 15,
             "sentinel_source": f"https://example.invalid/items/{name}"} for number in (1, 2)]


@pytest.fixture
def recovery_case(tmp_path, monkeypatch):
    monkeypatch.setattr(requests.Session, "request", lambda *a, **k: pytest.fail("Unexpected network request"))
    # Raster mathematics and COG integrity are exercised by source tests. Here,
    # deterministic controlled rows isolate orchestration/immutable artifacts.
    def regenerate(pivots, crops, root, *, output_path, **kwargs):
        pd.DataFrame(json.loads(crops.read_bytes())["controlled_fixture_rows"]).to_csv(output_path, index=False)
        return output_path
    monkeypatch.setattr("aquaclima.processing.indices.process_indices", regenerate)
    root = tmp_path / "data"
    pivots = root / "processed/pivots.geojson"
    write_json(pivots, {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"pivot_id": str(number), "area_ha": 50 + number},
         "geometry": mapping(box(-47.13 + number / 1000, -17.53, -47.129 + number / 1000, -17.529))}
        for number in (1, 2)]})
    policy = {"months": ["2022-01"], "max_scenes_per_month": 2, "min_valid_fraction": 0.70,
              "original_dataset": "history/curated/original", "c1_policy_key": "original_policy",
              "compatibility_audit": "recovery/compatibility.json", "dataset_version": "recovered_v1"}
    batches = []
    for month in ("2022-01", "2022-02"):
        folder = root / "history/batches/original_policy" / month
        native = scene("C1_FEB", "2022-02-08")
        native["collection"] = "sentinel-2-c1-l2a"
        selected = [native] if month == "2022-02" else []
        write_json(folder / "selected.json", {"selected": selected})
        document = {"month": month, "status": "complete", "query_complete": True,
            "data_root": os.path.relpath(root, folder), "pivots_sha256": checksum(pivots),
            "catalog_candidate_count": len(selected), "selected_scene_ids": [item["id"] for item in selected]}
        if selected:
            path = folder / "indices.csv"
            pd.DataFrame(rows("C1_FEB", "2022-02-08")).to_csv(path, index=False)
            document.update(indices_path=path.relative_to(root).as_posix(), indices_sha256=checksum(path))
        write_json(folder / "batch.json", document)
        batches.append(folder / "batch.json")
    precip = root / "rain.csv"
    pd.DataFrame([{"pivot_id": str(number), "month": month, "precip_mm": 30.0,
                   "precip_status": "ok", "chirps_source": "controlled fixture"}
                  for number in (1, 2) for month in ("2022-01", "2022-02")]).to_csv(precip, index=False)
    original = root / policy["original_dataset"]
    build_dataset(pivots, batches, precip, ["2022-01", "2022-02"], original)
    write_atomic(root / "curated/pilot.csv", b"original pilot artifact\n")
    proof = root / "recovery/proof.json"
    write_json(proof, {"fixture": "validated evidence"})
    write_json(root / policy["compatibility_audit"], {"status": "compatible", "adapter_version": 1,
        "checks": [{"path": proof.relative_to(root).as_posix(), "sha256": checksum(proof)}]})
    recovery.preserve_original(root, policy)
    return root, policy


def recovery_batch(root, policy, month="2022-01", name="PC_JAN", day="2022-01-04", *, second_ok=False):
    paths = recovery._paths(root, recovery._key(root, policy), month)
    native = scene(name, day)
    year, number = map(int, month.split("-"))
    write_json(paths["catalog"], {"collection": "sentinel-2-l2a", "query_complete": True,
        "candidate_count": 1, "candidates": [native],
        "request": {"collections": ["sentinel-2-l2a"],
                    "datetime": f"{month}-01T00:00:00Z/{month}-{calendar.monthrange(year, number)[1]}T23:59:59.999999Z"},
        "parameters": {"pivots_sha256": checksum(root / "processed/pivots.geojson")}})
    write_json(paths["normalized"], {"candidates": [native]})
    write_json(paths["selected"], {"selected": [native], "selected_ids": [name], "screening_complete": True})
    calibration = root / "recovery/native.xml"
    write_atomic(calibration, b"<native-metadata/>")
    write_json(paths["crops"], {"collection": "sentinel-2-l2a", "controlled_fixture_rows": rows(name, day, second_ok=second_ok), "scenes": [{
        "id": name, "native_item_id": name, "acquisition_key": recovery.acquisition_key(native), "status": "ok",
        "radiometric_calibration": {"xml_path": calibration.relative_to(root).as_posix(), "xml_sha256": checksum(calibration)}}]})
    pd.DataFrame(rows(name, day, second_ok=second_ok)).to_csv(paths["indices"], index=False)
    batch = {"month": month, "status": "complete", "query_complete": True,
        "data_root": os.path.relpath(root, paths["batch"].parent), "pivots_sha256": checksum(root / "processed/pivots.geojson"),
        "catalog_candidate_count": 1, "selected_scene_ids": [name],
        "compatibility_sha256": recovery.verify_compatibility(root, policy)}
    for field in ("selected", "crops", "indices", "normalized"):
        batch[f"{field}_path"] = paths[field].relative_to(root).as_posix()
        batch[f"{field}_sha256"] = checksum(paths[field])
    write_json(paths["batch"], batch)
    return paths


def test_original_snapshot_detects_changes_and_removed_files(recovery_case):
    root, policy = recovery_case
    original = root / policy["original_dataset"] / "monthly.csv"
    original.write_bytes(original.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="modificados"):
        recovery.preserve_original(root, policy)


@pytest.mark.parametrize("change", ["status", "version", "proof", "path"])
def test_compatibility_gate_requires_verified_evidence(recovery_case, change):
    root, policy = recovery_case
    path = root / policy["compatibility_audit"]
    document = json.loads(path.read_bytes())
    if change == "status": document["status"] = "pending"
    if change == "version": document["adapter_version"] = 2
    if change == "proof": document["checks"][0]["sha256"] = "wrong"
    if change == "path": document["checks"][0]["path"] = "../../outside.json"
    write_json(path, document)
    with pytest.raises((ValueError, FileNotFoundError)):
        recovery.verify_compatibility(root, policy)


def test_consolidation_keeps_missing_pivot_months_and_preserves_original(recovery_case):
    root, policy = recovery_case
    recovery_batch(root, policy)
    before = recovery._original_hashes(root, policy)
    files = recovery.consolidate(root, policy, root / "recovery/curated/new")
    monthly = pd.read_csv(files["monthly"], dtype={"pivot_id": str})
    assert len(monthly) == 4
    assert len(pd.read_csv(files["observations"])) == 2
    january = monthly.loc[monthly["month"].eq("2022-01")].set_index("pivot_id")
    assert january.loc["1", "monthly_status"] == "ok"
    assert january.loc["2", "monthly_status"] == "no_accepted_observation"
    assert pd.isna(january.loc["2", "ndvi_median"])
    assert monthly["precip_mm"].eq(30).all()
    assert recovery._original_hashes(root, policy) == before
    repeated = recovery.consolidate(root, policy, root / "recovery/curated/repeated")
    for key in files:
        assert files[key].read_bytes() == repeated[key].read_bytes()


def test_equivalent_acquisitions_prefer_accepted_c1_then_accepted_pc(recovery_case):
    root, policy = recovery_case
    policy["months"] = ["2022-02"]
    recovery_batch(root, policy, "2022-02", "PC_EQUIVALENT", "2022-02-08", second_ok=True)
    files = recovery.consolidate(root, policy, root / "recovery/curated/new")
    observations = pd.read_csv(files["observations"], dtype={"pivot_id": str}).set_index("pivot_id")
    assert len(observations) == 2
    assert observations.loc["1", "scene_id"] == "C1_FEB"
    assert observations.loc["2", "scene_id"] == "PC_EQUIVALENT"
    assert len(pd.read_csv(files["duplicate_exclusions"])) == 2


@pytest.mark.parametrize("nested", [False, True])
def test_consolidation_cannot_write_into_original_tree(recovery_case, nested):
    root, policy = recovery_case
    recovery_batch(root, policy)
    original = root / policy["original_dataset"]
    before = recovery._original_hashes(root, policy)
    with pytest.raises(ValueError):
        recovery.consolidate(root, policy, original / "nested" if nested else original)
    assert recovery._original_hashes(root, policy) == before


def test_consolidation_audit_rejection_has_no_output_side_effect(recovery_case):
    root, policy = recovery_case
    recovery_batch(root, policy)
    write_json(root / policy["compatibility_audit"], {"status": "rejected"})
    output = root / "recovery/curated/rejected"
    with pytest.raises(ValueError):
        recovery.consolidate(root, policy, output)
    assert not output.exists()


def test_offline_batch_recomputes_indices_and_repairs_missing_file(recovery_case, monkeypatch):
    root, policy = recovery_case
    paths = recovery_batch(root, policy)
    expected = paths["indices"].read_bytes()
    paths["indices"].unlink()
    def regenerate(*args, output_path, **kwargs):
        write_atomic(output_path, expected)
        return output_path
    monkeypatch.setattr("aquaclima.processing.indices.process_indices", regenerate)
    recovery._process_month(root, policy, "2022-01")
    assert paths["indices"].read_bytes() == expected


def test_offline_batch_rejects_modified_manifests_and_changed_math(recovery_case, monkeypatch):
    root, policy = recovery_case
    paths = recovery_batch(root, policy)
    before = paths["indices"].read_bytes()
    def changed(*args, output_path, **kwargs):
        write_atomic(output_path, b"different computed values")
        return output_path
    monkeypatch.setattr("aquaclima.processing.indices.process_indices", changed)
    with pytest.raises(ValueError, match="diferem"):
        recovery._process_month(root, policy, "2022-01")
    assert paths["indices"].read_bytes() == before
    write_json(paths["selected"], {"altered": True})
    with pytest.raises(ValueError, match="alterado"):
        recovery._process_month(root, policy, "2022-01")


def test_offline_missing_batch_is_explicit(recovery_case):
    root, policy = recovery_case
    with pytest.raises(ValueError, match="ausente/incompleto"):
        recovery._process_month(root, policy, "2022-01")


@pytest.fixture
def planned(recovery_case, monkeypatch):
    root, policy = recovery_case
    recovery_batch(root, policy)
    monkeypatch.setattr(recovery, "search_pc", lambda *args, output_path, **kwargs: output_path)
    with HttpClient(ledger=root / "recovery/acquisition.jsonl") as http:
        path = recovery.make_plan(http, root, policy, {"max_transfer_bytes": 100_000_000,
            "max_storage_bytes": 100_000_000, "max_downloads": 1000})
    return root, policy, path


def test_existing_complete_month_plans_no_new_transfer(planned):
    root, policy, path = planned
    plan = recovery.load_plan(root, policy)
    assert plan["estimated_transfer_bytes"] == 0
    assert plan["months"][0]["already_complete"]
    assert plan["months"][0]["products"] == plan["months"][0]["acquisitions"] == 1


@pytest.mark.parametrize("problem", ["months", "pivots", "selection", "estimate", "catalog_checksum"])
def test_plan_mismatches_are_rejected(planned, problem):
    root, policy, path = planned
    plan = json.loads(path.read_bytes())
    if problem == "months": plan["months"][0]["month"] = "2022-07"
    if problem == "pivots": plan["pivots_sha256"] = "wrong"
    if problem == "selection": plan["max_scenes_per_month"] = 3
    if problem == "estimate": plan["months"][0]["estimated_transfer_bytes"] = -1
    if problem == "catalog_checksum": plan["months"][0]["catalog_sha256"] = "wrong"
    write_json(path, plan)
    with pytest.raises(ValueError):
        recovery.load_plan(root, policy)


@pytest.mark.parametrize("problem", ["pivot_hash", "count", "duplicate", "collection", "outside_month", "interval", "request_collection"])
def test_semantically_invalid_catalog_is_rejected_even_with_matching_hash(planned, problem):
    root, policy, path = planned
    plan = json.loads(path.read_bytes())
    catalog_path = root / plan["months"][0]["catalog_path"]
    catalog = json.loads(catalog_path.read_bytes())
    if problem == "pivot_hash": catalog["parameters"]["pivots_sha256"] = "wrong"
    if problem == "count": catalog["candidate_count"] = 99
    if problem == "duplicate": catalog["candidates"] *= 2; catalog["candidate_count"] = 2
    if problem == "collection": catalog["candidates"][0]["collection"] = "sentinel-2-c1-l2a"
    if problem == "outside_month": catalog["candidates"][0]["properties"]["datetime"] = "2022-07-04T13:22:41Z"
    if problem == "interval": catalog["request"]["datetime"] = "2022-01-04T00:00:00Z/2022-01-05T23:59:59Z"
    if problem == "request_collection": catalog["request"]["collections"] = ["wrong"]
    write_json(catalog_path, catalog)
    plan["months"][0]["catalog_sha256"] = checksum(catalog_path)
    write_json(path, plan)
    with pytest.raises(ValueError, match="incompleto"):
        recovery.load_plan(root, policy)


def test_expansion_requires_explicit_bulk_and_preserves_quality_threshold(tmp_path):
    config = tmp_path / "recovery.toml"
    config.write_text('[recovery]\nmonths=["2022-01","2022-02","2022-03"]\n'
        'max_scenes_per_month=2\nmin_valid_fraction=0.70\noriginal_dataset="original"\n'
        'compatibility_audit="audit.json"\n[limits]\nmax_transfer_bytes=250000000\n'
        'max_storage_bytes=250000000\nmax_downloads=1000\n', encoding="utf-8")
    args = SimpleNamespace(config=config, data_dir=tmp_path, start=None, end=None, allow_bulk=False)
    with pytest.raises(ValueError, match="allow-bulk"):
        recovery.settings(args)
    args.allow_bulk = True
    policy, limits = recovery.settings(args)
    assert len(policy["months"]) == 3 and policy["min_valid_fraction"] == 0.70
    config.write_text(config.read_text().replace("0.70", "0.50"), encoding="utf-8")
    with pytest.raises(ValueError, match="política original"):
        recovery.settings(args)
