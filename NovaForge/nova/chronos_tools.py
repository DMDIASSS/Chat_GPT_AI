"""Viewing, paired screening, v5 export, and metrics-only reporting for Chronos runs."""
from __future__ import annotations
import copy
from datetime import datetime,timezone
import json
import inspect
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
from .chronos_guard import select_checkpoint,paired_statistics


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
        statistics=paired_statistics(rows,base_rows)
        delta=np.array([a['outcome']-b['outcome'] for a,b in zip(rows,base_rows)])
        out=ROOT/'reports'/f'{args.run}_chronos_eval_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}_{uuid.uuid4().hex[:6]}.json'
        atomic_json(out,dict(kind='first_goal_trials',contract=CHRONOS_CONTRACT,candidate_sha256=sha256(candidate.path),
            baseline_sha256=sha256(baseline.path),summary=summarize(rows),baseline_summary=summarize(base_rows),
            trials=rows,baseline_trials=base_rows,seconds_per_trial=args.seconds,seed_start=args.seed,paired_team_sides=True,
            paired_initial_observations_verified=True,
            paired_mean_outcome_delta=float(delta.mean()),paired_delta_standard_error=statistics['standard_error'],
            paired_seed_block_statistics=statistics,
            breakdown={o:{s:summarize([r for r in rows if r['opponent']==o and r['scenario']==s]) for s in scenarios} for o in opponents},
            note='Compare against the unchanged initialization; first-goal simulator screening, not full-match strength. No automatic promotion.'))
        print(json.dumps(summarize(rows),indent=2));print('CHRONOS_EVAL_READY:',out)
    report_chronos(args)


def watch_chronos(args):
    from .viewer import prepare_viewer,learner_first_state
    torch.set_num_threads(1)
    run=(ROOT/'runs'/args.run).resolve()
    if run.parent!=(ROOT/'runs').resolve():raise ValueError('Invalid run name')
    path=select_checkpoint(run,initial=args.initial,latest=getattr(args,'latest',False))
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
    source=select_checkpoint(run,initial=getattr(args,'initial',False),latest=getattr(args,'latest',False))
    meta=check_model(source,CHRONOS_CONTRACT)
    saved_body=load_config(run/'config.json').get('env',{}).get('learner_hitbox','octane') if (run/'config.json').exists() else 'breakout'
    body='breakout' if meta['timesteps']==0 else saved_body
    car_id=22 if body=='breakout' else 23
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
        shutil.copy2(stage/'actor.lt',stage/'actor.pt')
        shutil.copy2(stage/'actor.lt.json',stage/'actor.pt.json')
        torch.save(actor.state_dict(),stage/'actor_weights.pt')
        _sync_serialized_file(stage/'actor_weights.pt')
        write_model_meta(stage/'actor_weights.pt',contract=CHRONOS_CONTRACT,timesteps=meta['timesteps'],role='chronos_state_dict')
        # Standalone v4 export has no dependency on the training project or v5 SDK.
        from . import giga_teachers as features
        from .chronos_live import ChronosClock
        header='import numpy as np\nTABLE=np.asarray('+repr(features.TABLE.tolist())+',dtype=np.float32)\nBOOSTS=np.asarray('+repr(features.BOOSTS.tolist())+',dtype=np.float32)\nMIRROR_PADS=np.asarray('+repr(features.MIRROR_PADS.tolist())+',dtype=int)\n'
        functions='\n\n'.join(inspect.getsource(getattr(features,name)) for name in ('native_action_mask','_physics','_player','build_features'))
        (stage/'features.py').write_text(header+functions)
        (stage/'clock.py').write_text('import numpy as np\nimport torch\nfrom features import TABLE,build_features,native_action_mask\n\n'+inspect.getsource(ChronosClock))
        shutil.copy2(Path(__file__).with_name('chronos_v4.py'),stage/'chronos_v4.py')
        (stage/'bot_v4.py').write_text('from pathlib import Path\nfrom chronos_v4 import make_agent\nfrom clock import ChronosClock\nfrom features import BOOSTS\nclass NovaChronos(make_agent(Path(__file__).with_name("actor.pt"),ChronosClock,BOOSTS)):\n    pass\n')
        (stage/'bot.cfg').write_text('[Locations]\npython_file = bot_v4.py\nlooks_config = looks.cfg\nname = NovaChronos '+str(meta['timesteps'])+'\nmaximum_tick_rate = 120\nrequirements_file = requirements-v4.txt\n\n[Details]\ndeveloper = NovaForge user; original model KingJake3113\ndescription = Chronos PPO export. Python 3.11 x64. Estimated v4 flip timing; v5 preferred.\nlanguage = python\n')
        (stage/'looks.cfg').write_text('[Bot Loadout]\nteam_color_id = 27\ncustom_color_id = 0\ncar_id = '+str(car_id)+'\ndecal_id = 0\nwheels_id = 1565\nboost_id = 0\nantenna_id = 0\nhat_id = 0\npaint_finish_id = 197\npaint_finish_2_id = 197\n')
        (stage/'requirements-v4.txt').write_text('--extra-index-url https://download.pytorch.org/whl/cpu\ntorch==2.9.1+cpu\nnumpy==1.26.4\nrlbot==1.68.0\nsetuptools<81\n')
        from .reporting import clean_config,numbers
        saved_cfg=load_config(run/'config.json') if (run/'config.json').exists() else {}
        training_cfg=clean_config(saved_cfg)
        training_cfg['chronos']=numbers(saved_cfg.get('chronos'),{'actor_lr','critic_lr','anchor_coef','anchor_kl_limit','critic_warmup_updates'})
        atomic_json(stage/'training_config.json',training_cfg)
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
loadout_file = "loadout.toml"
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
        (stage/'loadout.toml').write_text('[blue_loadout]\ncar_id = '+str(car_id)+'\n[orange_loadout]\ncar_id = '+str(car_id)+'\n')
        (stage/'bot.py').write_text('from pathlib import Path\nimport sys\nsys.path.insert(0,str(Path(__file__).resolve().parents[2]))\nfrom nova.chronos_live import ChronosBot\nif __name__=="__main__":\n    ChronosBot(Path(__file__).with_name("actor.lt"),'+repr(agent_id)+').run()\n')
        (stage/'README.txt').write_text('RLBot v5: keep this folder inside novaforge/exports and add bot.bot.toml to v5. It uses actor.lt.\nRLBot v4: add bot.cfg to the v4 GUI with Python 3.11 x64 and install requirements-v4.txt in its separate v4 environment. This export uses actor.pt and can be moved as a complete folder. Never install the v4 SDK into the training .venv.\nactor.pt and actor.lt are the same 225->90 TorchScript network. actor_weights.pt is a separate state_dict for custom code; training_config.json describes the training settings. Full PPO/optimizer resume uses the .zip under runs, not actor_weights.pt.\nSHARED_HEAD.lt and POLICY.lt preserve the native Chronos architecture. Native observation/action timing must match.\nThe port mask lacks the original contact-normal exception; v4 also estimates flip timing from less detailed packet fields. Live full-match checks are required.\nSource model: KingJake3113/Chronos commit 4f8fdd27e4802d977b33b9ade4759ff6aeaca5aa.\nNo explicit root model license was identified; no new license grant for the original weights is implied.\n')
        archive=Path(temporary)/(stem+'.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(stage.iterdir()):z.write(p,stem+'/'+p.name)
        stage.replace(dest);archive.replace(parent/(stem+'.zip'))
    print('CHRONOS_EXPORT_READY:',dest/'bot.bot.toml')
    print('RLBot v4:',dest/'bot.cfg','with',dest/'actor.pt')
    print('Native components:',dest/'SHARED_HEAD.lt',dest/'POLICY.lt')


def report_chronos(args):
    from .reporting import read_json,clean_config,episode_summaries,ppo_summaries,checkpoint_metadata,evaluation_summaries,safe_url,numbers
    run=(ROOT/'runs'/args.run).resolve()
    if run.parent!=(ROOT/'runs').resolve():raise ValueError('Invalid run name')
    source=resolve_chronos(run);meta=check_model(source,CHRONOS_CONTRACT)
    cfg=read_json(run/'config.json');tracking=read_json(run/'wandb_status.json')
    history=checkpoint_metadata(run);hashes={r['sha256'] for r in history}
    initial=check_model(run/'checkpoints/step_000000000000.zip',CHRONOS_CONTRACT)
    champion=check_model(select_checkpoint(run),CHRONOS_CONTRACT)
    guard=read_json(run/'guard_state.json')
    report=dict(kind='chronos_ppo',contract=CHRONOS_CONTRACT,run=run.name,
        checkpoint=dict(sha256=meta['sha256'],timesteps=meta['timesteps']),configuration=clean_config(cfg),
        initial_checkpoint=dict(sha256=initial['sha256'],timesteps=0),
        champion_checkpoint=dict(sha256=champion['sha256'],timesteps=champion['timesteps']),
        automatic_guard=dict(numbers(guard,{'last_checked_step','checks','regressions','rollbacks','champion_timesteps'}),
            decision=guard.get('decision') if guard.get('decision') in {'improved','regressed','retain'} else None,
            statistics=numbers(guard.get('statistics'),{'blocks','trials','mean_delta','standard_error'}),
            candidate_wdl=numbers(guard.get('candidate_wdl'),{'matches','wins','draws','losses','goals_for','goals_against'}),
            champion_wdl=numbers(guard.get('champion_wdl'),{'matches','wins','draws','losses','goals_for','goals_against'})),
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
