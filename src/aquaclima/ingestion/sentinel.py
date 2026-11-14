"""Plan Earth Search acquisitions and cache bounded, native-resolution COG crops."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import re
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from urllib.parse import urljoin, urlsplit

import numpy as np
import rasterio
from rasterio.errors import WindowError
from rasterio.features import geometry_mask, geometry_window
from rasterio.io import MemoryFile
from rasterio.warp import transform_geom
from shapely import union_all
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from aquaclima.storage.http import AcquisitionError, BudgetError, HttpClient, checksum, write_atomic

STAC_ROOT = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-c1-l2a"
ASSETS = {"red": ("B04", 10), "nir": ("B08", 10), "swir16": ("B11", 20), "scl": ("SCL", 20)}
MAX_STAC_ITEMS = 500
MAX_CROP_PIXELS = 4_000_000
VALID_SCL = (4, 5)
LOGGER = logging.getLogger(__name__)


def _cache_json(http: HttpClient, path: Path, document: dict, source: str) -> None:
    data = (json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    http.ensure_storage(len(data))
    write_atomic(path, data)
    http.record_file(path, source=source)


def read_pivots(path: Path) -> list[tuple[str, BaseGeometry]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("type") != "FeatureCollection" or "crs" in document:
        raise ValueError("Os pivôs devem ser uma FeatureCollection GeoJSON RFC 7946 em WGS84.")
    pivots = []
    ids = set()
    for feature in document["features"]:
        pivot_id = str(feature["properties"]["pivot_id"])
        geometry = shape(feature["geometry"])
        if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError(f"Geometria poligonal inválida para o pivô {pivot_id}.")
        minx, miny, maxx, maxy = geometry.bounds
        if not (-180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90):
            raise ValueError(f"Coordenadas fora de WGS84 no pivô {pivot_id}.")
        if pivot_id in ids:
            raise ValueError(f"Identificador de pivô duplicado: {pivot_id}.")
        pivots.append((pivot_id, geometry))
        ids.add(pivot_id)
    if not pivots:
        raise ValueError("A amostra não contém pivôs.")
    return pivots


class _StacLimit(ValueError):
    """The current temporal slice needs to be subdivided."""


def _stac_items(http: HttpClient, request: dict, *, cache_dir: Path | None = None,
                subdivide: bool = False) -> list[dict]:
    try:
        return _stac_page_items(http, request, cache_dir=cache_dir)
    except _StacLimit:
        if not subdivide or "datetime" not in request:
            raise
    start, end = (datetime.fromisoformat(value) for value in request["datetime"].split("/"))
    midpoint = start + (end - start) / 2
    if midpoint <= start or midpoint >= end:
        raise ValueError("A busca STAC excedeu o limite no menor intervalo temporal representável.")
    intervals = ((start, midpoint), (midpoint + timedelta(microseconds=1), end))
    items = {}
    for first, last in intervals:
        child_request = request | {"datetime": f"{first.isoformat()}/{last.isoformat()}"}
        for item in _stac_items(http, child_request, cache_dir=cache_dir, subdivide=True):
            previous = items.setdefault(item["id"], item)
            if previous != item:
                raise ValueError(f"Metadados divergentes para item duplicado {item['id']}.")
    return list(items.values())


def _stac_page_items(http: HttpClient, request: dict, *, cache_dir: Path | None) -> list[dict]:
    endpoint = f"{STAC_ROOT}/search"
    method, url, payload = "POST", endpoint, request
    seen_pages = set()
    items = {}
    request_hash = hashlib.sha256(json.dumps(request, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    while True:
        page_key = (method, url, json.dumps(payload, sort_keys=True))
        if page_key in seen_pages:
            raise ValueError("A paginação STAC repetiu uma página.")
        seen_pages.add(page_key)
        arguments = {"method": method, "payload": payload}
        if cache_dir is not None:
            arguments["path"] = cache_dir / request_hash / f"page-{len(seen_pages):04d}.json"
        page = http.get_json(url, **arguments)
        if page.get("type") != "FeatureCollection":
            raise ValueError("A busca STAC não retornou uma FeatureCollection.")
        for item in page["features"]:
            if item.get("collection") != COLLECTION:
                raise ValueError("Coleção inesperada na resposta STAC.")
            if "datetime" in request:
                first, last = (datetime.fromisoformat(value) for value in request["datetime"].split("/"))
                observed = datetime.fromisoformat(item["properties"]["datetime"])
                if not first <= observed <= last:
                    raise ValueError(f"Item STAC fora do intervalo solicitado: {item['id']}.")
            existing = items.setdefault(item["id"], item)
            if existing != item:
                raise ValueError(f"Metadados divergentes para item duplicado {item['id']}.")
        next_link = next((link for link in page["links"] if link["rel"] == "next"), None)
        if len(items) > MAX_STAC_ITEMS or (len(items) >= MAX_STAC_ITEMS and next_link):
            raise _StacLimit(f"A busca alcançou {MAX_STAC_ITEMS} itens. Reduza o intervalo consultado.")
        if next_link is None:
            matched = page.get("numberMatched", page.get("context", {}).get("matched"))
            if isinstance(matched, int) and matched > len(items):
                raise _StacLimit(f"O catálogo declarou {matched} itens e encerrou a paginação após {len(items)}.")
            if isinstance(matched, int) and matched < len(items):
                raise ValueError("O total declarado pelo STAC é menor que a quantidade de itens recebida.")
            return list(items.values())
        url = urljoin(endpoint, next_link["href"])
        if urlsplit(url).netloc != urlsplit(STAC_ROOT).netloc or urlsplit(url).scheme != "https":
            raise ValueError(f"Domínio inesperado na paginação STAC: {url}.")
        method = next_link.get("method", "GET").upper()
        body = next_link.get("body", {})
        if method not in {"POST", "GET"}:
            raise ValueError(f"Método de paginação STAC não aceito: {method}.")
        payload = ((request | body) if next_link.get("merge") else body) if method == "POST" else None


def _item_date(item: dict) -> str:
    return datetime.fromisoformat(item["properties"]["datetime"]).date().isoformat()


def _select_scenes(items: list[dict], pivots: list[tuple[str, BaseGeometry]], max_cloud: float,
                   max_scenes: int) -> list[dict]:
    candidates = []
    for item in items:
        footprint = shape(item["geometry"]) if item.get("geometry") else None
        cloud = item["properties"].get("eo:cloud_cover")
        if footprint is None or not footprint.is_valid or cloud is None or not 0 <= cloud <= max_cloud:
            continue
        if not ASSETS.keys() <= item["assets"].keys():
            continue
        intersection_count = sum(footprint.intersection(geom).area > 0 for _, geom in pivots)
        if intersection_count:
            candidates.append({
                "item": item, "id": item["id"], "date": _item_date(item), "cloud_cover": cloud,
                "full_pivots": sum(footprint.covers(geom) for _, geom in pivots),
                "intersecting_pivots": intersection_count,
            })
    selected = []
    months, dates = set(), set()

    def rank(candidate):
        return (
            candidate["full_pivots"] != len(pivots), candidate["date"][:7] in months,
            -candidate["full_pivots"], -candidate["intersecting_pivots"], candidate["cloud_cover"],
            candidate["date"], candidate["id"],
        )

    for _ in range(max_scenes):
        candidate = min((entry for entry in candidates if entry["date"] not in dates), key=rank, default=None)
        if candidate is None:
            break
        selected.append(candidate)
        dates.add(candidate["date"])
        months.add(candidate["date"][:7])
    return sorted(selected, key=lambda candidate: candidate["date"])


def search_scenes(http: HttpClient, pivots_path: Path, data_dir: Path, *, start: date, end: date,
                  max_cloud: float, max_scenes: int, plan_path: Path | None = None,
                  allow_empty: bool = False) -> Path:
    if end < start or not 0 <= max_cloud <= 100 or max_scenes < 1:
        raise ValueError("Datas ou limites de busca Sentinel-2 inválidos.")
    pivots = read_pivots(pivots_path)
    request = {
        "collections": [COLLECTION],
        "intersects": mapping(union_all([geometry for _, geometry in pivots])),
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59.999999Z",
        "limit": 50,
    }
    parameters = {"pivots_sha256": checksum(pivots_path), "max_cloud": max_cloud, "max_scenes": max_scenes}
    path = plan_path if plan_path is not None else data_dir / "raw" / "sentinel" / "scenes.json"
    source = f"{STAC_ROOT}/search"
    if http.is_verified(path, source=source):
        cache = json.loads(path.read_text(encoding="utf-8"))
        if (cache.get("request", {}).get("datetime") == request["datetime"]
                and cache.get("parameters") == parameters and (cache.get("selected") or allow_empty)):
            return path
        if plan_path is not None:
            raise ValueError(f"O catálogo mensal existente não corresponde à configuração: {path}.")
    elif plan_path is not None and path.exists():
        raise ValueError(f"O catálogo mensal existente não passou pela verificação de integridade: {path}.")
    page_cache = path.parent / f"{path.stem}-pages" if plan_path is not None else None
    items = _stac_items(http, request, cache_dir=page_cache, subdivide=plan_path is not None)
    selected = _select_scenes(items, pivots, max_cloud, max_scenes)
    _cache_json(http, path, {
        "source": source, "collection": COLLECTION,
        "searched_at": datetime.now(timezone.utc).isoformat(), "request": request, "parameters": parameters,
        "candidate_count": len(items), "candidates": items,
        "selected_ids": [entry["id"] for entry in selected],
        "selection": [{key: value for key, value in entry.items() if key != "item"} for entry in selected],
        "selected": [entry["item"] for entry in selected],
        "query_complete": True,
    }, source)
    if not selected and not allow_empty:
        raise ValueError(f"Nenhuma cena com interseção e cobertura de nuvens compatíveis. Consulte {path}.")
    return path


class _RangeAsset:
    """Shared block cache for GDAL's independent handles to one remote COG."""

    block_size = 128 * 1024
    max_blocks = 64

    def __init__(self, http: HttpClient, url: str, size: int, etag: str | None):
        self.http = http
        self.url = url
        self.size = size
        self.etag = etag
        self.cache: OrderedDict[int, bytes] = OrderedDict()
        self.error: Exception | None = None
        self.transferred = 0

    def open(self, path: str, mode: str = "rb") -> _RangeFile:
        if Path(path).name != "source.tif" or mode not in {"r", "rb"}:
            raise FileNotFoundError(path)
        return _RangeFile(self)

    def block(self, start: int) -> bytes:
        if start not in self.cache:
            end = min(self.size, start + self.block_size)
            block = self.http.range_bytes(self.url, start, end, etag=self.etag)
            if len(block) != end - start:
                raise OSError("Segmento do COG incompleto.")
            self.transferred += len(block)
            self.cache[start] = block
            if len(self.cache) > self.max_blocks:
                self.cache.popitem(last=False)
        self.cache.move_to_end(start)
        return self.cache[start]


class _RangeFile(io.RawIOBase):
    """Seekable GDAL input whose every network byte passes through the HTTP budget."""

    def __init__(self, source: _RangeAsset):
        self.source = source
        self.position = 0

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.position, io.SEEK_END: self.source.size}[whence]
        if offset + base < 0:
            raise ValueError("Posição de arquivo negativa.")
        self.position = offset + base
        return self.position

    def read(self, size: int = -1) -> bytes:
        # Prevent an accidental GDAL fallback from transferring a complete tile.
        if size < 0 or size > 16 * 1024**2:
            self.source.error = OSError("Leitura de COG sem limite ou superior a 16 MiB.")
            return b""
        if self.source.error is not None:
            return b""
        parts = []
        stop = min(self.source.size, self.position + size)
        while self.position < stop:
            start = self.position // self.source.block_size * self.source.block_size
            try:
                block = self.source.block(start)
            except Exception as error:
                # GDAL's C file callbacks cannot propagate the Python exception.
                self.source.error = error
                return b""
            end = min(start + len(block), stop)
            parts.append(block[self.position - start:end - start])
            self.position = end
        return b"".join(parts)


def _asset_band(item: dict, name: str) -> dict:
    asset = item["assets"][name]
    bands = asset.get("raster:bands", [])
    if len(bands) != 1:
        raise ValueError(f"Metadados raster:bands ausentes ou ambíguos em {item['id']}/{name}.")
    band = bands[0]
    if band.get("nodata") != 0 or band.get("spatial_resolution") != ASSETS[name][1]:
        raise ValueError(f"NoData ou resolução não esperados em {item['id']}/{name}.")
    expected_type = "uint8" if name == "scl" else "uint16"
    if band.get("data_type") != expected_type or not asset.get("href"):
        raise ValueError(f"Tipo de pixel ou endereço ausente/inválido em {item['id']}/{name}.")
    if name != "scl":
        eo_names = [value.get("name") for value in asset.get("eo:bands", [])]
        if eo_names != [ASSETS[name][0]]:
            raise ValueError(f"Identificação espectral incompatível em {item['id']}/{name}: {eo_names}.")
        if not (math.isfinite(band.get("scale", math.nan)) and band["scale"] > 0
                and math.isfinite(band.get("offset", math.nan))):
            raise ValueError(f"Escala ou offset ausente/inválido em {item['id']}/{name}.")
    return band


def _crop_asset(http: HttpClient, item: dict, name: str, geometry: BaseGeometry, path: Path) -> dict:
    band = _asset_band(item, name)
    asset = item["assets"][name]
    url = asset["href"]
    if urlsplit(url).scheme != "https":
        raise ValueError(f"O asset {name} deve usar HTTPS público.")
    headers = {key.lower(): value for key, value in http.head(url).items()}
    size = int(headers.get("content-length", 0))
    if size <= 0:
        raise ValueError(f"O servidor não informou o tamanho de {url}.")
    if asset.get("file:size", size) != size:
        raise ValueError(f"Tamanho do COG diverge do STAC em {item['id']}/{name}.")
    remote = _RangeAsset(http, url, size, headers.get("etag"))
    try:
        with rasterio.open("source.tif", driver="GTiff", opener=remote.open) as source:
            resolution = ASSETS[name][1]
            if (source.crs is None or not source.crs.is_projected or source.crs.linear_units_factor[1] != 1
                    or source.count != 1 or not all(math.isclose(value, resolution) for value in source.res)):
                raise ValueError(f"Grade, CRS ou número de bandas inesperado em {item['id']}/{name}.")
            epsg = asset.get("proj:epsg", item["properties"].get("proj:epsg"))
            code = asset.get("proj:code", item["properties"].get("proj:code"))
            if (epsg is not None and source.crs.to_epsg() != epsg) or (code is not None and str(source.crs) != code):
                raise ValueError(f"CRS do COG diverge do STAC em {item['id']}/{name}.")
            if list(source.shape) != asset.get("proj:shape", list(source.shape)):
                raise ValueError(f"Dimensão do COG diverge do STAC em {item['id']}/{name}.")
            stac_transform = asset.get("proj:transform")
            if stac_transform is not None:
                transform = tuple(source.transform)[:len(stac_transform)]
                if len(stac_transform) not in {6, 9} or not all(
                    math.isclose(actual, expected, abs_tol=1e-8) for actual, expected in zip(transform, stac_transform)
                ):
                    raise ValueError(f"Transformação do COG diverge do STAC em {item['id']}/{name}.")
            if source.nodata is not None and source.nodata != band["nodata"]:
                raise ValueError(f"NoData do COG diverge do STAC em {item['id']}/{name}.")
            if source.dtypes != (band["data_type"],):
                raise ValueError(f"Tipo de pixel do COG diverge do STAC em {item['id']}/{name}.")
            if name != "scl" and (source.scales, source.offsets) != ((1.0,), (0.0,)):
                if not (math.isclose(source.scales[0], band["scale"], rel_tol=1e-6)
                        and math.isclose(source.offsets[0], band["offset"], abs_tol=1e-8)):
                    raise ValueError(f"Calibração do COG diverge do STAC em {item['id']}/{name}.")
            projected = transform_geom("EPSG:4326", source.crs, mapping(geometry))
            window = geometry_window(source, [projected], pad_x=2, pad_y=2)
            if window.width * window.height > MAX_CROP_PIXELS:
                raise ValueError(f"Janela superior a {MAX_CROP_PIXELS:,} pixels em {item['id']}/{name}.")
            values = source.read(1, window=window, masked=True).filled(band["nodata"])
            profile = {
                "driver": "GTiff", "count": 1, "crs": source.crs, "nodata": band["nodata"],
                "transform": source.window_transform(window), "dtype": values.dtype,
                "height": values.shape[0], "width": values.shape[1], "compress": "deflate",
            }
            source_shape = list(source.shape)
            source_resolution = list(source.res)
    except Exception:
        if remote.error is not None:
            raise remote.error from None
        raise
    if remote.error is not None:
        raise remote.error

    with MemoryFile() as buffer:
        with buffer.open(**profile) as crop:
            crop.write(values, 1)
            if name != "scl":
                crop.scales = (band["scale"],)
                crop.offsets = (band["offset"],)
            crop.update_tags(source=url, sentinel_band=ASSETS[name][0], sentinel_scene=item["id"])
        data = buffer.read()
    http.ensure_storage(len(data))
    write_atomic(path, data)
    http.record_file(path, source=url)
    with rasterio.open(path) as crop:
        return {
            "url": url, "source_bytes": size, "source_etag": headers.get("etag"),
            "source_stac_multihash": asset.get("file:checksum"),
            "source_last_modified": headers.get("last-modified"), "source_shape": source_shape,
            "range_bytes": remote.transferred, "bytes": path.stat().st_size, "sha256": checksum(path),
            "crs": str(crop.crs), "shape": list(crop.shape), "resolution": source_resolution,
            "bounds": list(crop.bounds), "window": list(window.flatten()), "raster_band": band,
            "acquired_at": datetime.now(timezone.utc).isoformat(),
        }


def _crop_path(data_dir: Path, pivots_hash: str, scene_id: str, name: str) -> Path:
    if re.fullmatch(r"[A-Za-z0-9_-]+", scene_id) is None:
        raise ValueError(f"Identificador de cena incompatível com o cache: {scene_id}.")
    return data_dir / "raw" / "sentinel" / "windows" / pivots_hash[:16] / scene_id / f"{name}.tif"


def _cached_crop(path: Path, item: dict, name: str) -> dict | None:
    sidecar = path.with_suffix(".json")
    if not path.is_file() or not sidecar.is_file():
        return None
    try:
        stored = json.loads(sidecar.read_text(encoding="utf-8"))
        if (stored["url"] == item["assets"][name]["href"] and stored["raster_band"] == _asset_band(item, name)
                and stored["bytes"] == path.stat().st_size and stored["sha256"] == checksum(path)):
            return stored
    except (KeyError, OSError, ValueError):
        LOGGER.warning("Ignorando recorte Sentinel-2 incompatível em %s", path)
    return None


def _obtain_crop(http: HttpClient, item: dict, name: str, geometry: BaseGeometry,
                 data_dir: Path, pivots_hash: str) -> dict:
    path = _crop_path(data_dir, pivots_hash, item["id"], name)
    metadata = _cached_crop(path, item, name)
    if metadata is None:
        metadata = _crop_asset(http, item, name, geometry, path)
        _cache_json(http, path.with_suffix(".json"), metadata, metadata["url"])
    return metadata | {"status": "ok", "path": path.relative_to(data_dir).as_posix()}


def acquire_crops(http: HttpClient, pivots_path: Path, scenes_path: Path, data_dir: Path,
                  *, manifest_path: Path | None = None) -> Path:
    pivots = read_pivots(pivots_path)
    pivots_hash = checksum(pivots_path)
    plan = json.loads(scenes_path.read_text(encoding="utf-8"))
    if plan["collection"] != COLLECTION or plan["parameters"]["pivots_sha256"] != pivots_hash:
        raise ValueError("O plano STAC não corresponde à coleção e ao arquivo de pivôs atuais.")
    checkpointed = manifest_path is not None
    destination = manifest_path if checkpointed else data_dir / "raw" / "sentinel" / "crops.json"
    manifest = {"collection": COLLECTION, "pivots_sha256": pivots_hash,
                "plan_sha256": checksum(scenes_path), "scenes": []}
    source = f"{STAC_ROOT}/search"
    if checkpointed:
        selection_identity = {"catalog_sha256": plan.get("catalog_sha256"), "screening_policy": plan.get("screening_policy")}
        manifest.update(state="incomplete", selected_ids=[item["id"] for item in plan["selected"]],
                        selection_identity=selection_identity, attempt_history=[])
        if destination.exists():
            if not http.is_verified(destination, source=source):
                raise ValueError(f"O checkpoint de recortes não passou pela verificação de integridade: {destination}.")
            previous = json.loads(destination.read_text(encoding="utf-8"))
            same_inputs = all(previous.get(key) == manifest[key] for key in ("collection", "pivots_sha256"))
            same_plan = previous.get("plan_sha256") == manifest["plan_sha256"]
            continuing_selection = (selection_identity["catalog_sha256"] is not None
                                    and previous.get("selection_identity") == selection_identity)
            if not same_inputs or not (same_plan or continuing_selection):
                raise ValueError(f"O checkpoint de recortes pertence a outro plano: {destination}.")
            if same_plan and previous.get("state") == "complete" and all(
                _cached_crop(_crop_path(data_dir, pivots_hash, item["id"], name), item, name) is not None
                for item in plan["selected"] for name in ASSETS
            ):
                return destination
            manifest["attempt_history"] = previous.get("attempt_history", []) + [{
                "manifest_sha256": checksum(destination), "scenes": previous["scenes"],
                "plan_sha256": previous["plan_sha256"], "selected_ids": previous.get("selected_ids"),
                "state": previous.get("state"), "recorded_at": datetime.now(timezone.utc).isoformat(),
            }]
    for item in plan["selected"]:
        scene_id = item["id"]
        _crop_path(data_dir, pivots_hash, scene_id, "scl")
        footprint = shape(item["geometry"])
        geometries = [geometry for _, geometry in pivots if footprint.intersection(geometry).area > 0]
        scene = {"id": scene_id, "date": _item_date(item), "datetime": item["properties"]["datetime"],
                 "cloud_cover": item["properties"].get("eo:cloud_cover"), "footprint": item["geometry"],
                 "processing_baseline": item["properties"].get("s2:processing_baseline"), "assets": {}}
        scene["status"] = "pending"
        manifest["scenes"].append(scene)
        if not geometries:
            scene["status"] = "no_intersection"
            if checkpointed:
                _cache_json(http, destination, manifest, source)
            continue
        geometry = union_all(geometries)
        for name in ASSETS:
            try:
                scene["assets"][name] = _obtain_crop(http, item, name, geometry, data_dir, pivots_hash)
            except BudgetError as error:
                if checkpointed:
                    scene["status"] = "budget_interrupted"
                    scene["assets"][name] = {"status": "budget_interrupted", "error": str(error)}
                    _cache_json(http, destination, manifest, source)
                raise
            except (AcquisitionError, WindowError, OSError, ValueError, rasterio.errors.RasterioError) as error:
                LOGGER.warning("Falha no recorte %s/%s: %s", scene_id, name, error)
                scene["assets"][name] = {"status": "failed", "url": item["assets"][name]["href"], "error": str(error)}
            if checkpointed:
                _cache_json(http, destination, manifest, source)
        scene["status"] = "ok" if all(entry["status"] == "ok" for entry in scene["assets"].values()) else "missing_assets"
        if checkpointed:
            _cache_json(http, destination, manifest, source)
    if checkpointed:
        manifest["state"] = "complete" if all(scene["status"] in {"ok", "no_intersection"} for scene in manifest["scenes"]) else "incomplete"
    if not http.is_verified(destination, source=source) or json.loads(destination.read_text(encoding="utf-8")) != manifest:
        _cache_json(http, destination, manifest, source)
    return destination


def _scl_pivot_quality(path: Path, pivots: list[tuple[str, BaseGeometry]], footprint: BaseGeometry) -> dict:
    quality = {}
    with rasterio.open(path) as dataset:
        for pivot_id, geometry in pivots:
            if footprint.intersection(geometry).area <= 0:
                quality[pivot_id] = {"status": "no_intersection", "total_pixels": None,
                                     "clear_pixels": 0, "valid_fraction": 0.0}
                continue
            projected = transform_geom("EPSG:4326", dataset.crs, mapping(geometry))
            window = geometry_window(dataset, [projected], boundless=True)
            if window.width * window.height > MAX_CROP_PIXELS:
                raise ValueError(f"Janela SCL do pivô {pivot_id} excede o limite de pixels.")
            mask_shape = (int(window.height), int(window.width))
            inside = geometry_mask([projected], mask_shape, dataset.window_transform(window), invert=True)
            values = dataset.read(1, window=window, boundless=True, masked=True).filled(0)
            total = int(np.count_nonzero(inside))
            clear = int(np.count_nonzero(inside & np.isin(values, VALID_SCL)))
            quality[pivot_id] = {"status": "ok" if total else "no_pixel_centers", "total_pixels": total,
                                 "clear_pixels": clear, "valid_fraction": clear / total if total else 0.0}
    return quality


def _screen_candidate(http: HttpClient, item: dict, pivots, data_dir: Path,
                       pivots_hash: str, min_valid_fraction: float) -> dict:
    result = {"id": item["id"], "date": _item_date(item),
              "cloud_cover": item["properties"].get("eo:cloud_cover"), "pivots": {}}
    footprint = shape(item["geometry"]) if item.get("geometry") else None
    if footprint is None or not footprint.is_valid or footprint.is_empty:
        return result | {"status": "rejected", "reason": "invalid_scene_footprint"}
    geometries = [geometry for _, geometry in pivots if footprint.intersection(geometry).area > 0]
    if not geometries:
        return result | {"status": "rejected", "reason": "no_intersection"}
    try:
        for name in ASSETS:
            _asset_band(item, name)
    except (KeyError, TypeError, ValueError) as error:
        return result | {"status": "rejected", "reason": "invalid_asset_metadata", "error": str(error)}
    try:
        scl = _obtain_crop(http, item, "scl", union_all(geometries), data_dir, pivots_hash)
        result["scl"] = scl
        result["pivots"] = _scl_pivot_quality(data_dir / scl["path"], pivots, footprint)
    except (AcquisitionError, WindowError, OSError, ValueError, rasterio.errors.RasterioError) as error:
        return result | {"status": "failed", "reason": "scl_acquisition_failed", "error": str(error)}
    fractions = [value["valid_fraction"] for value in result["pivots"].values()]
    eligible_count = sum(value > 0 and value >= min_valid_fraction for value in fractions)
    return result | {
        "status": "eligible" if eligible_count else "rejected",
        "reason": "scl_threshold_met" if eligible_count else "no_pivot_above_scl_threshold",
        "eligible_pivots": eligible_count, "minimum_valid_fraction": min(fractions),
        "mean_valid_fraction": sum(fractions) / len(fractions),
    }


def _finish_screening(document: dict, items: list[dict], max_scenes: int) -> None:
    candidates = {item["id"]: item for item in items}
    eligible = sorted((entry for entry in document["screening"] if entry["status"] == "eligible"), key=lambda entry: (
        -entry["eligible_pivots"], -entry["minimum_valid_fraction"], -entry["mean_valid_fraction"],
        entry["cloud_cover"] if entry["cloud_cover"] is not None else math.inf, entry["date"], entry["id"],
    ))
    selected, dates = [], set()
    for entry in eligible:
        if len(selected) >= max_scenes:
            break
        if entry["date"] not in dates:
            selected.append(entry)
            dates.add(entry["date"])
    selected.sort(key=lambda entry: (entry["date"], entry["id"]))
    document["selected_ids"] = [entry["id"] for entry in selected]
    document["selected"] = [candidates[entry["id"]] for entry in selected]
    document["selection"] = [{key: value for key, value in entry.items() if key != "scl"} for entry in selected]
    for entry in document["screening"]:
        if entry["status"] == "eligible":
            entry["selection_reason"] = "selected" if entry["id"] in document["selected_ids"] else "lower_local_quality_or_duplicate_date"


def screen_scenes(http: HttpClient, pivots_path: Path, scenes_path: Path, data_dir: Path,
                   *, output_path: Path, max_scenes: int, min_valid_fraction: float) -> Path:
    """Evaluate every candidate's local SCL before acquiring reflectance bands.

    A candidate can be selected when at least one pivot passes the threshold.
    The final index stage independently verifies all bands on the common grid.
    """
    if max_scenes < 1 or not math.isfinite(min_valid_fraction) or not 0 <= min_valid_fraction <= 1:
        raise ValueError("Limites de triagem SCL inválidos.")
    pivots = read_pivots(pivots_path)
    pivots_hash = checksum(pivots_path)
    plan = json.loads(scenes_path.read_text(encoding="utf-8"))
    if plan["collection"] != COLLECTION or plan["parameters"]["pivots_sha256"] != pivots_hash:
        raise ValueError("O catálogo STAC não corresponde à coleção e aos pivôs atuais.")
    policy = {"max_scenes": max_scenes, "min_valid_fraction": min_valid_fraction, "valid_scl": list(VALID_SCL)}
    source = f"{STAC_ROOT}/search"
    document = {
        "collection": COLLECTION, "source": source, "request": plan["request"], "parameters": plan["parameters"],
        "catalog_sha256": checksum(scenes_path), "candidate_count": plan["candidate_count"],
        "screening_policy": policy, "screening": [], "screening_complete": False,
        "state": "incomplete", "failures": [], "selected_ids": [], "selected": [], "selection": [],
    }
    if output_path.exists():
        if not http.is_verified(output_path, source=source):
            raise ValueError(f"O checkpoint de triagem não passou pela verificação de integridade: {output_path}.")
        previous = json.loads(output_path.read_text(encoding="utf-8"))
        if previous.get("catalog_sha256") != document["catalog_sha256"] or previous.get("screening_policy") != policy:
            raise ValueError(f"O checkpoint de triagem pertence a outro catálogo ou política: {output_path}.")
        if previous.get("screening_complete"):
            return output_path
        document["failures"] = previous.get("failures", [])
    items = plan["candidates"]
    for item in sorted(items, key=lambda value: (_item_date(value), value["id"])):
        try:
            entry = _screen_candidate(http, item, pivots, data_dir, pivots_hash, min_valid_fraction)
        except BudgetError as error:
            document["failures"].append({"id": item["id"], "reason": "budget_interrupted", "error": str(error),
                                         "at": datetime.now(timezone.utc).isoformat()})
            _finish_screening(document, items, max_scenes)
            _cache_json(http, output_path, document, source)
            raise
        document["screening"].append(entry)
        if entry["status"] == "failed":
            document["failures"].append({"id": item["id"], "reason": entry["reason"], "error": entry["error"],
                                         "at": datetime.now(timezone.utc).isoformat()})
        _finish_screening(document, items, max_scenes)
        _cache_json(http, output_path, document, source)
    document["screening_complete"] = all(entry["status"] != "failed" for entry in document["screening"])
    document["state"] = "complete" if document["screening_complete"] else "incomplete"
    _cache_json(http, output_path, document, source)
    return output_path


def _estimated_window_pixels(geometry: BaseGeometry, item: dict, name: str) -> int:
    asset = item["assets"][name]
    centroid = geometry.centroid
    zone = min(60, max(1, int((centroid.x + 180) // 6) + 1))
    local_utm = (32600 if centroid.y >= 0 else 32700) + zone
    target_crs = asset.get("proj:code", item["properties"].get("proj:code"))
    if target_crs is None:
        target_crs = asset.get("proj:epsg", item["properties"].get("proj:epsg", local_utm))
    left, bottom, right, top = shape(transform_geom("EPSG:4326", target_crs, mapping(geometry))).bounds
    resolution = ASSETS[name][1]
    width = math.ceil((right - left) / resolution) + 5
    height = math.ceil((top - bottom) / resolution) + 5
    pixels = width * height
    if pixels > MAX_CROP_PIXELS:
        raise ValueError(f"A janela estimada de {item['id']}/{name} excede o limite de pixels.")
    return pixels


def estimate_acquisition(pivots_path: Path, scenes_path: Path, data_dir: Path,
                          *, max_scenes: int = 2) -> dict:
    """Forecast cropped payloads without HTTP and keep full-scene sizes separate.

    Compression and TIFF layout vary between acquisitions. These estimates
    include a safety factor and the HTTP client enforces the actual hard cap.
    """
    if max_scenes < 1:
        raise ValueError("A estimativa requer ao menos uma cena por período.")
    pivots = read_pivots(pivots_path)
    pivots_hash = checksum(pivots_path)
    plan = json.loads(scenes_path.read_text(encoding="utf-8"))
    if plan["collection"] != COLLECTION or plan["parameters"]["pivots_sha256"] != pivots_hash:
        raise ValueError("O catálogo não corresponde à coleção e aos pivôs da estimativa.")
    items = plan.get("candidates", plan["selected"])
    geometry = union_all([value for _, value in pivots])
    pilot_path = data_dir / "raw" / "sentinel" / "crops.json"
    calibration = {name: [] for name in ASSETS}
    if pilot_path.is_file():
        pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
        for scene in pilot.get("scenes", []):
            for name, asset in scene.get("assets", {}).items():
                if name in calibration and asset.get("status") == "ok" and asset.get("range_bytes", 0) > 0:
                    calibration[name].append((asset["range_bytes"], math.prod(asset["shape"])))

    def predicted(item, name):
        path = _crop_path(data_dir, pivots_hash, item["id"], name)
        if _cached_crop(path, item, name) is not None:
            return 0
        pixels = _estimated_window_pixels(geometry, item, name)
        if calibration[name]:
            baseline = median(value[0] for value in calibration[name])
            per_pixel = median(value[0] / value[1] for value in calibration[name])
            return math.ceil(2 * max(baseline, pixels * per_pixel))
        # No TIFF headers are fetched during planning. Reserve metadata and
        # neighboring compressed blocks in addition to raw window samples.
        sample_bytes = 1 if name == "scl" else 2
        return 2 * (2 * 1024**2 + pixels * sample_bytes)

    scl_bytes, per_date_bands = 0, {}
    for item in items:
        if not ASSETS.keys() <= item.get("assets", {}).keys():
            continue
        footprint = shape(item["geometry"]) if item.get("geometry") else None
        if footprint is None or not footprint.is_valid or footprint.intersection(geometry).area <= 0:
            continue
        if "screening" not in plan:
            scl_bytes += predicted(item, "scl")
        band_bytes = sum(predicted(item, name) for name in ("red", "nir", "swir16"))
        day = _item_date(item)
        per_date_bands[day] = max(per_date_bands.get(day, 0), band_bytes)
    selected_bound = min(max_scenes, len(per_date_bands))
    band_bytes = sum(sorted(per_date_bands.values(), reverse=True)[:selected_bound])
    full_sizes = [item.get("assets", {}).get(name, {}).get("file:size") for item in items for name in ASSETS]
    known_sizes = all(isinstance(value, int) and value > 0 for value in full_sizes)
    return {
        "candidate_count": plan["candidate_count"], "selected_scene_count_upper_bound": selected_bound,
        "estimated_scl_transfer_bytes": scl_bytes, "estimated_band_transfer_bytes": band_bytes,
        "estimated_transfer_bytes": scl_bytes + band_bytes,
        "declared_full_cog_bytes": sum(full_sizes) if known_sizes else None,
        "declared_full_cog_scope": "catalog_candidates" if "candidates" in plan else "selected_items",
        "method": "pilot_range_scaled_safety2" if any(calibration.values()) else "window_samples_plus_block_overhead_safety2",
        "estimate_is_hard_cap": False,
        "assumptions": [
            "A triagem lê somente SCL dos candidatos ainda não armazenados.",
            "As três bandas contínuas são adquiridas apenas para as datas selecionadas.",
            "A estimativa utiliza o maior custo por data e fator de segurança 2 sobre o piloto ou a reserva sem calibração.",
            "Compressão, blocos TIFF, retentativas e respostas STAC podem alterar os bytes efetivos.",
            "O limite financeiro é zero e os limites efetivos de bytes e requisições são impostos pelo HttpClient.",
        ],
    }
