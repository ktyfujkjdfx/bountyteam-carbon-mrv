"""Contract-pack tests only: do NOT claim runtime API/contract deployment or real RS accuracy."""
import sys
from pathlib import Path
from copy import deepcopy
import json
import math
import shutil
import pytest
import numpy as np
import rasterio
from rasterio.warp import transform_geom
from PIL import Image
from shapely.geometry import shape
from jsonschema import Draft202012Validator, ValidationError
from openapi_spec_validator import validate as validate_openapi
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from contract_helpers import (read_json,canonical,digest,sha_bytes,check_schema,check_api,
    validate_evidence,validate_geometry,evaluate,decision_record,action_flags,safe_path)

LABELS=['no_change','fire','insufficient']

def fixture(label='fire'): return read_json(ROOT/'fixtures'/('verification_'+label+'.json'))

@pytest.mark.parametrize('name',['verification','rs-request','deployment','api-models'])
def test_schemas_are_valid_2020_12(name):
    Draft202012Validator.check_schema(read_json(ROOT/'contracts'/(name+'.schema.json')))

def test_openapi_validates():
    validate_openapi(yaml.safe_load((ROOT/'contracts/openapi.yaml').read_text()))

@pytest.mark.parametrize('label',LABELS)
def test_golden_evidence_schema_semantics_files_hashes(label):
    evidence=fixture(label);plot=read_json(ROOT/'fixtures/plot.json')
    result=validate_evidence(evidence,ROOT/'fixtures',plot['geometry'])
    expected=read_json(ROOT/'fixtures/expected_results.json')[label]
    for key,value in result.items(): assert value==expected[key]
    assert digest(evidence)==expected['evidence_hash']
    assert canonical(evidence)==(ROOT/'fixtures'/('verification_'+label+'.canonical.json')).read_bytes()
    assert digest(expected['decision_record'])==expected['decision_hash']

@pytest.mark.parametrize('label',LABELS)
def test_rs_request_valid(label):
    request=read_json(ROOT/'fixtures'/('rs_request_'+label+'.json'))
    check_schema(request,'rs-request.schema.json')
    validate_geometry(request['geometry'])
    assert digest(request['geometry'])==request['plot_geometry_hash']

@pytest.mark.parametrize('case',read_json(ROOT/'fixtures/http_examples.json')['cases'],ids=lambda x:x['name'])
def test_http_examples_match_models_and_routes(case):
    oas=yaml.safe_load((ROOT/'contracts/openapi.yaml').read_text())
    operation=oas['paths'][case['path']][case['method'].lower()]
    assert str(case['status']) in operation['responses']
    check_api(case['body'],case['response_schema'])
    response=operation['responses'][str(case['status'])]
    if '$ref' in response: response=oas['components']['responses'][response['$ref'].split('/')[-1]]
    assert response['content']['application/json']['schema']['$ref']=='#/components/schemas/'+case['response_schema']
    if 'request_body' in case:
        check_api(case['request_body'],case['request_schema'])
        assert operation['requestBody']['content']['application/json']['schema']['$ref']=='#/components/schemas/'+case['request_schema']

def test_no_public_freeze_and_all_mutations_protected():
    oas=yaml.safe_load((ROOT/'contracts/openapi.yaml').read_text())
    assert not any('freeze' in p for p in oas['paths'])
    for path,item in oas['paths'].items():
        if 'post' in item:
            op=item['post']; assert op['security']==[{'DemoSession':[]}]
            assert {'$ref':'#/components/parameters/IdempotencyKey'} in op['parameters']
            assert {'$ref':'#/components/parameters/DemoActor'} in op['parameters']

@pytest.mark.parametrize('label',['no_change','fire'])
def test_recompute_indices_area_from_synthetic_rasters(label):
    evidence=fixture(label); directory=ROOT/'fixtures/assets'/('verification_'+label)
    values=[]
    for side in ['before','after']:
        bands={}
        for band in ['B04','B08','B8A','B12']:
            with rasterio.open(directory/(side+'_'+band+'.tif')) as src:
                assert src.crs.to_epsg()==32646
                assert tuple(src.transform)[:6]==tuple(evidence['method']['grid']['transform'])
                bands[band]=src.read(1).astype('float64')*0.0001
        values.append(bands)
    a,b=values
    nbr=lambda x:(x['B8A']-x['B12'])/(x['B8A']+x['B12'])
    ndvi=lambda x:(x['B08']-x['B04'])/(x['B08']+x['B04'])
    dnbr=nbr(a)-nbr(b);mask=dnbr>=0.27
    assert int(mask.sum())==evidence['metrics']['affected_pixel_count']
    assert round(float(dnbr.mean()),6)==evidence['metrics']['dnbr_mean']
    assert round(float(ndvi(a).mean()),6)==evidence['metrics']['ndvi_before_mean']
    assert round(float(ndvi(b).mean()),6)==evidence['metrics']['ndvi_after_mean']
    with rasterio.open(directory/'dnbr.tif') as src:
        assert np.allclose(src.read(1),dnbr,atol=1e-7)
    features=read_json(directory/'affected_area.geojson')['features']
    area=sum(shape(transform_geom('EPSG:4326','EPSG:32646',f['geometry'])).area for f in features)/10000
    assert abs(area-evidence['metrics']['affected_area_ha'])<0.00001

@pytest.mark.parametrize('label',LABELS)
def test_preview_files_are_real_aligned_images(label):
    e=fixture(label)
    for art in e['artifacts']:
        if art['media_type']=='image/png':
            with Image.open(ROOT/'fixtures'/art['relative_path']) as image:
                assert image.size==(art['width'],art['height']);image.verify()

def test_insufficient_coverage_matches_scl():
    with rasterio.open(ROOT/'fixtures/assets/verification_insufficient/after_SCL.tif') as src:
        scl=src.read(1)
    assert np.mean(scl==9)==0.8
    assert np.mean(np.isin(scl,[4,5]))==fixture('insufficient')['quality']['paired_valid_forest_ratio']

@pytest.mark.parametrize('field,value',[('outcome','FROZEN'),('status','FROZEN'),('evidence_hash','0x'+'1'*64),('confidence',0.99)])
def test_rs_cannot_send_financial_status_or_self_hash(field,value):
    e=fixture();e[field]=value
    with pytest.raises(ValidationError):check_schema(e)

def test_bad_timestamp_and_unknown_fields_rejected():
    e=fixture();e['observation']['after']['acquired_at']='2024-08-01'
    with pytest.raises(ValidationError):check_schema(e)
    e=fixture();e['metrics']['forest_loss_pct']=90
    with pytest.raises(ValidationError):check_schema(e)

def test_reversed_dates_rejected():
    e=fixture();e['observation']['before'],e['observation']['after']=e['observation']['after'],e['observation']['before']
    with pytest.raises(ValueError):validate_evidence(e)

@pytest.mark.parametrize('field,value',[('affected_pixel_count',2600),('affected_area_ha',1000),('affected_fraction_of_baseline_forest',0.9),('affected_pixel_count',1)])
def test_bad_area_or_counts_rejected(field,value):
    e=fixture();e['metrics'][field]=value
    with pytest.raises((ValueError,ValidationError)):validate_evidence(e)

def test_wrong_crs_and_grid_rejected():
    e=fixture();e['method']['grid']['epsg']=4326
    with pytest.raises(ValueError):validate_evidence(e)
    e=fixture();e['method']['grid']['transform'][0]=10
    with pytest.raises(ValueError):validate_evidence(e)

def test_geometry_hash_and_unclosed_ring_rejected():
    e=fixture();geo=read_json(ROOT/'fixtures/plot.json')['geometry'];e['plot_geometry_hash']='0x'+'1'*64
    with pytest.raises(ValueError):validate_evidence(e,geometry=geo)
    geo['coordinates'][0][-1][0]+=0.01
    with pytest.raises(ValueError):validate_geometry(geo)

def test_tampered_artifact_rejected(tmp_path):
    shutil.copytree(ROOT/'fixtures',tmp_path/'fixture')
    e=fixture();art=e['artifacts'][0]
    with (tmp_path/'fixture'/art['relative_path']).open('ab') as f:f.write(b'TAMPERED')
    with pytest.raises(ValueError):validate_evidence(e,tmp_path/'fixture')

@pytest.mark.parametrize('value',['../private.key','/etc/passwd','assets/../../private.key','assets\\bad.tif'])
def test_traversal_rejected(value):
    with pytest.raises(ValueError):safe_path(ROOT/'fixtures',value)

def test_nonfinite_rejected():
    e=fixture();e['metrics']['dnbr_mean']=float('nan')
    with pytest.raises(ValueError):validate_evidence(e)

def test_jcs_known_vector_and_key_order():
    sample={'numbers':[333333333.33333329,1e30,4.50,2e-3,1e-27],'literals':[None,True,False]}
    assert canonical(sample)==b'{"literals":[null,true,false],"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27]}'
    assert digest({'a':1,'b':2})==digest({'b':2,'a':1})
    assert sha_bytes(bytes.fromhex('00'*32))!='0x'+'0'*64

def test_real_flag_cannot_relabel_fixture():
    e=fixture();e['dataset_kind']='REAL'
    with pytest.raises(ValidationError):check_schema(e)

def test_seasonal_mismatch_forces_review():
    e=fixture();e['quality']['temporal_comparability']='NO'
    assert validate_evidence(e)['decision']=='REVIEW_REQUIRED'

def test_no_firms_support_means_review_not_fire():
    e=fixture();e['firms'].update(support='NOT_FOUND',hotspot_count=0,matched_points_artifact_id=None)
    assert validate_evidence(e)['reason']=='DISTURBANCE_UNATTRIBUTED'

def changed_counts(e,n,v,k):
    e['metrics'].update(baseline_forest_pixel_count=n,paired_valid_forest_pixel_count=v,affected_pixel_count=k,
        baseline_forest_area_ha=n*0.04,analysed_forest_area_ha=v*0.04,affected_area_ha=k*0.04,
        affected_fraction_of_baseline_forest=round(k/n,6))
    e['quality']['paired_valid_forest_ratio']=round(v/n,6)
    return e

@pytest.mark.parametrize('v,quality',[(1749,'INSUFFICIENT'),(1750,'REVIEW_REQUIRED'),(2124,'REVIEW_REQUIRED'),(2125,'SUFFICIENT')])
def test_quality_boundaries_use_pixel_counts(v,quality):
    e=changed_counts(fixture(),2500,v,400)
    assert evaluate(e)['evidence_quality']==quality

@pytest.mark.parametrize('pixels,decision',[(124,'REVIEW_REQUIRED'),(125,'FREEZE_REQUESTED')])
def test_five_hectare_boundary(pixels,decision):
    assert evaluate(changed_counts(fixture(),2500,2500,pixels))['decision']==decision

def test_fraction_threshold_in_addition_to_area():
    assert evaluate(changed_counts(fixture(),20000,20000,125))['decision']=='REVIEW_REQUIRED'

def test_historical_future_and_frozen_never_auto_reactivate():
    with pytest.raises(ValueError):decision_record(fixture(),'2024-07-01T00:00:00Z')
    assert action_flags('FROZEN','NO_RESTRICTION',is_latest=True,demo_authorized=True)==dict(can_issue=False,can_buy=False,can_transfer_backend=False)
    assert not any(action_flags('ACTIVE','NO_RESTRICTION',is_latest=False,demo_authorized=True).values())
    assert not any(action_flags('ACTIVE','NO_RESTRICTION',is_latest=True,demo_authorized=True,pending_freeze=True).values())

def test_abi_is_compiler_produced_and_consistent():
    abi=read_json(ROOT/'contracts/contract-abi.json');meta=read_json(ROOT/'contracts/abi-build.json')
    assert meta['source_sha256']==sha_bytes((ROOT/'contracts/contract-interface.sol').read_bytes())
    assert meta['abi_sha256']==sha_bytes((ROOT/'contracts/contract-abi.json').read_bytes())
    assert meta['specification_only'] and not meta['deployable_bytecode'] and meta['deployed_contract_address'] is None
    functions={a['name']:a for a in abi if a['type']=='function'}
    assert set(functions)=={'issue','buy','transfer','freeze','getBatch','balanceOf','setIssuer','setOracle','withdrawProceeds'}
    assert functions['buy']['stateMutability']=='payable'
    assert [p['type'] for p in functions['freeze']['inputs']]==['uint256','bytes32','bytes32','uint64','uint8']
    assert [p['name'] for p in functions['getBatch']['outputs'][0]['components']]==['plotId','issuanceKey','seller','totalSupply','creditStatus','unitPriceWei','evidenceHash','decisionHash','issuedAt','frozenAt','lastObservedAt']
    # solc omits constructors from an abstract contract ABI. The constructor is
    # nevertheless compiler-checked in the Solidity specification source.
    source=(ROOT/'contracts/contract-interface.sol').read_text()
    assert 'constructor(address initialOwner)' in source
    assert 'if (initialOwner == address(0)) revert InvalidAddress();' in source

def test_all_shared_schema_fixtures_use_single_version():
    assert all(fixture(label)['schema_version']=='1.0.0' for label in LABELS)
    assert read_json(ROOT/'config/policy.v1.json')['policy_version']=='1.0.0'
