import json
from pathlib import Path

import numpy as np
import pytest
import torch

from nova.giga_teachers import build_features, native_action_mask, GigaTeacher, GigaNetwork, TABLE
from nova.teachers import verify_teacher, controls_for_ticks
from nova.training import load_config
from nova.environment import ArenaEnv
from rlgym_tools.rocket_league.misc.serialize import deserialize_game_state

FIXTURE=json.loads((Path(__file__).parent/'fixtures/giga_reference.json').read_text())


@pytest.mark.parametrize('kind',['chronos','galactus'])
def test_features_and_masks_against_original_cpp(kind):
    for record in FIXTURE['cases']:
        state=deserialize_game_state(np.array(record['state'],dtype=np.float32))
        agent=next(k for k,c in state.cars.items() if c.team_num==record['side'])
        reference=record['reference'][kind]
        features,_=build_features(state,agent,np.array(record['previous'],dtype=np.float32),
            np.random.default_rng(5),kind,np.array(record['predictions'],dtype=np.float32),
            opponent_slot=reference['opponent_slot'])
        np.testing.assert_allclose(features,reference['features'],atol=2e-6,rtol=2e-6)
        np.testing.assert_array_equal(native_action_mask(state.cars[agent]),reference['mask'])


def test_eight_tick_decisions_and_seven_tick_application_delay():
    # Keep the real native scheduler; a fixed-logit network makes timing observable.
    from types import SimpleNamespace
    cfg=load_config()
    env=ArenaEnv(cfg,opponent='scripted',scenario='kickoff',side=0)
    try:
        env.reset(seed=2)
        teacher=GigaTeacher.__new__(GigaTeacher)
        teacher.kind='chronos';teacher.forecast=None
        calls=[]
        def network(x):
            calls.append(x)
            logits=torch.zeros((1,90));logits[0,20]=100
            return logits
        teacher.network=network
        teacher.reset(env.state,env.agent,np.random.default_rng(2))
        sequences=[]
        for _ in range(4):
            commands=controls_for_ticks(teacher,env.state)
            sequences.append(commands)
            env.step_controls(commands)
        controls=np.concatenate(sequences)
        np.testing.assert_array_equal(controls[:7],np.zeros((7,8)))
        np.testing.assert_array_equal(controls[7:15],np.repeat(TABLE[20][None,:],8,axis=0))
        assert len(calls)==2
    finally: env.close()


@pytest.mark.parametrize('kind',['chronos','galactus'])
def test_actual_weights_against_original_cpp_logits(request,kind):
    if not request.config.getoption('--teachers'): pytest.skip('Requires downloaded native teacher weights')
    torch.set_num_threads(1)
    model=GigaNetwork(verify_teacher(kind),kind)
    for record in FIXTURE['cases']:
        ref=record['reference'][kind]
        features=torch.tensor(ref['features'],dtype=torch.float32)[None,:]
        with torch.inference_mode(): actual=model(features).numpy()[0]
        np.testing.assert_allclose(actual,ref['logits'],atol=3e-5,rtol=2e-5)


@pytest.mark.parametrize('kind',['chronos','galactus'])
@pytest.mark.parametrize('side',[0,1])
def test_actual_native_opponent_steps(request,cfg,kind,side):
    if not request.config.getoption('--teachers'): pytest.skip('Requires downloaded native teacher weights')
    env=ArenaEnv(cfg,opponent=kind,scenario='recovery',side=side)
    try:
        obs,_=env.reset(seed=778)
        for _ in range(4):
            obs,_,terminal,truncated,_=env.step(17)
            assert np.isfinite(obs).all()
    finally: env.close()
