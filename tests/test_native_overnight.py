from pathlib import Path
from types import SimpleNamespace
import copy
import pytest
import slater_native_overnight as overnight
from slater_native_eval import evaluate,EvaluationPaused
from slater_v041_core import read_json,atomic_json

def state():
    return {'config':copy.deepcopy(overnight.DEFAULT),'confirmed_playing':'protected.pt','cycle':0,'specialists':{}}

def row(path,score,kind='native'):
    return {'path':path,'identity':{'kind':kind},'score':{'mean_goal_diff':score,
        'wins':1,'draws':2,'losses':3},'report':'evidence.json'}

def test_shortlist_retains_close_and_losing_candidates_without_promotion(tmp_path):
    registry={'a':row('best',1),'b':row('close',.99),'c':row('weak',-2),'d':row('nexto',2,'nexto')}
    native=overnight.shortlist(tmp_path,registry,state(),limit=2)
    result=read_json(tmp_path/'shortlist.json')
    assert [r['path'] for r in native]==['best','close','weak']
    assert result['models_preserved']==4 and len(registry)==4
    assert result['confirmed_playing_checkpoint']=='protected.pt'
    assert result['status']=='PROVISIONAL_SHORT_MATCH_RANKING'
    assert 'close' in (tmp_path/'SHORTLIST.md').read_text()

def test_paused_evaluation_does_not_start_loading_models(tmp_path):
    stop=tmp_path/'pause.flag';stop.touch()
    with pytest.raises(EvaluationPaused):
        evaluate({'bad':'missing'},{'bad':'missing'},out=tmp_path/'eval.json',stop_file=stop)
    assert not (tmp_path/'eval.json').exists()

def test_tied_shortlist_is_stable_across_json_key_reordering(tmp_path):
    registry={'z':row('model_a',0),'a':row('model_b',0)}
    before=overnight.shortlist(tmp_path,registry,state())
    atomic_json(tmp_path/'models.json',registry)
    after=overnight.shortlist(tmp_path,read_json(tmp_path/'models.json'),state())
    assert [r['path'] for r in before]==[r['path'] for r in after]==['model_a','model_b']

def test_confirmation_uses_fresh_seeds_and_summable_error_budget(tmp_path,monkeypatch):
    s=state();s.update(confirmation_attempts=0)
    calls=[]
    monkeypatch.setattr(overnight,'evaluate',lambda *args,**kw:calls.append(kw) or {})
    monkeypatch.setattr(overnight,'paired_verdict',lambda *args,**kw:{'passed':False,'alpha':kw['alpha']})
    stop=tmp_path/'pause.flag'
    for i in range(3):overnight.confirm('candidate',tmp_path,s,{'nexto':'fixed'},'build',stop)
    assert s['confirmed_playing']=='protected.pt' and s['confirmation_attempts']==3
    assert len({c['seed_base'] for c in calls})==3
    assert all(c['seed_base']!=overnight.SCREEN_SEED for c in calls)
    alphas=[read_json(tmp_path/'confirmations'/f'attempt_{i:04d}.verdict.json')['alpha'] for i in range(1,4)]
    assert alphas==pytest.approx([.025,.05/6,.05/12]) and sum(alphas)<.05

def test_confirmation_retention_failure_keeps_incumbent(tmp_path,monkeypatch):
    s=state();s.update(confirmation_attempts=0)
    monkeypatch.setattr(overnight,'evaluate',lambda *args,**kw:{})
    monkeypatch.setattr(overnight,'paired_verdict',lambda *args,**kw:{'passed':True})
    monkeypatch.setattr(overnight,'guard',lambda *args,**kw:False)
    overnight.confirm('candidate',tmp_path,s,{'nexto':'fixed'},'build',tmp_path/'pause.flag')
    assert s['confirmed_playing']=='protected.pt'
    assert not s['last_confirmation']['passed']

def test_interrupted_confirmation_freezes_challenger_on_resume(tmp_path,monkeypatch):
    s=state();s.update(confirmation_attempts=0)
    def pause(*args,**kw):raise EvaluationPaused('during matches')
    monkeypatch.setattr(overnight,'evaluate',pause)
    with pytest.raises(EvaluationPaused):overnight.confirm('candidate_a',tmp_path,s,{},'build',None)
    with pytest.raises(ValueError,match='Frozen'):
        overnight.confirm('candidate_b',tmp_path,s,{},'build',None)

def test_completed_training_reuses_only_recorded_checkpoint_paths(tmp_path,monkeypatch):
    native=tmp_path/'runs'/'completed';native.mkdir(parents=True)
    recorded=native/'checkpoints'/'1000';recorded.mkdir(parents=True)
    atomic_json(native/'overnight_completed.json',{'checkpoints':[str(recorded)]})
    monkeypatch.setattr(overnight,'helper',lambda:SimpleNamespace(BASE=tmp_path))
    validated=[];monkeypatch.setattr(overnight,'checkpoint_identity',lambda p:validated.append(p))
    # No actor load, subprocess launch, or untrained source-copy screening.
    assert overnight.learn('completed','missing','bank','mixed',[],tmp_path,state(),'build',None)==[recorded]
    assert validated==[recorded]

def test_disk_floor_pauses_without_deleting_files(tmp_path,monkeypatch):
    checkpoint=tmp_path/'protected.lt';checkpoint.write_bytes(b'weights')
    monkeypatch.setattr(overnight.shutil,'disk_usage',lambda p:SimpleNamespace(free=1))
    with pytest.raises(EvaluationPaused,match='Disk floor'):
        overnight.capacity(tmp_path,overnight.DEFAULT)
    assert checkpoint.read_bytes()==b'weights'

def test_replay_preparation_failure_has_persistent_diagnostics(tmp_path,monkeypatch):
    monkeypatch.setattr(overnight,'paths',lambda run:tmp_path)
    def fail(*args,**kw):raise RuntimeError('parser failed')
    monkeypatch.setattr(overnight,'child',fail)
    with pytest.raises(RuntimeError,match='parser failed'):overnight.run('fixture')
    report=read_json(tmp_path/'status.json')
    assert report['status']=='ERROR' and report['reason']=='parser failed'

def test_refresh_trains_new_bank_and_keeps_previous_bank(tmp_path,monkeypatch):
    old=tmp_path/'old.bin';old.write_bytes(b'protected old bank')
    fresh=tmp_path/'fresh.bin';fresh.write_bytes(b'prepared fresh bank')
    s=state();s.update(cycle=4,active_bank=str(old),active_bank_sha=overnight.sha256(old))
    cfg=tmp_path/'supply.json';atomic_json(cfg,{'enabled':True});monkeypatch.setattr(overnight.supply,'CONFIG',cfg)
    pack={'inputs':'inputs','dataset':'dataset','bank':str(fresh)}
    monkeypatch.setattr(overnight.supply,'batch',lambda *a,**k:pack)
    monkeypatch.setattr(overnight,'child',lambda *a,**k:None)
    monkeypatch.setattr(overnight,'shortlist',lambda *a,**k:[{'path':'seed'}])
    learned=[]
    monkeypatch.setattr(overnight,'learn',lambda *a,**k:learned.append((a,k)) or [Path('new_checkpoint')])
    monkeypatch.setattr(overnight,'screen',lambda *a,**k:None)
    overnight.refresh_replays('run',tmp_path,s,{}, {},'build',tmp_path/'pause.flag')
    assert s['active_bank']==str(fresh) and s['replay_refresh_cycle']==4
    assert learned[0][0][2]==str(fresh) and learned[0][1]['bc_epochs']==2
    assert old.read_bytes()==b'protected old bank'

def test_failed_fresh_parser_keeps_training_bank(tmp_path,monkeypatch):
    s=state();s.update(cycle=4,active_bank='protected bank')
    cfg=tmp_path/'supply.json';atomic_json(cfg,{'enabled':True});monkeypatch.setattr(overnight.supply,'CONFIG',cfg)
    monkeypatch.setattr(overnight.supply,'batch',lambda *a,**k:{'inputs':'input','dataset':'data','bank':'new'})
    def fail(*a,**k):raise RuntimeError('parser failure')
    monkeypatch.setattr(overnight,'child',fail)
    overnight.refresh_replays('run',tmp_path,s,{}, {},'build',None)
    assert s['active_bank']=='protected bank'
    assert read_json(tmp_path/'replay_supply_status.json')['using_cached_bank']
