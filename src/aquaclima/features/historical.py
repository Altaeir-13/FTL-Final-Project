"""Consolidate explicitly selected, checksum-verified monthly acquisition batches."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from aquaclima.features.integration import INDEX_COLUMNS, PRECIP_COLUMNS, SENTINEL_SOURCE, _table, read_pivots
from aquaclima.storage.http import checksum, write_atomic

ALLOWED_BATCH_STATUS = {"complete", "partial", "failed", "planned", "in_progress"}
BATCH_COLUMNS = [
    "month", "batch_status", "query_complete", "catalog_candidate_count", "selected_scene_ids",
    "batch_manifest", "batch_manifest_sha256", "indices_sha256", "pivots_sha256",
]


def _csv(path: Path, frame: pd.DataFrame) -> Path:
    write_atomic(path, frame.to_csv(index=False, na_rep="", lineterminator="\n").encode("utf-8"))
    return path


def _months(months: list[str]) -> list[str]:
    if not months or len(set(months)) != len(months):
        raise ValueError("Forneça uma lista não vazia de meses únicos")
    if any(str(pd.Period(month, freq="M")) != month for month in months):
        raise ValueError("Meses devem seguir o formato YYYY-MM")
    return sorted(months)


def _batch(path: Path, pivots: pd.DataFrame, pivot_hash: str, months: list[str]):
    document = json.loads(path.read_bytes())
    month, status = document["month"], document["status"]
    if month not in months or status not in ALLOWED_BATCH_STATUS:
        raise ValueError(f"Mês ou estado de lote incompatível em {path}")
    if document.get("pivots_sha256") != pivot_hash:
        raise ValueError(f"Inventário de pivôs incompatível em {path}")
    complete = document.get("query_complete", status == "complete")
    if type(complete) is not bool or (status == "complete" and not complete):
        raise ValueError(f"Conclusão da consulta inconsistente em {path}")
    selected = document.get("selected_scene_ids", [])
    if not isinstance(selected, list) or any(not isinstance(scene, str) or not scene for scene in selected):
        raise ValueError(f"Identificadores de cenas inválidos em {path}")
    if len(selected) != len(set(selected)):
        raise ValueError(f"Cenas selecionadas duplicadas em {path}")
    candidate_count = document.get("catalog_candidate_count")
    if candidate_count is not None and (type(candidate_count) is not int or candidate_count < len(selected)):
        raise ValueError(f"Contagem de candidatas inconsistente em {path}")
    root = (path.parent / document["data_root"]).resolve()
    try:
        manifest_name = path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"Manifesto fora de sua raiz de dados em {path}") from exc
    info = {
        "month": month, "batch_status": status, "query_complete": complete,
        "catalog_candidate_count": candidate_count,
        "selected_scene_ids": json.dumps(sorted(selected), separators=(",", ":")),
        "batch_manifest": manifest_name, "batch_manifest_sha256": checksum(path),
        "indices_sha256": document.get("indices_sha256"), "pivots_sha256": pivot_hash,
    }
    if not document.get("indices_path"):
        if status == "complete" and selected:
            raise ValueError(f"Lote concluído com cenas selecionadas e sem índices em {path}")
        return info, pd.DataFrame(columns=INDEX_COLUMNS)
    index_path = (root / document["indices_path"]).resolve()
    if not index_path.is_relative_to(root) or not index_path.is_file():
        raise ValueError(f"Índices ausentes ou fora da raiz de dados em {path}")
    if not document.get("indices_sha256") or checksum(index_path) != document["indices_sha256"]:
        raise ValueError(f"Checksum dos índices inválido em {path}")
    table = _table(index_path, INDEX_COLUMNS, ["pivot_id", "date", "scene_id"])
    dates = pd.to_datetime(table["date"], format="%Y-%m-%d", errors="raise")
    if (not dates.dt.strftime("%Y-%m").eq(month).all()
            or not table["pivot_id"].isin(pivots["pivot_id"]).all()
            or not table["scene_id"].isin(selected).all()):
        raise ValueError(f"Observações fora dos pivôs, mês ou cenas selecionadas em {path}")
    if (table.duplicated(["pivot_id", "scene_id"]).any()
            or table.groupby("scene_id")["date"].nunique().gt(1).any()
            or table["status"].isna().any()):
        raise ValueError(f"Identidade ou estado das observações inconsistente em {path}")
    if status == "complete" and len(table) != len(pivots) * len(selected):
        raise ValueError(f"Lote completo com combinações pivô/cena ausentes em {path}")
    for column in ("ndvi_median", "ndmi_median", "valid_pixel_pct"):
        table[column] = pd.to_numeric(table[column], errors="raise")
        if np.isinf(table[column].to_numpy(dtype=float, na_value=np.nan)).any():
            raise ValueError(f"Valor infinito em {column} no lote {path}")
    accepted = table["status"].eq("ok")
    if (table.loc[accepted, ["ndvi_median", "ndmi_median", "valid_pixel_pct"]].isna().any().any()
            or not table.loc[accepted, ["ndvi_median", "ndmi_median"]].ge(-1).all().all()
            or not table.loc[accepted, ["ndvi_median", "ndmi_median"]].le(1).all().all()
            or not table.loc[accepted, "valid_pixel_pct"].between(0, 100, inclusive="right").all()):
        raise ValueError(f"Observação aceita com índices ou qualidade inválidos em {path}")
    return info, table


def build_dataset(pivots_path: Path, batch_paths: list[Path], precip_path: Path | None,
                  months: list[str], output_dir: Path) -> dict[str, Path]:
    """Create scene attempts, accepted observations and one explicit row per pivot/month.

    Monthly indices are medians of accepted scene medians with equal scene weights.
    No temporal interpolation or cloud-value substitution is applied.
    """
    months = _months(months)
    pivots = read_pivots(pivots_path)
    pivot_hash = checksum(pivots_path)
    batches, tables = [], []
    for path in batch_paths:
        info, table = _batch(Path(path), pivots, pivot_hash, months)
        batches.append(info)
        if not table.empty:
            for column, value in info.items():
                table[column] = value
            tables.append(table)
    manifest = pd.DataFrame(batches, columns=BATCH_COLUMNS)
    if manifest["month"].duplicated().any():
        raise ValueError("A consolidação exige um manifesto explicitamente escolhido por mês")
    attempts = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame(columns=INDEX_COLUMNS + BATCH_COLUMNS)
    attempts = attempts.loc[:, ~attempts.columns.duplicated()].copy()
    if attempts.duplicated(["pivot_id", "date", "scene_id"]).any():
        raise ValueError("Observação pivô/data/cena duplicada entre lotes")
    attempts = attempts.drop(columns=["area_ha", "ana_source", "sentinel_source"], errors="ignore")
    attempts = attempts.merge(pivots, on="pivot_id", how="left", validate="many_to_one")
    attempts["sentinel_source"] = attempts["scene_id"].map(lambda scene: f"{SENTINEL_SOURCE}/items/{scene}")
    precipitation = _table(precip_path, PRECIP_COLUMNS, ["pivot_id", "month"])
    if (not precipitation["pivot_id"].isin(pivots["pivot_id"]).all()
            or not precipitation["month"].isin(months).all()):
        raise ValueError("Precipitação incompatível com os pivôs ou meses solicitados")
    precipitation["precip_mm"] = pd.to_numeric(precipitation["precip_mm"], errors="raise")
    rain_ok = precipitation["precip_status"].eq("ok")
    rain = precipitation["precip_mm"].to_numpy(dtype=float, na_value=np.nan)
    if np.isinf(rain).any() or (rain_ok & (precipitation["precip_mm"].isna() | precipitation["precip_mm"].lt(0))).any():
        raise ValueError("Precipitação aceita com valor inválido")
    attempts = attempts.merge(precipitation, on=["pivot_id", "month"], how="left", validate="many_to_one")
    attempts["precip_status"] = attempts["precip_status"].fillna("no_monthly_data")
    attempts = attempts.sort_values(["pivot_id", "date", "scene_id"]).reset_index(drop=True)
    observations = attempts.loc[attempts["status"].eq("ok")].copy()
    monthly_rows = []
    for (pivot_id, month), rows in attempts.groupby(["pivot_id", "month"], sort=True):
        accepted = rows.loc[rows["status"].eq("ok")]
        dates = pd.to_datetime(accepted["date"], format="%Y-%m-%d")
        scene_ids = sorted(accepted["scene_id"].tolist())
        monthly_rows.append({
            "pivot_id": pivot_id, "month": month, "n_attempted_scenes": len(rows),
            "n_accepted_scenes": len(accepted), "n_accepted_dates": dates.nunique(),
            "ndvi_median": accepted["ndvi_median"].median() if len(accepted) else np.nan,
            "ndmi_median": accepted["ndmi_median"].median() if len(accepted) else np.nan,
            "valid_pixel_pct_median": accepted["valid_pixel_pct"].median() if len(accepted) else np.nan,
            "valid_pixel_pct_min": accepted["valid_pixel_pct"].min() if len(accepted) else np.nan,
            "first_observation_date": accepted["date"].min() if len(accepted) else None,
            "last_observation_date": accepted["date"].max() if len(accepted) else None,
            "observation_day_span": (dates.max() - dates.min()).days if len(accepted) else np.nan,
            "accepted_scene_ids": json.dumps(scene_ids, separators=(",", ":")),
            "attempt_status_counts": json.dumps(rows["status"].value_counts().to_dict(), sort_keys=True),
        })
    columns = [
        "pivot_id", "month", "n_attempted_scenes", "n_accepted_scenes", "n_accepted_dates",
        "ndvi_median", "ndmi_median", "valid_pixel_pct_median", "valid_pixel_pct_min",
        "first_observation_date", "last_observation_date", "observation_day_span",
        "accepted_scene_ids", "attempt_status_counts",
    ]
    aggregate = pd.DataFrame(monthly_rows, columns=columns)
    slots = pivots.merge(pd.DataFrame({"month": months}), how="cross")
    monthly = slots.merge(manifest, on="month", how="left", validate="many_to_one")
    monthly = monthly.merge(aggregate, on=["pivot_id", "month"], how="left", validate="one_to_one")
    monthly = monthly.merge(precipitation, on=["pivot_id", "month"], how="left", validate="one_to_one")
    monthly["batch_status"] = monthly["batch_status"].fillna("not_queried")
    monthly["query_complete"] = monthly["query_complete"].fillna(False).astype(bool)
    for column in ("n_attempted_scenes", "n_accepted_scenes", "n_accepted_dates"):
        monthly[column] = monthly[column].fillna(0).astype(int)
    monthly["monthly_status"] = np.select(
        [monthly["n_accepted_scenes"].gt(0), monthly["batch_status"].eq("not_queried"),
         monthly["batch_status"].eq("complete")],
        ["ok", "not_queried", "no_accepted_observation"], default="incomplete_batch",
    )
    for column in ("selected_scene_ids", "accepted_scene_ids"):
        monthly[column] = monthly[column].fillna("[]")
    monthly["attempt_status_counts"] = monthly["attempt_status_counts"].fillna("{}")
    monthly["precip_status"] = monthly["precip_status"].fillna("no_monthly_data")
    monthly["temporal_aggregation"] = "median_of_scene_medians_equal_weight"
    monthly["sentinel_source"] = SENTINEL_SOURCE
    monthly = monthly.sort_values(["pivot_id", "month"]).reset_index(drop=True)
    return {
        "observations": _csv(output_dir / "observations.csv", observations),
        "attempts": _csv(output_dir / "attempts.csv", attempts),
        "monthly": _csv(output_dir / "monthly.csv", monthly),
    }
