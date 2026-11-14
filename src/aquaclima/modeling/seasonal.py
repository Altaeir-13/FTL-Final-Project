"""Chronological seasonal references fitted on 2022–2023 and validated on 2024."""

from pathlib import Path

import numpy as np
import pandas as pd

from aquaclima.storage.http import checksum, write_atomic, write_json

TARGETS = ("ndvi_median", "ndmi_median")
TRAIN_YEARS = (2022, 2023)
VALIDATION_YEAR = 2024
MIN_RIDGE_MONTHS = 18
MIN_VALIDATION_MONTHS = 6
RIDGE_ALPHA = 1.0
PREDICTION_COLUMNS = [
    "pivot_id", "month", "target", "method", "phase", "observed", "predicted", "residual", "status",
    "training_months", "training_calendar_month_repeats",
]


def _design(calendar_months: np.ndarray) -> np.ndarray:
    angle = 2 * np.pi * (calendar_months - 1) / 12
    return np.column_stack((np.ones_like(angle), np.sin(angle), np.cos(angle), np.sin(2 * angle), np.cos(2 * angle)))


def _ridge(months: np.ndarray, values: np.ndarray) -> np.ndarray:
    design = _design(months)
    penalty = np.diag([0.0, RIDGE_ALPHA, RIDGE_ALPHA, RIDGE_ALPHA, RIDGE_ALPHA])
    return np.linalg.solve(design.T @ design + penalty, design.T @ values)


def _write_csv(path: Path, frame: pd.DataFrame) -> Path:
    write_atomic(path, frame.to_csv(index=False, na_rep="", lineterminator="\n").encode("utf-8"))
    return path


def run_baseline(monthly_path: Path, output_dir: Path) -> dict[str, Path]:
    """Validate fixed seasonal references with observed index values as numeric targets.

    Observed 2025 values are excluded before fitting, prediction and evaluation.
    A chronological numerical target assesses seasonal reconstruction, without field labels.
    """
    frame = pd.read_csv(monthly_path, dtype={"pivot_id": str, "month": str, "query_complete": "boolean"})
    required = {"pivot_id", "month", "monthly_status", "batch_status", "query_complete", *TARGETS}
    if required - set(frame.columns) or frame.duplicated(["pivot_id", "month"]).any():
        raise ValueError("Tabela mensal com esquema inválido ou pivô/mês duplicado")
    periods = pd.PeriodIndex(frame["month"], freq="M")
    if not frame["month"].eq(periods.astype(str)).all() or frame["pivot_id"].isna().any():
        raise ValueError("Identificadores ou meses inválidos na tabela mensal")
    frame["year"], frame["calendar_month"] = periods.year, periods.month
    for target in TARGETS:
        frame[target] = pd.to_numeric(frame[target], errors="raise")
        if np.isinf(frame[target].to_numpy(dtype=float, na_value=np.nan)).any():
            raise ValueError(f"Valores infinitos em {target}")
    excluded = frame.loc[~frame["year"].isin((*TRAIN_YEARS, VALIDATION_YEAR))]
    data = frame.loc[frame["year"].isin((*TRAIN_YEARS, VALIDATION_YEAR))].copy()
    eligible = (data["monthly_status"].eq("ok") & data["batch_status"].eq("complete")
                & data["query_complete"].fillna(False))
    predictions, metrics, parameters = [], [], []
    for pivot_id in sorted(frame["pivot_id"].unique()):
        pivot = data.loc[data["pivot_id"].eq(pivot_id)]
        validation = pivot.loc[pivot["year"].eq(VALIDATION_YEAR)].sort_values("month")
        for target in TARGETS:
            training = pivot.loc[
                pivot["year"].isin(TRAIN_YEARS) & eligible.loc[pivot.index] & pivot[target].notna()
            ].sort_values("month")
            grouped = training.groupby("calendar_month")[target].agg(["median", "count"])
            seasonal = grouped.loc[grouped["count"].ge(2), "median"].to_dict()
            coverage = sorted(training["calendar_month"].unique().tolist())
            ridge_ok = len(training) >= MIN_RIDGE_MONTHS and len(coverage) == 12
            coefficients = _ridge(training["calendar_month"].to_numpy(), training[target].to_numpy()) if ridge_ok else None
            parameter = {
                "pivot_id": pivot_id, "target": target, "training_months": training["month"].tolist(),
                "training_count": len(training), "calendar_months_represented": coverage,
                "seasonal_medians": {str(key): float(value) for key, value in seasonal.items()},
                "calendar_month_counts": {str(key): int(value) for key, value in grouped["count"].items()},
                "ridge_status": "fitted" if ridge_ok else "insufficient_training_data",
                "ridge_coefficients": coefficients.tolist() if ridge_ok else None,
            }
            parameters.append(parameter)
            for method in ("calendar_month_median", "harmonic_ridge"):
                rows = []
                for index, row in validation.iterrows():
                    calendar = int(row["calendar_month"])
                    estimate = seasonal.get(calendar) if method == "calendar_month_median" else (
                        float((_design(np.array([calendar])) @ coefficients)[0]) if ridge_ok else None
                    )
                    observed = float(row[target]) if pd.notna(row[target]) else None
                    if estimate is None:
                        status = "insufficient_training_data"
                    elif not bool(eligible.loc[index]):
                        status = "incomplete_reference_batch" if observed is not None else "missing_reference"
                    else:
                        status = "scored" if observed is not None else "missing_reference"
                    rows.append({
                        "pivot_id": pivot_id, "month": row["month"], "target": target, "method": method,
                        "phase": "validation_2024", "observed": observed, "predicted": estimate,
                        "residual": observed - estimate if status == "scored" else None, "status": status,
                        "training_months": len(training),
                        "training_calendar_month_repeats": int(grouped.loc[calendar, "count"]) if calendar in grouped.index else 0,
                    })
                predictions.extend(rows)
                errors = np.array([row["residual"] for row in rows if row["status"] == "scored"], dtype=float)
                adequate = len(errors) >= MIN_VALIDATION_MONTHS
                metrics.append({
                    "pivot_id": pivot_id, "target": target, "method": method, "phase": "validation_2024",
                    "training_months": len(training), "training_calendar_month_coverage": len(coverage),
                    "validation_rows_in_input": len(validation), "scored_months": len(errors),
                    "validation_annual_coverage_fraction": len(errors) / 12,
                    "mae": float(np.abs(errors).mean()) if adequate else None,
                    "rmse": float(np.sqrt(np.square(errors).mean())) if adequate else None,
                    "status": "ok" if adequate else "insufficient_validation_data",
                })
    prediction_frame = pd.DataFrame(predictions, columns=PREDICTION_COLUMNS)
    metric_frame = pd.DataFrame(metrics)
    model_file = output_dir / "model_parameters.json"
    write_json(model_file, {
        "training_years": list(TRAIN_YEARS), "validation_year": VALIDATION_YEAR,
        "ridge_alpha": RIDGE_ALPHA, "ridge_harmonics": 2, "ridge_penalize_intercept": False,
        "min_ridge_training_months": MIN_RIDGE_MONTHS, "min_ridge_calendar_months": 12,
        "min_seasonal_distinct_years_per_calendar_month": 2, "min_validation_months_for_metrics": MIN_VALIDATION_MONTHS,
        "models": parameters,
    })
    report = output_dir / "baseline_report.json"
    status = "validation_available" if any(metric["status"] == "ok" for metric in metrics) else "insufficient_data"
    excluded_years = {str(int(year)): int(count) for year, count in excluded["year"].value_counts().sort_index().items()}
    write_json(report, {
        "status": status, "monthly_input_sha256": checksum(monthly_path),
        "input_pivot_months": len(frame), "eligible_pivot_months_2022_2024": int(eligible.sum()),
        "excluded_pivot_months_by_year": excluded_years, "training_years": list(TRAIN_YEARS),
        "validation_year": VALIDATION_YEAR, "prediction_rows": len(predictions),
        "metrics_with_sufficient_validation": sum(metric["status"] == "ok" for metric in metrics),
        "numeric_reference": "Observed accepted monthly Sentinel-2 index aggregates",
        "interpretation": "Chronological seasonal reconstruction of spectral indices; agronomic field labels unavailable.",
    })
    return {
        "predictions": _write_csv(output_dir / "validation_predictions.csv", prediction_frame),
        "metrics": _write_csv(output_dir / "validation_metrics.csv", metric_frame),
        "parameters": model_file, "report": report,
    }
