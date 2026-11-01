import random

import numpy as np
import pytest

pytest.importorskip('rlgym_tools')
from rlgym.rocket_league.sim import RocketSimEngine
from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
from rlgym_tools.rocket_league.misc.serialize import serialize_replay_frame
from rlgym_tools.rocket_league.replays.replay_frame import ReplayFrame
from rlgym_tools.rocket_league.shared_info_providers.scoreboard_provider import ScoreboardInfo
from slater_replay_starts import ReplayStartBank
from slater_v041_overnight import replay_arguments
from slater_v041_core import atomic_json,sha256
from slater_v041_tests.test_curriculum import make_env


def frame():
    engine=RocketSimEngine()
    try:
        state=engine.create_base_state()
        FixedTeamSizeMutator(blue_size=1,orange_size=1).apply(state,{})
        random.seed(123);KickoffMutator().apply(state,{})
        state.ball.position=np.array([500.,-1000.,120.])
        state.ball.linear_velocity=np.array([100.,-800.,0.])
        state=engine.set_state(state,{})
        sb=ScoreboardInfo(120.,0.,0,0,False,False)
        f=ReplayFrame(state,{k:np.zeros(8) for k in state.cars},
                      {k:0. for k in state.cars},sb,60.,0,0)
        return serialize_replay_frame(f)
    finally:engine.close()


def test_real_replay_frame_resets_into_engine_with_canonical_ids(tmp_path):
    path=tmp_path/'starts.npy';np.save(path,np.stack([frame()]))
    bank=ReplayStartBank(path)
    state,index=bank.sample(44)
    assert index==0 and set(state.cars)=={'blue-0','orange-0'}
    assert not state.cars['blue-0'].is_orange
    env=make_env('orange')
    env.replay_bank=bank;env.replay_probability=.5
    seed=next(i for i in range(100) if random.Random(i^0x51A7E).random()<.5)
    try:
        obs=env.reset(seed)
        assert env.reset_source=='replay'
        np.testing.assert_array_equal(env.state.ball.position,state.ball.position)
        for _ in range(50):
            obs,reward,done,info=env.step(0)
            assert all(np.isfinite(v).all() for v in obs) and np.isfinite(reward)
            assert info['reset_source']=='replay'
            if done:break
        first=env.reset(seed)
        second=env.reset(seed)
        for a,b in zip(first,second):np.testing.assert_array_equal(a,b)
    finally:env.close()


def test_future_labels_and_controls_do_not_change_model_inputs(tmp_path):
    row=frame();other=row.copy()
    other[6:9]=[1.,1.,1.]  # future outcome fields
    other[14:30]=1.  # reconstructed per-player action arrays
    paths=[tmp_path/'first.npz',tmp_path/'second.npz']
    for p,r in zip(paths,(row,other)):np.savez(p,replay_frames=r[None])
    env=make_env('blue')
    seed=next(i for i in range(100) if random.Random(i^0x51A7E).random()<.5)
    try:
        result=[]
        for p in paths:
            env.replay_bank=ReplayStartBank(p);env.replay_probability=.5
            result.append(env.reset(seed))
        for a,b in zip(*result):np.testing.assert_array_equal(a,b)
    finally:env.close()


@pytest.mark.parametrize('column,value',[(9,4),(4,1),(5,1),(36,float('nan'))])
def test_invalid_rosters_pause_or_nonfinite_physics_rejected(tmp_path,column,value):
    row=frame();row[column]=value
    path=tmp_path/'bad.npy';np.save(path,row[None])
    with pytest.raises(ValueError):ReplayStartBank(path).sample(3)


def test_changed_dataset_cannot_be_reused_on_resume(tmp_path):
    path=tmp_path/'starts.npy';np.save(path,frame()[None])
    run_dir=tmp_path/'run'
    atomic_json(run_dir/'replay_starts_manifest.json',{
        'path':str(path.resolve()),'sha256':sha256(path)})
    config={'replay_starts':str(path),'replay_start_probability':.2}
    assert '--replay-starts-sha' in replay_arguments(tmp_path,config,run_dir)
    np.save(path,np.stack([frame(),frame()]))
    with pytest.raises(RuntimeError,match='differs'):replay_arguments(tmp_path,config,run_dir)
