"""Optional W&B metrics. Authentication stays with the SDK on the user's PC."""
from __future__ import annotations

import importlib
import json
import math
import numbers
import uuid
from collections import defaultdict, deque
from pathlib import Path

from stable_baselines3.common.logger import KVWriter

from .core import atomic_json


def sdk():
    try:
        return importlib.import_module('wandb')
    except ImportError:
        raise RuntimeError('W&B is not installed. Run 17_WANDB_SETUP.bat, or select --wandb off.') from None


def check_login():
    wandb=sdk()
    # Resolve existing session/env/settings/netrc credentials using the public SDK.
    # Never read a key ourselves or prompt for one inside an unattended trainer.
    try:
        ready=wandb.login(prompt=False,verify=True)
    except Exception as error:
        raise RuntimeError(f'W&B credential verification failed ({type(error).__name__}). '
                           'Run .venv\\Scripts\\python.exe -m wandb login locally, then retry.') from None
    if not ready:
        raise RuntimeError('W&B found no usable saved login. Run '
                           '.venv\\Scripts\\python.exe -m wandb login locally, then retry. '
                           'Also check that WANDB_MODE is not disabling online login.')
    print('WANDB_LOGIN_PASS: the SDK verified your saved login; no key is stored in NovaForge config.')


class EpisodeWindow:
    def __init__(self,size=200):
        self.records=deque(maxlen=size)

    def add(self,info):
        self.records.append(info)

    @staticmethod
    def outcomes(rows):
        n=len(rows)
        return dict(episodes=n,first_goal_score_fraction=sum(r['outcome']==1 for r in rows)/n,
                    concede_fraction=sum(r['outcome']==-1 for r in rows)/n,
                    timeout_fraction=sum(bool(r['timeout']) for r in rows)/n,
                    practice_success_fraction=sum(bool(r['practice_success']) for r in rows)/n)

    def metrics(self):
        if not self.records: return {}
        rows=list(self.records)
        result={f'window/{k}':v for k,v in self.outcomes(rows).items()}
        result['window/reward_mean']=sum(r['episode']['r'] for r in rows)/len(rows)
        result['window/touches_mean']=sum(r['touches'] for r in rows)/len(rows)
        by_opponent=defaultdict(list);by_scenario=defaultdict(list)
        for row in rows:
            by_opponent[row['opponent'].split(':')[0]].append(row)
            by_scenario[row['scenario']].append(row)
        for name,group in by_opponent.items():
            result.update({f'opponents/{name}/{k}':v for k,v in self.outcomes(group).items()})
        for name,group in by_scenario.items():
            result[f'mechanics/{name}/success_fraction']=sum(r['practice_success'] for r in group)/len(group)
            result[f'mechanics/{name}/episodes']=len(group)
        keys={k for r in rows for k in r['reward_parts']}
        for key in keys:
            result[f'rewards/{key}_mean']=sum(r['reward_parts'].get(key,0.) for r in rows)/len(rows)
        return result


class Tracker:
    def __init__(self,run_dir,cfg,mode=None,project=None,entity=None,continuous=False):
        self.run_dir=Path(run_dir)
        self.path=self.run_dir/'wandb_status.json'
        stored=json.loads(self.path.read_text()) if self.path.exists() else {}
        self.mode=mode if mode is not None else stored.get('mode','off')
        self.project=project or stored.get('project') or 'novaforge'
        self.entity=entity or stored.get('entity')
        self.id=stored.get('id') or uuid.uuid4().hex[:8]
        self.url=stored.get('url')
        self.run=None
        self.state='off' if self.mode=='off' else 'starting'
        self.last_step=0
        self.error=None
        if self.mode=='off':
            if stored and mode=='off':
                # Remember an explicit opt-out without losing a prior run ID.
                atomic_json(self.path,dict(stored,mode='off',state='off',error=None))
            return
        if stored.get('id') and (project and project!=stored.get('project') or
                               entity and stored.get('entity') and entity!=stored.get('entity')):
            raise ValueError('This training run already has a W&B project/entity. Keep them unchanged to resume it.')
        wandb=sdk()
        if self.mode=='online': check_login()
        kwargs=dict(project=self.project,entity=self.entity,id=self.id,name=self.run_dir.name,
            dir=str(self.run_dir),mode=self.mode,save_code=False,allow_val_change=True,
            config=dict(training=cfg,continuous_training=continuous),
            settings=wandb.Settings(init_timeout=45,login_timeout=15,save_code=False,
                disable_code=True,disable_git=True,x_disable_meta=True,console='off'))
        if self.mode=='online': kwargs['resume']='allow'
        try:
            self.run=wandb.init(**kwargs)
        except Exception as error:
            raise RuntimeError(f'W&B could not start ({type(error).__name__}). '
                'Check the local login, project permissions and connection; or use --wandb offline/off.') from None
        self.id=self.run.id
        self.project=self.run.project
        self.entity=self.run.entity
        self.url=self.run.url if self.mode=='online' else None
        self.state='online' if self.mode=='online' else 'offline'
        self.run.define_metric('trainer/timesteps')
        self.run.define_metric('*',step_metric='trainer/timesteps')
        self.save_status()
        print(f'W&B {self.state}: {self.url or self.run.dir}',flush=True)

    def status(self):
        return dict(mode=self.mode,state=self.state,id=self.id if self.mode!='off' else None,
                    project=self.project,entity=self.entity,url=self.url,
                    timesteps=self.last_step,error=self.error)

    def save_status(self):
        if self.mode!='off': atomic_json(self.path,self.status())

    def log(self,values,step):
        self.last_step=int(step)
        if self.run is None or self.error: return
        safe={}
        for key,value in values.items():
            if isinstance(value,numbers.Real) and math.isfinite(float(value)):
                safe[key]=float(value)
        safe['trainer/timesteps']=int(step)
        try:
            # Use W&B's own history sequence; checkpoint recovery can move the
            # training timestep backwards. Custom charts use trainer/timesteps.
            self.run.log(safe)
        except Exception as error:
            self.error=type(error).__name__
            self.state='logging_error'
            self.save_status()
            print(f'W&B logging stopped ({self.error}); training and local logs continue.',flush=True)

    def finish(self,state):
        if self.run is not None:
            try:
                self.run.summary['trainer/state']=state
                self.run.summary['trainer/timesteps']=self.last_step
                self.run.finish(exit_code=1 if state=='error' else 0)
            except Exception as error:
                self.error=type(error).__name__
            self.state=state if not self.error else 'logging_error'
            self.run=None
            self.save_status()


class WandBWriter(KVWriter):
    def __init__(self,tracker): self.tracker=tracker
    def write(self,key_values,key_excluded,step=0):
        values={k:v for k,v in key_values.items() if 'wandb' not in key_excluded.get(k,())}
        self.tracker.log(values,step)
    def close(self): pass
