"""Boundary and 2022 center pivots from the public ANA/SNIRH ArcGIS services."""

import hashlib
import json
import logging
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
from pyproj import CRS, Geod, Transformer
from pyproj.exceptions import CRSError
from shapely import make_valid, orient_polygons, union_all
from shapely.errors import GEOSException
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform
from shapely.prepared import prep
from shapely.validation import explain_validity

from aquaclima.storage.http import AcquisitionError, HttpClient, write_json

LOGGER = logging.getLogger(__name__)
ANA_REST = "https://portal1.snirh.gov.br/server/rest/services/SFI"
PIVOT_LAYER = f"{ANA_REST}/PIVOS_2022_SNIRH/MapServer/0"
BASIN_LAYER = f"{ANA_REST}/Unidades_Automonitoramento_UGRH_MRS/MapServer/0"
BASIN_WHERE = "sgautomoni='SMA'"
PIVOT_CRS = 4674
GEOJSON_CRS = 4326
DISTANCE_CRS = 31983  # SIRGAS 2000 / UTM 23S covers the official basin.


@dataclass(frozen=True)
class Pivot:
    fid: int
    properties: dict
    geometry: BaseGeometry
    area_ha: float
    input_validity: str | None


def _arcgis(http: HttpClient, url: str, params: dict, path: Path) -> dict:
    def validate(document):
        if not isinstance(document, dict) or "error" in document:
            raise AcquisitionError(f"Resposta ArcGIS inválida em {url}: {document}")

    return http.get_json(url, params=params, path=path, validate=validate)


def _source_crs(metadata: dict, expected: int) -> None:
    reference = metadata.get("sourceSpatialReference") or metadata.get("spatialReference") or {}
    source = reference.get("latestWkid", reference.get("wkid"))
    if source != expected:
        raise AcquisitionError(f"CRS de origem esperado EPSG:{expected}, recebido {source!r}")
    if metadata.get("geometryType") != "esriGeometryPolygon":
        raise AcquisitionError("A camada ANA não informa geometria poligonal")


def _collection(document: dict, expected: int) -> list[dict]:
    if document.get("type") != "FeatureCollection" or not isinstance(document.get("features"), list):
        raise AcquisitionError("A consulta ANA não retornou uma FeatureCollection GeoJSON")
    if "crs" in document:
        name = (document["crs"] or {}).get("properties", {}).get("name")
        try:
            actual = CRS.from_user_input(name)
        except (CRSError, TypeError, ValueError) as exc:
            raise AcquisitionError(f"CRS da resposta GeoJSON ANA inválido: {name!r}") from exc
        if not actual.equals(CRS.from_epsg(expected), ignore_axis_order=True):
            raise AcquisitionError(f"CRS da resposta ANA esperado EPSG:{expected}, recebido {name!r}")
    elif expected != GEOJSON_CRS:
        raise AcquisitionError(f"A resposta ANA omitiu o CRS EPSG:{expected} solicitado")
    return document["features"]


def _polygon_parts(geometry: BaseGeometry) -> list[BaseGeometry]:
    if geometry.geom_type == "Polygon":
        return [geometry]
    if geometry.geom_type in {"MultiPolygon", "GeometryCollection"}:
        return [part for element in geometry.geoms for part in _polygon_parts(element)]
    return []


def _valid_polygon(feature: dict) -> tuple[BaseGeometry, str | None]:
    if not feature.get("geometry"):
        raise ValueError("Geometria ANA ausente")
    geometry = shape(feature["geometry"])
    if geometry.geom_type not in {"Polygon", "MultiPolygon"} or geometry.is_empty:
        raise ValueError("Geometria ANA sem polígono")
    west, south, east, north = geometry.bounds
    if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        raise ValueError("Geometria ANA fora do domínio do CRS geográfico")
    issue = None
    if not geometry.is_valid:
        issue = explain_validity(geometry)
        geometry = union_all(_polygon_parts(make_valid(geometry)))
    if geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
        raise ValueError(f"Geometria ANA sem área poligonal válida: {issue}")
    return orient_polygons(geometry), issue


def _basin(http: HttpClient, directory: Path) -> tuple[dict, BaseGeometry, str | None]:
    metadata = _arcgis(http, BASIN_LAYER, {"f": "json"}, directory / "basin-layer.json")
    _source_crs(metadata, PIVOT_CRS)
    document = _arcgis(
        http, f"{BASIN_LAYER}/query",
        {"where": BASIN_WHERE, "outFields": "*", "outSR": GEOJSON_CRS, "f": "geojson"},
        directory / "sao-marcos.geojson",
    )
    features = _collection(document, GEOJSON_CRS)
    if document.get("exceededTransferLimit") or len(features) != 1:
        raise AcquisitionError("A unidade ANA de São Marcos (SMA) não retornou um polígono único")
    feature = features[0]
    if (feature.get("properties") or {}).get("sgautomoni") != "SMA":
        raise AcquisitionError("A unidade de automonitoramento retornada não corresponde a São Marcos")
    try:
        geometry, issue = _valid_polygon(feature)
    except (ValueError, TypeError, GEOSException) as exc:
        raise AcquisitionError(f"O limite oficial de São Marcos não pôde ser validado: {exc}") from exc
    return feature["properties"], geometry, issue


def _envelope_ids(
    http: HttpClient, directory: Path, bounds: tuple[float, float, float, float], oid_field: str,
) -> tuple[list[int], int]:
    params = {
        "where": "1=1", "geometry": ",".join(map(str, bounds)),
        "geometryType": "esriGeometryEnvelope", "inSR": GEOJSON_CRS,
        "spatialRel": "esriSpatialRelIntersects", "f": "json",
    }
    url = f"{PIVOT_LAYER}/query"
    count_reply = _arcgis(http, url, {**params, "returnCountOnly": "true"}, directory / "pivot-count.json")
    ids_reply = _arcgis(http, url, {**params, "returnIdsOnly": "true"}, directory / "pivot-ids.json")
    count = count_reply.get("count")
    identifiers = ids_reply.get("objectIds")
    if (ids_reply.get("objectIdFieldName") != oid_field or not isinstance(identifiers, list)
            or any(type(value) is not int for value in identifiers)):
        raise AcquisitionError("A consulta espacial ANA não devolveu identificadores inteiros do campo OID")
    unique = sorted(set(identifiers))
    if ids_reply.get("exceededTransferLimit") or type(count) is not int or len(unique) != count:
        raise AcquisitionError(f"Consulta espacial incompleta: contagem {count}, IDs únicos {len(unique)}")
    return unique, len(identifiers) - len(unique)


def _fetch_batch(http: HttpClient, directory: Path, ids: list[int], oid_field: str) -> tuple[dict, int]:
    selection = ",".join(map(str, ids))
    key = hashlib.sha256(selection.encode("ascii")).hexdigest()[:16]
    document = _arcgis(
        http, f"{PIVOT_LAYER}/query",
        {"objectIds": selection, "outFields": "*", "outSR": PIVOT_CRS, "f": "geojson"},
        directory / f"batch-{key}.geojson",
    )
    features = _collection(document, PIVOT_CRS)
    indexed = {}
    for feature in features:
        fid = (feature.get("properties") or {}).get(oid_field)
        if type(fid) is not int or feature.get("id", fid) != fid:
            raise AcquisitionError(f"Feição GeoJSON sem identificador {oid_field} consistente")
        if fid in indexed and feature != indexed[fid]:
            raise AcquisitionError(f"ANA devolveu geometrias ou atributos divergentes para o identificador {fid}")
        indexed[fid] = feature
    if set(indexed) - set(ids):
        raise AcquisitionError("Lote ANA contém identificadores fora da consulta")
    duplicate_count = len(features) - len(indexed)
    if document.get("exceededTransferLimit") or set(indexed) != set(ids):
        if len(ids) == 1:
            raise AcquisitionError(f"Lote ANA incompleto para o identificador {ids[0]}")
        midpoint = len(ids) // 2
        left, left_duplicates = _fetch_batch(http, directory, ids[:midpoint], oid_field)
        right, right_duplicates = _fetch_batch(http, directory, ids[midpoint:], oid_field)
        return left | right, duplicate_count + left_duplicates + right_duplicates
    return indexed, duplicate_count


def _compact_cluster(pivots: list[Pivot], count: int) -> tuple[list[Pivot], float]:
    """Minimize the distance to the kth nearest pivot among eligible center points."""
    if len(pivots) < count:
        raise AcquisitionError(f"Só {len(pivots)} pivôs elegíveis para uma amostra de {count}")
    to_meters = Transformer.from_crs(PIVOT_CRS, DISTANCE_CRS, always_xy=True)
    centers = [pivot.geometry.centroid for pivot in pivots]
    x, y = to_meters.transform([point.x for point in centers], [point.y for point in centers])
    coordinates = np.column_stack((x, y))
    winner = None
    for center_index, center in enumerate(coordinates):
        delta = coordinates - center
        squared = np.einsum("ij,ij->i", delta, delta)
        # Stable ordering by FID also gives reproducible ties at equal distances.
        order = np.argsort(squared, kind="stable")[:count]
        score = (float(squared[order[-1]]), float(squared[order].sum()), pivots[center_index].fid)
        if winner is None or score < winner[0]:
            winner = score, order
    score, order = winner
    return sorted((pivots[index] for index in order), key=lambda pivot: pivot.fid), math.sqrt(score[0])


def _output(http: HttpClient, path: Path, collection: dict, pivots: list[Pivot], source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gpkg = path.with_suffix(".gpkg")
    if not http.is_verified(gpkg, source=source):
        records = [feature["properties"] for feature in collection["features"]]
        frame = gpd.GeoDataFrame(records, geometry=[pivot.geometry for pivot in pivots], crs=PIVOT_CRS)
        with tempfile.TemporaryDirectory(dir=path.parent) as directory:
            candidate = Path(directory) / gpkg.name
            # Keep ANA's original FID as an ordinary property, separate from the GeoPackage key.
            frame.to_file(candidate, layer="pivots", driver="GPKG", engine="pyogrio", index=False,
                          layer_options={"FID": "gpkg_pk"})
            http.ensure_storage(candidate.stat().st_size)
            candidate.replace(gpkg)
        http.record_file(gpkg, source=source)
    if not http.is_verified(path, source=source):
        with tempfile.TemporaryDirectory(dir=path.parent) as directory:
            candidate = Path(directory) / path.name
            write_json(candidate, collection)
            http.ensure_storage(candidate.stat().st_size)
            candidate.replace(path)
        http.record_file(path, source=source)


def acquire_pivots(http: HttpClient, data_dir: Path, *, count: int = 4, min_area_ha: float = 25.0) -> Path:
    """Select a compact sample fully covered by the official São Marcos basin polygon."""
    if count < 1 or not math.isfinite(min_area_ha) or min_area_ha < 0:
        raise ValueError("A amostra deve ter tamanho positivo e área mínima finita não negativa")
    raw = data_dir / "raw" / "ana"
    path = data_dir / "processed" / "pivots.geojson"
    metadata = _arcgis(http, PIVOT_LAYER, {"f": "json"}, raw / "pivot-layer.json")
    _source_crs(metadata, PIVOT_CRS)
    supported_formats = metadata.get("supportedQueryFormats", "").lower()
    if "geojson" not in supported_formats:
        raise AcquisitionError("A camada ANA não anuncia suporte a consultas GeoJSON")
    oid_fields = [field["name"] for field in metadata.get("fields", []) if field.get("type") == "esriFieldTypeOID"]
    server_limit = metadata.get("maxRecordCount")
    if len(oid_fields) != 1 or type(server_limit) is not int or server_limit < 1:
        raise AcquisitionError("Metadados ANA não identificam o campo OID ou o limite de feições")
    oid_field = oid_fields[0]
    basin_properties, basin, basin_issue = _basin(http, raw)
    identifiers, duplicate_ids = _envelope_ids(http, raw, basin.bounds, oid_field)
    if len(identifiers) < count:
        raise AcquisitionError(f"A consulta espacial encontrou {len(identifiers)} pivôs para a amostra de {count}")
    batch_size = min(250, server_limit)
    basin_to_native = Transformer.from_crs(GEOJSON_CRS, PIVOT_CRS, always_xy=True)
    prepared_basin = prep(transform(basin_to_native.transform, basin))
    ellipsoid = Geod(ellps="GRS80")
    eligible = []
    invalid = {}
    repaired = {}
    duplicate_features = 0
    contained = 0
    for start in range(0, len(identifiers), batch_size):
        batch, duplicates = _fetch_batch(http, raw, identifiers[start:start + batch_size], oid_field)
        duplicate_features += duplicates
        for fid, feature in sorted(batch.items()):
            try:
                geometry, issue = _valid_polygon(feature)
            except (ValueError, TypeError, GEOSException) as exc:
                invalid[str(fid)] = str(exc)
                continue
            if issue:
                repaired[str(fid)] = issue
            if not prepared_basin.covers(geometry):
                continue
            contained += 1
            area = abs(ellipsoid.geometry_area_perimeter(geometry)[0]) / 10_000
            if math.isfinite(area) and area >= min_area_ha:
                eligible.append(Pivot(fid, feature["properties"], geometry, area, issue))
    sample, radius_m = _compact_cluster(eligible, count)
    to_wgs84 = Transformer.from_crs(PIVOT_CRS, GEOJSON_CRS, always_xy=True)
    features = [
        {
            "type": "Feature", "id": pivot.fid,
            "properties": {**pivot.properties, "pivot_id": str(pivot.fid), "area_ha": pivot.area_ha,
                           "geometry_repaired": pivot.input_validity is not None},
            "geometry": mapping(transform(to_wgs84.transform, pivot.geometry)),
        }
        for pivot in sample
    ]
    provenance = {
        "source": PIVOT_LAYER, "source_crs": f"EPSG:{PIVOT_CRS}", "geojson_crs": f"EPSG:{GEOJSON_CRS}",
        "gpkg_crs": f"EPSG:{PIVOT_CRS}", "area_ellipsoid": "GRS80", "distance_crs": f"EPSG:{DISTANCE_CRS}",
        "basin_source": BASIN_LAYER, "basin_source_crs": f"EPSG:{PIVOT_CRS}",
        "basin_properties": basin_properties, "basin_bbox": list(basin.bounds),
        "basin_input_validity_issue": basin_issue, "envelope_count": len(identifiers),
        "contained_count": contained, "eligible_count": len(eligible), "selected_count": count,
        "min_area_ha": min_area_ha, "cluster_radius_m": radius_m, "query_batch_size": batch_size,
        "duplicate_ids": duplicate_ids, "duplicate_features": duplicate_features,
        "invalid_geometries_rejected": invalid, "repaired_geometries": repaired,
    }
    document = {"type": "FeatureCollection", "features": features, "aquaclima": provenance}
    identity = hashlib.sha256(json.dumps(document, sort_keys=True).encode("utf-8")).hexdigest()
    source = f"{PIVOT_LAYER} [amostra BHO SMA sha256={identity}]"
    _output(http, path, document, sample, source)
    LOGGER.info("Pivôs ANA: %d no envelope, %d contidos, %d elegíveis, %d selecionados",
                len(identifiers), contained, len(eligible), count)
    return path
