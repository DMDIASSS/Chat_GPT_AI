"""Check compatibility before hours of Nexto distillation or PPO training.

By default never steps RocketSim. --engine-smoke runs a single 8-tick sim step
and validates both teacher and student observation schemas.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import numpy as np
from nexto_teacher import NextoTeacher, nexto_actions, action_mapping

ROOT=Path(__file__).resolve().parent


def inspect(engine_smoke: bool):
    import torch
    from rlgym.rocket_league.action_parsers import LookupTableAction
    from chatgpt_ai.config import PRESETS, POLICY_LAYERS

    table=np.asarray(LookupTableAction.make_lookup_table(),dtype=np.float32)
    mapping,errors=action_mapping(table)
    if table.shape!=(90,8) or not np.array_equal(nexto_actions(),table):
        raise RuntimeError('Nexto and RLGym LookupTableAction must match EXACTLY. Refusing to train.')
    if 'grounded' not in PRESETS:
        raise RuntimeError('Grounded preset missing; run INSTALL_FAST_TRACK.bat to install the compatible patch')
    if tuple(POLICY_LAYERS)!=(512,512):
        raise RuntimeError('Unexpected policy layers: we expect the existing 512x512 PPO model')
    teacher=NextoTeacher('cpu')
    print('Nexto TorchScript model: LOADED')
    print(f'Nexto model size: {(ROOT/"vendor/nexto/nexto-model.pt").stat().st_size/1024/1024:.2f} MB')
    print(f'Nexto/student action mapping: {int((errors==0).sum())}/90 EXACT')
    print(f'CUDA available for student PPO: {torch.cuda.is_available()}')
    if torch.cuda.is_available():
        print(f'CUDA GPU: {torch.cuda.get_device_name(0)}')
    else:
        print('Student distillation can also run on CPU.')

    saved=ROOT/'data/checkpoints/chat_gpt_ai'
    replays=ROOT/'data/replays/ranked-duels'
    print(f'Existing checkpoint files: {len(list(saved.rglob("PPO_POLICY.pt"))) if saved.exists() else 0}')
    print(f'Existing human replay files: {len(list(replays.rglob("*.replay"))) if replays.exists() else 0}')
    print(f'Human imitation weights: {(ROOT/"data/bc_policy.pt").exists()}')

    if engine_smoke:
        from rlgym.rocket_league.sim import RocketSimEngine
        from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
        from chatgpt_ai.env import make_obs
        engine=RocketSimEngine(rlbot_delay=False)
        try:
            state=engine.create_base_state()
            FixedTeamSizeMutator(blue_size=1,orange_size=1).apply(state,{})
            KickoffMutator().apply(state,{})
            state=engine.set_state(state,{})
            agents=list(state.cars)
            obs=make_obs()
            obs.reset(agents,state,{})
            views=obs.build_obs(agents,state,{})
            assert len(views)==2
            assert all(np.asarray(v).reshape(-1).shape==(92,) for v in views.values())
            teach_views=teacher.observe(state,{})
            logits=teacher.logits([(q,k,m) for _,q,k,m in teach_views])
            assert logits.shape==(2,90) and np.isfinite(logits).all()
            actions={k:np.tile(nexto_actions()[int(logits[i].argmax())],(8,1)) for i,k in enumerate([v[0] for v in teach_views])}
            after=engine.step(actions,{})
            assert after.tick_count > state.tick_count
            print('RocketSim one-step teacher rollout: PASS')
        finally:
            engine.close()
    print('Doctor PASSED. Start COLLECT_NEXTO_ROLLOUTS.bat')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--engine-smoke',action='store_true')
    a=parser.parse_args()
    inspect(a.engine_smoke)
