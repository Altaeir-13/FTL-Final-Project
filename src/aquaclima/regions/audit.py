"""Evidence-based ANA/IBGE inventory and bounded STAC regional screening."""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from pyproj import Geod, Transformer
from shapely import union_all
from shapely.geometry import mapping, shape
from shapely.errors import GEOSException
from shapely.ops import transform

from aquaclima.ingestion.ana import (
    GEOJSON_CRS, PIVOT_CRS, PIVOT_LAYER, Pivot, _arcgis, _fetch_batch,
    _source_crs, _valid_polygon,
)
from aquaclima.ingestion.sentinel import COLLECTION, STAC_ROOT, _stac_items
from aquaclima.storage.http import AcquisitionError, HttpClient, checksum, write_json

CANDIDATES = [
    ("MA", "Caxias", "2103000"), ("MA", "Timon", "2112209"),
    ("PI", "Guadalupe", "2204501"), ("PI", "Jerumenha", "2205300"),
    ("PI", "Landri Sales", "2205607"), ("MA", "Balsas", "2101400"),
    ("MA", "Riachão", "2109502"), ("MA", "Loreto", "2106102"),
]
SEDE_LAYER = "https://portal1.snirh.gov.br/arcgis/rest/services/DADOSABERTOS/Sede_Municipais/MapServer/0"
METHOD = {
    "registered_at_utc": None,
    "weights": {"geometry": .25, "availability": .25, "continuity": .20,
                "proximity": .15, "cost": .15},
    "minimum_area_ha": 25, "minimum_pivots": 3, "sample_target": 5,
    "period": "2023-01-01/2024-12-31", "preliminary_scene_cloud_max": 40,
    "geometry": "min(number of valid >=25 ha pivots with centroid inside official municipal mesh / 5, 1)",
    "availability": "min(distinct dates whose scene fully covers every selected pivot and eo:cloud_cover <=40 / 48, 1)",
    "continuity": "number of 2023-2024 months with a fully covering scene at scene cloud <=40 / 24",
    "proximity": "max(0, 1 - cluster-centroid geodesic distance from Caxias sede / 600 km)",
    "cost": "0.5 / number of distinct MGRS tiles among usable scenes + 0.5*max(0, 1 - cluster radius /20 km)",
    "targets_rationale": "5 pivots matches established pilot sample; 25 ha matches existing native-20m pixel budget; 48 dates is two candidate dates per month for cloud fallback, 24 months measures continuity. 600 km is the regional distance scale, 20 km is a compact pilot radius relative to a 100km Sentinel tile. Scores compare engineering feasibility, not statistical validity.",
    "eligibility": "At least 3 valid >=25ha pivots with verified municipal centroid; at least 6 months of fully covering cloud<=40 scenes; exact SCL acceptance and calibration require subsequent pixel-level pilot.",
    "selection_rule": "highest weighted score among eligible candidates; ties by distance then municipal code",
    "warning": "Scene cloud is only a planning proxy. No per-pivot quality, seasonality, index or regional model validation is inferred.",
}


class RegionalHttpClient(HttpClient):
    """Bounded gzip JSON for IBGE APIs that ignore Accept-Encoding: identity.

    Existing scientific raster transfer logic stays unchanged. Both compressed
    transport and decompressed body are capped, and inventory hashes describe
    the decoded JSON actually used for geometry checks.
    """

    def __init__(self, *, offline=False, **kwargs):
        super().__init__(**kwargs)
        self.offline = offline

    def _request(self, *args, **kwargs):
        if self.offline:
            raise AcquisitionError("Modo offline: resposta ausente ou sem integridade no inventário")
        return super()._request(*args, **kwargs)

    def _body(self, response, *, expected=None, max_body=32*1024*1024):
        encoding=response.headers.get("Content-Encoding", "identity").lower()
        if encoding != "gzip":
            return super()._body(response, expected=expected, max_body=max_body)
        original=response.headers.pop("Content-Encoding")
        try:
            compressed=super()._body(response, expected=expected, max_body=max_body)
        finally:
            response.headers["Content-Encoding"]=original
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
                decoded=stream.read(max_body+1)
        except (OSError,EOFError) as exc:
            raise AcquisitionError("JSON gzip inválido") from exc
        if len(decoded)>max_body:
            raise AcquisitionError("JSON gzip descomprimido ultrapassa limite")
        return decoded


def municipal_ids(http: HttpClient, directory: Path, where: str, label: str) -> list[int]:
    """Cross-check counts and IDs instead of unsupported resultOffset pagination."""
    base = {"where": where, "f": "json"}
    count = _arcgis(http, f"{PIVOT_LAYER}/query", base | {"returnCountOnly": "true"}, directory / f"{label}-count.json")
    reply = _arcgis(http, f"{PIVOT_LAYER}/query", base | {"returnIdsOnly": "true"}, directory / f"{label}-ids.json")
    ids = reply.get("objectIds")
    if ids is None and count.get("count") == 0:
        ids = []
    if (reply.get("objectIdFieldName") != "FID" or not isinstance(ids, list)
            or any(type(i) is not int for i in ids) or len(ids) != len(set(ids))
            or count.get("count") != len(ids) or reply.get("exceededTransferLimit")):
        raise AcquisitionError(f"Consulta municipal incompleta ou IDs inválidos: {label}")
    return sorted(ids)


def compact_cluster(pivots: list[Pivot], count: int = 5) -> tuple[list[Pivot], float]:
    """Geodesic nearest-neighbor cluster; regional UTM is never borrowed from MG."""
    if not pivots:
        return [], 0.0
    count = min(count, len(pivots))
    geod = Geod(ellps="GRS80")
    centers = {p.fid: p.geometry.centroid for p in pivots}
    best = None
    for anchor in pivots:
        center = centers[anchor.fid]
        ordered = sorted((abs(geod.inv(center.x, center.y, centers[p.fid].x, centers[p.fid].y)[2]), p.fid, p) for p in pivots)
        chosen = ordered[:count]
        score = (chosen[-1][0], sum(d*d for d, _, _ in chosen), anchor.fid)
        if best is None or score < best[0]:
            best = (score, sorted([p for _, _, p in chosen], key=lambda p: p.fid))
    return best[1], best[0][0]


def geometry_record(feature: dict, boundary, sede: tuple[float, float]) -> tuple[dict, Pivot | None]:
    properties = feature["properties"]
    fid = properties["FID"]
    base = {"FID": fid, "UF": properties["UF"], "MUNIC_NOME": properties["MUNIC_NOME"],
            "MUNIC_CD": properties["MUNIC_CD"], "ana_hectares": properties.get("Hectares")}
    try:
        geometry, issue = _valid_polygon(feature)
    except (ValueError, TypeError, GEOSException) as exc:
        return base | {"valid": False, "issue": str(exc)}, None
    geod = Geod(ellps="GRS80")
    area = abs(geod.geometry_area_perimeter(geometry)[0]) / 10000
    centroid = geometry.centroid
    inside = bool(boundary.covers(centroid)) if boundary is not None else None
    full = bool(boundary.covers(geometry)) if boundary is not None else None
    record = base | {"valid": True, "issue": issue, "area_ha": area,
                     "longitude": centroid.x, "latitude": centroid.y,
                     "caxias_km": abs(geod.inv(*sede, centroid.x, centroid.y)[2])/1000,
                     "municipal_centroid_inside": inside, "municipal_full_coverage": full,
                     "eligible_geometry": inside is True and area >= 25 and issue is None}
    pivot = Pivot(fid, properties, geometry, area, issue)
    return record, pivot


def score_candidate(count, usable_dates, months, distance_km, radius_m, tile_count):
    scores = {"geometry": min(count/5, 1), "availability": min(usable_dates/48, 1),
              "continuity": months/24, "proximity": max(0, 1-distance_km/600),
              "cost": (.5/tile_count if tile_count else 0) + .5*max(0, 1-radius_m/20000)}
    return scores | {"weighted_total": sum(METHOD["weights"][k]*v for k,v in scores.items())}


def immutable_json(path: Path, document) -> None:
    """Never mutate a sample already bound to an acquisition policy."""
    if path.exists():
        normalized = json.loads(json.dumps(document, ensure_ascii=False, allow_nan=False))
        if json.loads(path.read_text(encoding="utf-8")) != normalized:
            raise AcquisitionError(f"Artefato regional congelado diverge: {path}")
        return
    write_json(path, document)


def audit(directory: Path, *, inventory_only: bool = False, offline: bool = False) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    method_path = directory / "method.json"
    if not method_path.exists():
        write_json(method_path, METHOD | {"registered_at_utc": datetime.now(UTC).isoformat()})
    with RegionalHttpClient(ledger=directory / "acquisition.jsonl", offline=offline, max_transfer_bytes=160_000_000,
                    max_storage_bytes=160_000_000, max_downloads=250) as http:
        raw = directory / "raw"
        metadata = _arcgis(http, PIVOT_LAYER, {"f":"json"}, raw / "pivot-layer.json")
        _source_crs(metadata, PIVOT_CRS)
        fields = {f["name"]: f["type"] for f in metadata["fields"]}
        if not {"FID", "UF", "MUNIC_CD", "MUNIC_NOME", "Hectares"} <= fields.keys() or fields["MUNIC_CD"] != "esriFieldTypeString":
            raise AcquisitionError("Campos municipais ANA incompatíveis")
        # Official public seat point; only territorial coordinates are queried.
        seat_meta = _arcgis(http, SEDE_LAYER, {"f":"json"}, raw / "seat-layer.json")
        seat_fields = [f["name"] for f in seat_meta["fields"]]
        write_json(directory / "seat-fields.json", seat_fields)
        # National field definitions are checked on the live metadata.
        code_field = next((f for f in seat_fields if f.lower() in {"cd_mun", "cd_geocmu", "cd_geocodm", "codigoibge", "geocodigo", "cod_mun", "geocodigo_municipio"}), None)
        name_field = next((f for f in seat_fields if f.lower() in {"nm_mun", "nm_municip", "nome", "nm_sede", "sede_municipal"}), None)
        if code_field is None and name_field is None:
            raise AcquisitionError("Campos da sede municipal não reconhecidos")
        where = f"{code_field}='2103000'" if code_field else f"{name_field}='Caxias'"
        seat_doc = _arcgis(http, f"{SEDE_LAYER}/query", {"f":"geojson", "where":where,"outFields":"*","outSR":4326},raw / "caxias-seat.geojson")
        seats = [f for f in seat_doc["features"] if -44 < shape(f["geometry"]).x < -42]
        if len(seats) != 1:
            raise AcquisitionError(f"Sede de Caxias não identificada univocamente: {seat_fields}, {where}")
        sede = tuple(shape(seats[0]["geometry"]).coords[0])[:2]
        state_features = {}
        for uf in ("MA", "PI"):
            ids = municipal_ids(http, raw, f"UF='{uf}'", uf)
            for start in range(0,len(ids),min(250,metadata["maxRecordCount"])):
                batch, duplicate_count = _fetch_batch(http, raw, ids[start:start+250], "FID")
                if duplicate_count:
                    raise AcquisitionError("Feições estaduais duplicadas")
                for fid, feature in batch.items():
                    if feature["properties"]["UF"] != uf or fid in state_features:
                        raise AcquisitionError("UF divergente ou colisão de FIDs")
                    state_features[fid] = feature
        counts = Counter((f["properties"]["UF"],f["properties"]["MUNIC_NOME"],f["properties"]["MUNIC_CD"]) for f in state_features.values())
        write_json(directory / "state-municipality-counts.json", [{"UF":uf,"name":name,"code":code,"count":n} for (uf,name,code),n in sorted(counts.items())])
        print("STATE_COUNTS",json.dumps([{"uf":u,"name":n,"code":c,"count":v} for (u,n,c),v in sorted(counts.items())],ensure_ascii=False),flush=True)
        # Candidate list can be expanded after statewide inventory without prejudging STAC evidence.
        def normalized(value):
            return "".join(c for c in unicodedata.normalize("NFD",value.casefold()) if unicodedata.category(c) != "Mn")
        # Resolve names using official IBGE IDs; never trust manually entered check digits.
        localities = {}
        for uf in ("MA", "PI"):
            locations=http.get_json(f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios",path=raw/f"ibge-localities-{uf}.json")
            localities[uf]={normalized(item["nome"]):(item["nome"],str(item["id"])) for item in locations}
        candidates=[]
        for uf,name,_ in CANDIDATES:
            official_name,code=localities[uf][normalized(name)]
            candidates.append((uf,official_name,code))
        for (uf,name,code), n in sorted(counts.items()):
            features = [f for f in state_features.values() if f["properties"]["MUNIC_CD"] == code]
            points = [shape(f["geometry"]).centroid for f in features]
            nearest = min(abs(Geod(ellps="GRS80").inv(*sede,p.x,p.y)[2])/1000 for p in points)
            if ((n >= 3 and nearest < 250) or nearest < 150) and code not in {c for _,_,c in candidates}:
                candidates.append((uf,name,code))
        inventory, features_out, comparisons = [], [], []
        clusters = {}
        for uf, name, code in candidates:
            # Exact code query independently cross-checks the statewide inventory.
            ids = municipal_ids(http, raw, f"UF='{uf}' AND MUNIC_CD='{code}'", code)
            selected = [state_features[i] for i in ids]
            expected = {i for i,f in state_features.items() if f["properties"]["MUNIC_CD"] == code}
            if set(ids) != expected:
                raise AcquisitionError(f"Inventário por município diverge do estadual: {code}")
            url = f"https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{code}"
            doc = http.get_json(url, params={"formato":"application/vnd.geo+json","qualidade":"maxima"},path=raw/f"municipality-{code}.geojson")
            boundary = union_all([shape(f["geometry"]) for f in doc["features"]])
            if boundary.is_empty or not boundary.is_valid:
                raise AcquisitionError(f"Limite IBGE inválido: {code}")
            # Check geographic absence as well as the municipal attribute, including
            # zero-attributed candidates; statewide features are complete MA+PI.
            spatial_ids = sorted(fid for fid, f in state_features.items()
                                 if shape(f["geometry"]).intersection(boundary).area > 0)
            spatial_other = sorted(set(spatial_ids) - set(ids))
            eligible = []
            records = []
            for feature in selected:
                record,pivot = geometry_record(feature,boundary,sede)
                inventory.append(record); records.append(record)
                to_wgs84 = Transformer.from_crs(PIVOT_CRS, GEOJSON_CRS, always_xy=True)
                features_out.append({"type":"Feature","id":f"{uf}:{record['FID']}","properties":record,"geometry":mapping(transform(to_wgs84.transform,shape(feature["geometry"])))})
                if pivot is not None and record["eligible_geometry"]:
                    eligible.append(pivot)
            cluster,radius = compact_cluster(eligible)
            clusters[code] = cluster
            center = union_all([p.geometry for p in cluster]).centroid if cluster else None
            distance = abs(Geod(ellps="GRS80").inv(*sede,center.x,center.y)[2])/1000 if center else None
            summary = {"UF":uf,"name":name,"code":code,"ana_count":len(ids),"FIDs":ids,
                       "eligible_count":len(eligible),"area_ha":sum(r.get("area_ha",0) for r in records),
                       "invalid_or_repaired":sum(not r["valid"] or bool(r.get("issue")) for r in records),
                       "centroid_mismatches":sum(r.get("municipal_centroid_inside") is False for r in records),
                       "boundary_crossings":sum(r.get("municipal_full_coverage") is False for r in records),
                       "spatial_intersection_FIDs":spatial_ids,
                       "spatial_other_attribute_FIDs":spatial_other,
                       "sample_FIDs":[p.fid for p in cluster],"cluster_radius_m":radius,"caxias_km":distance}
            comparisons.append(summary)
            if cluster:
                to_wgs84 = Transformer.from_crs(PIVOT_CRS, GEOJSON_CRS, always_xy=True)
                immutable_json(directory/f"sample-{code}.geojson",{"type":"FeatureCollection","features":[{"type":"Feature","id":p.fid,"properties":p.properties | {"pivot_id":f"{uf}:{p.fid}","region_id":f"{name.lower().replace(' ','-')}-{uf.lower()}","area_ha":p.area_ha},"geometry":mapping(transform(to_wgs84.transform,p.geometry))} for p in cluster],"aquaclima":{"source":PIVOT_LAYER,"source_crs":"EPSG:4674","output_crs":"EPSG:4326","coordinate_operation":to_wgs84.description}})
        write_json(directory/"inventory.geojson",{"type":"FeatureCollection","features":features_out,"aquaclima":{"source":PIVOT_LAYER,"year":2022,"source_crs":"EPSG:4674","output_crs":"EPSG:4326","coordinate_operation":Transformer.from_crs(PIVOT_CRS,GEOJSON_CRS,always_xy=True).description,"sede_source":SEDE_LAYER,"caxias_sede":sede}})
        if inventory:
            with (directory/"inventory.csv").open("w",newline="",encoding="utf-8") as stream:
                writer=csv.DictWriter(stream,fieldnames=list(inventory[0]));writer.writeheader();writer.writerows(inventory)
        write_json(directory/"comparison.json",comparisons)
        if inventory_only:
            return {"comparison":comparisons,"transferred":http.transferred}
        for candidate in comparisons:
            cluster = clusters[candidate["code"]]
            if len(cluster) < 3:
                candidate.update({"eligible":False,"reason":"fewer than three valid >=25ha pivots with verified municipal centroid"})
                continue
            request={"collections":[COLLECTION],"intersects":mapping(union_all([p.geometry for p in cluster])),"datetime":"2023-01-01T00:00:00Z/2024-12-31T23:59:59.999999Z","limit":100}
            try:
                items = _stac_items(http,request,cache_dir=raw/f"stac-{candidate['code']}",subdivide=True)
            except (AcquisitionError,ValueError) as exc:
                candidate.update({"eligible":False,"reason":str(exc),"catalog_error":True})
                write_json(directory/"comparison.json",comparisons)
                continue
            usable=[]
            for item in items:
                cloud=item["properties"].get("eo:cloud_cover")
                geom=shape(item["geometry"])
                if isinstance(cloud,(int,float)) and 0<=cloud<=40 and all(geom.covers(p.geometry) for p in cluster):
                    usable.append(item)
            dates={i["properties"]["datetime"][:10] for i in usable}
            months=sorted({d[:7] for d in dates})
            tiles=sorted({i["properties"].get("mgrs:utm_zone","").__str__()+str(i["properties"].get("mgrs:latitude_band",""))+str(i["properties"].get("mgrs:grid_square","")) for i in usable})
            candidate.update({"stac_total_items":len(items),"usable_dates":len(dates),"usable_months":months,"tiles":tiles,
                              "eligible":len(months)>=6,"scores":score_candidate(candidate["eligible_count"],len(dates),len(months),candidate["caxias_km"],candidate["cluster_radius_m"],len(tiles))})
            write_json(directory/f"stac-summary-{candidate['code']}.json",{"request":request,"candidate_count":len(items),"usable_count":len(usable),"items":[{"id":i["id"],"datetime":i["properties"]["datetime"],"cloud_cover":i["properties"]["eo:cloud_cover"],"collection":i["collection"]} for i in usable]})
            print("SCREENED",json.dumps(candidate,ensure_ascii=False),flush=True)
            write_json(directory/"comparison.json",comparisons)
        eligible=[c for c in comparisons if c.get("eligible")]
        winner=min(eligible,key=lambda c:(-c["scores"]["weighted_total"],c["caxias_km"],c["code"])) if eligible else None
        decision_path=directory/"decision.json"
        previous=json.loads(decision_path.read_text(encoding="utf-8")) if decision_path.exists() else {}
        # Keep original decision time when a verified replay selects the same group.
        same_selection=bool(previous) and (previous.get("winner") or {}).get("sample_FIDs")== (winner or {}).get("sample_FIDs")
        decision={"decided_at_utc":previous["decided_at_utc"] if same_selection else datetime.now(UTC).isoformat(),"winner":winner,"method_sha256":checksum(method_path),"inventory_sha256":checksum(directory/"inventory.geojson"),"comparison":comparisons,"transfer_bytes":http.transferred,"stored_bytes":http.stored,"requests":http.downloads,"source":PIVOT_LAYER,"status":"selection-only; pixel-level pilot required"}
        if previous:
            if not same_selection or previous["method_sha256"] != decision["method_sha256"]:
                raise AcquisitionError("A reexecução divergiu da decisão congelada; utilize outro diretório de estudo")
            write_json(directory/"replay.json",decision | {"original_decision_sha256":checksum(decision_path)})
        else:
            write_json(decision_path,decision)
        print("DECISION",json.dumps(winner,ensure_ascii=False),flush=True)
        return decision


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",type=Path,default=Path("data/regions/selection"))
    parser.add_argument("--inventory-only",action="store_true")
    parser.add_argument("--offline",action="store_true")
    args=parser.parse_args()
    audit(args.directory,inventory_only=args.inventory_only,offline=args.offline)


if __name__ == "__main__":
    main()
