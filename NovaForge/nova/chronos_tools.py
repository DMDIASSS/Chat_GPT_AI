"""Viewing, paired screening, v5 export, and metrics-only reporting for Chronos runs."""
from __future__ import annotations
import copy
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import uuid
import zipfile

import numpy as np
import torch
from filelock import FileLock

from .core import ROOT,atomic_json,check_model,sha256,write_model_meta
from .chronos import CHRONOS_CONTRACT,ChronosEnv
from .chronos_training import ChronosRunner,load_network,resolve_chronos
from .models import _sync_serialized_file
from .training import load_config


def evaluate_chronos(args):
    from .evaluation import summarize
    torch.set_num_threads(1)
    run=(ROOT/'runs'/args.run).resolve()
    if run.parent!=(ROOT/'runs').resolve():raise ValueError('Invalid run name')
    with FileLock(str(run/'train.lock'),timeout=0):
        cfg=load_config(run/'config.json');cfg['curriculum']['adaptive']=False
        cfg['env'].update(episode_seconds=args.seconds,no_touch_seconds=args.seconds+1)
        candidate=ChronosRunner(run);baseline=ChronosRunner(run/'checkpoints/step_000000000000.zip')
        opponents=[s.strip() for s in args.opponents.split(',')];scenarios=[s.strip() for s in args.scenarios.split(',')]
        if set(opponents)-{'scorer','chronos','galactus','nexto','ripple'}:raise ValueError('Unsupported Chronos screening opponent')
        if set(scenarios)-set(cfg['curriculum']['weights']):raise ValueError('Unsupported scenario')
        rows=[];base_rows=[]
        for opponent in opponents:
            for scenario in scenarios:
                for pair in range(args.pairs):
                    for side in (0,1):
                        env=ChronosEnv(cfg,opponent=opponent,scenario=scenario,side=side)
                        try:
                            initial_observation=None
                            for policy,destination,label in [(candidate,rows,'candidate'),(baseline,base_rows,'baseline')]:
                                obs,_=env.reset(seed=args.seed+pair)
                                if initial_observation is None:initial_observation=obs.copy()
                                elif not np.array_equal(initial_observation,obs):
                                    raise RuntimeError('Chronos paired starts differ')
                                while True:
                                    obs,_,terminated,truncated,info=env.step(policy.action(obs))
                                    if terminated or truncated:break
                                destination.append(dict(info,seed=args.seed+pair,policy=label))
                        finally:env.close()
                print(f'CHRONOS_EVAL {opponent}/{scenario}: {args.pairs} paired starts on both teams',flush=True)
        delta=np.array([a['outcome']-b['outcome'] for a,b in zip(rows,base_rows)])
        out=ROOT/'reports'/f'{args.run}_chronos_eval_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}_{uuid.uuid4().hex[:6]}.json'
        atomic_json(out,dict(kind='first_goal_trials',contract=CHRONOS_CONTRACT,candidate_sha256=sha256(candidate.path),
            baseline_sha256=sha256(baseline.path),summary=summarize(rows),baseline_summary=summarize(base_rows),
            trials=rows,baseline_trials=base_rows,seconds_per_trial=args.seconds,seed_start=args.seed,paired_team_sides=True,
            paired_initial_observations_verified=True,
            paired_mean_outcome_delta=float(delta.mean()),paired_delta_standard_error=float(delta.std(ddof=1)/len(delta)**.5) if len(delta)>1 else None,
            breakdown={o:{s:summarize([r for r in rows if r['opponent']==o and r['scenario']==s]) for s in scenarios} for o in opponents},
            note='Compare against the unchanged initialization; first-goal simulator screening, not full-match strength. No automatic promotion.'))
        print(json.dumps(summarize(rows),indent=2));print('CHRONOS_EVAL_READY:',out)
    report_chronos(args)


def watch_chronos(args):
    from .viewer import prepare_viewer,learner_first_state
    torch.set_num_threads(1)
    run=(ROOT/'runs'/args.run).resolve()
    if run.parent!=(ROOT/'runs').resolve():raise ValueError('Invalid run name')
    path=run/'checkpoints/step_000000000000.zip' if args.initial else run
    policy=ChronosRunner(path);cfg=load_config(run/'config.json')
    cfg['env'].update(episode_seconds=30,no_touch_seconds=31)
    lock=ROOT/'work/rlviser-watch.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with FileLock(str(lock),timeout=0):
        prepare_viewer(mode=args.viewer_mode)
        from rlgym.rocket_league.rlviser import RLViserRenderer
        env=ChronosEnv(cfg,opponent=args.opponent,scenario=args.scenario)
        renderer=RLViserRenderer(tick_rate=15)
        print(f'Watching Chronos checkpoint {policy.path.name}, SHA256 {sha256(policy.path)}; camera follows learner.',flush=True)
        try:
            obs,_=env.reset(seed=631099)
            while True:
                start=time.monotonic()
                obs,_,terminal,truncated,info=env.step(policy.action(obs))
                renderer.render(learner_first_state(env.arena.state,env.arena.agent),{})
                if terminal or truncated:
                    print(json.dumps({k:info[k] for k in ['outcome','scenario','touches']}),flush=True);obs,_=env.reset()
                time.sleep(max(0,1/15-(time.monotonic()-start)))
        except KeyboardInterrupt:pass
        finally:
            try:renderer.close()
            finally:env.close()


def export_chronos(args):
    torch.set_num_threads(1)
    run=(ROOT/'runs'/args.run).resolve()
    if run.parent!=(ROOT/'runs').resolve():raise ValueError('Invalid run name')
    source=resolve_chronos(run/'checkpoints/step_000000000000.zip' if getattr(args,'initial',False) else run)
    meta=check_model(source,CHRONOS_CONTRACT)
    actor=load_network(source)
    stem='novachronos_'+meta['sha256'][:10]+'_'+uuid.uuid4().hex[:6]
    parent=ROOT/'exports';parent.mkdir(parents=True,exist_ok=True)
    dest=parent/stem;agent_id='DMDIASSS/'+stem
    with tempfile.TemporaryDirectory(prefix='chronos_export_',dir=parent) as temporary:
        stage=Path(temporary)/stem;stage.mkdir()
        # These are genuine separately scripted native-compatible components.
        for name,module,role in [('actor.lt',actor,'chronos_actor'),('SHARED_HEAD.lt',actor.head,'chronos_shared_head'),('POLICY.lt',actor.policy,'chronos_policy_head')]:
            torch.jit.save(torch.jit.script(copy.deepcopy(module).cpu().eval()),str(stage/name));_sync_serialized_file(stage/name)
            write_model_meta(stage/name,contract=CHRONOS_CONTRACT,timesteps=meta['timesteps'],source_sha256=meta['sha256'],role=role)
        with torch.inference_mode():
            x=torch.linspace(-1,1,450).reshape(2,225)
            full=torch.jit.load(str(stage/'actor.lt'))(x)
            parts=torch.jit.load(str(stage/'POLICY.lt'))(torch.jit.load(str(stage/'SHARED_HEAD.lt'))(x))
            torch.testing.assert_close(full,actor(x),rtol=0,atol=0)
            torch.testing.assert_close(parts,full,rtol=0,atol=0)
        toml='''#:schema https://rlbot.org/schemas/agent.json
[settings]
name = "NovaChronos"
agent_id = AGENT
run_command = WIN
run_command_linux = LINUX
hivemind = true
[details]
developer = "NovaForge user; Chronos model credit: KingJake3113"
description = "Chronos-initialized 1v1 PPO student. Requires enclosing NovaForge project."
language = "python"
tags = ["1v1"]
'''
        toml=toml.replace('name = "NovaChronos"','name = '+json.dumps('NovaChronos initial' if getattr(args,'initial',False) else f'NovaChronos {meta["timesteps"]}'))
        for token,value in [('AGENT',agent_id),('WIN','"..\\..\\.venv\\Scripts\\python.exe" bot.py'),('LINUX','"../../.venv/bin/python" bot.py')]:
            toml=toml.replace('= '+token+'\n','= '+json.dumps(value)+'\n')
        (stage/'bot.bot.toml').write_text(toml)
        (stage/'bot.py').write_text('from pathlib import Path\nimport sys\nsys.path.insert(0,str(Path(__file__).resolve().parents[2]))\nfrom nova.chronos_live import ChronosBot\nif __name__=="__main__":\n    ChronosBot(Path(__file__).with_name("actor.lt"),'+repr(agent_id)+').run()\n')
        (stage/'README.txt').write_text('Keep this folder inside novaforge/exports and add bot.bot.toml to RLBot v5.\nactor.lt is the combined 225->90 network used by this Python runtime.\nSHARED_HEAD.lt and POLICY.lt preserve Chronos component architecture for a separately configured copy of the original native runtime.\nTOML is a launcher, not weights. The native port action mask lacks the original world-contact-normal exception; live full-match validation is still needed.\nSource model: KingJake3113/Chronos commit 4f8fdd27e4802d977b33b9ade4759ff6aeaca5aa.\nThe original repository has no explicit root model license; no new license grant for its weights is implied.\n')
        archive=Path(temporary)/(stem+'.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(stage.iterdir()):z.write(p,stem+'/'+p.name)
        stage.replace(dest);archive.replace(parent/(stem+'.zip'))
    print('CHRONOS_EXPORT_READY:',dest/'bot.bot.toml')
    print('Native components:',dest/'SHARED_HEAD.lt',dest/'POLICY.lt')


def report_chronos(args):
    from .reporting import read_json,clean_config,episode_summaries,ppo_summaries,checkpoint_metadata,evaluation_summaries,safe_url,numbers
    run=(ROOT/'runs'/args.run).resolve()
    if run.parent!=(ROOT/'runs').resolve():raise ValueError('Invalid run name')
    source=resolve_chronos(run);meta=check_model(source,CHRONOS_CONTRACT)
    cfg=read_json(run/'config.json');tracking=read_json(run/'wandb_status.json')
    history=checkpoint_metadata(run);hashes={r['sha256'] for r in history}
    initial=check_model(run/'checkpoints/step_000000000000.zip',CHRONOS_CONTRACT)
    report=dict(kind='chronos_ppo',contract=CHRONOS_CONTRACT,run=run.name,
        checkpoint=dict(sha256=meta['sha256'],timesteps=meta['timesteps']),configuration=clean_config(cfg),
        initial_checkpoint=dict(sha256=initial['sha256'],timesteps=0),
        reward_profile='sparse_goal_v1' if cfg.get('rewards')=='sparse' else cfg.get('chronos',{}).get('reward_profile','potential_goal_v1'),
        chronos=numbers(cfg.get('chronos'),{'actor_lr','critic_lr','anchor_coef','critic_warmup_updates','checkpoints_keep'}),
        episodes=episode_summaries(run/'episodes.jsonl',meta['timesteps']),ppo=ppo_summaries(run),
        evaluations=evaluation_summaries(ROOT/'reports',meta['sha256'],hashes),wandb_url=safe_url(tracking.get('url')),
        note='PPO rewards on learner-controlled trajectories; frozen Chronos KL anchor, mixed frozen opponents and snapshot self-play. Compare actual gameplay with initialization.')
    parent=ROOT/'reports';parent.mkdir(parents=True,exist_ok=True)
    out=parent/f'{run.name}_chronos_report_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}_{uuid.uuid4().hex[:6]}.zip'
    # The report contains selected metrics only, without raw configs, weights or credentials.
    with tempfile.TemporaryDirectory(dir=parent) as temporary:
        temp=Path(temporary)/'report.zip'
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('report.json',json.dumps(report,indent=2,allow_nan=False))
            z.writestr('README.txt','Upload this ZIP for review. Checkpoint and initial-model comparisons are simulator screening, not a strength guarantee.\n')
        _sync_serialized_file(temp);temp.replace(out)
    print('CHRONOS_REPORT_READY:',out)
