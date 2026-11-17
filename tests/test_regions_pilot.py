import json
from pathlib import Path

import pytest

from aquaclima.regions.pilot import consolidate, product_radiometry, run, selected_study, verify_inventory
from aquaclima.storage.http import checksum, write_json
from test_sentinel import stac_case


def selection(tmp_path):
    directory = tmp_path / "selection"
    directory.mkdir()
    winner = {"eligible": True, "sample_FIDs": [1, 2, 3], "code": "2112209", "UF": "MA", "name": "Timon"}
    decision = directory / "decision.json"
    write_json(decision, {"winner": winner})
    features = [{"type": "Feature", "properties": {"FID": fid, "pivot_id": f"MA:{fid}",
                 "UF": "MA", "MUNIC_CD": "2112209", "area_ha": 40},
                 "geometry": {"type": "Polygon", "coordinates": [[[-43, -5], [-42.99, -5],
                 [-42.99, -4.99], [-43, -4.99], [-43, -5]]]}} for fid in (1, 2, 3)]
    write_json(directory / "sample-2112209.geojson", {"type": "FeatureCollection", "features": features})
    return decision


def test_unqualified_decision_never_creates_experiment(tmp_path):
    decision = tmp_path / "decision.json"
    write_json(decision, {"winner": None})
    target = tmp_path / "regions/timon-ma"
    with pytest.raises(ValueError, match="não autoriza"):
        selected_study(decision, target)
    assert not target.exists()


def test_namespace_prevents_overwriting_original_study(tmp_path):
    decision = selection(tmp_path)
    with pytest.raises(ValueError, match="namespace independente"):
        selected_study(decision, tmp_path / "recovery")
    config, pivots = selected_study(decision, tmp_path / "regions/timon-ma")
    assert config["municipality"] == "Timon"
    assert config["min_valid_fraction"] == .70
    assert pivots.is_file()
    document = json.loads(decision.read_bytes())
    document["winner"]["sample_FIDs"] = [1, 2, 9]
    write_json(decision, document)
    with pytest.raises(ValueError, match="diverge"):
        selected_study(decision, tmp_path / "regions/timon-ma")


@pytest.mark.parametrize("field,value", [("pivot_id", "1"), ("UF", "PI"), ("MUNIC_CD", "2204501")])
def test_cross_region_and_ambiguous_keys_fail_closed(tmp_path, field, value):
    decision = selection(tmp_path)
    path = decision.parent / "sample-2112209.geojson"
    document = json.loads(path.read_bytes())
    document["features"][0]["properties"][field] = value
    write_json(path, document)
    with pytest.raises(ValueError):
        selected_study(decision, tmp_path / "regions/timon-ma")


def test_offline_inventory_detects_tampering_and_traversal(tmp_path):
    root = tmp_path / "regions/timon-ma"
    root.mkdir(parents=True)
    artifact = root / "observations.csv"
    artifact.write_bytes(b"real artifact fixture\n")
    record = {"bytes": artifact.stat().st_size, "sha256": checksum(artifact)}
    write_json(root / "inventory.json", {"files": {artifact.name: record}})
    verify_inventory(root)
    artifact.write_bytes(b"tampered\n")
    with pytest.raises(ValueError, match="adulterado"):
        verify_inventory(root)
    write_json(root / "inventory.json", {"files": {"../../external": record}})
    with pytest.raises(ValueError, match="externo"):
        verify_inventory(root)


def test_new_product_requires_own_xml_and_matching_scale_offset(tmp_path, stac_case):
    from test_planetary import MetadataHttp, PRODUCT
    http, _ = stac_case
    item = http.item
    item["properties"].update({"s2:product_uri": PRODUCT, "s2:processing_baseline": "04.00"})
    with pytest.raises(ValueError, match="sem XML"):
        product_radiometry(MetadataHttp(), item, tmp_path)
    item["assets"]["product_metadata"] = {"href": "https://example.invalid/metadata.xml"}
    result = product_radiometry(MetadataHttp(), item, tmp_path)
    assert result["calibration"]["bands"]["red"]["offset"] == -.1
    item["assets"]["nir"]["raster:bands"][0]["offset"] = 0
    with pytest.raises(ValueError, match="divergem"):
        product_radiometry(MetadataHttp(), item, tmp_path)


def test_offline_cannot_overwrite_its_reference_dataset(tmp_path):
    decision = selection(tmp_path)
    root = tmp_path / "regions/timon-ma"
    selected_study(decision, root)
    original = root / "curated/v1/observations.csv"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"unchanged reference\n")
    for output in (root, root / "curated/v1", root / "batches"):
        with pytest.raises(ValueError, match="independente"):
            run(decision, root, original=tmp_path, offline=True, output=output)
    assert original.read_bytes() == b"unchanged reference\n"


def test_recomputation_regression_does_not_destroy_acquired_indices(tmp_path, monkeypatch):
    root = tmp_path / "regions/timon-ma"
    batch = root / "batches/2023-01"
    batch.mkdir(parents=True)
    original = batch / "indices.csv"
    original.write_bytes(b"acquired baseline\n")
    write_json(batch / "batch.json", {"indices_sha256": checksum(original)})
    def regression(*args, output_path, **kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"regressed computation\n")
    monkeypatch.setattr("aquaclima.regions.pilot.process_indices", regression)
    with pytest.raises(ValueError, match="diverge"):
        consolidate(root, root / "pivots.geojson", root / "reproduced/v1")
    assert original.read_bytes() == b"acquired baseline\n"
