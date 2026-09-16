"""Deterministic SYNTHETIC contract fixtures, not observations of an actual forest."""
from pathlib import Path
from copy import deepcopy
import json
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.features import shapes
from rasterio.warp import transform_geom, transform_bounds
from PIL import Image, ImageDraw
from contract_helpers import ROOT, canonical, digest, sha_bytes, read_json, evaluate, decision_record

FIX=ROOT/'fixtures'
TRANSFORM=Affine(20,0,430000,0,-20,6230000)
CRS='EPSG:32646'
DATES=['2023-07-10T05:00:00Z','2024-07-10T05:00:00Z','2024-08-01T05:00:00Z']

def save_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')

def tif(path,array):
    path.parent.mkdir(parents=True,exist_ok=True)
    with rasterio.open(path,'w',driver='GTiff',height=50,width=50,count=1,
                       dtype=array.dtype,crs=CRS,transform=TRANSFORM,compress='deflate') as ds:
        ds.write(array,1)

def preview(path,burn=False,cloud=False):
    image=Image.new('RGB',(400,400),(38,117,69));draw=ImageDraw.Draw(image)
    if burn: draw.rectangle((120,120,279,279),fill=(149,70,41))
    if cloud: draw.rectangle((0,80,399,399),fill=(180,180,185))
    draw.rectangle((0,0,399,23),fill=(0,0,0));draw.text((8,6),'SYNTHETIC FIXTURE - NOT SATELLITE DATA',fill=(255,255,255))
    image.save(path)

def main():
    FIX.mkdir(parents=True,exist_ok=True)
    params=read_json(ROOT/'contracts/verification.schema.json')['$defs']['Parameters']['properties']
    params={k:v['const'] for k,v in params.items()}
    bounds=list(transform_bounds(CRS,'EPSG:4326',430000,6229000,431000,6230000))
    geo=transform_geom(CRS,'EPSG:4326',{'type':'Polygon','coordinates':[[[430000,6229000],[431000,6229000],[431000,6230000],[430000,6230000],[430000,6229000]]]})
    project=dict(plot_id='SYNTHETIC-PLOT-001',name='Синтетический AOI для тестирования интерфейсов',geometry=geo,
                 geometry_hash=digest(geo),area_ha=100,dataset_kind='SYNTHETIC')
    save_json(FIX/'plot.json',project)
    source_index={}
    def index_file(path):
        h=sha_bytes(path.read_bytes());source_index[h]=path.relative_to(FIX).as_posix();return h
    forest_path=FIX/'assets/source_forest_mask.tif';tif(forest_path,np.ones((50,50),dtype='uint8'))
    forest_hash=index_file(forest_path)
    evidence_map={}; expected={}; requests={}; response_examples=[]
    for label,before_i,after_i in [('no_change',0,1),('fire',1,2),('insufficient',1,2)]:
        directory=FIX/'assets'/('verification_'+label);directory.mkdir(parents=True,exist_ok=True)
        scenes=[]; arrays=[]
        for side,i in [('before',before_i),('after',after_i)]:
            band_values={'B04':1000,'B08':5000,'B8A':5000,'B12':2000,'SCL':4}
            image_arrays={b:np.full((50,50),v,dtype='uint16') for b,v in band_values.items()}
            if label in ['fire','insufficient'] and side=='after':
                for b,v in {'B04':1500,'B08':1800,'B8A':1800,'B12':3500,'SCL':5}.items():
                    image_arrays[b][15:35,15:35]=v
            if label=='insufficient' and side=='after': image_arrays['SCL'][10:,:]=9
            assets=[]
            for band,values in image_arrays.items():
                path=directory/(side+'_'+band+'.tif');tif(path,values);h=index_file(path)
                assets.append(dict(band=band,source_ref='fixture://'+path.relative_to(FIX).as_posix(),local_sha256=h,
                    scale_applied=1 if band=='SCL' else 0.0001,offset_applied=0,
                    transform_origin='PRODUCT_METADATA' if band=='SCL' else 'PROVIDER_HARMONIZED'))
            scenes.append(dict(scene_id='SYNTHETIC_T'+str(i)+'_'+label,acquired_at=DATES[i],provider='SYNTHETIC_FIXTURE',
                collection='not-a-sentinel-collection',processing_baseline='SYNTHETIC-1',mgrs_tile='SYNTHETIC',assets=sorted(assets,key=lambda a:a['band'])))
            arrays.append(image_arrays)
        dnbr=[]; ndvis=[]
        for bands in arrays:
            vals={k:v.astype('float64')*0.0001 for k,v in bands.items() if k!='SCL'}
            dnbr.append((vals['B8A']-vals['B12'])/(vals['B8A']+vals['B12']))
            ndvis.append((vals['B08']-vals['B04'])/(vals['B08']+vals['B04']))
        difference=dnbr[0]-dnbr[1]
        mask=difference>=0.27
        incomplete=label=='insufficient'; count=int(mask.sum())
        files=[]
        def artifact(path,role,mime):
            a=dict(artifact_id=label+'-'+role.lower(),role=role,relative_path=path.relative_to(FIX).as_posix(),
                   media_type=mime,sha256=sha_bytes(path.read_bytes()),size_bytes=path.stat().st_size)
            if mime=='image/png':a.update(bounds_wgs84=bounds,width=400,height=400)
            files.append(a);return a['artifact_id']
        for side in ['before','after']:
            path=directory/(side+'.png');preview(path,burn=label!='no_change' and side=='after',cloud=incomplete and side=='after')
            artifact(path,'PREVIEW_'+side.upper(),'image/png')
        if not incomplete:
            path=directory/'dnbr.tif';tif(path,difference.astype('float32'));artifact(path,'DNBR_RASTER','image/tiff')
            features=[]
            for geometry,value in shapes(mask.astype('uint8'),mask=mask,transform=TRANSFORM,connectivity=8):
                features.append({'type':'Feature','properties':{'synthetic':True},'geometry':transform_geom(CRS,'EPSG:4326',geometry)})
            path=directory/'affected_area.geojson';save_json(path,{'type':'FeatureCollection','features':features})
            artifact(path,'AFFECTED_AREA','application/geo+json')
        firms_id=None; refs=[]
        if label=='fire':
            path=directory/'firms_points.geojson'
            point=transform_geom(CRS,'EPSG:4326',{'type':'Point','coordinates':[430500,6229500]})
            save_json(path,{'type':'FeatureCollection','features':[{'type':'Feature','geometry':point,'properties':{
                'synthetic':True,'acquired_at':'2024-07-15T10:00:00Z','confidence':'nominal','source':'SYNTHETIC_NOT_NASA'}}]})
            firms_id=artifact(path,'FIRMS_POINTS','application/geo+json');refs=['fixture://'+path.relative_to(FIX).as_posix()]
        evidence=dict(schema_version='1.0.0',dataset_kind='SYNTHETIC',plot_id=project['plot_id'],plot_geometry_hash=project['geometry_hash'],
            observation=dict(before=scenes[0],after=scenes[1]),outcome='INSUFFICIENT_DATA' if incomplete else ('DISTURBANCE_DETECTED' if count else 'NO_CHANGE'),
            method=dict(pipeline_version='synthetic-fixture-generator/1.0.0',code_commit=None,config_sha256=digest(params),
                grid=dict(epsg=32646,resolution_m=20,width=50,height=50,transform=list(TRANSFORM)[:6]),
                forest_mask=dict(source='fixture://assets/source_forest_mask.tif',version='synthetic-1',reference_year=2021,sha256=forest_hash,
                    interpretation_note='Synthetic all-forest mask. Not WorldCover, not a real land inventory.'),parameters=params),
            quality=dict(paired_valid_aoi_ratio=0.2 if incomplete else 1,paired_valid_forest_ratio=0.2 if incomplete else 1,
                aoi_cloud_ratio_before=0,aoi_cloud_ratio_after=0.8 if incomplete else 0,metadata_complete=True,grid_aligned=True,
                temporal_comparability='YES',temporal_note='Synthetic seasonal compatibility flag for contract tests only.'),
            metrics=dict(plot_area_ha=100,baseline_forest_area_ha=100,analysed_forest_area_ha=20 if incomplete else 100,
                affected_area_ha=None if incomplete else count*0.04,affected_fraction_of_baseline_forest=None if incomplete else count/2500,
                ndvi_before_mean=None if incomplete else round(float(ndvis[0].mean()),6),
                ndvi_after_mean=None if incomplete else round(float(ndvis[1].mean()),6),dnbr_mean=None if incomplete else round(float(difference.mean()),6),
                dnbr_mean_scope='PAIRED_VALID_BASELINE_FOREST',baseline_forest_pixel_count=2500,
                paired_valid_forest_pixel_count=500 if incomplete else 2500,affected_pixel_count=None if incomplete else count),
            firms=dict(support='SUPPORTED' if label=='fire' else ('NOT_CHECKED' if incomplete else 'NOT_FOUND'),
                hotspot_count=1 if label=='fire' else 0,window_start=DATES[before_i],window_end=DATES[after_i],
                spatial_tolerance_m=500,product='SYNTHETIC_VIIRS_SHAPED_TEST_DATA',confidence_filter=['nominal','high'],
                source_refs=refs,matched_points_artifact_id=firms_id),artifacts=sorted(files,key=lambda x:x['artifact_id']),
            limitations=['Entire fixture is synthetic, including location, spectral values, classifications and FIRMS-shaped support.',
                         'Contract test only; not scientific validation and not a carbon credit.'])
        evidence_map[label]=evidence
        save_json(FIX/('verification_'+label+'.json'),evidence)
        can=canonical(evidence);(FIX/('verification_'+label+'.canonical.json')).write_bytes(can)
        record=decision_record(evidence,DATES[after_i]);decision_hash=digest(record)
        result=evaluate(evidence)
        expected[label]={**result,'evidence_hash':digest(evidence),'decision_hash':decision_hash,'decision_record':record}
        request=dict(schema_version='1.0.0',request_id=f'10000000-0000-4000-8000-00000000000{len(requests)+1}',
            plot_id=project['plot_id'],geometry=geo,plot_geometry_hash=digest(geo),before=scenes[0],after=scenes[1],
            parameters=params,data_root='fixtures',dataset_kind='SYNTHETIC')
        requests[label]=request;save_json(FIX/('rs_request_'+label+'.json'),request)
        verification_id=f'20000000-0000-4000-8000-00000000000{len(requests)}'
        envelope=dict(verification_id=verification_id,evidence=evidence,evidence_hash=digest(evidence),
            **result,decision_record=record,decision_hash=decision_hash,is_latest=True,processed_at='2026-09-16T12:00:00Z',
            observation_mode='HISTORICAL_REPLAY',computation_mode='CACHED_REPLAY',
            artifacts=[dict(artifact_id=a['artifact_id'],role=a['role'],url='/api/v1/artifacts/'+a['artifact_id'],sha256=a['sha256'],media_type=a['media_type']) for a in evidence['artifacts']])
        response_examples.append(dict(name='verification_'+label,method='GET',path='/verifications/{verification_id}',status=200,response_schema='Verification',body=envelope))
    save_json(FIX/'source-index.json',source_index)
    save_json(FIX/'expected_results.json',expected)
    save_json(ROOT/'config/scenarios.json',{'mode':'CONTRACT_FIXTURE','dataset_kind':'SYNTHETIC',
        'real_scenes_configured':False,'scenarios':{k:{'fixture':'fixtures/verification_'+v+'.json',
        'rs_request':'fixtures/rs_request_'+v+'.json'} for k,v in [('baseline','no_change'),('post_fire','fire'),('insufficient','insufficient')]}})
    save_json(ROOT/'config/demo-authorizations.json',{'mode':'CONTRACT_FIXTURE','authorizations':[{
        'demo_authorization_id':'SYNTHETIC-AUTH-001','plot_id':project['plot_id'],'amount':'100',
        'unit_price_wei':'1000000000000000','issuer_actor':'issuer','seller_actor':'issuer','single_use':True,
        'certified_carbon_units':False}]})
    uid='20000000-0000-4000-8000-000000000001';job='30000000-0000-4000-8000-000000000001';op='40000000-0000-4000-8000-000000000001'
    blank='0x'+'0'*64
    examples=[
      ('health','GET','/health','Health',dict(api='UP',db='UP',worker='UP',chain='DOWN',deployment_id=None,mode='CONTRACT_FIXTURE')),
      ('plots','GET','/plots','Plots',{'items':[dict(plot_id=project['plot_id'],name=project['name'],latest_verification_id=uid,evidence_quality='SUFFICIENT',latest_decision='NO_RESTRICTION')]}),
      ('plot','GET','/plots/{plot_id}','Plot',dict(plot_id=project['plot_id'],name=project['name'],latest_verification_id=uid,evidence_quality='SUFFICIENT',latest_decision='NO_RESTRICTION',geometry=geo,geometry_hash=digest(geo),area_ha=100,can_issue=True,can_buy=False,can_transfer_backend=False,action_block_reason=None)),
      ('job','GET','/jobs/{job_id}','Job',dict(job_id=job,state='SUCCEEDED',verification_id=uid,error=None)),
      ('proof','GET','/verifications/{verification_id}/proof','Proof',dict(evidence_hash=expected['no_change']['evidence_hash'],recomputed_hash=expected['no_change']['evidence_hash'],decision_hash=expected['no_change']['decision_hash'],canonical_url='/api/v1/verifications/'+uid+'/canonical',anchors=[],integrity_ok=True)),
      ('canonical','GET','/verifications/{verification_id}/canonical','VerificationEvidence',evidence_map['no_change']),
      ('history','GET','/plots/{plot_id}/history','History',{'items':[dict(verification_id=uid,observed_at=DATES[1],processed_at='2026-09-16T12:00:00Z',outcome='NO_CHANGE',evidence_quality='SUFFICIENT',decision='NO_RESTRICTION',is_latest=True)]}),
      ('credits','GET','/plots/{plot_id}/credits','Credits',{'items':[]}),
      ('operation','GET','/operations/{operation_id}','Operation',dict(operation_id=op,kind='FREEZE',transaction_state='QUEUED',tx_hash=None,batch_id='0',error=None,receipt=None)),
      ('events','GET','/events','Events',{'items':[],'next_cursor':None}),
    ]
    for name,method,path,schema,body in examples:
        response_examples.append(dict(name=name,method=method,path=path,status=200,response_schema=schema,body=body))
    for name,path,request_schema,body in [
      ('verify','/plots/{plot_id}/verify','VerifyRequest',{'scenario_id':'baseline'}),
      ('issue','/plots/{plot_id}/issue','IssueRequest',{'demo_authorization_id':'SYNTHETIC-AUTH-001'}),
      ('buy','/batches/{batch_id}/buy','BuyRequest',{'amount':'10'}),
      ('transfer','/batches/{batch_id}/transfer','TransferRequest',{'to_actor':'recipient','amount':'1'})]:
        response=dict(job_id=job,state='QUEUED',status_url='/api/v1/jobs/'+job) if name=='verify' else dict(operation_id=op,transaction_state='QUEUED',status_url='/api/v1/operations/'+op)
        response_examples.append(dict(name=name,method='POST',path=path,status=202,
            request_schema=request_schema,request_body=body,response_schema='JobAccepted' if name=='verify' else 'OperationAccepted',body=response))
    response_examples.append(dict(name='invalid_json',method='POST',path='/plots/{plot_id}/verify',status=422,response_schema='Error',
        body={'error':{'code':'INVALID_EVIDENCE','message':'Неверная схема','details':{}},'request_id':job}))
    save_json(FIX/'http_examples.json',{'synthetic':True,'not_a_running_service':True,'cases':response_examples})
    print('Generated three synthetic evidence bundles, hashes, RS requests and HTTP examples.')

if __name__=='__main__': main()
