"""Descriptive temporal evidence for monthly spectral and regional rainfall data."""

import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.dates import DateFormatter, MonthLocator

from aquaclima.storage.http import checksum, write_atomic, write_json

CHANGE_THRESHOLDS = {"ndvi_median": 0.20, "ndmi_median": 0.15}
LOW_QUALITY_PIXEL_PCT = 80.0
INDICES = ("ndvi_median", "ndmi_median")
COLORS = ("#23785b", "#456f9b")


def _csv(path: Path, data: pd.DataFrame) -> Path:
    write_atomic(path, data.to_csv(index=False, na_rep="", lineterminator="\n").encode("utf-8"))
    return path


def _figure(figure, path: Path, credit: str) -> Path:
    buffer = io.BytesIO()
    try:
        figure.supxlabel(credit, fontsize=7)
        figure.savefig(buffer, format="png", dpi=150)
    finally:
        plt.close(figure)
    write_atomic(path, buffer.getvalue())
    return path


def _empty(axis) -> None:
    axis.text(0.5, 0.5, "Sem observações aceitas", ha="center", va="center", transform=axis.transAxes)


def _changes(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pivot_id, pivot in frame.groupby("pivot_id", sort=True):
        valid = pivot.loc[pivot["monthly_status"].eq("ok")].sort_values("month")
        for target, threshold in CHANGE_THRESHOLDS.items():
            observed = valid.loc[valid[target].notna()]
            for position in range(1, len(observed)):
                before, after = observed.iloc[position - 1], observed.iloc[position]
                delta = float(after[target] - before[target])
                if abs(delta) + 1e-12 < threshold:
                    continue
                gap = pd.Period(after["month"], freq="M").ordinal - pd.Period(before["month"], freq="M").ordinal
                rows.append({
                    "pivot_id": pivot_id, "index": target, "from_month": before["month"], "to_month": after["month"],
                    "from_value": float(before[target]), "to_value": float(after[target]), "change": delta,
                    "absolute_change_threshold": threshold, "elapsed_calendar_months": gap,
                    "unobserved_months_between": gap - 1, "consecutive_calendar_months": gap == 1,
                    "from_accepted_scenes": int(before["n_accepted_scenes"]),
                    "to_accepted_scenes": int(after["n_accepted_scenes"]),
                    "from_batch_status": before["batch_status"], "to_batch_status": after["batch_status"],
                })
    return pd.DataFrame(rows, columns=[
        "pivot_id", "index", "from_month", "to_month", "from_value", "to_value", "change",
        "absolute_change_threshold", "elapsed_calendar_months", "unobserved_months_between",
        "consecutive_calendar_months", "from_accepted_scenes", "to_accepted_scenes", "from_batch_status", "to_batch_status",
    ])


def generate_exploration(monthly_path: Path, observations_path: Path, output_dir: Path) -> dict[str, Path]:
    """Generate plots and descriptive changes while retaining missing temporal slots."""
    frame = pd.read_csv(monthly_path, dtype={"pivot_id": str, "month": str})
    observations = pd.read_csv(observations_path, dtype={"pivot_id": str})
    required = {"pivot_id", "month", "monthly_status", "batch_status", "n_accepted_scenes", "precip_mm", *INDICES}
    if required - set(frame.columns) or frame.duplicated(["pivot_id", "month"]).any() or frame.empty:
        raise ValueError("Tabela mensal inválida para exploração")
    dates = pd.to_datetime(frame["month"] + "-01", format="%Y-%m-%d", errors="raise")
    frame["year"], frame["calendar_month"] = dates.dt.year, dates.dt.month
    frame["date_axis"] = dates
    frame = frame.sort_values(["pivot_id", "month"])
    valid = frame.loc[frame["monthly_status"].eq("ok")].copy()
    years_present = ", ".join(str(year) for year in sorted(frame["year"].unique()))
    credit = f"Contains modified Copernicus Sentinel data {years_present} · CHIRPS3 / UCSB"
    artifacts = {}
    summary_rows = []
    for pivot_id, rows in frame.groupby("pivot_id", sort=True):
        for target in INDICES:
            values = rows.loc[rows["monthly_status"].eq("ok"), target].dropna()
            summary_rows.append({
                "pivot_id": pivot_id, "index": target, "requested_months": len(rows), "observed_months": len(values),
                "coverage_fraction": len(values) / len(rows), "median": values.median(), "min": values.min(),
                "max": values.max(), "q25": values.quantile(0.25), "q75": values.quantile(0.75),
            })
    artifacts["statistics"] = _csv(output_dir / "descriptive_statistics.csv", pd.DataFrame(summary_rows))
    coverage = frame[["pivot_id", "month", "batch_status", "query_complete", "monthly_status", "n_attempted_scenes",
                      "n_accepted_scenes", "n_accepted_dates", "valid_pixel_pct_median", "valid_pixel_pct_min",
                      "observation_day_span"]]
    artifacts["coverage"] = _csv(output_dir / "month_coverage.csv", coverage)
    seasonal = frame.assign(observed=frame["monthly_status"].eq("ok")).groupby("calendar_month").agg(
        expected_pivot_months=("month", "size"), observed_pivot_months=("observed", "sum"),
        queried_pivot_months=("query_complete", "sum"),
    ).reset_index()
    seasonal["coverage_fraction"] = seasonal["observed_pivot_months"] / seasonal["expected_pivot_months"]
    artifacts["seasonal_coverage"] = _csv(output_dir / "seasonal_coverage.csv", seasonal)
    low_quality = frame.loc[frame["n_accepted_scenes"].eq(0) | frame["valid_pixel_pct_min"].lt(LOW_QUALITY_PIXEL_PCT)].copy()
    low_quality["quality_review_reason"] = np.where(low_quality["n_accepted_scenes"].eq(0),
                                                   "no_accepted_scene", "valid_pixel_pct_below_threshold")
    low_quality["pixel_pct_threshold_analyst_parameter"] = LOW_QUALITY_PIXEL_PCT
    artifacts["low_quality"] = _csv(output_dir / "low_quality_months.csv", low_quality.drop(columns="date_axis"))
    changes = _changes(frame)
    artifacts["changes"] = _csv(output_dir / "pronounced_changes.csv", changes)

    figure, axes = plt.subplots(1, 2, figsize=(10.4, 4), layout="constrained")
    for axis, target, color in zip(axes, INDICES, COLORS, strict=True):
        values = valid[target].dropna()
        if len(values):
            axis.hist(values, bins=np.linspace(-1, 1, 21), color=color, edgecolor="white")
        else:
            _empty(axis)
        axis.set(xlabel=target.removesuffix("_median").upper(), ylabel="Pivôs-mês observados", xlim=(-1, 1))
        axis.grid(axis="y", alpha=0.2)
    figure.suptitle("Distribuição dos agregados mensais", fontweight="bold")
    artifacts["distributions"] = _figure(figure, output_dir / "distributions.png", credit)

    pivots = sorted(frame["pivot_id"].unique())
    figure, axes = plt.subplots(len(pivots), 2, figsize=(13, max(4, 2.0 * len(pivots))), squeeze=False,
                                sharex=True, sharey="col", layout="constrained")
    for axis_row, pivot_id in zip(axes, pivots, strict=True):
        rows = frame.loc[frame["pivot_id"].eq(pivot_id)]
        for axis, target, color in zip(axis_row, INDICES, COLORS, strict=True):
            axis.plot(rows["date_axis"], rows[target].where(rows["monthly_status"].eq("ok")),
                      marker="o", markersize=3, linewidth=1, color=color)
            axis.set_ylabel(f"Pivô {pivot_id}\n{target.removesuffix('_median').upper()}")
            axis.grid(alpha=0.2)
            axis.xaxis.set_major_formatter(DateFormatter("%m/%Y"))
            axis.xaxis.set_major_locator(MonthLocator(interval=max(1, (frame["month"].nunique() + 9) // 10)))
            axis.set_xlim(frame["date_axis"].min() - pd.Timedelta(days=3),
                          frame["date_axis"].max() + pd.offsets.MonthEnd(1))
    figure.suptitle("Evolução mensal por pivô · lacunas preservadas", fontweight="bold")
    artifacts["temporal"] = _figure(figure, output_dir / "temporal_pivots.png", credit)

    figure, axes = plt.subplots(1, 2, figsize=(10.4, 4), layout="constrained")
    years = sorted(frame["year"].unique())
    for axis, target, color in zip(axes, INDICES, COLORS, strict=True):
        values = [valid.loc[valid["year"].eq(year), target].dropna().to_numpy() for year in years]
        if any(len(value) for value in values):
            axis.boxplot(values, tick_labels=[str(year) for year in years], patch_artist=True,
                         boxprops={"facecolor": color, "alpha": 0.65}, medianprops={"color": "black"})
        else:
            axis.set_xticks(range(1, len(years) + 1), [str(year) for year in years])
            _empty(axis)
        axis.set(ylabel=target.removesuffix("_median").upper(), xlabel="Ano")
        axis.grid(axis="y", alpha=0.2)
    figure.suptitle("Comparação anual descritiva dos pivôs-mês disponíveis", fontweight="bold")
    artifacts["annual"] = _figure(figure, output_dir / "annual_comparison.png", credit)

    months = sorted(frame["month"].unique())
    heat = frame.pivot(index="pivot_id", columns="month", values="n_accepted_scenes").reindex(index=pivots, columns=months)
    spectral = frame.pivot(index="pivot_id", columns="month", values="ndvi_median").reindex(index=pivots, columns=months)
    figure, axes = plt.subplots(2, 1, figsize=(max(11, len(months) * 0.33), 5.7), layout="constrained")
    for axis, matrix, title, cmap, low, high in (
        (axes[0], heat, "Cenas aceitas por pivô-mês", "Blues", 0, max(1, heat.to_numpy().max())),
        (axes[1], spectral, "NDVI mensal · células brancas indicam dados ausentes", "YlGn", -1, 1),
    ):
        palette = plt.get_cmap(cmap).with_extremes(bad="white")
        mesh = axis.imshow(np.ma.masked_invalid(matrix.to_numpy(dtype=float)), aspect="auto", cmap=palette, vmin=low, vmax=high)
        axis.set_yticks(range(len(pivots)), pivots)
        axis.set_xticks(range(len(months)), months, rotation=90, fontsize=7)
        axis.set_title(title, fontsize=10)
        axis.set_ylabel("Pivô ANA")
        figure.colorbar(mesh, ax=axis, shrink=0.85)
    artifacts["heatmap"] = _figure(figure, output_dir / "seasonal_heatmap.png", credit)

    figure, axes = plt.subplots(1, 2, figsize=(10.5, 4.3), layout="constrained")
    rain = valid.loc[valid["precip_status"].eq("ok")]
    for axis, target, color in zip(axes, INDICES, COLORS, strict=True):
        pairs = rain[["precip_mm", target]].dropna()
        if len(pairs):
            axis.scatter(pairs["precip_mm"], pairs[target], color=color, alpha=0.6, s=20)
        else:
            _empty(axis)
        axis.set(xlabel="CHIRPS regional (mm/mês)", ylabel=target.removesuffix("_median").upper())
        axis.grid(alpha=0.2)
    figure.suptitle("Precipitação e resposta espectral no mesmo mês\n"
                   "Pivôs próximos podem compartilhar a mesma célula meteorológica", fontsize=11)
    artifacts["rain"] = _figure(figure, output_dir / "rain_context.png", credit)
    artifacts["report"] = output_dir / "exploration_report.json"
    write_json(artifacts["report"], {
        "monthly_input_sha256": checksum(monthly_path), "observations_input_sha256": checksum(observations_path),
        "pivot_count": len(pivots), "requested_months": months, "accepted_scene_observations": len(observations),
        "observed_pivot_months": len(valid), "expected_pivot_months": len(frame),
        "monthly_coverage_fraction": len(valid) / len(frame), "pronounced_change_count": len(changes),
        "change_thresholds_analyst_parameters": CHANGE_THRESHOLDS,
        "low_quality_pixel_pct_threshold_analyst_parameter": LOW_QUALITY_PIXEL_PCT,
        "low_quality_pivot_months": len(low_quality),
        "change_comparison": "Successive observed months with explicit calendar gaps; absolute spectral differences.",
        "rain_interpretation": "Regional monthly precipitation estimate; shared cells and seasonality create dependence.",
    })
    return artifacts
