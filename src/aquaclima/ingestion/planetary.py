"""Budgeted Planetary Computer access with native product provenance."""

from __future__ import annotations

import copy
import json
import math
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

from shapely import union_all
from shapely.geometry import mapping, shape
import rasterio
from rasterio.errors import WindowError

from aquaclima.ingestion.sentinel import (
    ASSETS, VALID_SCL, _cache_json, _cached_crop, _crop_path, _finish_screening,
    _obtain_crop, _screen_candidate, read_pivots,
)
from aquaclima.storage.http import AcquisitionError, BudgetError, HttpClient, checksum, write_atomic

PC_ROOT = "https://planetarycomputer.microsoft.com/api/stac/v1"
PC_COLLECTION = "sentinel-2-l2a"
PC_PROVIDER = "Microsoft Planetary Computer"
SAS_ROOT = "https://planetarycomputer.microsoft.com/api/sas/v1/token"
ASSET_KEYS = {"red": "B04", "nir": "B08", "swir16": "B11", "scl": "SCL"}
SAFE_PATTERN = re.compile(r"(S2[ABCD])_MSIL2A_(\d{8}T\d{6})_N\d{4}_R(\d{3})_T([A-Z0-9]{5})_")
PRODUCT_PATTERN = re.compile(r"S2[ABCD]_MSIL2A_\d{8}T\d{6}_N(\d{4})_R\d{3}_T[A-Z0-9]{5}_\d{8}T\d{6}\.SAFE")
MAX_ITEMS = 500
CALIBRATION_VERSION = "pc-safe-boa-v1"


def acquisition_key(item: dict) -> str:
    """Identify a sensing event independently of processing/generation versions."""
    properties = item["properties"]
    product = properties.get("s2:product_uri", "")
    match = SAFE_PATTERN.match(product)
    if match:
        platform, observed, orbit, tile = match.groups()
        return f"{platform}_{observed}_R{orbit}_T{tile}"
    platform = str(properties.get("platform", "")).lower().replace("sentinel-", "S").replace("-", "").upper()
    tile = properties.get("s2:mgrs_tile")
    orbit = properties.get("sat:relative_orbit", properties.get("s2:relative_orbit"))
    observed = datetime.fromisoformat(properties["datetime"]).date().isoformat()
    if not re.fullmatch(r"S2[ABCD]", platform) or not re.fullmatch(r"[A-Z0-9]{5}", str(tile)) or not isinstance(orbit, int):
        raise ValueError(f"Metadados insuficientes para identificar a aquisição {item['id']}.")
    return f"{platform}_{observed}_R{orbit:03d}_T{tile}_date_fallback"


class PlanetaryHttp:
    """Sign public Azure requests in memory while retaining unsigned provenance.

    The wrapped HttpClient owns all retries, payload counters and hard limits.
    Tokens and signing responses are never written to disk by this adapter.
    """

    def __init__(self, http: HttpClient):
        self.http = http
        self._tokens: dict[tuple[str, str], tuple[datetime, str]] = {}

    def __getattr__(self, name):
        return getattr(self.http, name)

    @staticmethod
    def _location(url: str) -> tuple[str, str]:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.query or parsed.fragment
                or re.fullmatch(r"sentinel2l2a\d+\.blob\.core\.windows\.net", parsed.hostname or "") is None):
            raise ValueError("O asset Planetary Computer deve usar um endereço Azure Sentinel-2 público sem assinatura persistida.")
        parts = parsed.path.lstrip("/").split("/", 1)
        if len(parts) != 2 or parts[0] != "sentinel2-l2":
            raise ValueError("Contêiner Azure inesperado para Sentinel-2 Planetary Computer.")
        return parsed.hostname.split(".", 1)[0], parts[0]

    def _signed_url(self, url: str) -> str:
        account, container = self._location(url)
        key = (account, container)
        now = datetime.now(timezone.utc)
        cached = self._tokens.get(key)
        if cached is None or cached[0] <= now + timedelta(seconds=60):
            response = self.http.get_json(f"{SAS_ROOT}/{account}/{container}")
            try:
                expiry = datetime.fromisoformat(response["msft:expiry"])
                token = response["token"]
            except (KeyError, TypeError, ValueError) as error:
                raise AcquisitionError("Resposta inválida do serviço público de assinatura Planetary Computer.") from error
            fields = parse_qs(token)
            permissions = fields.get("sp", [""])[0]
            if (expiry.tzinfo is None or expiry <= now + timedelta(seconds=60)
                    or not fields.get("sig") or "r" not in permissions or set(permissions) - {"r", "l"}):
                raise AcquisitionError("Assinatura Planetary Computer expirada ou sem permissão pública de leitura.")
            cached = (expiry, token)
            self._tokens[key] = cached
        parsed = urlsplit(url)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, cached[1], ""))

    def _call(self, method: str, url: str, *args, **kwargs):
        for attempt in range(2):
            try:
                return getattr(self.http, method)(self._signed_url(url), *args, **kwargs)
            except AcquisitionError as error:
                if attempt or error.status_code != 403:
                    raise
                self._tokens.pop(self._location(url), None)

    def head(self, url: str):
        return self._call("head", url)

    def range_bytes(self, url: str, start: int, stop: int, *, etag: str | None = None) -> bytes:
        return self._call("range_bytes", url, start, stop, etag=etag)

    def get_bytes(self, url: str, *, path: Path | None = None) -> bytes:
        self._location(url)
        if path is not None and self.http.is_verified(path, source=url):
            return path.read_bytes()
        data = self._call("get_bytes", url)
        if path is not None:
            self.http.ensure_storage(len(data))
            write_atomic(path, data)
            self.http.record_file(path, source=url)
        return data


def _pc_items(http: HttpClient, request: dict, pages: Path) -> list[dict]:
    method, url, payload = "POST", f"{PC_ROOT}/search", request
    seen, items = set(), {}
    first, last = (datetime.fromisoformat(value) for value in request["datetime"].split("/"))
    for page_number in range(1, MAX_ITEMS + 1):
        identity = (method, url, json.dumps(payload, sort_keys=True))
        if identity in seen:
            raise ValueError("A paginação Planetary Computer repetiu uma página.")
        seen.add(identity)
        page = http.get_json(url, method=method, payload=payload, path=pages / f"page-{page_number:04d}.json")
        if page.get("type") != "FeatureCollection":
            raise ValueError("Resposta Planetary Computer não é uma FeatureCollection.")
        for item in page["features"]:
            if item.get("collection") != PC_COLLECTION or not first <= datetime.fromisoformat(item["properties"]["datetime"]) <= last:
                raise ValueError("Item Planetary Computer fora da coleção ou do intervalo solicitado.")
            previous = items.setdefault(item["id"], item)
            if previous != item:
                raise ValueError(f"Versões divergentes do mesmo item Planetary Computer {item['id']}.")
            if len(items) > MAX_ITEMS:
                raise ValueError("A consulta Planetary Computer excedeu 500 produtos. Reduza o intervalo.")
        following = next((link for link in page["links"] if link["rel"] == "next"), None)
        if following is None:
            matched = page.get("numberMatched", page.get("context", {}).get("matched"))
            if isinstance(matched, int) and matched != len(items):
                raise ValueError("A contagem Planetary Computer diverge dos produtos recebidos.")
            if matched is None and len(items) >= MAX_ITEMS:
                raise ValueError("A consulta Planetary Computer alcançou o limite sem comprovação de completude.")
            return list(items.values())
        url = urljoin(f"{PC_ROOT}/", following["href"])
        if urlsplit(url).netloc != urlsplit(PC_ROOT).netloc or urlsplit(url).scheme != "https":
            raise ValueError("Domínio inesperado na paginação Planetary Computer.")
        method = following.get("method", "GET").upper()
        if method not in {"GET", "POST"}:
            raise ValueError("Método inesperado na paginação Planetary Computer.")
        body = following.get("body", {})
        payload = ((request | body) if following.get("merge") else body) if method == "POST" else None
    raise ValueError("Paginação Planetary Computer excessiva.")


def search_pc(http: HttpClient, pivots_path: Path, data_dir: Path, *, start: date, end: date,
               output_path: Path) -> Path:
    if end < start:
        raise ValueError("Intervalo Planetary Computer inválido.")
    pivots = read_pivots(pivots_path)
    request = {"collections": [PC_COLLECTION], "intersects": mapping(union_all([geometry for _, geometry in pivots])),
               "datetime": f"{start}T00:00:00Z/{end}T23:59:59.999999Z", "limit": 100}
    source = f"{PC_ROOT}/search"
    parameters = {"pivots_sha256": checksum(pivots_path)}
    if output_path.exists():
        if not http.is_verified(output_path, source=source):
            raise ValueError(f"Catálogo Planetary Computer existente sem integridade verificada: {output_path}.")
        previous = json.loads(output_path.read_bytes())
        if (json.dumps(previous.get("request"), sort_keys=True) != json.dumps(request, sort_keys=True)
                or previous.get("parameters") != parameters):
            raise ValueError(f"O catálogo Planetary Computer existente pertence a outra configuração: {output_path}.")
        return output_path
    items = _pc_items(http, request, output_path.parent / f"{output_path.stem}-pages")
    _cache_json(http, output_path, {
        "provider": PC_PROVIDER, "collection": PC_COLLECTION, "source": source, "parameters": parameters,
        "request": request, "query_complete": True, "candidate_count": len(items), "candidates": items,
        "acquisition_count": len({acquisition_key(item) for item in items}),
        "searched_at": datetime.now(timezone.utc).isoformat(),
    }, source)
    return output_path


def parse_product_calibration(data: bytes, *, product_uri: str, baseline: str) -> dict:
    """Read product-specific ESA BOA calibration, never infer it from sensing date.

    PC preserves SAFE digital numbers in COGs. PB >= 04 must explicitly contain
    every BOA_ADD_OFFSET. Earlier products explicitly use the original zero
    offset convention when that list is absent. Identity/baseline disagreements
    or unexpected radiometric declarations fail closed.
    """
    if len(data) > 2_000_000 or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("Metadados SAFE excessivos ou com declaração XML externa.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise ValueError("Metadados SAFE XML inválidos.") from error
    def elements(name):
        return [element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == name]
    def one(name):
        found = elements(name)
        if len(found) != 1 or not found[0].text:
            raise ValueError(f"Campo SAFE obrigatório ausente ou ambíguo: {name}.")
        return found[0].text.strip()
    if (one("PRODUCT_URI") != product_uri or one("PROCESSING_BASELINE") != baseline
            or one("PROCESSING_LEVEL") != "Level-2A" or one("PRODUCT_TYPE") != "S2MSI2A"):
        raise ValueError("Identidade, nível ou baseline SAFE diverge do item STAC.")
    if re.fullmatch(r"\d{2}\.\d{2}", baseline) is None:
        raise ValueError("Processing baseline SAFE inválido.")
    product_match = PRODUCT_PATTERN.fullmatch(product_uri)
    if product_match is None or product_match[1] != baseline.replace(".", ""):
        raise ValueError("Processing baseline não corresponde ao nome do produto SAFE.")
    quantification = float(one("BOA_QUANTIFICATION_VALUE"))
    if not math.isfinite(quantification) or quantification <= 0:
        raise ValueError("BOA_QUANTIFICATION_VALUE inválido.")
    offsets = {}
    for element in elements("BOA_ADD_OFFSET"):
        band_id = element.get("band_id")
        if band_id in offsets or not re.fullmatch(r"(?:[0-9]|1[0-2])", band_id or ""):
            raise ValueError("BOA_ADD_OFFSET duplicado ou band_id inválido.")
        value = float(element.text or "nan")
        if not math.isfinite(value):
            raise ValueError("BOA_ADD_OFFSET não finito.")
        offsets[band_id] = value
    if float(baseline) >= 4 and set(offsets) != {str(number) for number in range(13)}:
        raise ValueError("Produto PB >= 04 sem lista BOA_ADD_OFFSET completa.")
    if float(baseline) < 4 and offsets:
        raise ValueError("Produto anterior a PB04 com offsets inesperados; requer auditoria separada.")
    special = {}
    for element in elements("Special_Values"):
        values = {child.tag.rsplit("}", 1)[-1]: child.text for child in element}
        key = values.get("SPECIAL_VALUE_TEXT")
        if key in special:
            raise ValueError("Valores especiais SAFE duplicados.")
        special[key] = int(values.get("SPECIAL_VALUE_INDEX", "-1"))
    if special.get("NODATA") != 0 or special.get("SATURATED") != 65535:
        raise ValueError("NoData ou saturação SAFE inesperados.")
    band_ids = {"red": "3", "nir": "7", "swir16": "11"}
    return {"contract": CALIBRATION_VERSION, "product_uri": product_uri, "processing_baseline": baseline,
            "formula": "reflectance=(DN+BOA_ADD_OFFSET)/BOA_QUANTIFICATION_VALUE",
            "quantification_value": quantification, "special_values": special,
            "offset_policy": "explicit_safe_band_offsets" if offsets else "pre_pb04_zero_offset",
            "bands": {name: {"band_id": band_id, "scale": 1 / quantification,
                              "offset_dn": offsets.get(band_id, 0.0),
                              "offset": offsets.get(band_id, 0.0) / quantification}
                      for name, band_id in band_ids.items()}}


def normalize_pc_item(http: PlanetaryHttp, item: dict, data_dir: Path) -> dict:
    """Expose audited PC native COGs to the shared bounded raster operations.

    Native item, SAFE product and XML hash remain available. Namespaced cache IDs
    avoid a collision with any existing Earth Search crop or observation.
    """
    if item.get("collection") != PC_COLLECTION:
        raise ValueError("Coleção incompatível com o adaptador Planetary Computer.")
    if item.get("aquaclima:calibration"):
        raise ValueError("O adaptador exige um item STAC nativo, ainda não normalizado.")
    properties = item["properties"]
    product_uri, baseline = properties["s2:product_uri"], properties["s2:processing_baseline"]
    if PRODUCT_PATTERN.fullmatch(product_uri) is None:
        raise ValueError("Identificador de produto SAFE inválido.")
    metadata = item["assets"].get("product-metadata", item["assets"].get("product_metadata", {}))
    url = metadata.get("href", "")
    http._location(url)
    if not url.endswith(f"/{product_uri}/MTD_MSIL2A.xml"):
        raise ValueError("Metadados XML não pertencem ao produto SAFE declarado.")
    path = data_dir / "recovery" / "metadata" / "planetary" / (product_uri[:-5] + ".xml")
    data = http.get_bytes(url, path=path)
    calibration = parse_product_calibration(data, product_uri=product_uri, baseline=baseline)
    calibration.update(xml_source=url, xml_path=path.relative_to(data_dir).as_posix(), xml_sha256=checksum(path),
                       native_stac_item_id=item["id"], provider=PC_PROVIDER,
                       dn_semantics="native_SAFE_DN_preserved_in_PC_COG")
    normalized = copy.deepcopy(item)
    normalized["id"] = "pc_" + item["id"]
    normalized["aquaclima:native_item_id"] = item["id"]
    normalized["aquaclima:acquisition_key"] = acquisition_key(item)
    normalized["aquaclima:calibration"] = calibration
    normalized["aquaclima:source_item_url"] = f"{PC_ROOT}/collections/{PC_COLLECTION}/items/{item['id']}"
    normalized["assets"] = {}
    for name, key in ASSET_KEYS.items():
        asset = copy.deepcopy(item["assets"][key])
        http._location(asset["href"])
        if f"/{product_uri}/" not in asset["href"] or "profile=cloud-optimized" not in asset.get("type", ""):
            raise ValueError(f"Asset {key} não é COG do produto SAFE declarado.")
        if asset.get("gsd") != ASSETS[name][1]:
            raise ValueError(f"Resolução STAC inesperada em {key}.")
        declared = asset.get("raster:bands", [])
        band = {"data_type": "uint8" if name == "scl" else "uint16", "nodata": 0,
                "spatial_resolution": ASSETS[name][1]}
        if name != "scl":
            band.update({field: calibration["bands"][name][field] for field in ("scale", "offset")})
        if declared and (len(declared) != 1 or any(
            field in declared[0] and declared[0][field] != value for field, value in band.items()
        )):
            raise ValueError(f"Calibração SAFE diverge de raster:bands do asset {key}.")
        if name != "scl" and [entry.get("name") for entry in asset.get("eo:bands", [])] != [key]:
            raise ValueError(f"Identificação espectral inesperada para {key}.")
        asset["raster:bands"] = [band]
        normalized["assets"][name] = asset
    return normalized


def screen_pc(http: PlanetaryHttp, pivots_path: Path, catalog_path: Path, data_dir: Path, *,
              output_path: Path, max_scenes: int, min_valid_fraction: float) -> Path:
    """Screen local SCL using the original C1 policy with a separate checkpoint."""
    if max_scenes < 1 or not math.isfinite(min_valid_fraction) or not 0 <= min_valid_fraction <= 1:
        raise ValueError("Limites de triagem Planetary Computer inválidos.")
    plan = json.loads(catalog_path.read_bytes())
    pivots_hash = checksum(pivots_path)
    if plan["collection"] != PC_COLLECTION or plan["parameters"]["pivots_sha256"] != pivots_hash:
        raise ValueError("Catálogo Planetary Computer pertence a outra coleção ou pivôs.")
    policy = {"max_scenes": max_scenes, "min_valid_fraction": min_valid_fraction, "valid_scl": list(VALID_SCL)}
    source = f"{PC_ROOT}/search"
    document = {"collection": PC_COLLECTION, "provider": PC_PROVIDER, "source": source,
                "request": plan["request"], "parameters": plan["parameters"],
                "catalog_sha256": checksum(catalog_path), "candidate_count": plan["candidate_count"],
                "screening_policy": policy, "calibration_contract": CALIBRATION_VERSION,
                "screening": [], "screening_complete": False, "state": "incomplete", "failures": []}
    previous_entries = {}
    if output_path.exists():
        if not http.is_verified(output_path, source=source):
            raise ValueError("Checkpoint Planetary Computer sem integridade verificada.")
        previous = json.loads(output_path.read_bytes())
        if any(previous.get(key) != document[key] for key in ("catalog_sha256", "screening_policy", "calibration_contract")):
            raise ValueError("Checkpoint Planetary Computer pertence a outra política ou catálogo.")
        previous_entries = {entry["id"]: entry for entry in previous["screening"]}
        document["failures"] = previous.get("failures", [])
    items = plan["candidates"]
    if any(not item.get("aquaclima:calibration") or item["aquaclima:calibration"]["contract"] != CALIBRATION_VERSION for item in items):
        raise ValueError("A triagem exige catálogo Planetary Computer normalizado e auditado.")
    _finish_screening(document, items, max_scenes)
    pivots = read_pivots(pivots_path)
    for item in sorted(items, key=lambda entry: (entry["properties"]["datetime"], entry["id"])):
        try:
            previous = previous_entries.get(item["id"])
            scl_path = _crop_path(data_dir, pivots_hash, item["id"], "scl")
            if previous and previous["status"] != "failed" and _cached_crop(scl_path, item, "scl") is not None:
                entry = previous
            else:
                entry = _screen_candidate(http, item, pivots, data_dir, pivots_hash, min_valid_fraction)
        except BudgetError:
            _finish_screening(document, items, max_scenes)
            _cache_json(http, output_path, document, source)
            raise
        document["screening"].append(entry)
        _finish_screening(document, items, max_scenes)
        _cache_json(http, output_path, document, source)
    document["screening_complete"] = all(entry["status"] != "failed" for entry in document["screening"])
    document["state"] = "complete" if document["screening_complete"] else "incomplete"
    if not output_path.exists() or json.loads(output_path.read_bytes()) != document:
        _cache_json(http, output_path, document, source)
    return output_path


def acquire_pc_crops(http: PlanetaryHttp, pivots_path: Path, scenes_path: Path, data_dir: Path, *,
                     manifest_path: Path) -> Path:
    """Download only selected PC windows with durable per-asset checkpoints."""
    plan = json.loads(scenes_path.read_bytes())
    pivots_hash, pivots = checksum(pivots_path), read_pivots(pivots_path)
    if plan["collection"] != PC_COLLECTION or plan["parameters"]["pivots_sha256"] != pivots_hash:
        raise ValueError("Plano Planetary Computer pertence a outra coleção ou pivôs.")
    source = f"{PC_ROOT}/search"
    manifest = {"collection": PC_COLLECTION, "provider": PC_PROVIDER, "pivots_sha256": pivots_hash,
                "plan_sha256": checksum(scenes_path), "state": "incomplete", "scenes": [],
                "selection_identity": {"catalog_sha256": plan.get("catalog_sha256"),
                                       "screening_policy": plan.get("screening_policy")},
                "attempt_history": []}
    if manifest_path.exists():
        if not http.is_verified(manifest_path, source=source):
            raise ValueError("Manifesto Planetary Computer sem integridade verificada.")
        previous = json.loads(manifest_path.read_bytes())
        same_plan = previous.get("plan_sha256") == manifest["plan_sha256"]
        continuing = (manifest["selection_identity"]["catalog_sha256"] is not None
                      and previous.get("selection_identity") == manifest["selection_identity"])
        if (any(previous.get(key) != manifest[key] for key in ("collection", "pivots_sha256"))
                or not (same_plan or continuing)):
            raise ValueError("Manifesto Planetary Computer pertence a outro plano.")
        if same_plan and previous.get("state") == "complete" and all(
            _cached_crop(_crop_path(data_dir, pivots_hash, item["id"], name), item, name) is not None
            for item in plan["selected"] for name in ASSETS
        ):
            return manifest_path
        manifest["attempt_history"] = previous.get("attempt_history", []) + [{
            "manifest_sha256": checksum(manifest_path), "plan_sha256": previous["plan_sha256"],
            "scenes": previous["scenes"], "state": previous.get("state"),
        }]
    for item in plan["selected"]:
        calibration = item.get("aquaclima:calibration")
        if not calibration or calibration["contract"] != CALIBRATION_VERSION:
            raise ValueError("Produto selecionado sem calibração SAFE auditada.")
        footprint = shape(item["geometry"])
        geometries = [geometry for _, geometry in pivots if footprint.intersection(geometry).area > 0]
        scene = {"id": item["id"], "date": datetime.fromisoformat(item["properties"]["datetime"]).date().isoformat(),
                 "datetime": item["properties"]["datetime"], "cloud_cover": item["properties"].get("eo:cloud_cover"),
                 "footprint": item["geometry"], "processing_baseline": item["properties"]["s2:processing_baseline"],
                 "source_item_url": item["aquaclima:source_item_url"], "native_item_id": item["aquaclima:native_item_id"],
                 "acquisition_key": item["aquaclima:acquisition_key"], "radiometric_calibration": calibration,
                 "status": "pending", "assets": {}}
        manifest["scenes"].append(scene)
        if not geometries:
            scene["status"] = "no_intersection"
            _cache_json(http, manifest_path, manifest, source)
            continue
        for name in ASSETS:
            try:
                scene["assets"][name] = _obtain_crop(http, item, name, union_all(geometries), data_dir, pivots_hash)
            except BudgetError:
                scene["status"] = "budget_interrupted"
                _cache_json(http, manifest_path, manifest, source)
                raise
            except (AcquisitionError, WindowError, OSError, ValueError, rasterio.errors.RasterioError) as error:
                scene["assets"][name] = {"status": "failed", "url": item["assets"][name]["href"], "error": str(error)}
            _cache_json(http, manifest_path, manifest, source)
        scene["status"] = "ok" if all(value["status"] == "ok" for value in scene["assets"].values()) else "missing_assets"
        _cache_json(http, manifest_path, manifest, source)
    manifest["state"] = "complete" if all(scene["status"] in {"ok", "no_intersection"} for scene in manifest["scenes"]) else "incomplete"
    _cache_json(http, manifest_path, manifest, source)
    return manifest_path
