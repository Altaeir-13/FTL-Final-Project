"""Separate retrospective reference using the same calendar month of 2023."""

from pathlib import Path

import numpy as np
import pandas as pd

from aquaclima.modeling.seasonal import TARGETS
from aquaclima.storage.http import checksum, write_atomic, write_json

REFERENCE_YEAR = 2023
EVALUATION_YEAR = 2024
METHOD = "previous_year_same_calendar_month"


def run_naive_benchmark(monthly_path: Path, output_dir: Path) -> dict[str, Path]:
    """Compare accepted 2023/2024 month pairs without fitting or imputing values.

    This exploratory retrospective experiment has its own outputs and protocol.
    It leaves the original seasonal experiment unchanged and excludes 2025.
    """
    frame = pd.read_csv(monthly_path, dtype={"pivot_id": str, "month": str, "query_complete": "boolean"})
    required = {"pivot_id", "month", "monthly_status", "batch_status", "query_complete", *TARGETS}
    if required - set(frame.columns) or frame.empty or frame.duplicated(["pivot_id", "month"]).any():
        raise ValueError("Tabela mensal vazia, duplicada ou com colunas obrigatórias ausentes")
    periods = pd.PeriodIndex(frame["month"], freq="M")
    if frame["pivot_id"].isna().any() or not frame["month"].eq(periods.astype(str)).all():
        raise ValueError("Pivôs ou meses inválidos no benchmark")
    frame["year"], frame["calendar_month"] = periods.year, periods.month
    excluded = frame.loc[~frame["year"].isin((REFERENCE_YEAR, EVALUATION_YEAR))]
    eligible = frame.loc[frame["year"].isin((REFERENCE_YEAR, EVALUATION_YEAR))].copy()
    eligible["accepted_complete"] = (
        eligible["monthly_status"].eq("ok") & eligible["batch_status"].eq("complete")
        & eligible["query_complete"].fillna(False)
    )
    for target in TARGETS:
        eligible[target] = pd.to_numeric(eligible[target], errors="raise")
        values = eligible[target].to_numpy(dtype=float, na_value=np.nan)
        if np.isinf(values).any() or not eligible.loc[eligible["accepted_complete"], target].dropna().between(-1, 1).all():
            raise ValueError(f"Índice inválido em {target}")
    pairs, metrics = [], []
    for pivot_id in sorted(frame["pivot_id"].unique()):
        pivot = eligible.loc[eligible["pivot_id"].eq(pivot_id)].set_index("month")
        for target in TARGETS:
            rows = []
            for number in range(1, 13):
                reference_month = f"{REFERENCE_YEAR}-{number:02d}"
                evaluation_month = f"{EVALUATION_YEAR}-{number:02d}"
                reference = pivot.loc[reference_month] if reference_month in pivot.index else None
                evaluation = pivot.loc[evaluation_month] if evaluation_month in pivot.index else None
                source_ok = reference is not None and bool(reference["accepted_complete"]) and pd.notna(reference[target])
                target_ok = evaluation is not None and bool(evaluation["accepted_complete"]) and pd.notna(evaluation[target])
                status = "paired" if source_ok and target_ok else (
                    "missing_or_ineligible_both" if not source_ok and not target_ok else (
                        "missing_or_ineligible_reference" if not source_ok else "missing_or_ineligible_evaluation"
                    )
                )
                predicted = float(reference[target]) if source_ok else None
                observed = float(evaluation[target]) if target_ok else None
                rows.append({
                    "pivot_id": pivot_id, "target": target, "method": METHOD,
                    "experiment": "retrospective_exploratory_2023_to_2024", "calendar_month": number,
                    "reference_month": reference_month, "evaluation_month": evaluation_month,
                    "reference_available": source_ok, "evaluation_available": target_ok,
                    "predicted": predicted, "observed": observed,
                    "residual": observed - predicted if status == "paired" else None,
                    "status": status,
                })
            pairs.extend(rows)
            errors = np.array([row["residual"] for row in rows if row["status"] == "paired"], dtype=float)
            metrics.append({
                "pivot_id": pivot_id, "target": target, "method": METHOD,
                "phase": "retrospective_exploratory_2023_to_2024", "reference_year": REFERENCE_YEAR,
                "evaluation_year": EVALUATION_YEAR, "expected_months": 12,
                "reference_available_months": sum(row["reference_available"] for row in rows),
                "evaluation_available_months": sum(row["evaluation_available"] for row in rows),
                "n_valid_pairs": len(errors), "coverage_fraction": len(errors) / 12,
                "missing_reference_months": sum(not row["reference_available"] for row in rows),
                "missing_evaluation_months": sum(not row["evaluation_available"] for row in rows),
                "unpaired_months": 12 - len(errors),
                "mae": float(np.abs(errors).mean()) if len(errors) else None,
                "rmse": float(np.sqrt(np.square(errors).mean())) if len(errors) else None,
                "bias_mean": float(errors.mean()) if len(errors) else None,
                "status": "retrospective_exploratory" if len(errors) else "no_valid_pairs",
            })
    files = {"pairs": output_dir / "naive_pairs.csv", "metrics": output_dir / "naive_metrics.csv",
             "report": output_dir / "naive_report.json"}
    for key, rows in (("pairs", pairs), ("metrics", metrics)):
        data = pd.DataFrame(rows).to_csv(index=False, na_rep="", lineterminator="\n").encode("utf-8")
        write_atomic(files[key], data)
    write_json(files["report"], {
        "experiment": "retrospective_exploratory_2023_to_2024", "method": METHOD,
        "status": "exploratory_pairs_available" if any(row["n_valid_pairs"] for row in metrics) else "no_valid_pairs",
        "monthly_input_sha256": checksum(monthly_path), "reference_year": REFERENCE_YEAR,
        "evaluation_year": EVALUATION_YEAR, "expected_months_per_pivot_index": 12,
        "pivot_count": frame["pivot_id"].nunique(), "input_pivot_months": len(frame),
        "expected_pair_rows": len(pairs), "valid_pair_rows": sum(row["status"] == "paired" for row in pairs),
        "excluded_pivot_months_by_year": {
            str(int(year)): int(count) for year, count in excluded["year"].value_counts().sort_index().items()
        },
        "residual_convention": "observed_2024_minus_reference_2023",
        "eligibility": "Both months observed, monthly_status=ok, batch_status=complete, query_complete=true",
        "missing_data_policy": "No imputation. All 12 expected calendar-month slots retained per pivot/target; only paired accepted values enter metrics.",
        "limitations": [
            "Retrospective descriptive reconstruction, without independent agronomic or irrigation-failure labels.",
            "Both years may have different crop stages, crops, management and acquisition dates within a month.",
            "Cloud-related missingness can select a nonrepresentative subset of months.",
            "Nearby pivots and successive months are dependent; metrics are reported separately by pivot and index.",
            "The benchmark uses no precipitation or future evaluation-year values as predictors.",
        ],
        "interpretation": "Retrospective exploratory agreement with monthly spectral aggregates. Crop stage and field labels unavailable.",
    })
    return files
