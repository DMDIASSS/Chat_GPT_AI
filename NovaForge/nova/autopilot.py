"""One unattended selector job, protected local exports and automatic reports."""
from __future__ import annotations
import json
from pathlib import Path
import time
from filelock import FileLock
from . import __version__
from .core import atomic_json,sha256


def maintenance(run,*,report=True):
    """Caller owns train.lock. Artifact failures are recorded, never promoted."""
    from .research import report_locked
    from .triad_selector import selector_meta
    from .triad import export
    run=Path(run);path=run/'autopilot.json'
    state=json.loads(path.read_text()) if path.exists() else {}
    state.update(schema='selector-autopilot-v1',updated_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    errors=[]
    if report:
        try:state['report_zip']=str(report_locked(run))
        except Exception as error:errors.append('report: '+str(error))
    try:
        meta=selector_meta(run/'champion.pt');previous=state.get('champion_export',{})
        if previous.get('sha256')!=meta['sha256'] or previous.get('runtime_version')!=__version__ or not Path(previous.get('toml','')).is_file():
            folder=export(selector_path=run/'champion.pt')
            state['champion_export']=dict(sha256=meta['sha256'],timesteps=meta['timesteps'],folder=str(folder),
                toml=str(folder/'bot.bot.toml'),runtime_version=__version__)
            print('AUTOPILOT_CHAMPION_EXPORTED:',folder/'bot.bot.toml',flush=True)
    except Exception as error:errors.append('export: '+str(error))
    state['artifact_errors']=errors;atomic_json(path,state)
    for error in errors:print('AUTOPILOT_ARTIFACT_ERROR:',error,'Training checkpoints are retained; retry at the next save.',flush=True)
    return state


def run(name='selector06',once=False,wandb='online',steps=32768):
    from .research import run_path,backup
    from .triad_selector import train,SIX_NAMES,selector_meta
    from .opponent_sampling import configure
    run=run_path(name)
    if not (run/'full.zip').exists():raise FileNotFoundError('No saved selector06. Create with 26 and save training with 27 first.')
    with FileLock(str(run/'autopilot.lock'),timeout=0):
        with FileLock(str(run/'train.lock'),timeout=0):
            cfg=json.loads((run/'config.json').read_text())
            if tuple(cfg.get('selector_experts',()))!=SIX_NAMES:raise ValueError('Autopilot expects the six-expert Octane run')
            selector_meta(run/'full.zip')
            (run/'STOP').unlink(missing_ok=True)
        if not (run/'opponent_sampling_policy.json').exists():configure(name,True)
        backup(name)
        print('AUTOPILOT: resume one selector; frozen Fusion/experts; balanced guard checks; automatic reports and champion exports.',flush=True)
        print('Pause with 28 or Ctrl+C. No viewer or second trainer is started.',flush=True)
        train(name,steps=steps,forever=not once,wandb=wandb,autopilot=True,clear_stop=False)


def benchmark(name='selector06',steps=2048):
    """Fixed native environment workload, excludes PPO/evaluation/export time."""
    import numpy as np
    import torch
    from .triad_selector import SelectorEnv,SIX_NAMES
    from .research import run_path,stamp
    from .training import load_config
    if not isinstance(steps,int) or not 64<=steps<=32768:raise ValueError('Benchmark needs 64..32768 decisions')
    torch.set_num_threads(1);run=run_path(name)
    with FileLock(str(run/'train.lock'),timeout=0):
        cfg=load_config(run/'config.json')
        if tuple(cfg.get('selector_experts',()))!=SIX_NAMES:raise ValueError('Benchmark expects selector06')
        cfg['env'].update(episode_seconds=30,no_touch_seconds=30)
        before={n:sha256(run/n) for n in ('full.zip','latest.pt','champion.pt','frozen_fusion.pt')}
        env=SelectorEnv(cfg,run)
        try:
            env.reset(seed=271)
            for i in range(256):
                choice=(i//32)%6 if env.context.remaining==0 else env.context.last
                _,_,terminal,truncated,_=env.step(choice)
                if terminal or truncated:env.reset(seed=271+i)
            env.reset(seed=991);started=time.perf_counter()
            for i in range(steps):
                choice=(i//64)%6 if env.context.remaining==0 else env.context.last
                _,_,terminal,truncated,_=env.step(choice)
                if terminal or truncated:env.reset(seed=991+i)
            elapsed=time.perf_counter()-started
        finally:env.close()
        if before!={n:sha256(run/n) for n in before}:raise RuntimeError('Benchmark altered a protected checkpoint')
        result=dict(kind='six_expert_environment_benchmark_v1',decisions=steps,seconds=elapsed,environment_decisions_per_second=steps/elapsed,
            runtime_version=__version__,threads=1,physics_batch_ticks=2,decision_ticks=8,precision='float32',
            note='Six fixed experts rotate at free options; base opponent mix, seeded resets. No PPO, training, promotion or live viewer. Excludes startup and warmup; includes resets during measurement. Native demo respawns can vary.')
        out=run.parent.parent/'reports'/f'{name}_speed_{stamp()}.json';atomic_json(out,result)
        print('ENVIRONMENT_DECISIONS_PER_SECOND:',round(steps/elapsed,1),'(excludes PPO/evaluation/export)',flush=True)
        print('SPEED_REPORT_READY:',out,flush=True);return out
