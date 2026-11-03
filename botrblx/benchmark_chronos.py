"""Reproducible, actor-only RocketSim 1v1 comparison, independent of Roblox.

This is a bounded first-goal experiment against original Nexto. It is not a
ranking of all public bots and does not measure Turbo Soccer playing strength.
"""
import argparse
import json
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch

from chronos import ACTIONS, APP, Chronos, MANIFEST, PADS, observe, resolve_action

sys.path.insert(0, str(APP.parent))
from nexto_teacher import NextoTeacher
from independent_nexto_benchmark import build_cases


def has_flip_or_jump(car):
    # Exact CarState::HasFlipOrJump from the pinned Chronos RocketSim source.
    return car.on_ground or (not car.has_flipped and not car.has_double_jumped and car.air_time_since_jump < 1.25)


def packet_for(state, agent):
    car = state.cars[agent]
    def body(c):
        p = c.physics
        return dict(position=p.position.tolist(), velocity=p.linear_velocity.tolist(),
            angular_velocity=p.angular_velocity.tolist(), forward=p.rotation_mtx[:,0].tolist(),
            up=p.rotation_mtx[:,2].tolist(), has_jumped=c.has_jumped, is_demoed=c.is_demoed)
    return dict(team=int(car.is_orange), boost=car.boost_amount, ground_estimate=car.on_ground,
        has_jumped=car.has_jumped, is_demoed=car.is_demoed, car=body(car),
        ball=dict(position=state.ball.position.tolist(), velocity=state.ball.linear_velocity.tolist(),
                  angular_velocity=state.ball.angular_velocity.tolist()),
        other_cars=[dict(body(c), team=int(c.is_orange), boost_estimate=c.boost_amount,
            ground_estimate=c.on_ground, flip_estimate=has_flip_or_jump(c))
            for aid,c in state.cars.items() if aid != agent],
        boost_pads=[dict(position=p.tolist(), is_big=bool(p[2]>72), active=bool(timer<=0),
                        cooldown_remaining=float(timer)) for p,timer in zip(PADS,state.boost_pad_timers)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets',type=Path,default=APP/'models/chronos')
    parser.add_argument('--pairs',type=int,default=16)
    parser.add_argument('--decisions',type=int,default=750)
    parser.add_argument('--seed',type=int,default=9317701)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.pairs<1 or args.decisions<1:raise ValueError('Positive pairs and decisions required')
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    from chatgpt_ai.curriculum import ChatGPTCurriculum
    model=Chronos(args.assets)
    teacher=NextoTeacher()
    torch.set_num_threads(1)
    engine=RocketSimEngine(rlbot_delay=False)
    team_mutator=FixedTeamSizeMutator(blue_size=1,orange_size=1)
    totals=dict(chronos=0,nexto=0,draw=0)
    records=[]
    started=time.monotonic()
    try:
        for seed,orange,scenario in build_cases(args.seed,args.pairs):
            random.seed(seed);np.random.seed(seed)
            rng=random.Random(seed)
            base=engine.create_base_state();team_mutator.apply(base,{})
            (KickoffMutator() if scenario=='kickoff' else ChatGPTCurriculum('grounded')).apply(base,{})
            state=engine.set_state(base,{})
            ours=next(aid for aid,c in state.cars.items() if bool(c.is_orange)==orange)
            enemy=next(aid for aid in state.cars if aid!=ours)
            prev={aid:np.zeros(8,dtype=np.float32) for aid in state.cars}
            winner='draw'
            for tick in range(args.decisions):
                packet=packet_for(state,ours)
                c=state.cars[ours]
                obs,context=observe(packet,prev[ours],has_flip_or_jump(c),rng)
                with torch.inference_mode():
                    logits=model(torch.from_numpy(obs).unsqueeze(0))[0]
                    index=int(logits.masked_fill(~torch.tensor(context['mask']),-float('inf')).argmax())
                a=resolve_action(index,context['mirror'])
                view=next(v for v in teacher.observe(state,prev) if v[0]==enemy)
                b=ACTIONS[int(teacher.logits([(view[1],view[2],view[3])])[0].argmax())]
                # Both actors: evaluate every 8 ticks; apply after a 7-tick delay.
                commands={ours:np.vstack([np.tile(prev[ours],(7,1)),a]),
                          enemy:np.vstack([np.tile(prev[enemy],(7,1)),b])}
                state=engine.step(commands,{})
                prev={ours:a,enemy:b}
                if state.goal_scored:
                    scorer_orange=bool(state.ball.position[1]<0)
                    winner='chronos' if scorer_orange==orange else 'nexto'
                    break
            totals[winner]+=1
            record=dict(seed=seed,chronos_orange=orange,scenario=scenario,winner=winner,decisions=tick+1)
            records.append(record)
            print(json.dumps(dict(game=len(records),totals=totals,**record)),flush=True)
    finally:
        engine.close()
    report=dict(model=MANIFEST,opponent='original Nexto',seed=args.seed,pairs=args.pairs,
        decisions_limit=args.decisions,totals=totals,games=records,seconds=time.monotonic()-started,
        scope='RocketSim 1v1, bounded first-goal episodes, actors only, both team assignments, 7-tick action delay',
        limitations=['No Roblox execution or match results','Does not compare the other linked bots',
                     'No scripted kickoff overrides; not full five-minute matches',
                     'Simulator truth is available, unlike estimated Roblox opponent boost/jump state'])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(report=str(args.output),totals=totals)),flush=True)


if __name__=='__main__':main()
