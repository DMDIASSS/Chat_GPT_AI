"""Strict GC3–SSL replay collection with local credentials and resumable cooldowns."""
from pathlib import Path
import argparse,getpass,hashlib,json,math,os,sys,time,urllib.parse,urllib.request,urllib.error,uuid
from email.utils import parsedate_to_datetime
from slater_v041_core import atomic_json,read_json,sha256,process_lock

ROOT=Path(__file__).resolve().parent
TOKEN_FILE=ROOT/'data/isolated/native_replay_supply/ballchasing_token.txt'
DEFAULT_FOLDER=ROOT/'data/replays/ranked-doubles'
HOUR_LIMIT=180
SOURCE_PAGE='https://ballchasing.com/?playlist=11&min-rank=21&max-rank=22'

class DownloadError(RuntimeError):
    def __init__(self,message,*,retry_after=None,status=None):
        super().__init__(message);self.retry_after=retry_after;self.status=status

class BudgetWait(DownloadError):pass

def replay_id(value):
    try:return str(uuid.UUID(str(value)))
    except (ValueError,AttributeError,TypeError):return None

class ReplayIndex:
    """Incremental local file catalog; never overwrite, move or delete a replay."""
    def __init__(self,folder,roots):
        self.path=folder/'.replay_index.json';self.files={};self.ids={};self.hashes={}
        self.hashed=self.reused=self.unreadable=0
        try:saved=read_json(self.path,{}).get('files',{})
        except (ValueError,AttributeError):saved={}
        if not isinstance(saved,dict):saved={}
        seen=set()
        for root in dict.fromkeys([folder,*map(Path,roots)]):
            if not root.is_dir():continue
            for item in root.rglob('*.replay'):
                try:
                    path=item.resolve();key=str(path)
                    if key in seen:continue
                    seen.add(key);signature=self.signature(path)
                    if signature[0]<=0:continue
                    old=saved.get(key,{})
                    if not isinstance(old,dict):old={}
                    cached=old.get('signature')==signature and isinstance(old.get('sha256'),str) and len(old['sha256'])==64
                    digest=old['sha256'] if cached else sha256(path)
                    self.reused+=int(cached);self.hashed+=int(not cached)
                    ids={replay_id(path.stem)}
                    try:
                        meta=read_json(path.with_suffix('.source.json'),{})
                        if isinstance(meta,dict) and meta.get('source')=='ballchasing':ids.add(replay_id(meta.get('id')))
                    except (ValueError,OSError):pass
                    if cached and isinstance(old.get('aliases'),list):ids.update(replay_id(value) for value in old['aliases'])
                    self.record(path,digest,ids,signature)
                except OSError:self.unreadable+=1
        self.save()
        print('LOCAL INDEX:',len(self.files),'files |',self.reused,'cached hashes |',self.hashed,'new hashes',flush=True)

    @staticmethod
    def signature(path):
        stat=path.stat();return [stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns]

    def record(self,path,digest,ids,signature=None):
        path=path.resolve();key=str(path);ids=sorted(i for i in ids if i)
        self.files[key]={'signature':signature or self.signature(path),'sha256':digest,'aliases':ids}
        for rid in ids:self.ids[rid]=path
        self.hashes[digest]=path

    def find_id(self,rid):
        path=self.ids.get(rid)
        try:return path if path and self.signature(path)==self.files[str(path)]['signature'] else None
        except OSError:return None

    def find_hash(self,digest):
        path=self.hashes.get(digest)
        try:
            if not path:return None
            if self.signature(path)!=self.files[str(path)]['signature']:
                self.hashes.pop(digest,None);actual=sha256(path)
                self.record(path,actual,{replay_id(path.stem)})
                return path if actual==digest else None
            return path
        except OSError:return None

    def alias(self,rid,path):
        entry=self.files[str(path)];self.record(path,entry['sha256'],set(entry['aliases'])|{rid},entry['signature']);self.save()

    def save(self):atomic_json(self.path,{'schema':1,'files':self.files})

def search_url(playlist,mode,page_size):
    query={'playlist':playlist,'min-rank':'grand-champion-3' if mode=='exact' else 'grand-champion',
           'count':page_size,'sort-by':'replay-date','sort-dir':'desc'}
    # SSL is the current top tier. Keep the maximum (22) as an explicit
    # per-player metadata check instead of assuming extra API rank parameters.
    return 'https://ballchasing.com/api/replays?'+urllib.parse.urlencode(query)

def valid_url(url):
    parts=urllib.parse.urlsplit(url)
    if (parts.scheme!='https' or parts.hostname!='ballchasing.com' or parts.port is not None
            or parts.username or parts.password or parts.fragment or not parts.path.startswith('/api/')):
        raise ValueError('Unexpected API pagination URL')
    return url

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if urllib.parse.urlsplit(newurl).scheme!='https':raise ValueError('Non-HTTPS download redirect')
        new=super().redirect_request(req,fp,code,msg,headers,newurl)
        if urllib.parse.urlsplit(newurl).hostname!=urllib.parse.urlsplit(req.full_url).hostname:new.remove_header('Authorization')
        return new

def eligible(meta,playlist='ranked-doubles'):
    if not isinstance(meta,dict):return False
    size=2 if playlist=='ranked-doubles' else 1
    if meta.get('playlist_id') not in (playlist,11 if size==2 else 10,str(11 if size==2 else 10)):return False
    for team in ('blue','orange'):
        group=meta.get(team);players=group.get('players') if isinstance(group,dict) else None
        if not isinstance(players,list) or len(players)!=size:return False
        for player in players:
            rank=player.get('rank') if isinstance(player,dict) else None
            if not isinstance(rank,dict):return False
            tier=rank.get('tier')
            if tier is None and isinstance(rank.get('id'),str):tier={'grand-champion-3':21,'grand-champion-iii':21,'supersonic-legend':22}.get(rank['id'])
            if isinstance(tier,str) and tier.isdecimal():tier=int(tier)
            if isinstance(tier,bool) or tier not in (21,22):return False
    return True

def credentials(*,prompt=True,save=False,replace=False):
    if not replace:
        for key in ('BALLCHASING_TOKEN','BALLCHASING_API_KEY'):
            value=os.environ.get(key,'').strip()
            if value:return value
        if TOKEN_FILE.is_file():
            value=TOKEN_FILE.read_text(encoding='utf-8-sig').strip()
            if value:return value
    if not prompt:raise ValueError('Ballchasing token missing. Run CONFIGURE_BALLCHASING_TOKEN.bat on your PC.')
    value=getpass.getpass('Paste Ballchasing API token (hidden; Enter submits): ').strip()
    if not value:raise ValueError('No token entered. Get your API token at https://ballchasing.com/upload')
    if save:
        TOKEN_FILE.parent.mkdir(parents=True,exist_ok=True)
        with os.fdopen(os.open(TOKEN_FILE,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w',encoding='utf8') as stream:stream.write(value)
        TOKEN_FILE.chmod(0o600)
        print('Token saved locally in ignored project data, separate from logs and download state.',flush=True)
    return value

def cooldown(value,default=3600):
    try:seconds=float(value)
    except (ValueError,TypeError):
        try:seconds=parsedate_to_datetime(value).timestamp()-time.time()
        except (TypeError,ValueError,OverflowError):seconds=default
    return max(1.,seconds) if math.isfinite(seconds) else float(default)

def replay_bytes(raw):
    """Reject actual API error documents without mistaking a binary header for one.

    Rocket League starts with a little-endian header length. Its first byte
    can legitimately be '{' or '<'; inspecting just that byte rejects replays.
    """
    if not isinstance(raw,bytes) or not raw:raise ValueError('API returned no replay data')
    try:text=raw.decode('utf-8-sig').strip()
    except UnicodeError:return raw
    if text.startswith(('{','[')):
        try:document=json.loads(text)
        except ValueError:pass
        else:
            if isinstance(document,(dict,list)):raise ValueError('API returned JSON instead of replay data')
    if '\x00' not in text and text.lower().startswith(('<!doctype html','<html','<?xml')):
        raise ValueError('API returned HTML/XML instead of replay data')
    return raw


def http_fetch(secret,*,opener=None):
    opener=opener or urllib.request.build_opener(Redirect())
    def fetch(url,binary=False):
        req=urllib.request.Request(valid_url(url),headers={'Authorization':secret,'User-Agent':'Replay-Imitation/2.0'})
        try:
            with opener.open(req,timeout=30) as response:raw=response.read(30*1024**2+1)
        except urllib.error.HTTPError as error:
            if error.code==429:raise DownloadError('Ballchasing API rate limit.',retry_after=cooldown(error.headers.get('Retry-After')),status=429) from None
            if error.code in (500,502,503,504):raise DownloadError('Ballchasing service temporarily unavailable.',retry_after=30,status=error.code) from None
            if error.code in (401,403):raise DownloadError('Ballchasing rejected the token/access. Run CONFIGURE_BALLCHASING_TOKEN.bat to replace it.',status=error.code) from None
            raise DownloadError('Ballchasing HTTP '+str(error.code)+'.',status=error.code) from None
        except (urllib.error.URLError,TimeoutError,OSError):raise DownloadError('Ballchasing connection interrupted.',retry_after=30) from None
        if len(raw)>30*1024**2:raise ValueError('Oversized replay response')
        if binary:return replay_bytes(raw)
        try:return json.loads(raw)
        except (ValueError,UnicodeError):raise DownloadError('Ballchasing returned an invalid listing.',retry_after=30) from None
    return fetch

def download(folder,*,count=100,playlist='ranked-doubles',prompt=True,fetch=None,automatic=False,save_token=False,max_pages=None,
             existing_roots=None,page_size=200,refresh_search=False):
    if type(count) is not int or not 0<=count<=3000 or playlist not in ('ranked-duels','ranked-doubles'):raise ValueError('Invalid download budget')
    if page_size not in (100,200):raise ValueError('Page size must be 100 or 200')
    secret=credentials(prompt=prompt,save=save_token)
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    with process_lock(folder/'.download.lock'):
        roots=existing_roots if existing_roots is not None else [ROOT/'data/replays',ROOT/'data/isolated/native_replay_supply/downloads']
        print('Indexing existing replays (unchanged files reuse cached hashes)...',flush=True)
        index=ReplayIndex(folder,roots)
        return _download(folder,count,playlist,fetch or http_fetch(secret),automatic,max_pages,index,page_size,refresh_search)

def _download(folder,count,playlist,fetch,automatic,max_pages,index,page_size,refresh_search):
    statefile=folder/'.imitation_download.json';stop_file=folder/'.download_pause'
    stop_file.unlink(missing_ok=True)
    start=search_url(playlist,'exact',page_size)
    state=read_json(statefile,{'url':start,'pending':[],'attempts':[]})
    if state.get('playlist',playlist)!=playlist:raise ValueError('This folder contains another playlist. Choose a separate output folder.')
    state['playlist']=playlist;state.setdefault('requests',state.get('attempts',[]).copy())
    # Preserve old budget history conservatively through the first upgraded hour.
    state.setdefault('download_attempts',state['requests'].copy())
    if state.get('search_version')!=2 or refresh_search:
        state.update(search_version=2,url=start,search_mode='exact',page_size=page_size,query_verified=False)
        if refresh_search:state['pending']=[]
    added=pages=rejected=unavailable=failures=skipped_id=skipped_content=0;last=-math.inf;status='RUNNING';visited=set()
    if state['requests']:last=time.monotonic()-max(0.,time.time()-max(state['requests']))
    max_pages=max_pages if max_pages is not None else (0 if count==0 else 1000 if automatic else 20)
    if type(max_pages) is not int or not 0<=max_pages<=10000:raise ValueError('Invalid search page budget')
    print('GC3-SSL',playlist,'| target:',count or 'ALL PAGES','new replays |',folder,flush=True)
    origin=SOURCE_PAGE if playlist=='ranked-doubles' else SOURCE_PAGE.replace('playlist=11','playlist=10')
    print('Source filter:',origin,'| API pagination; narrow filters probed with a verified-rank fallback.',flush=True)
    print('All four doubles players need GC3/SSL metadata. Ctrl+C / PAUSE stops; rerun resumes.',flush=True)
    def progress(label,delay=0):
        atomic_json(folder/'download_status.json',{'status':label,'downloaded_this_launch':added,'target':count or None,
            'pages_this_launch':pages,'metadata_rejected':rejected,'unavailable':unavailable,
            'skipped_existing':skipped_id,'skipped_identical_content':skipped_content,
            'indexed_files':len(index.files),'source_page':origin,'search_mode':state['search_mode'],
            'page_size':state['page_size'],'local_download_hour_limit':HOUR_LIMIT,
            'retry_at_unix':time.time()+delay if delay else None,'playlist':playlist})
    def wait(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            if stop_file.exists():return False
            time.sleep(min(1.,max(0.,until-time.monotonic())))
        return True
    def request(url,binary=False):
        nonlocal last
        valid_url(url)
        state['requests']=[t for t in state['requests'] if time.time()-t<3600]
        state['download_attempts']=[t for t in state['download_attempts'] if time.time()-t<3600]
        if binary and len(state['download_attempts'])>=HOUR_LIMIT:raise BudgetWait('Local hourly download budget reached.',retry_after=max(1.,min(state['download_attempts'])+3601-time.time()))
        if not wait(max(0.,1.25-(time.monotonic()-last))):return None
        last=time.monotonic();state['requests'].append(time.time())
        if binary:state['download_attempts'].append(time.time())
        atomic_json(statefile,state)
        return fetch(url,binary)
    progress('RUNNING')
    while count==0 or added<count:
        if stop_file.exists():status='PAUSED';break
        try:
            if not state['pending']:
                if not state['url']:status='COMPLETE' if count==0 else 'SEARCH_EXHAUSTED';break
                if max_pages and pages>=max_pages:status='PAGE_BUDGET_REACHED';break
                if state['url'] in visited:raise DownloadError('API repeated a pagination cursor. Completed files are preserved.')
                page=request(state['url'])
                if page is None:status='PAUSED';break
                if not isinstance(page,dict) or not isinstance(page.get('list'),list):raise ValueError('Invalid Ballchasing listing schema')
                visited.add(state['url'])
                pages+=1;state['query_verified']=True;state['url']=valid_url(page['next']) if page.get('next') else None
                state['pending']=[];page_ids=set()
                for meta in page['list']:
                    rid=replay_id(meta.get('id')) if isinstance(meta,dict) else None
                    if not rid or not eligible(meta,playlist):rejected+=1;continue
                    if rid in page_ids or index.find_id(rid):skipped_id+=1;continue
                    page_ids.add(rid);state['pending'].append(meta)
                atomic_json(statefile,state);progress('RUNNING')
                print('SEARCH page',pages,'| new eligible',len(state['pending']),'| existing skipped',skipped_id,'| rejected',rejected,flush=True)
                failures=0;continue
            meta=state['pending'][0]
            try:rid=str(uuid.UUID(str(meta['id'])))
            except (ValueError,KeyError,TypeError):state['pending'].pop(0);rejected+=1;atomic_json(statefile,state);continue
            if not eligible(meta,playlist):state['pending'].pop(0);rejected+=1;atomic_json(statefile,state);continue
            target=folder/(rid+'.replay')
            if index.find_id(rid):
                skipped_id+=1;state['pending'].pop(0);atomic_json(statefile,state);continue
            raw=request('https://ballchasing.com/api/replays/'+rid+'/file',True)
            if raw is None:status='PAUSED';break
            replay_bytes(raw)
            digest=hashlib.sha256(raw).hexdigest();same=index.find_hash(digest)
            if same:
                index.alias(rid,same);skipped_content+=1;state['pending'].pop(0);atomic_json(statefile,state);progress('RUNNING')
                print('SKIP identical replay content:',rid,flush=True);continue
            if target.is_file() and target.stat().st_size>0:
                index.record(target,sha256(target),{rid});index.save();skipped_id+=1
                state['pending'].pop(0);atomic_json(statefile,state);continue
            tmp=target.with_suffix('.partial');tmp.write_bytes(raw)
            atomic_json(target.with_suffix('.source.json'),{'source':'ballchasing','playlist':playlist,'id':rid,
                'all_player_tiers':[p['rank'] for t in ('blue','orange') for p in meta[t]['players']],
                'rank_filter':'all players verified from API metadata as GC3 or SSL','sha256':digest,'discovered_from':origin})
            tmp.replace(target);index.record(target,digest,{rid});index.save();state['pending'].pop(0);atomic_json(statefile,state)
            added+=1;failures=0;progress('RUNNING');print('REPLAY_DOWNLOAD',added,'/',count or 'all pages',rid,flush=True)
        except DownloadError as error:
            if error.status==400 and not state['pending'] and not state['query_verified']:
                if state['search_mode']=='exact' and state['page_size']==200:state['page_size']=100
                elif state['search_mode']=='exact':state['search_mode']='broad';state['page_size']=page_size
                elif state['page_size']==200:state['page_size']=100
                else:progress('STOPPED');raise
                state['url']=search_url(playlist,state['search_mode'],state['page_size']);atomic_json(statefile,state)
                print('API rejected search settings; trying',state['search_mode'],'rank search,',state['page_size'],'items/page. All-player rank checks remain active.',flush=True)
                continue
            if error.status in (404,410) and state['pending']:
                state['pending'].pop(0);unavailable+=1;atomic_json(statefile,state);continue
            if error.retry_after is None:progress('STOPPED');raise
            failures=0 if error.status==429 or isinstance(error,BudgetWait) else failures+1
            delay=max(error.retry_after,min(900,30*2**max(0,failures-1)))
            if not automatic or failures>=6:
                status='RETRY_LATER';progress(status,delay);print(str(error),'Rerun to resume.',flush=True);break
            progress('WAITING_FOR_API',delay)
            print(str(error),'Automatically resuming in',round(delay),'seconds. Ctrl+C / PAUSE stops.',flush=True)
            if not wait(delay):status='PAUSED';break
    else:status='COMPLETE'
    if status!='RETRY_LATER':progress(status)
    return {'status':status,'downloaded':added,'metadata_rejected':rejected,'folder':str(folder),
            'playlist':playlist,'filter':'GC3-SSL, all players','pages':pages,
            'skipped_existing':skipped_id,'skipped_identical_content':skipped_content}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('auto','once','configure','pause','status'),nargs='?',default='auto')
    p.add_argument('--count',type=int,default=1000,help='Maximum new unique replays this launch (1..3000; 0 = all pages)')
    p.add_argument('--folder',type=Path,default=DEFAULT_FOLDER);p.add_argument('--max-pages',type=int)
    p.add_argument('--all-pages',action='store_true',help='Follow API pages until exhausted; no local file/page count limit')
    p.add_argument('--page-size',type=int,choices=(100,200),default=200)
    p.add_argument('--existing',type=Path,action='append',default=[],help='Also skip replay IDs/content in this folder (repeatable)')
    p.add_argument('--refresh-search',action='store_true',help='Restart from the newest page; keep existing files and deduplication index')
    a=p.parse_args(argv)
    if a.command=='configure':credentials(prompt=True,save=True,replace=True);return
    if a.command=='pause':
        a.folder.mkdir(parents=True,exist_ok=True);(a.folder/'.download_pause').touch();print('Download pause requested.');return
    if a.command=='status':print(json.dumps(read_json(a.folder/'download_status.json',{'status':'NOT_STARTED'}),indent=2));return
    roots=[ROOT/'data/replays',ROOT/'data/isolated/native_replay_supply/downloads',*a.existing]
    print(json.dumps(download(a.folder,count=0 if a.all_pages else a.count,automatic=a.command=='auto',save_token=True,
        max_pages=a.max_pages if a.max_pages is not None else 0 if a.all_pages else None,
        existing_roots=roots,page_size=a.page_size,refresh_search=a.refresh_search),indent=2))

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:print('\nStopped. Completed downloads and pagination are saved. Rerun to resume.');sys.exit(130)
    except (ValueError,RuntimeError,OSError,EOFError) as error:print('STOPPED:',error);sys.exit(1)
