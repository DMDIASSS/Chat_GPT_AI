"""Collect offline 1v1 RocketSim matches controlled by Nexto, not humans.

Unlike replay-state labeling, Nexto's *own* controls determine subsequent
states, so the dataset does not suffer from expert/off-policy state mismatch.

NOTE: Nexto's RLBot *scripted kickoff* is not included; this runs its learned
TorchScript policy from kickoff or preset scenarios only.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
from nexto_teacher import NextoTeacher, nexto_actions, action_mapping, compress_teacher_probs

ROOT=Path(__file__).resolve().parent


def run(args):
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.action_parsers import LookupTableAction
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator, KickoffMutator
    from chatgpt_ai.env import make_obs

    table=np.asarray(LookupTableAction.make_lookup_table())
    mapping,errors=action_mapping(table)
    if int(np.count_nonzero(errors<1e-6))<60:
        raise ValueError('Nexto/RLGym discrete controls differ substantially; investigate before collecting')
    teacher=NextoTeacher(device=args.teacher_device)
    teacher_controls=nexto_actions()
    mutator=FixedTeamSizeMutator(blue_size=1,orange_size=1)
    scenario_mutator=KickoffMutator()
    if args.scenarios == 'grounded':
        from chatgpt_ai.curriculum import ChatGPTCurriculum
        scenario_mutator=ChatGPTCurriculum('grounded')
    engine=RocketSimEngine(rlbot_delay=False)
    out=args.output
    out.mkdir(parents=True,exist_ok=True)
    prior_files=list(out.glob('nexto_rollout_*.npz'))
    next_shard=max([int(p.stem.rsplit('_',1)[-1]) for p in prior_files if p.stem.rsplit('_',1)[-1].isdigit()]+[-1])+1
    rows,soft_targets,groups=[],[],[]
    total=0; episode=0; decision=0
    previous={}; builder=None; state=None
    session_group_base=(next_shard+1)*1_000_000  # Avoid episode IDs colliding across sessions.

    def persist():
        nonlocal total,next_shard
        if not rows:
            return
        name=out / f'nexto_rollout_{next_shard:05}.npz'
        X=np.stack(rows).astype(np.float32)
        probs=np.stack(soft_targets).astype(np.float16)
        ids=np.asarray(groups,dtype=np.int64)
        if not np.isfinite(X).all() or not np.isfinite(probs).all() or not np.allclose(probs.astype(np.float32).sum(1),1,atol=2e-3):
            raise RuntimeError('Nonfinite or unnormalized rollout dataset')
        np.savez_compressed(name,obs=X,teacher_probs=probs,
            actions=probs.argmax(1).astype(np.int64),replay_ids=ids)
        total+=len(rows)
        print(f'Saved {len(rows):,} teacher decisions -> {name.name} (total {total:,})',flush=True)
        next_shard+=1
        rows.clear();soft_targets.clear();groups.clear()

    def reset():
        nonlocal episode,decision,previous,builder,state
        episode+=1
        decision=0
        previous={}
        base=engine.create_base_state()
        mutator.apply(base,{})
        scenario_mutator.apply(base,{})
        state=engine.set_state(base,{})
        builder=make_obs()
        builder.reset(list(state.cars),state,{})

    try:
        reset()
        for step in range(args.max_decisions):
            if decision>=args.episode_decisions or getattr(state,'goal_scored',False):
                reset()
            if len(state.cars)!=2:
                raise ValueError('Expected exactly two cars')
            agents=list(state.cars)
            view=teacher.observe(state,previous)
            # Teacher policy acts on both car states in the same batch.
            logits=teacher.logits([(q,kv,m) for _,q,kv,m in view])
            probs=compress_teacher_probs(logits,mapping,len(table),args.temperature)
            student=builder.build_obs(agents,state,{})
            engine_actions={}
            for i,(agent,_,_,_) in enumerate(view):
                control=teacher_controls[int(logits[i].argmax())]
                # Optional tiny stochastic fraction to create diverse states.
                if args.random_action_rate>0 and np.random.random()<args.random_action_rate:
                    control=teacher_controls[np.random.randint(len(teacher_controls))]
                prev_action=np.asarray(control,dtype=np.float32)
                previous[agent]=prev_action
                ob=np.asarray(student[agent],dtype=np.float32).reshape(-1)
                if ob.shape!=(92,) or not np.isfinite(ob).all():
                    raise ValueError('Student observation invalid')
                rows.append(ob)
                soft_targets.append(probs[i])
                # Prefix with a per-shard unique episode ID; prevents validation overlap.
                groups.append(session_group_base+episode)
                engine_actions[agent]=np.tile(prev_action,(8,1))
            state=engine.step(engine_actions,{})
            decision+=1
            if len(rows)>=args.save_every:
                persist()
            if (step+1)%1000==0:
                print(f'RocketSim Nexto decisions: {step+1:,}/{args.max_decisions:,}',flush=True)
    finally:
        persist()
        engine.close()
    print(f'Completed teacher rollouts. New samples: {total:,}. Run DISTILL_NEXTO_ROLLOUTS.bat next.')


def main():
    p=argparse.ArgumentParser(description='Generate live Nexto-teacher 1v1 RocketSim experience')
    p.add_argument('--max-decisions',type=int,default=5000,
                   help='Number of simulated decision ticks (two car samples each)')
    p.add_argument('--episode-decisions',type=int,default=450)
    p.add_argument('--save-every',type=int,default=5000,help='Rows per saved shard')
    p.add_argument('--scenarios',choices=['kickoff','grounded'],default='grounded')
    p.add_argument('--teacher-device',choices=['cpu','cuda:0'],default='cpu')
    p.add_argument('--temperature',type=float,default=1.)
    p.add_argument('--random-action-rate',type=float,default=0.)
    p.add_argument('--output',type=Path,default=ROOT/'data/datasets/nexto_rollouts')
    a=p.parse_args()
    if a.max_decisions<1 or a.episode_decisions<1 or a.save_every<1 or a.temperature<=0:
        p.error('step counts and temperature must be positive')
    if not 0<=a.random_action_rate<=1:
        p.error('random-action-rate must be in [0,1]')
    run(a)

if __name__=='__main__':
    main()
