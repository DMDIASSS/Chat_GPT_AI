"""Isolated greedy/sampled routing experiment; deployment stays greedy."""
from __future__ import annotations
import copy
import json
import time
import zipfile
import numpy as np
import torch
from filelock import FileLock,Timeout
from .core import atomic_json
from .triad_selector import Runner,selector_meta,teacher_pool
from .selector_diagnostics import OPPONENTS,FixedExpert,probabilities,protected_hashes
from .chronos_league import play_match,match_summary
from .chronos_guard import paired_statistics,EvaluationStopped
from .research import run_path,provenance,stamp,LIMITS
from .training import load_config

SEED=451000001


class SampledRunner(Runner):
    """Sample only at free choices, with an RNG independent of simulator/Torch."""
    def begin_match(self,seed,side):
        # Called once per timed match. Runner.bind resets context after each goal,
        # but must not rewind this stream when that happens.
        self.rng=np.random.default_rng(np.random.SeedSequence([seed,side,20261106]))
        self.free_counts=np.zeros(self.gate.n,dtype=np.int64)

    def world_controls(self,obs):
        gate=self.gate;context=gate.context
        if context.remaining:
            choice=context.last
        else:
            if not hasattr(self,'rng'):raise RuntimeError('begin_match must precede sampled routing')
            x=torch.from_numpy(context.observation(obs[:225]))[None,:]
            with torch.inference_mode():p=probabilities(gate.network(x)[0].numpy(),gate.n)
            gate.last_free_choice_probabilities=dict(zip(gate.names,map(float,p)))
            choice=int(self.rng.choice(gate.n,p=p));self.free_counts[choice]+=1
        context.advance(choice);self.counts[choice]+=1
        env=self.env
        return self.teacher.proposals(env.arena.state,env.previous,obs[:225],env.mirror)[choice]


def benchmark(cfg,policies,pairs,seconds,stop_path,seed_start=SEED):
    rows={name:[] for name in policies};total=len(policies)*len(OPPONENTS)*pairs*2;done=0
    print(f'ROUTING_MATCHES: {total} games, {seconds:g}s simulated/game. No training. Ctrl+C cancels.',flush=True)
    for op_index,opponent in enumerate(OPPONENTS):
        for pair in range(pairs):
            seed=seed_start+op_index*100000+pair
            for side in (0,1):
                initial=None
                for name,policy in policies.items():
                    prefix=f'ROUTING GAME {done+1}/{total} {name} vs {opponent} side={side} seed={seed}'
                    print(prefix+' START',flush=True)
                    begin=getattr(policy,'begin_match',None)
                    if begin is not None:begin(seed,side)
                    counts=getattr(policy,'counts',None);before=counts.copy() if counts is not None else None
                    def progress(event):
                        print(prefix+f' RUNNING {event["simulated_seconds"]:.1f}/{event["seconds"]:.1f}s score={event["goals_for"]}:{event["goals_against"]}',flush=True)
                    row=play_match(copy.deepcopy(cfg),policy,opponent,side,seed,seconds,stop_path,progress=progress)
                    if initial is None:initial=row['initial_observation_sha256']
                    if initial!=row['initial_observation_sha256']:raise RuntimeError('Different routing starts for the same hitbox/seed/color')
                    if before is not None:
                        row['expert_decisions']=dict(zip(policy.gate.names,map(int,policy.counts-before)))
                    if begin is not None:row['free_choices']=dict(zip(policy.gate.names,map(int,policy.free_counts)))
                    rows[name].append(row);done+=1
                    print(prefix+f' DONE score={row["goals_for"]}:{row["goals_against"]}',flush=True)
    return rows


def evaluate(run_name='selector04',pairs=1,seconds=30,seed_start=SEED):
    if not isinstance(pairs,int) or not 1<=pairs<=8 or not np.isfinite(seconds) or not 8/120<=seconds<=120:
        raise ValueError('Routing evaluation requires 1..8 pairs and 0.067..120 seconds per game')
    if not isinstance(seed_start,int) or not 0<=seed_start<=2**31-1000000:raise ValueError('Invalid routing seed start')
    print('ROUTING_EVALUATION_START: pause selector training first; loading models with one Torch thread.',flush=True)
    torch.set_num_threads(1);run=run_path(run_name)
    if not (run/'config.json').is_file():raise FileNotFoundError('No saved selector run to evaluate')
    try:
        with FileLock(str(run/'train.lock'),timeout=0):
            before=protected_hashes(run);started=time.monotonic()
            try:
                cfg=load_config(run/'config.json');body=cfg['env'].get('learner_hitbox','breakout')
                latest=selector_meta(run/'latest.pt');initial=selector_meta(run/'initial.pt')
                if latest['contract']!=initial['contract']:raise ValueError('Initial/latest selector contracts differ')
                greedy=Runner(run/'latest.pt',body)
                policies=dict(latest_greedy=greedy,latest_sampled=SampledRunner(run/'latest.pt',body),
                    initial_sampled=SampledRunner(run/'initial.pt',body))
                teacher=teacher_pool(greedy.gate.fusion_path)
                policies['fixed_chronos']=FixedExpert(teacher,'chronos')
                if 'fusion' in greedy.gate.names:policies['fixed_fusion']=FixedExpert(teacher,'fusion')
                stop=run/'ROUTING_STOP';stop.unlink(missing_ok=True)
                rows=benchmark(cfg,policies,pairs,seconds,stop,seed_start)
                summaries={name:dict(match_summary(r),by_opponent={op:match_summary([x for x in r if x['opponent']==op]) for op in OPPONENTS}) for name,r in rows.items()}
                report=dict(kind='selector_routing_v1',candidate_sha256=latest['sha256'],candidate_timesteps=latest['timesteps'],
                    initial_sha256=initial['sha256'],body=body,experts=list(greedy.gate.names),pairs=pairs,seconds=seconds,
                    seed_start=seed_start,opponents=list(OPPONENTS),summaries=summaries,trials=rows,
                    paired_vs_fixed_chronos={name:paired_statistics(r,rows['fixed_chronos']) for name,r in rows.items() if name!='fixed_chronos'},
                    paired_latest_sampled_vs_initial_sampled=paired_statistics(rows['latest_sampled'],rows['initial_sampled']),
                    paired_latest_sampled_vs_latest_greedy=paired_statistics(rows['latest_sampled'],rows['latest_greedy']),
                    provenance=provenance(cfg),wall_seconds=time.monotonic()-started,
                    sampling=dict(method='categorical softmax on free choices only',commitment_decisions=8,
                        rng='NumPy Generator seeded by SeedSequence([match_seed, side, 20261106]); shared seed for latest/initial, retained across goals',
                        note='Same policy distribution as PPO, not a replay of its Torch random draws. No age/repetition weights or temperature changes.'),
                    limitations=LIMITS+' Exploratory routing comparison, not a promotion test. Fresh relative to diagnostic/guard seed banks, not a permanent held-out test once inspected. One sampling stream per seed/color; repeat with fresh seed starts before drawing a strength conclusion. Matching starts do not guarantee identical native respawns. Common expert adapters retain the Ripple held-queue approximation. Deployment, training settings and champion remain unchanged.')
            except (EvaluationStopped,KeyboardInterrupt):
                print('ROUTING_CANCELLED: previous complete reports and weights retained.',flush=True);return
            finally:
                if protected_hashes(run)!=before:raise RuntimeError('Protected run files changed while evaluating routing')
            report['protected_run_files_unchanged']=True
            destination=run/'routing'/stamp();destination.mkdir(parents=True)
            atomic_json(destination/'routing.json',report)
            path=run.parent.parent/'reports'/f'{run.name}_routing_{destination.name}.zip';path.parent.mkdir(parents=True,exist_ok=True)
            with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
                z.write(destination/'routing.json','routing.json')
                z.writestr('README.txt','Isolated greedy versus sampled routing pilot. No training or promotion. See routing.json for seeds, frozen checkpoint identities, free-choice counts, complete trials and limitations.\n')
            atomic_json(run/'routing/latest.json',dict(path=str(destination.relative_to(run)),report_zip=str(path)))
            for name,data in summaries.items():print('ROUTING_RESULT',name,json.dumps({k:v for k,v in data.items() if k!='by_opponent'}),flush=True)
            print('ROUTING_REPORT_READY:',path,flush=True)
            return path
    except Timeout as error:
        raise RuntimeError('Selector training is active. Use 19 for selector04 or 8 for selector01, then wait for saving.') from error
