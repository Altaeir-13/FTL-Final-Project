"""Local resource accounting for recovery and its separate source audits."""

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from aquaclima.storage.http import read_ledger, write_json


def summarize_resources(root: Path) -> Path:
    ledgers = sorted((root / "recovery").rglob("*.jsonl"))
    by_host, by_ledger, requests = Counter(), {}, []
    for ledger in ledgers:
        events = [event for event in read_ledger(ledger) if event["event"] == "http"]
        by_ledger[ledger.relative_to(root).as_posix()] = {
            "http_requests": len(events), "transferred_bytes": sum(event["bytes"] for event in events)}
        requests.extend(events)
        for event in events:
            by_host[urlsplit(event["url"]).hostname] += event["bytes"]
    all_files = [path for path in root.rglob("*") if path.is_file()]
    # Recovery manifests, reports and copies plus namespaced raster windows.
    recovery_files = [path for path in all_files if path.is_relative_to(root / "recovery")
        or any(part.startswith(("pc_", "legacy_")) for part in path.relative_to(root).parts)]
    target = root / "recovery/resources.json"
    write_json(target, {"measured_at_utc": datetime.now(UTC).isoformat(),
        "scope": "All HTTP payloads recorded in recovery/*.jsonl recursively; excludes HTTP/TLS headers and prior C1/CHIRPS acquisition",
        "http_requests": len(requests), "transferred_bytes": sum(event["bytes"] for event in requests),
        "payload_bytes_by_host": dict(sorted(by_host.items())), "ledgers": by_ledger,
        "http_failure_count": sum(bool(event.get("error")) for event in requests),
        "all_data_storage_before_report_bytes": sum(path.stat().st_size for path in all_files),
        "recovery_storage_before_report_bytes": sum(path.stat().st_size for path in recovery_files),
        "storage_scope": "Includes cached catalogs, audits, old content-addressed packages, diagnostic batches and local reproduction copies."})
    return target
