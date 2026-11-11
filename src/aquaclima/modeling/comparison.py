"""Compare fixed seasonal references on exactly the same observed 2024 months."""

from itertools import combinations
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aquaclima.modeling.naive_seasonal import METHOD as NAIVE_METHOD
from aquaclima.modeling.seasonal import MIN_VALIDATION_MONTHS, TARGETS
from aquaclima.storage.http import checksum, write_atomic, write_json

METHODS = ("calendar_month_median", "harmonic_ridge", NAIVE_METHOD)
METRIC_COLUMNS = ["comparison", "pivot_id", "target", "method", "phase", "n_common_months",
                  "common_months", "coverage_fraction", "mae", "rmse", "bias_mean", "status"]
PREDICTION_COLUMNS = ["comparison", "pivot_id", "target", "method", "month", "observed", "predicted", "residual"]


def _read_predictions(path: Path, *, naive: bool, monthly: pd.DataFrame) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"pivot_id": str, "month": str, "evaluation_month": str})
    if naive:
        frame = frame.rename(columns={"evaluation_month": "month"})
    required = {"pivot_id", "month", "target", "method", "observed", "predicted", "residual", "status"}
    if (required - set(frame) or frame.duplicated(["pivot_id", "month", "target", "method"]).any()
            or not frame["month"].str.fullmatch(r"2024-(0[1-9]|1[0-2])").all()
            or not frame["method"].isin((NAIVE_METHOD,) if naive else METHODS[:2]).all()
            or not frame["target"].isin(TARGETS).all()):
        raise ValueError(f"Predições incompatíveis em {path.name}")
    accepted = frame.loc[frame["status"].eq("paired" if naive else "scored")].copy()
    for column in ("observed", "predicted", "residual"):
        accepted[column] = pd.to_numeric(accepted[column], errors="raise")
        if not np.isfinite(accepted[column].to_numpy(dtype=float)).all():
            raise ValueError(f"Predição aceita ausente ou não finita em {path.name}")
    if not np.allclose(accepted["observed"] - accepted["predicted"], accepted["residual"], atol=1e-8, rtol=0):
        raise ValueError(f"Resíduo divergente em {path.name}")
    reference = monthly.set_index(["pivot_id", "month"])
    for row in accepted.to_dict("records"):
        key = (row["pivot_id"], row["month"])
        if key not in reference.index:
            raise ValueError(f"Predição sem referência mensal em {path.name}")
        observed = reference.loc[key]
        if (observed["monthly_status"] != "ok" or observed["batch_status"] != "complete"
                or not bool(observed["query_complete"])
                or not np.isclose(observed[row["target"]], row["observed"], atol=1e-8, rtol=0)):
            raise ValueError(f"Predição divergente da referência mensal em {path.name}")
    return accepted[["pivot_id", "month", "target", "method", "observed", "predicted", "residual"]]


def run_common_month_comparison(monthly_path: Path, baseline_dir: Path, naive_dir: Path,
                                output_dir: Path) -> dict[str, Path]:
    """Supplement, without refitting, the original chronological experiments.

    Each contrast uses the intersection of scored months for its methods.
    The original six-month minimum for publishing validation metrics is retained.
    Neither training eligibility nor original experiment files are changed.
    """
    monthly = pd.read_csv(monthly_path, dtype={"pivot_id": str, "month": str, "query_complete": "boolean"})
    required = {"pivot_id", "month", "monthly_status", "batch_status", "query_complete", *TARGETS}
    if required - set(monthly) or monthly.duplicated(["pivot_id", "month"]).any() or monthly.empty:
        raise ValueError("Tabela mensal inválida para comparação")
    source_paths = {"monthly": monthly_path, "baseline_report": baseline_dir / "baseline_report.json",
                    "baseline_predictions": baseline_dir / "validation_predictions.csv",
                    "naive_report": naive_dir / "naive_report.json", "naive_predictions": naive_dir / "naive_pairs.csv"}
    monthly_hash = checksum(monthly_path)
    for name, year_field in (("baseline_report", "validation_year"), ("naive_report", "evaluation_year")):
        report = json.loads(source_paths[name].read_bytes())
        if report.get("monthly_input_sha256") != monthly_hash or report.get(year_field) != 2024:
            raise ValueError("Os experimentos devem usar a mesma tabela mensal e avaliar 2024")
    predictions = pd.concat((
        _read_predictions(source_paths["baseline_predictions"], naive=False, monthly=monthly),
        _read_predictions(source_paths["naive_predictions"], naive=True, monthly=monthly)), ignore_index=True)
    metrics, shared = [], []
    contrasts = [tuple(METHODS), *combinations(METHODS, 2)]
    for pivot_id in sorted(monthly["pivot_id"].unique()):
        for target in TARGETS:
            group = predictions.loc[predictions["pivot_id"].eq(pivot_id) & predictions["target"].eq(target)]
            for methods in contrasts:
                comparison = "__vs__".join(methods)
                by_method = {method: group.loc[group["method"].eq(method)].set_index("month") for method in methods}
                months = sorted(set.intersection(*(set(table.index) for table in by_method.values())))
                for method, table in by_method.items():
                    selected = table.loc[months]
                    errors = selected["residual"].to_numpy(dtype=float)
                    adequate = len(months) >= MIN_VALIDATION_MONTHS
                    metrics.append({"comparison": comparison, "pivot_id": pivot_id, "target": target,
                        "method": method, "phase": "common_months_validation_2024", "n_common_months": len(months),
                        "common_months": json.dumps(months, separators=(",", ":")), "coverage_fraction": len(months) / 12,
                        "mae": float(np.abs(errors).mean()) if adequate else None,
                        "rmse": float(np.sqrt(np.square(errors).mean())) if adequate else None,
                        "bias_mean": float(errors.mean()) if adequate else None,
                        "status": "ok" if adequate else "insufficient_common_validation_months"})
                    shared.extend({"comparison": comparison, "pivot_id": pivot_id, "target": target,
                        "method": method, "month": month, "observed": row["observed"], "predicted": row["predicted"],
                        "residual": row["residual"]} for month, row in selected.iterrows())
    files = {"metrics": output_dir / "common_month_metrics.csv", "predictions": output_dir / "common_month_predictions.csv",
             "report": output_dir / "comparison_report.json"}
    for key, rows, columns in (("metrics", metrics, METRIC_COLUMNS), ("predictions", shared, PREDICTION_COLUMNS)):
        write_atomic(files[key], pd.DataFrame(rows, columns=columns).to_csv(
            index=False, na_rep="", lineterminator="\n").encode("utf-8"))
    write_json(files["report"], {"experiment": "common_months_validation_2024", "validation_year": 2024,
        "monthly_input_sha256": monthly_hash, "methods": list(METHODS),
        "comparisons": [list(methods) for methods in contrasts], "min_common_months_for_metrics": MIN_VALIDATION_MONTHS,
        "eligible_metric_rows": sum(row["status"] == "ok" for row in metrics),
        "status": "comparisons_available" if any(row["status"] == "ok" for row in metrics) else "insufficient_common_months",
        "inputs": {name: {"name": path.name, "sha256": checksum(path)} for name, path in source_paths.items()},
        "policy": "No refitting. For each pivot/index/contrast, intersect months scored by every participating method; retain original six-month metric threshold.",
        "limitations": "Observed spectral reconstruction. Calendar gaps, crop changes, source differences and dependencies among nearby pivots remain; results do not diagnose irrigation failures."})
    return files
