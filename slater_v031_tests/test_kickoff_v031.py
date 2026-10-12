from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import numpy as np
import pytest
from types import SimpleNamespace
import slater_kickoff_extract_v031 as x
import slater_kickoff_train_v031 as t
import slater_mechanics_probe_v031 as m


def car(y,orange):
    phys=SimpleNamespace(position=np.array([250. if not orange else -250.,y,17.],dtype=np.float32),
            linear_velocity=np.zeros(3),euler_angles=np.array([0,0,1.57 if not orange else -1.57]))
    return SimpleNamespace(is_orange=orange,physics=phys,boost_amount=33.)


def sample_state():
    ball=SimpleNamespace(position=np.array([0.,0.,93.]),linear_velocity=np.zeros(3))
    return SimpleNamespace(cars={1:car(-2048.,False),2:car(2048.,True)},ball=ball)


def test_extract_only_valid_1v1_kickoff():
    state=sample_state()
    pose=x.kickoff_pose(state)
    assert set(pose)=={'blue_position','blue_euler','blue_boost','orange_position','orange_euler','orange_boost','ball_position'}
    assert pose['blue_position'][1]<0 and pose['orange_position'][1]>0
    state.ball.position[1]=1300
    assert x.kickoff_pose(state) is None
    state.ball.position[1]=0
    state.cars[3]=car(-3000.,False)
    assert x.kickoff_pose(state) is None


def test_select_kickoff_time_window():
    s=sample_state()
    frames=[SimpleNamespace(state=SimpleNamespace(**{**vars(s),'tick_count':t})) for t in (0,12,72,120)]
    assert int(x.select_kickoff(frames,0.05)['replay_tick'])==12
    assert x.select_kickoff(frames,2.0) is None


def test_replay_split_is_deterministic_and_by_sha():
    sha='9303f4d0'+'0'*56
    assert x.split_replay(sha)==x.split_replay(sha)
    assert x.split_replay(sha)=='train'


def test_fake_policy_switches_physical_controls():
    normal=np.array([1.,0.,0.,0.,0.,0.,1.,0.],dtype=np.float32)
    assert np.all(t.fake_controls('nexto',80,200,normal)==normal)
    assert np.all(t.fake_controls('idle_fake',0,2300,normal)==0)
    assert np.all(t.fake_controls('late_fake',0,1300,normal)==normal)
    changed=t.fake_controls('late_fake',0,900,normal)
    assert changed[0]==-1 and changed[6]==0 and changed[7]==1
    assert t.fake_controls('turn_fake',10,2000,normal)[7]==1


def test_kickoff_reward_direction_and_fake():
    common=dict(progress=0.,closing=0.,signed_ball_velocity=0.,student_touches=0,
                opponent_touches=0,first_touch=None,fake=False,ball_y=0.,goal_outcome=0)
    r0=t.kickoff_reward(**common)
    assert t.kickoff_reward(**{**common,'goal_outcome':1})>r0+10
    assert t.kickoff_reward(**{**common,'goal_outcome':-1})<r0-10
    assert t.kickoff_reward(**{**common,'first_touch':'student'})>r0+1
    assert t.kickoff_reward(**{**common,'first_touch':'opponent'})<r0
    assert t.kickoff_reward(**{**common,'fake':True,'student_touches':1,'ball_y':200})>t.kickoff_reward(**{**common,'fake':True,'student_touches':1,'ball_y':-200})


def test_macros_require_jump_release_and_continuous_control():
    seq=m.macro_timeline('speedflip_left_probe')
    assert seq.shape==(240,8)
    assert seq[33,5]==1 and seq[33,2]<0 and seq[33,3]<0
    assert seq[35,5]==0 and seq[35,2]>0
    assert m.macro_timeline('halfflip_probe')[31,5]==1
    with pytest.raises(ValueError):m.macro_timeline('spaceflip')


def test_lookup_exposes_action_space_limit():
    actions=np.zeros((90,8))
    actions[4,5]=1; actions[4,2]=-1
    out=m.audit_lookup(actions)
    assert out['jump_with_diagonal_pitch_yaw']==0
    actions[5,[2,3,5]]=[-1,.8,1]
    assert m.audit_lookup(actions)['diagonal_jump_action_ids']==[5]


def test_pose_apply_does_not_corrupt_kickoff_car_internal_state():
    st=sample_state()
    # Remap to RLGym simulator IDs, only positions/orientations should be changed.
    st.cars={'blue-0':st.cars[1],'orange-0':st.cars[2]}
    st.ball.angular_velocity=np.zeros(3)
    special=st.cars['blue-0'];special.has_flipped=False
    pose=x.kickoff_pose(sample_state())
    pose['blue_position']=np.array([-1200.,-2700.,17.],dtype=np.float32)
    t.apply_pose(st,pose)
    assert st.cars['blue-0'].physics.position[0]==-1200
    assert special.has_flipped is False
    assert np.linalg.norm(st.ball.linear_velocity)==0


def test_no_unsafe_checkpoint_location(tmp_path):
    from slater_cycle9_native_ppo_v025 import check_output
    root=tmp_path
    with pytest.raises(ValueError):check_output(root/'champion.pt',root)
    dest=root/'data'/'isolated'/'new.pt'
    assert check_output(dest,root)==dest.resolve()
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b'old')
    with pytest.raises(FileExistsError):check_output(dest,root)


def test_export_rejects_foreign_source_before_load(tmp_path):
    import slater_export_kickoff_rlbot_v031 as export
    (tmp_path/'data'/'isolated').mkdir(parents=True)
    wrong=tmp_path/'wrong.pt'
    wrong.write_bytes(b'donotread')
    with pytest.raises(ValueError):
        export.guarded_export(wrong,tmp_path/'source.pt',tmp_path/'data'/'isolated'/'x.pt',tmp_path)
