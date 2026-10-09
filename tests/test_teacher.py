import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nexto_teacher import NextoTeacher, encode_v2_state, nexto_actions, action_mapping, compress_teacher_probs


def fake_state():
    def car(y, orange):
        return SimpleNamespace(is_orange=orange, boost_amount=75., on_ground=True, ball_touches=0,
           has_flip=True, is_demoed=False, physics=SimpleNamespace(position=np.array([0.,y,17.]),
            rotation_mtx=np.eye(3), linear_velocity=np.array([0.,0.,0.]), angular_velocity=np.zeros(3)))
    return SimpleNamespace(cars={1:car(2500,True), 2:car(-2500,False)},
        boost_pad_timers=np.zeros(34), ball=SimpleNamespace(position=np.array([0.,0.,93.]),
          linear_velocity=np.array([100.,0.,0.]), angular_velocity=np.zeros(3)))


def test_teacher_input_and_inference():
    state=fake_state()
    enc, agents=encode_v2_state(state)
    assert enc.shape==(131,)
    assert agents==[2,1]
    teacher=NextoTeacher('cpu')
    observations=teacher.observe(state,{})
    assert len(observations)==2
    assert observations[0][1].shape==(1,32)
    assert observations[0][2].shape==(37,24)
    assert observations[0][3].shape==(37,)
    logits=teacher.logits([(ob[1],ob[2],ob[3]) for ob in observations])
    assert logits.shape==(2,90)
    assert np.isfinite(logits).all()


def test_prob_mapping():
    table=nexto_actions()
    assert table.shape==(90,8)
    mapping, error=action_mapping(table)
    assert not error.any()
    assert (mapping==np.arange(90)).all()
    probs=compress_teacher_probs(np.zeros((3,90)),mapping)
    assert probs.shape==(3,90)
    assert np.allclose(probs.sum(axis=1),1.)


def test_replay_split_no_overlap():
    from distill_nexto import split_by_replays
    groups=np.repeat(np.arange(20),15)
    train,val=split_by_replays(groups,0.2,42)
    assert set(groups[train]).isdisjoint(set(groups[val]))
    assert len(val)>0 and len(train)>0


def test_nexto_action_matches_rlgym_official_table():
    # RLGym v2 LookupTableAction source matches the original Nexto lookup
    # byte-for-byte, including the optional aerial wavedash handbrake.
    assert len(nexto_actions())==90
    m,loss=action_mapping(nexto_actions())
    assert np.count_nonzero(loss==0)==90


def test_boost_scale_matches_original_nexto_observation():
    # Legacy RLGym-compat stored player boost as a fraction, whereas
    # modern RLGym v2 stores boost in units [0, 100].
    state = fake_state()
    enc, agents = encode_v2_state(state)
    # Game state header 3, 34 pads, 18 ball values, 38 per car.
    first_car_boost_index = 3 + 34 + 18 + 37
    assert np.isclose(enc[first_car_boost_index], 0.75)
    teacher = NextoTeacher('cpu')
    views = teacher.observe(state, {})
    # The car boost is at key/value feature 20, and for current car at query 20.
    assert np.isclose(views[0][1][0, 20], 0.75)
    assert np.isclose(views[1][1][0, 20], 0.75)
