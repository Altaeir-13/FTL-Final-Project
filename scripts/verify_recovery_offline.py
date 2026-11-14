"""Rebuild the recovered version while forbidding every HTTP request."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from aquaclima.cli import main as aquaclima
from aquaclima.storage.http import checksum


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--config", type=Path, default=Path("configs/recovery-2022.toml"))
    parser.add_argument("--dataset-dir", type=Path, default=Path("data/recovery/curated/2022_2024_recovery_v1"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/recovery/reproduzido/2022_2024_recovery_v1"))
    parser.add_argument("--check-online-cache", action="store_true", help="também comprova a retomada normal sem requisições")
    args = parser.parse_args()
    if args.output_dir.resolve() == args.dataset_dir.resolve():
        parser.error("Escolha um diretório distinto para a reprodução.")
    active_package = json.loads((args.dataset_dir / "webgis/manifest.json").read_bytes())["package_sha256"]
    before = {}
    for path in args.dataset_dir.rglob("*"):
        if not path.is_file() or path.name == "execution_report.json":
            continue
        relative = path.relative_to(args.dataset_dir)
        # Older immutable packages remain cached but are outside this version's
        # active contract. A clean rebuild generates only the referenced package.
        if relative.parts[:2] == ("webgis", "packages") and relative.parts[2] != active_package:
            continue
        before[relative.as_posix()] = checksum(path)
    if not before:
        parser.error("Dataset de referência ausente.")
    with patch("requests.Session.request", side_effect=AssertionError("HTTP proibido nesta verificação")):
        result = aquaclima(["recovery-run", "--config", str(args.config), "--data-dir", str(args.data_dir),
                           "--allow-bulk", "--output-dir", str(args.output_dir)] + ([] if args.check_online_cache else ["--offline"]))
    if result:
        raise RuntimeError("A reprodução offline retornou erro.")
    differences = [name for name, digest in before.items()
                   if not (args.output_dir / name).is_file() or checksum(args.output_dir / name) != digest]
    if differences:
        raise AssertionError(f"Arquivos divergentes: {differences}")
    report = json.loads((args.output_dir / "execution_report.json").read_bytes())
    assert report["http_requests"] == report["transferred_bytes"] == 0
    print(json.dumps({"status": "identical", "files_checked": len(before), "http_requests": 0,
                      "transferred_bytes": 0, "elapsed_s": report["elapsed_s"]}, indent=2))


if __name__ == "__main__":
    main()
