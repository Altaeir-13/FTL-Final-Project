import json

import pandas as pd
import pytest

from aquaclima.modeling.naive_seasonal import run_naive_benchmark


def source(path):
    rows = []
    for year in (2022, 2023, 2024, 2025):
        for month in range(1, 13):
            value = 0.4 + month * 0.01 + (0.1 if year == 2024 else 0)
            rows.append({"pivot_id": "001", "month": f"{year}-{month:02d}", "monthly_status": "ok",
                         "batch_status": "complete", "query_complete": True,
                         "ndvi_median": value, "ndmi_median": value / 2})
    frame = pd.DataFrame(rows)
    frame.to_csv(path, index=False)
    return frame


def test_same_month_pairs_metrics_and_future_exclusion(tmp_path):
    path = tmp_path / "monthly.csv"
    frame = source(path)
    frame.loc[frame["month"].eq("2023-03"), "batch_status"] = "partial"
    frame.loc[frame["month"].eq("2024-02"), "query_complete"] = False
    frame.to_csv(path, index=False)
    result = run_naive_benchmark(path, tmp_path / "first")
    metrics = pd.read_csv(result["metrics"], dtype={"pivot_id": str})
    ndvi = metrics.loc[metrics["target"].eq("ndvi_median")].iloc[0]
    assert ndvi["pivot_id"] == "001"
    assert ndvi["n_valid_pairs"] == 10
    assert ndvi["coverage_fraction"] == pytest.approx(10 / 12)
    assert ndvi["reference_available_months"] == 11
    assert ndvi["evaluation_available_months"] == 11
    assert ndvi["unpaired_months"] == 2
    assert ndvi["mae"] == pytest.approx(0.1)
    assert ndvi["rmse"] == pytest.approx(0.1)
    assert ndvi["bias_mean"] == pytest.approx(0.1)
    pairs = pd.read_csv(result["pairs"])
    assert len(pairs) == 24
    assert pairs["reference_month"].str.startswith("2023").all()
    assert pairs["evaluation_month"].str.startswith("2024").all()
    assert pairs.loc[pairs["status"].ne("paired"), "residual"].isna().all()
    assert json.loads(result["report"].read_bytes())["excluded_pivot_months_by_year"] == {"2022": 12, "2025": 12}
    frame.loc[frame["month"].str.startswith("2025"), ["ndvi_median", "ndmi_median"]] = -0.99
    frame.to_csv(path, index=False)
    second = run_naive_benchmark(path, tmp_path / "second")
    assert result["metrics"].read_bytes() == second["metrics"].read_bytes()
    assert result["pairs"].read_bytes() == second["pairs"].read_bytes()


def test_missing_reference_year_keeps_explicit_empty_metrics(tmp_path):
    path = tmp_path / "monthly.csv"
    frame = source(path)
    frame = frame.loc[frame["month"].str.startswith("2024")]
    frame.to_csv(path, index=False)
    result = run_naive_benchmark(path, tmp_path / "out")
    metrics = pd.read_csv(result["metrics"])
    assert metrics["n_valid_pairs"].eq(0).all()
    assert metrics[["mae", "rmse", "bias_mean"]].isna().all().all()
    assert metrics["status"].eq("no_valid_pairs").all()


@pytest.mark.parametrize("problem", ["duplicate", "infinite", "bad_month"])
def test_invalid_evidence_rejected(tmp_path, problem):
    path = tmp_path / "monthly.csv"
    frame = source(path)
    if problem == "duplicate":
        frame = pd.concat([frame, frame.iloc[[0]]])
    elif problem == "infinite":
        frame.loc[frame["month"].eq("2024-01"), "ndvi_median"] = float("inf")
    else:
        frame.loc[0, "month"] = "2024-13"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError):
        run_naive_benchmark(path, tmp_path / "out")
