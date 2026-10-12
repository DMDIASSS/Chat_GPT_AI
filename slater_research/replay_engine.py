"""Two-phase replay-to-RocketSim scenario utilities.

Place this package next to the project's existing `replay_defense.py`. Requires:
    pip install rlgym rlgym-tools RocketSim

IMPORTANT: Replay inference has imperfect control labels. Kinematic ghosts are
counterfactual training aids and DO NOT establish deterministic physical fidelity.
"""
from __future__ import annotations
from dataclasses import dataclass
import bisect
import copy
import hashlib
import json
import math
from pathlib import Path
import numpy as np

TICKS = 8
FPS = 120


def _row_at(table, frame):
    """Replay dataframes can have duplicate frame indices; use first row."""
    row = table.loc[int(frame)]
    return row.iloc[0] if getattr(row, 'ndim', 1) != 1 else row


def goal_events(parsed, stats=None):
    """Get (goal_time, last-scoring-team-touch ID) from replay gameplay periods.

    rlgym-tools/carball gameplay_periods supply goal_frame. Analyzer hits are
    NOT generally labelled `is_goal`, which made v1 export zero clips.

    Important: last scoring-team touch is an inferred shooter, NOT guaranteed
    to be the officially credited goal scorer. Reject apparent own goals.
    """
    if stats is None:
        stats={}
    periods=parsed.analyzer.get('gameplay_periods', [])
    stats['goal_periods']=sum(p.get('goal_frame') is not None for p in periods)
    stats['inferred_events']=0
    stats['own_goal_skips']=0
    stats['missing_touch_skips']=0
    stats['missing_goal_frame_data']=0

    players={str(p['unique_id']):p for p in parsed.metadata.get('players', [])
             if isinstance(p,dict) and p.get('unique_id') is not None}
    hits=sorted((h for h in parsed.analyzer.get('hits', [])
                 if h.get('frame_number') is not None and h.get('player_unique_id') is not None),
                key=lambda h: int(h['frame_number']))
    result=[]
    for period in periods:
        goal_frame=period.get('goal_frame')
        if goal_frame is None:
            continue
        try:
            goal_frame=int(goal_frame)
            start_frame=int(period.get('start_frame',0))
            goal_time=float(_row_at(parsed.game_df,goal_frame)['time'])
            goal_y=float(_row_at(parsed.ball_df,goal_frame)['pos_y'])
            if not np.isfinite(goal_time) or not np.isfinite(goal_y):
                raise ValueError('Non-finite goal information')
        except (IndexError,KeyError,ValueError,TypeError):
            stats['missing_goal_frame_data']+=1
            continue
        # Ball in the positive-Y goal means blue scored; negative means orange.
        scoring_orange=goal_y<0
        relevant=[h for h in hits if start_frame<=int(h['frame_number'])<=goal_frame
                  and str(h['player_unique_id']) in players]
        if not relevant:
            stats['missing_touch_skips']+=1
            continue
        last_hit=relevant[-1]
        last_player=players[str(last_hit['player_unique_id'])]
        if bool(last_player.get('is_orange'))!=scoring_orange:
            stats['own_goal_skips']+=1
            continue
        scorer=str(last_hit['player_unique_id'])
        result.append((goal_time,scorer))
    # Prefer the converter's authoritative gameplay period boundaries. Fall back
    # to explicit goal-tagged hits only for parsers without those boundaries.
    if not periods:
        for h in hits:
            if h.get('is_goal') is not True and h.get('goal') is not True:
                continue
            try:
                t=float(_row_at(parsed.game_df,int(h['frame_number']))['time'])
            except (KeyError,IndexError,TypeError,ValueError):
                continue
            result.append((t,str(h['player_unique_id'])))
    stats['inferred_events']=len(set(result))
    return sorted(set(result))


def _mapped_frame(frame, ids):
    from rlgym_tools.rocket_league.misc.serialize import serialize_replay_frame
    f=copy.deepcopy(frame)
    old=sorted(int(x) for x in f.state.cars)
    if len(old)!=len(ids):raise ValueError('Roster size changed within clip')
    if set(old)!=set(ids):raise ValueError('Roster changed within clip')
    mapping={a:i+1 for i,a in enumerate(ids)}
    f.state.cars={mapping[a]:f.state.cars[a] for a in ids}
    f.actions={mapping[a]:f.actions.get(a,np.zeros(8)) for a in ids}
    f.update_age={mapping[a]:f.update_age.get(a,0) for a in ids}
    for c in f.state.cars.values():
        target=getattr(c,'bump_victim_id',None)
        if target in mapping:c.bump_victim_id=mapping[target]
        elif target is not None:c.bump_victim_id=None
    return np.asarray(serialize_replay_frame(f),dtype=np.float32)


def extract_goal_clips(replay_file, output_dir, lead_seconds=12.0, trailing_seconds=0.6, diagnostics=None):
    """Extract goals from 1v1, 2v2 and 3v3; goal-labelled hits only.

    Clips contain serialized states AND inferred actions and are losslessly
    grouped at replay level for train/val/test splitting. This is an exporter,
    NOT training code. Stops at previous goal/kickoff and rejects bad gaps.
    """
    from rlgym_tools.rocket_league.replays.parsed_replay import ParsedReplay
    from rlgym_tools.rocket_league.replays.convert import replay_to_rlgym
    src=Path(replay_file)
    rp=ParsedReplay.load(str(src))
    if diagnostics is None:
        diagnostics={}
    events=goal_events(rp,diagnostics)
    diagnostics['clip_skip_reasons']={}
    diagnostics['sample_failures']=[]
    diagnostics['goal_events']=len(events)
    if not events:return []
    frames=list(replay_to_rlgym(rp,interpolation='linear'))
    diagnostics['converted_frames']=len(frames)
    if not frames:return []
    # Ensure goal clips never span a preceding kickoff/reset. The previous
    # detected GOAL alone is not a sufficiently reliable period boundary.
    period_start_by_goal_time={}
    for period in rp.analyzer.get('gameplay_periods',[]):
        if period.get('goal_frame') is None:continue
        try:
            gt=float(_row_at(rp.game_df,period['goal_frame'])['time'])
            st=float(_row_at(rp.game_df,period['start_frame'])['time'])
            period_start_by_goal_time[gt]=st
        except (KeyError,IndexError,TypeError,ValueError):pass
    times=np.asarray([f.state.tick_count/FPS for f in frames],np.float64)
    if np.any(np.diff(times)<0):raise ValueError('Non-monotone replay ticks')
    sh=hashlib.sha256(src.read_bytes()).hexdigest()
    outdir=Path(output_dir);outdir.mkdir(parents=True,exist_ok=True)
    emitted=[]
    def skip(reason, detail=None):
        reasons=diagnostics['clip_skip_reasons']
        reasons[reason]=reasons.get(reason,0)+1
        if detail is not None and len(diagnostics['sample_failures']) < 8:
            diagnostics['sample_failures'].append({'reason':reason, **detail})
    last_goal=-1.e9
    for seq,(goal_time,scorer) in enumerate(events):
        first=max(goal_time-lead_seconds,last_goal+1.0,
                  period_start_by_goal_time.get(goal_time,-1.e9))
        # Replay conversion ends the gameplay period at the scored goal.
        # Frames beyond the goal can belong to the next kickoff. Never cross it.
        last=goal_time
        if first>goal_time-10.0:
            skip('less_than_10_seconds_of_play')
            last_goal=goal_time;continue
        start=int(np.searchsorted(times,first,'left'))
        end=int(np.searchsorted(times,last,'right'))
        if end-start<10:
            skip('insufficient_converted_frames')
            last_goal=goal_time;continue
        ids=sorted(int(a) for a in frames[start].state.cars)
        if len(ids) not in (2,4,6):
            skip('unsupported_roster')
            last_goal=goal_time;continue
        samples=[];actions=[]
        failure=None
        # RLGym-Tools sets state.tick_count = replay_time * 120, which can be
        # fractional. int() floors to a tick BEFORE the first replay frame,
        # causing *every* clip to fail the i < start check on its first sample.
        # Start on the first physics tick at/after the first available frame.
        tick0=math.ceil(float(times[start])*FPS - 1.e-7)
        tick_end=math.floor(min(float(times[end-1]),float(last))*FPS + 1.e-7)
        for tick in range(tick0,tick_end+1,TICKS):
            t=tick/FPS
            i=bisect.bisect_right(times,t)-1
            if i<start or i>=end:
                failure=('timestamp_outside_clip',{'t':round(t,4),'frame_index':i,'start':start,'end':end})
                break
            age=t-times[i]
            if age < -1e-6 or age > .11:
                failure=('time_gap_over_110ms',{'t':round(t,4),'last_frame_time':round(float(times[i]),4),'age_s':round(float(age),4)})
                break
            try:
                f=frames[i]
                serialized=_mapped_frame(f,ids)
                aa=np.array([f.actions.get(a,np.zeros(8)) for a in ids],np.float32)
                if aa.shape!=(len(ids),8) or not np.isfinite(aa).all():
                    failure=('invalid_controls',{'t':round(t,4),'shape':list(aa.shape)})
                    break
                samples.append(serialized)
                actions.append(aa)
            except Exception as exc:
                failure=('frame_serialization_failed',{'t':round(t,4),'error':f'{type(exc).__name__}: {exc}'[:250]})
                break
        if failure is None and len(samples)>=10 and len({len(x) for x in samples})!=1:
            failure=('serialized_frame_length_changed',{'lengths':sorted({len(x) for x in samples})})
        if failure is None and len(samples)>=10:
            # Always bound future exports: no destructive replacement.
            dest=outdir/f'{sh[:14]}_goal{seq:03d}.npz'
            if dest.exists():raise FileExistsError(dest)
            scored_id=int(scorer) if scorer.isdecimal() else None
            if scored_id not in ids:
                skip('scorer_not_in_roster')
                last_goal=goal_time;continue
            np.savez_compressed(dest,
                frames=np.stack(samples), controls=np.stack(actions),
                agent_ids=np.arange(1,len(ids)+1,dtype=np.int64),
                shooter_id=np.int64(ids.index(scored_id)+1),
                goal_step=np.int64(min(len(samples)-1,max(0,round((goal_time-tick0/FPS)/(TICKS/FPS))))),
                ticks_per_step=np.int64(TICKS),
                replay_sha=np.array(sh),
                inference_warning=np.array('replay inputs are inferred, not exact controller telemetry'),
                shooter_attribution_warning=np.array('shooter ID is the last ball-touching player on the scoring team, not necessarily the credited scorer'))
            emitted.append(dest)
        elif failure is not None:
            skip(failure[0],failure[1])
        else:
            skip('fewer_than_10_samples')
        last_goal=goal_time
    diagnostics['emitted_clips']=len(emitted)
    return emitted


@dataclass
class Clip:
    snapshots: list
    controls: np.ndarray
    ids: tuple
    shooter_id: int
    goal_step: int
    replay_sha: str

    @classmethod
    def load(cls, filename):
        from rlgym_tools.rocket_league.misc.serialize import deserialize_replay_frame
        with np.load(filename,allow_pickle=False) as f:
            snapshots=[deserialize_replay_frame(raw).state for raw in f['frames']]
            controls=f['controls'].copy()
            ids=tuple(int(v) for v in f['agent_ids'])
            shooter=int(f['shooter_id']);goal=int(f['goal_step'])
            digest=str(f['replay_sha'])
            tick=int(f['ticks_per_step'])
        if tick!=TICKS:raise ValueError(f'Expected {TICKS}-tick clips, got {tick}')
        if len(snapshots)!=len(controls) or controls.shape!=(len(snapshots),len(ids),8):
            raise ValueError('Malformed scenario arrays')
        if shooter not in ids:raise ValueError('Shooter not in roster')
        return cls(snapshots,controls,ids,shooter,goal,digest)


def split_replay(digest):
    """Replay-level deterministic split, preventing adjacent goals leaking."""
    b=int(digest[:8],16)%100
    return 'train' if b<80 else ('validation' if b<90 else 'test')


class TwoPhaseScenario:
    """One learner or multiple cooperative learners, with ghosted other cars.

    The learner's CAR and BALL remain physically dynamic. All other car poses
    are replay-positioned immediately before each RocketSim transition;
    these are *kinematic approximations* (possible teleport artifacts).
    Use only for a first curriculum, then transfer to all-physics opponents.
    """
    def __init__(self, clip: Clip, engine, phase='shooter', defenders=None, horizon=None):
        if phase not in ('shooter','defender'):raise ValueError(phase)
        self.clip=clip;self.engine=engine;self.phase=phase
        shooter=clip.shooter_id
        defending_orange=not clip.snapshots[0].cars[shooter].is_orange
        eligible=[a for a in clip.ids if clip.snapshots[0].cars[a].is_orange==defending_orange]
        self.learners=(shooter,) if phase=='shooter' else tuple(defenders or eligible)
        if not self.learners or any(a not in eligible for a in self.learners) and phase=='defender':
            raise ValueError('Defenders must be on the conceding team')
        self.horizon=min(horizon or len(clip.snapshots)-1,len(clip.snapshots)-1)
        self.idindex={a:i for i,a in enumerate(clip.ids)}
        self.reset()

    def reset(self, start_step=0):
        # Short starts (0.5/2/4/8/12s before shot) form the fidelity curriculum.
        if not 0<=start_step<self.horizon:raise ValueError(start_step)
        self.i=start_step
        self.state=self.engine.set_state(copy.deepcopy(self.clip.snapshots[start_step]),{})
        self.last_ball=np.asarray(self.state.ball.position,float).copy()
        self.touch_count={a:0 for a in self.learners}
        self.was_threat=False
        return self.state

    def step(self, actions):
        if set(actions)!=set(self.learners):raise KeyError('Action required for every learner')
        # Only override nonlearning cars; keep learner states and ball dynamic.
        force=copy.deepcopy(self.state)
        reference=self.clip.snapshots[self.i]
        for aid in self.clip.ids:
            if aid not in self.learners:
                force.cars[aid]=copy.deepcopy(reference.cars[aid])
        self.state=self.engine.set_state(force,{})
        inputs={}
        for aid in self.clip.ids:
            vec=(np.asarray(actions[aid],float) if aid in self.learners
                 else self.clip.controls[self.i,self.idindex[aid]])
            if vec.shape!=(8,):raise ValueError('Controls must be 8-vectors')
            inputs[aid]=np.tile(np.clip(vec,-1,1).astype(np.float32),(TICKS,1))
        previous_ball=np.asarray(self.state.ball.position,float).copy()
        self.state=self.engine.step(inputs,{})
        self.i+=1
        terminal=self.state.goal_scored or self.i>=self.horizon
        rewards={a:0.0 for a in self.learners}
        if self.phase=='shooter':
            target=self.clip.snapshots[self.i]
            for a in self.learners:
                p=self.state.cars[a].physics; q=target.cars[a].physics
                epos=np.linalg.norm(p.position-q.position)/2300
                evel=np.linalg.norm(p.linear_velocity-q.linear_velocity)/2300
                er=np.linalg.norm(p.rotation_mtx-q.rotation_mtx)/3
                # Dense imitation shaped as bounded similarity, not raw positive drift.
                rewards[a]=float(.045*np.exp(-epos**2/.16-evel**2/.64-er**2/.25))
                if self.state.cars[a].ball_touches:rewards[a]+=0.4
                if self.state.goal_scored:rewards[a]+=10.
        else:
            for a in self.learners:
                car=self.state.cars[a]
                if car.ball_touches:
                    self.touch_count[a]+=1
                    y=np.asarray(self.state.ball.linear_velocity)[1]
                    # A meaningful clear should reverse flow from its own net
                    own_goal_sign=1 if car.is_orange else -1
                    if own_goal_sign*y<0:rewards[a]+=1.0
                if self.state.goal_scored:
                    own_score=0 if self.state.ball.position[1]>0 else 1
                    rewards[a]+=10. if car.team_num==own_score else -10.
                else:
                    # No +10 for merely surviving a short episode; must verify a baseline threat.
                    rewards[a]-=0.001
        self.last_ball=previous_ball
        return self.state,rewards,bool(terminal),{'frame':self.i,'phase':self.phase}

    def close(self): self.engine.close()


def counterfactual_goal_check(clip: Clip, *, max_shot_position_error=250.0):
    """Strict pre-train fidelity gate with inferred defender controls.

    Return dict: replay scorer's opponent net must be reached, and simulated
    ball at annotated shot moment must be reasonably close to replay ball.
    Kinematic ghosts do not guarantee genuine reproduction; evaluate visual
    quality and collision contact traces on your Windows RocketSim build.
    """
    from rlgym.rocket_league.sim import RocketSimEngine
    shooter=clip.shooter_id
    attacker_orange=clip.snapshots[0].cars[shooter].is_orange
    defenders=[a for a in clip.ids if clip.snapshots[0].cars[a].is_orange!=attacker_orange]
    engine=RocketSimEngine(rlbot_delay=False)
    try:
        env=TwoPhaseScenario(clip,engine,phase='defender',defenders=defenders)
        score=False;ball_errors=[]
        while True:
            commands={a:clip.controls[env.i,env.idindex[a]] for a in env.learners}
            state,reward,done,_=env.step(commands)
            if env.i==min(clip.goal_step,len(clip.snapshots)-1):
                target=clip.snapshots[env.i].ball.position
                ball_errors.append(float(np.linalg.norm(state.ball.position-target)))
            if state.goal_scored:
                scorer_blue=state.ball.position[1]>0
                score=(scorer_blue != attacker_orange)
            if done:break
        e=min(ball_errors) if ball_errors else float('inf')
        return {'accepted':bool(score and e<=max_shot_position_error),
                'scored_as_reference':bool(score),
                'ball_error_uu_at_goal_frame':e,
                'criterion':'trajectory-only diagnostic; not exact replay reconstruction'}
    finally:engine.close()
