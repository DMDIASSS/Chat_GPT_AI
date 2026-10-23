import copy,json
from types import SimpleNamespace as S
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from slater_focus_evaluation import mastery,Tracker,setup,episode
from slater_event_windows import source_coverage,events,native_row

def test_streak_requires_both_colors_varied_seeds_and_actual_success():
    rows=[dict(seed=j,side=side,success=True,window=None) for j in range(10) for side in ('blue','orange')]
    assert mastery(rows)['passed']
    rows[-1]['success']=False;assert not mastery(rows)['passed']
    rows[-1]['success']=True;rows.append(rows[0])
    with pytest.raises(ValueError):mastery(rows)


def test_replay_mastery_does_not_count_repeated_one_replay_as_independent():
    rows=[dict(seed=j,side=side,success=True,window='same') for j in range(12) for side in ('blue','orange')]
    assert not mastery(rows)['passed']
    for r in rows:r['window']='replay'+str(r['seed']%6)
    assert mastery(rows)['passed']


def test_missing_controls_are_explicit_not_neutral():
    parsed=S(player_dfs={'1':pd.DataFrame({'throttle':[np.nan,np.nan],'steer':[127,127]}),'2':pd.DataFrame({'throttle':[255,255]})})
    assert source_coverage(parsed)=={'1':{'throttle':0,'steer':2},'2':{'throttle':2,'steer':0}}


def state():
    return S(cars={'us':S(team_num=0,boost_amount=0,ball_touches=0),'enemy':S(team_num=1,boost_amount=0,ball_touches=0)},ball=S(position=np.array([0.,-4700,93]),linear_velocity=np.array([0.,-500,0])),goal_scored=False)


def test_save_timeout_and_free_goal_do_not_count():
    s=state();tracker=Tracker('replay_save',s,'us','enemy');tracker.tick(s,s,np.zeros(8));assert not tracker.success(s)
    tracker.touch=True;tracker.clear=True;assert not tracker.success(s)
    tracker.active=True;assert tracker.success(s)
    s.goal_scored=True;s.ball.position[1]=-5300;assert not tracker.success(s)
    attack=Tracker('replay_attack',s,'us','enemy');s.ball.position[1]=5300;assert not attack.success(s)
    attack.touch=True;attack.active=True;assert attack.success(s)


def test_event_selection_uses_save_tags_and_periods_not_unmarked_hits():
    p=S(metadata={'players':[{'unique_id':1,'is_orange':False},{'unique_id':2,'is_orange':True}]},analyzer={'hits':[{'frame_number':10,'player_unique_id':2,'is_save':True},{'frame_number':11,'player_unique_id':2}],'gameplay_periods':[]},game_df=pd.DataFrame({'time':[1.,2.]},index=[10,11]),ball_df=pd.DataFrame())
    result=events(p);assert len(result)==1 and result[0]['kind']=='save' and result[0]['query']=='2'


def test_physical_focus_setups_and_native_rows_are_finite():
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    engine=RocketSimEngine(rlbot_delay=False)
    try:
        for stage in ('touch_warmup','ground_score','boost_pickup','wall_roll','wall_pop','air_carry','air_finish','wall_to_air_finish','reset_acquire','reset_use','reset_finish','reset_double_tap'):
            s=engine.create_base_state();FixedTeamSizeMutator(blue_size=1,orange_size=1).apply(s,{});KickoffMutator().apply(s,{})
            setup(s,stage,'blue-0','orange-0',100,0.3);s=engine.set_state(s,{})
            r=native_row(s,['blue-0','orange-0'],{},'blue-0',np.eye(90)[16],1,0)
            assert r.shape==(231,) and np.isfinite(r).all()
            assert np.linalg.det(s.cars['blue-0'].physics.rotation_mtx)==pytest.approx(1,abs=.01)
    finally:engine.close()


def test_equivalent_yaw_roll_dodge_is_not_rejected_as_wrong_input():
    from slater_event_windows import event_label
    car=S(can_flip=True,on_ground=False,is_jumping=False,has_flip=True,boost_amount=50)
    controls=np.array([0,0,-.7,.8,0,1,0,0],dtype=np.float32)
    result=event_label(car,controls)
    assert result is not None and result[1]>.9 and result[0].sum()==pytest.approx(1)


def test_prepare_real_physics_trace_keeps_goals_and_balances_source_cap(tmp_path,monkeypatch):
    import slater_event_windows as module
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator
    from mechanics_scenarios import set_ball,set_car
    from rlgym_tools.rocket_league.replays.parsed_replay import ParsedReplay
    engine=RocketSimEngine(rlbot_delay=False)
    initial=engine.create_base_state();FixedTeamSizeMutator(blue_size=1,orange_size=1).apply(initial,{})
    initial.cars={1:initial.cars['blue-0'],2:initial.cars['orange-0']}
    set_ball(initial.ball,[0,4700,93],[0,0,0]);set_car(initial.cars[1],[0,4400,17],[0,4700,17],boost=33,on_ground=True)
    set_car(initial.cars[2],[700,4950,17],[0,4700,17],boost=33,on_ground=True)
    current=engine.set_state(initial,{});frames=[];hits=[]
    try:
        for j in range(180):
            actions={1:np.array([1,0,0,0,0,0,1,0],dtype=np.float32) if j>=90 else np.zeros(8,dtype=np.float32),2:np.zeros(8,dtype=np.float32)}
            frames.append(S(state=copy.deepcopy(current),actions=actions,update_age={1:0,2:0},scoreboard=S(go_to_kickoff=current.goal_scored,is_over=False,kickoff_timer_seconds=0)))
            if current.cars[1].ball_touches:hits.append({'frame_number':j,'player_unique_id':1})
            if current.goal_scored:break
            current=engine.step({aid:np.tile(a,(8,1)) for aid,a in actions.items()}, {})
    finally:engine.close()
    assert current.goal_scored
    final=len(frames)-1
    parsed=S(metadata={'players':[{'unique_id':1,'is_orange':False},{'unique_id':2,'is_orange':True}]},
        analyzer={'hits':hits,'gameplay_periods':[{'start_frame':0,'goal_frame':final}]},
        game_df=pd.DataFrame({'time':[f.state.tick_count/120 for f in frames]}),
        ball_df=pd.DataFrame({'pos_y':[f.state.ball.position[1] for f in frames]}),
        player_dfs={str(i):pd.DataFrame({'throttle':[127,255],'steer':[127,127]}) for i in (1,2)})
    monkeypatch.setattr(ParsedReplay,'load',lambda path:parsed)
    import rlgym_tools.rocket_league.replays.convert as converter
    monkeypatch.setattr(converter,'replay_to_rlgym',lambda *args,**kwargs:iter(frames))
    monkeypatch.setattr(module,'BASE',tmp_path)
    inputs=tmp_path/'inputs';inputs.mkdir()
    known={}
    for i in range(12):
        p=inputs/f'{i:02}.replay';p.write_bytes(str(i).encode());known[module.sha256(p)]='train' if i<6 else 'validation' if i<10 else 'test'
    monkeypatch.setattr(module,'partition',lambda digest:known[digest])
    result=module.prepare(inputs,tmp_path/'out',max_rows=240,max_replays=12)
    assert len(result['sources'])==12 and result['stats']['verified_attack_windows']>0 and result['stats']['verified_save_windows']>0
    assert all('error' not in source for source in result['sources'])
    windows=json.loads(Path(result['windows']).read_text())['windows']
    assert {w['split'] for w in windows}=={0,1,2}
    assert len({w['replay_sha'] for w in windows})==12


def test_goal_mouth_state_is_valid_before_score_but_outside_wall_is_not():
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator
    from slater_event_windows import event_state_valid
    from rlgym.rocket_league.state_mutators import KickoffMutator
    engine=RocketSimEngine(rlbot_delay=False)
    try:
        s=engine.create_base_state();FixedTeamSizeMutator(blue_size=1,orange_size=1).apply(s,{})
        KickoffMutator().apply(s,{})
        s.ball.position=np.array([0.,5150,93]);s=engine.set_state(s,{})
        assert event_state_valid(s)
        s.ball.position[0]=2000;assert not event_state_valid(s)
    finally:engine.close()
