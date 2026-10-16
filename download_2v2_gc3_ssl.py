"""Strict GC3–SSL replay collection with local credentials and resumable cooldowns."""
from pathlib import Path
import argparse,getpass,json,math,os,sys,time,urllib.parse,urllib.request,urllib.error,uuid
from email.utils import parsedate_to_datetime
from slater_v041_core import atomic_json,read_json,sha256,process_lock

ROOT=Path(__file__).resolve().parent
TOKEN_FILE=ROOT/'data/isolated/native_replay_supply/ballchasing_token.txt'
DEFAULT_FOLDER=ROOT/'data/replays/ranked-doubles'
HOUR_LIMIT=180

class DownloadError(RuntimeError):
    def __init__(self,message,*,retry_after=None,status=None):
        super().__init__(message);self.retry_after=retry_after;self.status=status

class BudgetWait(DownloadError):pass

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
        if binary:return raw
        try:return json.loads(raw)
        except (ValueError,UnicodeError):raise DownloadError('Ballchasing returned an invalid listing.',retry_after=30) from None
    return fetch

def download(folder,*,count=100,playlist='ranked-doubles',prompt=True,fetch=None,automatic=False,save_token=False,max_pages=None):
    if type(count) is not int or not 1<=count<=3000 or playlist not in ('ranked-duels','ranked-doubles'):raise ValueError('Invalid download budget')
    secret=credentials(prompt=prompt,save=save_token)
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    with process_lock(folder/'.download.lock'):
        return _download(folder,count,playlist,fetch or http_fetch(secret),automatic,max_pages)

def _download(folder,count,playlist,fetch,automatic,max_pages):
    statefile=folder/'.imitation_download.json';stop_file=folder/'.download_pause'
    stop_file.unlink(missing_ok=True)
    query={'playlist':playlist,'min-rank':'grand-champion','count':100,'sort-by':'replay-date','sort-dir':'desc'}
    start='https://ballchasing.com/api/replays?'+urllib.parse.urlencode(query)
    state=read_json(statefile,{'url':start,'pending':[],'attempts':[]})
    if state.get('playlist',playlist)!=playlist:raise ValueError('This folder contains another playlist. Choose a separate output folder.')
    state['playlist']=playlist;state.setdefault('requests',state.get('attempts',[]).copy())
    added=pages=rejected=unavailable=failures=0;last=-math.inf;status='RUNNING'
    max_pages=max_pages if max_pages is not None else (1000 if automatic else 20)
    if type(max_pages) is not int or not 1<=max_pages<=10000:raise ValueError('Invalid search page budget')
    print('GC3-SSL',playlist,'| target:',count,'new replays |',folder,flush=True)
    print('All four doubles players need GC3/SSL metadata. Ctrl+C / PAUSE stops; rerun resumes.',flush=True)
    def progress(label,delay=0):
        atomic_json(folder/'download_status.json',{'status':label,'downloaded_this_launch':added,'target':count,
            'pages_this_launch':pages,'metadata_rejected':rejected,'unavailable':unavailable,
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
        if len(state['requests'])>=HOUR_LIMIT:raise BudgetWait('Local hourly API budget reached.',retry_after=max(1.,min(state['requests'])+3601-time.time()))
        if not wait(max(0.,1.25-(time.monotonic()-last))):return None
        last=time.monotonic();state['requests'].append(time.time());atomic_json(statefile,state)
        return fetch(url,binary)
    progress('RUNNING')
    while added<count:
        if stop_file.exists():status='PAUSED';break
        try:
            if not state['pending']:
                if not state['url']:status='SEARCH_EXHAUSTED';break
                if pages>=max_pages:status='PAGE_BUDGET_REACHED';break
                page=request(state['url'])
                if page is None:status='PAUSED';break
                if not isinstance(page,dict) or not isinstance(page.get('list'),list):raise ValueError('Invalid Ballchasing listing schema')
                pages+=1;state['url']=valid_url(page['next']) if page.get('next') else None
                state['pending']=[m for m in page['list'] if eligible(m,playlist)]
                rejected+=len(page['list'])-len(state['pending']);atomic_json(statefile,state)
                print('SEARCH page',pages,'| eligible',len(state['pending']),'| rejected',rejected,flush=True)
                failures=0;continue
            meta=state['pending'][0]
            try:rid=str(uuid.UUID(str(meta['id'])))
            except (ValueError,KeyError,TypeError):state['pending'].pop(0);rejected+=1;atomic_json(statefile,state);continue
            if not eligible(meta,playlist):state['pending'].pop(0);rejected+=1;atomic_json(statefile,state);continue
            target=folder/(rid+'.replay')
            if target.exists():state['pending'].pop(0);atomic_json(statefile,state);continue
            raw=request('https://ballchasing.com/api/replays/'+rid+'/file',True)
            if raw is None:status='PAUSED';break
            if not isinstance(raw,bytes) or not raw or raw.lstrip().startswith((b'{',b'<')):raise ValueError('API returned text rather than replay data')
            tmp=target.with_suffix('.partial');tmp.write_bytes(raw)
            atomic_json(target.with_suffix('.source.json'),{'source':'ballchasing','playlist':playlist,'id':rid,
                'all_player_tiers':[p['rank'] for t in ('blue','orange') for p in meta[t]['players']],
                'rank_filter':'all players verified from API metadata as GC3 or SSL','sha256':sha256(tmp)})
            tmp.replace(target);state['pending'].pop(0);atomic_json(statefile,state)
            added+=1;failures=0;progress('RUNNING');print('REPLAY_DOWNLOAD',added,'/',count,rid,flush=True)
        except DownloadError as error:
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
            'playlist':playlist,'filter':'GC3-SSL, all players','pages':pages}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('auto','once','configure','pause','status'),nargs='?',default='auto')
    p.add_argument('--count',type=int,default=1000,help='Maximum new replays this launch (1..3000)')
    p.add_argument('--folder',type=Path,default=DEFAULT_FOLDER);p.add_argument('--max-pages',type=int)
    a=p.parse_args(argv)
    if a.command=='configure':credentials(prompt=True,save=True,replace=True);return
    if a.command=='pause':
        a.folder.mkdir(parents=True,exist_ok=True);(a.folder/'.download_pause').touch();print('Download pause requested.');return
    if a.command=='status':print(json.dumps(read_json(a.folder/'download_status.json',{'status':'NOT_STARTED'}),indent=2));return
    print(json.dumps(download(a.folder,count=a.count,automatic=a.command=='auto',save_token=True,max_pages=a.max_pages),indent=2))

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:print('\nStopped. Completed downloads and pagination are saved. Rerun to resume.');sys.exit(130)
    except (ValueError,RuntimeError,OSError,EOFError) as error:print('STOPPED:',error);sys.exit(1)
