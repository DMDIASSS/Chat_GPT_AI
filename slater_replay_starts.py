"""Seeded 1v1 reset sampling from rlgym-tools 2.6.5 ReplayFrame arrays.

Uses current reconstructed state only. Future scoreboard annotations and
inferred action labels never enter the actor or the training target.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


class ReplayStartBank:
    def __init__(self,path):
        from rlgym_tools.rocket_league.misc.serialize import (
            GS_CARS,GS_CAR_LENGTH,RF_AGENT_IDS_START,RF_NUM_PLAYERS,
            RF_SCOREBOARD,SB_KICKOFF_TIMER_SECONDS,SB_GO_TO_KICKOFF,SB_IS_OVER)
        path=Path(path)
        if path.suffix=='.npy':
            self.frames=np.load(path,mmap_mode='r',allow_pickle=False)
        elif path.suffix=='.npz':
            with np.load(path,allow_pickle=False) as archive:
                self.frames=archive['replay_frames']
        else:raise ValueError('Replay starts require .npy or .npz ReplayFrame arrays')
        size=RF_AGENT_IDS_START+2*(2+8)+GS_CARS.start+2*GS_CAR_LENGTH
        if self.frames.ndim!=2 or self.frames.shape[1]<size or self.frames.dtype.kind!='f':
            raise ValueError('Expected a floating-point matrix of serialized ReplayFrames')
        scoreboard=self.frames[:,RF_SCOREBOARD]
        mask=(self.frames[:,RF_NUM_PLAYERS]==2)
        mask &= (scoreboard[:,SB_KICKOFF_TIMER_SECONDS]==0)
        mask &= (scoreboard[:,SB_GO_TO_KICKOFF]==0) & (scoreboard[:,SB_IS_OVER]==0)
        self.indices=np.flatnonzero(mask)
        if not len(self.indices):raise ValueError('No active 1v1 replay starts available')
        self.path=path.resolve()

    def sample(self,seed):
        from rlgym_tools.rocket_league.misc.serialize import (
            deserialize_replay_frame,RF_AGENT_IDS_START,GS_CARS,GS_CAR_LENGTH)
        from rlgym.rocket_league import common_values as cv
        rng=np.random.default_rng(seed)
        for _ in range(32):
            idx=int(rng.choice(self.indices))
            try:
                start=RF_AGENT_IDS_START+2*(2+8)
                end=start+GS_CARS.start+2*GS_CAR_LENGTH
                if not np.isfinite(self.frames[idx,start:end]).all():continue
                frame=deserialize_replay_frame(self.frames[idx].copy())
                state=frame.state
                if state.goal_scored or len(state.cars)!=2:continue
                if sorted(c.team_num for c in state.cars.values())!=[0,1]:continue
                cfg=state.config
                if not np.allclose([cfg.gravity,cfg.boost_consumption,cfg.dodge_deadzone],
                                   [1.,1.,.5],rtol=0,atol=1e-6):continue
                physics=[state.ball]+[c.physics for c in state.cars.values()]
                if any(not np.isfinite(x).all() for p in physics for x in
                       (p.position,p.linear_velocity,p.angular_velocity,p.rotation_mtx)):continue
                if any(not np.allclose(p.rotation_mtx.T@p.rotation_mtx,np.eye(3),atol=.02)
                       or np.linalg.det(p.rotation_mtx)<.98 for p in physics):continue
                if any(abs(p.position[0])>cv.SIDE_WALL_X or abs(p.position[1])>=cv.GOAL_THRESHOLD
                       or not 0<p.position[2]<cv.CEILING_Z for p in physics):continue
                if state.boost_pad_timers.shape!=(34,) or not np.isfinite(state.boost_pad_timers).all():continue
                if np.any(state.boost_pad_timers<0):continue
                if any(c.is_demoed or not np.isfinite(c.boost_amount) or not 0<=c.boost_amount<=100
                       for c in state.cars.values()):continue
                # The league hardcodes these IDs; preserve team membership and
                # all serialized jump/flip state rather than rebuilding a pose.
                mapping={aid:('orange-0' if c.is_orange else 'blue-0')
                         for aid,c in state.cars.items()}
                for c in state.cars.values():
                    c.bump_victim_id=mapping.get(c.bump_victim_id)
                    c.ball_touches=0
                state.cars={mapping[aid]:c for aid,c in state.cars.items()}
                state.tick_count=0
                return state,idx
            except (ValueError,TypeError,IndexError,AssertionError,OverflowError):
                continue
        raise ValueError('Replay bank did not supply a valid standard, finite 1v1 state in 32 attempts')
