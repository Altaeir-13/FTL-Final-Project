"""Render two real, aligned Sentinel-2 false-colour crops without new downloads."""
import json
from contextlib import ExitStack
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import transform_geom
from shapely.geometry import shape

from aquaclima.processing.indices import _align, _local_asset, _reflectance
from aquaclima.regions.pilot import verify_inventory
from aquaclima.storage.http import checksum, write_json


def main():
    root = Path("data/regions/guadalupe-pi")
    verify_inventory(root)
    destination = Path("docs/evidencias/guadalupe-pi/comparison")
    destination.mkdir(parents=True, exist_ok=True)
    pivots = json.loads((root / "pivots.geojson").read_bytes())["features"]
    observations = pd.read_csv(root / "curated/v1/observations.csv")
    reference = None
    metadata = {"region_id": "guadalupe-pi", "type": "observed_false_colour_comparison",
        "composition": "R=B08 (NIR), G=B04 (red), B=B11 (SWIR1)", "grid_resolution_m": 20,
        "stretch": {"method": "fixed linear reflectance", "min": 0, "max": .6},
        "mask": "SCL4/5 and finite nonnegative reflectance; other pixels shown grey",
        "note": "Real C1 imagery; same grid and fixed display parameters. Display colours do not diagnose irrigation. 10m bands averaged to native20m B11 grid. PNGs are visual derivatives, not analytical rasters.",
        "scenes": []}
    for month in ("2023-07", "2024-07"):
        manifest_path = root / "batches" / month / "crops.json"
        scene = json.loads(manifest_path.read_bytes())["scenes"][0]
        quality = observations.loc[observations.scene_id.eq(scene["id"]), "valid_pixel_pct"]
        if len(quality) != len(pivots) or not quality.eq(100).all():
            raise ValueError("A comparação requer os cinco pivôs com 100% de pixels válidos nas duas datas.")
        with ExitStack() as stack:
            datasets = {name: stack.enter_context(rasterio.open(_local_asset(root, asset)))
                        for name, asset in scene["assets"].items()}
            target = datasets["swir16"]
            signature = (str(target.crs), tuple(target.transform), target.shape)
            if reference is not None and signature != reference:
                raise ValueError("Datas não compartilham exatamente a mesma grade.")
            reference = signature
            grid = {"crs": target.crs, "transform": target.transform, "grid_shape": target.shape}
            values = {}
            for name in ("nir", "red", "swir16"):
                dataset = datasets[name]
                reflectance = _reflectance(dataset.read(1, masked=True), scene["assets"][name]["raster_band"])
                values[name] = _align(reflectance, dataset, resampling=Resampling.average, nodata=np.nan, **grid)
            scl = _align(datasets["scl"].read(1), datasets["scl"], resampling=Resampling.nearest, nodata=0, **grid)
            rgb = np.stack([values[n] for n in ("nir", "red", "swir16")], axis=-1)
            valid = np.isin(scl, (4, 5)) & np.isfinite(rgb).all(axis=-1)
            rgb = np.clip(np.nan_to_num(rgb) / .6, 0, 1)
            rgb[~valid] = [.88, .90, .90]
            fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
            bounds = target.bounds
            ax.imshow(rgb, extent=(bounds.left, bounds.right, bounds.bottom, bounds.top))
            for feature in pivots:
                geometry = shape(transform_geom("EPSG:4326", target.crs, feature["geometry"]))
                polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
                for polygon in polygons:
                    x, y = polygon.exterior.xy
                    ax.plot(x, y, color="white", linewidth=1.3)
                    ax.plot(x, y, color="#172e37", linewidth=.35)
                point = geometry.centroid
                ax.text(point.x, point.y, str(feature["properties"]["FID"]), color="white", fontsize=8,
                        ha="center", va="center", bbox={"facecolor": "#172e37", "alpha": .75, "pad": 1.8, "edgecolor": "none"})
            ax.set_title(f"Guadalupe / PI · {scene['date']}\nSentinel-2B L2A · falsa cor B08/B04/B11", fontsize=13, loc="left")
            ax.ticklabel_format(style="plain", useOffset=False)
            ax.set_xlabel("E (m) · UTM 23S / EPSG:32723")
            ax.set_ylabel("N (m)")
            ax.tick_params(labelsize=8)
            fig.text(.125, .02, "Contornos: ANA 2022 · Cinco pivôs com 100% de pixels conjuntos válidos na cena", fontsize=8)
            fig.tight_layout(rect=(0, .04, 1, 1))
            path = destination / f"false-colour-{scene['date']}.png"
            fig.savefig(path, facecolor="white")
            plt.close(fig)
            metadata["scenes"].append({"date": scene["date"], "scene_id": scene["id"],
                "source": f"https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a/items/{scene['id']}",
                "processing_baseline": scene["processing_baseline"], "valid_pixel_pct_each_pivot": float(quality.min()),
                "manifest_sha256": checksum(manifest_path), "image": path.name, "image_sha256": checksum(path),
                "crs": str(target.crs), "transform": list(target.transform), "shape": list(target.shape),
                "bounds": list(target.bounds), "source_crops_sha256": {n: a["sha256"] for n, a in scene["assets"].items()}})
    write_json(destination / "provenance.json", metadata)
    print(json.dumps({"status": "same verified grid", "images": [s["image"] for s in metadata["scenes"]]}))


if __name__ == "__main__":
    main()
