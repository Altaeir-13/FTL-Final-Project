"""Export the small, real regional evidence; never export raw TIFF/XML/cache."""
import json
import shutil
from pathlib import Path

import pandas as pd

from aquaclima.storage.http import checksum, write_json
from aquaclima.regions.pilot import verify_inventory


def main():
    root = Path("data/regions/guadalupe-pi")
    verify_inventory(root)
    verification = json.loads((root / "offline-verification.json").read_bytes())
    if verification.get("status") != "identical" or verification.get("http_requests") != 0:
        raise ValueError("A exportação requer reprodução offline idêntica documentada.")
    destination = Path("docs/evidencias/guadalupe-pi")
    destination.mkdir(parents=True, exist_ok=True)
    names = ["pivots.geojson", "policy.json", "execution.json", "inventory.json", "offline-verification.json"]
    names += [f"curated/v1/{name}" for name in ("observations.csv", "attempts.csv", "monthly.csv", "precipitation.csv", "summary.json")]
    names += [p.relative_to(root).as_posix() for p in sorted((root / "batches").glob("*/radiometry.json"))]
    records = {}
    for name in names:
        source = root / name
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        records[name] = {"sha256": checksum(target), "bytes": target.stat().st_size}
    observations = pd.read_csv(root / "curated/v1/observations.csv")
    monthly = pd.read_csv(root / "curated/v1/monthly.csv")
    rows = []
    for path in sorted((root / "batches").glob("*/crops.json")):
        for scene in json.loads(path.read_bytes())["scenes"]:
            accepted = observations[observations.scene_id.eq(scene["id"])]
            rain = monthly[monthly.month.eq(path.parent.name)]
            rows.append({"month": path.parent.name, "date": scene["date"], "scene_id": scene["id"],
                "processing_baseline": scene["processing_baseline"], "accepted_pivots": len(accepted),
                "ndvi_min": accepted.ndvi_median.min(), "ndvi_max": accepted.ndvi_median.max(),
                "ndmi_min": accepted.ndmi_median.min(), "ndmi_max": accepted.ndmi_median.max(),
                "rain_mm_min": rain.precip_mm.min(), "rain_mm_max": rain.precip_mm.max()})
    table = pd.DataFrame(rows)
    table.to_csv(destination / "scene-summary.csv", index=False, lineterminator="\n")
    path = destination / "scene-summary.csv"
    records[path.name] = {"sha256": checksum(path), "bytes": path.stat().st_size}
    write_json(destination / "manifest.json", {"region_id": root.name, "validation_state": "exploratory_portability",
        "note": "Small evidence snapshot. Raw COG windows, ESA XML and STAC caches remain local and are listed by SHA-256 in inventory.json. Offline raster reproduction requires that local cache.", "files": records})
    print(table.to_string(index=False))
    print(f"Exported {len(records)} verified small evidence files to {destination}")


if __name__ == "__main__":
    main()
