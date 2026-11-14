"""Prepare the fixed audit protocol and the single coincident PC acquisition query."""

import argparse
import json
from pathlib import Path

from aquaclima.ingestion.catalog_diagnostic import PROVIDERS, _fetch, _request
from aquaclima.ingestion.sentinel import _cache_json, read_pivots
from aquaclima.storage.http import HttpClient, write_atomic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    root = args.data_dir
    protocol = Path(__file__).resolve().parents[1] / "configs/radiometry-protocol.json"
    target = root / "recovery/diagnostic/radiometry/compatibility-protocol.json"
    if target.is_file() and target.read_bytes() != protocol.read_bytes():
        raise ValueError("Protocolo local difere do protocolo científico versionado.")
    if not target.is_file():
        if args.offline:
            raise FileNotFoundError("Protocolo local ausente em modo offline.")
        write_atomic(target, protocol.read_bytes())
    pivots = read_pivots(root / "processed/pivots.geojson")
    endpoint, collection = PROVIDERS["planetary"]
    request = _request(pivots, "2022-03-20", collection)
    path = root / "recovery/diagnostic/catalogs/planetary/2022-03-20.json"
    with HttpClient(ledger=root / "recovery/diagnostic/http.jsonl", max_transfer_bytes=10_000_000,
                    max_storage_bytes=10_000_000, max_downloads=100) as http:
        if http.is_verified(path, source=f"{endpoint}/search"):
            document = json.loads(path.read_bytes())
            if json.dumps(document["request"], sort_keys=True) != json.dumps(request, sort_keys=True) or not document.get("query_complete"):
                raise ValueError("Consulta coincidente em cache usa outra geometria ou intervalo.")
        elif args.offline:
            raise FileNotFoundError("Consulta coincidente ausente ou corrompida em modo offline.")
        else:
            document = _fetch(http, "planetary", request, path)
            _cache_json(http, path, document, f"{endpoint}/search")
        print(json.dumps({"products": document["candidate_count"], "http_requests": http.downloads,
                          "transferred_bytes": http.transferred}, indent=2))


if __name__ == "__main__":
    main()
