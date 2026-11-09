"""Exact identities and seed/color accounting must survive resumption and reject stale data."""
from pathlib import Path
from types import SimpleNamespace
import hashlib,json,sys,time
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import stationary_jobs as j

def rows(seed=123,pairs=2):
    return [dict(seed=seed+i,side=side,opponent='original_chronos',seconds=135.,goals_for=1,goals_against=0,outcome=1)
            for i in range(pairs) for side in (0,1)]

def test_exact_rounds_and_invalid_inputs():
    valid=rows();j.validate_rounds(valid,2,123,135.,'original_chronos')
    for invalid in (valid[:-1],valid[:-1]+[valid[0]], [dict(r,seed=-123) for r in valid],
                    [dict(r,seconds=100.) for r in valid],[dict(r,outcome=-1) for r in valid],
                    [dict(r,opponent='other') for r in valid]):
        with pytest.raises(ValueError):j.validate_rounds(invalid,2,123,135.,'original_chronos')
    with pytest.raises(ValueError):j.validate_rounds([],0,2_200_000_000,135.,'original_chronos')

def test_paired_summary():
    data=rows(pairs=100);out=j.summary(data)
    assert out['games']==200 and out['wins']==200 and out['paired_seed_blocks']==100
    assert out['score_interval_95'][0]>.5 and not out['automatic_promotion']
    for r in data:r.update(goals_for=0,outcome=0)
    assert j.summary(data)['score_rate']==.5 and j.summary(data)['score_interval_95'][0]<.5

def test_paired_candidate_baseline_comparison():
    candidate=rows(pairs=100);baseline=[dict(r,goals_for=0,outcome=0) for r in candidate]
    result=j.paired_difference(candidate,baseline)
    assert result['delta']==.5 and result['paired_seed_blocks']==100 and result['interval_95'][0]>0
    with pytest.raises(ValueError):j.paired_difference(candidate,baseline[:-1])

def fake_runtime(tmp_path):
    binary=tmp_path/'native';binary.write_bytes(b'binary v1')
    def write(p,d):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d))
    m=SimpleNamespace(binary=lambda:binary,sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest(),write=write,
                      read=lambda p:json.loads(Path(p).read_text()),descriptor=lambda p,f:dict(path=str(p),family=f,hitbox='breakout'))
    for who in ('candidate','opponent'):
        p=tmp_path/who;p.mkdir()
        for n in ('SHARED_HEAD.lt','POLICY.lt'):(p/n).write_bytes((who+n).encode())
    return m

def test_cached_jobs_reject_corruption_and_separate_changed_models(tmp_path,monkeypatch):
    m=fake_runtime(tmp_path);calls=[]
    def launch(m,recipe,*args,**kwargs):
        s=recipe['evaluation'];calls.append(s)
        m.write(s['output'],dict(trials=rows(s['seed'],s['pairs']),baseline_trials=[],direct_head_to_head=True,evaluation_protocol='arena-rng-v4'))
    monkeypatch.setattr(j,'launch',launch)
    args=(m,tmp_path/'study',tmp_path/'candidate',tmp_path/'opponent','chronos','chronos','original_chronos')
    kwargs=dict(pairs=2,seed=123,seconds=135.,device='cpu',stop=tmp_path/'STOP',deadline=time.monotonic()+30)
    assert len(j.evaluate(*args,**kwargs))==4 and len(calls)==1
    assert len(j.evaluate(*args,**kwargs))==4 and len(calls)==1
    (tmp_path/'candidate/POLICY.lt').write_bytes(b'new model')
    j.evaluate(*args,**kwargs);assert len(calls)==2
    result=Path(calls[-1]['output']);result.write_text('{}')
    with pytest.raises(ValueError,match='records changed'):j.evaluate(*args,**kwargs)

def test_new_native_binary_gets_a_different_job_identity(tmp_path,monkeypatch):
    m=fake_runtime(tmp_path);before=j.model_identity(m,tmp_path/'candidate')
    assert before['files']['POLICY.lt']!=before['files']['SHARED_HEAD.lt']
    assert j.digest(dict(native=m.sha(m.binary()),model=before))!=j.digest(dict(native='other',model=before))
