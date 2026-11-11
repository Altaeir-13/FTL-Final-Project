"""Incremental monthly acquisition using the pilot's shared local raster cache."""

import calendar
import hashlib
import json
import logging
import os
import shutil
import time
import tomllib
from tempfile import TemporaryDirectory
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd

from aquaclima.features.integration import month_range
from aquaclima.ingestion.chirps import chirps_url, download_precip, extract_precip, usgs_url
from aquaclima.ingestion.sentinel import (
    COLLECTION, estimate_acquisition, search_scenes, screen_scenes, acquire_crops,
)
from aquaclima.processing.indices import process_indices
from aquaclima.storage.http import (
    AcquisitionError, BudgetError, HttpClient, checksum, read_ledger, write_json,
)

LOGGER = logging.getLogger(__name__)
POLICY_VERSION = 1
PILOT_DATES = ["2025-06-27", "2025-07-02", "2025-08-26"]


def _json(path: Path) -> dict:
    return json.loads(path.read_bytes())


def settings(args) -> tuple[dict, dict]:
    config = tomllib.loads(args.config.read_text(encoding="utf-8"))
    policy = config["history"].copy()
    policy["start"] = args.start or policy["start"]
    policy["end"] = args.end or policy["end"]
    start, end = policy["start"], policy["end"]
    if not isinstance(start, date) or not isinstance(end, date) or end < start:
        raise ValueError("Configure datas TOML válidas e ordenadas.")
    if start.year < 2022 or end.year > 2024:
        raise ValueError("Esta fase histórica admite 2022–2024. O ano de 2025 permanece reservado.")
    if start.day != 1 or end.day != calendar.monthrange(end.year, end.month)[1]:
        raise ValueError("Os lotes históricos exigem meses civis completos.")
    if not args.allow_bulk and len(month_range(start, end)) > 3:
        raise ValueError("Uma expansão acima de um trimestre exige --allow-bulk e um novo plano.")
    if type(policy["max_scenes_per_month"]) is not int or not 1 <= policy["max_scenes_per_month"] <= 10:
        raise ValueError("Configure de uma a dez cenas por mês.")
    if not 0 <= policy["min_valid_fraction"] <= 1:
        raise ValueError("A validade mínima precisa estar entre zero e um.")
    policy.setdefault("chirps_provider", "ucsb")
    if policy["chirps_provider"] not in {"ucsb", "usgs"}:
        raise ValueError("Fornecedor CHIRPS precisa ser ucsb ou usgs.")
    limits = config["limits"]
    if any(type(limits[key]) is not int or limits[key] <= 0 for key in (
        "max_transfer_bytes", "max_storage_bytes", "max_downloads",
    )):
        raise ValueError("Limites precisam ser inteiros positivos.")
    return policy, limits


def policy_key(policy: dict, pivots: Path) -> str:
    scientific = {
        "version": POLICY_VERSION, "pivots_sha256": checksum(pivots),
        "max_scenes_per_month": policy["max_scenes_per_month"],
        "min_valid_fraction": policy["min_valid_fraction"],
    }
    return hashlib.sha256(json.dumps(scientific, sort_keys=True).encode()).hexdigest()[:12]


def _paths(root: Path, key: str, month: str) -> dict[str, Path]:
    batch = root / "history/batches" / key / month
    return {name: batch / f"{name}.json" for name in ("catalog", "selected", "crops", "batch")} | {
        "indices": batch / "indices.csv",
    }


def _dates(month: str) -> tuple[date, date]:
    year, number = map(int, month.split("-"))
    return date(year, number, 1), date(year, number, calendar.monthrange(year, number)[1])


def _plan_path(root: Path, policy: dict, key: str) -> Path:
    provider = policy.get("chirps_provider", "ucsb")
    suffix = "" if provider == "ucsb" else f"_{provider}"
    return root / "history/plans" / f"{policy['start']}_{policy['end']}_{key}{suffix}.json"


def _save(http, path, document, source):
    if path.is_file() and _json(path) == document:
        return
    data_size = len(json.dumps(document).encode("utf-8")) * 2
    http.ensure_storage(data_size)
    write_json(path, document)
    http.record_file(path, source=source)


def _history_origin(root: Path) -> int:
    path = root / "history/origin.json"
    if not path.is_file():
        write_json(path, {
            "ledger_start": len(read_ledger(root / "acquisition.jsonl")),
            "started_at_utc": datetime.now(UTC).isoformat(),
            "pilot_2025_dates_examined": PILOT_DATES,
        })
    return _json(path)["ledger_start"]


def make_plan(http: HttpClient, root: Path, policy: dict, limits: dict, pivots: Path) -> Path:
    key = policy_key(policy, pivots)
    target = _plan_path(root, policy, key)
    months = month_range(policy["start"], policy["end"])
    entries = []
    climate_paused = None
    provider = policy.get("chirps_provider", "ucsb")
    for month in months:
        LOGGER.info("Inventário e estimativa %s", month)
        paths = _paths(root, key, month)
        start, end = _dates(month)
        catalog = search_scenes(
            http, pivots, root, start=start, end=end, max_cloud=100, max_scenes=500,
            plan_path=paths["catalog"], allow_empty=True,
        )
        estimate = estimate_acquisition(
            pivots, catalog, root, max_scenes=policy["max_scenes_per_month"],
        )
        source = usgs_url(month) if provider == "usgs" else chirps_url(month)
        domain = "usgs" if provider == "usgs" else "latam"
        climate = root / "raw/chirps" / domain / source.rsplit("/", 1)[1]
        header_path = root / "history/planning/chirps" / domain / f"{month}.json"
        if _climate_cached(root, month):
            previous = _json(root / "history/chirps.json")["months"][month]
            rain = {"source": previous["source"], "bytes": previous["size_bytes"],
                    "cached": True, "status": "available"}
        elif http.is_verified(climate, source=source):
            rain = {"source": source, "bytes": climate.stat().st_size, "cached": True, "status": "available"}
        elif header_path.is_file() and _json(header_path).get("source") == source:
            rain = _json(header_path) | {"cached": False}
        elif climate_paused:
            rain = {"source": source, "bytes": 30_000_000, "cached": False,
                    "status": "unverified", "request_skipped": True, "error": climate_paused}
        else:
            try:
                headers = {key.lower(): value for key, value in http.head(source).items()}
                size = int(headers.get("content-length", 0))
                if size <= 0:
                    raise ValueError("CHIRPS sem Content-Length para estimativa")
                rain = {
                    "source": source, "bytes": size, "cached": False, "status": "available",
                    "etag": headers.get("etag"), "last_modified": headers.get("last-modified"),
                }
            except (AcquisitionError, ValueError) as exc:
                if isinstance(exc, AcquisitionError) and exc.status_code in {403, 429}:
                    climate_paused = str(exc)
                rain = {"source": source, "bytes": 30_000_000, "cached": False,
                        "status": "unverified", "error": str(exc)}
            _save(http, header_path, rain, source)
        expected = estimate["estimated_transfer_bytes"] + (0 if rain["cached"] else rain["bytes"])
        entries.append({
            "month": month, "catalog_path": catalog.relative_to(root).as_posix(),
            "catalog_sha256": checksum(catalog), "sentinel": estimate,
            "chirps": rain, "estimated_transfer_bytes": expected,
        })
    document = {
        "schema_version": 1, "policy_key": key, "pivots_sha256": checksum(pivots),
        "start": str(policy["start"]), "end": str(policy["end"]),
        "max_scenes_per_month": policy["max_scenes_per_month"],
        "min_valid_fraction": policy["min_valid_fraction"], "months": entries,
        "chirps_provider": provider,
        "estimated_transfer_bytes": sum(entry["estimated_transfer_bytes"] for entry in entries),
        "estimated_storage_bytes": sum(entry["estimated_transfer_bytes"] for entry in entries),
        "storage_estimate_rule": "conservative storage upper estimate equal to estimated payload",
        "limits_at_planning": limits,
        "disk_free_at_planning": shutil.disk_usage(root).free,
        "estimate_is_hard_cap": False,
        "pilot_2025_dates_examined": PILOT_DATES,
    }
    _save(http, target, document, "AquaClima monthly acquisition plan")
    return target


def _load_plan(root, policy, pivots):
    key = policy_key(policy, pivots)
    path = _plan_path(root, policy, key)
    if not path.is_file():
        raise ValueError(f"Gere history-plan antes da aquisição. Plano esperado em {path}")
    plan = _json(path)
    if (plan["schema_version"] != 1 or plan["policy_key"] != key or plan["pivots_sha256"] != checksum(pivots)
            or plan["start"] != str(policy["start"]) or plan["end"] != str(policy["end"])):
        raise ValueError("Plano incompatível com a configuração histórica atual.")
    if (plan["max_scenes_per_month"] != policy["max_scenes_per_month"]
            or plan["min_valid_fraction"] != policy["min_valid_fraction"]
            or plan.get("chirps_provider", "ucsb") != policy.get("chirps_provider", "ucsb")):
        raise ValueError("Parâmetros científicos do plano diferem da configuração.")
    expected = month_range(policy["start"], policy["end"])
    if [entry["month"] for entry in plan["months"]] != expected:
        raise ValueError("O plano precisa conter exatamente os meses solicitados, sem duplicatas.")
    for entry in plan["months"]:
        if any(type(entry[field]) is not int or entry[field] < 0 for field in ("estimated_transfer_bytes",)):
            raise ValueError("Estimativa mensal inválida no plano.")
        if (type(entry["sentinel"]["estimated_transfer_bytes"]) is not int
                or entry["sentinel"]["estimated_transfer_bytes"] < 0
                or type(entry["chirps"]["bytes"]) is not int or entry["chirps"]["bytes"] <= 0):
            raise ValueError("Estimativas de fonte inválidas no plano.")
        catalog = (root / entry["catalog_path"]).resolve()
        wanted = _paths(root, key, entry["month"])["catalog"]
        if catalog != wanted or checksum(catalog) != entry["catalog_sha256"]:
            raise ValueError(f"Inventário mensal ausente ou alterado em {entry['month']}.")
        document = _json(catalog)
        start, end = _dates(entry["month"])
        interval = f"{start}T00:00:00Z/{end}T23:59:59.999999Z"
        if (document.get("collection") != COLLECTION or document.get("query_complete") is not True
                or document.get("request", {}).get("datetime") != interval
                or document.get("parameters", {}).get("pivots_sha256") != checksum(pivots)
                or document.get("candidate_count") != len(document["candidates"])):
            raise ValueError(f"Consulta do catálogo incompatível com o mês {entry['month']}.")
        for item in document["candidates"]:
            observed = datetime.fromisoformat(item["properties"]["datetime"]).date()
            if item.get("collection") != COLLECTION or not start <= observed <= end:
                raise ValueError(f"Item STAC fora do mês ou coleção em {entry['month']}.")
    return plan


def _verify_batch(batch_path, pivots, root):
    batch = _json(batch_path)
    if batch["pivots_sha256"] != checksum(pivots):
        raise ValueError(f"Pivôs incompatíveis em {batch_path}")
    for name in ("selected", "crops"):
        path = root / batch[f"{name}_path"]
        if not path.resolve().is_relative_to(root) or checksum(path) != batch[f"{name}_sha256"]:
            raise ValueError(f"Manifesto {name} alterado em {batch_path}")
    return batch


def _offline_month(pivots, paths, root, policy):
    batch = _verify_batch(paths["batch"], pivots, root)
    with TemporaryDirectory(dir=paths["batch"].parent) as temporary:
        indices = process_indices(
            pivots, paths["crops"], root, min_valid_fraction=policy["min_valid_fraction"],
            output_path=Path(temporary) / "indices.csv",
        )
        if checksum(indices) != batch["indices_sha256"]:
            raise ValueError(f"Índices reprocessados diferem do lote registrado em {paths['batch']}")
        if not paths["indices"].is_file() or checksum(paths["indices"]) != batch["indices_sha256"]:
            indices.replace(paths["indices"])


def _climate_cached(root: Path, month: str) -> bool:
    manifest = root / "history/chirps.json"
    if not manifest.is_file():
        return False
    entry = _json(manifest).get("months", {}).get(month, {})
    if entry.get("status") != "available":
        return False
    path = (root / entry["path"]).resolve()
    return (path.is_relative_to((root / "raw/chirps").resolve()) and path.is_file()
            and path.stat().st_size == entry["size_bytes"] and checksum(path) == entry["sha256"])


def _acquire_month(http, pivots, root, policy, key, month):
    paths = _paths(root, key, month)
    if paths["batch"].is_file() and _json(paths["batch"])["status"] == "complete":
        try:
            _offline_month(pivots, paths, root, policy)
            return
        except (OSError, ValueError, KeyError) as exc:
            LOGGER.warning("Revalidando lote %s após falha de integridade: %s", month, exc)
    if not paths["batch"].is_file():
        _save(http, paths["batch"], {
            "schema_version": 1, "month": month, "policy_key": key, "status": "in_progress",
            "query_complete": True, "screening_complete": False,
            "data_root": os.path.relpath(root, paths["batch"].parent),
            "pivots_sha256": checksum(pivots), "catalog_candidate_count": _json(paths["catalog"])["candidate_count"],
            "selected_scene_ids": [],
        }, "AquaClima monthly batch")
    selected = screen_scenes(
        http, pivots, paths["catalog"], root, output_path=paths["selected"],
        max_scenes=policy["max_scenes_per_month"], min_valid_fraction=policy["min_valid_fraction"],
    )
    crops = acquire_crops(http, pivots, selected, root, manifest_path=paths["crops"])
    indices = process_indices(
        pivots, crops, root, min_valid_fraction=policy["min_valid_fraction"], output_path=paths["indices"],
    )
    selection = _json(selected)
    manifest = _json(crops)
    complete = selection["screening_complete"] and all(s["status"] == "ok" for s in manifest["scenes"])
    batch = {
        "schema_version": 1, "month": month, "policy_key": key, "status": "complete" if complete else "partial",
        "query_complete": True, "screening_complete": selection["screening_complete"],
        "data_root": os.path.relpath(root, paths["batch"].parent),
        "pivots_sha256": checksum(pivots), "catalog_candidate_count": _json(paths["catalog"])["candidate_count"],
        "selected_scene_ids": selection["selected_ids"], "min_valid_fraction": policy["min_valid_fraction"],
    }
    for name, path in (("selected", selected), ("crops", crops), ("indices", indices)):
        batch[f"{name}_path"] = path.relative_to(root).as_posix()
        batch[f"{name}_sha256"] = checksum(path)
    _save(http, paths["batch"], batch, "AquaClima monthly batch")


def consolidate(root, policy, pivots, output):
    from aquaclima.features.historical import build_dataset

    key = policy_key(policy, pivots)
    months = month_range(policy["start"], policy["end"])
    batches = [_paths(root, key, month)["batch"] for month in months]
    available = [path for path in batches if path.is_file()]
    rain_manifest = root / "history/chirps.json"
    precipitation = None
    if rain_manifest.is_file():
        precipitation = extract_precip(
            pivots, rain_manifest, root, months=months,
            output_path=root / "history/processed" / f"precip_{policy['start']}_{policy['end']}.csv",
        )
    return build_dataset(pivots, available, precipitation, months, output)


def _report(root, output, started, ledger_start, failures, policy, key, *, offline):
    from aquaclima.reporting.exploration import generate_exploration
    from aquaclima.modeling.seasonal import run_baseline

    datasets = consolidate(root, policy, root / "processed/pivots.geojson", output)
    generate_exploration(datasets["monthly"], datasets["observations"], output)
    run_baseline(datasets["monthly"], output / "baseline")
    events = read_ledger(root / "acquisition.jsonl")
    requests = [event for event in events[ledger_start:] if event["event"] == "http"]
    origin = _json(root / "history/origin.json")["ledger_start"]
    historical_requests = [event for event in events[origin:] if event["event"] == "http"]
    monthly = pd.read_csv(datasets["monthly"])
    observations = pd.read_csv(datasets["observations"])
    attempts = pd.read_csv(datasets["attempts"])
    monthly_counts = monthly.groupby("month")["ndvi_median"].count()
    climate = root / "history/chirps.json"
    climate_entries = _json(climate)["months"] if climate.is_file() else {}
    batches = [_paths(root, key, month)["batch"] for month in month_range(policy["start"], policy["end"])]
    report = {
        "mode": "offline" if offline else "online", "elapsed_s": round(time.perf_counter() - started, 3),
        "start": str(policy["start"]), "end": str(policy["end"]), "policy_key": key,
        "batch_status": {path.parent.name: _json(path)["status"] if path.is_file() else "not_acquired" for path in batches},
        "valid_observations": len(observations), "attempted_observations": len(attempts),
        "distinct_valid_scenes": observations["scene_id"].nunique(),
        "monthly_rows": len(monthly), "observed_pivot_months": int(monthly["ndvi_median"].notna().sum()),
        "observed_pivots_by_month": monthly_counts.to_dict(),
        "observed_months_by_pivot": monthly.groupby("pivot_id")["ndvi_median"].count().to_dict(),
        "climate_month_status": {
            month: climate_entries.get(month, {}).get("status", "not_acquired")
            for month in month_range(policy["start"], policy["end"])
        },
        "climate_month_sources": {
            month: climate_entries.get(month, {}).get("source")
            for month in month_range(policy["start"], policy["end"])
        },
        "requests": len(requests), "payload_bytes": sum(row["bytes"] for row in requests),
        "history_requests": len(historical_requests),
        "history_payload_bytes": sum(row["bytes"] for row in historical_requests),
        "history_payload_by_host": dict(_bytes_by_host(historical_requests)),
        "storage_bytes_under_data_dir": sum(p.stat().st_size for p in root.rglob("*") if p.is_file()),
        "request_failures": [r for r in requests if r.get("error")], "stage_failures": failures,
        "dataset_sha256": {name: checksum(path) for name, path in datasets.items()},
        "pilot_2025_dates_examined": PILOT_DATES,
    }
    write_json(output / "report.json", report)
    return report


def _bytes_by_host(requests):
    counts = Counter()
    for row in requests:
        counts[urlsplit(row["url"]).netloc] += row["bytes"]
    return counts


def execute(args) -> int:
    policy, limits = settings(args)
    root = args.data_dir
    pivots = root / "processed/pivots.geojson"
    key = policy_key(policy, pivots)
    output = args.output_dir or root / "history/curated" / f"{policy['start']}_{policy['end']}_{key}"
    output = output.resolve()
    plan_path = _plan_path(root, policy, key)
    if args.dry_run:
        document = _load_plan(root, policy, pivots) if plan_path.is_file() else {
            "status": "plan_required", "expected_plan": str(plan_path),
            "months": month_range(policy["start"], policy["end"]),
        }
        print(json.dumps({"plan": document, "limits": limits, "disk_free": shutil.disk_usage(root).free}, indent=2))
        return 0
    started = time.perf_counter()
    baseline = len(read_ledger(root / "acquisition.jsonl"))
    _history_origin(root)
    if args.command == "history-plan":
        if args.offline:
            print(json.dumps(_load_plan(root, policy, pivots), indent=2))
            return 0
        with HttpClient(ledger=root / "acquisition.jsonl", **limits) as http:
            print(make_plan(http, root, policy, limits, pivots))
        return 0
    if args.command == "history-baseline":
        from aquaclima.modeling.seasonal import run_baseline
        print(run_baseline(output / "monthly.csv", output / "baseline"))
        return 0
    if args.command == "history-explore":
        from aquaclima.reporting.exploration import generate_exploration
        print(generate_exploration(output / "monthly.csv", output / "observations.csv", output))
        return 0
    failures = []
    months = month_range(policy["start"], policy["end"])
    if args.command == "history-run":
        plan = _load_plan(root, policy, pivots)
        if args.offline:
            for month in months:
                paths = _paths(root, key, month)
                if paths["batch"].is_file() and _json(paths["batch"]).get("indices_path"):
                    _offline_month(pivots, paths, root, policy)
                else:
                    failures.append(f"{month}: lote local ausente ou ainda incompleto")
        else:
            remaining = [
                entry for entry in plan["months"]
                if not (_paths(root, key, entry["month"])["batch"].is_file()
                        and _json(_paths(root, key, entry["month"])["batch"])["status"] == "complete")
            ]
            forecast = sum(entry["sentinel"]["estimated_transfer_bytes"] for entry in remaining)
            forecast += sum(entry["chirps"]["bytes"] for entry in plan["months"]
                            if not _climate_cached(root, entry["month"]))
            if forecast > min(limits["max_transfer_bytes"], limits["max_storage_bytes"], shutil.disk_usage(root).free):
                raise BudgetError("Estimativa excede orçamento ou espaço livre. Reduza o intervalo ou ajuste limites explicitamente.")
            with HttpClient(ledger=root / "acquisition.jsonl", **limits) as http:
                exhausted = False
                for month in months:
                    LOGGER.info("Lote histórico %s", month)
                    try:
                        _acquire_month(http, pivots, root, policy, key, month)
                    except BudgetError as exc:
                        failures.append(f"{month}: {exc}")
                        exhausted = True
                        break
                    except (AcquisitionError, ValueError, OSError, KeyError) as exc:
                        LOGGER.error("%s: %s", month, exc)
                        failures.append(f"{month}: {exc}")
                if not exhausted:
                    try:
                        download_precip(
                            http, root, months, manifest_path=root / "history/chirps.json",
                            provider=policy.get("chirps_provider", "ucsb"),
                        )
                    except (AcquisitionError, BudgetError, ValueError, OSError) as exc:
                        failures.append(f"CHIRPS: {exc}")
    report = _report(root, output, started, baseline, failures, policy, key, offline=args.offline)
    print(output / "report.json")
    return int(
        bool(failures) or any(status != "complete" for status in report["batch_status"].values())
        or any(status != "available" for status in report["climate_month_status"].values())
    )
