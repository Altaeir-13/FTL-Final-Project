"""Compute cloud-screened Sentinel-2 index medians entirely from local inputs."""

from __future__ import annotations

import csv
import json
import math
from contextlib import ExitStack
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask, geometry_window
from rasterio.warp import reproject, transform_geom
from shapely.geometry import mapping, shape

from aquaclima.ingestion.sentinel import ASSETS, COLLECTION, MAX_CROP_PIXELS, VALID_SCL, read_pivots
from aquaclima.storage.http import checksum

# SCL classes vegetation (4) and bare/non-vegetated (5). Water, dark areas,
# shadows, clouds, cirrus, snow, unclassified and missing pixels are excluded.
INDEX_FIELDS = [
    "pivot_id", "date", "scene_id", "status", "ndvi_median", "ndmi_median", "valid_pixel_pct",
    "ndvi_valid_pixel_pct", "ndmi_valid_pixel_pct", "pivot_pixels", "joint_valid_pixels",
    "scene_cloud_pct", "processing_baseline", "sentinel_source",
]


def _reflectance(raw: np.ma.MaskedArray, band: dict) -> np.ndarray:
    values = np.asarray(raw.data, dtype=np.float64)
    invalid = np.ma.getmaskarray(raw) | (values == band["nodata"])
    calibrated = values * band["scale"] + band["offset"]
    # Negative reflectance may occur in L2A over dark surfaces. Exclude it
    # from these terrestrial ratios instead of clipping or modifying it.
    return np.where(invalid | (calibrated < 0), np.nan, calibrated).astype(np.float32)


def _align(values, source, *, crs, transform, grid_shape, resampling, nodata):
    if source.crs == crs and source.transform == transform and values.shape == grid_shape:
        return values
    destination = np.full(grid_shape, nodata, dtype=values.dtype)
    reproject(
        values, destination, src_transform=source.transform, src_crs=source.crs, src_nodata=nodata,
        dst_transform=transform, dst_crs=crs, dst_nodata=nodata,
        resampling=resampling,
    )
    return destination


def _index(nir: np.ndarray, other: np.ndarray, clear: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    denominator = nir + other
    valid = clear & np.isfinite(nir) & np.isfinite(other) & (denominator > 1e-6)
    ratio = np.full(nir.shape, np.nan, dtype=np.float32)
    np.divide(nir - other, denominator, out=ratio, where=valid)
    return ratio, valid


def _local_asset(data_dir: Path, asset: dict) -> Path:
    root = data_dir.resolve()
    path = (root / asset["path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise FileNotFoundError(f"Recorte local ausente ou fora do diretório de dados: {asset['path']}.")
    if path.stat().st_size != asset["bytes"] or checksum(path) != asset["sha256"]:
        raise ValueError(f"O recorte local falhou na verificação de integridade: {path}.")
    return path


def _pivot_statistics(geometry, datasets, arrays, min_valid_fraction: float) -> dict:
    swir = datasets["swir16"]
    projected = transform_geom("EPSG:4326", swir.crs, mapping(geometry))
    window = geometry_window(swir, [projected], boundless=True)
    if window.width * window.height > MAX_CROP_PIXELS:
        raise ValueError("Janela de processamento maior que o limite de pixels.")
    grid = {"crs": swir.crs, "transform": swir.window_transform(window),
            "grid_shape": (int(window.height), int(window.width))}
    inside = geometry_mask([projected], grid["grid_shape"], grid["transform"], invert=True)
    count = np.count_nonzero(inside)
    if not count:
        return {"status": "no_pixel_centers", "pivot_pixels": 0, "joint_valid_pixels": 0}

    scl = _align(arrays["scl"], datasets["scl"], resampling=Resampling.nearest, nodata=0, **grid)
    clear = inside & np.isin(scl, VALID_SCL)
    # Aggregate 10 m reflectances onto the native B11 grid before computing
    # ratios. B11 remains at 20 m. No spatial detail is inferred from it.
    nir = _align(arrays["nir"], datasets["nir"], resampling=Resampling.average, nodata=np.nan, **grid)
    red = _align(arrays["red"], datasets["red"], resampling=Resampling.average, nodata=np.nan, **grid)
    swir_values = _align(arrays["swir16"], swir, resampling=Resampling.nearest, nodata=np.nan, **grid)
    ndvi, ndvi_valid = _index(nir, red, clear)
    ndmi, ndmi_valid = _index(nir, swir_values, clear)
    joint = ndvi_valid & ndmi_valid
    joint_count = np.count_nonzero(joint)
    accepted = joint_count > 0 and joint_count / count >= min_valid_fraction
    return {
        "status": "ok" if accepted else "insufficient_valid_pixels",
        "ndvi_median": float(np.median(ndvi[joint])) if accepted else None,
        "ndmi_median": float(np.median(ndmi[joint])) if accepted else None,
        "valid_pixel_pct": 100 * joint_count / count,
        "ndvi_valid_pixel_pct": 100 * np.count_nonzero(ndvi_valid) / count,
        "ndmi_valid_pixel_pct": 100 * np.count_nonzero(ndmi_valid) / count,
        "pivot_pixels": count, "joint_valid_pixels": joint_count,
    }


def _scene_rows(scene: dict, pivots, data_dir: Path, min_valid_fraction: float):
    footprint = shape(scene["footprint"])
    scene_fields = {"scene_id": scene["id"], "date": scene["date"], "scene_cloud_pct": scene["cloud_cover"],
                    "processing_baseline": scene["processing_baseline"],
                    "sentinel_source": f"Element 84 Earth Search / {COLLECTION}"}
    with ExitStack() as stack:
        datasets, arrays = {}, {}
        if scene["status"] == "ok":
            for name in ASSETS:
                asset = scene["assets"][name]
                dataset = stack.enter_context(rasterio.open(_local_asset(data_dir, asset)))
                if dataset.count != 1 or dataset.crs is None or dataset.shape != tuple(asset["shape"]):
                    raise ValueError(f"Metadados locais do recorte não conferem em {dataset.name}.")
                band = asset["raster_band"]
                masked = dataset.read(1, masked=True)
                arrays[name] = masked.filled(0) if name == "scl" else _reflectance(masked, band)
                datasets[name] = dataset
            # Exclude cloudy native samples before any reflectance averages.
            for name in ("red", "nir", "swir16"):
                source = datasets[name]
                scl_on_source = _align(arrays["scl"], datasets["scl"], crs=source.crs,
                                       transform=source.transform, grid_shape=source.shape,
                                       resampling=Resampling.nearest, nodata=0)
                arrays[name][~np.isin(scl_on_source, VALID_SCL)] = np.nan

        for pivot_id, geometry in pivots:
            row = scene_fields | {"pivot_id": pivot_id}
            if footprint.intersection(geometry).area <= 0:
                yield row | {"status": "no_intersection", "valid_pixel_pct": 0.0}
            elif scene["status"] != "ok":
                yield row | {"status": scene["status"]}
            else:
                yield row | _pivot_statistics(geometry, datasets, arrays, min_valid_fraction)


def process_indices(pivots_path: Path, crop_manifest_path: Path, data_dir: Path,
                    *, min_valid_fraction: float, output_path: Path | None = None) -> Path:
    if not math.isfinite(min_valid_fraction) or not 0 <= min_valid_fraction <= 1:
        raise ValueError("A fração mínima de pixels válidos deve estar entre 0 e 1.")
    pivots = read_pivots(pivots_path)
    manifest = json.loads(crop_manifest_path.read_text(encoding="utf-8"))
    if manifest["collection"] != COLLECTION or manifest["pivots_sha256"] != checksum(pivots_path):
        raise ValueError("O manifesto Sentinel-2 não corresponde à coleção e ao arquivo de pivôs atuais.")
    destination = output_path if output_path is not None else data_dir / "processed" / "indices.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with temporary.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=INDEX_FIELDS)
            writer.writeheader()
            for scene in manifest["scenes"]:
                writer.writerows(_scene_rows(scene, pivots, data_dir, min_valid_fraction))
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
