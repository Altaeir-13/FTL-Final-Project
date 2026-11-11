"""Acquisition with explicit payload budgets and a persistent file inventory."""

import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit

import requests
from urllib3.exceptions import HTTPError as TransportError

LOGGER = logging.getLogger(__name__)
CHUNK = 64 * 1024


class AcquisitionError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class BudgetError(RuntimeError):
    """Stop when a configured resource limit is reached."""


class _Retryable(AcquisitionError):
    def __init__(self, message, *, retry_after=None, status_code=None):
        super().__init__(message, status_code=status_code)
        self.retry_after = retry_after


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".part")
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path: Path, document) -> None:
    write_atomic(path, (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def read_ledger(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    entries = []
    for index, line in enumerate(lines):
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            if index != len(lines) - 1:
                raise
            LOGGER.warning("Última linha incompleta do inventário %s", path)
    return entries


def _repair_ledger(path: Path) -> None:
    """Discard an interrupted final append before starting a new one."""
    if not path.is_file():
        return
    with path.open("rb+") as stream:
        data = stream.read()
        if not data:
            return
        records = data.rstrip(b"\r\n")
        last = records.rfind(b"\n") + 1
        try:
            json.loads(records[last:])
        except (json.JSONDecodeError, UnicodeDecodeError):
            stream.truncate(last)
        else:
            if not data.endswith(b"\n"):
                stream.write(b"\n")


def retry_delay(retry_after: str | None, attempt: int) -> float:
    if retry_after:
        try:
            return max(0, int(retry_after))
        except ValueError:
            try:
                return max(0.0, (parsedate_to_datetime(retry_after) - datetime.now(UTC)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
    return min(30, 2 ** attempt)


class HttpClient:
    def __init__(
        self,
        *,
        ledger: Path,
        max_transfer_bytes: int = 2_000_000_000,
        max_storage_bytes: int = 2_000_000_000,
        max_downloads: int = 2500,
        attempts: int = 4,
        timeout: tuple[float, float] = (10, 45),
        session: requests.Session | None = None,
    ):
        self.ledger = Path(ledger).resolve()
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        _repair_ledger(self.ledger)
        self.max_transfer_bytes = max_transfer_bytes
        self.max_storage_bytes = max_storage_bytes
        self.max_downloads = max_downloads
        self.attempts = attempts
        self.timeout = timeout
        self.session = session if session is not None else requests.Session()
        self.session.headers.update({"Accept-Encoding": "identity", "User-Agent": "AquaClima/0.1"})
        self.transferred = self.stored = self.downloads = 0
        self.failures = []
        self._last_chirps_request = None
        self.files = {
            entry["path"]: entry for entry in read_ledger(self.ledger) if entry["event"] == "file"
        }

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.session.close()

    def _log(self, event: str, **fields) -> None:
        entry = {"event": event, "at_utc": datetime.now(UTC).isoformat(), **fields}
        with self.ledger.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def ensure_storage(self, additional_bytes: int) -> None:
        if additional_bytes > self.max_storage_bytes - self.stored:
            raise BudgetError("Limite de armazenamento desta execução atingido")
        if additional_bytes > shutil.disk_usage(self.ledger.parent).free:
            raise BudgetError("Espaço livre insuficiente para a aquisição")

    def _path_key(self, path: Path) -> str:
        return Path(os.path.relpath(path.resolve(), self.ledger.parent)).as_posix()

    def is_verified(self, path: Path, *, source: str | None = None) -> bool:
        entry = self.files.get(self._path_key(path))
        return bool(
            entry and (source is None or source == entry["source"]) and path.is_file()
            and path.stat().st_size == entry["bytes"] and checksum(path) == entry["sha256"]
        )

    def record_file(self, path: Path, *, source: str) -> dict:
        key = self._path_key(path)
        if self.is_verified(path, source=source):
            return self.files[key]
        size = path.stat().st_size
        self.ensure_storage(size)
        self.stored += size
        entry = {"path": key, "source": source, "bytes": size, "sha256": checksum(path)}
        self.files[key] = entry
        self._log("file", **entry)
        return entry

    def _reserve_transfer(self, size: int) -> None:
        if size > self.max_transfer_bytes - self.transferred:
            raise BudgetError("Limite de transferência desta execução atingido")

    def _throttle(self, url: str) -> None:
        if urlsplit(url).hostname not in {"data.chc.ucsb.edu", "edcintl.cr.usgs.gov"}:
            return
        if self._last_chirps_request is not None:
            time.sleep(max(0.0, 1.1 - (time.monotonic() - self._last_chirps_request)))
        self._last_chirps_request = time.monotonic()

    def _request(self, method, url, consume, *, params=None, payload=None, headers=None):
        for attempt in range(self.attempts):
            if self.downloads >= self.max_downloads:
                raise BudgetError("Limite de requisições desta execução atingido")
            self._throttle(url)
            self.downloads += 1
            before = self.transferred
            status = None
            requested_url = url
            start = time.perf_counter()
            error = None
            try:
                with self.session.request(
                    method, url, params=params, json=payload, headers=headers,
                    stream=True, timeout=self.timeout, allow_redirects=True,
                ) as response:
                    status = response.status_code
                    requested_url = response.url or url
                    if status == 429 or 500 <= status < 600:
                        raise _Retryable(
                            f"HTTP {status} em {url}", status_code=status,
                            retry_after=response.headers.get("Retry-After"),
                        )
                    if status >= 400:
                        raise AcquisitionError(f"HTTP {status} em {url}", status_code=status)
                    return consume(response)
            except (requests.RequestException, TransportError) as exc:
                error = _Retryable(f"{url}: {type(exc).__name__}: {exc}")
            except _Retryable as exc:
                error = exc
            except (AcquisitionError, BudgetError) as exc:
                error = exc
                self.failures.append(str(exc))
                raise
            finally:
                self._log(
                    "http", method=method, url=requested_url, status=status,
                    range=(headers or {}).get("Range"), bytes=self.transferred - before,
                    elapsed_s=round(time.perf_counter() - start, 6),
                    error=str(error) if error else None,
                )
            if attempt + 1 == self.attempts:
                self.failures.append(str(error))
                raise error
            time.sleep(retry_delay(error.retry_after, attempt))

    def _consume(self, response, write, *, expected=None, max_body=None) -> None:
        encoding = response.headers.get("Content-Encoding", "identity").lower()
        if encoding != "identity":
            raise AcquisitionError(f"Content-Encoding inesperado: {encoding}")
        length = response.headers.get("Content-Length")
        if length is not None:
            try:
                declared = int(length)
            except ValueError as exc:
                raise AcquisitionError("Content-Length inválido") from exc
            if declared < 0 or (expected is not None and declared != expected):
                raise AcquisitionError("Content-Length incompatível com o tamanho esperado")
            expected = declared
        if expected is not None:
            self._reserve_transfer(expected)
            if max_body is not None and expected > max_body:
                raise BudgetError("Corpo HTTP maior que o limite desta aquisição")
        received = 0
        while expected is None or received < expected:
            remaining = self.max_transfer_bytes - self.transferred
            if max_body is not None:
                remaining = min(remaining, max_body - received)
            if remaining <= 0:
                raise BudgetError("Resposta HTTP atingiu o limite sem tamanho final confirmado")
            length = min(CHUNK, remaining)
            if expected is not None:
                length = min(length, expected - received)
            chunk = response.raw.read1(length)
            if not chunk:
                break
            self.transferred += len(chunk)
            received += len(chunk)
            write(chunk)
        if expected is not None and received != expected:
            raise _Retryable(f"Resposta incompleta: {received} de {expected} bytes")

    def _body(self, response, *, expected=None, max_body=32 * 1024 * 1024):
        data = bytearray()
        self._consume(response, data.extend, expected=expected, max_body=max_body)
        return bytes(data)

    @staticmethod
    def _identity(url, params, payload) -> str:
        request = requests.Request("GET", url, params=params).prepare()
        if payload is None:
            return request.url
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return f"{request.url} [corpo sha256={hashlib.sha256(encoded).hexdigest()}]"

    def _save(self, path, data, source):
        self.ensure_storage(len(data))
        write_atomic(path, data)
        self.record_file(path, source=source)

    def get_json(self, url, *, params=None, path=None, method="GET", payload=None, validate=None):
        source = self._identity(url, params, payload)
        if path is not None and self.is_verified(path, source=source):
            document = json.loads(path.read_bytes())
            if validate is not None:
                validate(document)
            return document

        def consume(response):
            data = self._body(response)
            try:
                document = json.loads(data)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise AcquisitionError(f"Resposta JSON inválida de {url}") from exc
            if validate is not None:
                validate(document)
            if path is not None:
                self._save(path, data, source)
            return document

        return self._request(method, url, consume, params=params, payload=payload)

    def get_bytes(self, url, *, params=None, path=None, headers=None):
        source = self._identity(url, params, None)
        if path is not None and self.is_verified(path, source=source):
            return path.read_bytes()
        data = self._request("GET", url, self._body, params=params, headers=headers)
        if path is not None:
            self._save(path, data, source)
        return data

    def head(self, url):
        return self._request("HEAD", url, lambda response: response.headers.copy())

    def range_bytes(self, url, start: int, stop: int, *, etag: str | None = None) -> bytes:
        if start < 0 or stop <= start:
            raise ValueError("Intervalo HTTP inválido")
        self._reserve_transfer(stop - start)
        headers = {"Range": f"bytes={start}-{stop - 1}"}
        if etag and not etag.startswith("W/"):
            headers["If-Match"] = etag

        def consume(response):
            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
            if response.status_code != 206 or not match:
                raise AcquisitionError(f"Servidor não respeitou Range em {url}", status_code=response.status_code)
            first, last, total = map(int, match.groups())
            if (first, last) != (start, stop - 1) or last >= total:
                raise AcquisitionError(f"Content-Range incompatível em {url}", status_code=206)
            if etag and response.headers.get("ETag", etag) != etag:
                raise AcquisitionError(f"ETag mudou durante leitura de {url}", status_code=206)
            return self._body(response, expected=stop - start, max_body=stop - start)

        return self._request("GET", url, consume, headers=headers)

    def download(self, url, path: Path, *, validate=None) -> Path:
        if self.is_verified(path, source=url):
            if validate is not None:
                validate(path)
            return path
        path.parent.mkdir(parents=True, exist_ok=True)

        def consume(response):
            if response.status_code != 200:
                raise AcquisitionError(f"Resposta inesperada para download de {url}", status_code=response.status_code)
            fd, name = tempfile.mkstemp(dir=path.parent, suffix=path.suffix + ".part")
            temporary = Path(name)
            try:
                with os.fdopen(fd, "wb") as stream:
                    max_body = min(self.max_storage_bytes - self.stored, shutil.disk_usage(path.parent).free)
                    self._consume(response, stream.write, max_body=max_body)
                if validate is not None:
                    try:
                        validate(temporary)
                    except (OSError, ValueError) as exc:
                        raise AcquisitionError(f"Arquivo inválido de {url}: {exc}") from exc
                self.ensure_storage(temporary.stat().st_size)
                temporary.replace(path)
                self.record_file(path, source=url)
                return path
            finally:
                temporary.unlink(missing_ok=True)

        return self._request("GET", url, consume)
