"""Read-only selector measurements and matched fixed-expert adapter benchmarks."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import time
import zipfile
import numpy as np
import torch
from filelock import FileLock,Timeout
from .core import atomic_json,check_model,sha256
from .triad_selector import Runner,Gate,NAMES,selector_meta,teacher_pool
from .chronos_league import play_match,match_summary
from .chronos_guard import paired_statistics,EvaluationStopped
from .research import run_path,provenance,stamp,LIMITS
from .training import load_config

OPPONENTS=('chronos','galactus','nexto','ripple')
REFERENCE_BODIES=dict(chronos='breakout',galactus='octane',ripple='octane')
SEED=331000001


def probabilities(logits,n=3):
    x=np.asarray(logits,dtype=np.float64)
    if x.shape!=(n,) or not np.isfinite(x).all():raise ValueError('Invalid diagnostic selector logits')
    p=np.exp(x-x.max());return p/p.sum()


class ChoiceStats:
    def __init__(self,names=NAMES):
        self.names=tuple(names);n=len(names)
        self.count=0;self.total=np.zeros(n);self.square=np.zeros(n)
        self.low=np.ones(n);self.high=np.zeros(n);self.greedy=np.zeros(n,dtype=int)
        self.entropy=0.;self.margins=[];self.margin_total=0.;self.kl=0.
    def add(self,p,reference):
        self.count+=1;self.total+=p;self.square+=p*p;self.low=np.minimum(self.low,p);self.high=np.maximum(self.high,p)
        self.greedy[int(p.argmax())]+=1
        self.entropy-=float((p*np.log(np.maximum(p,1e-300))).sum())
        margin=float(np.sort(p)[-1]-np.sort(p)[-2]);self.margin_total+=margin
        if len(self.margins)<4096:self.margins.append(margin)
        self.kl+=float((p*(np.log(np.maximum(p,1e-300))-np.log(np.maximum(reference,1e-300)))).sum())
    def summary(self):
        if not self.count:return dict(free_choices=0)
        mean=self.total/self.count;std=np.sqrt(np.maximum(self.square/self.count-mean*mean,0))
        return dict(free_choices=self.count,probability_mean=dict(zip(self.names,map(float,mean))),
            probability_std=dict(zip(self.names,map(float,std))),probability_min=dict(zip(self.names,map(float,self.low))),
            probability_max=dict(zip(self.names,map(float,self.high))),greedy_choices=dict(zip(self.names,map(int,self.greedy))),
            mean_entropy_nats=self.entropy/self.count,mean_top_two_margin=self.margin_total/self.count,
            top_two_margin_percentiles_first_4096=dict(zip(('p10','p50','p90'),map(float,np.percentile(self.margins,[10,50,90])))),
            mean_kl_to_initial=self.kl/self.count)


class Audit:
    def __init__(self,reference,names=NAMES):
        self.names=tuple(names);self.n=len(names)
        self.reference=reference;self.latest=ChoiceStats(names);self.initial=ChoiceStats(names);self.by_opponent={}
        self.forced_decisions=0
    def observe(self,gate,features,opponent):
        if gate.context.remaining:
            self.forced_decisions+=1;return
        obs=gate.context.observation(features)
        if not np.all(obs[-self.n:]==1):raise ValueError('A free choice must allow every expert')
        x=torch.from_numpy(obs)[None,:]
        with torch.inference_mode():
            p=probabilities(gate.network(x)[0].numpy(),self.n);q=probabilities(self.reference(x)[0].numpy(),self.n)
        self.latest.add(p,q);self.initial.add(q,q)
        if opponent not in self.by_opponent:self.by_opponent[opponent]=ChoiceStats(self.names)
        self.by_opponent[opponent].add(p,q)
    def summary(self):
        return dict(latest=self.latest.summary(),initial_on_same_latest_visited_contexts=self.initial.summary(),
            by_opponent={k:v.summary() for k,v in self.by_opponent.items()},forced_decisions_excluded=self.forced_decisions,
            note='Probabilities are measured only when the commitment expires. Initial weights are queried on the same latest-policy observations/context, not separate initial-policy trajectories.')


class DiagnosticRunner(Runner):
    def __init__(self,path,body,initial):
        super().__init__(path,body);self.audit=Audit(Gate(initial,body).network,self.gate.names)
    def world_controls(self,obs):
        self.audit.observe(self.gate,obs[:225],self.env.arena.opponent_label)
        return super().world_controls(obs)


class FixedExpert:
    def __init__(self,teacher,name):self.teacher=teacher;self.index=tuple(getattr(teacher,'names',NAMES)).index(name)
    def bind(self,env):
        self.env=env;self.teacher.reset(env.arena.state,env.arena.agent,np.random.default_rng(271))
    def world_controls(self,obs):
        env=self.env
        return self.teacher.proposals(env.arena.state,env.previous,obs[:225],env.mirror)[self.index]


def conditions(body,body_check=True,names=NAMES):
    cells=[dict(label='selector_latest',body=body,expert=None)]
    cells += [dict(label='fixed_'+n,body=body,expert=n) for n in names]
    if body_check:
        cells += [dict(label=n+'_reference_body',body=REFERENCE_BODIES[n],expert=n)
                  for n in NAMES if body!=REFERENCE_BODIES[n]]
    return cells


def benchmark(cfg,cells,policies,pairs,seconds,stop_path):
    rows={cell['label']:[] for cell in cells};total=len(cells)*len(OPPONENTS)*pairs*2;done=0
    started=time.monotonic()
    print(f'DIAGNOSTIC_MATCHES: {total} games, {seconds:g}s simulated/game. No training. Ctrl+C cancels.',flush=True)
    for op_index,opponent in enumerate(OPPONENTS):
        for pair in range(pairs):
            seed=SEED+op_index*100000+pair
            for side in (0,1):
                hashes={}
                for cell in cells:
                    label=cell['label'];body=cell['body'];config=copy.deepcopy(cfg);config['env']['learner_hitbox']=body
                    prefix=f'DIAG GAME {done+1}/{total} {label}/{body} vs {opponent} side={side} seed={seed}'
                    print(prefix+' START',flush=True)
                    def progress(event):
                        print(prefix+f' RUNNING {event["simulated_seconds"]:.1f}/{event["seconds"]:.1f}s score={event["goals_for"]}:{event["goals_against"]}',flush=True)
                    row=play_match(config,policies[label],opponent,side,seed,seconds,stop_path,progress=progress)
                    old=hashes.setdefault(body,row['initial_observation_sha256'])
                    if old!=row['initial_observation_sha256']:raise RuntimeError('Different diagnostic starts for the same hitbox/seed/color')
                    rows[label].append(dict(row,learner_hitbox=body));done+=1
                    print(prefix+f' DONE score={row["goals_for"]}:{row["goals_against"]} elapsed={time.monotonic()-started:.0f}s',flush=True)
    return rows


def protected_hashes(run):
    names=['config.json','experiment.json','guard.json','status.json','STOP','six_origin.json','fusion_selection.json','fusion_refinement.json']
    names += [n+s for n in ('full.zip','latest.pt','initial.pt','champion.pt','frozen_fusion.pt') for s in ('','.json')]
    return {n:sha256(run/n) if (run/n).is_file() else None for n in names}


def diagnose(run_name='selector01',pairs=1,seconds=30,body_check=True):
    if not isinstance(pairs,int) or not 1<=pairs<=8 or not np.isfinite(seconds) or not 8/120<=seconds<=120:
        raise ValueError('Diagnostics require 1..8 pairs and 0.067..120 seconds per game')
    print('SELECTOR_DIAGNOSTIC_START: loading Python/models, one Torch thread; pause training with 8 first.',flush=True)
    torch.set_num_threads(1);run=run_path(run_name)
    if not (run/'config.json').exists():raise FileNotFoundError('No saved selector run to diagnose')
    try:
        with FileLock(str(run/'train.lock'),timeout=0):
            before=protected_hashes(run);started=time.monotonic()
            try:
                cfg=load_config(run/'config.json');body=cfg['env'].get('learner_hitbox','breakout')
                latest=selector_meta(run/'latest.pt');initial=selector_meta(run/'initial.pt')
                if len(latest['contract']['actions'])==6:raise ValueError('Use launcher 30 for six-expert native-timing diagnostics')
                print(f'Checkpoint: {latest["timesteps"]} decisions; {latest["sha256"]}',flush=True)
                print('LOADING 1/2: latest selector, initial probability reference and three experts',flush=True)
                candidate=DiagnosticRunner(run/'latest.pt',body,run/'initial.pt')
                print('LOADING 2/2: shared fixed-expert benchmark controllers',flush=True)
                gate=getattr(candidate,'gate',None);names=getattr(gate,'names',NAMES)
                teacher=teacher_pool(getattr(gate,'fusion_path',None));cells=conditions(body,body_check,names);policies={'selector_latest':candidate}
                policies.update({c['label']:FixedExpert(teacher,c['expert']) for c in cells if c['expert'] is not None})
                stop=run/'DIAGNOSTIC_STOP';stop.unlink(missing_ok=True)
                rows=benchmark(cfg,cells,policies,pairs,seconds,stop)
                summaries={name:dict(match_summary(r),by_opponent={op:match_summary([x for x in r if x['opponent']==op]) for op in OPPONENTS}) for name,r in rows.items()}
                same_body={name:paired_statistics(r,rows['fixed_chronos']) for name,r in rows.items()
                           if name!='fixed_chronos' and next(c['body'] for c in cells if c['label']==name)==body}
                body_effects={c['label']:dict(reference_body=c['body'],training_body=body,
                    statistics=paired_statistics(rows[c['label']],rows['fixed_'+c['expert']]))
                    for c in cells if c['body']!=body}
                report=dict(kind='selector_diagnostics_v1',candidate_sha256=latest['sha256'],candidate_timesteps=latest['timesteps'],
                    initial_sha256=initial['sha256'],conditions=cells,opponents=list(OPPONENTS),pairs=pairs,seconds=seconds,seed_start=SEED,
                    free_choice_probabilities=candidate.audit.summary(),latest_expert_decisions=dict(zip(names,map(int,candidate.counts))),
                    summaries=summaries,paired_vs_fixed_chronos_same_body=same_body,reference_body_effects=body_effects,
                    trials=rows,provenance=provenance(cfg),wall_seconds=time.monotonic()-started,
                    limitations=LIMITS+' Exploratory short matches from kickoffs; not a promotion test. All expert conditions use the common 8-tick/7+1-delay adapter and Ripple held-queue approximation. Body comparisons intentionally change physics and do not validate native timing or full transfer fidelity.')
            except (EvaluationStopped,KeyboardInterrupt):
                print('DIAGNOSTIC_CANCELLED: no new complete report; existing reports and weights retained.',flush=True);return
            finally:
                if protected_hashes(run)!=before:raise RuntimeError('Protected run files changed while diagnosing; stop and investigate')
            report['protected_run_files_unchanged']=True
            destination=run/'diagnostics'/stamp();destination.mkdir(parents=True)
            atomic_json(destination/'diagnostic.json',report)
            zip_path=run.parent.parent/'reports'/f'{run.name}_diagnostics_{destination.name}.zip';zip_path.parent.mkdir(parents=True,exist_ok=True)
            with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
                z.write(destination/'diagnostic.json','diagnostic.json')
                z.writestr('README.txt','Exploratory diagnostics only. Free-choice probabilities exclude forced commitment steps. Same-body fixed experts use the exact common selector adapter. Reference-body comparisons change only the learner body. No training, checkpoint edits, or champion promotion. See diagnostic.json limitations.\n')
            atomic_json(run/'diagnostics/latest.json',dict(path=str(destination.relative_to(run)),report_zip=str(zip_path)))
            print('FREE_CHOICE_PROBABILITIES:',json.dumps(report['free_choice_probabilities']['latest'],indent=2),flush=True)
            for name,data in summaries.items():print('EXPERT_RESULT',name,json.dumps({k:v for k,v in data.items() if k!='by_opponent'}),flush=True)
            print('DIAGNOSTIC_REPORT_READY:',zip_path,flush=True)
            return zip_path
    except Timeout as error:
        raise RuntimeError('Selector training is active. Pause with launcher 8 and wait for saving to finish before diagnostics.') from error
