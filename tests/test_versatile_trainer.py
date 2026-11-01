from pathlib import Path
import json
import numpy as np
import pytest
import torch
from slater_v041_core import atomic_json,sha256
from slater_versatile_data import DemoDataset,label,capture_frames,valid_state,partition
from slater_versatile_env import VersatileEnv,TASKS
from slater_versatile_eval import verdict,sign_pvalue,evaluate,EvaluationPaused
from slater_mechanics_eval import load_actor
import slater_versatile_trainer as trainer

ROOT=Path(__file__).resolve().parents[1]
@pytest.fixture(scope='module')
def actor():
    torch.set_num_threads(2)
    return load_actor(ROOT,ROOT/'vendor/nexto/nexto-model.pt')


def dataset(path,n=96):
    rng=np.random.default_rng(819);path.mkdir()
    q=rng.normal(0,.1,(n,1,32)).astype(np.float32)
    kv=rng.normal(0,.1,(n,41,24)).astype(np.float32)
    target=np.eye(90,dtype=np.float32)[rng.integers(90,size=n)]
    arrays={'q':q,'kv':kv,'mask':np.zeros((n,41),np.float32),'target':target,
            'weight':np.ones(n,np.float32),'bucket':rng.integers(6,size=n,dtype=np.uint8),
            'split':np.arange(n,dtype=np.uint8)%3,'source_id':np.arange(n,dtype=np.int32)%3}
    for k,v in arrays.items():np.save(path/(k+'.npy'),v)
    atomic_json(path/'manifest.json',{'samples':n,'arrays':{k:sha256(path/(k+'.npy')) for k in arrays},'sources':[]})
    return DemoDataset(path)


def test_replay_split_and_balanced_batches(tmp_path):
    d=dataset(tmp_path/'data');b=d.batch(np.random.default_rng(1),48)
    assert b['q'].shape==(48,1,32) and b['target'].shape==(48,90)
    assert len(np.unique(b['bucket']))==6
    assert set(d.arrays['source_id'][d.indices['train']]).isdisjoint(d.arrays['source_id'][d.indices['test']])
    assert partition('00000000')=='train' and partition('00000050')=='validation' and partition('0000005a')=='test'


def test_dataset_tamper_and_leakage_refused(tmp_path):
    d=dataset(tmp_path/'data');path=d.path/'q.npy';q=np.load(path);q[0,0,0]=99;np.save(path,q)
    with pytest.raises(ValueError,match='changed'):DemoDataset(d.path)
    d=dataset(tmp_path/'other');np.save(d.path/'source_id.npy',np.zeros(96,np.int32))
    m=json.loads((d.path/'manifest.json').read_text());m['arrays']['source_id']=sha256(d.path/'source_id.npy');atomic_json(d.path/'manifest.json',m)
    with pytest.raises(ValueError,match='leakage'):DemoDataset(d.path)


@pytest.mark.parametrize('task',[t for t in TASKS if t!='replay'])
def test_all_real_scenarios_and_scripted_opponents(actor,task):
    e=VersatileEnv({'nexto':actor},task_name=task,max_seconds=.4)
    try:
        obs=e.reset(71)
        assert len(e.state.cars)==(4 if task=='teamplay' else 2)
        for _ in range(8):
            obs,reward,done,info=e.step(0)
            assert np.isfinite(reward) and all(np.isfinite(x).all() for x in obs)
            assert obs[1].shape==(41,24)
            if done:break
        assert done and info['timeout']
        if task=='match':assert info['script_physics_ticks']>0
        if task in ('aerial','air_dribble','reset_use'):assert info['script_physics_ticks']==0
    finally:e.close()


def test_exact_capture_alignment_and_misalignment(tmp_path,actor):
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    from rlgym_tools.rocket_league.misc.serialize import serialize_game_state
    engine=RocketSimEngine(rlbot_delay=False)
    try:
        state=engine.create_base_state();FixedTeamSizeMutator(1,1).apply(state,{});KickoffMutator().apply(state,{})
        state=engine.set_state(state,{});ids=sorted(state.cars)
        raw=np.array([[1,0,0,0,0,0,0,0]]*2,np.float32);states=[serialize_game_state(state)]
        for _ in range(8):
            state=engine.step({aid:np.repeat(raw[j][None],8,axis=0) for j,aid in enumerate(ids)},{})
            states.append(serialize_game_state(state))
    finally:engine.close()
    path=tmp_path/'trace.npz';np.savez(path,states=states,controls=np.repeat(raw[None],8,axis=0),tick_skip=8)
    frames=list(capture_frames(path));assert len(frames)==8
    assert label(next(iter(frames[0][0].cars.values())),np.zeros(8)) is not None
    # Wrong controls must not be treated as an exact input demonstration.
    wrong=raw.copy();wrong[:,5]=1
    np.savez(path,states=states,controls=np.repeat(wrong[None],8,axis=0),tick_skip=8)
    assert len(list(capture_frames(path)))<8
    assert label(next(iter(frames[0][0].cars.values())),np.full(8,np.nan)) is None


def test_bc_real_update_and_exact_rollback(tmp_path):
    data=dataset(tmp_path/'data');actor=load_actor(ROOT,ROOT/'vendor/nexto/nexto-model.pt',trainable=True)
    opt=torch.optim.Adam(actor.parameters(),lr=1e-5)
    before={k:v.clone() for k,v in actor.state_dict().items()}
    result=trainer.bc_update(actor,opt,data,np.random.default_rng(2),size=32,lr=2e-6,max_kl=.01)
    assert result['accepted'] and result['batch_policy_kl']<=.01
    assert any(not torch.equal(v,actor.state_dict()[k]) for k,v in before.items())
    before={k:v.clone() for k,v in actor.state_dict().items()};saved=opt.state_dict()
    result=trainer.bc_update(actor,opt,data,np.random.default_rng(3),size=32,lr=1.,max_kl=1e-15)
    assert not result['accepted']
    assert all(torch.equal(v,actor.state_dict()[k]) for k,v in before.items())
    assert saved['param_groups']==opt.state_dict()['param_groups']
    for key,values in saved['state'].items():
        for field,value in values.items():
            if isinstance(value,torch.Tensor):assert torch.equal(value,opt.state_dict()['state'][key][field])


def paired_rows(delta=1,n=12):
    return [{'candidate':{'rival':rival,'side':side,'seed':seed,'goal_diff':delta},
             'reference':{'rival':rival,'side':side,'seed':seed,'goal_diff':0}}
            for seed in range(n) for rival in ('nexto','start') for side in ('blue','orange')]


def test_confirmation_requires_complete_fresh_pairs():
    assert verdict(paired_rows(),seeds=12,seconds=60,alpha=.002,confirm=True)['passed']
    assert not verdict(paired_rows(0),seeds=12,seconds=60,alpha=.002,confirm=True)['passed']
    assert not verdict(paired_rows(n=2),seeds=2,seconds=60,alpha=.002,confirm=True)['passed']
    assert not verdict(paired_rows()[:-1],seeds=12,seconds=60,alpha=.002,confirm=True)['passed']
    assert sign_pvalue([1]*12)==2**-12


def test_resumable_evaluation_and_pause(tmp_path,monkeypatch):
    import slater_versatile_eval as evaluation
    calls=[]
    def fake_match(actor,rivals,**kwargs):
        calls.append(kwargs);return {**kwargs,'goals_for':1,'goals_against':0,'goal_diff':actor}
    monkeypatch.setattr(evaluation,'match',fake_match)
    kwargs=dict(out=tmp_path/'eval.json',identity={'sha':'fixed'},seeds=2,seconds=30,seed_base=100)
    result=evaluate(1,0,{'nexto':None},**kwargs);assert len(calls)==8 and result['done']
    evaluate(1,0,{'nexto':None},**kwargs);assert len(calls)==8
    pause=tmp_path/'pause';pause.touch()
    with pytest.raises(EvaluationPaused):evaluate(1,0,{'nexto':None},**{**kwargs,'out':tmp_path/'new.json'},pause_path=pause)


def test_real_hybrid_save_rollback_resume_and_source_protection(tmp_path,monkeypatch):
    d=dataset(tmp_path/'data');monkeypatch.setattr(trainer,'run_path',lambda name:tmp_path/name)
    source=ROOT/'vendor/nexto/nexto-model.pt';initial_hash=sha256(source)
    config={**trainer.DEFAULT,'n_envs':2,'steps_per_env':32,'epochs':1,'minibatch':32,
            'updates_per_cycle':1,'screen_seeds':1,'screen_seconds':8,'bc_every':1}
    trainer.train('run',source,d.path,cycles=1,config=config)
    run=tmp_path/'run';progress=json.loads((run/'progress.json').read_text())
    assert progress['updates']==1 and progress['phase']=='training'
    assert (run/'update_000001.pt').is_file() and (run/'cycle_0001_resume.pt').is_file()
    metrics=json.loads((run/'update_000001.json').read_text());assert len(metrics['replay_bc'])==2
    assert metrics['accepted_actor_epochs']>0 and metrics['scripted_rival_ticks']>0
    trainer.train('run',resume=True,cycles=1)
    assert json.loads((run/'progress.json').read_text())['updates']==2
    assert sha256(source)==initial_hash
    p=run/'protocol.json';doc=json.loads(p.read_text());doc['config']['actor_lr']=2e-5;atomic_json(p,doc)
    with pytest.raises(ValueError,match='changed'):trainer.train('run',resume=True,cycles=1)


def test_evaluation_student_script_is_optional_and_tick_level(actor):
    scripted=VersatileEnv({'nexto':actor},task_name='match',scripted_student=True)
    try:
        scripted.reset(71)
        for _ in range(6):_,_,_,info=scripted.step(0)
        assert info['student_script_physics_ticks']==48
        assert scripted.previous[scripted.ours][6]==1
        assert scripted.previous[scripted.ours][1]==-1
    finally:scripted.close()


def test_padded_attention_matches_unpadded_rlbot_observations(actor):
    from nexto_teacher import NextoTeacher
    from slater_versatile_env import VersatileCritic
    import slater_cycle9_native_ppo_v025 as base
    e=VersatileEnv({'nexto':actor},task_name='match')
    try:
        obs=e.reset(711)
        raw=NextoTeacher().observe(e.state,{})
        unpadded=next((q,kv,mask) for aid,q,kv,mask in raw if aid==e.ours)
        with torch.no_grad():
            padded_logits=base.logits_of(actor,base.to_tensors(obs))
            original_logits=base.logits_of(actor,base.to_tensors(unpadded))
        torch.testing.assert_close(padded_logits,original_logits,atol=1e-5,rtol=1e-5)
        assert np.sum(obs[2]<0)==4
        critic=VersatileCritic();x=base.to_tensors(obs);y=[v.clone() for v in x]
        y[1][0,np.flatnonzero(obs[2]<0),:]=99
        # Placeholders do not affect the critic's pool/ball selection either.
        y[1][0,np.flatnonzero(obs[2]<0),3]=0
        torch.testing.assert_close(critic.value_for_task(x,torch.tensor([0])),critic.value_for_task(tuple(y),torch.tensor([0])))
    finally:e.close()


def test_promotion_commit_requires_match_and_skill_gates(tmp_path,monkeypatch):
    monkeypatch.setattr(trainer,'run_path',lambda name:tmp_path/name)
    monkeypatch.setattr(trainer,'evaluate',lambda *a,**k:{'verdict':{'passed':True}})
    guard={'passed':False,'guards':{'defense':{'passed':False}}}
    monkeypatch.setattr(trainer,'skill_guard',lambda *a,**k:dict(guard))
    source=ROOT/'vendor/nexto/nexto-model.pt'
    config={**trainer.DEFAULT,'n_envs':2,'steps_per_env':32,'epochs':1,'minibatch':32,
            'updates_per_cycle':1,'screen_seeds':1,'screen_seconds':8}
    trainer.train('rejected',source,cycles=1,config=config)
    selected=json.loads((tmp_path/'rejected/selected.json').read_text())
    assert selected['promotions']==0 and selected['status']=='INITIAL_BASELINE'
    guard['passed']=True;guard['guards']={'defense':{'passed':True}}
    trainer.train('promoted',source,cycles=1,config=config)
    run=tmp_path/'promoted';selected=json.loads((run/'selected.json').read_text())
    assert selected['promotions']==1 and selected['status']=='CONFIRMED_SIMULATOR_CANDIDATE'
    assert Path(selected['checkpoint'])==run/'update_000001.pt'
    before=torch.load(selected['checkpoint'],weights_only=True)
    trainer.train('promoted',resume=True,cycles=1)
    state=json.loads((run/'progress.json').read_text())
    assert state['updates']==2 and len(state['history'])==2
    assert state['history'][1]['previous_champion']==str(run/'update_000001.pt')
    # The first promoted snapshot remains immutable while a successor is tested.
    assert sha256(run/'update_000001.pt')==selected['sha256']
