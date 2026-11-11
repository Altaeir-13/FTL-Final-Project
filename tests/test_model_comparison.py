import json

import numpy as np
import pandas as pd
import pytest

from aquaclima.modeling.comparison import METHODS, run_common_month_comparison
from aquaclima.modeling.naive_seasonal import run_naive_benchmark
from aquaclima.modeling.seasonal import run_baseline
from aquaclima.storage.http import write_json


def experiments(tmp_path, *, sparse=False):
    rows = []
    for year in (2022, 2023, 2024):
        for month in range(1, 13):
            value = 0.5 + 0.2 * np.sin(2 * np.pi * (month - 1) / 12) + 0.03 * (year - 2022)
            missing = sparse and ((year == 2022 and month <= 6) or (year == 2024 and month == 12))
            rows.append({"pivot_id": "001", "month": f"{year}-{month:02d}",
                "monthly_status": "no_accepted_observation" if missing else "ok", "batch_status": "complete",
                "query_complete": True, "ndvi_median": None if missing else value,
                "ndmi_median": None if missing else value - 0.4})
    monthly = tmp_path / "monthly.csv"
    pd.DataFrame(rows).to_csv(monthly, index=False)
    baseline, naive = tmp_path / "baseline", tmp_path / "naive"
    run_baseline(monthly, baseline)
    run_naive_benchmark(monthly, naive)
    return monthly, baseline, naive


def test_all_methods_evaluated_on_identical_months_without_refitting(tmp_path):
    monthly, baseline, naive = experiments(tmp_path)
    original = {path: path.read_bytes() for folder in (baseline, naive) for path in folder.iterdir()}
    result = run_common_month_comparison(monthly, baseline, naive, tmp_path / "comparison")
    metrics = pd.read_csv(result["metrics"], dtype={"pivot_id": str})
    assert len(metrics) == 18
    assert metrics["pivot_id"].eq("001").all()
    assert metrics.n_common_months.eq(12).all() and metrics.status.eq("ok").all()
    naive_metrics = metrics.loc[metrics.method.eq(METHODS[2])]
    assert np.allclose(naive_metrics.mae, 0.03)
    assert np.allclose(naive_metrics.rmse, 0.03)
    predictions = pd.read_csv(result["predictions"])
    for _, contrast in predictions.groupby(["comparison", "target"]):
        month_sets = contrast.groupby("method")["month"].agg(set).tolist()
        assert all(values == month_sets[0] for values in month_sets)
    assert original == {path: path.read_bytes() for path in original}
    repeated = run_common_month_comparison(monthly, baseline, naive, tmp_path / "repeated")
    assert all(result[name].read_bytes() == repeated[name].read_bytes() for name in result)


def test_sparse_intersection_retains_six_month_gate(tmp_path):
    monthly, baseline, naive = experiments(tmp_path, sparse=True)
    result = run_common_month_comparison(monthly, baseline, naive, tmp_path / "out")
    metrics = pd.read_csv(result["metrics"])
    seasonal = metrics.loc[metrics.comparison.str.contains("calendar_month_median")]
    assert seasonal.n_common_months.eq(5).all()
    assert seasonal.mae.isna().all() and seasonal.rmse.isna().all()
    ridge_naive = metrics.loc[~metrics.comparison.str.contains("calendar_month_median")]
    assert ridge_naive.n_common_months.eq(11).all() and ridge_naive.status.eq("ok").all()
    assert json.loads(result["report"].read_bytes())["min_common_months_for_metrics"] == 6


@pytest.mark.parametrize("problem", ["dataset", "observed", "future", "duplicate"])
def test_incompatible_prediction_evidence_is_rejected(tmp_path, problem):
    monthly, baseline, naive = experiments(tmp_path)
    path = baseline / "validation_predictions.csv"
    frame = pd.read_csv(path, dtype={"pivot_id": str})
    if problem == "dataset":
        report_path = baseline / "baseline_report.json"
        report = json.loads(report_path.read_bytes())
        report["monthly_input_sha256"] = "wrong"
        write_json(report_path, report)
    elif problem == "observed":
        frame.loc[0, "observed"] += 0.1
        frame.loc[0, "residual"] += 0.1
    elif problem == "future":
        frame.loc[0, "month"] = "2025-01"
    else:
        frame = pd.concat([frame, frame.iloc[[0]]])
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError):
        run_common_month_comparison(monthly, baseline, naive, tmp_path / "out")


def test_future_values_cannot_change_comparison_metrics(tmp_path):
    monthly, baseline, naive = experiments(tmp_path)
    first = run_common_month_comparison(monthly, baseline, naive, tmp_path / "first")
    frame = pd.read_csv(monthly, dtype={"pivot_id": str})
    future = frame.loc[frame.month.str.startswith("2024")].copy()
    future["month"] = future["month"].str.replace("2024", "2025")
    future[["ndvi_median", "ndmi_median"]] = -0.9
    pd.concat([frame, future]).to_csv(monthly, index=False)
    run_baseline(monthly, baseline)
    run_naive_benchmark(monthly, naive)
    second = run_common_month_comparison(monthly, baseline, naive, tmp_path / "second")
    for name in ("metrics", "predictions"):
        assert first[name].read_bytes() == second[name].read_bytes()
