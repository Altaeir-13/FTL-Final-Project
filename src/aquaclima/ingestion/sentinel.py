"""Plan Earth Search acquisitions and cache bounded, native-resolution COG crops."""

from __future__ import annotations

import io
import json
import logging
import math
import re
from collections import OrderedDict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import rasterio
from rasterio.errors import WindowError
from rasterio.features import geometry_window
from rasterio.io import MemoryFile
from rasterio.warp import transform_geom
from shapely import union_all
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from aquaclima.storage.http import AcquisitionError, HttpClient, checksum, write_atomic

STAC_ROOT = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-c1-l2a"
ASSETS = {"red": ("B04", 10), "nir": ("B08", 10), "swir16": ("B11", 20), "scl": ("SCL", 20)}
MAX_STAC_ITEMS = 500
MAX_CROP_PIXELS = 4_000_000
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


def _stac_items(http: HttpClient, request: dict) -> list[dict]:
    endpoint = f"{STAC_ROOT}/search"
    method, url, payload = "POST", endpoint, request
    seen_pages = set()
    items = {}
    while True:
        page_key = (method, url, json.dumps(payload, sort_keys=True))
        if page_key in seen_pages:
            raise ValueError("A paginação STAC repetiu uma página.")
        seen_pages.add(page_key)
        page = http.get_json(url, method=method, payload=payload)
        if page.get("type") != "FeatureCollection":
            raise ValueError("A busca STAC não retornou uma FeatureCollection.")
        for item in page["features"]:
            if item.get("collection") != COLLECTION:
                raise ValueError("Coleção inesperada na resposta STAC.")
            existing = items.setdefault(item["id"], item)
            if existing != item:
                raise ValueError(f"Metadados divergentes para item duplicado {item['id']}.")
        next_link = next((link for link in page["links"] if link["rel"] == "next"), None)
        if len(items) > MAX_STAC_ITEMS or (len(items) >= MAX_STAC_ITEMS and next_link):
            raise ValueError(f"A busca alcançou {MAX_STAC_ITEMS} itens. Reduza o intervalo consultado.")
        if next_link is None:
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
                  max_cloud: float, max_scenes: int) -> Path:
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
    path = data_dir / "raw" / "sentinel" / "scenes.json"
    source = f"{STAC_ROOT}/search"
    if http.is_verified(path, source=source):
        cache = json.loads(path.read_text(encoding="utf-8"))
        if (cache.get("request", {}).get("datetime") == request["datetime"]
                and cache.get("parameters") == parameters and cache.get("selected")):
            return path
    items = _stac_items(http, request)
    selected = _select_scenes(items, pivots, max_cloud, max_scenes)
    _cache_json(http, path, {
        "source": source, "collection": COLLECTION,
        "searched_at": datetime.now(timezone.utc).isoformat(), "request": request, "parameters": parameters,
        "candidate_count": len(items), "candidates": items,
        "selected_ids": [entry["id"] for entry in selected],
        "selection": [{key: value for key, value in entry.items() if key != "item"} for entry in selected],
        "selected": [entry["item"] for entry in selected],
    }, source)
    if not selected:
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


def acquire_crops(http: HttpClient, pivots_path: Path, scenes_path: Path, data_dir: Path) -> Path:
    pivots = read_pivots(pivots_path)
    pivots_hash = checksum(pivots_path)
    plan = json.loads(scenes_path.read_text(encoding="utf-8"))
    if plan["collection"] != COLLECTION or plan["parameters"]["pivots_sha256"] != pivots_hash:
        raise ValueError("O plano STAC não corresponde à coleção e ao arquivo de pivôs atuais.")
    directory = data_dir / "raw" / "sentinel"
    manifest_path = directory / "crops.json"
    manifest = {"collection": COLLECTION, "pivots_sha256": pivots_hash,
                "plan_sha256": checksum(scenes_path), "scenes": []}
    for item in plan["selected"]:
        scene_id = item["id"]
        if re.fullmatch(r"[A-Za-z0-9_-]+", scene_id) is None:
            raise ValueError(f"Identificador de cena incompatível com o cache: {scene_id}.")
        footprint = shape(item["geometry"])
        geometries = [geometry for _, geometry in pivots if footprint.intersection(geometry).area > 0]
        scene = {"id": scene_id, "date": _item_date(item), "datetime": item["properties"]["datetime"],
                 "cloud_cover": item["properties"].get("eo:cloud_cover"), "footprint": item["geometry"],
                 "processing_baseline": item["properties"].get("s2:processing_baseline"), "assets": {}}
        manifest["scenes"].append(scene)
        if not geometries:
            scene["status"] = "no_intersection"
            continue
        geometry = union_all(geometries)
        for name in ASSETS:
            path = directory / "windows" / pivots_hash[:16] / scene_id / f"{name}.tif"
            sidecar = path.with_suffix(".json")
            metadata = None
            if path.is_file() and sidecar.is_file():
                try:
                    stored = json.loads(sidecar.read_text(encoding="utf-8"))
                    if (stored["url"] == item["assets"][name]["href"] and stored["raster_band"] == _asset_band(item, name)
                            and stored["bytes"] == path.stat().st_size and stored["sha256"] == checksum(path)):
                        metadata = stored
                except (KeyError, OSError, ValueError):
                    LOGGER.warning("Ignorando recorte Sentinel-2 incompatível em %s", path)
            if metadata is None:
                try:
                    metadata = _crop_asset(http, item, name, geometry, path)
                except (AcquisitionError, WindowError, OSError, ValueError, rasterio.errors.RasterioError) as error:
                    LOGGER.warning("Falha no recorte %s/%s: %s", scene_id, name, error)
                    scene["assets"][name] = {"status": "failed", "url": item["assets"][name]["href"],
                                             "error": str(error)}
                    continue
                _cache_json(http, sidecar, metadata, metadata["url"])
            scene["assets"][name] = metadata | {"status": "ok", "path": path.relative_to(data_dir).as_posix()}
        scene["status"] = "ok" if all(entry["status"] == "ok" for entry in scene["assets"].values()) else "missing_assets"
    source = f"{STAC_ROOT}/search"
    if not http.is_verified(manifest_path, source=source) or json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
        _cache_json(http, manifest_path, manifest, source)
    return manifest_path
