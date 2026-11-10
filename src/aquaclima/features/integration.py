"""Join local spectral observations to monthly climate context."""

import json
from pathlib import Path

import pandas as pd

from aquaclima.storage.http import write_atomic

ANA_SOURCE = "https://portal1.snirh.gov.br/server/rest/services/SFI/PIVOS_2022_SNIRH/MapServer/0"
SENTINEL_SOURCE = "https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a"
INDEX_COLUMNS = [
    "pivot_id", "date", "scene_id", "status", "ndvi_median", "ndmi_median", "valid_pixel_pct",
]
PRECIP_COLUMNS = ["pivot_id", "month", "precip_mm", "precip_status", "chirps_source"]


def month_range(start, end) -> list[str]:
    return [str(month) for month in pd.period_range(start, end, freq="M")]


def read_pivots(path: Path) -> pd.DataFrame:
    document = json.loads(path.read_bytes())
    pivots = pd.DataFrame([
        {"pivot_id": str(f["properties"]["pivot_id"]), "area_ha": float(f["properties"]["area_ha"])}
        for f in document["features"]
    ], columns=["pivot_id", "area_ha"])
    if pivots.empty or pivots["pivot_id"].duplicated().any():
        raise ValueError("GeoJSON sem pivôs ou com identificadores duplicados")
    if not pivots["area_ha"].gt(0).all():
        raise ValueError("Área inválida em pivots.geojson")
    pivots["ana_source"] = ANA_SOURCE
    return pivots


def _table(path: Path | None, columns: list[str], keys: list[str]) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame(columns=columns)
    table = pd.read_csv(path, dtype={"pivot_id": str, "month": str})
    if set(columns) - set(table.columns):
        raise ValueError(f"Colunas obrigatórias ausentes em {path}: {set(columns) - set(table.columns)}")
    if table[keys].isna().any().any() or table.duplicated(keys).any():
        raise ValueError(f"Chaves ausentes ou duplicadas em {path}: {keys}")
    return table


def integrate(pivots_path: Path, indices_path: Path | None, precip_path: Path | None,
              months: list[str], output_dir: Path) -> Path:
    pivots = read_pivots(pivots_path)
    indices = _table(indices_path, INDEX_COLUMNS, ["pivot_id", "date", "scene_id"])
    precipitation = _table(precip_path, PRECIP_COLUMNS, ["pivot_id", "month"])
    if not indices.empty:
        dates = pd.to_datetime(indices["date"], format="%Y-%m-%d", errors="raise")
        indices["month"] = dates.dt.strftime("%Y-%m")
    else:
        indices["month"] = pd.Series(dtype=str)
    for table in (indices, precipitation):
        if not table["pivot_id"].isin(pivots["pivot_id"]).all() or not table["month"].isin(months).all():
            raise ValueError("Observações locais incompatíveis com os pivôs ou meses do piloto")
    slots = pivots.merge(pd.DataFrame({"month": months}), how="cross")
    # Canonical areas and source URLs come from the inventory, regardless of upstream columns.
    indices = indices.drop(columns=["area_ha", "ana_source", "sentinel_source"], errors="ignore")
    observations = slots.merge(indices, how="left", on=["pivot_id", "month"], validate="one_to_many")
    observations["sentinel_source"] = observations["scene_id"].map(
        lambda scene: f"{SENTINEL_SOURCE}/items/{scene}" if pd.notna(scene) else SENTINEL_SOURCE
    )
    observations["status"] = observations["status"].fillna("no_scene")
    joined = observations.merge(precipitation, how="left", on=["pivot_id", "month"], validate="many_to_one")
    joined["precip_status"] = joined["precip_status"].fillna("no_monthly_data")
    front = [
        "pivot_id", "date", "month", "area_ha", "ndvi_median", "ndmi_median", "precip_mm",
        "valid_pixel_pct", "scene_id", "status", "precip_status", "ana_source",
        "sentinel_source", "chirps_source",
    ]
    ordered = joined[front + [c for c in joined if c not in front]].sort_values(
        ["pivot_id", "month", "date", "scene_id"], na_position="last"
    )
    target = output_dir / "observacoes.csv"
    write_atomic(target, ordered.to_csv(index=False, na_rep="", lineterminator="\n").encode("utf-8"))
    return target
