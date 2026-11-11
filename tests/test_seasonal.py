import json

import numpy as np
import pandas as pd
import pytest

from aquaclima.modeling.seasonal import run_baseline


def monthly(path, years, *, validation_months=12, missing_train_month=None):
    records = []
    for year in years:
        for month in range(1, 13):
            observed = not (year == 2024 and month > validation_months)
            observed = observed and not (year == 2023 and month == missing_train_month)
            ndvi = 0.5 + 0.2 * np.sin(2 * np.pi * (month - 1) / 12) + (0.05 if year == 2024 else 0)
            records.append({
                "pivot_id": "001", "month": f"{year}-{month:02d}", "batch_status": "complete",
                "query_complete": True, "monthly_status": "ok" if observed else "no_accepted_observation",
                "ndvi_median": ndvi if observed else None,
                "ndmi_median": 0.5 * ndvi if observed else None,
            })
    frame = pd.DataFrame(records)
    frame.to_csv(path, index=False)
    return frame


def test_chronological_seasonal_validation_and_explicit_future_exclusion(tmp_path):
    source = tmp_path / "monthly.csv"
    data = monthly(source, [2022, 2023, 2024, 2025])
    result = run_baseline(source, tmp_path / "first")
    predictions = pd.read_csv(result["predictions"])
    metrics = pd.read_csv(result["metrics"])
    assert predictions["month"].str.startswith("2024-").all()
    assert predictions["status"].eq("scored").all()
    seasonal = metrics.loc[metrics["method"].eq("calendar_month_median") & metrics["target"].eq("ndvi_median")].iloc[0]
    assert seasonal["mae"] == pytest.approx(0.05)
    assert seasonal["rmse"] == pytest.approx(0.05)
    report = json.loads(result["report"].read_bytes())
    assert report["excluded_pivot_months_by_year"] == {"2025": 12}
    data.loc[data["month"].str.startswith("2025"), "ndvi_median"] = -0.99
    data.loc[data["month"].str.startswith("2025"), "ndmi_median"] = -0.99
    data.to_csv(source, index=False)
    second = run_baseline(source, tmp_path / "second")
    assert result["parameters"].read_bytes() == second["parameters"].read_bytes()
    assert result["predictions"].read_bytes() == second["predictions"].read_bytes()
    assert result["metrics"].read_bytes() == second["metrics"].read_bytes()
    model = json.loads(result["parameters"].read_bytes())["models"][0]
    assert all(month.startswith(("2022", "2023")) for month in model["training_months"])


def test_sparse_validation_does_not_publish_mae_rmse(tmp_path):
    source = tmp_path / "monthly.csv"
    monthly(source, [2022, 2023, 2024], validation_months=5)
    paths = run_baseline(source, tmp_path / "result")
    metrics = pd.read_csv(paths["metrics"])
    assert metrics["status"].eq("insufficient_validation_data").all()
    assert metrics[["mae", "rmse"]].isna().all().all()
    assert metrics["scored_months"].eq(5).all()


def test_same_calendar_month_requires_two_distinct_training_years(tmp_path):
    source = tmp_path / "monthly.csv"
    monthly(source, [2022, 2023, 2024], missing_train_month=4)
    result = run_baseline(source, tmp_path / "result")
    predictions = pd.read_csv(result["predictions"])
    april = predictions.loc[predictions["month"].eq("2024-04") & predictions["method"].eq("calendar_month_median")]
    assert april["status"].eq("insufficient_training_data").all()
    assert april["predicted"].isna().all()
    other = predictions.loc[predictions["month"].eq("2024-05") & predictions["method"].eq("calendar_month_median")]
    assert other["status"].eq("scored").all()


def test_ridge_needs_representatives_of_every_calendar_month(tmp_path):
    source = tmp_path / "monthly.csv"
    frame = monthly(source, [2022, 2023, 2024])
    train_april = frame["month"].isin(["2022-04", "2023-04"])
    frame.loc[train_april, ["ndvi_median", "ndmi_median"]] = None
    frame.loc[train_april, "monthly_status"] = "no_accepted_observation"
    frame.to_csv(source, index=False)
    result = run_baseline(source, tmp_path / "result")
    predictions = pd.read_csv(result["predictions"])
    ridge = predictions.loc[predictions["method"].eq("harmonic_ridge")]
    assert ridge["status"].eq("insufficient_training_data").all()
    assert ridge["predicted"].isna().all()


def test_incomplete_acquisition_is_excluded_from_model_training(tmp_path):
    source = tmp_path / "monthly.csv"
    frame = monthly(source, [2022, 2023, 2024])
    frame.loc[frame["month"].eq("2023-01"), "batch_status"] = "partial"
    frame.to_csv(source, index=False)
    result = run_baseline(source, tmp_path / "result")
    params = json.loads(result["parameters"].read_bytes())
    assert all("2023-01" not in model["training_months"] for model in params["models"])


def test_future_only_input_produces_insufficient_status_without_predictions(tmp_path):
    source = tmp_path / "monthly.csv"
    monthly(source, [2025])
    result = run_baseline(source, tmp_path / "result")
    assert pd.read_csv(result["predictions"]).empty
    assert json.loads(result["report"].read_bytes())["status"] == "insufficient_data"
