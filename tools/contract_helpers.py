"""Reference validation/hash/policy functions; NOT the application or an oracle worker."""
from pathlib import Path
import hashlib
import json
import math
from decimal import Decimal
from datetime import datetime
import rfc8785
from jsonschema import Draft202012Validator, FormatChecker
from shapely.geometry import shape

ROOT=Path(__file__).resolve().parents[1]

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf8'),
                      parse_constant=lambda s: (_ for _ in ()).throw(ValueError('Non-finite JSON: '+s)))

def canonical(value): return rfc8785.dumps(value)
def sha_bytes(data): return '0x'+hashlib.sha256(data).hexdigest()
def digest(value): return sha_bytes(canonical(value))
def utc(value): return datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ')

def check_schema(value, name='verification.schema.json'):
    schema=read_json(ROOT/'contracts'/name)
    Draft202012Validator(schema,format_checker=FormatChecker()).validate(value)

def check_api(value, name):
    schema=read_json(ROOT/'contracts/api-models.schema.json')
    schema['$ref']='#/components/schemas/'+name
    Draft202012Validator(schema,format_checker=FormatChecker()).validate(value)

def finite_tree(value):
    if isinstance(value,float) and not math.isfinite(value): raise ValueError('Non-finite number')
    if isinstance(value,dict):
        for item in value.values(): finite_tree(item)
    if isinstance(value,list):
        for item in value: finite_tree(item)

def safe_path(root, relative):
    base=Path(root).resolve()
    given=Path(relative)
    if given.is_absolute() or '..' in given.parts or '\\' in relative:
        raise ValueError('Unsafe relative path')
    path=base/given
    for candidate in [path,*path.parents]:
        if candidate==base: break
        if candidate.is_symlink(): raise ValueError('Symlink in bundle')
    if not path.resolve().is_relative_to(base): raise ValueError('Path escapes bundle')
    if not path.is_file(): raise ValueError('Missing bundle file: '+relative)
    return path

def assert_close(actual, expected, field, tolerance=0.0000011):
    if actual is None or abs(float(actual)-float(expected))>tolerance:
        raise ValueError('Inconsistent '+field)

def validate_geometry(geometry):
    geom=shape(geometry)
    if geom.is_empty or not geom.is_valid or geom.geom_type not in ('Polygon','MultiPolygon'):
        raise ValueError('Invalid polygon')
    # Shapely closes open rings automatically; require explicit closed rings as submitted.
    polygons=[geometry['coordinates']] if geometry['type']=='Polygon' else geometry['coordinates']
    for polygon in polygons:
        for ring in polygon:
            if ring[0]!=ring[-1]: raise ValueError('Unclosed GeoJSON ring')
    if not (-180<=geom.bounds[0]<=geom.bounds[2]<=180 and -90<=geom.bounds[1]<=geom.bounds[3]<=90):
        raise ValueError('Invalid WGS84 coordinates')

def validate_evidence(e, bundle_root=None, geometry=None):
    finite_tree(e); check_schema(e)
    before=e['observation']['before']; after=e['observation']['after']
    if utc(before['acquired_at'])>=utc(after['acquired_at']): raise ValueError('Invalid observation chronology')
    if geometry is not None:
        validate_geometry(geometry)
        if digest(geometry)!=e['plot_geometry_hash']: raise ValueError('Wrong plot geometry hash')
    m=e['metrics']; q=e['quality']; method=e['method']; params=method['parameters']
    if method['config_sha256']!=digest(params): raise ValueError('Wrong processing config hash')
    grid=method['grid']
    if grid:
        a,b,c,d,f,g=grid['transform']
        if b!=0 or d!=0 or a!=20 or f!=-20: raise ValueError('v1 requires north-up 20 m grid')
        if not (32601<=grid['epsg']<=32660 or 32701<=grid['epsg']<=32760):
            raise ValueError('v1 grid must use WGS84 UTM metres')
        if e['outcome']!='INSUFFICIENT_DATA' and m['baseline_forest_pixel_count'] is None:
            raise ValueError('Missing pixel counts')
        n=m['baseline_forest_pixel_count']; v=m['paired_valid_forest_pixel_count']; k=m['affected_pixel_count']
        if n is not None:
            if n<=0 or n>grid['width']*grid['height']: raise ValueError('Invalid forest count')
            assert_close(m['baseline_forest_area_ha'], n*0.04, 'forest area')
        if v is not None and n is not None:
            if not 0<=v<=n: raise ValueError('Invalid valid count')
            assert_close(m['analysed_forest_area_ha'],v*0.04,'analysed area')
            assert_close(q['paired_valid_forest_ratio'],v/n,'valid ratio')
        if k is not None and n is not None and v is not None:
            if not 0<=k<=v: raise ValueError('Invalid affected count')
            if 0<k<25: raise ValueError('Below minimum connected-component area')
            assert_close(m['affected_area_ha'],k*0.04,'affected area')
            assert_close(m['affected_fraction_of_baseline_forest'],k/n,'affected fraction')
    else:
        if q['grid_aligned']: raise ValueError('No grid but grid_aligned=true')
        if e['outcome']!='INSUFFICIENT_DATA': raise ValueError('Missing grid')
    ids=[x['artifact_id'] for x in e['artifacts']]
    roles=[x['role'] for x in e['artifacts']]
    paths=[x['relative_path'] for x in e['artifacts']]
    if len(set(ids))!=len(ids) or len(set(paths))!=len(paths) or len(set(roles))!=len(roles):
        raise ValueError('Duplicate artifact identity/role/path')
    if e['outcome']!='INSUFFICIENT_DATA':
        if not {'AFFECTED_AREA','DNBR_RASTER','PREVIEW_BEFORE','PREVIEW_AFTER'}<=set(roles):
            raise ValueError('Missing analysable evidence artifacts')
        for scene in [before,after]:
            bands=[a['band'] for a in scene['assets']]
            if sorted(bands)!=['B04','B08','B12','B8A','SCL']:
                raise ValueError('Expected exactly five input bands')
    for art in e['artifacts']:
        expected={'AFFECTED_AREA':'application/geo+json','FIRMS_POINTS':'application/geo+json','DNBR_RASTER':'image/tiff'}.get(art['role'])
        if expected and art['media_type']!=expected: raise ValueError('Wrong artifact MIME')
        if 'bounds_wgs84' in art:
            w,s,x,n=art['bounds_wgs84']
            if not w<x or not s<n: raise ValueError('Invalid preview bounds')
    previews=[a for a in e['artifacts'] if a['role'] in ['PREVIEW_BEFORE','PREVIEW_AFTER']]
    if len(previews)==2:
        if any(previews[0][f]!=previews[1][f] for f in ['width','height','bounds_wgs84']):
            raise ValueError('Unaligned previews')
    firms=e['firms']
    if (firms['window_start'],firms['window_end'])!=(before['acquired_at'],after['acquired_at']):
        raise ValueError('FIRMS window differs from comparison')
    if firms['support']=='SUPPORTED' and (firms['matched_points_artifact_id'] not in ids or firms['hotspot_count']<1):
        raise ValueError('Missing FIRMS supporting artifact')
    if firms['support']!='SUPPORTED' and firms['hotspot_count']!=0:
        raise ValueError('hotspot_count means matched usable detections, not all nearby points')
    if bundle_root is not None:
        total=0
        for art in e['artifacts']:
            path=safe_path(bundle_root,art['relative_path']); data=path.read_bytes(); total+=len(data)
            if len(data)!=art['size_bytes'] or sha_bytes(data)!=art['sha256']: raise ValueError('Artifact checksum/size mismatch')
        if total>512*1024*1024: raise ValueError('Oversized bundle outputs')
        index=read_json(Path(bundle_root)/'source-index.json')
        hashes=[asset['local_sha256'] for scene in [before,after] for asset in scene['assets']]
        if method['forest_mask']: hashes.append(method['forest_mask']['sha256'])
        for h in hashes:
            if h not in index: raise ValueError('Missing source cache entry')
            if sha_bytes(safe_path(bundle_root,index[h]).read_bytes())!=h: raise ValueError('Source checksum mismatch')
    result=evaluate(e)
    if result['evidence_quality']=='INSUFFICIENT' and e['outcome']!='INSUFFICIENT_DATA':
        raise ValueError('Outcome claims analysis despite insufficient data')
    if result['evidence_quality']!='INSUFFICIENT':
        k=m['affected_pixel_count']
        if k is None: raise ValueError('Analysable report needs affected count')
        expected='DISTURBANCE_DETECTED' if k>0 else 'NO_CHANGE'
        if e['outcome']!=expected: raise ValueError('Outcome disagrees with counts/gates')
    return result

def evaluate(e):
    """Classification of ONE evidence; no authorisation, tx, state mutation or automatic unfreeze."""
    p=read_json(ROOT/'config/policy.v1.json'); q=e['quality']; m=e['metrics']
    n=m['baseline_forest_pixel_count']; v=m['paired_valid_forest_pixel_count']; k=m['affected_pixel_count']
    ratio=None if n is None or n==0 or v is None else Decimal(v)/Decimal(n)
    score=None if ratio is None else math.floor(100*ratio+Decimal('0.5'))
    bad=(ratio is None or ratio<Decimal(str(p['minimum_valid_forest_ratio'])) or not q['metadata_complete'] or not q['grid_aligned'] or e['method']['grid'] is None or e['method']['forest_mask'] is None)
    if bad: quality,decision,reason='INSUFFICIENT','REVIEW_REQUIRED','DATA_INSUFFICIENT'
    elif ratio<Decimal(str(p['sufficient_valid_forest_ratio'])) or q['temporal_comparability']!='YES':
        quality,decision,reason='REVIEW_REQUIRED','REVIEW_REQUIRED','DATA_REVIEW'
    elif e['outcome']=='NO_CHANGE':
        quality,decision,reason='SUFFICIENT','NO_RESTRICTION','NO_SIGNIFICANT_CHANGE'
    elif k is None:
        raise ValueError('Missing affected pixels')
    elif Decimal(k)*Decimal('0.04')<Decimal(str(p['freeze_min_area_ha'])) or Decimal(k)/Decimal(n)<Decimal(str(p['freeze_min_forest_fraction'])):
        quality,decision,reason='SUFFICIENT','REVIEW_REQUIRED','BELOW_POLICY_THRESHOLD'
    elif e['firms']['support']!='SUPPORTED':
        quality,decision,reason='SUFFICIENT','REVIEW_REQUIRED','DISTURBANCE_UNATTRIBUTED'
    else:
        quality,decision,reason='SUFFICIENT','FREEZE_REQUESTED','FIRE_REVERSAL'
    return dict(evidence_quality=quality,evidence_quality_score=score,decision=decision,reason=reason)

def decision_record(e, replay_as_of):
    if utc(replay_as_of)<utc(e['observation']['after']['acquired_at']):
        raise ValueError('Cannot use future evidence in replay')
    result=evaluate(e); p=read_json(ROOT/'config/policy.v1.json')
    return dict(evidence_hash=digest(e),plot_id=e['plot_id'],policy_version=p['policy_version'],
        policy_parameters_hash=digest(p),decision=result['decision'],reason=result['reason'],
        effective_observed_at=e['observation']['after']['acquired_at'],replay_as_of=replay_as_of)

def action_flags(credit_status, latest_decision, *, is_latest, demo_authorized, pending_freeze=False):
    """API gating. Actual ACTIVE contract transfers remain possible until freeze confirms."""
    gate=is_latest and latest_decision=='NO_RESTRICTION' and not pending_freeze
    return dict(can_issue=gate and demo_authorized and credit_status is None,
        can_buy=gate and credit_status=='ACTIVE',can_transfer_backend=gate and credit_status=='ACTIVE')
