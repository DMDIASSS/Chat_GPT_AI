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
        if binary:return b'REPLAY_BINARY_TEST_ONLY'
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

def test_api_budget_includes_listing_and_waits_before_next_attempt(tmp_path,environment,monkeypatch):
    use_token(monkeypatch);monkeypatch.setattr(dl,'HOUR_LIMIT',2)
    first,second=replay(),replay();calls=[]
    def fetch(url,binary=False):
        calls.append((environment.time(),url))
        return b'REPLAY_TEST_ONLY' if binary else {'list':[first,second],'next':None}
    result=dl.download(tmp_path,count=2,prompt=False,fetch=fetch,automatic=True)
    assert result['status']=='COMPLETE'
    assert calls[2][0]-calls[0][0]>=3600

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
