import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
from nova import six_experts as s
from nova.triad_selector import SIX_NAMES,SIX_CONTRACT,Context,contract_for
from rlgym_tools.rocket_league.misc.serialize import deserialize_game_state

FIXTURES=json.loads((Path(__file__).parent/'fixtures/six_reference.json').read_text())


@pytest.mark.parametrize('kind',['ducky','rain','megabyte'])
def test_observations_match_original_compiled_cpp_across_colors_and_scenarios(kind):
    for case in FIXTURES['cases']:
        state=deserialize_game_state(np.array(case['state'],np.float32));agent=next(k for k,c in state.cars.items() if c.team_num==case['side'])
        reference=case['reference'][kind]
        actual=s.features(state,agent,np.array(case['previous'],np.float32),np.random.default_rng(2),kind,
            np.array(case['predictions'],np.float32),opponent_slot=reference['opponent_slot'])
        np.testing.assert_allclose(actual,reference['features'],atol=2e-6,rtol=2e-6)


class Pool:
    def __init__(self):self.calls=[]
    def reset(self,state,agent,rng):pass
    def command(self,name,state,previous):
        self.calls.append((name,state.tick_count,previous.copy()))
        return np.array([1 if name=='rain' else -1,0,0,0,0,0,0,0],np.float32)


def test_rain_keeps_six_tick_inference_and_five_tick_planned_delay():
    pool=Pool();clock=s.Clock(pool);clock.fixed_choice=SIX_NAMES.index('rain');state=NS(tick_count=0)
    clock.reset(state,0,np.random.default_rng(7));commands=[]
    for frame in range(0,24,2):
        state.tick_count=frame;commands.extend(clock.controls_for_ticks(state,2))
    assert [(n,t) for n,t,_ in pool.calls]==[('rain',0),('rain',6),('rain',12),('rain',18)]
    commands=np.array(commands)
    assert not commands[:5].any() and np.all(commands[5:,0]==1)
    assert clock.counts.sum()==3


def test_switch_cancels_outgoing_pending_control_and_queries_only_selected_expert():
    pool=Pool();clock=s.Clock(pool);clock.fixed_choice=4;state=NS(tick_count=0)
    clock.reset(state,0,np.random.default_rng(7));commands=[]
    for frame in range(0,24,2):
        if frame==8:clock.fixed_choice=2
        state.tick_count=frame;commands.extend(clock.controls_for_ticks(state,2))
    assert [(n,t) for n,t,_ in pool.calls]==[('rain',0),('rain',6),('fusion',8),('fusion',16)]
    commands=np.array(commands)
    assert np.all(commands[5:15,0]==1) and np.all(commands[15:,0]==-1)
    assert pool.calls[2][2][0]==1 # Incoming expert observes actually held control.


def test_gate_queries_do_not_change_expert_random_stream(monkeypatch):
    class RandomPool(Pool):
        def reset(self,state,agent,rng):self.rng=rng;self.draws=[]
        def command(self,name,state,previous):self.draws.append(int(self.rng.integers(3)));return np.zeros(8,np.float32)
    monkeypatch.setattr(s,'build_features',lambda state,agent,previous,rng,*a:(np.full(225,rng.integers(3),np.float32),False))
    gate=NS(reset=lambda:None,choose=lambda obs:2)
    clocks=[s.Clock(RandomPool(),gate),s.Clock(RandomPool())];clocks[1].fixed_choice=2
    for clock in clocks:
        state=NS(tick_count=0);clock.reset(state,0,np.random.default_rng(77))
        for tick in range(0,48,2):state.tick_count=tick;clock.controls_for_ticks(state,2)
    assert clocks[0].pool.draws==clocks[1].pool.draws


def test_six_contract_and_commitment_use_new_order_and_240_inputs():
    assert contract_for(SIX_NAMES)==SIX_CONTRACT and 'ripple' not in SIX_NAMES
    c=Context('octane',SIX_NAMES);assert c.observation(np.zeros(225)).shape==(240,)
    c.advance(2)
    with pytest.raises(ValueError,match='committed'):c.advance(4)
    for _ in range(7):c.advance(2)
    c.advance(4)


def test_wandb_fractions_include_all_six_without_a_ripple_entry():
    from nova.tracking import EpisodeWindow
    window=EpisodeWindow();window.add(dict(outcome=0,timeout=True,practice_success=False,
        episode={'r':0,'l':21},touches=0,opponent='rain',scenario='kickoff',reward_parts={},
        selector_counts=dict(zip(SIX_NAMES,[1,2,3,4,5,6]))))
    metrics=window.metrics();fractions={k:v for k,v in metrics.items() if k.startswith('selector/')}
    assert len(fractions)==6 and 'selector/ripple_fraction' not in fractions
    assert sum(fractions.values())==pytest.approx(1) and fractions['selector/megabyte_fraction']==pytest.approx(6/21)


def test_two_tick_physics_preserves_eight_tick_episode_and_discounted_potential(cfg):
    from nova.chronos import ChronosEnv
    cfg['chronos']={'reward_profile':'potential_goal_v2'};cfg['env'].update(episode_seconds=.2,no_touch_seconds=2)
    env=ChronosEnv(cfg,opponent='scripted',scenario='kickoff',side=0)
    try:
        env.reset(seed=27);clock=s.Clock(Pool());clock.fixed_choice=2
        clock.reset(env.arena.state,env.arena.agent,np.random.default_rng(27))
        phi=env.arena.potential(env.arena.state);total=0;gamma=cfg['ppo']['gamma'];count=0;start=env.arena.state.tick_count
        while True:
            _,reward,terminal,truncated,info=s.transition(env,clock);total+=gamma**count*reward;count+=1
            if terminal or truncated:break
        assert truncated and not terminal and count==3
        assert env.arena.state.tick_count-start==24 and info['episode']['l']==3
        assert total==pytest.approx(gamma**count*env.arena.potential(env.arena.state)-phi,abs=1e-7)
    finally:env.close()


@pytest.mark.parametrize('kind',['ducky','rain','megabyte'])
def test_actual_logits_match_cpp_loader_and_all_parameters_stay_frozen(request,kind):
    if not request.config.getoption('--teachers'):pytest.skip('Requires downloaded extra models')
    import torch
    from nova.teachers import verify_teacher
    torch.set_num_threads(1);model=s.ExtraNetwork(verify_teacher(kind),kind)
    assert all(not p.requires_grad for p in model.parameters())
    for case in FIXTURES['cases']:
        ref=case['reference'][kind]
        with torch.inference_mode():actual=model(torch.tensor(ref['features'])[None,:])[0].numpy()
        np.testing.assert_allclose(actual,ref['logits'],atol=4e-5,rtol=3e-5)
