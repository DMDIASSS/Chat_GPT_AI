"""Regression tests for goal detection from rlgym-tools gameplay_periods."""
from types import SimpleNamespace
import hashlib
import numpy as np
import pandas as pd

from slater_research.replay_engine import goal_events,extract_goal_clips,Clip


def fake_parsed(last_hit_player=10):
    # 12 seconds into a play, the ball enters the positive-Y net (blue scores).
    # No analyzer hit has an `is_goal` boolean (normal carball case).
    return SimpleNamespace(
        analyzer={
            'gameplay_periods':[{'start_frame':0,'end_frame':1450,'goal_frame':1440}],
            'hits':[{'frame_number':1432,'player_unique_id':last_hit_player}]
        },
        game_df=pd.DataFrame({'time':[12.0]},index=[1440]),
        ball_df=pd.DataFrame({'pos_y':[5130.0]},index=[1440]),
        metadata={'players':[{'unique_id':10,'is_orange':False},
                             {'unique_id':20,'is_orange':True}]},
    )


def test_goals_do_not_require_is_goal_hit_annotation():
    metrics={}
    assert goal_events(fake_parsed(), metrics)==[(12.0,'10')]
    assert metrics['goal_periods']==1
    assert metrics['inferred_events']==1


def test_own_goals_are_not_mislabelled_as_shooter_examples():
    stats={}
    assert goal_events(fake_parsed(last_hit_player=20),stats)==[]
    assert stats['own_goal_skips']==1


def test_clip_export_from_goal_period_without_hit_goal_tag(tmp_path,monkeypatch):
    import sys
    import types
    import slater_research.replay_engine as mod
    parsed=fake_parsed()
    frames=[]
    car=SimpleNamespace(is_orange=False)
    enemy=SimpleNamespace(is_orange=True)
    # Replay-to-RLGym frames generally aren't every physics tick; 8-tick
    # synthetic frames are sufficient to test matching/export logic.
    for tick in range(0,1441,8):
        state=SimpleNamespace(tick_count=tick,cars={10:car,20:enemy})
        frames.append(SimpleNamespace(state=state,actions={10:np.zeros(8),20:np.zeros(8)}))
    pkg=types.ModuleType('rlgym_tools')
    rl=types.ModuleType('rlgym_tools.rocket_league')
    replay_pkg=types.ModuleType('rlgym_tools.rocket_league.replays')
    parsed_mod=types.ModuleType('rlgym_tools.rocket_league.replays.parsed_replay')
    parsed_mod.ParsedReplay=SimpleNamespace(load=lambda x: parsed)
    convert_mod=types.ModuleType('rlgym_tools.rocket_league.replays.convert')
    convert_mod.replay_to_rlgym=lambda *_args,**_kwargs: iter(frames)
    for name,module in [('rlgym_tools',pkg),('rlgym_tools.rocket_league',rl),
                        ('rlgym_tools.rocket_league.replays',replay_pkg),
                        ('rlgym_tools.rocket_league.replays.parsed_replay',parsed_mod),
                        ('rlgym_tools.rocket_league.replays.convert',convert_mod)]:
        monkeypatch.setitem(sys.modules,name,module)
    monkeypatch.setattr(mod,'_mapped_frame',lambda f,ids: np.zeros(15,dtype=np.float32))
    src=tmp_path/'sample.replay';src.write_bytes(b'fake replay')
    info={}
    created=extract_goal_clips(src,tmp_path/'out',lead_seconds=12.0,diagnostics=info)
    assert len(created)==1
    assert info['emitted_clips']==1
    with np.load(created[0],allow_pickle=False) as f:
        assert f['frames'].shape[0]>100
        assert f['shooter_id']==1
        assert f['controls'].shape[-2:]==(2,8)


def test_fractional_replay_tick_does_not_reject_first_sample(tmp_path, monkeypatch):
    """Regression: replay_to_rlgym computes tick_count = time * 120.

    These values are not necessarily integral; using int(tick_count)
    silently floors and puts the first requested tick before the first frame.
    """
    import sys
    import types
    import slater_research.replay_engine as mod
    parsed=fake_parsed()
    frames=[]
    car=SimpleNamespace(is_orange=False)
    enemy=SimpleNamespace(is_orange=True)
    for tick in range(0,1441,8):
        # 0.37 tick offset, modelling unsnapped replay timestamps.
        state=SimpleNamespace(tick_count=tick+0.37,cars={10:car,20:enemy})
        frames.append(SimpleNamespace(state=state,actions={10:np.zeros(8),20:np.zeros(8)}))
    monkeypatch.setitem(sys.modules,'rlgym_tools',types.ModuleType('rlgym_tools'))
    monkeypatch.setitem(sys.modules,'rlgym_tools.rocket_league',types.ModuleType('rlgym_tools.rocket_league'))
    monkeypatch.setitem(sys.modules,'rlgym_tools.rocket_league.replays',types.ModuleType('rlgym_tools.rocket_league.replays'))
    parsed_mod=types.ModuleType('rlgym_tools.rocket_league.replays.parsed_replay')
    parsed_mod.ParsedReplay=SimpleNamespace(load=lambda _:parsed)
    convert_mod=types.ModuleType('rlgym_tools.rocket_league.replays.convert')
    convert_mod.replay_to_rlgym=lambda *_args,**_kwargs:iter(frames)
    monkeypatch.setitem(sys.modules,'rlgym_tools.rocket_league.replays.parsed_replay',parsed_mod)
    monkeypatch.setitem(sys.modules,'rlgym_tools.rocket_league.replays.convert',convert_mod)
    monkeypatch.setattr(mod,'_mapped_frame',lambda f,ids:np.zeros(15,dtype=np.float32))
    source=tmp_path/'fractional.replay';source.write_bytes(b'fake fractional replay')
    info={}
    clips=extract_goal_clips(source,tmp_path/'export',diagnostics=info)
    assert len(clips)==1,info
    assert info['clip_skip_reasons']=={}
    with np.load(clips[0]) as data:
        assert len(data['frames'])>100
        assert data['goal_step']<len(data['frames'])
