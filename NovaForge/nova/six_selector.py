"""Separate six-expert Octane experiment; preserves the existing four-way run."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import time
import zipfile
import numpy as np
import torch
from filelock import FileLock,Timeout
from .core import ROOT,atomic_json,sha256
from .triad_selector import SIX_NAMES,Runner,Gate,selector_meta,fusion_asset
from .six_experts import Clock
from .selector_diagnostics import protected_hashes,Audit
from .chronos_league import play_match,match_summary
from .chronos_guard import paired_statistics,EvaluationStopped
from .research import run_path,stamp,provenance,LIMITS
from .training import load_config

OPPONENTS=('chronos','galactus','nexto','ducky','rain','megabyte','fusion')
SEED=491000001


def create(name='selector06',source='selector04'):
    from .teachers import fetch_teachers
    dst=run_path(name);src=run_path(source)
    if dst==src or dst.exists():raise ValueError('Six-expert destination must be new; do not reuse selector04')
    if not (src/'config.json').exists():raise FileNotFoundError('Saved selector04 is needed to preserve its exact frozen Fusion')
    fetch_teachers(['chronos','galactus','nexto','ducky','rain','megabyte'])
    with FileLock(str(src/'train.lock'),timeout=0):
        before=protected_hashes(src);meta=selector_meta(src/'latest.pt')
        if 'fusion_teacher' not in meta:raise ValueError('Source does not contain a frozen Fusion expert')
        frozen=fusion_asset(src,meta['fusion_teacher']);cfg=load_config(src/'config.json')
        cfg['selector_experts']=list(SIX_NAMES);cfg['selector_initial_expert']='fusion'
        cfg['env']['learner_hitbox']='octane';cfg['chronos']['reward_profile']='potential_goal_v2'
        cfg['selector_opponents']={n:1/len(OPPONENTS) for n in OPPONENTS}
        cfg['selector_evaluation_opponents']=list(OPPONENTS)
        cfg['league']['weights']=dict(cfg['selector_opponents'])
        cfg['fusion_teacher']=dict(path='frozen_fusion.pt',sha256=sha256(frozen))
        cfg['env']['fusion_opponent']='frozen_fusion.pt'
        cfg.update(workers=1,threads=1,device='cpu',selector_seed=271)
        stage=dst.parent/('.incomplete_'+stamp());stage.mkdir(parents=True)
        try:
            shutil.copy2(frozen,stage/'frozen_fusion.pt');shutil.copy2(str(frozen)+'.json',stage/'frozen_fusion.pt.json')
            for extra in ('fusion_selection.json','fusion_refinement.json'):
                if (src/extra).exists():shutil.copy2(src/extra,stage/extra)
            atomic_json(stage/'config.json',cfg)
            atomic_json(stage/'six_origin.json',dict(schema='six-expert-octane-v1',source_run=source,
                source_selector_sha256=meta['sha256'],frozen_fusion_sha256=sha256(frozen),
                extra_teacher_lock_sha256=sha256(ROOT/'extra_teachers.lock.json'),
                note='Exact local frozen Fusion retained; new Octane selector gate starts at zero, initially routes greedily to Fusion. Source model strength on Octane is not asserted.'))
            if protected_hashes(src)!=before:raise RuntimeError('Source selector changed during preparation')
            if dst.exists():raise ValueError('Destination appeared during preparation')
            stage.rename(dst)
        finally:
            if stage.exists():shutil.rmtree(stage)
    print('SIX_SELECTOR_READY:',dst,'Octane; frozen Fusion SHA256',cfg['fusion_teacher']['sha256'],flush=True)
    return dst


class Fixed(Runner):
    def __init__(self,path,body,name,pool):
        self.gate=Gate(path,body);self.teacher=pool;self.counts=np.zeros(6,np.int64);self.expert=name
    def bind(self,env):
        self.env=env;self.native_clock=Clock(self.teacher,counts=self.counts)
        self.native_clock.fixed_choice=SIX_NAMES.index(self.expert)
        self.native_clock.reset(env.arena.state,env.arena.agent,np.random.default_rng(271))


def diagnose(name='selector06',pairs=1,seconds=15):
    if not isinstance(pairs,int) or not 1<=pairs<=8 or not np.isfinite(seconds) or not 8/120<=seconds<=120:raise ValueError('Use 1..8 pairs, 0.067..120 seconds')
    torch.set_num_threads(1);run=run_path(name)
    print('SIX_DIAGNOSTIC_START: Octane, native decision periods; loading models. Pause training first.',flush=True)
    try:
        with FileLock(str(run/'train.lock'),timeout=0):
            before=protected_hashes(run);started=time.monotonic()
            try:
                cfg=load_config(run/'config.json');latest=selector_meta(run/'latest.pt');initial=selector_meta(run/'initial.pt')
                if tuple(latest['contract']['actions'])!=SIX_NAMES or cfg['env']['learner_hitbox']!='octane':raise ValueError('Expected the separate six-expert Octane run')
                candidate=Runner(run/'latest.pt','octane');audit=Audit(Gate(run/'initial.pt','octane').network,SIX_NAMES)
                original_bind=candidate.bind
                def bind(env):
                    original_bind(env)
                    candidate.native_clock.observer=lambda features:audit.observe(candidate.gate,features,env.arena.opponent_label)
                candidate.bind=bind
                policies={'selector_latest':candidate}
                policies.update({'fixed_'+n:Fixed(run/'latest.pt','octane',n,candidate.teacher) for n in SIX_NAMES})
                trials={n:[] for n in policies};total=len(policies)*len(OPPONENTS)*pairs*2;done=0;opponent_cache={}
                stop=run/'SIX_DIAGNOSTIC_STOP';stop.unlink(missing_ok=True)
                print(f'SIX_DIAGNOSTIC_MATCHES: {total} games, {seconds:g} simulated seconds/game; Ctrl+C cancels.',flush=True)
                for oi,opponent in enumerate(OPPONENTS):
                    for pair in range(pairs):
                        seed=SEED+oi*100000+pair
                        for side in (0,1):
                            first=None
                            for label,policy in policies.items():
                                prefix=f'SIX GAME {done+1}/{total} {label} vs {opponent} side={side}'
                                print(prefix+' START',flush=True)
                                def progress(e):print(prefix+f' RUNNING {e["simulated_seconds"]:.1f}/{e["seconds"]:.1f}s score={e["goals_for"]}:{e["goals_against"]}',flush=True)
                                row=play_match(cfg,policy,opponent,side,seed,seconds,stop,progress,opponent_cache=opponent_cache)
                                if first is None:first=row['initial_observation_sha256']
                                if first!=row['initial_observation_sha256']:raise RuntimeError('Six-expert match starts differ')
                                trials[label].append(row);done+=1
                                print(prefix+f' DONE score={row["goals_for"]}:{row["goals_against"]}',flush=True)
                summaries={label:dict(match_summary(rows),by_opponent={op:match_summary([r for r in rows if r['opponent']==op]) for op in OPPONENTS}) for label,rows in trials.items()}
                report=dict(kind='six_expert_diagnostics_v1',candidate_sha256=latest['sha256'],candidate_timesteps=latest['timesteps'],
                    initial_sha256=initial['sha256'],frozen_fusion_sha256=cfg['fusion_teacher']['sha256'],body='octane',
                    experts=list(SIX_NAMES),opponents=list(OPPONENTS),pairs=pairs,seconds=seconds,seed_start=SEED,
                    free_choice_probabilities=audit.summary(),latest_expert_decisions=dict(zip(SIX_NAMES,map(int,candidate.counts))),
                    summaries=summaries,paired_vs_fixed_fusion={n:paired_statistics(rows,trials['fixed_fusion']) for n,rows in trials.items() if n!='fixed_fusion'},
                    trials=trials,provenance=provenance(cfg),wall_seconds=time.monotonic()-started,
                    limitations=LIMITS+' All learner conditions use Octane. Six/eight-tick expert periods run on two-tick physics batches with one-tick simulator input delay. Ported deterministic neural policies omit external kickoff/difficulty helpers. Ducky uses installed RocketSim ball prediction in place of its V3 backend; world-contact normal is unavailable for turtle masks. Padding permutations have the same distribution, not the same C++ random stream. This is exploratory, not a promotion test or proof of native strength.')
            except (EvaluationStopped,KeyboardInterrupt):
                print('SIX_DIAGNOSTIC_CANCELLED: previous complete reports retained.',flush=True);return
            finally:
                if protected_hashes(run)!=before:raise RuntimeError('Protected run changed during six-expert diagnostics')
            report['protected_run_files_unchanged']=True
            destination=run/'six_diagnostics'/stamp();destination.mkdir(parents=True)
            atomic_json(destination/'diagnostic.json',report)
            out=run.parent.parent/'reports'/f'{name}_six_diagnostics_{destination.name}.zip';out.parent.mkdir(parents=True,exist_ok=True)
            with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:z.write(destination/'diagnostic.json','diagnostic.json')
            atomic_json(run/'six_diagnostics/latest.json',dict(path=str(destination.relative_to(run)),report_zip=str(out)))
            for label,summary in summaries.items():print('SIX_RESULT',label,json.dumps({k:v for k,v in summary.items() if k!='by_opponent'}),flush=True)
            print('SIX_DIAGNOSTIC_REPORT_READY:',out,flush=True);return out
    except Timeout as error:raise RuntimeError('Pause selector06 using 28 and wait for saving before diagnostics.') from error


def watch(path):
    from .viewer import prepare_viewer,learner_first_state
    from .chronos import ChronosEnv
    from rlgym.rocket_league.rlviser import RLViserRenderer
    from .six_experts import Pool
    torch.set_num_threads(1);path=Path(path).resolve();gate=Gate(path,'octane')
    cfg=load_config(path.parent/'config.json');lock=ROOT/'work/rlviser-watch.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with FileLock(str(lock),timeout=0):
        prepare_viewer(mode='auto');env=ChronosEnv(cfg,opponent='chronos',scenario='kickoff')
        renderer=RLViserRenderer(tick_rate=30);clock=Clock(Pool(gate.fusion_path),gate)
        try:
            env.reset(seed=271);clock.reset(env.arena.state,env.arena.agent,np.random.default_rng(271))
            last_log=0.;frames=0
            print('SIX WATCH: learner is car 1 / Octane. Opponent is Chronos. Console shows active expert. Ctrl+C stops.',flush=True)
            while True:
                start=time.monotonic()
                _,_,terminal,truncated,_=env.arena.step_control_ticks(clock.controls_for_ticks(env.arena.state,2),2,observation=False)
                frames+=1
                if frames%2==0:renderer.render(learner_first_state(env.arena.state,env.arena.agent),{})
                if time.monotonic()-last_log>=3:
                    print(json.dumps(dict(active=SIX_NAMES[clock.last_choice],decisions=dict(zip(SIX_NAMES,map(int,clock.counts))),**gate.status())),flush=True);last_log=time.monotonic()
                if terminal or truncated:
                    env.reset();clock.reset(env.arena.state,env.arena.agent,np.random.default_rng(271))
                time.sleep(max(0,2/120-(time.monotonic()-start)))
        except KeyboardInterrupt:pass
        finally:
            try:renderer.close()
            finally:env.close()
