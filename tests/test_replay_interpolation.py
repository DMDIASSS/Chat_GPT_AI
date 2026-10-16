"""Synthetic physics fixtures exercise the real replay converter, not training data."""
import copy,random,os
from types import SimpleNamespace as S
import numpy as np
import pandas as pd
import pytest
from rlgym.rocket_league.sim import RocketSimEngine
from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
from rlgym_tools.rocket_league.replays import convert
from replay_il.data import make_rows,replay_frames
from slater_v041_core import read_json

def repeated_update_replay(update_every=2):
 engine=RocketSimEngine(rlbot_delay=False); frames=[]
 saved=random.getstate();random.seed(12)
 try:
  state=engine.create_base_state();FixedTeamSizeMutator(1,1).apply(state,{});KickoffMutator().apply(state,{})
  state.cars={i+1:c for i,c in enumerate(state.cars.values())}
  state=engine.set_state(state,{})
  state=engine.step({i:np.tile(np.array([1,.3 if i==1 else -.2,0,0,0,0,1,0],np.float32),(120,1)) for i in state.cars},{})
  for index in range(61):
   action={i:np.array([1,.3 if i==1 else -.2,0,0,0,0,1,0],np.float32) for i in state.cars}
   frames.append((copy.deepcopy(state),action))
   state=engine.step({i:np.tile(v,(4,1)) for i,v in action.items()},{})
 finally:engine.close();random.setstate(saved)
 game=pd.DataFrame([{'time':i/30,'delta':1/30,'is_overtime':0,'scoreboard_timer':300-i/30,'kickoff_timer':0.,'episode_seconds_remaining':2-i/30} for i in range(len(frames))])
 ball=[];players={1:[],2:[]}
 for i,(state,actions) in enumerate(frames):
  b=state.ball
  ball.append({**{f'{name}_{axis}':float(val) for name,values in [('pos',b.position),('vel',b.linear_velocity),('ang_vel',b.angular_velocity),('quat',b.quaternion)] for axis,val in zip('wxyz' if name=='quat' else 'xyz',values)}})
  for uid,car in state.cars.items():
   original=frames[i-i%update_every][0].cars[uid].physics; act=actions[uid]
   row={f'{name}_{axis}':float(val) for name,values in [('pos',original.position),('vel',original.linear_velocity),('ang_vel',original.angular_velocity),('quat',original.quaternion)] for axis,val in zip('wxyz' if name=='quat' else 'xyz',values)}
   row.update(is_repeat=bool(i%update_every),update_age=(i%update_every)/30,is_demoed=False,got_demoed=False,respawned=False,boost_amount=car.boost_amount,
    boost_pickup=0.,throttle=(act[0]+1)*255/2,steer=(act[1]+1)*255/2,pitch=0.,yaw=0.,roll=0.,handbrake=0.,boost_is_active=1,
    jumped=False,dodged=False,double_jumped=False,jump_is_active=False,dodge_is_active=False,double_jump_is_active=False,
    flip_car_is_active=False,got_flip_reset=False,dodge_torque_x=0.,dodge_torque_y=0.)
   players[uid].append(row)
 ball=pd.DataFrame(ball); players={str(k):pd.DataFrame(v) for k,v in players.items()}
 replay=S(metadata={'players':[{'unique_id':str(i),'is_orange':c.team_num==1} for i,c in frames[0][0].cars.items()], 'game':{'goals':[]}},
  analyzer={'hits':[],'gameplay_periods':[{'start_frame':0,'end_frame':len(frames)-1}]},game_df=game,ball_df=ball,player_dfs=players)
 return replay,(ball,game,{int(k):v for k,v in players.items()})

@pytest.fixture(scope="module")
def repeated_updates():
    return repeated_update_replay()

def test_repeated_car_updates_reconstruct_without_relaxing_quality(repeated_updates,monkeypatch):
    replay,prepared=repeated_updates
    # Only the parquet preparation is substituted; the converter and both
    # reconstruction/verification engines execute their real implementations.
    monkeypatch.setattr(convert,'_prepare_segment_dfs',lambda *a:prepared)
    frozen=list(convert.replay_to_rlgym(replay,interpolation='none'))
    corrected=list(replay_frames(replay))
    assert np.array_equal(frozen[0].state.cars[1].physics.position,frozen[1].state.cars[1].physics.position)
    assert not np.array_equal(corrected[0].state.cars[1].physics.position,corrected[1].state.cars[1].physics.position)
    old,_,failed=make_rows(frozen,cap=1024)
    actual,_,stats=make_rows(corrected,cap=1024)
    assert not old and failed['rejected_fit']==60 and failed['rejected_position']>0
    assert len(actual)==54 and stats['accepted_fit']==60
    assert stats.get('rejected_fit',0)==0 and stats['chunks_verified']==27
    assert stats['max_accepted_position']<40 and stats['max_accepted_velocity']<180 and stats['max_accepted_rotation']<.3


def test_empty_reconstruction_keeps_failure_evidence(tmp_path,repeated_updates,monkeypatch,capsys):
    import replay_il.data as data
    from rlgym_tools.rocket_league.replays.parsed_replay import ParsedReplay
    replay,prepared=repeated_updates
    monkeypatch.setattr(convert,'_prepare_segment_dfs',lambda *a:prepared)
    frozen=list(convert.replay_to_rlgym(replay,interpolation='none'))
    monkeypatch.setattr(data,'ROOT',tmp_path)
    monkeypatch.setattr(ParsedReplay,'load',lambda *a:S(metadata={'game':{'id':'fixture-only'}}))
    monkeypatch.setattr(data,'replay_frames',lambda _:iter(frozen))
    path=tmp_path/'fixture.replay';path.write_bytes(b'FAKE_FILE_NOT_HUMAN_REPLAY_DATA')
    out=tmp_path/'data/isolated/fixture_dataset'
    with pytest.raises(ValueError,match='two distinct real matches'):
        data.prepare([path],out)
    progress=read_json(out/'parse_progress.json')
    assert progress['completed']==1 and progress['samples']==0
    failure=progress['errors'][0]
    assert failure['error']=='No contiguous, forward-verified action chunks'
    assert failure['reconstruction']['rejected_fit']==60
    assert failure['reconstruction']['rejected_position']>0
    assert not (out/'manifest.json').exists()
    assert 'REPLAY_REJECT fixture.replay' in capsys.readouterr().out


def test_normal_sparse_updates_keep_chunks_but_unobserved_predictions_do_not(monkeypatch):
    replay,prepared=repeated_update_replay(update_every=4)
    monkeypatch.setattr(convert,'_prepare_segment_dfs',lambda *a:prepared)
    frames=list(replay_frames(replay))
    assert max(max(f.update_age.values()) for f in frames)>.05
    rows,_,stats=make_rows(frames)
    assert len(rows)>20 and stats['chunks_verified']>10
    assert stats['max_accepted_update_age_seconds']>.05
    # A prediction cannot validate its own labels without any observed refresh,
    # even if its reported ages claim it was recently seen.
    unseen=copy.deepcopy(frames)
    for frame in unseen:frame.update_age={k:.033 for k in frame.state.cars}
    rejected,_,detail=make_rows(unseen)
    assert not rejected and detail['chunks_missing_observed_refresh']>0
    # Predictions older than the bounded interpolation interval remain unusable.
    for frame in unseen:frame.update_age={k:.2 for k in frame.state.cars}
    rejected,_,detail=make_rows(unseen)
    assert not rejected and detail['stale_states']>0


def test_ball_surface_orientation_does_not_change_labels_but_car_orientation_is_checked():
    from test_replay_imitation import trace
    from replay_il.data import transition_errors
    frames=trace(2.)
    rotated=copy.deepcopy(frames)
    for i,frame in enumerate(rotated):
        angle=i*.7;c,s=np.cos(angle),np.sin(angle)
        frame.state.ball.rotation_mtx=np.array([[c,-s,0],[s,c,0],[0,0,1]],np.float32)
    expected,_,_=make_rows(frames,cap=128)
    actual,_,_=make_rows(rotated,cap=128)
    assert len(actual)==len(expected)>0
    for a,b in zip(expected,actual):
        np.testing.assert_array_equal(a['controls'],b['controls'])
        for x,y in zip(a['history'],b['history']):np.testing.assert_array_equal(x,y)
    before=frames[0].state;after=copy.deepcopy(before)
    first=next(iter(after.cars));after.cars[first].physics.euler_angles=np.array([0,0,1.],np.float32)
    assert transition_errors(before,after)['rotation']>.3


@pytest.mark.skipif(not os.environ.get('REPLAY_IL_REAL_REPLAY'),reason='Private original replay supplied separately through REPLAY_IL_REAL_REPLAY')
def test_private_original_replay_produces_a_verified_finite_shard(tmp_path,monkeypatch):
    from pathlib import Path
    import replay_il.data as data
    from slater_v041_core import sha256
    source=Path(os.environ['REPLAY_IL_REAL_REPLAY'])
    assert source.is_file()
    monkeypatch.setattr(data,'ROOT',tmp_path)
    out=tmp_path/'data/isolated/real_replay_check'
    # One real match cannot create a train/validation/test split. Verify its
    # genuine cached shard without inventing extra matches to bypass the guard.
    with pytest.raises(ValueError,match='two distinct real matches'):
        data.prepare([source],out)
    records=list((out/'shards').glob('*.json'))
    record=next(read_json(p) for p in records if not p.name.endswith('.kickoffs.json'))
    assert record['original_sha256']==sha256(source) and record['samples']>0
    assert record['reconstruction']['chunks_verified']>0
    assert record['config']['chunk_requires_observed_car_refresh']
    assert record['config']['rotation_entities']=='cars_only'
    assert record['reconstruction']['max_accepted_update_age_seconds']<=16/120
    with np.load(record['shard'],allow_pickle=False) as shard:
        assert shard['q'].shape==(record['samples'],8,1,32)
        assert shard['controls'].shape==(record['samples'],32,8)
        assert all(np.isfinite(shard[k]).all() for k in shard.files)
        assert np.isin(shard['controls'][:,:,5:],[0,1]).all()
    assert not (out/'manifest.json').exists()
