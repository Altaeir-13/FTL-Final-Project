"""Regional invariants: municipal completeness, spatial honesty, bounded cache."""

import gzip
import io
import json
from pathlib import Path

import pytest
from shapely.geometry import Polygon, box, mapping

from aquaclima.ingestion.ana import Pivot
from aquaclima.regions.audit import (
    RegionalHttpClient, compact_cluster, geometry_record, immutable_json, municipal_ids,
)
from aquaclima.storage.http import AcquisitionError, write_json


class FakeArcGIS:
    def __init__(self, count, identifiers):
        self.count = count
        self.identifiers = identifiers
        self.queries = []

    def get_json(self, url, *, params, path, validate):
        self.queries.append(params)
        document = ({"count": self.count} if "returnCountOnly" in params
                    else {"objectIdFieldName": "FID", "objectIds": self.identifiers})
        validate(document)
        return document


def test_zero_municipal_count_is_evidence_not_missing_data():
    http = FakeArcGIS(0, None)
    assert municipal_ids(http, Path("unused"), "UF='MA' AND MUNIC_CD='2103000'", "Caxias") == []
    assert all(query["where"] == "UF='MA' AND MUNIC_CD='2103000'" for query in http.queries)
    assert not any("resultOffset" in query for query in http.queries)


@pytest.mark.parametrize("count,identifiers", [(3, [1, 2]), (2, [1, 1]), (1, ["1"]), (1, None)])
def test_truncated_duplicate_or_wrong_type_municipal_ids_are_rejected(count, identifiers):
    with pytest.raises(AcquisitionError, match="incompleta"):
        municipal_ids(FakeArcGIS(count, identifiers), Path("unused"), "UF='PI'", "PI")


def feature(geometry):
    return {"type": "Feature", "properties": {"FID": 99, "UF": "PI", "MUNIC_NOME": "A", "MUNIC_CD": "2204501", "Hectares": 100}, "geometry": geometry}


def test_municipal_attribute_does_not_override_actual_geometry():
    record, pivot = geometry_record(feature(mapping(box(-43.1, -6.1, -43.09, -6.09))),
                                    box(-44, -5, -43, -4), (-43.35, -4.86))
    assert pivot is not None and record["valid"]
    assert record["MUNIC_CD"] == "2204501"
    assert record["municipal_centroid_inside"] is False
    assert record["eligible_geometry"] is False


def test_missing_geometry_and_repaired_geometry_cannot_enter_sample():
    missing, pivot = geometry_record(feature(None), box(-44, -7, -42, -4), (-43.35, -4.86))
    assert not missing["valid"] and pivot is None
    bow = Polygon([(-43.1, -6.1), (-43, -6), (-43, -6.1), (-43.1, -6), (-43.1, -6.1)])
    repaired, pivot = geometry_record(feature(mapping(bow)), box(-44, -7, -42, -4), (-43.35, -4.86))
    assert pivot is not None and repaired["issue"]
    assert repaired["eligible_geometry"] is False


def test_cluster_uses_region_location_and_is_deterministic():
    pivots = [Pivot(i, {}, box(x, -6, x+.002, -5.998), 50, None)
              for i, x in [(20, -43.0), (10, -43.005), (30, -43.01), (40, -45.0)]]
    first, radius = compact_cluster(pivots, 3)
    second, radius_again = compact_cluster(list(reversed(pivots)), 3)
    assert [p.fid for p in first] == [10, 20, 30]
    assert [p.fid for p in second] == [10, 20, 30]
    assert 500 < radius < 600 and radius_again == radius


def test_acquisition_sample_is_byte_immutable(tmp_path):
    path = tmp_path / "sample.geojson"
    immutable_json(path, {"pivots": [1, 2, 3]})
    before = path.read_bytes(), path.stat().st_mtime_ns
    immutable_json(path, {"pivots": [1, 2, 3]})
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    with pytest.raises(AcquisitionError, match="congelado"):
        immutable_json(path, {"pivots": [4, 5, 6]})
    assert path.read_bytes() == before[0]


def test_verified_offline_cache_is_used_and_tampering_fails_closed(tmp_path):
    url = "https://servicodados.ibge.gov.br/api/example"
    path = tmp_path / "response.json"
    with RegionalHttpClient(ledger=tmp_path / "acquisition.jsonl", offline=True) as http:
        write_json(path, {"id": 1})
        http.record_file(path, source=http._identity(url, None, None))
        assert http.get_json(url, path=path) == {"id": 1}
        assert http.downloads == 0
        path.write_text('{"id":2}', encoding="utf-8")
        with pytest.raises(AcquisitionError, match="offline"):
            http.get_json(url, path=path)
        assert http.downloads == 0


class RawBytes(io.BytesIO):
    def read1(self, size=-1):
        return self.read(size)


class Response:
    def __init__(self, content):
        self.headers = {"Content-Encoding": "gzip", "Content-Length": str(len(content))}
        self.raw = RawBytes(content)


def test_ibge_gzip_is_bounded_and_wire_bytes_are_counted(tmp_path):
    content = gzip.compress(json.dumps({"name": "Caxias"}).encode())
    with RegionalHttpClient(ledger=tmp_path / "ledger.jsonl") as http:
        response = Response(content)
        assert json.loads(http._body(response)) == {"name": "Caxias"}
        assert http.transferred == len(content)
        assert response.headers["Content-Encoding"] == "gzip"
        oversized = gzip.compress(b"x" * 10000)
        with pytest.raises(AcquisitionError, match="descomprimido"):
            http._body(Response(oversized), max_body=100)
