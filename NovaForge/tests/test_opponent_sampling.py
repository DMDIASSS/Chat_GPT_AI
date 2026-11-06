import copy
import json
from types import SimpleNamespace as NS
import numpy as np
import pytest
from filelock import FileLock,Timeout
from nova import opponent_sampling as s

NAMES=('chronos','galactus','nexto','ducky','rain','megabyte','fusion')
BASE={n:1/7 for n in NAMES}


def policy():return copy.deepcopy(s.POLICY)


def episode(name,loss,seconds):return dict(opponent=name,outcome=-1 if loss else 1,seconds=seconds)


def test_targets_concessions_per_time_not_unequal_raw_game_totals_and_retains_pool():
    p=policy();p['update_every_episodes']=1;sampler=s.ConcessionSampler(BASE,p)
    # Chronos concedes at 6/min; Galactus has more raw concessions but at .1/min.
    for _ in range(20):sampler.observe(episode('galactus',True,600))
    for _ in range(10):sampler.observe(episode('chronos',True,10))
    weights=sampler.probabilities()
    assert weights['chronos']>weights['galactus']
    assert sampler.rates()[0]>sampler.rates()[1]
    assert sum(weights.values())==pytest.approx(1)
    assert all(.05-1e-12<=v<=.30+1e-12 for v in weights.values())


def test_no_concessions_keeps_base_and_cadence_smooths_update():
    p=policy();sampler=s.ConcessionSampler(BASE,p)
    for i in range(128):sampler.observe(episode(NAMES[i%7],False,1+i%5))
    np.testing.assert_allclose(list(sampler.probabilities().values()),list(BASE.values()),atol=1e-12)
    prior=sampler.probabilities()
    for _ in range(63):assert not sampler.observe(episode('chronos',True,1))
    assert sampler.probabilities()==prior
    assert sampler.observe(episode('chronos',True,1))
    assert sampler.probabilities()['chronos']>prior['chronos']
    assert sampler.probabilities()['chronos']<=prior['chronos']+.25*(.30-prior['chronos'])+1e-12


def test_checkpoint_resume_produces_same_future_updates_with_bounded_memory():
    p=policy();p.update(window_per_opponent=8,update_every_episodes=3)
    a=s.ConcessionSampler(BASE,p)
    for i in range(70):a.observe(episode(NAMES[i%7],i%3==0,2+i%9))
    b=s.ConcessionSampler(BASE,p,json.loads(json.dumps(a.state())))
    for i in range(100):
        row=episode(NAMES[i%7],i%5==0,3+i%7);assert a.observe(row)==b.observe(row)
    assert a.state()==b.state() and all(len(q)<=8 for q in a.records.values())
    corrupt=copy.deepcopy(a.state());corrupt['weights']['chronos']=99
    with pytest.raises(ValueError,match='probabilities'):s.ConcessionSampler(BASE,p,corrupt)


def test_invalid_policy_history_and_unknown_opponents_fail_explicitly(tmp_path):
    p=policy();p['min_probability']=.2
    (tmp_path/'opponent_sampling_policy.json').write_text(json.dumps(p))
    with pytest.raises(ValueError,match='bounds'):s.policy_for(tmp_path,NAMES)
    sampler=s.ConcessionSampler(BASE,policy())
    with pytest.raises(ValueError,match='outside'):sampler.observe(episode('unknown',True,1))
    with pytest.raises(ValueError,match='duration'):sampler.observe(episode('chronos',True,0))
    wrong=policy();wrong['prior_seconds']=60
    with pytest.raises(ValueError,match='does not match'):s.ConcessionSampler(BASE,wrong,sampler.state())


def test_training_reset_uses_sampler_but_forced_evaluation_bypasses_it():
    from nova.environment import ArenaEnv
    class RNG:
        def choice(self,names,p):
            np.testing.assert_allclose(p,[.8,.2]);return 'chronos'
    sampler=NS(probabilities=lambda:dict(chronos=.8,galactus=.2))
    env=ArenaEnv.__new__(ArenaEnv);env.cfg={'league':{'weights':{'chronos':.5,'galactus':.5}}}
    env.forced_snapshot=None;env.forced_opponent=None;env.opponent_sampler=sampler;env.np_random=RNG()
    env.cache={('chronos','None'):NS(),('galactus','None'):NS()}
    env._choose_opponent();assert env.opponent_label=='chronos'
    env.forced_opponent='galactus'
    env._choose_opponent();assert env.opponent_label=='galactus'
    assert env.cfg['league']['weights']=={'chronos':.5,'galactus':.5}


def test_enable_disable_preserves_checkpoint_and_immutable_config(tmp_path,monkeypatch):
    from nova import triad_selector
    from nova.core import sha256
    monkeypatch.setattr(triad_selector,'RUNS',tmp_path)
    run=tmp_path/'selector06';run.mkdir();(run/'full.zip').write_bytes(b'original checkpoint')
    cfg=dict(selector_experts=list(triad_selector.SIX_NAMES),selector_opponents=BASE)
    (run/'config.json').write_text(json.dumps(cfg));before={n:sha256(run/n) for n in ('full.zip','config.json')}
    s.configure('selector06',True);assert s.policy_for(run,NAMES)['enabled']
    s.configure('selector06',False);assert not s.policy_for(run,NAMES)['enabled']
    assert before=={n:sha256(run/n) for n in before}
    assert len(list((run/'research/sampling_changes').glob('*.json')))==2
    with FileLock(str(run/'train.lock')):
        with pytest.raises(Timeout):s.configure('selector06',True)


def test_probability_projection_rejects_bad_values_and_handles_extreme_focus():
    out=s.bounded_probabilities([1,0,0,0,0,0,0],.05,.30)
    assert out[0]==pytest.approx(.30) and sum(out)==pytest.approx(1)
    assert all(.05-1e-12<=v<=.30+1e-12 for v in out)
    with pytest.raises(ValueError):s.bounded_probabilities([np.nan,1],0,.8)
