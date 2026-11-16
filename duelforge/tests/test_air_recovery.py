import numpy as np
import torch
from duelforge.air_recovery import air_states,elevated_hits,AirBatch
from duelforge.acquisition import stage_config
from duelforge.runtime import config,batch,load,sha
from duelforge.observation import ACTIONS

def cfg():
    c=stage_config(config(),'trajectory');c.update(n_envs=4,width=32,device='cpu',torch_threads=1)
    c['ppo'].update(steps=8,epochs=1,batch_size=32);c['wandb']['enabled']=False;c['auto_evaluate_every']=10**9
    c['air_recovery']={'fraction':.4,'seconds':1.4,'approach_weight':.02,'contact_bonus':1.}
    return c

def test_air_contacts_require_real_high_ball_and_lifted_car():
    w=air_states(np.random.default_rng(1),1);raw={'final_world':w.copy(),'info':np.array([[0,1,1,8,0,0]],np.float32)}
    assert not elevated_hits(w,raw).any()
    raw['final_world'][:,1,2]=100;assert elevated_hits(w,raw)[0,0]
    raw['final_world'][:,0,2]=100;before=w.copy();before[:,0,2]=100
    assert not elevated_hits(before,raw).any()

def test_air_masks_are_full_native_and_jump_can_make_valid_contact():
    c=cfg();e=AirBatch(batch(c,n=1),c,17)
    w=air_states(np.random.default_rng(6),1)[0];w[0,:3]=[0,0,310];w[0,3:9]=0
    w[1,:3]=[0,-150,17];w[1,9:12]=[0,1,0];w[1,3:6]=[0,300,0]
    w[2,:3]=[3000,3000,17];w[2,3:9]=0
    e.env.inject(0,w);e.raw=e.env.observe();e.drill[:]=True;e.seen[:]=False;e.elapsed[:]=0
    np.testing.assert_array_equal(e.observe()['mask'],e.env.observe()['mask'])
    jump=int(np.flatnonzero((ACTIONS[:,5]==1)&(ACTIONS[:,2]==0)&(ACTIONS[:,4]==0)&(ACTIONS[:,6]==0))[0])
    assert e.observe()['mask'][0,0,jump]
    success=False
    for _ in range(21):
        r=e.step(np.array([[jump,10]],np.int64))
        if r['reward_parts'][0,0,2]>0:
            assert r['terminated'][0] and r['final_world'][0,1,2]>65
            success=True;break
    assert success

def test_air_fork_preserves_source_and_real_ppo_resumes(tmp_path):
    from duelforge.train import train
    from duelforge.air_experiment import setup,probe
    parent=tmp_path/'parent';train(parent,cfg(),minutes=1,max_updates=1)
    identity=sha(parent/'latest.pt');p=load(parent/'latest.pt');root=tmp_path/'air01'
    folder=setup(root,parent/'latest.pt');child=load(folder/'latest.pt')
    for k in p['model']:
        if k.startswith('actor.'):torch.testing.assert_close(p['model'][k],child['model'][k],atol=0,rtol=0)
    assert child['config']['ppo']['entropy']==.01
    count=train(folder,minutes=1,max_updates=2);assert count>p['learning_transitions']
    child_hash=sha(folder/'latest.pt');r=probe(folder/'latest.pt',pairs=2)
    assert r['trials']==4 and sha(folder/'latest.pt')==child_hash
    assert sha(parent/'latest.pt')==identity and sha(root/'baseline.pt')==identity

def test_air_normal_play_keeps_scoring_reward_and_concede_penalty():
    c=cfg()
    for direction in (-1,1):
        e=AirBatch(batch(c,n=1),c,17)
        w=air_states(np.random.default_rng(2),1)[0]
        w[0,:3]=[0,direction*4800,200];w[0,3:6]=[0,direction*1600,0]
        w[1,:3]=[-3000,0,17];w[2,:3]=[3000,0,17];w[1:,3:9]=0
        e.env.inject(0,w);e.raw=e.env.observe();e.drill[:]=False
        for _ in range(15):
            r=e.step(np.array([[10,10]],np.int64))
            if r['terminated'][0]:
                np.testing.assert_array_equal(r['reward_parts'][0,:,0],[direction,-direction])
                assert r['rewards'][0,0]*direction>0 and r['rewards'][0,1]*direction<0
                break
        else:raise AssertionError('Physical goal must be registered')

def test_existing_air_skill_is_diagnosed_without_training(tmp_path,monkeypatch):
    from duelforge import air_experiment
    from duelforge.train import train
    import duelforge.train as training
    parent=tmp_path/'parent';train(parent,cfg(),minutes=1,max_updates=1)
    identity=sha(parent/'latest.pt')
    monkeypatch.setattr(air_experiment,'probe',lambda *a,**k:{'jump_used_rate':1.,'elevated_contact_rate':.75})
    monkeypatch.setattr(air_experiment,'report',lambda root:None)
    def forbidden(*a,**k):raise AssertionError('Unnecessary recovery training must not start')
    monkeypatch.setattr(training,'train',forbidden)
    state=air_experiment.start(tmp_path/'air01',parent/'latest.pt',steps=64)
    assert state['status']=='air_skill_present_in_controlled_probe' and state['additional_steps']==0
    assert sha(parent/'latest.pt')==identity
