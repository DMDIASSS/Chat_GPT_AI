"""RLViser preview of specialist scenarios; does not update model."""
import argparse
import random
import time
from pathlib import Path
import numpy as np
from mechanics_scenarios import STAGES
from mechanics_tasks import MechanicsMatch
from mechanics_train import ROOT, DEFAULT_SOURCE, load_actor
from native_nexto import select_action
from nexto_teacher import NextoTeacher


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--stage',required=True,choices=STAGES)
    p.add_argument('--source', choices=['baseline','candidate'],default='candidate')
    p.add_argument('--speed', type=float,default=1.)
    p.add_argument('--episodes',type=int,default=10)
    p.add_argument('--episode-decisions',type=int,default=120)
    p.add_argument('--opponent',choices=['passive','nexto'],default='passive')
    p.add_argument('--seed',type=int,default=123)
    args=p.parse_args()
    if args.speed <= 0: p.error('speed must be positive')
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.rlviser import RLViserRenderer
    ck=DEFAULT_SOURCE if args.source=='baseline' else ROOT/'data'/'mechanics'/args.stage/'last.pt'
    actor=load_actor(ck,'cpu')
    teacher=NextoTeacher('cpu')
    rng=np.random.default_rng(args.seed)
    random.seed(args.seed)
    engine=RocketSimEngine(rlbot_delay=False)
    renderer=None
    print(f'RLViser: stage={args.stage}, {args.source} actor={ck.resolve()}',flush=True)
    try:
        renderer=RLViserRenderer(tick_rate=15*args.speed)
        for ep in range(args.episodes):
            match=MechanicsMatch(teacher,engine,args.stage,seed=args.seed+ep,
                    orange=bool(ep%2),max_steps=args.episode_decisions,opponent=args.opponent)
            for _ in range(args.episode_decisions):
                t0=time.perf_counter()
                renderer.render(match.state,{})
                ours,theirs=match.observe()
                aid,_,_=select_action(actor,ours,'cpu',sample=False)
                tid=int(teacher.logits([(theirs[1],theirs[2],theirs[3])])[0].argmax()) if args.opponent=='nexto' else 0
                _,done,success=match.step(aid,tid)
                elapsed=time.perf_counter()-t0
                if elapsed < 1/(15*args.speed):
                    time.sleep(1/(15*args.speed)-elapsed)
                if done: break
            print(f'EP {ep+1}: success={match.tracker.success}, '
                  f'decisions={match.tracker.t}, touches={match.tracker.touch_events}',flush=True)
    finally:
        if renderer is not None: renderer.close()
        engine.close()

if __name__=='__main__':main()
