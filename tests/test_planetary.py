import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aquaclima.ingestion.planetary import (
    CALIBRATION_VERSION, PlanetaryHttp, acquisition_key, normalize_pc_item,
    parse_product_calibration,
    screen_pc, acquire_pc_crops,
)
from aquaclima.storage.http import HttpClient, checksum, write_json
from aquaclima.storage.http import AcquisitionError
from test_sentinel import stac_case

PRODUCT = "S2A_MSIL2A_20220129T132231_N0400_R038_T23KKA_20220214T021101.SAFE"
ROOT = f"https://sentinel2l2a01.blob.core.windows.net/sentinel2-l2/23/K/KA/2022/01/29/{PRODUCT}"


def metadata(baseline="04.00", offsets=True, product=PRODUCT):
    offset_xml = "".join(f'<BOA_ADD_OFFSET band_id="{number}">-1000</BOA_ADD_OFFSET>' for number in range(13)) if offsets else ""
    return f'''<Product><PRODUCT_URI>{product}</PRODUCT_URI><PROCESSING_BASELINE>{baseline}</PROCESSING_BASELINE>
      <PROCESSING_LEVEL>Level-2A</PROCESSING_LEVEL><PRODUCT_TYPE>S2MSI2A</PRODUCT_TYPE>
      <BOA_QUANTIFICATION_VALUE>10000</BOA_QUANTIFICATION_VALUE>{offset_xml}
      <Special_Values><SPECIAL_VALUE_TEXT>NODATA</SPECIAL_VALUE_TEXT><SPECIAL_VALUE_INDEX>0</SPECIAL_VALUE_INDEX></Special_Values>
      <Special_Values><SPECIAL_VALUE_TEXT>SATURATED</SPECIAL_VALUE_TEXT><SPECIAL_VALUE_INDEX>65535</SPECIAL_VALUE_INDEX></Special_Values>
      </Product>'''.encode()


def test_safe_calibration_uses_explicit_offsets_and_band_ids():
    calibration = parse_product_calibration(metadata(), product_uri=PRODUCT, baseline="04.00")
    assert calibration["contract"] == CALIBRATION_VERSION
    assert {name: band["band_id"] for name, band in calibration["bands"].items()} == {"red": "3", "nir": "7", "swir16": "11"}
    assert calibration["bands"]["red"]["scale"] == .0001
    assert calibration["bands"]["nir"]["offset"] == -.1


def test_pre_pb04_zero_offset_is_explicit_protocol():
    product = PRODUCT.replace("N0400", "N0300")
    calibration = parse_product_calibration(metadata("03.00", False, product), product_uri=product, baseline="03.00")
    assert calibration["offset_policy"] == "pre_pb04_zero_offset"
    assert calibration["bands"]["red"]["offset"] == 0


@pytest.mark.parametrize("data,baseline", [
    (metadata(offsets=False), "04.00"),
    (metadata().replace(b'band_id="12"', b'band_id="11"'), "04.00"),
    (metadata().replace(b">10000<", b">0<"), "04.00"),
    (metadata().replace(b">-1000<", b">nan<"), "04.00"),
    (metadata(), "05.10"),
    (metadata().replace(b">NODATA<", b">OTHER<"), "04.00"),
    (b'<!DOCTYPE x [<!ENTITY a "x">]>'+metadata(), "04.00"),
])
def test_ambiguous_or_inconsistent_safe_rejected(data, baseline):
    with pytest.raises(ValueError):
        parse_product_calibration(data, product_uri=PRODUCT, baseline=baseline)


def native_item():
    return {"id": "S2A_native", "collection": "sentinel-2-l2a", "properties": {
        "s2:product_uri": PRODUCT, "s2:processing_baseline": "04.00"}, "assets": {
            "product-metadata": {"href": ROOT+"/MTD_MSIL2A.xml"},
            **{name: {"href": ROOT+f"/{name}.tif", "gsd": resolution,
                       "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                       "eo:bands": [{"name": name}]} for name, resolution in (("B04",10),("B08",10),("B11",20),("SCL",20))}}}


class MetadataHttp:
    _location = staticmethod(PlanetaryHttp._location)
    def get_bytes(self, url, *, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(metadata())
        return path.read_bytes()


def test_normalization_keeps_native_provenance_and_separates_cache(tmp_path):
    item = native_item()
    normalized = normalize_pc_item(MetadataHttp(), item, tmp_path)
    assert normalized["id"] == "pc_S2A_native"
    assert normalized["aquaclima:native_item_id"] == item["id"]
    assert normalized["aquaclima:acquisition_key"] == "S2A_20220129T132231_R038_T23KKA"
    assert normalized["assets"]["nir"]["eo:bands"][0]["name"] == "B08"
    assert normalized["assets"]["red"]["raster:bands"][0]["offset"] == -.1
    assert len(normalized["aquaclima:calibration"]["xml_sha256"]) == 64
    assert "raster:bands" not in item["assets"]["B04"]
    assert "sig=" not in json.dumps(normalized)


def test_normalization_rejects_conflicting_stac_calibration(tmp_path):
    item = native_item()
    item["assets"]["B04"]["raster:bands"] = [{"scale": .0001, "offset": 0}]
    with pytest.raises(ValueError, match="diverge"):
        normalize_pc_item(MetadataHttp(), item, tmp_path)


def test_acquisition_key_ignores_product_generation_and_baseline():
    first = native_item()
    second = copy.deepcopy(first)
    second["properties"]["s2:product_uri"] = PRODUCT.replace("N0400", "N0510").replace("20220214T021101", "20240601T120000")
    assert acquisition_key(first) == acquisition_key(second)


@pytest.mark.parametrize("url", [ROOT+"/B04.tif?sig=secret", "http://sentinel2l2a01.blob.core.windows.net/sentinel2-l2/a", "https://example.com/sentinel2-l2/a"])
def test_signer_rejects_unexpected_or_persisted_credentials(url):
    with pytest.raises(ValueError):
        PlanetaryHttp._location(url)


def test_empty_approved_catalog_produces_complete_empty_manifests(tmp_path):
    from shapely.geometry import mapping, box
    pivots=tmp_path/'pivots.geojson'
    write_json(pivots, {'type':'FeatureCollection','features':[{'type':'Feature','properties':{'pivot_id':'1'},'geometry':mapping(box(-47,-18,-46.99,-17.99))}]})
    catalog=tmp_path/'catalog.json'
    write_json(catalog, {'collection':'sentinel-2-l2a','request':{},'parameters':{'pivots_sha256':checksum(pivots)},'candidate_count':0,'candidates':[]})
    with HttpClient(ledger=tmp_path/'http.jsonl') as client:
        selected=screen_pc(PlanetaryHttp(client),pivots,catalog,tmp_path,output_path=tmp_path/'selected.json',max_scenes=2,min_valid_fraction=.7)
        document=json.loads(selected.read_bytes())
        assert document['selected']==[] and document['selected_ids']==[]
        assert document['screening_complete'] and document['state']=='complete'
        manifest=acquire_pc_crops(PlanetaryHttp(client),pivots,selected,tmp_path,manifest_path=tmp_path/'crops.json')
        assert json.loads(manifest.read_bytes())['scenes']==[]
        assert json.loads(manifest.read_bytes())['state']=='complete'
        assert client.downloads==0


def test_pc_asset_resume_keeps_verified_bands_and_provenance(stac_case, tmp_path):
    http, pivots = stac_case
    item = copy.deepcopy(http.item)
    item.update(collection='sentinel-2-l2a', **{
        'aquaclima:calibration':{'contract':CALIBRATION_VERSION},
        'aquaclima:source_item_url':'https://planetarycomputer.microsoft.com/item/native',
        'aquaclima:native_item_id':'native', 'aquaclima:acquisition_key':'physical-acquisition',
    })
    catalog = tmp_path/'pc-catalog.json'
    write_json(catalog, {'collection':'sentinel-2-l2a','request':{},
                        'parameters':{'pivots_sha256':checksum(pivots)},'candidate_count':1,'candidates':[item]})
    selected = screen_pc(http,pivots,catalog,tmp_path,output_path=tmp_path/'selected.json',max_scenes=2,min_valid_fraction=.5)
    original_head = http.head
    def unavailable(url):
        if url.endswith('red.tif'):
            raise AcquisitionError('temporary server failure',status_code=503)
        return original_head(url)
    http.head = unavailable
    crops = acquire_pc_crops(http,pivots,selected,tmp_path,manifest_path=tmp_path/'pc-crops.json')
    first=json.loads(crops.read_bytes())
    assert first['state']=='incomplete'
    assert first['scenes'][0]['assets']['red']['status']=='failed'
    good={name:first['scenes'][0]['assets'][name]['sha256'] for name in ('nir','swir16','scl')}
    http.head = original_head
    calls=len(http.calls)
    acquire_pc_crops(http,pivots,selected,tmp_path,manifest_path=crops)
    recovered=json.loads(crops.read_bytes())
    assert recovered['state']=='complete'
    assert recovered['scenes'][0]['source_item_url']==item['aquaclima:source_item_url']
    assert recovered['scenes'][0]['acquisition_key']=='physical-acquisition'
    assert recovered['attempt_history'][0]['scenes'][0]['assets']['red']['status']=='failed'
    assert all(recovered['scenes'][0]['assets'][name]['sha256']==value for name,value in good.items())
    assert all('/red.tif' in call[1] for call in http.calls[calls:])
    calls=len(http.calls)
    acquire_pc_crops(http,pivots,selected,tmp_path,manifest_path=crops)
    assert len(http.calls)==calls
    assert json.loads(crops.read_bytes())==recovered


def test_public_signer_refreshes_expired_access_once():
    class TokenHttp:
        def __init__(self):
            self.signs = self.reads = 0
        def get_json(self,url):
            self.signs+=1
            return {'msft:expiry':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
                    'token':f'sp=r&sig=temporary-{self.signs}'}
        def head(self,url):
            self.reads+=1
            if self.reads==1:
                raise AcquisitionError('expired read token',status_code=403)
            return {'content-length':'123'}
    base=TokenHttp()
    signer=PlanetaryHttp(base)
    assert signer.head(ROOT+'/B04.tif')=={'content-length':'123'}
    assert base.signs==base.reads==2
