"""Reproduce the six-product local radiometric audit (no full scenes).

Run from the checkout: python scripts/audit_radiometry.py --offline
The acquisition mode requires the cached native diagnostic STAC catalogs and
has its own 50 MB HTTP payload cap. Offline mode denies every HTTP request.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.warp import reproject, transform_geom
from shapely import union_all
from shapely.geometry import mapping

from aquaclima.ingestion.planetary import PlanetaryHttp, normalize_pc_item
from aquaclima.ingestion.sentinel import _obtain_crop, read_pivots
from aquaclima.processing.indices import _scene_rows
from aquaclima.storage.http import HttpClient, checksum, write_atomic

SAMPLES = (
    ("2022-01", "20220124"), ("2022-01", "20220129"),
    ("2022-07", "20240709T005945"), ("2022-07", "20220729T211106"),
    ("2022-03-20", "20220324T023009"), ("2022-03-20", "20240601T152534"),
)


class OfflineSession(requests.Session):
    def request(self, *args, **kwargs):
        raise RuntimeError("HTTP proibido na auditoria offline; recorte ou metadado local ausente.")


def write_json(path: Path, document) -> None:
    payload = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if not path.is_file() or path.read_bytes() != payload:
        write_atomic(path, payload)


def save(path, document):
    write_json(path, json.loads(json.dumps(document, default=lambda value: value.item())))


def acquire_samples(root: Path, http: PlanetaryHttp) -> dict:
    diagnostic = root / "recovery" / "diagnostic"
    pivot_path = root / "processed" / "pivots.geojson"
    pivots = read_pivots(pivot_path)
    geometry = union_all([item for _, item in pivots])
    report = {"method": "same native COG window, XML-derived reflectance; exact-product C1 cross-source comparison", "scenes": []}
    for month, product in SAMPLES:
        catalog = json.loads((diagnostic / "catalogs" / "planetary" / f"{month}.json").read_bytes())
        item = next(entry for entry in catalog["candidates"] if product in entry["id"])
        normalized = normalize_pc_item(http, item, root)
        assets = {name: _obtain_crop(http, normalized, name, geometry, root, checksum(pivot_path))
                  for name in ("red", "nir", "swir16", "scl")}
        scene = {"id": normalized["id"], "date": item["properties"]["datetime"][:10],
                 "cloud_cover": item["properties"]["eo:cloud_cover"], "footprint": item["geometry"],
                 "processing_baseline": item["properties"]["s2:processing_baseline"],
                 "source_item_url": normalized["aquaclima:source_item_url"], "status": "ok", "assets": assets}
        entry = {"native_item_id": item["id"], "calibration": normalized["aquaclima:calibration"],
                 "crops": assets, "indices": list(_scene_rows(scene, pivots, root, .7)), "reflectance": {}}
        for name in ("red", "nir", "swir16"):
            with rasterio.open(root / assets[name]["path"]) as raster:
                dn = raster.read(1)
                band = assets[name]["raster_band"]
                values = dn[dn != 0] * band["scale"] + band["offset"]
                entry["reflectance"][name] = {
                    "count_non_nodata": int(len(values)), "dn_min": int(dn[dn != 0].min()), "dn_max": int(dn.max()),
                    "quantiles": np.quantile(values, [0, .01, .5, .99, 1]).tolist(),
                    "negative_count": int((values < 0).sum()), "crs": str(raster.crs),
                    "resolution": list(raster.res), "shape": list(raster.shape), "transform": list(raster.transform)[:6]}
        report["scenes"].append(entry)
    return report


def compare_sources(root: Path, destination: Path, pixel_report: dict) -> dict:
    """Compare raw samples on verified equal grids; retain every failed test."""
    diagnostic = root / "recovery" / "diagnostic"
    protocol_path = diagnostic / "radiometry" / "compatibility-protocol.json"
    protocol = json.loads(protocol_path.read_bytes())
    rule = protocol["pb04_pb0510_common_clear_rule"]
    def proof(path):
        return {"path": path.relative_to(root).as_posix(), "sha256": checksum(path)}
    record = {"protocol_sha256": checksum(protocol_path), "exact_product": {}, "processing_comparisons": [], "checks": []}
    items = pixel_report["scenes"]
    c1 = json.loads((root / "history/batches/a48cba82f744/2022-03/crops.json").read_bytes())["scenes"][0]
    pc = next(item for item in items if "20240601T152534" in item["native_item_id"])
    geometry = mapping(union_all([shape for _, shape in read_pivots(root / "processed/pivots.geojson")]))
    same_product_ok, cross_baseline_ok = True, True
    for name in ("red", "nir", "swir16", "scl"):
        first, second = root / c1["assets"][name]["path"], root / pc["crops"][name]["path"]
        if checksum(first) != c1["assets"][name]["sha256"]:
            raise ValueError("Recorte C1 diverge do inventário original.")
        with rasterio.open(first) as a, rasterio.open(second) as b:
            x, y = a.read(1), b.read(1)
            same = a.crs == b.crs and a.transform == b.transform and x.shape == y.shape
            count = int(np.count_nonzero(x != y)) if same else None
            record["exact_product"][name] = {
                "same_crs_transform_shape": same, "pixel_count": int(x.size), "different_dn_pixels": count,
                "max_abs_dn_difference": int(np.abs(x.astype("i4") - y.astype("i4")).max()) if same else None}
            same_product_ok &= same and count == 0
        record["checks"] += [proof(first), proof(second)]
    for observed, old_id, new_id in (("2022-03-20", "20220324T023009", "20240601T152534"),
                                     ("2022-07-28", "20220729T211106", "20240709T005945")):
        old = next(item for item in items if old_id in item["native_item_id"])
        new = next(item for item in items if new_id in item["native_item_id"])
        result = {"date": observed, "old_product": old["calibration"]["product_uri"],
                  "new_product": new["calibration"]["product_uri"], "bands": {}, "pivot_indices": []}
        for name in ("red", "nir", "swir16"):
            with rasterio.open(root / old["crops"][name]["path"]) as a, rasterio.open(root / new["crops"][name]["path"]) as b:
                x, y = a.read(1), b.read(1)
                if not (a.crs == b.crs and a.transform == b.transform and x.shape == y.shape):
                    raise ValueError("Grades PB04 e PB05.10 divergentes na amostra.")
                clear = []
                for item in (old, new):
                    with rasterio.open(root / item["crops"]["scl"]["path"]) as scl:
                        mask = np.zeros(a.shape, dtype="u1")
                        reproject(scl.read(1), mask, src_transform=scl.transform, src_crs=scl.crs,
                                  dst_transform=a.transform, dst_crs=a.crs, resampling=Resampling.nearest)
                        clear.append(np.isin(mask, [4, 5]))
                inside = geometry_mask([transform_geom("EPSG:4326", a.crs, geometry)], a.shape, a.transform, invert=True)
                bx, by = old["crops"][name]["raster_band"], new["crops"][name]["raster_band"]
                rx, ry = x * bx["scale"] + bx["offset"], y * by["scale"] + by["offset"]
                valid = inside & clear[0] & clear[1] & (x != 0) & (y != 0) & (rx >= 0) & (ry >= 0)
                delta = ry[valid] - rx[valid]
                result["bands"][name] = {"common_valid_pixels": int(valid.sum()), "same_grid": True,
                    "median_signed_reflectance_difference": float(np.median(delta)),
                    "p95_absolute_reflectance_difference": float(np.quantile(np.abs(delta), .95)),
                    "max_absolute_reflectance_difference": float(np.max(np.abs(delta)))}
                cross_baseline_ok &= result["bands"][name]["p95_absolute_reflectance_difference"] <= rule["reflectance_p95_absolute_difference_max"]
            record["checks"] += [proof(root / old["crops"][name]["path"]), proof(root / new["crops"][name]["path"])]
        for first, second in zip(old["indices"], new["indices"]):
            if first["pivot_id"] != second["pivot_id"]:
                raise ValueError("Identificadores de pivô divergentes.")
            okay = first["status"] == second["status"] == "ok"
            entry = {"pivot_id": first["pivot_id"], "both_accepted": okay,
                     "ndvi_difference": second["ndvi_median"] - first["ndvi_median"] if okay else None,
                     "ndmi_difference": second["ndmi_median"] - first["ndmi_median"] if okay else None}
            result["pivot_indices"].append(entry)
            cross_baseline_ok &= okay and all(abs(entry[key]) <= rule["accepted_pivot_index_median_absolute_difference_max"]
                                              for key in ("ndvi_difference", "ndmi_difference"))
        record["processing_comparisons"].append(result)
    write_json(destination / "source-comparison.json", record)
    checks = [proof(protocol_path), proof(destination / "source-comparison.json"), proof(destination / "pixel-audit.json")]
    checks += [proof(root / item["calibration"]["xml_path"]) for item in items]
    checks += record["checks"]
    gate = {"adapter_version": 1, "status": "compatible" if same_product_ok else "rejected",
            "validated_baselines": (["04.00", "05.10"] if cross_baseline_ok else ["05.10"]) if same_product_ok else [],
            "excluded_baselines": {
                "03.00": "Native reflectance known, but no local reprocessed comparison and PB04 S2B VNIR harmonization prevent inclusion.",
                "04.00": "Fails declared index tolerance at March20/pivot8087: deltaNDVI0.0352454 and deltaNDMI0.0330517 exceed0.02."},
            "checks": checks, "limitations": [
                "Two dates and five neighboring fields do not establish global radiometric validity.",
                "Processing baseline is retained as a possible temporal confounder.",
                "PB03 and PB04 are diagnostic only; no ad-hoc rescaling or relaxed threshold.",
                "The exact-product PC/C1 comparison checks source conversion, not absolute field truth."],
            "source_references": ["https://github.com/microsoft/PlanetaryComputer/issues/134",
                                  "https://sentiwiki.copernicus.eu/web/s2-products", "https://sentiwiki.copernicus.eu/web/s2-processing"]}
    write_json(destination / "compatibility.json", gate)
    return gate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    root = args.data_dir
    destination = args.output_dir or root / "recovery/diagnostic/radiometry"
    if not destination.resolve().is_relative_to(root.resolve()):
        parser.error("O relatório deve permanecer no diretório de dados.")
    with HttpClient(ledger=root / "recovery/diagnostic/pixel-audit-http.jsonl", max_transfer_bytes=50_000_000,
                    max_storage_bytes=100_000_000, max_downloads=1200,
                    session=OfflineSession() if args.offline else None) as base:
        report = acquire_samples(root, PlanetaryHttp(base))
        save(destination / "pixel-audit.json", report)
        gate = compare_sources(root, destination, report)
        print(json.dumps({"status": gate["status"], "validated_baselines": gate["validated_baselines"],
                          "http_requests": base.downloads, "transferred_bytes": base.transferred}, indent=2))


if __name__ == "__main__":
    main()
