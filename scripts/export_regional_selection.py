"""Export compact review evidence without bundling ANA/STAC acquisition caches."""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from aquaclima.storage.http import checksum, read_ledger, write_json


def export(directory=Path("data/regions/selection")):
    comparison = json.loads((directory / "comparison.json").read_text(encoding="utf-8"))
    columns = ["UF", "name", "code", "ana_count", "eligible_count", "area_ha",
               "cluster_radius_m", "caxias_km", "FIDs", "sample_FIDs", "usable_dates",
               "usable_months", "score", "eligible", "centroid_mismatches", "boundary_crossings"]
    with (directory / "municipalities.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for candidate in comparison:
            record = {key: candidate.get(key) for key in columns}
            for key in ("FIDs", "sample_FIDs", "usable_months"):
                record[key] = ";".join(map(str, candidate.get(key, [])))
            record["score"] = candidate.get("scores", {}).get("weighted_total")
            writer.writerow(record)
    entries = read_ledger(directory / "acquisition.jsonl")
    records = {entry["path"]: entry for entry in entries if entry["event"] == "file"}
    http_entries = [entry for entry in entries if entry["event"] == "http"]
    write_json(directory / "cache-inventory.json", {
        "files": list(records.values()),
        "http_requests_including_failures": len(http_entries),
        "http_transfer_bytes": sum(entry["bytes"] for entry in http_entries),
        "recorded_file_bytes": sum(entry["bytes"] for entry in records.values()),
        "failed_http_requests": sum(bool(entry.get("error")) for entry in http_entries),
        "note": "Wire bytes are recorded before decompression; raw caches remain local and are not required for public-artifact integrity verification.",
    })
    selected = ["decision.json", "method.json", "inventory.csv", "inventory.geojson",
                "inventory-initial-recovered.geojson", "comparison.json", "supplemental.json",
                "state-municipality-counts.json", "municipalities.csv", "cache-inventory.json",
                "sample-2204501.geojson"]
    selected.extend(path.name for path in sorted(directory.glob("stac-summary-*.json")))
    write_json(directory / "public-integrity.json", {
        "format_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "files": [{"path": name, "bytes": (directory / name).stat().st_size,
                   "sha256": checksum(directory / name)} for name in selected],
        "frozen_decision_sha256": checksum(directory / "decision.json"),
        "note": "Initial decision and sample remain frozen; inventory.geojson is transformed WGS84 supplemental inventory; initial inventory hash is retained separately.",
    })
    print(json.dumps({"files": len(selected) + 1,
                      "bytes": sum((directory / name).stat().st_size for name in selected),
                      "allowlist": selected + ["public-integrity.json"]}, ensure_ascii=False))


if __name__ == "__main__":
    export()
