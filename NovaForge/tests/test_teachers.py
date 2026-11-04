import numpy as np
import pytest

from nova.core import ROOT, ACTIONS, as_v1
from nova.environment import ArenaEnv
from nova.teachers import make_opponent


@pytest.fixture(autouse=True)
def requested(request):
    if not request.config.getoption('--teachers'):
        pytest.skip('Download teacher assets and pass --teachers to run real model tests')


def test_ripple_delayed_controls_and_matching_actions(cfg):
    env=ArenaEnv(cfg,opponent='scripted',scenario='kickoff',side=0)
    try:
        env.reset(seed=1)
        teacher=make_opponent('ripple')
        teacher.reset(env.state,env.agent,np.random.default_rng(1))
        outputs=[]
        for i in range(7):
            command=teacher.act(env.state)
            outputs.append(command.copy())
            if i==0: first_plan=teacher.queue[0,0].copy()
            assert np.any(np.all(ACTIONS==command,axis=1))
            env.step_controls(command)
        np.testing.assert_array_equal(outputs[:6],np.zeros((6,8)))
        np.testing.assert_array_equal(outputs[6],first_plan)
    finally: env.close()


@pytest.mark.parametrize('name',['nexto','ripple'])
@pytest.mark.parametrize('side',[0,1])
def test_real_teacher_model_on_non_kickoff_state(cfg,name,side):
    env=ArenaEnv(cfg,opponent='scripted',scenario='aerial',side=side)
    try:
        env.reset(seed=781)
        teacher=make_opponent(name)
        teacher.reset(env.state,env.agent,np.random.default_rng(781))
        for _ in range(4):
            command=teacher.act(env.state)
            assert command.shape==(8,) and np.isfinite(command).all()
            env.step_controls(command)
    finally: env.close()
