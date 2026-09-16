"""Generate the pinned shared contracts. Edit definitions here, regenerate, review diff."""
from pathlib import Path
from copy import deepcopy
import json
import yaml

ROOT = Path(__file__).resolve().parents[1]
DRAFT = 'https://json-schema.org/draft/2020-12/schema'
BASE = 'https://bountyteam.invalid/contracts/'

def obj(properties, required=None):
    return dict(type='object', properties=properties,
                required=list(properties) if required is None else required,
                additionalProperties=False)

def array(item, **kw): return dict(type='array', items=item, **kw)
def enum(*values): return dict(type='string', enum=list(values))
def nullable(schema): return dict(anyOf=[schema, dict(type='null')])
def ref(name): return {'$ref': '#/$defs/'+name}
def string(**kw): return dict(type='string', **kw)
def number(**kw): return dict(type='number', **kw)
def integer(**kw): return dict(type='integer', **kw)
def write(name, data):
    target = ROOT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')

HASH=string(pattern='^0x[0-9a-f]{64}$')
NONZERO_HASH={**HASH, 'not':{'const':'0x'+'0'*64}}
UTC=string(format='date-time', pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
DECIMAL=string(pattern=r'^(0|[1-9][0-9]{0,77})$')
POSITIVE_DECIMAL=string(pattern=r'^[1-9][0-9]{0,77}$')
ID=string(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$')
RELATIVE=string(pattern=r'^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$')
POSITION={'type':'array', 'prefixItems':[number(minimum=-180,maximum=180),number(minimum=-90,maximum=90)],'items':False,'minItems':2,'maxItems':2}
RING=array(POSITION,minItems=4)
POLYGON=obj({'type':{'const':'Polygon'},'coordinates':array(RING,minItems=1)})
MULTI=obj({'type':{'const':'MultiPolygon'},'coordinates':array(array(RING,minItems=1),minItems=1)})
GEOMETRY={'oneOf':[POLYGON,MULTI]}
BOUNDS={'type':'array','prefixItems':[number(minimum=-180,maximum=180),number(minimum=-90,maximum=90),number(minimum=-180,maximum=180),number(minimum=-90,maximum=90)],'items':False,'minItems':4,'maxItems':4}

defs={
 'Hash32':HASH, 'Timestamp':UTC,
 'SourceAsset':obj({'band':enum('B04','B08','B8A','B12','SCL'), 'source_ref':string(minLength=1,maxLength=2048),
    'local_sha256':NONZERO_HASH,'scale_applied':number(),'offset_applied':number(),
    'transform_origin':enum('PRODUCT_METADATA','PROVIDER_HARMONIZED')}),
 'Scene':obj({'scene_id':string(minLength=1,maxLength=256),'acquired_at':UTC,
    'provider':string(minLength=1,maxLength=96),'collection':string(minLength=1,maxLength=96),
    'processing_baseline':nullable(string(minLength=1,maxLength=64)),
    'mgrs_tile':nullable(string(minLength=1,maxLength=64)), 'assets':array(ref('SourceAsset'),maxItems=16)}),
 'Grid':obj({'epsg':integer(minimum=1,maximum=999999), 'resolution_m':{'const':20},
    'width':integer(minimum=1,maximum=20000),'height':integer(minimum=1,maximum=20000),
    'transform':array(number(),minItems=6,maxItems=6)}),
 'ForestMask':obj({'source':string(minLength=1),'version':string(minLength=1),
    'reference_year':integer(minimum=1970,maximum=2100),'sha256':NONZERO_HASH,
    'interpretation_note':string(minLength=1)}),
 'Parameters':obj({'ndvi_bands':{'const':['B08','B04']},'nbr_bands':{'const':['B8A','B12']},
    'disturbance_dnbr_min':{'const':0.27}, 'min_component_area_ha':{'const':1},
    'connectivity':{'const':8},'excluded_scl_classes':{'const':[0,1,2,3,6,7,8,9,10,11]},
    'resampling_continuous':{'const':'average'},'resampling_categorical':{'const':'nearest'}}),
}
defs['Method']=obj({'pipeline_version':string(minLength=1,maxLength=96),
 'code_commit':nullable(string(pattern='^[0-9a-f]{40}$')),'config_sha256':NONZERO_HASH,
 'grid':nullable(ref('Grid')),'forest_mask':nullable(ref('ForestMask')),'parameters':ref('Parameters')})
defs['Quality']=obj({**{n:nullable(number(minimum=0,maximum=1)) for n in
 ['paired_valid_aoi_ratio','paired_valid_forest_ratio','aoi_cloud_ratio_before','aoi_cloud_ratio_after']},
 'metadata_complete':{'type':'boolean'},'grid_aligned':{'type':'boolean'},
 'temporal_comparability':enum('YES','NO','UNCERTAIN'),'temporal_note':string(minLength=1)})
defs['Metrics']=obj({'plot_area_ha':number(exclusiveMinimum=0),
 **{n:nullable(number(minimum=0)) for n in ['baseline_forest_area_ha','analysed_forest_area_ha','affected_area_ha']},
 'affected_fraction_of_baseline_forest':nullable(number(minimum=0,maximum=1)),
 **{n:nullable(number()) for n in ['ndvi_before_mean','ndvi_after_mean','dnbr_mean']},
 'dnbr_mean_scope':{'const':'PAIRED_VALID_BASELINE_FOREST'},
 **{n:nullable(integer(minimum=0,maximum=400000000)) for n in ['baseline_forest_pixel_count','paired_valid_forest_pixel_count','affected_pixel_count']}})
defs['Firms']=obj({'support':enum('SUPPORTED','NOT_FOUND','NOT_CHECKED'),
 'hotspot_count':integer(minimum=0),'window_start':UTC,'window_end':UTC,
 'spatial_tolerance_m':{'const':500},'product':string(minLength=1),
 'confidence_filter':array(string(minLength=1),uniqueItems=True),
 'source_refs':array(string(minLength=1)), 'matched_points_artifact_id':nullable(ID)})
defs['Artifact']=obj({'artifact_id':ID,'role':enum('PREVIEW_BEFORE','PREVIEW_AFTER','DNBR_RASTER','AFFECTED_AREA','FIRMS_POINTS','DNBR_PREVIEW','SWIR_BEFORE','SWIR_AFTER'),
 'relative_path':RELATIVE,'media_type':enum('image/png','image/webp','image/tiff','application/geo+json'),
 'sha256':NONZERO_HASH,'size_bytes':integer(minimum=1,maximum=1000000000),
 'bounds_wgs84':BOUNDS,'width':integer(minimum=1),'height':integer(minimum=1)},
 required=['artifact_id','role','relative_path','media_type','sha256','size_bytes'])
defs['Artifact']['allOf']=[{'if':{'properties':{'media_type':{'enum':['image/png','image/webp']}}},
 'then':{'required':['bounds_wgs84','width','height']}}]
evidence=obj({'schema_version':{'const':'1.0.0'},'dataset_kind':enum('REAL','SYNTHETIC'),
 'plot_id':ID,'plot_geometry_hash':NONZERO_HASH,'observation':obj({'before':ref('Scene'),'after':ref('Scene')}),
 'outcome':enum('NO_CHANGE','DISTURBANCE_DETECTED','INSUFFICIENT_DATA'),
 'method':ref('Method'),'quality':ref('Quality'),'metrics':ref('Metrics'),
 'firms':ref('Firms'),'artifacts':array(ref('Artifact'),maxItems=32),
 'limitations':array(string(minLength=1),uniqueItems=True)})
numeric_metrics=[k for k in defs['Metrics']['properties'] if k not in ['plot_area_ha','dnbr_mean_scope']]
evidence['allOf']=[
 {'if':{'properties':{'outcome':{'enum':['NO_CHANGE','DISTURBANCE_DETECTED']}}},'then':{
   'properties':{'metrics':{'properties':{n:{'not':{'type':'null'}} for n in numeric_metrics}},
    'method':{'properties':{'grid':{'not':{'type':'null'}},'forest_mask':{'not':{'type':'null'}}}},
    'quality':{'properties':{'metadata_complete':{'const':True},'grid_aligned':{'const':True},
                           'paired_valid_forest_ratio':{'type':'number','minimum':0.7}}},
    'observation':{'properties':{side:{'properties':{'processing_baseline':{'type':'string'},'mgrs_tile':{'type':'string'},'assets':{'minItems':5}}} for side in ['before','after']}}
 }}},
 {'if':{'properties':{'dataset_kind':{'const':'REAL'}}},'then':{'properties':{
    'method':{'properties':{'code_commit':{'type':'string'}}},
    'plot_id':{'not':{'pattern':'^SYNTHETIC'}},
    'observation':{'properties':{side:{'properties':{'scene_id':{'not':{'pattern':'^SYNTHETIC'}}}} for side in ['before','after']}}
 }}},
 {'if':{'properties':{'firms':{'properties':{'support':{'const':'SUPPORTED'}}}}},
  'then':{'properties':{'firms':{'properties':{'hotspot_count':{'minimum':1},'source_refs':{'minItems':1},'matched_points_artifact_id':{'type':'string'}}}}}}
 ]
evidence.update({'$schema':DRAFT,'$id':BASE+'verification.schema.json','title':'VerificationEvidence','$defs':defs})

request=obj({'schema_version':{'const':'1.0.0'},'request_id':string(format='uuid'),
 'plot_id':ID,'geometry':GEOMETRY,'plot_geometry_hash':NONZERO_HASH,
 'before':ref('Scene'),'after':ref('Scene'),'parameters':ref('Parameters'),
 'data_root':string(minLength=1), 'dataset_kind':enum('REAL','SYNTHETIC')})
request.update({'$schema':DRAFT,'$id':BASE+'rs-request.schema.json','$defs':deepcopy(defs)})

policy={'policy_version':'1.0.0','policy_kind':'DEMO_LOGIC',
 'minimum_valid_forest_ratio':0.7,'sufficient_valid_forest_ratio':0.85,
 'freeze_min_area_ha':5,'freeze_min_forest_fraction':0.01,
 'require_firms_support':True,'reason_code_fire_reversal':1,
 'quality_score':'floor(100 * paired_valid_forest_ratio + 0.5)',
 'automatic_unfreeze':False,'automatic_revoke':False}

def api_ref(name): return {'$ref':'#/components/schemas/'+name}
def remap(value):
    if isinstance(value,dict):
        return {k:('#/components/schemas/Evidence'+v.split('/')[-1] if k=='$ref' and v.startswith('#/$defs/') else remap(v)) for k,v in value.items() if k not in ['$id','$schema','$defs']}
    if isinstance(value,list): return [remap(v) for v in value]
    return value

UUID=string(format='uuid')
ADDRESS=string(pattern='^0x[0-9a-fA-F]{40}$')
ACTOR=enum('issuer','buyer','recipient')
OUTCOME=evidence['properties']['outcome']
QUALITY=enum('SUFFICIENT','REVIEW_REQUIRED','INSUFFICIENT')
DECISION=enum('NO_RESTRICTION','REVIEW_REQUIRED','FREEZE_REQUESTED')
REASON=enum('NO_SIGNIFICANT_CHANGE','DATA_INSUFFICIENT','DATA_REVIEW','DISTURBANCE_UNATTRIBUTED','BELOW_POLICY_THRESHOLD','FIRE_REVERSAL')
TXSTATE=enum('QUEUED','SUBMITTED','CONFIRMED','FAILED')
api={**{'Evidence'+k:remap(v) for k,v in defs.items()},'VerificationEvidence':remap(evidence)}
api['ErrorDetail']=obj({'code':string(minLength=1),'message':string(minLength=1),'details':{'type':'object','additionalProperties':True}})
api['Error']=obj({'error':api_ref('ErrorDetail'),'request_id':UUID})
api['ArtifactLink']=obj({'artifact_id':ID,'role':defs['Artifact']['properties']['role'],'url':string(pattern='^/api/v1/artifacts/'), 'sha256':HASH,'media_type':string(minLength=1)})
api['DecisionRecord']=obj({'evidence_hash':HASH,'plot_id':ID,'policy_version':{'const':'1.0.0'},
 'policy_parameters_hash':HASH,'decision':DECISION,'reason':REASON,
 'effective_observed_at':UTC,'replay_as_of':UTC})
api['Verification']=obj({'verification_id':UUID,'evidence':api_ref('VerificationEvidence'),
 'evidence_hash':HASH,'evidence_quality':QUALITY,'evidence_quality_score':nullable(integer(minimum=0,maximum=100)),
 'decision':DECISION,'reason':REASON,'decision_record':api_ref('DecisionRecord'),'decision_hash':HASH,
 'is_latest':{'type':'boolean'},'processed_at':UTC,'observation_mode':{'const':'HISTORICAL_REPLAY'},
 'computation_mode':enum('COMPUTED','CACHED_REPLAY'),'artifacts':array(api_ref('ArtifactLink'))})
api['JobAccepted']=obj({'job_id':UUID,'state':{'const':'QUEUED'},'status_url':string(pattern='^/api/v1/jobs/')})
api['Job']=obj({'job_id':UUID,'state':enum('QUEUED','RUNNING','SUCCEEDED','FAILED'),
 'verification_id':nullable(UUID),'error':nullable(api_ref('ErrorDetail'))})
api['Job']['allOf']=[{'if':{'properties':{'state':{'const':'SUCCEEDED'}}},'then':{'properties':{'verification_id':UUID,'error':{'type':'null'}}}},
 {'if':{'properties':{'state':{'const':'FAILED'}}},'then':{'properties':{'error':api_ref('ErrorDetail'),'verification_id':{'type':'null'}}}}]
api['Receipt']=obj({'transaction_hash':HASH,'block_number':DECIMAL,'status':{'const':1},'event_names':array(string()),'state_readback_ok':{'const':True}})
api['OperationAccepted']=obj({'operation_id':UUID,'transaction_state':{'const':'QUEUED'},'status_url':string(pattern='^/api/v1/operations/')})
api['Operation']=obj({'operation_id':UUID,'kind':enum('ISSUE','BUY','TRANSFER','FREEZE'),
 'transaction_state':TXSTATE,'tx_hash':nullable(HASH),'batch_id':nullable(DECIMAL),
 'error':nullable(api_ref('ErrorDetail')),'receipt':nullable(api_ref('Receipt'))})
api['Operation']['allOf']=[{'if':{'properties':{'transaction_state':{'const':'CONFIRMED'}}},
 'then':{'properties':{'receipt':api_ref('Receipt'),'tx_hash':HASH,'batch_id':DECIMAL,'error':{'type':'null'}}}},
 {'if':{'properties':{'transaction_state':{'enum':['QUEUED','SUBMITTED','FAILED']}}},'then':{'properties':{'receipt':{'type':'null'}}}}]
api['CreditBatch']=obj({'batch_id':DECIMAL,'plot_id':ID,'seller':ADDRESS,'actor':ACTOR,
 'total_supply':POSITIVE_DECIMAL,'seller_balance':DECIMAL,'actor_balance':DECIMAL,
 'unit_price_wei':POSITIVE_DECIMAL,'credit_status':enum('ACTIVE','FROZEN','REVOKED'),
 'evidence_hash':HASH,'decision_hash':HASH,'issued_at':UTC,'frozen_at':nullable(UTC),'last_observed_at':UTC,
 'chain_state_checked_at':UTC,'can_buy':{'type':'boolean'},'can_transfer_backend':{'type':'boolean'}})
api['PlotSummary']=obj({'plot_id':ID,'name':string(minLength=1),'latest_verification_id':nullable(UUID),
 'evidence_quality':nullable(QUALITY),'latest_decision':nullable(DECISION)})
api['Plot']=obj({**deepcopy(api['PlotSummary']['properties']),'geometry':GEOMETRY,
 'geometry_hash':HASH,'area_ha':number(exclusiveMinimum=0),'can_issue':{'type':'boolean'},
 'can_buy':{'type':'boolean'},'can_transfer_backend':{'type':'boolean'},'action_block_reason':nullable(string(minLength=1))})
api['HistoryItem']=obj({'verification_id':UUID,'observed_at':UTC,'processed_at':UTC,'outcome':OUTCOME,
 'evidence_quality':QUALITY,'decision':DECISION,'is_latest':{'type':'boolean'}})
api['Anchor']=obj({'event_name':enum('Issued','Frozen'),'batch_id':DECIMAL,'tx_hash':HASH,
 'evidence_hash':HASH,'decision_hash':nullable(HASH),'confirmed':{'const':True}})
api['Proof']=obj({'evidence_hash':HASH,'recomputed_hash':HASH,'decision_hash':HASH,
 'canonical_url':string(pattern='^/api/v1/verifications/'),'anchors':array(api_ref('Anchor')),'integrity_ok':{'type':'boolean'}})
api['Event']=obj({'event_id':UUID,'occurred_at':UTC,'plot_id':ID,
 'kind':enum('VERIFICATION','DECISION','TX_SUBMITTED','TX_CONFIRMED','TX_FAILED'),
 'verification_id':nullable(UUID),'operation_id':nullable(UUID),'tx_hash':nullable(HASH),
 'batch_id':nullable(DECIMAL),'message':string(minLength=1)})
api['Events']=obj({'items':array(api_ref('Event')),'next_cursor':nullable(string(minLength=1))})
api['Health']=obj({**{k:enum('UP','DOWN') for k in ['api','db','worker','chain']},
 'deployment_id':nullable(UUID),'mode':enum('CONTRACT_FIXTURE','LOCAL_DEMO')})
api['VerifyRequest']=obj({'scenario_id':enum('baseline','post_fire','insufficient')})
api['IssueRequest']=obj({'demo_authorization_id':ID})
api['BuyRequest']=obj({'amount':POSITIVE_DECIMAL})
api['TransferRequest']=obj({'to_actor':ACTOR,'amount':POSITIVE_DECIMAL})
for name,item in [('Plots','PlotSummary'),('Credits','CreditBatch'),('History','HistoryItem')]:
    api[name]=obj({'items':array(api_ref(item))})

paths={}
def endpoint(path,method,operation,response,body=None,actor=False):
    params=[]
    for parameter,part in [('plot_id',ID),('batch_id',DECIMAL),('job_id',UUID),('verification_id',UUID),('operation_id',UUID),('artifact_id',ID)]:
        if '{'+parameter+'}' in path:
            params.append(dict(name=parameter,**{'in':'path'},required=True,schema=part))
    mutation=method=='post'
    if mutation: params.append({'$ref':'#/components/parameters/IdempotencyKey'})
    if mutation or actor: params.append({'$ref':'#/components/parameters/DemoActor'})
    responses={'202' if mutation else '200':{'description':'Принято в очередь' if mutation else 'Успешное чтение',
        'content':{'application/json':{'schema':api_ref(response)}}}}
    for code in ['401','403','404','409','422','503']:
        responses[code]={'$ref':'#/components/responses/Failure'}
    value={'operationId':operation,'summary':operation,'parameters':params,'responses':responses,
        'security':[{'DemoSession':[]}]}
    if body: value['requestBody']={'required':True,'content':{'application/json':{'schema':api_ref(body)}}}
    paths.setdefault(path,{})[method]=value

endpoint('/health','get','getHealth','Health'); paths['/health']['get']['security']=[]
endpoint('/plots','get','listPlots','Plots')
endpoint('/plots/{plot_id}','get','getPlot','Plot',actor=True)
endpoint('/plots/{plot_id}/verify','post','startVerification','JobAccepted','VerifyRequest')
endpoint('/jobs/{job_id}','get','getVerificationJob','Job')
endpoint('/verifications/{verification_id}','get','getVerification','Verification')
endpoint('/verifications/{verification_id}/proof','get','getProof','Proof')
endpoint('/verifications/{verification_id}/canonical','get','getCanonicalEvidence','VerificationEvidence')
endpoint('/plots/{plot_id}/history','get','getHistory','History')
endpoint('/plots/{plot_id}/credits','get','getCredits','Credits',actor=True)
endpoint('/plots/{plot_id}/issue','post','issueBatch','OperationAccepted','IssueRequest')
endpoint('/batches/{batch_id}/buy','post','buyCredits','OperationAccepted','BuyRequest')
endpoint('/batches/{batch_id}/transfer','post','transferCredits','OperationAccepted','TransferRequest')
endpoint('/operations/{operation_id}','get','getOperation','Operation')
endpoint('/events','get','listEvents','Events')
paths['/events']['get']['parameters']=[{'name':'plot_id','in':'query','required':True,'schema':ID},
 {'name':'cursor','in':'query','schema':string(minLength=1)},{'name':'limit','in':'query','schema':integer(minimum=1,maximum=100,default=50)}]
endpoint('/artifacts/{artifact_id}','get','getArtifact','Error')
paths['/artifacts/{artifact_id}']['get']['responses']['200']={'description':'Файл из разрешённого manifest',
 'content':{m:{'schema':string(format='binary')} for m in ['image/png','image/webp','image/tiff','application/geo+json']}}
paths['/verifications/{verification_id}/canonical']['get']['description']='Возвращает сохранённые JCS-байты без повторной сериализации.'
for p in ['/plots/{plot_id}/verify','/plots/{plot_id}/issue']:
    paths[p]['post']['description']='Только demo-актор issuer. Неверная роль — 403.'
oas={'openapi':'3.1.0','info':{'title':'BountyTeam shared REST contract','version':'1.0.0',
 'description':'Specification, not a running service. Historical replay and valueless demo units only.'},
 'jsonSchemaDialect':DRAFT,'servers':[{'url':'http://127.0.0.1:8000/api/v1'}],
 'paths':paths,'components':{'schemas':api,'securitySchemes':{'DemoSession':{'type':'apiKey','in':'header','name':'X-Demo-Session'}},
 'parameters':{'IdempotencyKey':{'name':'Idempotency-Key','in':'header','required':True,'schema':string(minLength=8,maxLength=128)},
 'DemoActor':{'name':'X-Demo-Actor','in':'header','required':True,'schema':ACTOR}},
 'responses':{'Failure':{'description':'Структурированная ошибка','content':{'application/json':{'schema':api_ref('Error')}}}}}}

def main():
    write('contracts/verification.schema.json',evidence)
    write('contracts/rs-request.schema.json',request)
    write('config/policy.v1.json',policy)
    write('contracts/api-models.schema.json',{'$schema':DRAFT,'$id':BASE+'api-models.schema.json','components':{'schemas':api}})
    (ROOT/'contracts/openapi.yaml').write_text(yaml.safe_dump(oas,allow_unicode=True,sort_keys=False),encoding='utf8')
    write('contracts/deployment.schema.json',{'$schema':DRAFT,**obj({'deployment_id':UUID,
     'chain_id':DECIMAL,'contract_address':ADDRESS,'deployment_tx_hash':HASH,
     'contract_code_hash':NONZERO_HASH,'abi_sha256':HASH,
     'roles':obj({'owner':ADDRESS,'issuer':ADDRESS,'oracle':ADDRESS,'buyer':ADDRESS,'recipient':ADDRESS})})})
    print('Generated JSON Schema, OpenAPI, policy and deployment schema.')

if __name__=='__main__': main()
