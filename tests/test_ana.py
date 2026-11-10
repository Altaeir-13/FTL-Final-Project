from pathlib import Path

import pytest
from shapely.geometry import Polygon, mapping

from aquaclima.ingestion.ana import PIVOT_CRS, _collection, _envelope_ids, _fetch_batch, _valid_polygon
from aquaclima.storage.http import AcquisitionError


def feature(fid):
    return {"type": "Feature", "id": fid, "properties": {"FID": fid}, "geometry": None}


def collection(features, crs="EPSG:4674", *, truncated=False):
    return {
        "type": "FeatureCollection", "features": features, "exceededTransferLimit": truncated,
        "crs": {"type": "name", "properties": {"name": crs}},
    }


class FakeArcGIS:
    def __init__(self, respond):
        self.respond = respond
        self.queries = []

    def get_json(self, url, *, params, path, validate):
        self.queries.append(params)
        reply = self.respond(params)
        validate(reply)
        return reply


def test_invalid_bow_tie_preserves_polygon_parts():
    bow_tie = Polygon([(-47, -17), (-46, -16), (-46, -17), (-47, -16), (-47, -17)])
    geometry, reason = _valid_polygon({"geometry": mapping(bow_tie)})
    assert reason.startswith("Self-intersection")
    assert geometry.is_valid and geometry.geom_type == "MultiPolygon"
    assert geometry.area == pytest.approx(0.5)


def test_degenerate_polygon_cannot_be_repaired():
    collapsed = Polygon([(-47, -17), (-46, -17), (-45, -17), (-47, -17)])
    with pytest.raises(ValueError, match="sem área"):
        _valid_polygon({"geometry": mapping(collapsed)})


@pytest.mark.parametrize("crs", ["EPSG:3857", "identificador inválido", None])
def test_unexpected_or_missing_geojson_crs_is_rejected(crs):
    document = collection([], crs)
    if crs is None:
        del document["crs"]
    with pytest.raises(AcquisitionError, match="CRS"):
        _collection(document, PIVOT_CRS)


def test_envelope_can_exceed_feature_limit_without_losing_ids():
    ids = list(range(2_001))
    http = FakeArcGIS(lambda p: {"count": len(ids)} if "returnCountOnly" in p
                       else {"objectIds": ids + [ids[-1]], "objectIdFieldName": "FID"})
    assert _envelope_ids(http, Path("unused"), (-48, -18, -47, -17), "FID") == (ids, 1)
    assert all(query["geometryType"] == "esriGeometryEnvelope" for query in http.queries)


def test_envelope_count_detects_truncated_ids():
    http = FakeArcGIS(lambda p: {"count": 3} if "returnCountOnly" in p
                       else {"objectIds": [1, 2], "objectIdFieldName": "FID"})
    with pytest.raises(AcquisitionError, match="Consulta espacial incompleta"):
        _envelope_ids(http, Path("unused"), (-48, -18, -47, -17), "FID")


def test_truncated_batch_splits_and_deduplicates():
    def respond(params):
        ids = list(map(int, params["objectIds"].split(",")))
        if len(ids) > 1:
            return collection([feature(ids[0])], truncated=True)
        return collection([feature(ids[0]), feature(ids[0])])

    http = FakeArcGIS(respond)
    records, duplicates = _fetch_batch(http, Path("unused"), [2, 3], "FID")
    assert list(records) == [2, 3]
    assert duplicates == 2
    assert [query["objectIds"] for query in http.queries] == ["2,3", "2", "3"]


def test_batch_with_conflicting_duplicate_fails():
    modified = feature(2)
    modified["properties"]["Hectares"] = 30
    http = FakeArcGIS(lambda _: collection([feature(2), modified]))
    with pytest.raises(AcquisitionError, match="divergentes"):
        _fetch_batch(http, Path("unused"), [2], "FID")


def test_single_missing_id_fails_after_split():
    http = FakeArcGIS(lambda _: collection([]))
    with pytest.raises(AcquisitionError, match="incompleto para o identificador 2"):
        _fetch_batch(http, Path("unused"), [2, 3], "FID")
