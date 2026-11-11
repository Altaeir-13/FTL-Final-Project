"""Inspect legacy Earth Search DN against independently calibrated PC products.

Diagnostic only: never creates accepted observations or changes the source gate.
Both products must already be present in the native diagnostic STAC caches.
"""

import argparse
import copy
import json
from pathlib import Path

import numpy as np
import rasterio
import requests
from shapely import union_all

from aquaclima.ingestion.sentinel import ASSETS, _obtain_crop, read_pivots
from aquaclima.ingestion.planetary import acquisition_key
from aquaclima.storage.http import HttpClient, checksum, write_atomic


class OfflineSession(requests.Session):
    def request(self, *args, **kwargs):
        raise RuntimeError("A auditoria legacy offline não permite HTTP.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    root = args.data_dir
    diagnostic = root / "recovery/diagnostic"
    pivot_path = root / "processed/pivots.geojson"
    geometry = union_all([value for _, value in read_pivots(pivot_path)])
    pc_report = json.loads((diagnostic / "radiometry/pixel-audit.json").read_bytes())
    report = {"purpose": "diagnostic_only_not_integrated", "samples": []}
    with HttpClient(ledger=diagnostic / "legacy-pixel-http.jsonl", max_transfer_bytes=20_000_000,
                    max_storage_bytes=30_000_000, max_downloads=300,
                    session=OfflineSession() if args.offline else None) as http:
        for period, legacy_id, pc_fragment in (("2022-01", "S2A_23KKA_20220129_0_L2A", "20220214T021101"),
                                               ("2022-07", "S2A_23KKA_20220728_0_L2A", "20220729T211106")):
            catalog = json.loads((diagnostic / f"catalogs/earth-legacy/{period}.json").read_bytes())
            native = next(item for item in catalog["candidates"] if item["id"] == legacy_id)
            item = copy.deepcopy(native)
            item["id"] = "diagnostic_legacy_" + item["id"]
            for name in ("red", "nir", "swir16"):
                band_name = ASSETS[name][0]
                if not item["assets"][name]["href"].endswith(f"/{band_name}.tif"):
                    raise ValueError("Identidade espectral do endereço legacy inesperada.")
                item["assets"][name]["eo:bands"][0]["name"] = band_name
            pc = next(item for item in pc_report["scenes"] if pc_fragment in item["native_item_id"])
            pc_identity = {"properties": {"s2:product_uri": pc["calibration"]["product_uri"]}}
            if (acquisition_key(pc_identity) != acquisition_key(item)
                    or pc["calibration"]["processing_baseline"] != item["properties"]["s2:processing_baseline"]):
                raise ValueError("A comparação exige a mesma aquisição e processing baseline.")
            assets = {name: _obtain_crop(http, item, name, geometry, root, checksum(pivot_path))
                      for name in ("red", "nir", "swir16", "scl")}
            result = {"legacy_item_id": legacy_id, "pc_item_id": pc["native_item_id"],
                      "safe_product": pc["calibration"]["product_uri"],
                      "legacy_safe_product": item["properties"]["s2:product_uri"],
                      "same_safe_product": pc["calibration"]["product_uri"] == item["properties"]["s2:product_uri"],
                      "comparison_limitation": "Same sensing event and baseline, distinct product generation; differences also include processing-version effects.",
                      "earthsearch_boa_offset_applied": item["properties"]["earthsearch:boa_offset_applied"],
                      "assets": assets, "bands": {}}
            for name in ("red", "nir", "swir16", "scl"):
                with rasterio.open(root / assets[name]["path"]) as a, rasterio.open(root / pc["crops"][name]["path"]) as b:
                    x, y = a.read(1), b.read(1)
                    if not (a.crs == b.crs and a.transform == b.transform and x.shape == y.shape):
                        raise ValueError("Grades incompatíveis na comparação de DN legacy/PC.")
                    common = (x != 0) & (y != 0)
                    delta = x[common].astype("i4") - y[common].astype("i4")
                    band = {"common_non_nodata_pixels": int(common.sum()),
                            "legacy_minus_pc_dn_quantiles": np.quantile(delta, [0, .5, 1]).tolist(),
                            "equal_dn_pixels": int(np.count_nonzero(delta == 0)),
                            "minus1000_dn_pixels": int(np.count_nonzero(delta == -1000))}
                    if name != "scl":
                        legacy_band, pc_band = assets[name]["raster_band"], pc["crops"][name]["raster_band"]
                        difference = (x[common] * legacy_band["scale"] + legacy_band["offset"]
                                      - (y[common] * pc_band["scale"] + pc_band["offset"]))
                        band.update(stac_scale=legacy_band["scale"], stac_offset=legacy_band["offset"],
                                    declared_reflectance_difference_median=float(np.median(difference)))
                    result["bands"][name] = band
            report["samples"].append(result)
        path = diagnostic / "radiometry/legacy-pixel-comparison.json"
        payload = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if not path.is_file() or path.read_bytes() != payload:
            write_atomic(path, payload)
        print(json.dumps({"samples": len(report["samples"]), "http_requests": http.downloads,
                          "transferred_bytes": http.transferred, "report": str(path)}, indent=2))


if __name__ == "__main__":
    main()
