"""Static time-series figure and audit summaries for a local pilot."""

import io
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.dates import DateFormatter

from aquaclima.storage.http import read_ledger, write_atomic, write_json


def plot_timeseries(table_path: Path, output_dir: Path) -> Path | None:
    data = pd.read_csv(table_path, dtype={"pivot_id": str})
    if not data[["ndvi_median", "ndmi_median", "precip_mm"]].notna().any().any():
        return None
    figure, axes = plt.subplots(3, 1, figsize=(10.8, 8.0), sharex=True, layout="constrained")
    figure.suptitle("AquaClima · Bacia do rio São Marcos", fontsize=16, fontweight="bold")
    for pivot, rows in data.groupby("pivot_id", sort=True):
        # Missing months remain gaps. An undated row is placed at month start solely on the x-axis.
        dates = pd.to_datetime(rows["date"].astype("string").fillna(rows["month"] + "-01"))
        for ax, key in zip(axes[:2], ("ndvi_median", "ndmi_median"), strict=True):
            ax.plot(dates, rows[key], marker="o", linewidth=1.15, markersize=4, label=pivot)
    rain = data.dropna(subset=["precip_mm"])
    cell = ["month", "chirps_cell_lon", "chirps_cell_lat"]
    if set(cell).issubset(rain.columns):
        rain = rain.drop_duplicates(cell)
    for month, rows in rain.groupby("month", sort=True):
        values = rows["precip_mm"]
        x = pd.Timestamp(f"{month}-01")
        axes[2].vlines(x, values.min(), values.max(), color="#328293", linewidth=5)
        axes[2].scatter(x, values.median(), color="#1b6575", s=22)
    for ax, label in zip(axes, ("NDVI mediano", "NDMI mediano", "CHIRPS (mm/mês)"), strict=True):
        ax.set_ylabel(label)
        ax.grid(alpha=0.25)
    axes[0].legend(title="Pivô ANA", ncol=5, loc="best", fontsize=8)
    axes[2].set_title("Mediana e amplitude entre as células regionais amostradas", fontsize=9)
    axes[2].xaxis.set_major_formatter(DateFormatter("%d/%m/%Y"))
    years = ", ".join(sorted(data["date"].dropna().astype("string").str.slice(0, 4).unique()))
    credit = f"Contains modified Copernicus Sentinel data {years} · " if years else ""
    axes[2].set_xlabel(f"Data Sentinel-2 / início do mês CHIRPS\n{credit}CHIRPS3 / UCSB")
    buffer = io.BytesIO()
    try:
        figure.savefig(buffer, format="png", dpi=150)
    finally:
        plt.close(figure)
    target = output_dir / "serie_temporal.png"
    write_atomic(target, buffer.getvalue())
    return target


def summarize(data_dir: Path, output_dir: Path, *, table_path: Path | None, elapsed: float,
              run_start: int, failures: list[str], requested_months: list[str],
              pivots: int, scenes: dict, offline: bool) -> Path:
    ledger = read_ledger(data_dir / "acquisition.jsonl")
    all_requests = [e for e in ledger if e["event"] == "http"]
    requests = [e for e in ledger[run_start:] if e["event"] == "http"]
    files = {entry["path"]: entry for entry in ledger if entry["event"] == "file"}
    for name, entry in files.items():
        entry["present"] = (data_dir / name).is_file()
    existing = [p for p in data_dir.rglob("*") if p.is_file()]
    table = pd.read_csv(table_path) if table_path is not None else None
    crop_manifest = data_dir / "raw/sentinel/crops.json"
    chirps_manifest = data_dir / "raw/chirps/manifest.json"
    crops = json.loads(crop_manifest.read_bytes())["scenes"] if crop_manifest.is_file() else []
    rain = json.loads(chirps_manifest.read_bytes())["months"] if chirps_manifest.is_file() else {}
    report = {
        "mode": "offline" if offline else "online",
        "elapsed_s": round(elapsed, 3),
        "pivot_count": pivots,
        "requested_months": requested_months,
        "sentinel_candidate_count": scenes.get("candidate_count"),
        "sentinel_selected_ids": scenes.get("selected_ids", []),
        "sentinel_scene_ids_in_table": sorted(table["scene_id"].dropna().unique()) if table is not None else [],
        "sentinel_crop_status": {s["id"]: s["status"] for s in crops},
        "sentinel_successful_crops": sum(a["status"] == "ok" for s in crops for a in s["assets"].values()),
        "chirps_month_status": {month: entry["status"] for month, entry in rain.items()},
        "observations": int(len(table)) if table is not None else 0,
        "spectral_status": dict(Counter(table["status"])) if table is not None else {},
        "precip_status": dict(Counter(table["precip_status"])) if table is not None else {},
        "requests": len(requests),
        "payload_bytes": sum(r["bytes"] for r in requests),
        "payload_bytes_by_host": _transfer_by_host(requests),
        "cumulative_payload_bytes": sum(r["bytes"] for r in all_requests),
        "cumulative_payload_bytes_by_host": _transfer_by_host(all_requests),
        "cumulative_requests": len(all_requests),
        "cumulative_http_elapsed_s": round(sum(r["elapsed_s"] for r in all_requests), 3),
        "storage_bytes_under_data_dir": sum(p.stat().st_size for p in existing),
        "files_acquired_or_generated_in_inventory": list(files.values()),
        "request_failures": [r for r in requests if r.get("error")],
        "stage_failures": failures,
    }
    target = output_dir / "relatorio_aquisicao.json"
    write_json(target, report)
    return target


def _transfer_by_host(requests: list[dict]) -> dict:
    from urllib.parse import urlsplit

    hosts = Counter()
    for entry in requests:
        hosts[urlsplit(entry["url"]).netloc] += entry["bytes"]
    return dict(hosts)
