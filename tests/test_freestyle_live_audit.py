"""Use actual v5 serialization to distinguish adapter replay from input echo."""
import json
from types import SimpleNamespace
import numpy as np
import pytest
import torch

from freestyle_rlbot_v5 import runtime as r
from freestyle_rlbot_v5.live import LiveController, rotation
from freestyle_rlbot_v5.live_audit import Recorder, audit


@pytest.mark.parametrize('invert_echo',[False,True])
def test_capture_replay_and_controller_echo_are_independent(tmp_path,invert_echo):
    flat=pytest.importorskip('rlbot.flat')
    pads=[flat.BoostPad(location=flat.Vector3(*map(float,p)),is_full_boost=p[2]>72)for p in r.PAD_LOCATIONS]
    field=flat.FieldInfo(boost_pads=pads)
    chosen=next(i for i,a in enumerate(r.ACTIONS)if tuple(a)==(1,1,0,1,0,0,0,0))
    actor=torch.nn.Linear(512,94)
    with torch.no_grad():actor.weight.zero_();actor.bias.zero_();actor.bias[chosen]=5
    policy=tmp_path/'policy.pt';torch.jit.trace(actor,torch.zeros(1,512)).save(str(policy))
    cfg={'stage':0,'difficulty':.75,'episode_seconds':12,'tick_skip':4,'action_delay':1,
         'scripted_kickoff':False,'update':1000}
    controller=LiveController(lambda obs,mask:chosen,field,cfg)
    recorder=Recorder(tmp_path,field,cfg,policy,packets=20)
    previous=np.zeros(8)
    for frame in range(30):
        echo=previous.copy()
        if invert_echo:echo[1]*=-1;echo[3]*=-1
        last=flat.ControllerState(throttle=float(echo[0]),steer=float(echo[1]),yaw=float(echo[3]))
        player=flat.PlayerInfo(player_id=1,team=0,physics=flat.Physics(
            location=flat.Vector3(0,-1000,17)),air_state=flat.AirState.OnGround,
            boost=50,demolished_timeout=-1,dodge_timeout=-1,last_input=last)
        packet=flat.GamePacket(players=[player],balls=[flat.BallInfo(physics=flat.Physics(location=flat.Vector3(0,0,93)))],
            boost_pads=[flat.BoostPadState(is_active=True)for _ in pads],match_info=flat.MatchInfo(
                frame_num=frame,seconds_elapsed=frame/120,match_phase=flat.MatchPhase.Active))
        previous=controller.act(packet,0);recorder.append(packet,0,previous,1.0)
    assert recorder.file is None  # Recording has a hard packet bound.
    report=audit(recorder.path,policy)
    assert report['packets']==20 and report['adapter_replay_output_mismatches']==0
    assert report['policy_decisions']==5
    assert report['last_input_echo_by_physics_frame_lag']['1']['fraction']==(1.0 if not invert_echo else 1/19)
    assert report['physics_frames_between_callbacks_median']==1
    with torch.no_grad():actor.bias[chosen]=3
    torch.jit.trace(actor,torch.zeros(1,512)).save(str(policy))
    with pytest.raises(ValueError,match='different policy'):audit(recorder.path,policy)


def test_live_euler_basis_matches_rocketsim_not_just_python_formula():
    rs=pytest.importorskip('RocketSim')
    rng=np.random.default_rng(217)
    for _ in range(100):
        yaw,pitch,roll=map(float,rng.uniform(-3,3,3))
        native=rs.Angle(yaw,pitch,roll).as_rot_mat()
        actual=rotation(SimpleNamespace(yaw=yaw,pitch=pitch,roll=roll))
        for got,expected in zip(actual,(native.forward,native.right,native.up)):
            np.testing.assert_allclose(got,expected.as_numpy(),atol=5e-7)
