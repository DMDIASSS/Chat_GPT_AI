"""Slater v0.3.3: search *physical* speedflip control sequences with RocketSim.

This is an isolated mechanics experiment, NOT an RLBot export or a change to an
existing learned policy. All candidates use per-physics-tick controls (120 Hz),
which the old 90-action Nexto policy cannot represent.

Search requires a local RLGym RocketSim install. Save results only under
`data/isolated` and NEVER overwrite previous reports. A macro is marked
`validated` ONLY if it beats plain boost while recovering on *new* seeds.
"""
from __future__ import annotations
import argparse
import json
import math
import random
from pathlib import Path

import numpy as np

FPS = 120
HORIZON = 240


def control(throttle=1., steer=0., pitch=0., yaw=0., roll=0., jump=0., boost=1., handbrake=0.):
    return np.asarray((throttle, steer, pitch, yaw, roll, jump, boost, handbrake), dtype=np.float32)


def macro(params: dict, *, side: int = -1, ticks: int = HORIZON) -> np.ndarray:
    """Input order: throttle steer pitch yaw roll jump boost handbrake.

    Diagonal dodge (second jump) is followed by opposite pitch cancellation.
    We *search* the timings; none of these constitute a proven speedflip.
    """
    if side not in (-1, 1): raise ValueError('side must be -1 or +1')
    if ticks < 180: raise ValueError('Need >=180 ticks for recovery check')
    start=int(params['start']); held=int(params['held']); released=int(params['released'])
    dodge=int(params['dodge']); cancel=int(params['cancel'])
    diag=float(params['diag']); airroll=float(params['airroll']); correction=int(params['correction'])
    assert 0<=start<60 and 1<=held<=15 and 1<=released<=12 and 1<=dodge<=5
    assert 4<=cancel<=80 and .1<=diag<=1.0 and 0<=airroll<=1.0 and 0<=correction<=70
    j1=start; j1end=j1+held; j2=j1end+released; j2end=j2+dodge
    if j2end+cancel+correction>ticks: raise ValueError('Macro extends beyond horizon')
    a=np.tile(control(),(ticks,1))
    a[j1:j1end,5]=1.0
    a[j1:j1end,2]=-float(params.get('first_pitch',0.0))
    # Jump edge and diagonal dodge toward car's forward direction.
    a[j2:j2end,5]=1.0
    a[j2:j2end,2]=-1.0
    a[j2:j2end,3]=side*diag
    # Cancel pitch; use air roll to reorient and recover.
    a[j2end:j2end+cancel,2]=1.0
    a[j2end:j2end+cancel,4]=-side*airroll
    if correction:
        a[j2end+cancel:j2end+cancel+correction,4]=side*airroll*.6
        a[j2end+cancel:j2end+cancel+correction,2]=float(params.get('correction_pitch',0.0))
    return a


def random_params(rng:random.Random) -> dict:
    return {'start':rng.randrange(5,36), 'held':rng.randrange(1,10),
            'released':rng.randrange(2,8), 'dodge':rng.randrange(1,4),
            'cancel':rng.randrange(10,51), 'diag':round(rng.uniform(.45,1.),3),
            'airroll':round(rng.uniform(.1,1.),3), 'correction':rng.randrange(0,46),
            'first_pitch':0.0,'correction_pitch':0.0}


def seed_list(seed:int,n:int,*,holdout:bool=False)->list[int]:
    if not 1<=n<=20:raise ValueError('1-20 seeds required')
    base=seed+1000003 if holdout else seed
    return [base+7919*i for i in range(n)]


def checked_out(out:str, root:Path)->Path:
    dest=Path(out).resolve()
    safe=(root/'data'/'isolated').resolve()
    if not dest.is_relative_to(safe) or dest.suffix!='.json':
        raise ValueError('Report must be a .json in data/isolated')
    if dest.exists(): raise FileExistsError('Will not overwrite '+str(dest))
    return dest


def run_physics(frames:np.ndarray, seed:int)->dict:
    """Fresh RocketSim engine and deterministic reset per rollout.

    Do not average away a failing landing: every seed's result is retained.
    """
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator, KickoffMutator
    frames=np.asarray(frames,dtype=np.float32)
    if frames.ndim!=2 or frames.shape[1]!=8 or len(frames)!=HORIZON:
        raise ValueError('Expected 240 x 8 physics control array')
    if not np.isfinite(frames).all(): raise ValueError('Nonfinite controls')
    random.seed(int(seed));np.random.seed(int(seed)%(2**32))
    engine=RocketSimEngine(rlbot_delay=False)
    try:
        state=engine.create_base_state()
        FixedTeamSizeMutator(blue_size=1,orange_size=0).apply(state,{})
        KickoffMutator().apply(state,{})
        state=engine.set_state(state,{})
        car=state.cars['blue-0'].physics
        p0=np.asarray(car.position,dtype=float).copy()
        forward=np.asarray(car.forward[:2],dtype=float).copy()
        forward/=np.linalg.norm(forward)+1e-12
        metrics={}
        first_touch_tick=None
        for i in range(0,HORIZON,8):
            state=engine.step({'blue-0':frames[i:i+8]}, {})
            c=state.cars['blue-0'];phy=c.physics
            if first_touch_tick is None and c.ball_touches>0:first_touch_tick=i+8
            if i+8 in (96,144,192,240):
                pos=np.asarray(phy.position,dtype=float)
                facing=np.asarray(phy.forward[:2],dtype=float)
                facing/=np.linalg.norm(facing)+1e-12
                velocity=np.asarray(phy.linear_velocity,dtype=float)
                up=getattr(phy,'up',None)
                upright_z=None if up is None else float(np.asarray(up,dtype=float)[2])
                metrics[str(i+8)]={'forward_progress':float(np.dot(pos[:2]-p0[:2],forward)),
                    'forward_speed':float(np.dot(velocity[:2],forward)),
                    'speed':float(np.linalg.norm(velocity)),
                    'height':float(pos[2]),
                    'on_ground':bool(c.on_ground),
                    'alignment':float(np.dot(facing,forward)),
                    'upright_z':upright_z}
        return {'seed':seed,'metrics':metrics,'first_touch_tick_upper':first_touch_tick}
    finally:engine.close()


def qualified(one:dict, baseline:dict, *, min_gain:float=35.) -> bool:
    end=one['metrics']['240'];boost=baseline['metrics']['240']
    upright=end['upright_z']
    return bool(end['on_ground'] and end['alignment']>.93 and
            (upright is None or upright>.88) and
            end['forward_speed']>1400. and
            end['forward_progress']>=boost['forward_progress']+min_gain)


def score(one:dict, baseline:dict)->float:
    # Physical distance early/late vs matched plain boost, with explicit
    # recovery penalties. Search score isn't the validation decision.
    m=one['metrics'];b=baseline['metrics'];end=m['240']
    gain=(m['144']['forward_progress']-b['144']['forward_progress'])*.25
    gain+=m['192']['forward_progress']-b['192']['forward_progress']
    gain+=.6*(end['forward_progress']-b['240']['forward_progress'])
    if not end['on_ground']:gain-=850
    gain-=500*max(0., .95-end['alignment'])
    if end['upright_z'] is not None:gain-=500*max(0., .9-end['upright_z'])
    gain-=.2*max(0., 1700-end['forward_speed'])
    return float(gain)


def search(trials:int, train_seeds:list[int], val_seeds:list[int], seed:int)->dict:
    rng=random.Random(seed)
    boost=np.tile(control(),(HORIZON,1))
    baseline_train=[run_physics(boost,s) for s in train_seeds]
    # Even the canonical rough v031 sequence gets evaluated alongside random
    # timing variations. Never claim it is a successful speedflip a priori.
    seeds=[{'start':22,'held':7,'released':4,'dodge':2,'cancel':30,
            'diag':.72,'airroll':.68,'correction':0,'first_pitch':0.,'correction_pitch':0.}]
    seeds += [random_params(rng) for _ in range(trials-1)]
    ranking=[]
    for idx,p in enumerate(seeds):
        controls=macro(p)
        runs=[run_physics(controls,s) for s in train_seeds]
        scores=[score(r,b) for r,b in zip(runs,baseline_train)]
        passes=[qualified(r,b) for r,b in zip(runs,baseline_train)]
        ranking.append({'trial':idx,'parameters':p,'train_score':sum(scores)/len(scores),
            'train_passes':sum(passes),'train_runs':runs})
        if (idx+1)%max(1,min(trials,20))==0 or idx==0:
            leader=max(ranking,key=lambda x:(x['train_passes'],x['train_score']))
            print('SEARCH_PROGRESS',json.dumps({'tested':idx+1,'total':trials,
                'top_train_passes':leader['train_passes'],'top_train_score':round(leader['train_score'],2)}),flush=True)
    # Holdout scores are computed ONLY after selecting the best training macro.
    best=max(ranking,key=lambda x:(x['train_passes'],x['train_score']))
    baseline_val=[run_physics(boost,s) for s in val_seeds]
    candidate_val=[run_physics(macro(best['parameters']),s) for s in val_seeds]
    gains=[round(a['metrics']['240']['forward_progress']-b['metrics']['240']['forward_progress'],2)
           for a,b in zip(candidate_val,baseline_val)]
    passes=[qualified(a,b) for a,b in zip(candidate_val,baseline_val)]
    validated=bool(all(passes))
    return {'version':'v0.3.3','status':'PHYSICS_VALIDATED_ON_NEW_SEEDS' if validated else 'UNVALIDATED_EXPERIMENT',
        'validated':validated,'metric':'forward progress at 2.0s vs pure boosting; grounded, upright, forward-facing',
        'trials':trials,'train_seeds':train_seeds,'heldout_seeds':val_seeds,
        'best_parameters':best['parameters'],'best_train_score':best['train_score'],
        'best_train_passes':best['train_passes'],'train_count':len(train_seeds),
        'holdout_progress_gain_uu':gains,'holdout_passes':passes,
        'heldout_baseline':baseline_val,'heldout_candidate':candidate_val,
        'warnings':['This is NOT a trained skill and is not installed in RLBot.',
            'Only 1v0 physical acceleration has been measured, not 1v1 kickoffs.',
            'If validated=false, do not deploy the macro.',
            'Both left and right orientations must be verified before RLBot use.']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trials',type=int,default=96)
    p.add_argument('--train-seeds',type=int,default=2)
    p.add_argument('--holdout-seeds',type=int,default=3)
    p.add_argument('--seed',type=int,default=20261011)
    p.add_argument('--out',required=True)
    a=p.parse_args()
    if not 2<=a.trials<=600:p.error('trials must be 2..600')
    if not 1<=a.train_seeds<=12:p.error('train-seeds 1..12')
    if not 1<=a.holdout_seeds<=12:p.error('holdout-seeds 1..12')
    root=Path.cwd().resolve()
    dst=checked_out(a.out,root)
    print('SPEEDFLIP_PHYSICS_SEARCH no training checkpoint changed; each trial per-tick 120Hz',flush=True)
    report=search(a.trials,seed_list(a.seed,a.train_seeds),seed_list(a.seed,a.holdout_seeds,holdout=True),a.seed)
    dst.parent.mkdir(parents=True,exist_ok=True)
    with dst.open('x',encoding='utf8') as f:json.dump(report,f,indent=2,allow_nan=False)
    print('BEST_MACRO',json.dumps({'validated':report['validated'],'status':report['status'],
        'train_passes':report['best_train_passes'],'holdout_passes':report['holdout_passes'],
        'holdout_gain_uu':report['holdout_progress_gain_uu'],
        'params':report['best_parameters']}),flush=True)
    print('SAVED_CREATE_ONLY',dst,flush=True)
    if not report['validated']:
        print('NOT_READY_FOR_RLBOT: no physics validation; do not install this macro.',flush=True)
if __name__=='__main__':main()
