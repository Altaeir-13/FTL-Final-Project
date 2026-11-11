import json
from datetime import date

import pytest

from aquaclima.ingestion.sentinel import acquire_crops, search_scenes
from aquaclima.processing.indices import process_indices
from test_sentinel import stac_case


def test_alternative_collection_requires_explicit_processing_contract(stac_case, tmp_path):
    http, pivots = stac_case
    plan = search_scenes(
        http, pivots, tmp_path, start=date(2025, 7, 1), end=date(2025, 7, 31),
        max_cloud=60, max_scenes=2,
    )
    path = acquire_crops(http, pivots, plan, tmp_path)
    manifest = json.loads(path.read_bytes())
    manifest["collection"] = "sentinel-2-l2a"
    url = "https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-2-l2a/items/test"
    manifest["scenes"][0]["source_item_url"] = url
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="coleção"):
        process_indices(pivots, path, tmp_path, min_valid_fraction=0.5)
    output = process_indices(
        pivots, path, tmp_path, min_valid_fraction=0.5, expected_collection="sentinel-2-l2a",
    )
    assert url in output.read_text(encoding="utf-8")
