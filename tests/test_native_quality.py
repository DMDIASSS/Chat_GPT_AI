from pathlib import Path
from types import SimpleNamespace
import copy,json
import numpy as np
import pytest
import torch
from torch import nn
from slater_native_actor import NativeActor,observation,action_mask
from slater_native_eval import Controller,paired_verdict
from slater_native_campaign import checkpoints
from nexto_teacher import nexto_actions

@pytest.fixture
def archive(tmp_path):
    path=tmp_path/'1000';path.mkdir();torch.manual_seed(4)
    shared=nn.Sequential(nn.Linear(230,64),nn.LayerNorm(64),nn.ReLU(),nn.Linear(64,64),nn.LayerNorm(64),nn.ReLU())
    policy=nn.Sequential(nn.Linear(64,64),nn.LayerNorm(64),nn.ReLU(),nn.Linear(64,64),nn.LayerNorm(64),nn.ReLU(),nn.Linear(64,90))
    critic=nn.Sequential(nn.Linear(64,1))
    for name,module in (('SHARED_HEAD.lt',shared),('POLICY.lt',policy),('CRITIC.lt',critic)):
        torch.jit.script(module).save(str(path/name))
    (path/'RUNNING_STATS.json').write_text('{}')
    return path,shared,policy

def test_native_reader_matches_module_and_preserves_files(archive):
    path,shared,policy=archive;before={p:p.read_bytes() for p in path.iterdir()}
    model=NativeActor(path);x=torch.randn(5,230)
    with torch.no_grad():assert torch.allclose(model(x),policy(shared(x)),atol=1e-6)
    assert model.width==64 and model.depth==2
    assert all(p.read_bytes()==b for p,b in before.items())

def sample_car(team=0):
    return {'id':team+1,'team':team,'pos':[0,0,17],'vel':[0,0,0],'ang':[0,0,0],
        'rot':np.eye(3).T.reshape(-1).tolist(),'boost':33.,'ground':True,'jumped':False,
        'double_jumped':False,'flipped':False,'air_time':0.,'demo':False,'world_contact':False,
        'contact_normal':[0,0,0],'previous':[0]*8}

def test_observation_preserves_native_timer_accessor_quirk():
    timers=np.arange(34,dtype=float);p={'ball':sample_car(),'timers':timers.tolist(),'cars':[sample_car(),sample_car(1)]}
    blue=observation(p,1);orange=observation(p,2)
    assert blue.shape==(230,) and orange.shape==(230,)
    assert blue[17]==1 and blue[18]==pytest.approx(1/33)
    assert orange[17]==1 and orange[18]==pytest.approx(1/2)
    # Two absent mate slots, one present opponent, then two absent opponents.
    assert np.array_equal(blue[80:140],np.zeros(60)) and blue[169]==1

def test_mask_matches_pinned_index_edge_and_boost_jump_order():
    car=sample_car();car.update(ground=False,air_time=2,flipped=True,boost=0)
    mask=action_mask(car);assert not mask[24] and not mask[nexto_actions()[:,6].astype(bool)].any()
    car.update(world_contact=True,contact_normal=[0,0,1]);mask=action_mask(car)
    assert mask[nexto_actions()[:,5].astype(bool)].all()

def test_native_cadence_holds_one_tick_before_new_controls(archive,monkeypatch):
    import slater_native_eval as evaluator
    model=NativeActor(archive[0]);control=Controller(model)
    state=SimpleNamespace(cars={k:SimpleNamespace(team_num=team,physics=SimpleNamespace(position=np.array([0,(-1 if team==0 else 1)*4608,17])))
        for k,team in (('blue-0',0),('orange-0',1))},ball=SimpleNamespace(position=np.array([0,0,93])))
    monkeypatch.setattr(evaluator,'packet',lambda *args:({}, {'blue-0':1,'orange-0':2}))
    choices=iter((18,22));monkeypatch.setattr(evaluator,'infer',lambda *args:next(choices))
    actions=[control.controls(state,'blue-0',{},None,tick,False,None) for tick in range(10)]
    assert np.array_equal(actions[0],np.zeros(8))
    assert all(np.array_equal(a,nexto_actions()[18]) for a in actions[1:9])
    assert np.array_equal(actions[9],nexto_actions()[22])

def paired_records():
    protocol={'seconds':60,'seed_base':100,'seeds':8,'rivals':{'one':{},'two':{}},'tasks':['match']}
    records=[]
    for j in range(8):
        for rival in protocol['rivals']:
            for side in ('blue','orange'):
                for candidate in ('leader','reference'):
                    records.append({'candidate':candidate,'rival':rival,'side':side,'seed':100+997*j,
                        'task':'match','goal_diff':1 if candidate=='leader' else 0})
    return {'protocol':protocol,'records':records}

def test_confirmation_requires_complete_pairs_and_favors_strict_improvement():
    result=paired_records();assert paired_verdict(result,'leader','reference')['passed']
    result['records']=result['records'][2:]
    with pytest.raises(ValueError,match='Incomplete'):paired_verdict(result,'leader','reference')

def test_ties_and_duplicate_matches_are_not_confirmation():
    result=paired_records()
    for row in result['records']:row['goal_diff']=0
    assert not paired_verdict(result,'leader','reference')['passed']
    result['records'].append(result['records'][0])
    with pytest.raises(ValueError,match='Duplicate'):paired_verdict(result,'leader','reference')

def test_checkpoint_inventory_ignores_incomplete_and_non_numbered_folders(archive):
    path=archive[0];(path.parent/'2000').mkdir();(path.parent/'notes').mkdir()
    assert checkpoints(path.parent)==[path]
