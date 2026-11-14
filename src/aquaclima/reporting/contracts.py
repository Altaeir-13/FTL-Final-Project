"""Versioned, local WebGIS exchange files with explicit units and provenance."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import shape

from aquaclima.features.integration import read_pivots
from aquaclima.storage.http import checksum, write_atomic

VERSION = "1.0.0"
MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
MODEL_COLUMNS = ["experiment", "pivot_id", "target", "method", "phase", "status", "n_valid_pairs",
                 "expected_months", "coverage_fraction", "mae", "rmse", "bias_mean"]
EVENT_COLUMNS = ["pivot_id", "index", "from_month", "to_month", "from_value", "to_value", "change",
                 "absolute_change_threshold", "elapsed_calendar_months", "unobserved_months_between",
                 "consecutive_calendar_months"]
PREDICTION_COLUMNS = ["experiment", "pivot_id", "target", "method", "phase", "month", "reference_month",
                      "observed", "predicted", "residual", "status"]


def _json_bytes(document) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _csv_bytes(frame: pd.DataFrame) -> bytes:
    data = frame.copy()
    for column in data:
        if pd.api.types.is_bool_dtype(data[column]):
            data[column] = data[column].map({True: "true", False: "false"})
    return data.to_csv(index=False, na_rep="", lineterminator="\n").encode("utf-8")


def _table(path: Path, required: list[str], keys: list[str], pivot_ids: set[str]) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={name: str for name in ("pivot_id", "month", "scene_id", "native_scene_id",
        "acquisition_key", "processing_baseline", "provider", "collection", "calibration_path", "calibration_sha256")})
    if set(required) - set(frame) or frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise ValueError(f"Esquema, chaves ausentes ou duplicadas em {path.name}")
    if not frame["pivot_id"].isin(pivot_ids).all():
        raise ValueError(f"Pivô desconhecido em {path.name}")
    for column in frame.select_dtypes(include="number"):
        if np.isinf(frame[column].to_numpy(dtype=float, na_value=np.nan)).any():
            raise ValueError(f"Valor infinito em {path.name}/{column}")
    return frame


def _schema(required, keys, properties, *, description):
    return {"type": "object", "required": required, "properties": properties,
            "additionalProperties": True, "x-primary-key": keys, "description": description}


def _schemas() -> dict:
    text = {"type": "string"}
    number = {"type": ["number", "null"]}
    pivot = {"type": "string", "minLength": 1}
    month = {"type": "string", "pattern": MONTH_PATTERN}
    index = {"type": ["number", "null"], "minimum": -1, "maximum": 1, "x-unit": "dimensionless"}
    percent = {"type": ["number", "null"], "minimum": 0, "maximum": 100, "x-unit": "percent"}
    basic = {"pivot_id": pivot, "month": month}
    definitions = {
        "observations": _schema(["pivot_id", "date", "month", "scene_id", "status", "ndvi_median", "ndmi_median"],
            ["pivot_id", "date", "scene_id"], basic | {"date": {"type": "string", "format": "date"},
            "scene_id": text, "status": {"const": "ok"}, "ndvi_median": index, "ndmi_median": index,
            "valid_pixel_pct": percent, "processing_baseline": {"type": "string", "pattern": r"^\d{2}\.\d{2}$"},
            "provider": text, "collection": text, "native_scene_id": text, "acquisition_key": text,
            "radiometric_method": text, "calibration_path": text,
            "calibration_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "sentinel_source": text},
            description="Accepted scene-level index medians over one pivot. Processing baseline is a version string, not a decimal number."),
        "monthly": _schema(["pivot_id", "month", "monthly_status", "batch_status", "query_complete",
            "n_accepted_scenes", "ndvi_median", "ndmi_median"], ["pivot_id", "month"], basic | {
            "monthly_status": text, "batch_status": text, "query_complete": {"type": "boolean"},
            "n_accepted_scenes": {"type": "integer", "minimum": 0}, "ndvi_median": index, "ndmi_median": index,
            "temporal_aggregation": {"const": "median_of_scene_medians_equal_weight"}},
            description="One pivot/month slot. Indices aggregate accepted scene medians with equal scene weights."),
        "precipitation": _schema(["pivot_id", "month", "precip_mm", "precip_status"], ["pivot_id", "month"],
            basic | {"precip_mm": {"type": ["number", "null"], "minimum": 0, "x-unit": "mm/month"},
            "precip_status": text, "chirps_source": {"type": ["string", "null"]}},
            description="Regional CHIRPS monthly precipitation context. Nearby pivots may share one grid cell."),
        "quality": _schema(["pivot_id", "month", "monthly_status", "batch_status", "query_complete",
            "n_attempted_scenes", "n_accepted_scenes", "quality_review"], ["pivot_id", "month"], basic | {
            "query_complete": {"type": "boolean"}, "quality_review": {"type": "boolean"},
            "valid_pixel_pct_min": percent, "valid_pixel_pct_median": percent,
            "n_accepted_scenes": {"type": "integer", "minimum": 0}},
            description="Acquisition and observation coverage. Quality review uses zero accepted scenes or minimum valid area below 80%."),
        "models": _schema(MODEL_COLUMNS, ["experiment", "pivot_id", "target", "method", "phase"], {
            "experiment": text, "pivot_id": pivot, "target": {"enum": ["ndvi_median", "ndmi_median"]},
            "method": text, "phase": text, "status": text, "n_valid_pairs": {"type": "integer", "minimum": 0},
            "expected_months": {"type": "integer", "minimum": 1}, "coverage_fraction": {
                "type": "number", "minimum": 0, "maximum": 1}, "mae": number, "rmse": number, "bias_mean": number},
            description="Separate numerical experiment summaries. Missing metrics remain null with their evidence status."),
        "model_predictions": _schema(PREDICTION_COLUMNS,
            ["experiment", "pivot_id", "target", "method", "phase", "month"], {
            "experiment": text, "pivot_id": pivot, "target": {"enum": ["ndvi_median", "ndmi_median"]},
            "method": text, "phase": text, "month": month,
            "reference_month": {"type": ["string", "null"], "pattern": MONTH_PATTERN},
            "observed": index, "predicted": number, "residual": number, "status": text},
            description="Per-month predictions, including missing targets and insufficient-training statuses. Residual is observed minus predicted."),
        "events": _schema(EVENT_COLUMNS + ["event_type"], ["pivot_id", "index", "from_month", "to_month"], {
            "pivot_id": pivot, "index": {"enum": ["ndvi_median", "ndmi_median"]}, "from_month": month,
            "to_month": month, "event_type": {"const": "descriptive_spectral_change"}, "change": number,
            "consecutive_calendar_months": {"type": "boolean"}},
            description="Threshold crossings between successive observed months, with calendar gaps explicitly retained."),
        "pivots": {"type": "object", "required": ["type", "features"], "properties": {
            "type": {"const": "FeatureCollection"}, "features": {"type": "array", "minItems": 1,
            "items": {"type": "object", "required": ["type", "geometry", "properties"], "properties": {
                "type": {"const": "Feature"}, "properties": {"type": "object", "required": ["pivot_id", "area_ha"],
                "properties": {"pivot_id": pivot, "area_ha": {"type": "number", "exclusiveMinimum": 0, "x-unit": "ha"}}},
                "geometry": {"type": "object", "required": ["type", "coordinates"],
                "properties": {"type": {"enum": ["Polygon", "MultiPolygon"]}, "coordinates": {"type": "array"}}}}}}},
            "description": "RFC7946 GeoJSON in WGS84 longitude/latitude. Original ANA attributes retained."},
    }
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "AquaClima WebGIS records",
            "contract_version": VERSION, "$defs": definitions,
            "x-csv-decoding": {"encoding": "UTF-8", "delimiter": ",", "missing": "empty field becomes null",
                "booleans": ["true", "false"], "identifiers": "Keep pivot_id as text, including leading zeroes",
                "typed-decoding": "Decode CSV columns using the corresponding record schema before JSON validation"}}


def _models(model_dir, benchmark_dir, monthly_hash, pivot_ids, sources):
    frames, prediction_frames, parameters, available, reports = [], [], {}, {}, {}
    specifications = (
        ("seasonal_original", model_dir, "validation_metrics.csv", "baseline_report.json"),
        ("naive_contingency", benchmark_dir, "naive_metrics.csv", "naive_report.json"),
    )
    for name, directory, filename, report_name in specifications:
        available[name] = "not_requested" if directory is None else "not_available"
        if directory is None:
            continue
        metric_path, report_path = Path(directory) / filename, Path(directory) / report_name
        if not metric_path.is_file():
            continue
        if not report_path.is_file():
            raise ValueError(f"Relatório de proveniência ausente para {name}")
        report = json.loads(report_path.read_bytes())
        if report.get("monthly_input_sha256") != monthly_hash:
            raise ValueError(f"Experimento {name} pertence a outro conjunto mensal")
        if report.get("evaluation_year", report.get("validation_year")) != 2024:
            raise ValueError(f"Ano de avaliação incompatível em {name}")
        reports[name] = report
        for kind, path in (("metrics", metric_path), ("report", report_path)):
            sources[f"{name}_{kind}"] = {"name": path.name, "sha256": checksum(path), "bytes": path.stat().st_size}
        table = _table(metric_path, ["pivot_id", "target", "method", "phase", "status", "mae", "rmse"],
                       ["pivot_id", "target", "method", "phase"], pivot_ids)
        normalized = table.assign(experiment=name)
        if name == "seasonal_original":
            normalized = normalized.assign(n_valid_pairs=table["scored_months"], expected_months=12,
                coverage_fraction=table["validation_annual_coverage_fraction"], bias_mean=np.nan)
        if (not normalized["target"].isin(("ndvi_median", "ndmi_median")).all()
                or not normalized["n_valid_pairs"].between(0, 12).all()
                or not np.allclose(normalized["coverage_fraction"], normalized["n_valid_pairs"] / normalized["expected_months"])):
            raise ValueError(f"Contagens ou índices incompatíveis em {name}")
        frames.append(normalized[MODEL_COLUMNS])
        prediction_name = "validation_predictions.csv" if name == "seasonal_original" else "naive_pairs.csv"
        prediction_path = Path(directory) / prediction_name
        if not prediction_path.is_file():
            raise ValueError(f"Predições ausentes para {name}")
        prediction_keys = ["pivot_id", "target", "method", "month"] if name == "seasonal_original" else [
            "pivot_id", "target", "method", "evaluation_month"]
        predictions = _table(prediction_path, [*prediction_keys, "observed", "predicted", "residual", "status"],
                             prediction_keys, pivot_ids)
        if name == "naive_contingency":
            predictions = predictions.rename(columns={"evaluation_month": "month"}).assign(
                phase="retrospective_exploratory_2023_to_2024")
        else:
            predictions = predictions.assign(reference_month=None)
            parameter_path = Path(directory) / "model_parameters.json"
            if not parameter_path.is_file():
                raise ValueError(f"Parâmetros ausentes para {name}")
            parameters[name] = json.loads(parameter_path.read_bytes())
            sources[f"{name}_parameters"] = {"name": parameter_path.name, "sha256": checksum(parameter_path),
                                             "bytes": parameter_path.stat().st_size}
        if not predictions["month"].str.fullmatch(r"2024-(0[1-9]|1[0-2])").all():
            raise ValueError(f"Predição fora de 2024 em {name}")
        if not predictions["target"].isin(("ndvi_median", "ndmi_median")).all():
            raise ValueError(f"Índice incompatível nas predições de {name}")
        prediction_frames.append(predictions.assign(experiment=name)[PREDICTION_COLUMNS])
        sources[f"{name}_predictions"] = {"name": prediction_path.name, "sha256": checksum(prediction_path),
                                          "bytes": prediction_path.stat().st_size}
        available[name] = report.get("status", "available")
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=MODEL_COLUMNS),
            pd.concat(prediction_frames, ignore_index=True) if prediction_frames else pd.DataFrame(columns=PREDICTION_COLUMNS),
            parameters, available, reports)


def export_contracts(pivots_path: Path, dataset_dir: Path, output_dir: Path, *,
                     model_dir: Path | None = None, benchmark_dir: Path | None = None) -> Path:
    """Publish an atomic manifest pointing to an immutable content-addressed package."""
    pivots = read_pivots(pivots_path)
    pivot_ids = set(pivots["pivot_id"])
    geojson = json.loads(pivots_path.read_bytes())
    reference = geojson.get("crs", {}).get("properties", {}).get("name")
    if reference not in (None, "EPSG:4326", "urn:ogc:def:crs:OGC:1.3:CRS84"):
        raise ValueError("O contrato GeoJSON exige WGS84 longitude/latitude")
    for feature in geojson["features"]:
        geometry = shape(feature["geometry"])
        if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError("Polígono inválido no contrato de pivôs")
        west, south, east, north = geometry.bounds
        if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
            raise ValueError("Coordenadas fora do domínio geográfico WGS84")
        feature["properties"]["pivot_id"] = str(feature["properties"]["pivot_id"])
    paths = {"pivots": pivots_path, "observations": dataset_dir / "observations.csv", "monthly": dataset_dir / "monthly.csv"}
    sources = {name: {"name": path.name, "sha256": checksum(path), "bytes": path.stat().st_size} for name, path in paths.items()}
    dataset_name = dataset_dir.name
    dataset_manifest = dataset_dir / "dataset_manifest.json"
    if dataset_manifest.is_file():
        identity = json.loads(dataset_manifest.read_bytes())
        if not isinstance(identity.get("dataset_version"), str) or not identity["dataset_version"].strip():
            raise ValueError("A versão do dataset deve ser uma identificação textual não vazia")
        for name in ("observations", "monthly"):
            if identity.get("files", {}).get(name, {}).get("sha256") != sources[name]["sha256"]:
                raise ValueError(f"O manifesto do dataset diverge do arquivo {name}")
        dataset_name = identity["dataset_version"]
        sources["dataset_manifest"] = {"name": dataset_manifest.name, "sha256": checksum(dataset_manifest),
                                        "bytes": dataset_manifest.stat().st_size}
    observations = _table(paths["observations"], ["pivot_id", "month", "date", "scene_id", "status", "ndvi_median", "ndmi_median"],
                          ["pivot_id", "date", "scene_id"], pivot_ids)
    monthly = _table(paths["monthly"], ["pivot_id", "month", "monthly_status", "batch_status", "query_complete",
        "n_attempted_scenes", "n_accepted_scenes", "ndvi_median", "ndmi_median", "precip_mm", "precip_status",
        "valid_pixel_pct_min", "valid_pixel_pct_median", "temporal_aggregation"], ["pivot_id", "month"], pivot_ids)
    for table in (observations, monthly):
        periods = pd.PeriodIndex(table["month"], freq="M")
        if not table["month"].eq(periods.astype(str)).all():
            raise ValueError("Mês inválido no conjunto exportado")
    months = sorted(monthly["month"].unique())
    if not months or len(monthly) != len(months) * len(pivot_ids):
        raise ValueError("O contrato mensal exige todos os espaços pivô/mês solicitados")
    if months != pd.period_range(months[0], months[-1], freq="M").astype(str).tolist():
        raise ValueError("O contrato mensal exige meses consecutivos, inclusive sem observações")
    if not all(isinstance(value, (bool, np.bool_)) for value in monthly["query_complete"]):
        raise ValueError("query_complete deve conter booleanos explícitos")
    for column in ("n_attempted_scenes", "n_accepted_scenes"):
        counts = pd.to_numeric(monthly[column], errors="raise")
        if counts.isna().any() or not counts.ge(0).all() or not np.equal(counts, np.floor(counts)).all():
            raise ValueError(f"Contagem mensal inválida em {column}")
        monthly[column] = counts.astype(int)
    if monthly["n_attempted_scenes"].lt(monthly["n_accepted_scenes"]).any():
        raise ValueError("Quantidade de cenas aceitas maior que a de tentativas")
    if not monthly["monthly_status"].eq("ok").eq(monthly["n_accepted_scenes"].gt(0)).all():
        raise ValueError("Estado mensal incompatível com a contagem de cenas aceitas")
    if not monthly["temporal_aggregation"].eq("median_of_scene_medians_equal_weight").all():
        raise ValueError("Método de agregação temporal incompatível com o contrato")
    if not observations["status"].eq("ok").all() or not observations["month"].isin(months).all():
        raise ValueError("O contrato de observações admite apenas cenas aceitas nos meses declarados")
    dates = pd.to_datetime(observations["date"], format="%Y-%m-%d", errors="raise")
    if not observations["month"].eq(dates.dt.strftime("%Y-%m")).all():
        raise ValueError("Datas e meses das observações divergentes")
    indexed = monthly.set_index(["pivot_id", "month"])
    grouped = observations.groupby(["pivot_id", "month"])
    counts = grouped.size().reindex(indexed.index, fill_value=0)
    if not np.array_equal(counts.to_numpy(), indexed["n_accepted_scenes"].to_numpy()):
        raise ValueError("Contagens mensais divergem das observações exportadas")
    for target in ("ndvi_median", "ndmi_median"):
        medians = grouped[target].median().reindex(indexed.index)
        if not np.allclose(medians.to_numpy(dtype=float), indexed[target].to_numpy(dtype=float), equal_nan=True, atol=1e-8):
            raise ValueError(f"Agregação mensal divergente em {target}")
        if not observations[target].between(-1, 1).all():
            raise ValueError(f"Índice inválido no contrato de observações: {target}")
    for table, columns in ((observations, ("valid_pixel_pct",)),
                           (monthly, ("valid_pixel_pct_min", "valid_pixel_pct_median"))):
        for column in columns:
            if column in table and not table[column].dropna().between(0, 100).all():
                raise ValueError(f"Percentual de qualidade inválido em {column}")
    precipitation_columns = [column for column in monthly if column in {"pivot_id", "month", "precip_mm", "precip_status"}
                             or column.startswith("chirps_")]
    precipitation = monthly[precipitation_columns].copy()
    rain_ok = precipitation["precip_status"].eq("ok")
    if (rain_ok & (precipitation["precip_mm"].isna() | precipitation["precip_mm"].lt(0))).any():
        raise ValueError("Precipitação aceita inválida no contrato")
    quality_columns = ["pivot_id", "month", "monthly_status", "batch_status", "query_complete", "n_attempted_scenes",
                       "n_accepted_scenes", "valid_pixel_pct_min", "valid_pixel_pct_median"]
    quality_columns += [column for column in ("n_accepted_dates", "observation_day_span", "accepted_scene_ids",
        "selected_scene_ids", "batch_manifest_sha256", "indices_sha256", "pivots_sha256") if column in monthly]
    quality = monthly[quality_columns].copy()
    quality["quality_review"] = quality["n_accepted_scenes"].eq(0) | quality["valid_pixel_pct_min"].lt(80)
    models, predictions, parameters, availability, reports = _models(
        model_dir, benchmark_dir, sources["monthly"]["sha256"], pivot_ids, sources)
    event_path = dataset_dir / "pronounced_changes.csv"
    if event_path.is_file():
        events = _table(event_path, EVENT_COLUMNS, ["pivot_id", "index", "from_month", "to_month"], pivot_ids)
        if not events["from_month"].isin(months).all() or not events["to_month"].isin(months).all():
            raise ValueError("Evento fora do intervalo mensal exportado")
        for event in events.to_dict("records"):
            target = event["index"]
            if target not in ("ndvi_median", "ndmi_median"):
                raise ValueError("Índice desconhecido em evento espectral")
            start, end = pd.Period(event["from_month"], freq="M"), pd.Period(event["to_month"], freq="M")
            gap = end.ordinal - start.ordinal
            previous = indexed.loc[(event["pivot_id"], event["from_month"]), target]
            current = indexed.loc[(event["pivot_id"], event["to_month"]), target]
            if (gap < 1 or not np.isfinite(previous) or not np.isfinite(current)
                    or not np.allclose([event["from_value"], event["to_value"], event["change"]],
                                       [previous, current, current - previous], atol=1e-8)
                    or event["elapsed_calendar_months"] != gap or event["unobserved_months_between"] != gap - 1
                    or not isinstance(event["consecutive_calendar_months"], (bool, np.bool_))
                    or event["consecutive_calendar_months"] != (gap == 1)
                    or event["absolute_change_threshold"] <= 0
                    or abs(event["change"]) < event["absolute_change_threshold"]):
                raise ValueError("Evento espectral incompatível com a série mensal")
        sources["events"] = {"name": event_path.name, "sha256": checksum(event_path), "bytes": event_path.stat().st_size}
    else:
        events = pd.DataFrame(columns=EVENT_COLUMNS)
    events["event_type"] = "descriptive_spectral_change"
    provenance = {
        "contract_version": VERSION, "dataset_name": dataset_name, "source_files": sources,
        "months": months, "experiment_availability": availability, "experiment_reports": reports,
        "events_status": "available" if event_path.is_file() else "not_available",
        "quality_review_rule": {"accepted_scene_count": 0, "or_minimum_valid_pixel_pct_below": 80},
        "interpretation": "Exploratory spectral behavior with regional precipitation context; agronomic causes require independent evidence.",
        "path_semantics": "Manifest paths are package-relative. Source batch_manifest fields identify artifacts in the acquisition inventory.",
    }
    tables = {"observations": observations, "monthly": monthly, "precipitation": precipitation,
              "quality": quality, "models": models, "model_predictions": predictions, "events": events}
    payloads = {f"{name}.csv": _csv_bytes(table.sort_values([column for column in ("pivot_id", "month", "date", "scene_id")
        if column in table])) for name, table in tables.items()}
    payloads.update({"pivots.geojson": _json_bytes(geojson), "provenance.json": _json_bytes(provenance),
                     "schemas.json": _json_bytes(_schemas()), "model_parameters.json": _json_bytes(parameters)})
    identity = hashlib.sha256()
    for name, payload in sorted(payloads.items()):
        identity.update(name.encode("utf-8") + b"\0" + hashlib.sha256(payload).digest())
    digest = identity.hexdigest()
    package = output_dir / "packages" / digest
    files = {}
    for name, payload in sorted(payloads.items()):
        target = package / name
        if not target.is_file() or target.read_bytes() != payload:
            write_atomic(target, payload)
        record_name = name.split(".")[0]
        files[record_name] = {"path": target.relative_to(output_dir).as_posix(), "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(), "format": name.rsplit(".", 1)[1],
            "rows": len(tables[record_name]) if record_name in tables else len(pivots) if record_name == "pivots" else None,
            "record_schema": f"packages/{digest}/schemas.json#/$defs/{record_name}" if record_name in {*tables, "pivots"} else None}
    manifest = {"contract_version": VERSION, "package_sha256": digest, "crs": "EPSG:4326",
                "coordinate_order": ["longitude", "latitude"], "files": files}
    target = output_dir / "manifest.json"
    document = _json_bytes(manifest)
    if not target.is_file() or target.read_bytes() != document:
        write_atomic(target, document)
    return target
