import copy,json
from pathlib import Path
import numpy as np
import pytest,torch
from duelforge.runtime import config,batch,load,sha
from duelforge.acquisition import (stage_config,drill_states,reward_components,
    possession,AcquisitionBatch,validate_recipe)
from duelforge.acquisition_experiment import fork_stage,probe_checkpoint,contact_gate
from duelforge.observation import ACTIONS
from duelforge.train import train,gae

def small():
    c=config();c.update(width=32,n_envs=4,device='cpu',torch_threads=1)
    c['ppo'].update(steps=8,epochs=1,batch_size=32)
    c['wandb']['enabled']=False;c['auto_evaluate_every']=10**9
    return c

def transition(w,hits=(1,0),terminal=False,ticks=8):
    n=len(w)
    return dict(final_world=w.copy(),info=np.tile([0,*hits,ticks,0,0],(n,1)).astype(np.float32),
                reward_parts=np.zeros((n,2,3),np.float32),terminated=np.full(n,terminal))

def test_contact_actual_hit_once_time_discount_and_potential_terminal():
    c=stage_config(small(),'contact');w=drill_states(np.random.default_rng(5),2)
    raw=transition(w,terminal=True);seen=np.zeros((2,2),bool)
    a,new,_=reward_components(c,w,raw,np.array([.5,3.]),seen)
    assert a[0,0,2]>a[1,0,2]>0 and (a[:,1,2]==0).all()
    assert (a[:,:,1]>=0).all()
    again,_,_=reward_components(c,w,raw,np.array([.5,3.]),seen|new)
    assert (again[:,:,2]==0).all()
    zero=transition(w,ticks=0);r,_,_=reward_components(c,w,zero,np.zeros(2),seen)
    assert not r.any()

@pytest.mark.parametrize('stage',['possession','trajectory'])
def test_possession_is_time_scaled_bounded_zero_sum_and_side_symmetric(stage):
    c=stage_config(small(),stage);w=drill_states(np.random.default_rng(35),4,True)
    # Ensure first car is unambiguously closer and aligned to a stationary ball.
    w[:,0,:3]=[0,0,94];w[:,0,3:9]=0
    w[:,1,:3]=[0,-400,17];w[:,2,:3]=[0,2000,17]
    w[:,1,9:12]=[0,1,0];w[:,2,9:12]=[0,-1,0];w[:,1:,3:9]=0
    lead,_,_=possession(w,c);assert (lead>0).all()
    rotated=w.copy();rotated[:,:,:15]*=np.array([-1,-1,1]*5)
    rotated[:,[1,2]]=rotated[:,[2,1]]
    other,_,_=possession(rotated,c);np.testing.assert_allclose(other,-lead,atol=2e-6)
    raw=transition(w,hits=(0,0));seen=np.zeros((4,2),bool)
    parts,_,_=reward_components(c,w,raw,np.zeros(4),seen)
    np.testing.assert_allclose(parts[:,0,1],-parts[:,1,1]);assert (parts[:,0,1]>0).all()
    assert np.abs(parts[:,:,1]).max()<=c['acquisition']['possession_rate_per_second']*8/120
    half=transition(w,hits=(0,0),ticks=4);p2,_,_=reward_components(c,w,half,np.zeros(4),seen)
    np.testing.assert_allclose(parts[:,:,1],2*p2[:,:,1])
    c['acquisition']['possession_rate_per_second']=2
    with pytest.raises(ValueError):validate_recipe(c)

def test_drills_finite_orthonormal_reproducible_and_not_fixed_kickoffs():
    a=drill_states(np.random.default_rng(4),200,True)
    np.testing.assert_array_equal(a,drill_states(np.random.default_rng(4),200,True))
    assert np.isfinite(a).all() and np.std(a[:,0,0])>500
    f=a[:,1:,9:12];u=a[:,1:,12:15]
    np.testing.assert_allclose(np.linalg.norm(f,axis=-1),1,atol=1e-6)
    np.testing.assert_allclose((f*u).sum(-1),0)
    assert np.abs(a[:,1:,0]).max()<4000 and np.abs(a[:,1:,1]).max()<5000

def test_native_contact_drill_ends_and_does_not_leak_reset_into_final_state():
    c=stage_config(small(),'contact');e=AcquisitionBatch(batch(c,n=1),c,19)
    w=drill_states(np.random.default_rng(1),1)[0]
    w[0,:3]=[0,0,94];w[0,3:9]=0
    for side in (0,1):
        w[side+1,:3]=[0,(-350 if side==0 else 350),17]
        w[side+1,3:9]=0;w[side+1,9:12]=[0,(1 if side==0 else -1),0]
    e.env.inject(0,w);e.raw=e.env.observe();e.drill[:]=True;e.elapsed[:]=0
    drive=int(np.flatnonzero((ACTIONS[:,0]==1)&(ACTIONS[:,1]==0)&(ACTIONS[:,5]==0)&(ACTIONS[:,6]==1)&(ACTIONS[:,7]==0))[0])
    found=False
    for _ in range(60):
        r=e.step(np.array([[drive,drive]],np.int64))
        if r['terminated'][0]:
            assert r['info'][0,1:3].any() and not r['truncated'][0]
            assert r['reward_parts'][0,:,2].sum()>0
            assert not np.array_equal(r['world'],r['final_world'])
            assert e.elapsed[0]==0 and not e.seen.any()
            found=True;break
    assert found,'Aligned, physically reachable ground contact must be detected'

def test_ground_jump_mask_is_only_used_in_contact_training_drills():
    c=stage_config(small(),'contact');e=AcquisitionBatch(batch(c,n=4),c,6)
    e.drill[:]=[True,False,True,False]
    raw=e._drill_mask(e.env.observe());jump=ACTIONS[:,5]>.5
    assert not raw['mask'][e.drill][:,:,jump].any()
    np.testing.assert_array_equal(raw['mask'][~e.drill],e.env.observe()['mask'][~e.drill])
    c2=stage_config(small(),'possession');f=AcquisitionBatch(batch(c2,n=4),c2,6)
    np.testing.assert_array_equal(f._drill_mask(f.env.observe())['mask'],f.env.observe()['mask'])

def test_fork_stop_bound_resume_probe_and_parent_preserved(tmp_path):
    parent=tmp_path/'parent';c=small();train(parent,c,minutes=1,max_updates=2)
    original=sha(parent/'latest.pt');state=load(parent/'latest.pt')
    child=tmp_path/'contact';fork_stage(parent/'latest.pt',child,parent/'latest.pt','contact',state['learning_transitions'])
    ck=load(child/'latest.pt')
    assert sha(child/'initial.pt')==original
    for k in state['model']:
        if k.startswith('actor.'):torch.testing.assert_close(state['model'][k],ck['model'][k],atol=0,rtol=0)
    for index,moment in ck['optimizer']['state'].items():
        assert index<14
        torch.testing.assert_close(moment['exp_avg'],state['optimizer']['state'][index]['exp_avg'],atol=0,rtol=0)
    target=ck['learning_transitions']+75
    count=train(child,minutes=1,stop_at_transitions=target)
    assert target<=count<target+64
    cfg=load(child/'latest.pt')['config'];assert cfg['acquisition']['stage']=='contact'
    again=train(child,minutes=1,max_updates=1);assert again>count
    child_hash=sha(child/'latest.pt')
    probe=probe_checkpoint(child/'latest.pt',parent/'latest.pt',0x80000011,pairs=2,seconds=.5)
    assert probe['games']==4 and len(probe['by_color'])==2
    assert sha(child/'latest.pt')==child_hash and sha(parent/'latest.pt')==original
    race=probe_checkpoint(child/'latest.pt',parent/'latest.pt',0x80000012,pairs=2,seconds=.5,race=True)
    assert race['wins']+race['draws']+race['losses']==4
    with pytest.raises(FileExistsError):fork_stage(parent/'latest.pt',child,parent/'latest.pt','contact',0)

def test_gate_requires_reliability_speed_and_no_large_parent_regression():
    baseline={'success_rate':.95,'median_contact_seconds':1.5}
    assert contact_gate({'success_rate':.94,'median_contact_seconds':1.6},baseline)
    assert not contact_gate({'success_rate':.5,'median_contact_seconds':1.0},baseline)
    assert not contact_gate({'success_rate':.95,'median_contact_seconds':3.},baseline)
    assert not contact_gate({'success_rate':.86,'median_contact_seconds':1.5},baseline)

def test_kl_controller_is_bounded_and_does_not_change_a_healthy_rate():
    from duelforge.acquisition import adapt_learning_rate
    from types import SimpleNamespace
    c=stage_config(small(),'contact');opt=SimpleNamespace(param_groups=[{'lr':5e-5}])
    assert adapt_learning_rate(opt,c,.003)==5e-5
    assert adapt_learning_rate(opt,c,.00001)>5e-5
    for _ in range(100):adapt_learning_rate(opt,c,0)
    assert opt.param_groups[0]['lr']==3e-4
    for _ in range(100):adapt_learning_rate(opt,c,.1)
    assert opt.param_groups[0]['lr']==1e-5

def test_controller_creates_independent_run_bounds_steps_and_reports(tmp_path):
    from duelforge.acquisition_experiment import start,active,pause,initialize
    source=tmp_path/'potential01';train(source,small(),minutes=1,max_updates=1)
    original=sha(source/'latest.pt');root=tmp_path/'contact01'
    state=start(root,source,steps=100,chunk_steps=100,max_checks=1)
    assert state['additional_steps']>=100 and state['additional_steps']<164
    assert state['stage_index']==0 and len(state['probes'])==1
    assert active(root)==root/'01_contact'
    ck=load(active(root)/'latest.pt');assert ck['config']['acquisition']['stage']=='contact'
    assert sha(source/'latest.pt')==original and sha(root/'baseline.pt')==original
    first=state['additional_steps'];pause(root)
    assert (root/'STOP').is_file() and (active(root)/'STOP').is_file()
    state=start(root,source,steps=64,chunk_steps=64,max_checks=1)
    assert state['additional_steps']>first and len(state['probes'])==2
    # Recipe corruption must be rejected rather than silently changing a run.
    file=root/'curriculum.json';bad=json.loads(file.read_text());bad['recipe']['checkpoint_steps']=3
    file.write_text(json.dumps(bad))
    with pytest.raises(ValueError):initialize(root,source)

def test_all_stage_transitions_are_resumable_and_keep_frozen_baseline(tmp_path,monkeypatch):
    from duelforge import acquisition_experiment as experiment
    from duelforge.acquisition import RECIPE
    for k in ('contact_min_steps','possession_min_steps'):monkeypatch.setitem(RECIPE,k,64)
    # Gate scoring is covered independently above. This test forces gates only
    # to exercise orchestration of all three real native/PPO stage transitions.
    def passed(*args,**kwargs):
        return {'success_rate':1.,'median_contact_seconds':1.,'race_score':1.,'raw':{}}
    monkeypatch.setattr(experiment,'probe_checkpoint',passed)
    source=tmp_path/'potential01';train(source,small(),minutes=1,max_updates=1)
    identity=sha(source/'latest.pt');root=tmp_path/'curriculum'
    state=experiment.start(root,source,steps=300,chunk_steps=64,max_checks=3)
    assert state['stage_index']==2 and len(state['probes'])==3
    assert experiment.active(root).name=='03_trajectory'
    assert sha(root/'baseline.pt')==identity and sha(source/'latest.pt')==identity
    for i in range(3):
        folder=experiment.stage_folder(root,i)
        assert sha(folder/'initial.pt')==identity
        ck=load(folder/'latest.pt');assert ck['config']['acquisition']['stage']==('contact','possession','trajectory')[i]
