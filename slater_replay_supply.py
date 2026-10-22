"""Optional, bounded replay supply. Local files first; no quota bypass or secrets in reports."""
from __future__ import annotations
import argparse,base64,datetime,getpass,hashlib,io,json,os,shutil,time,urllib.error,urllib.parse,urllib.request,uuid,zipfile
from pathlib import Path
from slater_v041_core import atomic_json,read_json,sha256,process_lock

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'data/isolated/native_replay_supply'
CONFIG=BASE/'config.json'
DEFAULT={'enabled':True,'batch_size':64,'refresh_cycles':4,'hour_limit':180,
    'after':'2021-01-01','before':'2026-10-12','min_tier':21,'max_tier':22,
    'kaggle_fallback':True,'kaggle_local':None,'max_file_mb':30,'min_disk_gb':10}
KAGGLE='https://www.kaggle.com/api/v1/datasets/'
DATASET='rolvarild/high-level-rocket-league-replay-dataset'

class SupplyUnavailable(RuntimeError):pass
class Limited(SupplyUnavailable):pass
class SupplyPaused(RuntimeError):pass

def check_pause(stop_file):
    if stop_file and Path(stop_file).exists():raise SupplyPaused('Replay acquisition paused at request boundary')

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if urllib.parse.urlsplit(newurl).scheme!='https':raise SupplyUnavailable('Non-HTTPS redirect refused')
        redirected=super().redirect_request(req,fp,code,msg,headers,newurl)
        if urllib.parse.urlsplit(newurl).hostname!=urllib.parse.urlsplit(req.full_url).hostname:
            redirected.remove_header('Authorization')
        return redirected

def request(url,headers=None,*,max_bytes=30*1024**2,opener=None):
    req=urllib.request.Request(url,headers={'User-Agent':'Slater-Replay-Supply/1.0',**(headers or {})})
    try:
        with (opener or urllib.request.build_opener(SafeRedirect()).open)(req,timeout=30) as response:
            raw=response.read(max_bytes+1)
            if len(raw)>max_bytes:raise SupplyUnavailable('Response exceeds bounded download size')
            return raw
    except urllib.error.HTTPError as exc:
        if exc.code==429:
            try:delay=max(60,float(exc.headers.get('Retry-After','3600')))
            except ValueError:delay=3600
            error=Limited('API rate limit; continue with cached replays');error.retry_after=delay;raise error from None
        raise SupplyUnavailable(f'HTTP {exc.code}; replay acquisition deferred') from None
    except (urllib.error.URLError,TimeoutError) as exc:
        raise SupplyUnavailable('Network unavailable; continue with cached replays') from None

def token():
    value=os.environ.get('BALLCHASING_TOKEN') or os.environ.get('BALLCHASING_API_KEY')
    return value.strip() if value else (BASE/'ballchasing_token.txt').read_text().strip() if (BASE/'ballchasing_token.txt').is_file() else None

def valid_api_url(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or p.hostname!='ballchasing.com' or p.port is not None or not p.path.startswith('/api/'):
        raise SupplyUnavailable('Invalid Ballchasing pagination URL')
    return url

def search_url(cfg):
    # Published API uses text ranks; website tiers 21/22 are checked in metadata.
    query={'playlist':'ranked-duels','min-rank':'grand-champion','count':100,
        'sort-by':'replay-date','sort-dir':'desc','replay-date-after':cfg['after']+'T00:00:00Z',
        'replay-date-before':cfg['before']+'T23:59:59Z'}
    return 'https://ballchasing.com/api/replays?'+urllib.parse.urlencode(query)

def elite_duel(meta,cfg):
    if meta.get('playlist_id') not in ('ranked-duels',10,'10'):return False
    ranks=[]
    labels={'grand-champion-3':21,'supersonic-legend':22}
    for team in ('blue','orange'):
        players=meta.get(team,{}).get('players',[])
        if len(players)!=1:return False
        rank=players[0].get('rank') or {};tier=rank.get('tier') if isinstance(rank,dict) else None
        if tier is None and isinstance(rank,dict):tier=labels.get(rank.get('id'))
        if tier is None:return False
        try:ranks.append(int(tier))
        except (ValueError,TypeError):return False
    return all(cfg['min_tier']<=r<=cfg['max_tier'] for r in ranks)

def replay_bytes(raw,cfg):
    limit=cfg['max_file_mb']*1024**2
    if raw[:2]==b'PK':
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            files=[i for i in archive.infolist() if i.filename.lower().endswith('.replay') and not i.is_dir()]
            if len(files)!=1 or files[0].file_size>limit:raise SupplyUnavailable('Expected one bounded replay file')
            raw=archive.read(files[0])
    if not raw or len(raw)>limit or raw.lstrip().lower().startswith((b'{',b'<html',b'<!doctype')):
        raise SupplyUnavailable('Response is not a bounded binary replay')
    return raw

def save(raw,path,cfg):
    raw=replay_bytes(raw,cfg);digest=hashlib.sha256(raw).hexdigest()
    if path.exists():
        if sha256(path)!=digest:raise SupplyUnavailable('Existing replay differs; preserve it')
        return path
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.partial');tmp.write_bytes(raw);tmp.replace(path)
    return path

def ballchasing(cfg,state,want,*,fetch=request,stop_file=None):
    secret=token()
    if not secret:raise SupplyUnavailable('Ballchasing token is not configured')
    headers={'Authorization':secret};now=time.time()
    events=[v for v in state.get('download_attempts',[]) if now-v<3600]
    state['download_attempts']=events
    if len(events)>=cfg['hour_limit']:raise Limited('Local hourly replay budget reached')
    pending=state.setdefault('pending',[]);files=[];pages=0
    while len(files)<want:
        check_pause(stop_file)
        if not pending:
            url=state.get('next_url',search_url(cfg))
            if not url:break
            valid_api_url(url);time.sleep(1.25)
            page=json.loads(fetch(url,headers,max_bytes=5*1024**2))
            state['next_url']=page.get('next');pending.extend(page.get('list',[]));pages+=1
            if not pending and (not state['next_url'] or pages>=5):break
        if not pending:continue
        meta=pending[0]
        try:rid=str(uuid.UUID(str(meta['id'])))
        except (ValueError,KeyError):pending.pop(0);continue
        destination=BASE/'downloads'/f'{rid}.replay'
        if destination.is_file():files.append(destination);pending.pop(0);continue
        if not elite_duel(meta,cfg):pending.pop(0);continue
        if len(events)>=cfg['hour_limit']:raise Limited('Local hourly replay budget reached')
        events.append(time.time());atomic_json(BASE/'provider_state.json',state)
        time.sleep(1.25)
        raw=fetch('https://ballchasing.com/api/replays/'+rid+'/file',headers,max_bytes=cfg['max_file_mb']*1024**2)
        files.append(save(raw,destination,cfg));pending.pop(0)
        atomic_json(destination.with_suffix('.source.json'),{'source':'ballchasing','id':rid,'sha256':sha256(destination),
            'rank_filter':'Both reported player ranks in GC3/SSL; not independent skill verification.'})
        if pages>=5 and not pending:break
    return files

def kaggle(cfg,state,want,*,fetch=request,stop_file=None,seen=()):
    files=[];local=Path(cfg['kaggle_local']) if cfg.get('kaggle_local') else None
    if local and local.is_dir():
        files.extend(p for p in sorted(local.rglob('*.replay')) if any(tag in str(p.relative_to(local)).lower() for tag in ('1v1','duel')) and sha256(p) not in seen)
        if len(files)>=want:return files[:want]
    headers={};user=os.environ.get('KAGGLE_USERNAME');key=os.environ.get('KAGGLE_KEY')
    if user and key:headers['Authorization']='Basic '+base64.b64encode((user+':'+key).encode()).decode()
    pending=state.setdefault('kaggle_pending',[])
    if not pending and not state.get('kaggle_exhausted'):
        url=KAGGLE+'list/'+DATASET+'?pageSize=100'
        if state.get('kaggle_page'):url+='&pageToken='+urllib.parse.quote(state['kaggle_page'],safe='')
        page=json.loads(fetch(url,headers,max_bytes=10*1024**2))
        pending.extend(page.get('datasetFiles',page.get('files',[])));state['kaggle_page']=page.get('nextPageToken')
        state['kaggle_exhausted']=not bool(state['kaggle_page'])
    while pending and len(files)<want:
        check_pause(stop_file)
        row=pending[0];name=row.get('name','');size=int(row.get('totalBytes',row.get('size',0)) or 0)
        if not name.lower().endswith('.replay') or not any(t in name.lower() for t in ('1v1','duel')) or size>cfg['max_file_mb']*1024**2:
            pending.pop(0);continue
        tag=hashlib.sha256(name.encode()).hexdigest()[:24];destination=BASE/'downloads'/('kaggle_'+tag+'.replay')
        if not destination.is_file():
            raw=fetch(KAGGLE+'download/'+DATASET+'/'+urllib.parse.quote(name,safe='/'),headers,
                max_bytes=cfg['max_file_mb']*1024**2)
            save(raw,destination,cfg)
            atomic_json(destination.with_suffix('.source.json'),{'source':'kaggle','dataset':DATASET,'file':name,
                'sha256':sha256(destination),'rank_filter':'Upstream curated duel data; exact GC3/SSL ranks not independently verified.'})
        files.append(destination);pending.pop(0)
    return files

def initial_seen(folder,inputs=ROOT/'data/replays/ranked-duels'):
    path=Path(folder)/'replay_seen.json'
    if not path.exists():
        manifest=read_json(ROOT/'data/isolated/ranked_duels_quality_dataset01/manifest.json',{})
        parsed={r['source_sha'] for r in manifest.get('sources',[]) if r.get('source','').endswith('.replay')}
        atomic_json(path,sorted(parsed or {sha256(p) for p in sorted(Path(inputs).rglob('*.replay'))[:500]}))

def batch(folder,index,*,cfg=None,inputs=ROOT/'data/replays/ranked-duels',stop_file=None):
    cfg={**DEFAULT,**(cfg if cfg is not None else read_json(CONFIG,{'enabled':False}))}
    if not cfg['enabled']:return None
    if not 16<=cfg['batch_size']<=200 or not 1<=cfg['hour_limit']<=180:raise ValueError('Invalid replay supply budget')
    for key in ('after','before'):datetime.date.fromisoformat(cfg[key])
    if not 1<=cfg['refresh_cycles']<=100 or not 1<=cfg['max_file_mb']<=30:raise ValueError('Invalid replay refresh or file cap')
    check_pause(stop_file)
    folder=Path(folder);out=folder/'replay_batches'/f'batch_{index:05d}'
    if (out/'batch.json').is_file():return read_json(out/'batch.json')
    if shutil.disk_usage(folder).free<cfg['min_disk_gb']*1024**3:return None
    with process_lock(BASE/'supply.lock'):
        seen=set(read_json(folder/'replay_seen.json',[]));selected=[];digests=set(seen)
        candidates=sorted(Path(inputs).rglob('*.replay'))+sorted((BASE/'downloads').glob('*.replay'))
        def add(paths):
            for p in paths:
                digest=sha256(p)
                if digest not in digests:selected.append((p,digest));digests.add(digest)
                if len(selected)>=cfg['batch_size']:break
        add(candidates)
        provider=read_json(BASE/'provider_state.json',{});notes=[]
        if len(selected)<cfg['batch_size'] and time.time()>=provider.get('cooldown_until',0):
            try:add(ballchasing(cfg,provider,cfg['batch_size']-len(selected),stop_file=stop_file))
            except SupplyUnavailable as exc:
                notes.append(str(exc));provider['cooldown_until']=time.time()+getattr(exc,'retry_after',3600)
                add(sorted((BASE/'downloads').glob('*.replay')))
        if len(selected)<cfg['batch_size'] and cfg['kaggle_fallback']:
            try:add(kaggle(cfg,provider,cfg['batch_size']-len(selected),stop_file=stop_file,seen=digests))
            except (SupplyUnavailable,ValueError,json.JSONDecodeError) as exc:notes.append('Kaggle acquisition deferred; cached training continues')
        atomic_json(BASE/'provider_state.json',provider)
        atomic_json(folder/'replay_supply_status.json',{'new_files':len(selected),'notes':notes,'using_cached_bank':len(selected)<16})
        if len(selected)<16:return None
        out.mkdir(parents=True,exist_ok=True);records=[]
        for p,digest in selected:
            target=out/(digest+'.replay')
            if not target.exists():shutil.copy2(p,target)
            records.append({'sha256':digest,'source':str(p),'file':str(target)})
        result={'inputs':str(out),'dataset':str(out/'prepared'),'bank':str(out/'bank.bin'),'files':records}
        atomic_json(out/'batch.json',result);atomic_json(folder/'replay_seen.json',sorted(seen|{r['sha256'] for r in records}))
        return result

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('configure','status'));a=p.parse_args()
    if a.command=='status':print(json.dumps(read_json(CONFIG,{'enabled':False}),indent=2));return
    secret=getpass.getpass('Ballchasing API token (hidden; blank keeps current token): ').strip()
    BASE.mkdir(parents=True,exist_ok=True)
    if secret:
        path=BASE/'ballchasing_token.txt';path.write_text(secret,encoding='utf8');path.chmod(0o600)
    atomic_json(CONFIG,DEFAULT)
    print('Configured optional GC3/SSL duel supply. Token stays in ignored local data. Quotas retain cached training.')

if __name__=='__main__':main()
