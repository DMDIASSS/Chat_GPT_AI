import numpy as np
import pytest
from stable_baselines3.common.env_checker import check_env

from nova.core import ACTIONS, OBS_SIZE, observe, observe_v1, as_v1, DecisionClock
from nova.environment import ArenaEnv
from nova.scenarios import SCENARIOS


def test_real_gymnasium_contract_and_timelimit(cfg):
    env=ArenaEnv(cfg,opponent='scripted',scenario='kickoff')
    try:
        check_env(env,warn=True)
        obs,_=env.reset(seed=331)
        for _ in range(10):
            obs,reward,terminal,truncated,info=env.step(0)
            if terminal or truncated: break
        assert truncated and not terminal
        assert info['timeout'] and info['outcome']==0
        assert obs.shape==(OBS_SIZE,)
        assert info['seconds']>=.15
    finally: env.close()


@pytest.mark.parametrize('scenario',SCENARIOS)
def test_both_sides_and_live_feature_parity(cfg,scenario):
    observations=[]
    for side in (0,1):
        env=ArenaEnv(cfg,opponent='scripted',scenario=scenario,side=side)
        try:
            obs,_=env.reset(seed=233)
            observations.append(obs)
            v1=as_v1(env.state)
            index=next(i for i,p in enumerate(v1.players) if p.team_num==side)
            np.testing.assert_allclose(observe_v1(v1,index,np.zeros(8)),obs,atol=2e-6)
            assert .3<=v1.players[index].boost_amount<=1
            after=env.step(17)
            assert np.isfinite(after[0]).all()
        finally: env.close()
    np.testing.assert_allclose(observations[0],observations[1],atol=2e-6)


def test_reset_seed_and_goal_precedence(cfg):
    env=ArenaEnv(cfg,opponent='scripted',scenario='kickoff',side=0)
    try:
        a,_=env.reset(seed=897)
        env.step(12)
        b,_=env.reset(seed=897)
        np.testing.assert_array_equal(a,b)
        state=env.state
        state.ball.position=np.array([0,5150,93.15],dtype=np.float32)
        state.ball.linear_velocity=np.array([0,5000,0],dtype=np.float32)
        env.state=env.engine.set_state(state,{})
        env.cfg['env']['episode_seconds']=.001
        _,_,terminal,truncated,info=env.step(0)
        assert terminal and not truncated
        assert info['outcome']==1 and not info['timeout']
        assert info['reward_parts']['goal']==10
    finally: env.close()


def test_clock_uses_frame_distance_and_handles_rewind():
    c=DecisionClock()
    assert c.due(100)
    assert not c.due(100)
    assert not c.due(103)
    assert c.due(104)
    assert c.due(119)
    assert c.due(2)


def test_action_buttons_and_finite_table():
    assert ACTIONS.shape==(276,8)
    assert len(np.unique(ACTIONS,axis=0))==276
    assert set(np.unique(ACTIONS[:,5:]))<={0,1}


def test_repeated_team_resets_do_not_mutate_shared_kickoff_templates(cfg):
    from rlgym.rocket_league.state_mutators import KickoffMutator
    blue=KickoffMutator.SPAWN_BLUE_POS.copy();orange=KickoffMutator.SPAWN_ORANGE_POS.copy()
    for side in (1,0,1,1,0):
        env=ArenaEnv(cfg,opponent='scripted',scenario='kickoff',side=side)
        try:
            states=[]
            for _ in range(3):
                obs,_=env.reset(seed=233);states.append(obs.copy())
                position=env.state.cars[env.agent].physics.position
                assert position[1]>0 if side==1 else position[1]<0
                np.testing.assert_array_equal(KickoffMutator.SPAWN_BLUE_POS,blue)
                np.testing.assert_array_equal(KickoffMutator.SPAWN_ORANGE_POS,orange)
            for obs in states[1:]:np.testing.assert_array_equal(obs,states[0])
        finally:env.close()
