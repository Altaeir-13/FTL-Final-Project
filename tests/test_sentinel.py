import csv
import json
from datetime import date
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_geom
from shapely.geometry import box, mapping, shape

from aquaclima.ingestion.sentinel import ASSETS, COLLECTION, STAC_ROOT, _asset_band, _stac_items, acquire_crops, search_scenes
from aquaclima.processing.indices import _index, _reflectance, process_indices
from aquaclima.storage.http import AcquisitionError, BudgetError, HttpClient, checksum, write_json


class LocalStac(HttpClient):
    def __init__(self, tmp_path, item, assets):
        super().__init__(ledger=tmp_path / "ledger.jsonl")
        self.item = item
        self.assets = assets
        self.calls = []

    def get_json(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return {"type": "FeatureCollection", "features": [self.item], "links": []}

    def head(self, url):
        self.calls.append(("HEAD", url))
        return {"Content-Length": len(self.assets[url]), "ETag": '"test"'}

    def range_bytes(self, url, start, stop, *, etag=None):
        assert etag == '"test"'
        self.calls.append(("GET", url, start, stop))
        return self.assets[url][start:stop]


def _wgs84(left, bottom, right, top):
    return transform_geom("EPSG:32722", "EPSG:4326", mapping(box(left, bottom, right, top)))


@pytest.fixture
def stac_case(tmp_path):
    item = {
        "collection": COLLECTION, "id": "S2A_TEST_L2A",
        "properties": {"datetime": "2025-07-01T12:30:00Z", "eo:cloud_cover": 5.0, "proj:epsg": 32722,
                       "s2:processing_baseline": "05.11"},
        "geometry": _wgs84(790000, 8104880, 795120, 8110000), "assets": {},
    }
    assets = {}
    for name, (band_name, resolution) in ASSETS.items():
        url = f"https://example.invalid/{name}.tif"
        size = 5120 // resolution
        dtype = "uint8" if name == "scl" else "uint16"
        raster_band = {"nodata": 0, "data_type": dtype, "spatial_resolution": resolution}
        if name != "scl":
            raster_band.update(scale=0.0001, offset=-0.1)
        item["assets"][name] = {"href": url, "eo:bands": [{"name": band_name}], "raster:bands": [raster_band]}
        values = np.full((size, size), {"red": 2000, "nir": 4000, "swir16": 3000, "scl": 4}[name], dtype=dtype)
        if name == "red":
            values[40:42, 40:42] = [[1000, 1000], [1000, 5000]]
        if name == "swir16":
            values[21, 20] = 0
        if name == "scl":
            values[20, 21] = 9
        source = tmp_path / f"source_{name}.tif"
        with rasterio.open(source, "w", driver="GTiff", height=size, width=size, count=1, dtype=dtype,
                           nodata=0, tiled=True, blockxsize=64, blockysize=64, crs="EPSG:32722",
                           transform=from_origin(790000, 8110000, resolution, resolution)) as dataset:
            dataset.write(values, 1)
        assets[url] = source.read_bytes()
    pivots = tmp_path / "pivots.geojson"
    pivots.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"pivot_id": "A", "area_ha": 0.16},
         "geometry": _wgs84(790400, 8109560, 790440, 8109600)},
        {"type": "Feature", "properties": {"pivot_id": "B", "area_ha": 0.16},
         "geometry": _wgs84(795200, 8109560, 795240, 8109600)},
    ]}), encoding="utf-8")
    return LocalStac(tmp_path, item, assets), pivots


def _rows(path: Path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def test_window_acquisition_and_offline_processing_are_idempotent(stac_case, tmp_path):
    http, pivots = stac_case
    dates = {"start": date(2025, 7, 1), "end": date(2025, 7, 31), "max_cloud": 60, "max_scenes": 2}
    plan = search_scenes(http, pivots, tmp_path, **dates)
    manifest = acquire_crops(http, pivots, plan, tmp_path)
    scene = json.loads(manifest.read_text(encoding="utf-8"))["scenes"][0]
    assert scene["status"] == "ok"
    assert scene["assets"]["red"]["range_bytes"] < scene["assets"]["red"]["source_bytes"]
    assert scene["assets"]["red"]["shape"][0] < 16
    assert scene["assets"]["nir"]["resolution"] == [10, 10]
    assert scene["assets"]["swir16"]["resolution"] == [20, 20]
    calls = list(http.calls)
    assert search_scenes(http, pivots, tmp_path, **dates) == plan
    assert acquire_crops(http, pivots, plan, tmp_path) == manifest
    assert http.calls == calls

    path = process_indices(pivots, manifest, tmp_path, min_valid_fraction=0.5)
    accepted, non_intersecting = _rows(path)
    assert accepted["status"] == "ok"
    assert float(accepted["ndvi_median"]) == pytest.approx(0.5)
    assert float(accepted["ndmi_median"]) == pytest.approx(0.2)
    assert float(accepted["valid_pixel_pct"]) == 50
    assert float(accepted["ndvi_valid_pixel_pct"]) == 75
    assert non_intersecting["status"] == "no_intersection"
    original = path.read_bytes()
    assert process_indices(pivots, manifest, tmp_path, min_valid_fraction=0.5).read_bytes() == original
    assert http.calls == calls

    rejected = _rows(process_indices(pivots, manifest, tmp_path, min_valid_fraction=0.51))[0]
    assert rejected["status"] == "insufficient_valid_pixels"
    assert rejected["ndvi_median"] == rejected["ndmi_median"] == ""

    crop = tmp_path / scene["assets"]["red"]["path"]
    crop.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="integridade"):
        process_indices(pivots, manifest, tmp_path, min_valid_fraction=0.5)
    acquire_crops(http, pivots, plan, tmp_path)
    assert any(call[0] == "GET" for call in http.calls[len(calls):])


def test_reject_wrong_nir_and_missing_calibration(stac_case):
    http, _ = stac_case
    http.item["assets"]["nir"]["eo:bands"][0]["name"] = "B8A"
    with pytest.raises(ValueError, match="espectral"):
        _asset_band(http.item, "nir")
    del http.item["assets"]["red"]["raster:bands"][0]["offset"]
    with pytest.raises(ValueError, match="offset"):
        _asset_band(http.item, "red")


def test_crop_rejects_unexpected_crs_and_keeps_asset_failures(stac_case, tmp_path):
    http, pivots = stac_case
    http.item["properties"]["proj:epsg"] = 32723
    head = http.head

    def unavailable_head(url):
        if url.endswith("scl.tif"):
            raise AcquisitionError("Serviço indisponível", status_code=503)
        return head(url)

    http.head = unavailable_head
    plan = search_scenes(http, pivots, tmp_path, start=date(2025, 7, 1), end=date(2025, 7, 31),
                         max_cloud=30, max_scenes=1)
    manifest = acquire_crops(http, pivots, plan, tmp_path)
    scene = json.loads(manifest.read_text(encoding="utf-8"))["scenes"][0]
    assert scene["status"] == "missing_assets"
    assert "CRS" in scene["assets"]["red"]["error"]
    assert "indisponível" in scene["assets"]["scl"]["error"]
    assert _rows(process_indices(pivots, manifest, tmp_path, min_valid_fraction=0.5))[0]["status"] == "missing_assets"

    def exhausted_budget(*args, **kwargs):
        raise BudgetError("Orçamento de transferência esgotado")

    http.range_bytes = exhausted_budget
    with pytest.raises(BudgetError, match="transferência"):
        acquire_crops(http, pivots, plan, tmp_path)


def test_reflectance_nodata_and_zero_denominator():
    raw = np.ma.array([[0, 1000, 2000, 3000]], mask=[[False, False, False, True]])
    values = _reflectance(raw, {"nodata": 0, "scale": 0.0001, "offset": -0.1})
    assert np.isnan(values[0, 0]) and np.isnan(values[0, 3])
    assert values[0, 1:3] == pytest.approx([0, 0.1])
    index, valid = _index(values, values, np.ones(values.shape, dtype=bool))
    assert valid.tolist() == [[False, False, True, False]]
    assert index[0, 2] == 0
    assert np.isnan(index[0, 1])


def test_stac_pagination_deduplicates_and_detects_loops(stac_case):
    http, _ = stac_case
    request = {"collections": [COLLECTION], "limit": 1}
    next_link = {"rel": "next", "href": f"{STAC_ROOT}/search", "method": "POST", "merge": True,
                 "body": {"next": "two"}}
    pages = [
        {"type": "FeatureCollection", "features": [http.item], "links": [next_link]},
        {"type": "FeatureCollection", "features": [http.item], "links": []},
    ]

    def next_page(url, *, method, payload):
        assert method == "POST"
        assert payload == (request if len(pages) == 2 else request | {"next": "two"})
        return pages.pop(0)

    http.get_json = next_page
    assert _stac_items(http, request) == [http.item]
    http.get_json = lambda *args, **kwargs: {"type": "FeatureCollection", "features": [], "links": [next_link]}
    with pytest.raises(ValueError, match="repetiu"):
        _stac_items(http, request)


def test_cli_offline_uses_only_local_files(stac_case, tmp_path, monkeypatch):
    import requests

    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "mpl"))
    from aquaclima import cli
    from aquaclima.ingestion.chirps import PRODUCT, _metadata, chirps_url

    http, fixture_pivots = stac_case
    data_dir = tmp_path / "data"
    document = json.loads(fixture_pivots.read_bytes())
    document["features"].append({"type": "Feature", "properties": {"pivot_id": "C", "area_ha": 0.16},
                                 "geometry": _wgs84(790460, 8109560, 790500, 8109600)})
    pivots = data_dir / "processed/pivots.geojson"
    write_json(pivots, document)
    plan = search_scenes(http, pivots, data_dir, start=date(2025, 7, 1), end=date(2025, 7, 31),
                         max_cloud=60, max_scenes=2)
    acquire_crops(http, pivots, plan, data_dir)

    rain = data_dir / "raw/chirps/latam/chirps-v3.0.2025.07.tif"
    rain.parent.mkdir(parents=True)
    bounds = [shape(feature["geometry"]).bounds for feature in document["features"]]
    transform = from_origin(min(bound[0] for bound in bounds) - 0.05,
                            max(bound[3] for bound in bounds) + 0.05, 0.05, 0.05)
    with rasterio.open(rain, "w", driver="GTiff", width=4, height=4, count=1, dtype="float32",
                       nodata=-9999, crs="EPSG:4326", transform=transform) as dataset:
        dataset.write(np.full((4, 4), 21.25, dtype="float32"), 1)
    with rasterio.open(rain) as dataset:
        metadata = _metadata(dataset)
    write_json(data_dir / "raw/chirps/manifest.json", {"product": PRODUCT, "months": {"2025-07": {
        "status": "available", "source": chirps_url("2025-07"), "path": rain.relative_to(data_dir).as_posix(),
        "size_bytes": rain.stat().st_size, "sha256": checksum(rain), "metadata": metadata,
    }}})
    config = tmp_path / "pilot.toml"
    config.write_text("""[study]
pivot_count = 3
start = 2025-07-01
end = 2025-07-31
max_scene_cloud_pct = 60
max_scenes = 2
min_valid_fraction = 0.5
[limits]
max_transfer_bytes = 2000000000
max_storage_bytes = 2000000000
max_downloads = 100
""", encoding="utf-8")

    def reject_remote(*args, **kwargs):
        pytest.fail("A reprodução offline tentou acessar a rede.")

    monkeypatch.setattr(cli, "HttpClient", reject_remote)
    monkeypatch.setattr(requests.sessions.Session, "request", reject_remote)
    outputs = []
    for name in ("first", "second"):
        target = tmp_path / name
        assert cli.main(["run", "--offline", "--config", str(config), "--data-dir", str(data_dir),
                         "--output-dir", str(target)]) == 0
        report = json.loads((target / "relatorio_aquisicao.json").read_bytes())
        assert report["mode"] == "offline"
        assert report["requests"] == report["payload_bytes"] == 0
        table = target / "observacoes.csv"
        assert all(float(row["precip_mm"]) == 21.25 for row in _rows(table))
        outputs.append(table.read_bytes())
    assert outputs[0] == outputs[1]
