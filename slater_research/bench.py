"""Microbenchmark pure RocketSim RLGym transition throughput, no neural inference.

Prints PHYSICS TICKS/s, not 8-tick learner decisions/s. If slow, profile first.
"""
import argparse
import time
import numpy as np
from rlgym.rocket_league.sim import RocketSimEngine
from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator


def bench(n_arena=1,seconds=6.0,n_players=2,ticks=8):
    arenas=[]
    for _ in range(n_arena):
        e=RocketSimEngine(rlbot_delay=False)
        s=e.create_base_state()
        FixedTeamSizeMutator(blue_size=n_players//2,orange_size=n_players//2).apply(s,{})
        KickoffMutator().apply(s,{})
        s=e.set_state(s,{})
        arenas.append((e,list(s.cars)))
    actions=[{aid:np.tile(np.array([1,0,0,0,0,0,1,0],np.float32),(ticks,1))
              for aid in ids} for e,ids in arenas]
    count=0; start=time.perf_counter()
    try:
        while time.perf_counter()-start<seconds:
            for (engine,_),a in zip(arenas,actions):
                engine.step(a,{})
                count+=ticks
    finally:
        for e,_ in arenas:e.close()
    duration=time.perf_counter()-start
    print(f'Physics ticks/s={count/duration:,.0f}; decisions/s={count/ticks/duration:,.0f} '
          f'arenas={n_arena} car_count={n_players} action_repeat={ticks}')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--arenas',type=int,default=1)
    p.add_argument('--seconds',type=float,default=6)
    p.add_argument('--players',type=int,choices=(2,4,6),default=2)
    p.add_argument('--ticks',type=int,choices=(1,2,4,8),default=8)
    a=p.parse_args();bench(a.arenas,a.seconds,a.players,a.ticks)
