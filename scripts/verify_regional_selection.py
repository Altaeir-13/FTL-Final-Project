"""Verify the portable regional audit artifact set without network access."""

import json
from pathlib import Path

from aquaclima.ingestion.sentinel import read_pivots
from aquaclima.storage.http import AcquisitionError, checksum


def verify(directory=Path("data/regions/selection")):
    root = directory.resolve()
    manifest = json.loads((root / "public-integrity.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root):
            raise AcquisitionError("Caminho fora do inventário regional")
        if (not path.is_file() or path.stat().st_size != entry["bytes"]
                or checksum(path) != entry["sha256"]):
            raise AcquisitionError(f"Integridade regional falhou: {entry['path']}")
    decision = json.loads((root / "decision.json").read_text(encoding="utf-8"))
    if checksum(root / "decision.json") != manifest["frozen_decision_sha256"]:
        raise AcquisitionError("Decisão diverge do manifesto regional")
    if checksum(root / "method.json") != decision["method_sha256"]:
        raise AcquisitionError("Método diverge da decisão congelada")
    original = root / "inventory-initial-recovered.geojson"
    if checksum(original) != decision["inventory_sha256"]:
        raise AcquisitionError("Inventário inicial diverge da decisão congelada")
    pivots = json.loads((root / "sample-2204501.geojson").read_text(encoding="utf-8"))
    read_pivots(root / "sample-2204501.geojson")
    if sorted(feature["properties"]["FID"] for feature in pivots["features"]) != decision["winner"]["sample_FIDs"]:
        raise AcquisitionError("Amostra diverge da decisão congelada")
    return {"files_verified": len(manifest["files"]), "network_requests": 0,
            "decision_sha256": checksum(root / "decision.json")}


if __name__ == "__main__":
    print(json.dumps(verify()))
