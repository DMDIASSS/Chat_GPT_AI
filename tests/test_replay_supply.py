import copy,io,json,urllib.error,urllib.parse,uuid,zipfile
from pathlib import Path
import pytest
import slater_replay_supply as supply
from slater_v041_core import atomic_json,read_json,sha256

def config():return {**supply.DEFAULT,'batch_size':16,'min_disk_gb':0}
def replay_files(folder,count):
    folder.mkdir(parents=True,exist_ok=True)
    result=[]
    for i in range(count):
        p=folder/f'{i}.replay';p.write_bytes(bytes([i%256])*100+b'fixture');result.append(p)
    return result
def meta(tiers=(21,22)):
    return {'id':str(uuid.uuid4()),'playlist_id':'ranked-duels',
        'blue':{'players':[{'rank':{'tier':tiers[0]}}]},'orange':{'players':[{'rank':{'tier':tiers[1]}}]}}

def test_search_uses_documented_filters_and_checks_exact_player_tiers():
    cfg=config();query=urllib.parse.parse_qs(urllib.parse.urlsplit(supply.search_url(cfg)).query)
    assert query['playlist']==['ranked-duels'] and query['min-rank']==['grand-champion']
    assert query['replay-date-after']==['2021-01-01T00:00:00Z']
    assert supply.elite_duel(meta(),cfg)
    assert not supply.elite_duel(meta((20,22)),cfg)
    missing=meta();missing['blue']['players'][0]['rank']={}
    assert not supply.elite_duel(missing,cfg)

def test_local_replays_are_used_before_any_api_and_preserved(tmp_path,monkeypatch):
    inputs=tmp_path/'inputs';files=replay_files(inputs,16)
    monkeypatch.setattr(supply,'BASE',tmp_path/'supply')
    def forbidden(*args,**kw):raise AssertionError('API called before local files exhausted')
    monkeypatch.setattr(supply,'ballchasing',forbidden);monkeypatch.setattr(supply,'kaggle',forbidden)
    run=tmp_path/'run';run.mkdir();pack=supply.batch(run,4,cfg=config(),inputs=inputs)
    assert len(pack['files'])==16 and all(p.exists() for p in files)
    assert len(read_json(run/'replay_seen.json'))==16
    assert supply.batch(run,4,cfg=config(),inputs=inputs)==pack

def test_ballchasing_limit_falls_back_to_independent_dataset(tmp_path,monkeypatch):
    monkeypatch.setattr(supply,'BASE',tmp_path/'supply');files=replay_files(tmp_path/'dataset'/'1v1',16)
    def limited(*args,**kw):raise supply.Limited('quota reached')
    monkeypatch.setattr(supply,'ballchasing',limited)
    calls=[];monkeypatch.setattr(supply,'kaggle',lambda *args,**kw:calls.append(kw) or files)
    run=tmp_path/'run';run.mkdir()
    pack=supply.batch(run,4,cfg=config(),inputs=tmp_path/'empty')
    assert len(pack['files'])==16 and calls
    status=read_json(run/'replay_supply_status.json');assert not status['using_cached_bank']
    assert 'quota' in status['notes'][0]

def test_missing_sources_keep_cached_bank_without_fake_batch(tmp_path,monkeypatch):
    monkeypatch.setattr(supply,'BASE',tmp_path/'supply')
    monkeypatch.setattr(supply,'ballchasing',lambda *a,**k:[]);monkeypatch.setattr(supply,'kaggle',lambda *a,**k:[])
    run=tmp_path/'run';run.mkdir()
    assert supply.batch(run,4,cfg=config(),inputs=tmp_path/'empty') is None
    assert read_json(run/'replay_supply_status.json')['using_cached_bank']

def test_hour_budget_does_not_make_network_requests(monkeypatch):
    monkeypatch.setattr(supply,'token',lambda:'fixture-token')
    state={'download_attempts':[supply.time.time()]*180}
    def forbidden(*a,**k):raise AssertionError('quota bypass')
    with pytest.raises(supply.Limited):supply.ballchasing(config(),state,1,fetch=forbidden)

def test_api_bytes_saved_once_and_no_credentials_in_provenance(tmp_path,monkeypatch):
    monkeypatch.setattr(supply,'BASE',tmp_path);monkeypatch.setattr(supply,'token',lambda:'fixture-secret')
    monkeypatch.setattr(supply.time,'sleep',lambda *a:None)
    row=meta();state={'pending':[row],'next_url':None};calls=[]
    def fetch(url,headers,**kw):calls.append(url);return b'\x00binary replay fixture'
    files=supply.ballchasing(config(),state,1,fetch=fetch)
    assert len(files)==1 and len(calls)==1
    assert 'fixture-secret' not in files[0].with_suffix('.source.json').read_text()
    assert len(state['download_attempts'])==1

def test_http_429_returns_cooldown_without_blocking_retries():
    def opener(req,**kw):raise urllib.error.HTTPError(req.full_url,429,'limit',{'Retry-After':'123'},io.BytesIO(b'body'))
    with pytest.raises(supply.Limited) as caught:supply.request('https://ballchasing.com/api/replays',opener=opener)
    assert caught.value.retry_after==123

def test_kaggle_fetches_only_bounded_duel_files_and_handles_single_file_zip(tmp_path,monkeypatch):
    monkeypatch.setattr(supply,'BASE',tmp_path)
    page={'datasetFiles':[{'name':'2v2/a.replay','totalBytes':100},
        {'name':'1v1/huge.replay','totalBytes':100*1024**2},{'name':'1v1/good.replay','totalBytes':100}]}
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as z:z.writestr('../../good.replay',b'\x00bounded replay')
    calls=[]
    def fetch(url,*args,**kw):calls.append(url);return json.dumps(page).encode() if '/list/' in url else output.getvalue()
    files=supply.kaggle(config(),{},1,fetch=fetch)
    assert len(files)==1 and len(calls)==2
    assert '1v1/good.replay' in calls[-1]
    assert not (tmp_path.parent/'good.replay').exists()

def test_local_dataset_fallback_skips_already_seen_bytes(tmp_path):
    files=replay_files(tmp_path/'1v1',2);cfg={**config(),'kaggle_local':str(tmp_path)}
    assert supply.kaggle(cfg,{},1,seen={sha256(files[0])})==[files[1]]

def test_pause_prevents_new_api_calls(tmp_path,monkeypatch):
    stop=tmp_path/'pause.flag';stop.touch();monkeypatch.setattr(supply,'token',lambda:'fixture')
    with pytest.raises(supply.SupplyPaused):supply.ballchasing(config(),{},1,stop_file=stop)

def test_pagination_cannot_send_token_to_another_host():
    with pytest.raises(supply.SupplyUnavailable):supply.valid_api_url('https://example.com/api/replays')
