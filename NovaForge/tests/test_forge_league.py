import copy
import json
from pathlib import Path

import numpy as np
import pytest
import torch

from nova.core import ROOT,check_model,sha256
from nova.forge_env import ForgeEnv
from nova.forge_eval import action,paired,judgement
from nova.forge_models import CORE,FAMILIES,DirectActor,DirectController,contract,new_model,save_actor
from nova.forge_league import read,validate,weighted_pool
from nova.chronos import ChronosPPO
from nova.models import save_ppo


def settings():
    cfg=read(ROOT/'configs/forge_league.json')
    cfg.update(match_seconds=.2,warmup_rollouts=1,checkpoint_decisions=8,pilot_decisions=16,
        specialist_decisions=16,block_decisions=16)
    cfg['ppo'].update(n_steps=8,batch_size=8,n_epochs=1)
    cfg['evaluation'].update(pairs=1,confirmation_pairs=1,seconds=.2,test_pairs=1,test_seconds=.2)
    return validate(cfg)


@pytest.mark.parametrize('family',FAMILIES)
def test_initial_logits_exact_then_core_learns_and_resumes_without_oracle(tmp_path,family):
    torch.set_num_threads(1);cfg=settings();env=ForgeEnv(cfg,family,[dict(name='scorer')])
    try:
        obs,_=env.reset(seed=271)
        initial=DirectActor(family);p=save_actor(initial,tmp_path/'initial.lt',family)
        with torch.inference_mode():
            x=torch.from_numpy(obs[:CORE[family]+3])[None,:]
            torch.testing.assert_close(initial(x),initial.core(x[:,:CORE[family]]),rtol=0,atol=0)
        model=new_model(cfg,env,family,True,p)
        observations=torch.from_numpy(np.repeat(obs[None,:],2,0))
        changed=observations.clone();changed[:,-9:]=torch.linspace(-50,50,9)
        with torch.no_grad():
            # Windows BLAS can round identical inputs differently in different
            # batch rows. Compare each row with itself under private changes.
            torch.testing.assert_close(model.policy.logits(observations),model.policy.logits(changed),rtol=0,atol=0)
        observations.requires_grad_(True)
        private_gradient=torch.autograd.grad(model.policy.logits(observations).sum(),observations)[0][:,-9:]
        assert torch.count_nonzero(private_gradient)==0
        before={k:v.clone() for k,v in model.policy.actor.core.state_dict().items()}
        model.learn(8)
        assert all(torch.equal(v,before[k]) for k,v in model.policy.actor.core.state_dict().items())
        model.learn(16,reset_num_timesteps=False)
        assert any(not torch.equal(v,before[k]) for k,v in model.policy.actor.core.state_dict().items())
        full=tmp_path/'full.zip';save_ppo(model,full,contract=contract(family))
        restored=ChronosPPO.load(full,env=env,device='cpu')
        assert restored.num_timesteps==24 and restored.chronos_updates==3
        assert restored.policy.privileged and restored.policy.family==family
        assert len(restored.policy.optimizer.state)>0
        np.testing.assert_array_equal(model.predict(obs,deterministic=True)[0],restored.predict(obs,deterministic=True)[0])
        exported=save_actor(restored.policy.actor,tmp_path/'trained.lt',family,timesteps=24)
        script=torch.jit.load(str(exported));assert all('value_net' not in k and 'anchor' not in k for k in script.state_dict())
        with torch.no_grad():torch.testing.assert_close(script(x),restored.policy.actor(x),rtol=0,atol=0)
        controls=DirectController(exported);controls.reset(env.arena.state,env.arena.agent,np.random.default_rng(271))
        held=controls.controls_for_ticks(env.arena.state,2)
        assert not held.any() and controls.pending[0]==7
    finally:env.close()


def test_critic_privilege_mask_and_seeded_opponent_preparation(tmp_path):
    torch.set_num_threads(1);cfg=settings();env=ForgeEnv(cfg,'chronos',[dict(name='scorer')])
    try:
        obs,_=env.reset(seed=271);actor=save_actor(DirectActor('chronos'),tmp_path/'initial.lt','chronos')
        policy=new_model(cfg,env,'chronos',False,actor).policy
        batch=torch.from_numpy(np.repeat(obs[None,:],2,0));changed=batch.clone();changed[:,-9:]=999
        with torch.no_grad():
            policy.value_net[-1].weight.fill_(.1)
            torch.testing.assert_close(policy.predict_values(batch),policy.predict_values(changed),rtol=0,atol=0)
        assert env.arena.opponent.cached is not None
        prepared=env.arena.opponent.cached[1].copy()
        private_again=env.arena.opponent.prepare(env.arena.state)
        np.testing.assert_array_equal(obs[-9:],private_again)
        result=env.step(int(np.flatnonzero(obs[228:318])[0]))
        # Consuming a prepared frame doesn't query it a second time.
        assert env.arena.state.tick_count==8
        initial,_=env.reset(seed=271);np.testing.assert_array_equal(initial,obs)
        again=env.step(int(np.flatnonzero(obs[228:318])[0]))
        np.testing.assert_array_equal(again[0],result[0]);assert again[1:4]==result[1:4]
    finally:env.close()


def test_multi_goal_match_is_not_first_goal_and_potential_telescopes():
    torch.set_num_threads(1);cfg=settings();cfg['match_seconds']=1
    env=ForgeEnv(cfg,'chronos',[dict(name='scorer')],scenario='kickoff',side=0)
    try:
        obs,_=env.reset(seed=222)
        state=copy.deepcopy(env.arena.state)
        state.ball.position=np.array([0,5100,100],np.float32)
        state.ball.linear_velocity=np.array([0,3000,0],np.float32)
        env.arena.state=env.arena.engine.set_state(state,{})
        obs=env.observation();phi=env.arena.potential(env.arena.state)
        discounted=0.;goal_term=0.;discount=1.;scored=False
        for _ in range(15):
            obs,reward,terminal,truncated,info=env.step(int(np.flatnonzero(obs[228:318])[0]))
            discounted+=discount*reward;goal_term+=discount*cfg['objective']['goal']*info['goal']
            if info['goal']:
                scored=True;assert not terminal
                assert env.previous.tolist()==[0.]*8
                assert obs[225]==pytest.approx(env.score/5)
            if terminal:
                goal_term+=discount*cfg['objective']['match_result']*info['outcome'];break
            discount*=cfg['ppo']['gamma']
        assert scored and terminal and not truncated
        assert info['goals_for']>=1 and info['episode']['l']==15
        assert discounted-goal_term==pytest.approx(-phi,abs=1e-7)
    finally:env.close()


def test_paired_guard_needs_replication_and_fresh_confirmation_is_separate():
    from nova.forge_eval import SEEDS
    cfg=settings();a=[];b=[]
    for opponent in ('one','two'):
        for seed in range(4):
            for side in (0,1):
                row=dict(opponent=opponent,seed=seed,side=side,goals_for=1,goals_against=0)
                a.append(dict(row,outcome=1));b.append(dict(row,outcome=-1))
    assert judgement(paired(a,b),cfg['evaluation'])=='improved'
    assert judgement(paired(b,a),cfg['evaluation'])=='regressed'
    assert judgement(paired(a[:4],b[:4]),cfg['evaluation'])=='uncertain'
    assert judgement(paired(a,a),cfg['evaluation'])=='uncertain'
    with pytest.raises(ValueError):paired(a,b[:-1])
    assert len(set(SEEDS.values()))==3


def test_configuration_validation_rejects_silent_reward_or_budget_edits():
    cfg=settings();cfg['objective']['goal']=float('nan')
    with pytest.raises(ValueError):validate(cfg)
    cfg=settings();cfg['pilot_decisions']=9
    with pytest.raises(ValueError):validate(cfg)


@pytest.mark.parametrize('family',FAMILIES)
def test_actual_pretrained_initialization_and_causal_queue(tmp_path,family,request):
    if not request.config.getoption('--teachers'):pytest.skip('Use --teachers with downloaded native models')
    from nova.giga_teachers import GigaNetwork
    from nova.teachers import verify_teacher
    torch.set_num_threads(1);cfg=settings()
    actor=DirectActor(family);native=GigaNetwork(verify_teacher(family),family)
    actor.core.load_state_dict(native.state_dict())
    path=save_actor(actor,tmp_path/(family+'.lt'),family)
    env=ForgeEnv(cfg,family,[dict(name='chronos')])
    try:
        obs,_=env.reset(seed=1234)
        command=env.arena.opponent.base.pending
        assert command is not None and command[0]==7
        np.testing.assert_array_equal(obs[-9:-1],command[1]);assert obs[-1]==pytest.approx(7/8)
        with torch.inference_mode():
            x=torch.from_numpy(obs[:CORE[family]+3])[None,:]
            torch.testing.assert_close(actor(x),native(x[:,:CORE[family]]),rtol=0,atol=0)
        env.step(action(torch.jit.load(str(path)),obs,family))
        assert env.arena.opponent.base.last_call==8 # next frame prepared once
    finally:env.close()
