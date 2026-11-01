import numpy as np
import pytest
import torch

pytest.importorskip('rlgym.rocket_league.sim')
from afk_team_research import TeamObserver
from nexto_teacher import nexto_actions
from slater_v041_worker import ScriptedPoolEnv


class Frozen(torch.nn.Module):
    def forward(self,x):return torch.zeros((x[0].shape[0],90))


def make_env(side,reset='mixed_ground',delay=True):
    frozen=Frozen()
    return ScriptedPoolEnv(nexto_actions(),TeamObserver(),(frozen,frozen),frozen,
        120,'cpu',pool={'p_nexto':frozen},modes=('p_nexto',),fixed_side=side,
        training_reset=reset,rlbot_delay=delay)


def test_real_mixed_resets_repeat_and_remain_finite_on_both_sides():
    blue=make_env('blue');orange=make_env('orange')
    saw_ground=saw_kickoff=False
    try:
        assert blue.engine.config['rlbot_delay'] is True
        for seed in range(20):
            first=blue.reset(seed);other=orange.reset(seed)
            position=blue.state.ball.position.copy()
            np.testing.assert_array_equal(position,orange.state.ball.position)
            for agent in blue.state.cars:
                np.testing.assert_array_equal(blue.state.cars[agent].physics.position,
                                              orange.state.cars[agent].physics.position)
            saw_kickoff |= bool(np.allclose(position[:2],0))
            saw_ground |= bool(not np.allclose(position[:2],0))
            for _ in range(4):
                obs,reward,done,_=blue.step(0)
                assert all(np.isfinite(x).all() for x in obs)
                assert np.isfinite(reward)
                assert not done
            # Reset restores exact observations after actual physics transitions.
            repeated=blue.reset(seed)
            for a,b in zip(first,repeated):np.testing.assert_array_equal(a,b)
            assert all(np.isfinite(x).all() for x in other)
        assert saw_ground and saw_kickoff
    finally:blue.close();orange.close()


def test_kickoff_evaluation_remains_kickoff_only():
    env=make_env('blue',reset='kickoff',delay=False)
    try:
        env.reset(42)
        np.testing.assert_array_equal(env.state.ball.position[:2],np.zeros(2))
        assert env.engine.config['rlbot_delay'] is False
    finally:env.close()
