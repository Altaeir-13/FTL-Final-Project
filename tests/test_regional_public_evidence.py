"""Validate the actual small evidence shipped to reviewers in a clean clone."""
import json
import runpy
from pathlib import Path

import pandas as pd

from aquaclima.storage.http import checksum

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidencias/guadalupe-pi"


def test_official_selection_snapshot_retains_frozen_decision_and_sample():
    verify = runpy.run_path(str(ROOT / "scripts/verify_regional_selection.py"))["verify"]
    result = verify(ROOT / "data/regions/selection")
    assert result["files_verified"] == 18
    assert result["network_requests"] == 0


def test_published_regional_evidence_hashes_and_scientific_denominators():
    manifest = json.loads((EVIDENCE / "manifest.json").read_bytes())
    for name, record in manifest["files"].items():
        path = EVIDENCE / name
        assert path.resolve().is_relative_to(EVIDENCE.resolve())
        assert path.stat().st_size == record["bytes"]
        assert checksum(path) == record["sha256"]
    summary = json.loads((EVIDENCE / "curated/v1/summary.json").read_bytes())
    attempts = pd.read_csv(EVIDENCE / "curated/v1/attempts.csv")
    monthly = pd.read_csv(EVIDENCE / "curated/v1/monthly.csv")
    observations = pd.read_csv(EVIDENCE / "curated/v1/observations.csv")
    assert len(observations) == summary["accepted_observations"] == 29
    assert len(attempts) == 30
    assert len(monthly) == summary["calendar_slots"] == 115
    assert monthly.month.nunique() == 23
    assert monthly.monthly_status.eq("not_queried").sum() == 85
    assert observations.pivot_id.str.startswith("PI:").all()
    assert observations.valid_pixel_pct.ge(70).all()
    rejected = attempts.loc[attempts.status.ne("ok")]
    assert len(rejected) == 1
    assert rejected[["ndvi_median", "ndmi_median"]].isna().all().all()
    assert rejected.valid_pixel_pct.lt(70).all()
    proof = json.loads((EVIDENCE / "offline-verification.json").read_bytes())
    assert proof == {"status": "identical", "files_checked": 5, "http_requests": 0, "transferred_bytes": 0}


def test_real_image_derivatives_share_a_grid_and_true_quality_labels():
    provenance = json.loads((EVIDENCE / "comparison/provenance.json").read_bytes())
    scenes = provenance["scenes"]
    observations = pd.read_csv(EVIDENCE / "curated/v1/observations.csv")
    assert len(scenes) == 2
    assert scenes[0]["date"] != scenes[1]["date"]
    for key in ("crs", "transform", "shape", "bounds"):
        assert scenes[0][key] == scenes[1][key]
    for scene in scenes:
        path = EVIDENCE / "comparison" / scene["image"]
        assert checksum(path) == scene["image_sha256"]
        rows = observations.loc[observations.scene_id.eq(scene["scene_id"])]
        assert len(rows) == 5
        assert rows.valid_pixel_pct.eq(scene["valid_pixel_pct_each_pivot"]).all()
