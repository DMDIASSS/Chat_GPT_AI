"""Bounded Ballchasing API download; strict metadata filtering of all players."""
from pathlib import Path
import getpass,hashlib,json,os,time,urllib.parse,urllib.request,urllib.error,uuid
from slater_v041_core import atomic_json,read_json,sha256

def valid_url(url):
    parts=urllib.parse.urlsplit(url)
    if parts.scheme!='https' or parts.hostname!='ballchasing.com' or parts.port or not parts.path.startswith('/api/'):
        raise ValueError('Unexpected API pagination URL')
    return url

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if urllib.parse.urlsplit(newurl).scheme!='https':raise ValueError('Non-HTTPS download redirect')
        new=super().redirect_request(req,fp,code,msg,headers,newurl)
        if urllib.parse.urlsplit(newurl).hostname!=urllib.parse.urlsplit(req.full_url).hostname:new.remove_header('Authorization')
        return new

def eligible(meta,playlist='ranked-doubles'):
    size=2 if playlist=='ranked-doubles' else 1
    if meta.get('playlist_id') not in (playlist,11 if size==2 else 10,str(11 if size==2 else 10)):return False
    ranks=[]
    for team in ('blue','orange'):
        players=meta.get(team,{}).get('players',[])
        if len(players)!=size:return False
        for player in players:
            rank=player.get('rank') or {};tier=rank.get('tier')
            if tier is None:tier={'grand-champion-3':21,'supersonic-legend':22}.get(rank.get('id'))
            if tier not in (21,22):return False
            ranks.append(tier)
    return len(ranks)==size*2

def download(folder,*,count=100,playlist='ranked-doubles',prompt=True,fetch=None):
    if not 1<=count<=3000 or playlist not in ('ranked-duels','ranked-doubles'):raise ValueError('Invalid download budget')
    secret=os.environ.get('BALLCHASING_TOKEN') or os.environ.get('BALLCHASING_API_KEY')
    if not secret and prompt:secret=getpass.getpass('Ballchasing API token (local hidden input; get it at ballchasing.com/upload): ').strip()
    if not secret:raise ValueError('Ballchasing API login is required for downloading. Existing local replays can train without it.')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);statefile=folder/'.imitation_download.json'
    query={'playlist':playlist,'min-rank':'grand-champion','count':100,'sort-by':'replay-date','sort-dir':'desc'}
    start='https://ballchasing.com/api/replays?'+urllib.parse.urlencode(query)
    state=read_json(statefile,{'url':start,'pending':[],'attempts':[]})
    opener=urllib.request.build_opener(Redirect());last=0.
    def request(url,binary=False):
        nonlocal last
        valid_url(url);time.sleep(max(0,1.25-(time.monotonic()-last)));last=time.monotonic()
        req=urllib.request.Request(url,headers={'Authorization':secret,'User-Agent':'Replay-Imitation/1.0'})
        try:
            with opener.open(req,timeout=30) as response:raw=response.read(30*1024**2+1)
        except urllib.error.HTTPError as error:
            raise RuntimeError('Ballchasing HTTP '+str(error.code)+'. Keep cached files; retry after the API cooldown if rate limited.') from None
        if len(raw)>30*1024**2:raise ValueError('Oversized replay response')
        return raw if binary else json.loads(raw)
    fetch=fetch or request;added=0;pages=0;rejected=0
    while added<count:
        state['attempts']=[t for t in state['attempts'] if time.time()-t<3600]
        if len(state['attempts'])>=180:print('Local hourly download budget reached. Resume later.',flush=True);break
        if not state['pending']:
            if not state['url'] or pages>=20:break
            page=fetch(valid_url(state['url']));pages+=1
            state['url']=valid_url(page['next']) if page.get('next') else None
            state['pending']=[m for m in page.get('list',[]) if eligible(m,playlist)]
            rejected+=len(page.get('list',[]))-len(state['pending']);atomic_json(statefile,state)
            if not state['pending']:continue
        meta=state['pending'][0];rid=str(uuid.UUID(meta['id']));target=folder/(rid+'.replay')
        if target.exists():state['pending'].pop(0);atomic_json(statefile,state);continue
        state['attempts'].append(time.time());atomic_json(statefile,state)
        raw=fetch('https://ballchasing.com/api/replays/'+rid+'/file',True)
        if not raw or raw.lstrip().startswith((b'{',b'<')):raise ValueError('API returned text rather than replay data')
        tmp=target.with_suffix('.partial');tmp.write_bytes(raw);tmp.replace(target)
        atomic_json(target.with_suffix('.source.json'),{'source':'ballchasing','playlist':playlist,'all_player_tiers':[p['rank'] for t in ('blue','orange') for p in meta[t]['players']],
            'rank_filter':'all players verified from API metadata as GC3 or SSL','sha256':sha256(target)})
        state['pending'].pop(0);atomic_json(statefile,state);added+=1;print('REPLAY_DOWNLOAD',added,'/',count,rid,flush=True)
    return {'downloaded':added,'metadata_rejected':rejected,'folder':str(folder),'playlist':playlist,'filter':'GC3–SSL, all players'}
