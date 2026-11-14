import json

from aquaclima.reporting.recovery import summarize_resources
from aquaclima.storage.http import write_atomic


def test_resource_report_counts_recovery_payloads_and_excludes_previous_acquisition(tmp_path):
    root = tmp_path / "data"
    for relative, events in {
        "acquisition.jsonl": [{"event": "http", "url": "https://old.example/file", "bytes": 999}],
        "recovery/acquisition.jsonl": [{"event": "http", "url": "https://pc.example/file", "bytes": 40},
            {"event": "file", "bytes": 1000}],
        "recovery/diagnostic/http.jsonl": [{"event": "http", "url": "https://pc.example/file", "bytes": 60,
            "error": "retry"}],
    }.items():
        write_atomic(root / relative, ("\n".join(json.dumps(row) for row in events) + "\n").encode())
    report = json.loads(summarize_resources(root).read_bytes())
    assert report["http_requests"] == 2
    assert report["transferred_bytes"] == 100
    assert report["payload_bytes_by_host"] == {"pc.example": 100}
    assert report["http_failure_count"] == 1
    assert report["all_data_storage_before_report_bytes"] > report["recovery_storage_before_report_bytes"]
