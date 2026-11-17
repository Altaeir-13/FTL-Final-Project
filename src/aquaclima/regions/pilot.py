"""Bounded regional portability experiment using AquaClima's existing pipeline.

No model fitting occurs here. The official selection decision must precede any
raster request. Original study directories are read only cache sources.
"""
from __future__ import annotations

import argparse
import calendar
import json
import math
import re
import shutil
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from aquaclima.features.historical import build_dataset
from aquaclima.features.integration import month_range
from aquaclima.ingestion.chirps import download_precip, extract_precip
from aquaclima.ingestion.planetary import parse_product_calibration
from aquaclima.ingestion.sentinel import (
    COLLECTION, _asset_band, _cache_json, acquire_crops, read_pivots,
    screen_scenes, search_scenes,
)
from aquaclima.processing.indices import process_indices
from aquaclima.storage.http import HttpClient, checksum, read_ledger, write_json

MONTHS = ("2023-01", "2023-07", "2023-11", "2024-03", "2024-07", "2024-11")
POLICY = {"version": 1, "months": list(MONTHS), "min_valid_fraction": .70,
          "max_scenes_per_month": 1, "max_screened_candidates_per_month": 3,
          "cloud_limit_pct": 40, "collection": COLLECTION,
          "month_selection": "Declared after catalog selection, before raster acquisition: six available months across 2023/24; March 2023 lacked a cloud<=40 candidate, so January 2023 is targeted. Uneven/nonrandom sampling.",
          "temporal_inference": "descriptive only; six prespecified months, no annual seasonality claim"}


def product_radiometry(http: HttpClient, item: dict, root: Path) -> dict:
    """Check each C1 product against its own ESA XML, without PC approvals."""
    if re.fullmatch(r"[A-Za-z0-9_-]+", item["id"]) is None:
        raise ValueError("Identificador de produto incompatível com o cache regional.")
    properties = item["properties"]
    asset = item["assets"].get("product_metadata", {})
    url = asset.get("href", "")
    if not url.startswith("https://"):
        raise ValueError("Produto C1 sem XML radiométrico público.")
    path = root / "radiometry" / f"{item['id']}.xml"
    payload = http.get_bytes(url, path=path)
    expected = asset.get("file:checksum")
    if expected and expected != "1220" + checksum(path):
        raise ValueError("XML ESA diverge do checksum STAC.")
    calibration = parse_product_calibration(payload, product_uri=properties["s2:product_uri"],
                                             baseline=properties["s2:processing_baseline"])
    for name in ("red", "nir", "swir16"):
        band = _asset_band(item, name)
        if any(not math.isclose(band[field], calibration["bands"][name][field], abs_tol=1e-12)
               for field in ("scale", "offset")):
            raise ValueError(f"Escala/offset C1 divergem do próprio XML ESA: {item['id']}/{name}")
    return {"scene_id": item["id"], "collection": COLLECTION,
            "provider": "Element 84 Earth Search", "product": properties["s2:product_uri"],
            "processing_baseline": properties["s2:processing_baseline"],
            "method": "C1 raster:bands independently matched to product-specific ESA BOA XML; downloaded COG grid checked",
            "xml_path": path.relative_to(root).as_posix(), "xml_source": url, "xml_sha256": checksum(path),
            "calibration": calibration,
            "bands": {name: _asset_band(item, name) for name in ("red", "nir", "swir16")}}


def read_json(path: Path):
    return json.loads(path.read_bytes())


def selected_study(decision_path: Path, root: Path) -> tuple[dict, Path]:
    decision = read_json(decision_path)
    winner = decision.get("winner")
    if not winner or not winner.get("eligible") or len(winner.get("sample_FIDs", [])) < 3:
        raise ValueError("A decisão regional não autoriza um piloto de três pivôs.")
    if root.resolve().parent.name != "regions" or not re.fullmatch(r"[a-z0-9-]+", root.name):
        raise ValueError("O piloto exige um namespace independente em data/regions/<região>.")
    source = decision_path.parent / f"sample-{winner['code']}.geojson"
    pivots = read_pivots(source)
    document = read_json(source)
    fids = [f["properties"]["FID"] for f in document["features"]]
    if sorted(fids) != sorted(winner["sample_FIDs"]) or len(pivots) not in range(3, 6):
        raise ValueError("A amostra diverge da decisão oficial.")
    for feature in document["features"]:
        props = feature["properties"]
        if props["UF"] != winner["UF"] or props["MUNIC_CD"] != winner["code"]:
            raise ValueError("A amostra mistura municípios ou regiões.")
        if props["pivot_id"] != f"{winner['UF']}:{props['FID']}":
            raise ValueError("Chave regional ambígua.")
    destination = root / "pivots.geojson"
    root.mkdir(parents=True, exist_ok=True)
    if destination.exists() and checksum(source) != checksum(destination):
        raise ValueError("O namespace existente pertence a outra amostra.")
    if not destination.exists():
        shutil.copyfile(source, destination)
    config = POLICY | {"region_id": root.name, "municipality": winner["name"], "UF": winner["UF"],
                       "municipality_code": winner["code"], "decision_sha256": checksum(decision_path),
                       "pivots_sha256": checksum(destination)}
    config_path = root / "policy.json"
    if config_path.exists() and read_json(config_path) != config:
        raise ValueError("A política existente não pode ser substituída silenciosamente.")
    write_json(config_path, config)
    return config, destination


def copy_climate_cache(http: HttpClient, original: Path, root: Path) -> None:
    """Copy verified global/regional CHIRPS rasters without editing the source."""
    source_manifest = original / "history/chirps.json"
    target_manifest = root / "chirps.json"
    if target_manifest.exists() or not source_manifest.exists():
        return
    document = read_json(source_manifest)
    retained = {}
    for month in MONTHS:
        entry = document["months"].get(month, {})
        if entry.get("status") != "available":
            continue
        source = (original / entry["path"]).resolve()
        if not source.is_relative_to((original / "raw/chirps").resolve()):
            raise ValueError("Cache CHIRPS fora da raiz declarada.")
        if not source.is_file() or checksum(source) != entry["sha256"] or source.stat().st_size != entry["size_bytes"]:
            raise ValueError("Cache CHIRPS original sem integridade.")
        target = root / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        http.ensure_storage(source.stat().st_size)
        shutil.copyfile(source, target)
        http.record_file(target, source=entry["source"])
        retained[month] = entry | {"cache_reuse": "verified preexisting CHIRPS v3 raster; new regional extraction"}
    write_json(target_manifest, {"product": document["product"], "months": retained})


def verify_inventory(root: Path) -> None:
    inventory = read_json(root / "inventory.json")
    for name, record in inventory["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError(f"Arquivo regional ausente ou externo: {name}")
        if path.stat().st_size != record["bytes"] or checksum(path) != record["sha256"]:
            raise ValueError(f"Arquivo regional adulterado: {name}")


def consolidate(root: Path, pivots: Path, output: Path) -> dict:
    batches = []
    for month in MONTHS:
        directory = root / "batches" / month
        manifest = directory / "crops.json"
        batch = read_json(directory / "batch.json")
        recomputed = output / "verification-indices" / f"{month}.csv"
        process_indices(pivots, manifest, root, min_valid_fraction=.70, output_path=recomputed)
        if checksum(recomputed) != batch["indices_sha256"]:
            raise ValueError("Reprocessamento espectral diverge do lote adquirido.")
        batches.append(directory / "batch.json")
    # Keep every calendar slot, including the 17 months not targeted by this pilot.
    months = month_range(date(2023, 1, 1), date(2024, 11, 30))
    precip = extract_precip(pivots, root / "chirps.json", root, months=months,
                            output_path=output / "precipitation.csv")
    paths = build_dataset(pivots, batches, precip, months, output)
    accepted = pd.read_csv(paths["observations"], dtype={"pivot_id": str})
    monthly = pd.read_csv(paths["monthly"], dtype={"pivot_id": str})
    summary = {"region_id": root.name, "validation_state": "exploratory_portability",
               "target_months": list(MONTHS), "calendar_slots": len(monthly),
               "pivot_count": len(read_pivots(pivots)), "accepted_observations": len(accepted),
               "accepted_scenes": int(accepted["scene_id"].nunique()),
               "observed_months": sorted(accepted["month"].unique().tolist()),
               "observed_pivot_months": int(monthly["monthly_status"].eq("ok").sum()),
               "rain_target_slots_ok": int((monthly["month"].isin(MONTHS) & monthly["precip_status"].eq("ok")).sum()),
               "minimum_accepted_valid_pixel_pct": float(accepted["valid_pixel_pct"].min()) if len(accepted) else None,
               "models": "not fitted; no regional generalization metrics",
               "policy_sha256": checksum(root / "policy.json"), "pivots_sha256": checksum(pivots),
               "files": {key: {"path": path.name, "sha256": checksum(path), "bytes": path.stat().st_size}
                         for key, path in (paths | {"precipitation": precip}).items()}}
    write_json(output / "summary.json", summary)
    return summary


def run(decision_path: Path, root: Path, *, original: Path, offline: bool = False, output: Path | None = None):
    config, pivots = selected_study(decision_path, root)
    output = output or root / ("reproduced/v1" if offline else "curated/v1")
    if not output.resolve().is_relative_to(root.resolve()):
        raise ValueError("Saída regional fora do namespace.")
    if offline:
        if not output.resolve().is_relative_to((root / "reproduced").resolve()):
            raise ValueError("A reprodução offline exige saída independente em reproduced/.")
        verify_inventory(root)
        with patch("requests.Session.request", side_effect=AssertionError("HTTP proibido na reprodução regional")):
            summary = consolidate(root, pivots, output)
        reference = root / "curated/v1"
        names = ["observations.csv", "attempts.csv", "monthly.csv", "precipitation.csv", "summary.json"]
        if any(checksum(output / name) != checksum(reference / name) for name in names):
            raise ValueError("Reprodução regional não é byte a byte idêntica.")
        result = {"status": "identical", "files_checked": len(names), "http_requests": 0, "transferred_bytes": 0}
        write_json(root / "offline-verification.json", result)
        return result
    with HttpClient(ledger=root / "acquisition.jsonl", max_transfer_bytes=150_000_000,
                    max_storage_bytes=250_000_000, max_downloads=1800, attempts=3) as http:
        for month in MONTHS:
            print(f"REGIONAL {month}", flush=True)
            directory = root / "batches" / month
            year, number = map(int, month.split("-"))
            catalog = search_scenes(http, pivots, root, start=date(year, number, 1),
                end=date(year, number, calendar.monthrange(year, number)[1]), max_cloud=40,
                max_scenes=3, plan_path=directory / "catalog.json", allow_empty=True)
            document = read_json(catalog)
            # First three full-coverage, low-cloud acquisitions, selected without
            # looking at NDVI/NDMI. This bounded subset is explicit provenance.
            items = document["selected"]
            calibrations = []
            for item in items:
                for name in ("red", "nir", "swir16", "scl"):
                    _asset_band(item, name)
                if item["collection"] != COLLECTION:
                    raise ValueError("Produto regional fora do contrato C1.")
                calibrations.append(product_radiometry(http, item, root))
            write_json(directory / "radiometry.json", {"catalog_sha256": checksum(catalog), "products": calibrations,
                "limitation": "Independent per-product XML/STAC/COG consistency checks; no field radiometric validation or transfer of Paracatu PC calibration approval"})
            subset = document | {"candidates": items, "candidate_count": len(items),
                                "full_catalog_sha256": checksum(catalog),
                                "subset_policy": "up to three full-coverage low-cloud dates; no index-based selection"}
            shortlist = directory / "shortlist.json"
            _cache_json(http, shortlist, subset, "AquaClima bounded regional shortlist")
            selected = screen_scenes(http, pivots, shortlist, root, output_path=directory / "selected.json",
                                    max_scenes=1, min_valid_fraction=.70)
            crops = acquire_crops(http, pivots, selected, root, manifest_path=directory / "crops.json")
            indices = process_indices(pivots, crops, root, min_valid_fraction=.70, output_path=directory / "indices.csv")
            scene_document = read_json(crops)
            selection = read_json(selected)
            complete = selection["screening_complete"] and all(s["status"] == "ok" for s in scene_document["scenes"])
            write_json(directory / "batch.json", {"schema_version": 1, "month": month,
                "status": "complete" if complete else "partial", "query_complete": True,
                "screening_complete": selection["screening_complete"], "data_root": "../..",
                "pivots_sha256": checksum(pivots), "catalog_candidate_count": document["candidate_count"],
                "selected_scene_ids": selection["selected_ids"], "min_valid_fraction": .70,
                "indices_path": indices.relative_to(root).as_posix(), "indices_sha256": checksum(indices),
                "crops_path": crops.relative_to(root).as_posix(), "crops_sha256": checksum(crops),
                "selected_path": selected.relative_to(root).as_posix(), "selected_sha256": checksum(selected)})
        copy_climate_cache(http, original, root)
        download_precip(http, root, MONTHS, manifest_path=root / "chirps.json", provider="usgs")
        summary = consolidate(root, pivots, output)
        entries = read_ledger(root / "acquisition.jsonl")
        requests = [e for e in entries if e["event"] == "http"]
        write_json(root / "execution.json", {"transferred_bytes": sum(e.get("bytes", 0) for e in requests),
            "http_requests": len(requests), "stored_bytes": sum(p.stat().st_size for p in root.rglob("*") if p.is_file()),
            "new_run_transfer_bytes": http.transferred, "new_run_stored_bytes": http.stored,
            "failures": http.failures, "policy": config})
    excluded = {"inventory.json", "offline-verification.json"}
    files = {p.relative_to(root).as_posix(): {"sha256": checksum(p), "bytes": p.stat().st_size}
             for p in sorted(root.rglob("*")) if p.is_file() and p.name not in excluded and "reproduced" not in p.parts}
    write_json(root / "inventory.json", {"region_id": root.name, "files": files})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision", type=Path, default=Path("data/regions/selection/decision.json"))
    parser.add_argument("--region-dir", type=Path, required=True)
    parser.add_argument("--original-data", type=Path, default=Path("data"))
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.decision, args.region_dir, original=args.original_data, offline=args.offline), indent=2))


if __name__ == "__main__":
    main()
