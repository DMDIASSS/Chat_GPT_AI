import copy
import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

import download_2v2_gc3_ssl as dl

TOKEN='LOCAL_TEST_SECRET_ONLY'

class Clock:
    def __init__(self):self.value=10000.;self.slept=0
    def time(self):return self.value
    def sleep(self,seconds):self.value+=seconds;self.slept+=seconds

@pytest.fixture
def environment(tmp_path,monkeypatch):
    clock=Clock()
    monkeypatch.setattr(dl.time,'time',clock.time)
    monkeypatch.setattr(dl.time,'monotonic',clock.time)
    monkeypatch.setattr(dl.time,'sleep',clock.sleep)
    monkeypatch.setattr(dl,'ROOT',tmp_path)
    monkeypatch.delenv('BALLCHASING_TOKEN',raising=False)
    monkeypatch.delenv('BALLCHASING_API_KEY',raising=False)
    monkeypatch.setattr(dl,'TOKEN_FILE',tmp_path/'private/ballchasing_token.txt')
    return clock

def replay():
    return {'id':str(uuid.uuid4()),'playlist_id':'ranked-doubles',
        **{side:{'players':[{'rank':{'tier':21}},{'rank':{'tier':22}}]} for side in ('blue','orange')}}

def use_token(monkeypatch):monkeypatch.setenv('BALLCHASING_TOKEN',TOKEN)

def test_reuses_saved_token_environment_override_and_hidden_setup(environment,monkeypatch,capsys):
    monkeypatch.setattr(dl.getpass,'getpass',lambda prompt:TOKEN)
    assert dl.credentials(save=True)==TOKEN
    assert dl.TOKEN_FILE.read_text()==TOKEN
    monkeypatch.setattr(dl.getpass,'getpass',lambda prompt:pytest.fail('Saved token prompted again'))
    assert dl.credentials(prompt=False)==TOKEN
    monkeypatch.setenv('BALLCHASING_TOKEN',' ENV_TOKEN ')
    assert dl.credentials()== 'ENV_TOKEN'
    assert TOKEN not in capsys.readouterr().out

@pytest.mark.parametrize('bad',[None,{},[],{'tier':20},{'tier':23},{'tier':True},{'id':[]},'GC3'])
def test_every_player_must_have_known_gc3_or_ssl_rank(bad):
    good=replay();assert dl.eligible(good)
    good['orange']['players'][1]['rank']=bad
    assert not dl.eligible(good)

def test_resume_pages_duplicates_and_no_secret_in_reports(tmp_path,environment,monkeypatch):
    use_token(monkeypatch);first,second=replay(),replay();bad=copy.deepcopy(first)
    bad['orange']['players'][0]['rank']['tier']=20
    calls=[]
    def fetch(url,binary=False):
        calls.append(url)
        if binary:return b'REPLAY_BINARY_TEST_ONLY:'+url.encode()
        return {'list':[first,bad],'next':'https://ballchasing.com/api/replays?after=page1'} if 'after=page1' not in url else {'list':[first,second],'next':None}
    folder=tmp_path/'ranked-doubles'
    assert dl.download(folder,count=1,fetch=fetch,prompt=False,automatic=True)['downloaded']==1
    assert dl.download(folder,count=1,fetch=fetch,prompt=False,automatic=True)['downloaded']==1
    assert len(list(folder.glob('*.replay')))==2
    assert len([u for u in calls if u.endswith('/file')])==2
    assert len(json.loads((folder/'.imitation_download.json').read_text())['requests'])==4
    for path in folder.iterdir():
        if path.is_file():assert TOKEN not in path.read_text(errors='ignore')

def test_429_wait_retries_same_pending_replay(tmp_path,environment,monkeypatch):
    use_token(monkeypatch);meta=replay();downloads=[]
    def fetch(url,binary=False):
        if not binary:return {'list':[meta],'next':None}
        downloads.append(url)
        if len(downloads)==1:raise dl.DownloadError('Rate limited',retry_after=42,status=429)
        return b'REPLAY_TEST_ONLY'
    result=dl.download(tmp_path,count=1,prompt=False,fetch=fetch,automatic=True)
    assert result['status']=='COMPLETE' and result['downloaded']==1
    assert downloads[0]==downloads[1] and environment.slept>=42
    assert len(json.loads((tmp_path/'.imitation_download.json').read_text())['requests'])==3

def test_download_budget_waits_before_next_file_attempt(tmp_path,environment,monkeypatch):
    use_token(monkeypatch);monkeypatch.setattr(dl,'HOUR_LIMIT',1)
    first,second=replay(),replay();calls=[]
    def fetch(url,binary=False):
        calls.append((environment.time(),url))
        return b'REPLAY_TEST_ONLY:'+url.encode() if binary else {'list':[first,second],'next':None}
    result=dl.download(tmp_path,count=2,prompt=False,fetch=fetch,automatic=True)
    assert result['status']=='COMPLETE'
    assert calls[2][0]-calls[0][0]>=3600

def test_search_pages_do_not_consume_download_hour_budget(tmp_path,environment,monkeypatch):
    use_token(monkeypatch);monkeypatch.setattr(dl,'HOUR_LIMIT',1);calls=[]
    def fetch(url,binary=False):
        assert not binary;calls.append(url)
        return {'list':[],'next':f'https://ballchasing.com/api/replays?page={len(calls)}' if len(calls)<5 else None}
    result=dl.download(tmp_path,count=1,prompt=False,fetch=fetch,automatic=True)
    assert result['pages']==5 and result['downloaded']==0 and environment.slept<10
    assert json.loads((tmp_path/'.imitation_download.json').read_text())['download_attempts']==[]

def test_existing_ids_in_other_folders_and_renamed_sidecars_skip_network_files(tmp_path,environment,monkeypatch):
    use_token(monkeypatch);a,b,new=replay(),replay(),replay();old=tmp_path/'elsewhere';old.mkdir()
    (old/(a['id']+'.replay')).write_bytes(b'PREEXISTING_A')
    (old/'renamed.replay').write_bytes(b'PREEXISTING_B')
    (old/'renamed.source.json').write_text(json.dumps({'source':'ballchasing','id':b['id']}))
    calls=[]
    def fetch(url,binary=False):
        if binary:calls.append(url);return b'NEW_REPLAY'
        return {'list':[a,b,new,new],'next':None}
    folder=tmp_path/'out'
    result=dl.download(folder,count=1,prompt=False,fetch=fetch,existing_roots=[old])
    assert len(calls)==1 and new['id'] in calls[0] and result['skipped_existing']==3
    assert len(list(old.glob('*.replay')))==2 and len(list(folder.glob('*.replay')))==1

def test_content_duplicate_alias_is_cached_to_avoid_future_download(tmp_path,environment,monkeypatch):
    use_token(monkeypatch);meta=replay();old=tmp_path/'existing';old.mkdir()
    (old/'manually_renamed.replay').write_bytes(b'SAME_REPLAY_BYTES');calls=[]
    def fetch(url,binary=False):
        calls.append((url,binary));return b'SAME_REPLAY_BYTES' if binary else {'list':[meta],'next':None}
    folder=tmp_path/'out'
    first=dl.download(folder,count=1,prompt=False,fetch=fetch,existing_roots=[old])
    assert first['downloaded']==0 and first['skipped_identical_content']==1
    second=dl.download(folder,count=1,prompt=False,fetch=fetch,existing_roots=[old],refresh_search=True)
    assert second['skipped_existing']==1 and sum(binary for _,binary in calls)==1
    assert not list(folder.glob('*.replay'))

def test_hash_cache_reuses_unchanged_files_and_invalidates_edits(tmp_path,environment,monkeypatch):
    folder=tmp_path/'out';folder.mkdir();old=tmp_path/'old';old.mkdir();path=old/'test.replay';path.write_bytes(b'OLD_BYTES')
    first=dl.ReplayIndex(folder,[old]);assert first.hashed==1
    second=dl.ReplayIndex(folder,[old]);assert second.hashed==0 and second.reused==1
    alias=str(uuid.uuid4());second.alias(alias,path.resolve())
    path.write_bytes(b'CHANGED_LONGER_BYTES')
    assert second.find_id(alias) is None
    third=dl.ReplayIndex(folder,[old]);assert third.hashed==1 and third.find_id(alias) is None
    assert third.find_hash(dl.hashlib.sha256(b'OLD_BYTES').hexdigest()) is None

def test_narrow_rank_and_larger_page_search_probe_falls_back_safely(tmp_path,environment,monkeypatch):
    from urllib.parse import parse_qs,urlsplit
    use_token(monkeypatch);meta=replay();queries=[]
    def fetch(url,binary=False):
        if binary:return b'REPLAY_TEST'
        query=parse_qs(urlsplit(url).query);queries.append(query)
        if query['min-rank']==['grand-champion-3'] or query['count']==['200']:
            raise dl.DownloadError('Unsupported query',status=400)
        return {'list':[meta],'next':None}
    result=dl.download(tmp_path,count=1,prompt=False,fetch=fetch)
    assert result['downloaded']==1
    assert [(q['min-rank'][0],q['count'][0]) for q in queries]==[
        ('grand-champion-3','200'),('grand-champion-3','100'),('grand-champion','200'),('grand-champion','100')]
    saved=json.loads((tmp_path/'.imitation_download.json').read_text())
    assert saved['search_mode']=='broad' and saved['page_size']==100 and saved['query_verified']

def test_all_pages_continues_until_server_exhaustion_and_can_refresh(tmp_path,environment,monkeypatch):
    use_token(monkeypatch);metas=[replay() for _ in range(3)];page=0
    def fetch(url,binary=False):
        nonlocal page
        if binary:return b'REPLAY:'+url.encode()
        current=page;page+=1
        return {'list':[metas[current]],'next':f'https://ballchasing.com/api/replays?page={page}' if page<3 else None}
    result=dl.download(tmp_path,count=0,prompt=False,fetch=fetch,automatic=True)
    assert result['status']=='COMPLETE' and result['downloaded']==3 and result['pages']==3
    page=0
    again=dl.download(tmp_path,count=0,prompt=False,fetch=fetch,automatic=True,refresh_search=True)
    assert again['downloaded']==0 and again['skipped_existing']==3

def test_upgrade_keeps_old_files_pending_candidates_and_quota_history(tmp_path,environment,monkeypatch):
    use_token(monkeypatch);old,new=replay(),replay()
    (tmp_path/(old['id']+'.replay')).write_bytes(b'EXISTING_REPLAY')
    old_time=environment.time()-10
    (tmp_path/'.imitation_download.json').write_text(json.dumps({
        'url':'https://ballchasing.com/api/replays?old-cursor=1','pending':[old],
        'requests':[old_time],'playlist':'ranked-doubles'}))
    calls=[]
    def fetch(url,binary=False):
        calls.append((url,binary))
        if binary:return b'NEW_REPLAY'
        assert 'old-cursor' not in url
        return {'list':[old,new],'next':None}
    result=dl.download(tmp_path,count=1,prompt=False,fetch=fetch)
    assert result['downloaded']==1 and result['skipped_existing']==2
    assert len(calls)==2 and new['id'] in calls[1][0]
    state=json.loads((tmp_path/'.imitation_download.json').read_text())
    assert old_time in state['requests'] and old_time in state['download_attempts']

def test_all_pages_rejects_cyclic_server_pagination(tmp_path,environment,monkeypatch):
    use_token(monkeypatch);calls=[]
    def fetch(url,binary=False):calls.append(url);return {'list':[],'next':url}
    with pytest.raises(dl.DownloadError,match='repeated a pagination cursor'):
        dl.download(tmp_path,count=0,prompt=False,fetch=fetch,automatic=True)
    assert len(calls)==1

def test_pause_during_cooldown_and_resume_keeps_pending_file(tmp_path,environment,monkeypatch):
    use_token(monkeypatch);meta=replay();calls=[]
    def fetch(url,binary=False):
        calls.append(url)
        if binary:
            (tmp_path/'.download_pause').touch()
            raise dl.DownloadError('Rate limited',retry_after=3600,status=429)
        return {'list':[meta],'next':None}
    result=dl.download(tmp_path,count=1,prompt=False,fetch=fetch,automatic=True)
    assert result['status']=='PAUSED'
    assert len(json.loads((tmp_path/'.imitation_download.json').read_text())['pending'])==1
    def finish(url,binary=False):assert binary;return b'REPLAY_TEST_ONLY'
    assert dl.download(tmp_path,count=1,prompt=False,fetch=finish,automatic=True)['status']=='COMPLETE'

def test_http_auth_retry_after_and_error_body_not_logged(environment):
    seen=[]
    class Opener:
        def open(self,req,timeout):
            seen.append(req)
            raise urllib.error.HTTPError(req.full_url,429,TOKEN,{'Retry-After':'77'},None)
    with pytest.raises(dl.DownloadError) as caught:
        dl.http_fetch(TOKEN,opener=Opener())('https://ballchasing.com/api/replays')
    assert caught.value.retry_after==77 and TOKEN not in str(caught.value)
    assert seen[0].get_header('Authorization')==TOKEN
    class Denied:
        def open(self,req,timeout):raise urllib.error.HTTPError(req.full_url,401,TOKEN,{},None)
    with pytest.raises(dl.DownloadError) as caught:
        dl.http_fetch(TOKEN,opener=Denied())('https://ballchasing.com/api/replays')
    assert caught.value.retry_after is None and TOKEN not in str(caught.value)

def test_invalid_token_stops_without_retry_or_publishing_partial_file(tmp_path,environment,monkeypatch):
    use_token(monkeypatch);calls=[]
    def fail(url,binary=False):calls.append(url);raise dl.DownloadError('Invalid token',status=401)
    with pytest.raises(dl.DownloadError):dl.download(tmp_path,count=1,prompt=False,fetch=fail,automatic=True)
    assert len(calls)==1 and not list(tmp_path.glob('*.replay'))
    assert json.loads((tmp_path/'download_status.json').read_text())['status']=='STOPPED'

def test_missing_ranks_and_wrong_mode_are_not_downloaded(tmp_path,environment,monkeypatch):
    use_token(monkeypatch);unknown=replay();unknown['blue']['players'][0].pop('rank')
    duel=replay();duel['playlist_id']='ranked-duels'
    def fetch(url,binary=False):assert not binary;return {'list':[unknown,duel],'next':None}
    result=dl.download(tmp_path,count=1,prompt=False,fetch=fetch,automatic=True)
    assert result['status']=='SEARCH_EXHAUSTED' and result['metadata_rejected']==2
    assert result['downloaded']==0

def test_redirect_does_not_forward_token_to_another_host():
    req=urllib.request.Request('https://ballchasing.com/api/replays/id/file',headers={'Authorization':TOKEN})
    forwarded=dl.Redirect().redirect_request(req,None,302,'Found',{},'https://cdn.example/replay')
    assert forwarded.get_header('Authorization') is None
    with pytest.raises(ValueError):dl.valid_url('https://evil.example/api/replays')
