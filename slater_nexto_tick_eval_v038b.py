"""Slater v0.3.8b: read-only comparison of old and tick-scheduled Nexto.

Standalone isolated simulator diagnostic. Requires Slater's existing files and
protected checkpoints under E:\\Downloads\\Chat_GPT_AI. It neither trains nor
modifies exported bots. Requires PASS v038a engine/observation gate reports.

Only the per-physics-tick scheduling is source-matched. The kickoff-pause
boolean is a *RocketSim proxy* until live RLBot trace alignment is performed.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import json
import random
import hashlib
import math
import numpy as np

from slater_nexto_scheduler_v038b import NextoV4Clock, KICKOFF_SHA, VERSION

KNOWN_V037A_SHA = 'a647823c227602f9c658a58a3e32b0d18a8dfe0dd1b144eadd93aaf9a856fd44'
KNOWN_OBS_SHA = '7247046d836059ab4428fb8f08968af1a977cf3228f1462a0235cd7a825362b0'


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def outpath(root: Path, dest_arg: str):
    path = (root / dest_arg).resolve()
    if not path.is_relative_to((root / 'data' / 'isolated').resolve()) or path.suffix != '.json':
        raise ValueError('Refusing JSON output outside data/isolated')
    if path.exists() or Path(str(path)+'.partial').exists():
        raise FileExistsError(f'Report already exists; use a new filename: {path}')
    return path


def gate(root: Path, relative: str, expected_test: str, expected_field: str):
    path=(root/relative).resolve()
    if not path.is_relative_to((root/'data'/'isolated').resolve()):
        raise ValueError('Gate must be under data/isolated')
    d=json.loads(path.read_text(encoding='utf8'))
    if d.get('test')!=expected_test or not d.get(expected_field):
        raise ValueError(f'Failed or unexpected gate {relative} (expected {expected_test})')
    if expected_test=='same_state_reference_nexto_vs_teamobserver':
        if d.get('fail_count')!=0 or d.get('action_disagreement_count')!=0 or d.get('pass_count',0)<100:
            raise ValueError('Observation stress lacks adequate coverage')
        if d.get('reference_nexto_obs_sha256')!=KNOWN_OBS_SHA:
            raise ValueError('Unexpected reference observation version')
    else:
        if d.get('max_abs_error',math.inf)>0.001 or d.get('blocks_checked',0)<8:
            raise ValueError('Physics stepping gate insufficient')
        if d.get('nexto_script_sha')!=KICKOFF_SHA:
            raise ValueError('Script changed')
    return {'path':str(path),'sha256':file_sha(path),'test':expected_test}


class TickNextoEnv:
    """Lazy RLGym wrapper: controls computed from evolving physics every tick.

    Keeps the v027 simulator geometry/scoring/reward unchanged. Unlike v037a,
    corrects action scheduling, previously overridden action, midstep changes.
    Proxy for packet.is_kickoff_pause = not yet observed first kickoff touch;
    this is NOT equivalent to a real packet authoritative flag.
    """
    def __init__(self, actions, observer, opponents, *, max_steps, device, mode, fixed_side):
        import slater_nexto_kickoff_v037a as old
        if mode not in ('nexto_greedy_tick','nexto_script_tick','nexto_stock_tick'):
            raise ValueError('Unknown tick mode')
        if fixed_side not in ('blue','orange'):
            raise ValueError('A fixed side required')
        self.base_env = old.ScriptedNextoEnv(actions, observer, opponents,
                                             max_steps=max_steps,device=device,
                                             modes=('nexto_greedy',),fixed_side=fixed_side)
        self.actions=actions
        self.mode=mode
        self.device=device
        self.scheduler=NextoV4Clock(hardcoded=mode!='nexto_greedy_tick',
                                   stochastic=mode=='nexto_stock_tick')
        self.kickoff_pause_proxy=True
        self.script_control_blocks=0
        self.ticks_stepped=0
        self.touched_before_last_tick=False
        self.inference_previous_mismatches=0

    def reset(self,seed):
        obs=self.base_env.reset(seed)
        self.scheduler.reset()
        self.kickoff_pause_proxy=True
        self.script_control_blocks=0
        self.ticks_stepped=0
        self.touched_before_last_tick=False
        return obs

    @property
    def state(self):return self.base_env.state

    @staticmethod
    def player_info(state,oid):
        # RLBot index is the position in state.cars ordered by team; for 1v1
        # this produces [blue-0, orange-0]. Validating teams is mandatory.
        ids=sorted(state.cars, key=lambda cid:(state.cars[cid].team_num,cid))
        teams=np.array([int(state.cars[cid].team_num) for cid in ids],dtype=np.int32)
        positions=np.array([state.cars[cid].physics.position[:2] for cid in ids],dtype=np.float64)
        if len(ids)!=2 or set(teams)!={0,1}:
            raise ValueError('This diagnostic supports exactly one car per team')
        return positions,teams,ids.index(oid)

    def step(self,student_action:int):
        import slater_cycle9_native_ppo_v025 as base
        import slater_nexto_kickoff_v037a as old
        env=self.base_env
        sid='blue-0' if env.student_side=='blue' else 'orange-0'
        oid='orange-0' if sid=='blue-0' else 'blue-0'
        sign=1 if env.student_side=='blue' else -1
        start_y=float(env.state.ball.position[1])
        start_dist=float(np.linalg.norm(env.state.cars[sid].physics.position-env.state.ball.position))
        student_control=np.asarray(self.actions[int(student_action)],dtype=np.float32).reshape(8)
        tick_student_touches=0
        tick_opponent_touches=0
        script_any=False
        for j in range(base.ACTION_REPEAT):
            state=env.state
            ball_xy=state.ball.position[:2]
            positions,teams,index=self.player_info(state,oid)
            # Called only on the same schedule as RLBot v4 Nexto uses; at these
            # points, the action passed to observer was scheduler.action.
            def infer(prev_action, beta):
                prev={sid:student_control.copy(),oid:prev_action.copy()}
                o=base.read_obs(state,prev,env.observer,oid)
                idx=old.sample_nexto_action(env.opponent,o,beta=beta,device=self.device)
                return idx,np.asarray(self.actions[idx],dtype=np.float32)
            f=self.scheduler.frame(is_kickoff_pause=self.kickoff_pause_proxy,
                                   ball_xy=ball_xy, positions=positions, teams=teams,
                                   index=index, infer=infer, ticks_elapsed=1)
            if f.script_applied:
                script_any=True
            env.state=env.engine.step({sid:student_control[None],oid:f.controls[None]}, {})
            self.ticks_stepped+=1
            env.previous={sid:student_control.copy(),oid:f.action.copy()}
            tc=int(env.state.cars[sid].ball_touches)
            oc=int(env.state.cars[oid].ball_touches)
            tick_student_touches+=tc
            tick_opponent_touches+=oc
            if tc or oc:
                self.kickoff_pause_proxy=False
                env.kickoff_ball_touched=True
            if env.state.goal_scored:
                # Avoid stepping through a goal after it already happened.
                break
        if script_any:
            self.script_control_blocks+=1
        env.script_action_steps=self.script_control_blocks
        env.stochastic_action_steps=self.scheduler.stochastic_nn_inferences
        env.neural_action_steps=self.scheduler.nn_inferences
        env.t+=1
        car=env.state.cars[sid];ball=env.state.ball
        progress=float(np.clip(sign*(ball.position[1]-start_y)/500.,-.5,.5))
        closing=float(np.clip((start_dist-np.linalg.norm(car.physics.position-ball.position))/500.,-.5,.5))
        outcome=int(sign*np.sign(float(ball.position[1]))) if env.state.goal_scored else 0
        reward=.20*progress+.07*closing+.35*tick_student_touches-.002+10.*outcome
        if not math.isfinite(reward):
            raise FloatingPointError('Nonfinite reward')
        env.total_reward+=reward
        env.touches+=tick_student_touches
        env.opponent_touches+=tick_opponent_touches
        done=bool(env.state.goal_scored or env.t>=env.max_steps)
        env.obs=base.read_obs(env.state,env.previous,env.observer,sid)
        return env.obs,float(reward),done,{
            'outcome':outcome,'student_side':env.student_side,'opponent':self.mode,
            'steps':env.t,'student_touches':env.touches,'opponent_touches':env.opponent_touches,
            'timeout':bool(done and not env.state.goal_scored),
            'script_action_steps':self.script_control_blocks,
            'script_physics_ticks':self.scheduler.script_physics_ticks,
            'script_interrupted_ticks':self.scheduler.interrupted_physics_ticks,
            'neural_inferences':self.scheduler.nn_inferences,
            'stochastic_neural_inferences':self.scheduler.stochastic_nn_inferences,
            'kickoff_pause_proxy':self.kickoff_pause_proxy,
            'physics_ticks':self.ticks_stepped,
        }

    def close(self):self.base_env.close()


def evaluate(root,checkpoint,seeds,horizon,seed_base):
    """All configurations run with frozen weights on paired seeds & sides."""
    import torch
    import slater_nexto_kickoff_v037a as old
    from afk_team_research import TeamObserver
    from slater_cycle9_paired_eval_v026_fixed import greedy_action
    actor,cycle9,nexto,actions,checkpoint_data,provenance=old.load_protected(root,checkpoint)
    modes=('nexto_greedy','nexto_script','nexto_stock_approx',
           'nexto_greedy_tick','nexto_script_tick','nexto_stock_tick')
    records=[]
    for i in range(seeds):
        match_seed=seed_base+997*i
        for side in ('blue','orange'):
            for mode in modes:
                for policy,model in (('u60',actor),('cycle9',cycle9)):
                    # Match stochastic sampling seeds across all modes for the
                    # same kickoff/side/student. Otherwise mode loop order
                    # contaminates the comparison through global Torch RNG.
                    episode_rng_seed = int(match_seed + (0 if side == 'blue' else 100_003)
                                           + (0 if policy == 'u60' else 200_003))
                    torch.manual_seed(episode_rng_seed)
                    np.random.seed(episode_rng_seed)
                    if mode.endswith('_tick'):
                        env=TickNextoEnv(actions,TeamObserver(),(cycle9,nexto),
                                         max_steps=horizon,device='cpu', mode=mode,fixed_side=side)
                    else:
                        env=old.ScriptedNextoEnv(actions,TeamObserver(),(cycle9,nexto),
                                                 max_steps=horizon,device='cpu',
                                                 modes=(mode,),fixed_side=side)
                    try:
                        obs=env.reset(match_seed)
                        while True:
                            obs,_,done,info=env.step(greedy_action(model,obs,'cpu'))
                            if done:
                                records.append(dict(seed=match_seed,side=side,mode=mode,
                                                    policy=policy,outcome=info['outcome'],
                                                    steps=info['steps'],timeout=info['timeout'],
                                                    script_blocks=info['script_action_steps'],
                                                    script_physics_ticks=info.get('script_physics_ticks'),
                                                    script_interrupted_ticks=info.get('script_interrupted_ticks'),
                                                    neural_inferences=info.get('neural_inferences'),
                                                    stochastic_neural_inferences=info.get('stochastic_neural_inferences'),
                                                    physics_ticks=info.get('physics_ticks')))
                                break
                    finally:env.close()
        print(f'V038B_SEED_COMPLETED {i+1}/{seeds}',flush=True)
    summary={}
    for mode in modes:
        summary[mode]={}
        for policy in ('u60','cycle9'):
            subset=[r for r in records if r['mode']==mode and r['policy']==policy]
            summary[mode][policy]={
                'episodes':len(subset),'wins':sum(r['outcome']==1 for r in subset),
                'losses':sum(r['outcome']==-1 for r in subset),
                'timeouts':sum(r['timeout'] for r in subset),
                'win_fraction_not_match_rate':sum(r['outcome']==1 for r in subset)/len(subset),
                'script_blocks':sum(r['script_blocks'] for r in subset),
                'script_physics_ticks':sum((r['script_physics_ticks'] or 0) for r in subset),
            }
    return {'version':VERSION,'status':'SIMULATOR_TICK_CONTROLLER_NOT_RLBOT_PARITY',
            'summary':summary,'records':records,'seeds':seeds,'horizon_actions':horizon,
            'provenance':provenance,
            'limitations':[
                'All scores are first-goal episodes, not five-minute matches; timeouts are censored.',
                'RocketSim kickoff-pause is approximated as until first ball touch, NOT an RLBot packet flag.',
                'The exact RLBot packet timing and packet.game_state.decode semantics remain unverified.',
                'Real Nexto stock can use stochastic sampling during kickoff pause; scripted controls commonly override it.',
                'Old v037a scripted count uses action blocks; new version tracks both 8-tick blocks and physics ticks.',
                'Need live RLBot capture and reference trace for exact parity before any training.',
            ]}


def trace(n=175,ball_move_tick=None,not_taker=False):
    if not 1<=n<=1000:raise ValueError('Bad number of ticks')
    c=NextoV4Clock(hardcoded=True,stochastic=True)
    positions=np.array([[0,-4608],[0,4608]],dtype=float)
    teams=np.array([0,1],dtype=int)
    if not_taker:
        positions[1]=[0,5120]
    def infer(prev,beta):return 16,np.asarray([1,0,0,0,0,0,1,0],dtype=np.float32)
    records=[]
    for t in range(n):
        ball_y=1.0 if ball_move_tick is not None and t>=ball_move_tick else 0.0
        out=c.frame(is_kickoff_pause=True,ball_xy=(0,ball_y),positions=positions,
                    teams=teams,index=1,infer=infer)
        if t<4 or t in (43,44,59,60,67,68,71,72,75,76,127,128,167,168,169) or t==ball_move_tick:
            records.append({'tick':t,'script_index':out.kickoff_index,
                            'script':out.script_applied,'interrupted':out.script_interrupted,
                            'ctrl':out.controls.tolist(),'neural_updated':out.neural_updated,
                            'beta':out.beta})
    return {'version':VERSION,'frames':n,'script_applied':c.script_physics_ticks,
            'interrupted':c.interrupted_physics_ticks,'neural_inferences':c.nn_inferences,
            'stochastic_nn_inferences':c.stochastic_nn_inferences,
            'control_trace':records,'script_sha':KICKOFF_SHA}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    t=sub.add_parser('trace')
    t.add_argument('--out',required=True)
    t.add_argument('--ticks',type=int,default=175)
    t.add_argument('--ball-move-tick',type=int,default=None)
    b=sub.add_parser('benchmark')
    b.add_argument('--out',required=True)
    b.add_argument('--seeds',type=int,default=2)
    b.add_argument('--horizon',type=int,default=180)
    b.add_argument('--seed',type=int,default=20261021)
    b.add_argument('--checkpoint',default='data/isolated/slater_v027_campaign01_u0060.pt')
    b.add_argument('--physics-gate',default='data/isolated/v038a_engine_gate01.json')
    b.add_argument('--obs-gate',default='data/isolated/v038a_obs_stress01.json')
    a=p.parse_args(argv)
    root=Path.cwd().resolve()
    dest=outpath(root,a.out)
    if a.command=='trace':
        data=trace(a.ticks,a.ball_move_tick)
    else:
        if not 1<=a.seeds<=24 or not 30<=a.horizon<=4500 or not 1<=a.seed<2**31-5000000:
            p.error('Invalid benchmark settings')
        import slater_nexto_kickoff_v037a as old
        if file_sha(root/'slater_nexto_kickoff_v037a.py')!=KNOWN_V037A_SHA:
            raise RuntimeError('v037a source changed; benchmark guard failed')
        required={
            'physics':gate(root,a.physics_gate,'eight_ticks_batch_vs_eight_single_ticks','passed'),
            'observation':gate(root,a.obs_gate,'same_state_reference_nexto_vs_teamobserver','allclose'),
        }
        import torch
        torch.set_num_threads(2)
        torch.manual_seed(a.seed);np.random.seed(a.seed);random.seed(a.seed)
        ck=(root/a.checkpoint).resolve()
        data=evaluate(root,ck,a.seeds,a.horizon,a.seed)
        data['gates']=required
        data['reference_v037a_sha']=KNOWN_V037A_SHA
        print('V038B_COMPARISON',json.dumps(data['summary'],sort_keys=True),flush=True)
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open('x',encoding='utf8') as f:json.dump(data,f,indent=2,sort_keys=True)
    print('V038B_REPORT',dest,flush=True)


if __name__=='__main__':main()
