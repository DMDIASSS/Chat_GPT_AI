"""Real RocketSim & control validation; no model changes."""
import argparse, json
import numpy as np
from skillforge_core import Simulator, rollout, WavedashDetector, macro_control, ZERO


def parse():
    p=argparse.ArgumentParser()
    p.add_argument('--seeds',type=int,default=6)
    return p


def preflight(n):
    if n<1: raise ValueError('seeds must be positive')
    sim=Simulator()
    try:
        for i in range(n):
            seed=700+i
            state=sim.reset(seed,'near')
            c=state.cars[sim.ours]
            checks={
                'jumped':bool(c.has_jumped),
                'flip_available':bool(c.has_flip),
                'not_flipped':not bool(c.has_flipped),
                'not_grounded':not bool(c.on_ground),
                'no_boost':float(c.boost_amount)<=0.15,
                'descending':float(c.physics.linear_velocity[2])<0,
                'orientation_valid':np.linalg.det(np.asarray(c.physics.rotation_mtx))>0.98,
            }
            print(f'Spawn {i+1}/{n} seed={seed}: {checks}',flush=True)
            if not all(checks.values()):
                raise RuntimeError('RocketSim spawn violates required flip-state semantics: '+str(checks))
            # Null action must not count as an executed wavedash.
            m,_=rollout(sim,seed,{'delay':8,'hold':1,'cancel_delay':1,'cancel_ticks':10,
                        'pre':0.,'post':0.,'direction':-1.},
                        policy=lambda obs:ZERO.copy(),max_ticks=70)
            if m.success or m.dodge_detected:
                raise RuntimeError('Invalid detector: idle counted as dodge')
            print(f'   IDLE: success={m.success} reason={m.reason}',flush=True)
        # Force at least one real dodge to verify the flip activation is detectable;
        # this can be false if spawn too close to ground, so audit it separately.
        count=0
        for i in range(n):
            m,_=rollout(sim,700+i,{'delay':0,'hold':1,'cancel_delay':0,'cancel_ticks':12,
                'pre':0.,'post':0.,'direction':-1.},max_ticks=70)
            count+=int(m.dodge_detected)
            print(f'   DODGE-TEST seed={700+i}: detected={m.dodge_detected} '
                  f'landed_during_flip={m.landed_during_dodge} '
                  f'gain={m.speed_gain:.1f} verified={m.success}',flush=True)
        if not count:
            raise RuntimeError('No airborne dodge detected in real physics; fix spawn before search!')
        print('REAL PHYSICS PREFLIGHT PASSED. Idle rejected; flip-state events observed.')
        print('This does NOT mean any successful wavedash has been found.')
    finally:
        sim.close()


if __name__=='__main__': preflight(parse().parse_args().seeds)
