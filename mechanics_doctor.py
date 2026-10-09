"""Windows-only real RocketSim compatibility preflight; no checkpoint writes."""
from pathlib import Path
import sys
import numpy as np
from mechanics_scenarios import STAGES
from mechanics_tasks import MechanicsMatch


def main():
    import torch
    from rlgym.rocket_league.sim import RocketSimEngine
    from mechanics_train import ROOT, DEFAULT_SOURCE, load_actor
    from nexto_teacher import NextoTeacher
    if not DEFAULT_SOURCE.exists():
        raise FileNotFoundError(f'Needs verified baseline: {DEFAULT_SOURCE}')
    actor=load_actor(DEFAULT_SOURCE,'cpu')
    teacher=NextoTeacher('cpu')
    engine=RocketSimEngine(rlbot_delay=False)
    try:
        for index,stage in enumerate(STAGES):
            match=MechanicsMatch(teacher,engine,stage,seed=100+index,
                                  orange=bool(index%2), max_steps=50)
            ours, opp=match.observe()
            for view in (ours,opp):
                _,q,kv,mask=view
                assert np.isfinite(q).all() and np.isfinite(kv).all() and np.isfinite(mask).all(), stage
            with torch.no_grad():
                action = teacher.logits([(ours[1],ours[2],ours[3])])[0].argmax()
                # forward of candidate must use native Nexto observation format
                x=actor((torch.from_numpy(ours[1][None]),
                         torch.from_numpy(ours[2][None]),
                         torch.from_numpy(ours[3][None])))
                assert x[0].shape == (1,90), (stage,x[0].shape)
            reward,finished,success=match.step(int(action),0)
            assert np.isfinite(reward)
            assert np.isfinite(match.state.ball.position).all()
            print(f'{stage:16s} | real physics step OK | reward {reward:+.4f} | success={success}',flush=True)
    finally:
        engine.close()
    print('PRE-FLIGHT PASSED. Use MECH_1_RECOVERY_SMOKE.bat.')

if __name__=='__main__':
    main()
