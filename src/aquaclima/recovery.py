"""Separate, audit-gated Sentinel-2 recovery without changing the C1 experiment."""

from __future__ import annotations

import calendar
import hashlib
import json
import logging
import os
import shutil
import time
import tomllib
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from aquaclima.features.historical import _batch
from aquaclima.features.integration import read_pivots
from aquaclima.ingestion.planetary import PC_COLLECTION, PC_ROOT, acquisition_key, search_pc
from aquaclima.storage.http import BudgetError, HttpClient, checksum, read_ledger, write_atomic, write_json

VERSION = 1
LOGGER = logging.getLogger(__name__)
PROVENANCE = ["provider", "collection", "native_scene_id", "acquisition_key", "radiometric_method",
              "calibration_path", "calibration_sha256"]


def _read(path):
    return json.loads(Path(path).read_bytes())


def _inside(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("O caminho de recuperação precisa permanecer no diretório de dados.")
    return path


def _csv(path, frame):
    write_atomic(path, frame.to_csv(index=False, na_rep="", lineterminator="\n").encode())
    return path


def _validate_output(root, policy, output):
    destination = output.resolve()
    for protected in (_inside(root, policy["original_dataset"]), (root / "curated").resolve()):
        if destination.is_relative_to(protected) or protected.is_relative_to(destination):
            raise ValueError("O diretório de saída não pode sobrepor o dataset ou piloto original.")


def settings(args):
    config = tomllib.loads(args.config.read_text(encoding="utf-8"))
    policy, limits = config["recovery"], config["limits"]
    months = policy["months"]
    if (not months or len(months) != len(set(months))
            or any(str(pd.Period(month, freq="M")) != month or not month.startswith("2022-") for month in months)):
        raise ValueError("A recuperação exige meses únicos de 2022 no formato YYYY-MM.")
    if args.start or args.end:
        months = [month for month in months if (not args.start or month >= args.start.strftime("%Y-%m"))
                  and (not args.end or month <= args.end.strftime("%Y-%m"))]
    if not months:
        raise ValueError("O intervalo solicitado não contém meses configurados.")
    policy["months"] = sorted(months)
    if len(months) > 2 and not args.allow_bulk:
        raise ValueError("A expansão além de dois meses exige --allow-bulk e plano explícito.")
    if (type(policy["max_scenes_per_month"]) is not int or not 1 <= policy["max_scenes_per_month"] <= 2
            or policy["min_valid_fraction"] != 0.70):
        raise ValueError("Mantenha a política original: até duas cenas por mês e 70% de pixels válidos.")
    if any(type(limits[key]) is not int or limits[key] <= 0 for key in
           ("max_transfer_bytes", "max_storage_bytes", "max_downloads")):
        raise ValueError("Limites de recursos devem ser inteiros positivos.")
    if limits["max_transfer_bytes"] > 2_000_000_000:
        raise ValueError("A transferência de recuperação não pode exceder 2 GB por execução.")
    for field in ("original_dataset", "compatibility_audit"):
        _inside(args.data_dir, policy[field])
    return policy, limits


def _key(root, policy):
    audit = _inside(root, policy["compatibility_audit"])
    identity = {"version": VERSION, "pivots": checksum(root / "processed/pivots.geojson"),
                "max_scenes": policy["max_scenes_per_month"], "min_valid": policy["min_valid_fraction"],
                "radiometric_audit_sha256": checksum(audit) if audit.is_file() else None}
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:12]


def _paths(root, key, month):
    folder = root / "recovery/batches" / key / month
    return {name: folder / f"{name}.json" for name in ("catalog", "normalized", "selected", "crops", "batch")} | {
        "indices": folder / "indices.csv"}


def _plan_path(root, policy):
    identity = hashlib.sha256(json.dumps(policy["months"]).encode()).hexdigest()[:12]
    return root / "recovery/plans" / f"{_key(root, policy)}_{identity}.json"


def _original_hashes(root, policy):
    original = _inside(root, policy["original_dataset"])
    paths = [*original.rglob("*"), * (root / "curated").glob("*")]
    return {path.relative_to(root).as_posix(): checksum(path) for path in paths if path.is_file()}


def preserve_original(root, policy):
    path = root / "recovery/original_snapshot.json"
    current = _original_hashes(root, policy)
    if not current:
        raise ValueError("O dataset original não está disponível.")
    if path.is_file():
        stored = _read(path)
        if stored["files"] != current:
            raise ValueError("Os arquivos do dataset ou piloto original foram modificados.")
    else:
        write_json(path, {"version": VERSION, "original_dataset": policy["original_dataset"], "files": current})


def verify_compatibility(root, policy):
    path = _inside(root, policy["compatibility_audit"])
    document = _read(path)
    if document.get("status") != "compatible" or document.get("adapter_version") != VERSION or not document.get("checks"):
        raise ValueError("A aquisição alternativa exige auditoria radiométrica compatível e verificável.")
    for record in document["checks"]:
        proof = _inside(root, record["path"])
        if checksum(proof) != record["sha256"]:
            raise ValueError("Uma evidência da auditoria radiométrica foi alterada.")
    return checksum(path)


def make_plan(http, root, policy, limits):
    entries = []
    key = _key(root, policy)
    for month in policy["months"]:
        year, number = map(int, month.split("-"))
        paths = _paths(root, key, month)
        catalog = search_pc(http, root / "processed/pivots.geojson", root,
            start=date(year, number, 1), end=date(year, number, calendar.monthrange(year, number)[1]),
            output_path=paths["catalog"])
        items = _read(catalog)["candidates"]
        acquisitions = len({acquisition_key(item) for item in items})
        audit_path = _inside(root, policy["compatibility_audit"])
        approved = _read(audit_path).get("validated_baselines", []) if audit_path.is_file() else None
        approved_acquisitions = len({acquisition_key(item) for item in items
            if approved is None or item["properties"].get("s2:processing_baseline") in approved})
        # COG layout differs from C1: conservative fixed block overhead, plus
        # observed crop payload. Hard counters remain authoritative at runtime.
        scl = approved_acquisitions * 2_000_000
        spectral = min(approved_acquisitions, policy["max_scenes_per_month"]) * 18_000_000
        complete = paths["batch"].is_file() and _read(paths["batch"]).get("status") == "complete"
        entries.append({"month": month, "products": len(items), "acquisitions": acquisitions,
            "radiometrically_approved_acquisitions": approved_acquisitions,
            "selected_upper_bound": min(approved_acquisitions, policy["max_scenes_per_month"]),
            "catalog_path": catalog.relative_to(root).as_posix(), "catalog_sha256": checksum(catalog),
            "estimated_transfer_bytes": 0 if complete else scl + spectral,
            "estimate_method": "2MB_SCL_per_acquisition_plus_18MB_per_selected_crop_set",
            "already_complete": complete})
    plan = {"version": VERSION, "policy_key": key, "months": entries,
        "pivots_sha256": checksum(root / "processed/pivots.geojson"),
        "max_scenes_per_month": policy["max_scenes_per_month"], "min_valid_fraction": policy["min_valid_fraction"],
        "estimated_transfer_bytes": sum(entry["estimated_transfer_bytes"] for entry in entries),
        "limits": limits, "disk_free_bytes": shutil.disk_usage(root).free,
        "provider": "Microsoft Planetary Computer", "collection": PC_COLLECTION,
        "requires_radiometric_approval": True, "estimate_is_hard_cap": False}
    path = _plan_path(root, policy)
    if not path.is_file() or _read(path) != plan:
        write_json(path, plan)
    return path


def load_plan(root, policy):
    plan = _read(_plan_path(root, policy))
    if (plan["version"] != VERSION or plan["policy_key"] != _key(root, policy)
            or plan["pivots_sha256"] != checksum(root / "processed/pivots.geojson")
            or [entry["month"] for entry in plan["months"]] != policy["months"]
            or plan["max_scenes_per_month"] != policy["max_scenes_per_month"]
            or plan["min_valid_fraction"] != policy["min_valid_fraction"]):
        raise ValueError("Plano de recuperação incompatível. Execute recovery-plan.")
    for entry in plan["months"]:
        paths = _paths(root, plan["policy_key"], entry["month"])
        if _inside(root, entry["catalog_path"]) != paths["catalog"] or checksum(paths["catalog"]) != entry["catalog_sha256"]:
            raise ValueError("Inventário mensal da recuperação ausente ou alterado.")
        document = _read(paths["catalog"])
        year, month_number = map(int, entry["month"].split("-"))
        interval = f"{entry['month']}-01T00:00:00Z/{entry['month']}-{calendar.monthrange(year, month_number)[1]}T23:59:59.999999Z"
        items = document["candidates"]
        if (document.get("query_complete") is not True or document.get("collection") != PC_COLLECTION
                or document.get("parameters", {}).get("pivots_sha256") != plan["pivots_sha256"]
                or document.get("request", {}).get("datetime") != interval
                or document.get("candidate_count") != len(items)
                or len({item["id"] for item in items}) != len(items)
                or document.get("request", {}).get("collections") != [PC_COLLECTION]
                or any(item.get("collection") != PC_COLLECTION or not item["properties"]["datetime"].startswith(entry["month"]) for item in items)):
            raise ValueError("Catálogo de recuperação incompleto ou fora do período.")
        if type(entry["estimated_transfer_bytes"]) is not int or entry["estimated_transfer_bytes"] < 0:
            raise ValueError("Estimativa de transferência inválida.")
    return plan


def _process_month(root, policy, month, http=None):
    from aquaclima.processing.indices import process_indices

    paths = _paths(root, _key(root, policy), month)
    pivots = root / "processed/pivots.geojson"
    audit = verify_compatibility(root, policy)
    if paths["batch"].is_file() and _read(paths["batch"]).get("status") == "complete":
        batch = _read(paths["batch"])
        if batch.get("pivots_sha256") != checksum(pivots):
            raise ValueError("Geometrias diferentes das utilizadas no lote de recuperação.")
        for name in ("selected", "crops", "normalized"):
            if checksum(paths[name]) != batch[f"{name}_sha256"]:
                raise ValueError(f"Manifesto de recuperação alterado: {paths[name]}")
        if batch["compatibility_sha256"] != audit:
            raise ValueError("A auditoria radiométrica do lote foi alterada.")
        for scene in _read(paths["crops"])["scenes"]:
            calibration = scene["radiometric_calibration"]
            if checksum(_inside(root, calibration["xml_path"])) != calibration["xml_sha256"]:
                raise ValueError("XML de calibração do lote foi alterado.")
        with TemporaryDirectory(dir=paths["batch"].parent) as temporary:
            regenerated = process_indices(pivots, paths["crops"], root, min_valid_fraction=0.70,
                output_path=Path(temporary) / "indices.csv", expected_collection=PC_COLLECTION)
            if checksum(regenerated) != batch["indices_sha256"]:
                raise ValueError("Os índices reprocessados diferem do lote de recuperação.")
            if not paths["indices"].is_file() or checksum(paths["indices"]) != batch["indices_sha256"]:
                regenerated.replace(paths["indices"])
        return
    if http is None:
        raise ValueError(f"Lote de recuperação offline ausente/incompleto: {month}")
    LOGGER.info("Recuperação %s: triagem local SCL e até %s datas", month, policy["max_scenes_per_month"])
    from aquaclima.ingestion.planetary import PlanetaryHttp, screen_pc, acquire_pc_crops, normalize_pc_item

    signed = PlanetaryHttp(http)
    native = _read(paths["catalog"])
    if paths["normalized"].is_file():
        normalized = _read(paths["normalized"])
        if (normalized["native_catalog_sha256"] != checksum(paths["catalog"])
                or not http.is_verified(paths["normalized"], source=f"{PC_ROOT}/search")
                or (normalized.get("compatibility_sha256") != audit and normalized["candidates"])):
            raise ValueError("Catálogo normalizado sem integridade ou com origem alterada.")
    else:
        products = {}
        for item in sorted(native["candidates"], key=lambda item: (item["properties"].get("s2:processing_baseline", ""), item["id"]), reverse=True):
            products.setdefault(acquisition_key(item), item)
        existing = set()
        old_attempts = pd.read_csv(_inside(root, policy["original_dataset"]) / "attempts.csv", dtype={"pivot_id": str})
        pivot_count = len(read_pivots(pivots))
        accepted_counts = old_attempts.loc[old_attempts["status"].eq("ok")].groupby("scene_id")["pivot_id"].nunique()
        fully_accepted = set(accepted_counts.loc[accepted_counts.eq(pivot_count)].index)
        for path in (root / "history/batches" / policy["c1_policy_key"]).glob("*/selected.json"):
            existing.update(acquisition_key(item) for item in _read(path)["selected"] if item["id"] in fully_accepted)
        approved = _read(_inside(root, policy["compatibility_audit"]))["validated_baselines"]
        excluded_calibration = [{"id": item["id"], "baseline": item["properties"]["s2:processing_baseline"],
            "reason": "processing_baseline_not_independently_validated"} for item in products.values()
            if item["properties"]["s2:processing_baseline"] not in approved]
        candidates = [normalize_pc_item(signed, item, root) for key, item in sorted(products.items())
            if key not in existing and item["properties"]["s2:processing_baseline"] in approved]
        normalized = {**native, "candidates": candidates, "candidate_count": len(candidates),
            "native_catalog_sha256": checksum(paths["catalog"]),
            "compatibility_sha256": audit,
            "excluded_equivalent_C1": sorted(existing & products.keys()),
            "excluded_radiometry": excluded_calibration,
            "product_preference": "highest_processing_baseline_then_native_product_id"}
        write_json(paths["normalized"], normalized)
        http.record_file(paths["normalized"], source=f"{PC_ROOT}/search")
    selected = screen_pc(signed, pivots, paths["normalized"], root, output_path=paths["selected"],
        max_scenes=policy["max_scenes_per_month"], min_valid_fraction=0.70)
    crops = acquire_pc_crops(signed, pivots, selected, root, manifest_path=paths["crops"])
    indices = process_indices(pivots, crops, root, min_valid_fraction=0.70,
        output_path=paths["indices"], expected_collection=PC_COLLECTION)
    selection, manifest = _read(selected), _read(crops)
    complete = selection["screening_complete"] and all(scene["status"] == "ok" for scene in manifest["scenes"])
    batch = {"schema_version": VERSION, "month": month, "status": "complete" if complete else "partial",
        "policy_key": _key(root, policy), "query_complete": True, "screening_complete": selection["screening_complete"],
        "compatibility_sha256": audit, "pivots_sha256": checksum(pivots),
        "data_root": os.path.relpath(root, paths["batch"].parent),
        "catalog_candidate_count": _read(paths["catalog"])["candidate_count"],
        "selected_scene_ids": selection["selected_ids"]}
    for name in ("selected", "crops", "indices", "normalized"):
        batch[f"{name}_path"] = paths[name].relative_to(root).as_posix()
        batch[f"{name}_sha256"] = checksum(paths[name])
    write_json(paths["batch"], batch)


def _source_rows(root, policy, attempts):
    rows = []
    for path in sorted((root / "history/batches" / policy["c1_policy_key"]).glob("*/selected.json")):
        for item in _read(path)["selected"]:
            rows.append({"scene_id": item["id"], "provider": "Element 84 Earth Search", "collection": "sentinel-2-c1-l2a",
                "native_scene_id": item["id"], "acquisition_key": acquisition_key(item),
                "processing_baseline": item["properties"].get("s2:processing_baseline"),
                "radiometric_method": "C1_STAC_raster_bands_scale_offset", "calibration_path": path.relative_to(root).as_posix(),
                "calibration_sha256": checksum(path)})
    source = pd.DataFrame(rows).drop_duplicates("scene_id")
    joined = attempts.drop(columns=PROVENANCE + ["processing_baseline"], errors="ignore").merge(source, on="scene_id", validate="many_to_one")
    if len(joined) != len(attempts):
        raise ValueError("Proveniência C1 incompleta para as observações originais.")
    return joined


def consolidate(root, policy, output):
    """Combine verified observations; prefer accepted C1 for equivalent acquisitions."""
    _validate_output(root, policy, output)
    verify_compatibility(root, policy)
    preserve_original(root, policy)
    original = _inside(root, policy["original_dataset"])
    old_monthly = pd.read_csv(original / "monthly.csv", dtype={"pivot_id": str, "month": str})
    old = pd.read_csv(original / "attempts.csv", dtype={"pivot_id": str, "month": str})
    old = _source_rows(root, policy, old)
    pivots = read_pivots(root / "processed/pivots.geojson")
    months = sorted(old_monthly["month"].unique())
    parts, batches = [old], {}
    for month in policy["months"]:
        _process_month(root, policy, month)
        paths = _paths(root, _key(root, policy), month)
        info, table = _batch(paths["batch"], pivots, checksum(root / "processed/pivots.geojson"), months)
        batches[month] = info
        if table.empty:
            continue
        crop_manifest = _read(paths["crops"])
        source = []
        for scene in crop_manifest["scenes"]:
            metadata = scene.get("radiometric_calibration", {})
            source.append({"scene_id": scene["id"], "provider": "Microsoft Planetary Computer", "collection": PC_COLLECTION,
                "native_scene_id": scene["native_item_id"],
                "processing_baseline": scene.get("processing_baseline"),
                "acquisition_key": scene["acquisition_key"],
                "radiometric_method": "SAFE_XML_BOA_quantification_and_add_offset",
                "calibration_path": metadata.get("xml_path"),
                "calibration_sha256": metadata.get("xml_sha256")})
        table = table.drop(columns=PROVENANCE + ["processing_baseline"], errors="ignore").merge(pd.DataFrame(source), on="scene_id", validate="many_to_one")
        for column in ("acquisition_key", "calibration_path", "calibration_sha256"):
            if table[column].isna().any():
                raise ValueError(f"Proveniência alternativa ausente: {column}")
        for column, value in info.items():
            table[column] = value
        # Canonical field/precipitation context is carried over unchanged.
        context = old_monthly.loc[old_monthly["month"].eq(month), [column for column in old_monthly
            if column in {"pivot_id", "month", "area_ha", "ana_source", "precip_mm", "precip_status"} or column.startswith("chirps_")]]
        table = table.drop(columns=[column for column in context if column not in {"pivot_id", "month"}], errors="ignore")
        parts.append(table.merge(context, on=["pivot_id", "month"], validate="many_to_one"))
    attempts = pd.concat(parts, ignore_index=True)
    attempts["_accepted_rank"] = attempts["status"].ne("ok").astype(int)
    attempts["_source_rank"] = attempts["collection"].ne("sentinel-2-c1-l2a").astype(int)
    ordered = attempts.sort_values(["pivot_id", "acquisition_key", "_accepted_rank", "_source_rank", "scene_id"])
    duplicate = ordered.duplicated(["pivot_id", "acquisition_key"])
    exclusions = ordered.loc[duplicate].drop(columns=["_accepted_rank", "_source_rank"])
    attempts = ordered.loc[~duplicate].drop(columns=["_accepted_rank", "_source_rank"]).sort_values(["pivot_id", "date", "scene_id"]).reset_index(drop=True)
    observations = attempts.loc[attempts["status"].eq("ok")].copy()
    monthly = old_monthly.copy()
    monthly["collections"] = pd.Series(index=monthly.index, dtype=object)
    monthly["c1_catalog_candidate_count"] = monthly["catalog_candidate_count"]
    monthly["recovery_catalog_product_count"] = 0
    monthly["recovery_batch_manifest"] = pd.Series(index=monthly.index, dtype=object)
    for index, record in monthly.iterrows():
        rows = attempts.loc[attempts["pivot_id"].eq(record["pivot_id"]) & attempts["month"].eq(record["month"])]
        accepted = rows.loc[rows["status"].eq("ok")]
        dates = pd.to_datetime(accepted["date"])
        for target in ("ndvi_median", "ndmi_median"):
            monthly.at[index, target] = accepted[target].median() if len(accepted) else float("nan")
        values = {"n_attempted_scenes": len(rows), "n_accepted_scenes": len(accepted), "n_accepted_dates": dates.nunique(),
            "valid_pixel_pct_median": accepted["valid_pixel_pct"].median(), "valid_pixel_pct_min": accepted["valid_pixel_pct"].min(),
            "first_observation_date": accepted["date"].min() if len(accepted) else None,
            "last_observation_date": accepted["date"].max() if len(accepted) else None,
            "observation_day_span": (dates.max() - dates.min()).days if len(accepted) else float("nan"),
            "accepted_scene_ids": json.dumps(sorted(accepted["scene_id"].tolist()), separators=(",", ":")),
            "selected_scene_ids": json.dumps(sorted(rows["scene_id"].unique()), separators=(",", ":")),
            "attempt_status_counts": json.dumps(rows["status"].value_counts().to_dict(), sort_keys=True),
            "monthly_status": "ok" if len(accepted) else "no_accepted_observation",
            "collections": json.dumps(sorted(accepted["collection"].unique()), separators=(",", ":")),
            "sentinel_source": json.dumps(sorted(accepted["sentinel_source"].dropna().unique()), separators=(",", ":"))}
        if record["month"] in batches:
            batch = batches[record["month"]]
            values["batch_status"] = "complete" if record["batch_status"] == batch["batch_status"] == "complete" else "partial"
            values["query_complete"] = bool(record["query_complete"]) and batch["query_complete"]
            values["recovery_catalog_product_count"] = batch["catalog_candidate_count"]
            values["recovery_batch_manifest"] = batch["batch_manifest"]
        for column, value in values.items():
            monthly.at[index, column] = value
        for field in ("batch_manifest", "batch_manifest_sha256", "indices_sha256"):
            references = set(rows[field].dropna().unique())
            if pd.notna(record[field]):
                references.add(record[field])
            if record["month"] in batches and batches[record["month"]].get(field):
                references.add(batches[record["month"]][field])
            monthly.at[index, field] = json.dumps(sorted(references), separators=(",", ":"))
    collection_rows = []
    for _, record in monthly.iterrows():
        for collection in ("sentinel-2-c1-l2a", PC_COLLECTION):
            rows = attempts.loc[attempts["pivot_id"].eq(record["pivot_id"]) & attempts["month"].eq(record["month"])
                & attempts["collection"].eq(collection)]
            accepted = rows.loc[rows["status"].eq("ok")]
            queried = collection == "sentinel-2-c1-l2a" or record["month"] in batches
            collection_rows.append({"pivot_id": record["pivot_id"], "month": record["month"], "collection": collection,
                "provider": "Element 84 Earth Search" if collection == "sentinel-2-c1-l2a" else "Microsoft Planetary Computer",
                "queried": queried, "attempted_scenes": len(rows), "accepted_scenes": len(accepted),
                "valid_pixel_pct_min": accepted["valid_pixel_pct"].min(), "valid_pixel_pct_median": accepted["valid_pixel_pct"].median(),
                "status_counts": json.dumps(rows["status"].value_counts().to_dict(), sort_keys=True),
                "quality_status": "accepted" if len(accepted) else "no_accepted_observation" if queried else "not_queried"})
    before = old_monthly[["pivot_id", "month", "n_accepted_scenes", "monthly_status", "ndvi_median"]].rename(
        columns={"n_accepted_scenes": "accepted_before", "monthly_status": "status_before", "ndvi_median": "ndvi_before"})
    coverage = before.merge(monthly[["pivot_id", "month", "n_accepted_scenes", "monthly_status", "ndvi_median", "collections"]], on=["pivot_id", "month"])
    coverage["recovered"] = coverage["ndvi_before"].isna() & coverage["ndvi_median"].notna()
    files = {name: _csv(output / f"{name}.csv", frame) for name, frame in
        (("observations", observations), ("attempts", attempts), ("monthly", monthly),
         ("coverage_before_after", coverage), ("collection_quality_coverage", pd.DataFrame(collection_rows)),
         ("duplicate_exclusions", exclusions))}
    write_json(output / "dataset_manifest.json", {"dataset_version": policy["dataset_version"], "schema_version": VERSION,
        "original_dataset": policy["original_dataset"], "original_snapshot_sha256": checksum(root / "recovery/original_snapshot.json"),
        "compatibility_sha256": verify_compatibility(root, policy), "recovery_months": policy["months"],
        "equivalence_policy": "same_platform_SAFE_sensing_time_relative_orbit_mgrs_tile; accepted_C1_then_accepted_PC_then_rejected_C1_then_PC",
        "aggregation": "median_of_scene_medians_equal_weight", "accepted_observations": len(observations),
        "distinct_valid_scenes": observations["scene_id"].nunique(), "recovered_pivot_months": int(coverage["recovered"].sum()),
        "files": {name: {"path": path.name, "sha256": checksum(path)} for name, path in files.items()},
        "pilot_2025_dates_examined": ["2025-06-27", "2025-07-02", "2025-08-26"]})
    preserve_original(root, policy)
    return files


def execute(args):
    policy, limits = settings(args)
    root, started = args.data_dir, time.perf_counter()
    output = (args.output_dir or root / "recovery/curated" / policy["dataset_version"]).resolve()
    _validate_output(root, policy, output)
    if args.dry_run:
        path = _plan_path(root, policy)
        print(json.dumps(_read(path) if path.is_file() else {"status": "plan_required", "path": str(path)}, indent=2))
        return 0
    preserve_original(root, policy)
    if args.command == "recovery-plan":
        if args.offline:
            print(json.dumps(load_plan(root, policy), indent=2))
        else:
            with HttpClient(ledger=root / "recovery/acquisition.jsonl", **limits) as http:
                print(make_plan(http, root, policy, limits))
        return 0
    plan = load_plan(root, policy)
    verify_compatibility(root, policy)
    ledger = root / "recovery/acquisition.jsonl"
    ledger_start = len(read_ledger(ledger))
    failures = []
    if args.command == "recovery-run":
        if args.offline:
            for month in policy["months"]:
                _process_month(root, policy, month)
        else:
            forecast = sum(entry["estimated_transfer_bytes"] for entry in plan["months"]
                if not _paths(root, _key(root, policy), entry["month"])["batch"].is_file()
                or _read(_paths(root, _key(root, policy), entry["month"])["batch"]).get("status") != "complete")
            if forecast > min(limits["max_transfer_bytes"], limits["max_storage_bytes"], shutil.disk_usage(root).free):
                raise BudgetError("A estimativa excede limites ou espaço livre. Reduza o plano.")
            with HttpClient(ledger=ledger, **limits) as http:
                for month in policy["months"]:
                    _process_month(root, policy, month, http)
    files = consolidate(root, policy, output)
    from aquaclima.modeling.seasonal import run_baseline
    from aquaclima.modeling.naive_seasonal import run_naive_benchmark
    from aquaclima.reporting.exploration import generate_exploration
    from aquaclima.reporting.contracts import export_contracts
    generate_exploration(files["monthly"], files["observations"], output)
    run_baseline(files["monthly"], output / "baseline")
    run_naive_benchmark(files["monthly"], output / "naive")
    from aquaclima.modeling.comparison import run_common_month_comparison
    run_common_month_comparison(files["monthly"], output / "baseline", output / "naive", output / "comparison")
    export_contracts(root / "processed/pivots.geojson", output, output / "webgis",
        model_dir=output / "baseline", benchmark_dir=output / "naive")
    events = read_ledger(ledger)
    requests = [event for event in events[ledger_start:] if event["event"] == "http"]
    write_json(output / "execution_report.json", {"mode": "offline" if args.offline else "online",
        "elapsed_s": round(time.perf_counter() - started, 3), "http_requests": len(requests),
        "transferred_bytes": sum(event.get("bytes", 0) for event in requests), "failures": failures,
        "disk_free_bytes": shutil.disk_usage(root).free, "data_storage_bytes": sum(p.stat().st_size for p in root.rglob("*") if p.is_file())})
    from aquaclima.reporting.recovery import summarize_resources
    summarize_resources(root)
    print(output / "dataset_manifest.json")
    return int(any(_read(_paths(root, _key(root, policy), month)["batch"])["status"] != "complete" for month in policy["months"]))
