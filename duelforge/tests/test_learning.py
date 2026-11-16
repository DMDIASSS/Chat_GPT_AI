import copy
import numpy as np
import pytest
from duelforge.runtime import config,ROOT,validate
from duelforge.learning import entropy_coefficient,bootstrap_parts

def cfg():return config(ROOT/'config_learning.json')

def raw():
    w=np.zeros((2,3,32),np.float32);w[:,0,:3]=[1000,0,94];w[:,1:,2]=17;w[:,1,3]=1000;w[:,2,3]=-1000
    return {'world':w},{'final_world':w.copy(),'info':np.asarray([[0,1,0,8,5,8],[0,0,0,8,5,8]],np.float32)}

def test_entropy_high_start_decay_and_resume_counter():
    c=cfg();assert entropy_coefficient(c,0)==.03
    assert entropy_coefficient(c,5000000)==pytest.approx(.0165)
    assert entropy_coefficient(c,10000000)==pytest.approx(.003)
    assert entropy_coefficient(c,90000000)==pytest.approx(.003)
    c['ppo'].pop('entropy_schedule');assert entropy_coefficient(c,0)==.01

def test_approach_signal_has_direction_no_jump_or_backwards_bonus():
    c=cfg();b,a=raw();r=bootstrap_parts(c,b,a,0)
    assert 0<r[0,0,0]<.01 and r[0,1,0]==0 and r[0,0,1]==pytest.approx(.15)
    # Reverse orientation never changes reward: motion toward the ball matters.
    a['final_world'][:,1,9]=-1
    np.testing.assert_array_equal(r,bootstrap_parts(c,b,a,0))
    # Controls and airborne flags alone cannot earn reward.
    a['final_world'][:,:,3:6]=0;a['final_world'][:,1:,26]=1;a['info'][:,1:3]=0
    np.testing.assert_array_equal(bootstrap_parts(c,b,a,0),0)

def test_fade_partial_ticks_and_disabled_legacy():
    c=cfg();b,a=raw();full=bootstrap_parts(c,b,a,0)
    np.testing.assert_allclose(bootstrap_parts(c,b,a,10000000),full*.5)
    np.testing.assert_array_equal(bootstrap_parts(c,b,a,20000000),0)
    a['info'][:,3]=4;half=bootstrap_parts(c,b,a,0);np.testing.assert_allclose(half[:,:,0],full[:,:,0]/2)
    np.testing.assert_array_equal(bootstrap_parts(config(),b,a,0),0)

def test_invalid_exploration_or_reward_budget_rejected():
    c=cfg();c['ppo']['entropy_schedule']['start']=.5
    with pytest.raises(ValueError):validate(c)
    c=cfg();c['bootstrap']['contact_weight']=3
    with pytest.raises(ValueError):validate(c)

def test_arena_autotune_requires_complete_updates_and_material_gain():
    from duelforge.profile import select_arenas
    rows=[{'arenas':64,'measured_updates':3,'median_learner_transitions_s':10000},{'arenas':128,'measured_updates':3,'median_learner_transitions_s':10500}]
    assert select_arenas({'full_training':rows})==64
    rows[1]['median_learner_transitions_s']=12000;assert select_arenas({'full_training':rows})==128
    rows[1]['measured_updates']=1;assert select_arenas({'full_training':rows})==64

def test_frozen_actor_only_logits_and_actions_identical():
    import torch
    from duelforge.model import ActorCritic
    torch.set_num_threads(1);m=ActorCritic(32).eval();actor=torch.jit.script(m.actor);x=torch.randn(25,109);legal=torch.rand(25,90)>.3;legal[:,8]=True
    with torch.inference_mode():
        a=m(x,legal)[0];b=actor(x).masked_fill(~legal,-1e9)
    torch.testing.assert_close(a,b,rtol=0,atol=0);assert torch.equal(a.argmax(-1),b.argmax(-1))
