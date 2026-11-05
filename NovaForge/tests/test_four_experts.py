import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
import torch
from nova.core import ROOT,atomic_json,write_model_meta,sha256
from nova.chronos import CHRONOS_CONTRACT
from nova.training import load_config
from nova.triad_selector import Context,FOUR_NAMES,FOUR_CONTRACT,CONTRACT,SelectorEnv,SelectorPolicy,save_actor,Gate
from nova.fusion_selection import parameter_fingerprint,ranking


def test_four_option_masks_and_original_contract_remain_distinct():
    old=Context();new=Context(names=FOUR_NAMES);features=np.zeros(225,np.float32)
    assert old.observation(features).shape==(234,) and new.observation(features).shape==(236,)
    assert CONTRACT['actions']==['chronos','galactus','ripple']
    new.advance(3)
    for _ in range(7):
        np.testing.assert_array_equal(new.observation(features)[-4:],[0,0,0,1])
        with pytest.raises(ValueError):new.advance(0)
        new.advance(3)
    assert new.observation(features)[-4:].sum()==4


def test_policy_fingerprints_deduplicate_actual_parameters_and_ranking_uses_match_points():
    actor=torch.nn.Linear(225,90);clone=copy.deepcopy(actor)
    assert parameter_fingerprint(actor)==parameter_fingerprint(clone)
    with torch.no_grad():clone.bias[0]+=1
    assert parameter_fingerprint(actor)!=parameter_fingerprint(clone)
    rows={'a':[dict(outcome=1,goals_for=1,goals_against=0)],'b':[dict(outcome=0,goals_for=10,goals_against=10)]}
    assert ranking(rows,['b','a'])==['a','b']


def test_fusion_selection_fresh_confirmation_and_four_creation_preserve_sources(tmp_path,monkeypatch):
    import nova.fusion_selection as f
    import nova.teachers as teachers
    import nova.triad_selector as selector
    root=tmp_path/'novaforge';(root/'configs').mkdir(parents=True)
    cfg=load_config(ROOT/'configs/chronos.json');atomic_json(root/'configs/chronos.json',cfg)
    run=root/'runs/fusion01';(run/'checkpoints').mkdir(parents=True)
    atomic_json(run/'config.json',cfg);atomic_json(run/'fusion_state.json',dict(phase='complete'))
    original=torch.nn.Linear(225,90);a=copy.deepcopy(original);b=copy.deepcopy(original)
    with torch.no_grad():a.bias[0]+=1;b.bias[1]+=1
    for step,actor in [(100,a),(200,b),(50,a)]:f.save_frozen(actor,run/f'checkpoints/step_{step:012d}.pt',step)
    # Include the pruned-full-checkpoint case: a retained .lt snapshot must be discovered.
    (run/'snapshots').mkdir();f.save_frozen(b,run/'snapshots/step_000000000200.lt',200)
    monkeypatch.setattr(f,'checkpoint_paths',lambda r:sorted(list((r/'checkpoints').glob('*.pt'))+list((r/'snapshots').glob('*.lt'))))
    monkeypatch.setattr(f,'ROOT',root);monkeypatch.setattr(f,'BASE',tmp_path/'triadbot/fusion_selection')
    monkeypatch.setattr(selector,'RUNS',tmp_path/'triadbot/runs')
    monkeypatch.setattr(teachers,'fetch_teachers',lambda *a:None);monkeypatch.setattr(teachers,'verify_teacher',lambda *a:tmp_path)
    monkeypatch.setattr(f,'GigaNetwork',lambda *a:copy.deepcopy(original))
    seeds=[]
    def fake_stage(cfg,actors,pairs,seconds,seed,stop):
        seeds.append(seed);result={}
        for name in actors:
            # Deliberately let the runner-up win fresh confirmation.
            score=0 if name=='original_chronos' else (1 if ('fusion_02' in name)==(seed==391000001) else -1)
            result[name]=[dict(opponent=op,scenario='match',seed=seed+i,side=side,outcome=score,
                goals_for=int(score>0),goals_against=int(score<0)) for i,op in enumerate(('chronos','galactus','nexto','ripple')) for side in (0,1)]
        return result
    monkeypatch.setattr(f,'stage',fake_stage)
    before={p.name:sha256(p) for p in (run/'checkpoints').iterdir()}
    out=f.select_best('fusion01',pairs=1,seconds=1,confirmation_pairs=1,confirmation_seconds=1)
    report=json.loads((out/'report.json').read_text())
    assert seeds==[371000001,391000001] and len(report['candidates'])==2
    assert report['screening_ranking'][0]!=report['selected']['label']
    assert before=={p.name:sha256(p) for p in (run/'checkpoints').iterdir()}
    new=f.create_four('selector04',direct=True)
    assert json.loads((new/'config.json').read_text())['selector_experts']==list(FOUR_NAMES)
    assert sha256(new/'frozen_fusion.pt')==report['selected_actor_sha256']
    with pytest.raises(ValueError):f.create_four('selector04',direct=True)


def test_demo_stress_opponent_targets_the_other_car_instead_of_the_ball():
    from nova.teachers import DemoChaser,Scripted
    own=NS(team_num=0,on_ground=True,boost_amount=100,physics=NS(position=np.zeros(3),linear_velocity=np.zeros(3),forward=np.array([0,1,0]),right=np.array([1,0,0])))
    other=NS(team_num=1,physics=NS(position=np.array([1000,1000,0]),linear_velocity=np.zeros(3)))
    state=NS(cars={'a':own,'b':other},ball=NS(position=np.array([-1000,1000,93.])))
    demo=DemoChaser();demo.reset(state,'a',None);normal=Scripted();normal.reset(state,'a',None)
    assert demo.act(state)[1]>0 and normal.act(state)[1]<0


def test_four_selector_training_and_export_keep_all_experts_frozen(tmp_path,request):
    if not request.config.getoption('--teachers'):pytest.skip('Requires pinned experts')
    from nova.fusion_selection import save_frozen
    from stable_baselines3 import PPO
    from nova import research
    torch.set_num_threads(1)
    frozen=tmp_path/'frozen_fusion.pt';save_frozen(torch.nn.Linear(225,90),frozen,100)
    cfg=load_config(ROOT/'configs/chronos.json');cfg.update(workers=1,device='cpu',selector_experts=list(FOUR_NAMES),fusion_teacher=dict(path=frozen.name,sha256=sha256(frozen)))
    cfg['league']['weights']={'demochaser':1};cfg['env'].update(episode_seconds=.3,no_touch_seconds=1)
    env=SelectorEnv(cfg,tmp_path)
    try:
        model=PPO(SelectorPolicy,env,n_steps=16,batch_size=16,n_epochs=1,device='cpu',seed=271)
        obs,_=env.reset(seed=271);before={n:p.clone() for n,p in env.teacher.fusion.named_parameters()}
        model.learn(32)
        assert all(torch.equal(before[n],p) and not p.requires_grad for n,p in env.teacher.fusion.named_parameters())
        path=tmp_path/'latest.pt';save_actor(model,path,'breakout',cfg['fusion_teacher']);gate=Gate(path)
        assert gate.names==FOUR_NAMES and gate.choose(obs[:225])==int(model.predict(obs,deterministic=True)[0])
        assert gate.last_free_choice_probabilities.keys()==dict.fromkeys(FOUR_NAMES).keys()
        frozen.write_bytes(b'changed')
        with pytest.raises(ValueError):Gate(path)
    finally:env.close()
