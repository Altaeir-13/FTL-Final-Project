import io
from pathlib import Path

import pytest
import requests

from aquaclima.storage.http import AcquisitionError, BudgetError, HttpClient, read_ledger

URL = "https://example.test/product.tif"


class Response:
    def __init__(self, body=b"", *, status=200, headers=None):
        self.raw = io.BytesIO(body)
        self.headers = headers if headers is not None else {"Content-Length": str(len(body))}
        self.status_code = status
        self.url = URL

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass


class Session:
    def __init__(self, *responses):
        self.headers = {}
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        pass


def test_retry_timeout_rate_limit_and_retry_after(tmp_path, monkeypatch):
    from aquaclima.storage import http

    waits = []
    monkeypatch.setattr(http.time, "sleep", waits.append)
    session = Session(
        requests.Timeout("timed out"), Response(status=429, headers={"Retry-After": "4"}),
        Response(status=503), Response(b"done"),
    )
    client = HttpClient(ledger=tmp_path / "ledger.jsonl", session=session)
    assert client.get_bytes(URL) == b"done"
    assert waits == [1, 4, 4]
    assert [event["status"] for event in read_ledger(client.ledger)] == [None, 429, 503, 200]
    assert client.transferred == 4


def test_range_refuses_whole_object_without_consuming_body(tmp_path):
    response = Response(b"large", status=200)
    client = HttpClient(ledger=tmp_path / "ledger.jsonl", session=Session(response))
    with pytest.raises(AcquisitionError, match="não respeitou Range"):
        client.range_bytes(URL, 0, 2)
    assert response.raw.tell() == client.transferred == 0


def test_range_verifies_response_and_budget(tmp_path):
    session = Session(Response(
        b"ab", status=206, headers={"Content-Range": "bytes 2-3/9", "Content-Length": "2", "ETag": '"v1"'},
    ))
    client = HttpClient(ledger=tmp_path / "ledger.jsonl", max_transfer_bytes=2, session=session)
    assert client.range_bytes(URL, 2, 4, etag='"v1"') == b"ab"
    assert session.calls[0][2]["headers"] == {"Range": "bytes=2-3", "If-Match": '"v1"'}
    with pytest.raises(BudgetError):
        client.range_bytes(URL, 0, 1)
    assert len(session.calls) == 1


def test_unknown_length_is_bounded_before_next_read(tmp_path):
    response = Response(b"larger", headers={})
    client = HttpClient(ledger=tmp_path / "ledger.jsonl", max_transfer_bytes=3, session=Session(response))
    with pytest.raises(BudgetError):
        client.get_bytes(URL)
    assert response.raw.tell() == client.transferred == 3


def test_incomplete_invalid_and_reusable_download(tmp_path, monkeypatch):
    from aquaclima.storage import http

    monkeypatch.setattr(http.time, "sleep", lambda seconds: None)
    ledger = tmp_path / "ledger.jsonl"
    path = tmp_path / "monthly.tif"
    session = Session(Response(b"broken", headers={"Content-Length": "12"}), Response(b"complete"))
    client = HttpClient(ledger=ledger, session=session)
    assert client.download(URL, path).read_bytes() == b"complete"
    assert client.transferred == len(b"brokencomplete")
    assert not list(tmp_path.glob("*.part"))
    again = HttpClient(ledger=ledger, session=Session())
    assert again.download(URL, path) == path
    assert again.transferred == 0

    path.write_bytes(b"changed!")
    assert not again.is_verified(path)
    invalid = HttpClient(ledger=ledger, session=Session(Response(b"bad format")))

    def reject(_path: Path):
        raise ValueError("formato corrompido")

    with pytest.raises(AcquisitionError, match="formato corrompido"):
        invalid.download(URL, path, validate=reject)
    assert path.read_bytes() == b"changed!"
    assert not list(tmp_path.glob("*.part"))


def test_restart_with_partial_ledger_record(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(b'{"event":"http","status":503}\n{"eve')
    client = HttpClient(ledger=path, session=Session(Response(b"abc")))
    assert client.get_bytes(URL) == b"abc"
    assert [e["status"] for e in read_ledger(path)] == [503, 200]


@pytest.mark.parametrize("host", ["data.chc.ucsb.edu", "edcintl.cr.usgs.gov"])
def test_climate_providers_are_paced(tmp_path, monkeypatch, host):
    from aquaclima.storage import http

    pauses = []
    monkeypatch.setattr(http.time, "sleep", pauses.append)
    monkeypatch.setattr(http.time, "monotonic", lambda: 10.0)
    client = HttpClient(ledger=tmp_path / "ledger.jsonl", session=Session(Response(), Response()))
    client.head(f"https://{host}/first")
    client.head(f"https://{host}/second")
    assert pauses == [1.1]
