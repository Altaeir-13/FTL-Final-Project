import pandas as pd
import pytest

from aquaclima.cli import main
from aquaclima.features.integration import integrate
from aquaclima.storage.http import write_json


@pytest.fixture
def pivots(tmp_path):
    path = tmp_path / "pivots.geojson"
    write_json(path, {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"pivot_id": "0001", "area_ha": 15.5}},
    ]})
    return path


def test_integration_keeps_missing_months_rejections_and_rain(pivots, tmp_path):
    indices = tmp_path / "indices.csv"
    indices.write_text(
        "pivot_id,date,scene_id,status,ndvi_median,ndmi_median,valid_pixel_pct\n"
        "0001,2025-06-14,S1,insufficient_valid_pixels,,,25\n"
        "0001,2025-07-02,S2,ok,0.6,0.2,92\n",
        encoding="utf-8",
    )
    climate = tmp_path / "monthly.csv"
    climate.write_text(
        "pivot_id,month,precip_mm,precip_status,chirps_source\n"
        "0001,2025-06,0,ok,https://example.test/chirps.tif\n",
        encoding="utf-8",
    )
    result = integrate(pivots, indices, climate, ["2025-06", "2025-07", "2025-08"], tmp_path)
    actual = pd.read_csv(result, dtype={"pivot_id": str})
    assert actual["pivot_id"].tolist() == ["0001"] * 3
    assert actual["status"].tolist() == ["insufficient_valid_pixels", "ok", "no_scene"]
    assert actual["precip_status"].tolist() == ["ok", "no_monthly_data", "no_monthly_data"]
    assert actual["precip_mm"].iloc[0] == 0
    assert actual["precip_mm"].iloc[1:].isna().all()
    assert actual["ndmi_median"].iloc[1] == 0.2
    assert actual["ndmi_median"].iloc[[0, 2]].isna().all()
    before = result.read_bytes()
    assert integrate(pivots, indices, climate, ["2025-06", "2025-07", "2025-08"], tmp_path).read_bytes() == before


def test_dry_run_writes_nothing_and_does_not_connect(tmp_path, monkeypatch, capsys):
    from aquaclima import cli

    def forbidden(*args, **kwargs):
        pytest.fail("Não deve criar cliente HTTP")

    monkeypatch.setattr(cli, "HttpClient", forbidden)
    data = tmp_path / "new"
    assert main(["run", "--dry-run", "--data-dir", str(data)]) == 0
    assert not data.exists()
    assert "chirps-v3.0.2025.06.tif" in capsys.readouterr().out
