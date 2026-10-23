"""Resumable acquisition of the user's curated 3v3 Ballchasing group."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import time
import urllib.parse
from download_2v2_gc3_ssl import credentials,http_fetch,valid_url,replay_id,ReplayIndex,DownloadError,HOUR_LIMIT,replay_bytes
from slater_v041_core import atomic_json,read_json,process_lock

ROOT=Path(__file__).resolve().parent
DEFAULT_GROUP='ranked-3v3-2026-10-15-lwizwie17f'


def group_id(value):
    if '://' in value:
        parts=urllib.parse.urlsplit(value)
        if (parts.scheme!='https' or parts.netloc!='ballchasing.com' or parts.query or parts.fragment
                or not parts.path.startswith('/group/')):raise ValueError('Expected a Ballchasing HTTPS group URL')
        value=parts.path[len('/group/'):].rstrip('/')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,140}',value):raise ValueError('Invalid Ballchasing group ID')
    return value


def eligible(meta):
    if not isinstance(meta,dict) or meta.get('playlist_id') not in ('ranked-standard',13,'13'):return False
    for team in ('blue','orange'):
        info=meta.get(team)
        if not isinstance(info,dict):return False
        players=info.get('players',[])
        if not isinstance(players,list) or len(players)!=3 or any(not isinstance(p,dict) for p in players):return False
    return replay_id(meta.get('id')) is not None


def listing_url(group,url=None):
    if url:
        parts=urllib.parse.urlsplit(valid_url(url))
        if parts.path!='/api/replays':raise ValueError('Unexpected group pagination endpoint')
        query=dict(urllib.parse.parse_qsl(parts.query))
        if query.get('group',group)!=group:raise ValueError('Pagination left the requested group')
    else:query={'count':'200','sort-by':'replay-date','sort-dir':'desc'}
    query['group']=group
    return 'https://ballchasing.com/api/replays?'+urllib.parse.urlencode(query)


def download(group=DEFAULT_GROUP,*,folder=None,count=0,fetch=None,refresh=False,
             existing_roots=None,min_interval=1.25,now=time.time,sleep=time.sleep):
    group=group_id(group)
    if type(count) is not int or not 0<=count<=100000:raise ValueError('Count must be 0 (all) or 1..100000')
    folder=Path(folder) if folder is not None else ROOT/'data/replays/ranked-standard'/group
    folder.mkdir(parents=True,exist_ok=True)
    if fetch is None:fetch=http_fetch(credentials(prompt=True,save=True))
    statefile=folder/'.group_download.json';pause=folder/'.download_pause'
    with process_lock(folder/'.download.lock'):
        state=read_json(statefile,{'group':group,'url':listing_url(group),'pending':[],'downloads':[]})
        if state.get('group')!=group:raise ValueError('Folder belongs to another replay group')
        if state.get('retry_at',0)>now():
            report={'status':'RETRY_LATER','group':group,'folder':str(folder),'downloaded':0,
                    'retry_at_unix':state['retry_at'],'note':'Saved API cooldown is still active; no request sent.'}
            atomic_json(folder/'group_download_status.json',report)
            print('API cooldown active for',round(state['retry_at']-now()),'more seconds.',flush=True)
            return report
        if refresh:state.update(url=listing_url(group),pending=[])
        pause.unlink(missing_ok=True)
        index=ReplayIndex(folder,existing_roots if existing_roots is not None else [ROOT/'data/replays'])
        added=skipped=rejected=pages=0;status='RUNNING';retry_at=None;visited=set()
        def save():atomic_json(statefile,state)
        def request(url,binary=False):
            recent=[t for t in state['downloads'] if now()-t<3600];state['downloads']=recent
            if binary and len(recent)>=HOUR_LIMIT:
                raise DownloadError('Local hourly file budget reached.',retry_after=max(1.,min(recent)+3601-now()))
            delay=max(0.,min_interval-(now()-state.get('last_request',0)))
            if delay:sleep(delay)
            if pause.exists():raise KeyboardInterrupt
            state['last_request']=now()
            if binary:state['downloads'].append(now())
            save();return fetch(url,binary)
        try:
            while not count or added<count:
                if pause.exists():status='PAUSED';break
                if not state['pending']:
                    if not state['url']:status='COMPLETE';break
                    url=listing_url(group,state['url'])
                    if url in visited:raise ValueError('API repeated a pagination cursor')
                    try:page=request(url)
                    except DownloadError as error:
                        parts=urllib.parse.urlsplit(url);query=dict(urllib.parse.parse_qsl(parts.query))
                        if error.status==400 and query.get('count')=='200':
                            query['count']='100'
                            state['url']=listing_url(group,'https://ballchasing.com/api/replays?'+urllib.parse.urlencode(query))
                            save();continue
                        raise
                    if not isinstance(page,dict) or not isinstance(page.get('list'),list):raise ValueError('Invalid API replay listing')
                    visited.add(url);pages+=1
                    state['url']=listing_url(group,page['next']) if page.get('next') else None
                    state['pending']=[];seen=set()
                    for meta in page['list']:
                        if not eligible(meta):rejected+=1;continue
                        rid=replay_id(meta['id'])
                        if rid in seen or index.find_id(rid):skipped+=1;continue
                        seen.add(rid);state['pending'].append(meta)
                    save();print('GROUP PAGE',pages,'| queued',len(state['pending']),'| skipped',skipped,'| rejected',rejected,flush=True)
                    continue
                meta=state['pending'][0];rid=replay_id(meta.get('id'))
                if not eligible(meta):rejected+=1;state['pending'].pop(0);save();continue
                if index.find_id(rid):skipped+=1;state['pending'].pop(0);save();continue
                try:raw=request('https://ballchasing.com/api/replays/'+rid+'/file',True)
                except DownloadError as error:
                    if error.status in (404,410):rejected+=1;state['pending'].pop(0);save();continue
                    raise
                replay_bytes(raw)
                digest=hashlib.sha256(raw).hexdigest();same=index.find_hash(digest)
                if same:index.alias(rid,same);skipped+=1
                else:
                    target=folder/(rid+'.replay')
                    if target.exists():raise ValueError('Existing replay was not indexed; refusing to overwrite it')
                    partial=target.with_suffix('.partial');partial.write_bytes(raw)
                    players=[p for team in ('blue','orange') for p in meta[team]['players']]
                    atomic_json(target.with_suffix('.source.json'),{'source':'ballchasing','id':rid,'playlist':'ranked-standard',
                        'group':group,'discovered_from':'https://ballchasing.com/group/'+group,'sha256':digest,
                        'quality_provenance':'user-curated group; not independent skill verification',
                        'ranks':[p.get('rank') for p in players],'car_ids':[p.get('car_id') for p in players],
                        'car_names':[p.get('car_name') for p in players],
                        'octane_hitbox_claim':'user supplied; verify actual replay hitbox metadata before enforcing'})
                    partial.replace(target);index.record(target,digest,{rid});index.save();added+=1
                    print('GROUP DOWNLOAD',added,'|',rid,flush=True)
                state['pending'].pop(0);save()
            else:status='COUNT_REACHED'
        except KeyboardInterrupt:status='PAUSED';save()
        except DownloadError as error:
            status='RETRY_LATER' if error.retry_after is not None else 'STOPPED'
            retry_at=now()+error.retry_after if error.retry_after is not None else None
            state['retry_at']=retry_at or 0
            save()
            if error.retry_after is None:raise
            print(str(error),'Rerun the same command after the cooldown; completed files are preserved.',flush=True)
        report={'status':status,'group':group,'folder':str(folder),'downloaded':added,'skipped_existing':skipped,
            'metadata_rejected':rejected,'pages':pages,'retry_at_unix':retry_at,
            'quality':'user-curated 3v3; API team sizes checked; ranks/hitboxes retained without invented verification'}
        atomic_json(folder/'group_download_status.json',report);return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group',default=DEFAULT_GROUP);parser.add_argument('--folder',type=Path)
    parser.add_argument('--count',type=int,default=0);parser.add_argument('--refresh',action='store_true')
    args=parser.parse_args(argv)
    print(json.dumps(download(args.group,folder=args.folder,count=args.count,refresh=args.refresh),indent=2))


if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError) as error:print('STOPPED:',str(error),flush=True);raise SystemExit(1)
