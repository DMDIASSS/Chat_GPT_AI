"""An options-style PPO selector over three frozen, version-locked experts.

Original implementation inspired by Opti's hierarchy; no Opti code/weights are
vendored. The selector chooses an expert, never edits the expert networks.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import shutil
import time
import numpy as np
import torch
from torch import nn
from gymnasium import Env,spaces
from stable_baselines3 import PPO
from stable_baselines3.common.policies import ActorCriticPolicy
from stable_baselines3.common.logger import configure
from stable_baselines3.common.callbacks import BaseCallback
from filelock import FileLock
from .core import ROOT,atomic_json,check_model,write_model_meta,sha256
from .models import save_ppo,_sync_serialized_file
from .chronos import ChronosEnv
from .training import load_config

NAMES=('chronos','galactus','ripple')
CONTRACT=dict(name='triad-selector-v1',observation=234,actions=list(NAMES),decision_ticks=8,hold_decisions=8)
RUNS=ROOT.parent/'triadbot/runs'


class Context:
    def __init__(self,body='breakout'):
        if body not in ('breakout','octane'):raise ValueError('Unsupported selector body')
        self.body=body;self.last=None;self.remaining=0
    def observation(self,features):
        previous=np.zeros(3,np.float32)
        if self.last is not None:previous[self.last]=1
        mask=np.ones(3,np.float32) if self.remaining==0 else previous.copy()
        return np.concatenate((features,previous,[self.remaining/8],
            [self.body=='breakout',self.body=='octane'],mask)).astype(np.float32)
    def advance(self,choice):
        if choice not in (0,1,2) or (self.remaining and choice!=self.last):raise ValueError('Expert is committed during this option')
        self.remaining=7 if self.remaining==0 else self.remaining-1
        self.last=int(choice)


class SelectorPolicy(ActorCriticPolicy):
    def distribution(self,obs):
        features=self.extract_features(obs);latent=self.mlp_extractor.forward_actor(features)
        logits=self.action_net(latent);mask=obs[:,-3:]>0
        if not mask.any(dim=-1).all():raise ValueError('Empty selector mask')
        return self.action_dist.proba_distribution(action_logits=torch.where(mask,logits,torch.full_like(logits,-1e9)))
    def get_distribution(self,obs):return self.distribution(obs)
    def _predict(self,obs,deterministic=False):return self.distribution(obs).get_actions(deterministic=deterministic)
    def forward(self,obs,deterministic=False):
        dist=self.distribution(obs);actions=dist.get_actions(deterministic=deterministic)
        return actions,self.predict_values(obs),dist.log_prob(actions)
    def evaluate_actions(self,obs,actions):
        dist=self.distribution(obs)
        return self.predict_values(obs),dist.log_prob(actions),dist.entropy()


class Gate:
    def __init__(self,path,body='breakout'):
        path=resolve(path);meta=check_model(path,CONTRACT)
        if meta['hitbox']!=body:raise ValueError('Selector was trained for a different hitbox')
        if meta['teacher_lock_sha256']!=sha256(ROOT/'teachers.lock.json'):raise ValueError('Selector teacher pins changed')
        self.network=torch.jit.load(str(path),map_location='cpu').eval();self.body=body;self.training_steps=meta['timesteps'];self.reset()
    def reset(self):self.context=Context(self.body)
    def choose(self,features):
        obs=self.context.observation(features)
        with torch.inference_mode():logits=self.network(torch.from_numpy(obs)[None,:])[0].numpy()
        if logits.shape!=(3,) or not np.isfinite(logits).all():raise ValueError('Invalid selector output')
        choice=int(np.where(obs[-3:]>0,logits,-np.inf).argmax());self.context.advance(choice)
        return choice


def resolve(path):
    path=Path(path)
    if not path.exists() and len(path.parts)==1:path=RUNS/path
    elif not path.exists() and not path.is_absolute():path=RUNS.parent/path
    if path.is_dir():path=path/'champion.pt'
    check_model(path,CONTRACT)
    return path


class SelectorEnv(Env):
    def __init__(self,cfg):
        self.inner=ChronosEnv(cfg);self.body=cfg['env']['learner_hitbox']
        self.action_space=spaces.Discrete(3);self.observation_space=spaces.Box(-np.inf,np.inf,(234,),np.float32)
        self.teacher=None
    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed)
        if self.teacher is None:
            from .chronos_fusion import TeacherFusion
            self.teacher=TeacherFusion()
        self.features,info=self.inner.reset(seed=seed,options=options);self.context=Context(self.body)
        self.teacher.reset(self.inner.arena.state,self.inner.arena.agent,np.random.default_rng(seed))
        self.counts=np.zeros(3,dtype=int)
        return self.context.observation(self.features[:225]),info
    def step(self,choice):
        choice=int(choice);self.context.advance(choice);self.counts[choice]+=1
        controls=self.teacher.proposals(self.inner.arena.state,self.inner.previous,self.features[:225],self.inner.mirror)
        self.features,reward,terminal,truncated,info=self.inner.step_world_controls(controls[choice])
        if 'episode' in info:info['selector_counts']=dict(zip(NAMES,map(int,self.counts)))
        return self.context.observation(self.features[:225]),reward,terminal,truncated,info
    def close(self):self.inner.close()


class Runner:
    def __init__(self,path,body):
        self.gate=Gate(path,body)
        from .chronos_fusion import TeacherFusion
        self.teacher=TeacherFusion()
    def bind(self,env):
        self.env=env;self.gate.reset()
        self.teacher.reset(env.arena.state,env.arena.agent,np.random.default_rng(271))
    def world_controls(self,obs):
        env=self.env;choice=self.gate.choose(obs[:225])
        return self.teacher.proposals(env.arena.state,env.previous,obs[:225],env.mirror)[choice]


def save_actor(model,path,body):
    actor=nn.Sequential(copy.deepcopy(model.policy.mlp_extractor.policy_net),copy.deepcopy(model.policy.action_net)).cpu().eval()
    script=torch.jit.script(actor)
    path=Path(path);temp=path.with_suffix('.tmp.pt');torch.jit.save(script,str(temp));_sync_serialized_file(temp);temp.replace(path)
    write_model_meta(path,contract=CONTRACT,timesteps=int(model.num_timesteps),hitbox=body,
        teacher_lock_sha256=sha256(ROOT/'teachers.lock.json'))


def train(run_name='selector01',steps=32768,forever=True,wandb='online'):
    from .teachers import fetch_teachers
    from .tracking import Tracker,EpisodeWindow,WandBWriter
    fetch_teachers(['chronos','galactus','ripple','nexto']);torch.set_num_threads(1)
    run=(RUNS/run_name).resolve()
    if run.parent!=RUNS.resolve():raise ValueError('Invalid selector run name')
    run.mkdir(parents=True,exist_ok=True)
    with FileLock(str(run/'train.lock'),timeout=0):
        cfg=load_config(run/'config.json' if (run/'config.json').exists() else ROOT/'configs/chronos.json')
        cfg['env'].setdefault('learner_hitbox','breakout');cfg['league']['weights']={n:.25 for n in ('chronos','galactus','ripple','nexto')}
        atomic_json(run/'config.json',cfg);env=SelectorEnv(cfg);tracker=Tracker(run,cfg,mode=wandb,continuous=forever)
        model=None;state='error';before=None;window=EpisodeWindow()
        try:
            if (run/'full.zip').exists():
                check_model(run/'full.zip',CONTRACT);model=PPO.load(run/'full.zip',env=env,device='cpu')
            else:
                model=PPO(SelectorPolicy,env,device='cpu',learning_rate=1e-4,n_steps=512,batch_size=256,n_epochs=4,
                    gamma=cfg['ppo']['gamma'],gae_lambda=.97,clip_range=.1,ent_coef=.003,target_kl=.02,seed=271,verbose=1,
                    policy_kwargs=dict(net_arch=dict(pi=[128,128],vf=[128,128])))
                with torch.no_grad():
                    model.policy.action_net.weight.zero_();model.policy.action_net.bias.copy_(torch.tensor([1.,0.,0.]))
                save_actor(model,run/'initial.pt',cfg['env']['learner_hitbox'])
                shutil.copy2(run/'initial.pt',run/'champion.pt');shutil.copy2(run/'initial.pt.json',run/'champion.pt.json')
            model.set_logger(configure(str(run/'logs'),['stdout','csv']))
            if tracker.run is not None:model.logger.output_formats.append(WandBWriter(tracker))
            if getattr(model,'selector_halt',None):
                print('SELECTOR_HALTED:',model.selector_halt,'Export the retained champion.');state='stopped';return
            (run/'STOP').unlink(missing_ok=True)
            checks=json.loads((run/'guard.json').read_text()) if (run/'guard.json').exists() else {}
            class Callback(BaseCallback):
                def _on_step(self):
                    for info in self.locals.get('infos',[]):
                        if 'outcome' in info:window.add(info)
                    if self.n_calls%500==0:
                        metrics=window.metrics();tracker.log(metrics,self.num_timesteps)
                        atomic_json(run/'status.json',dict(state='training',timesteps=self.num_timesteps,metrics=metrics,wandb=tracker.status()))
                    return not (run/'STOP').exists()
            callback=Callback()
            while not (run/'STOP').exists():
                before=copy.deepcopy(model.policy.state_dict());optim_before=copy.deepcopy(model.policy.optimizer.state_dict())
                try:model.learn(steps,callback=callback,reset_num_timesteps=False)
                except BaseException:
                    if any(not torch.isfinite(p).all() for p in model.policy.parameters()):
                        model.policy.load_state_dict(before);model.policy.optimizer.load_state_dict(optim_before)
                    raise
                if any(not torch.isfinite(p).all() for p in model.policy.parameters()):
                    model.policy.load_state_dict(before);model.policy.optimizer.load_state_dict(optim_before)
                    model.selector_halt='Nonfinite selector update';(run/'STOP').touch()
                save_ppo(model,run/'full.zip',contract=CONTRACT)
                save_actor(model,run/'latest.pt',cfg['env']['learner_hitbox'])
                if not (run/'STOP').exists() and model.num_timesteps-checks.get('step',0)>=131072:
                    atomic_json(run/'status.json',dict(state='evaluating',timesteps=model.num_timesteps))
                    check_progress(run,cfg,model,checks)
                if not forever:state='finished';break
            else:state='stopped'
            if (run/'STOP').exists():state='stopped'
        except KeyboardInterrupt:state='stopped'
        finally:
            if model is not None:
                save_ppo(model,run/'full.zip',contract=CONTRACT)
                save_actor(model,run/'latest.pt',cfg['env']['learner_hitbox'])
                atomic_json(run/'status.json',dict(state=state,timesteps=model.num_timesteps,
                    halt_reason=getattr(model,'selector_halt',None),guard=checks if 'checks' in locals() else {},wandb=tracker.status()))
            env.close();tracker.finish(state)


def check_progress(run,cfg,model,checks):
    from .chronos_league import match_suite,match_summary
    from .chronos_guard import paired_statistics,judgement,EvaluationStopped
    settings=cfg['chronos']['guard'];seed=51000001+checks.get('checks',0)*10000000;body=cfg['env']['learner_hitbox']
    try:
        rows,old=match_suite(cfg,Runner(run/'latest.pt',body),Runner(run/'champion.pt',body),4,60,seed,run/'STOP')
        stats=paired_statistics(rows,old);decision=judgement(stats,settings)
        if decision=='improved':
            fresh,prior=match_suite(cfg,Runner(run/'latest.pt',body),Runner(run/'champion.pt',body),4,60,seed+5000000,run/'STOP')
            if judgement(paired_statistics(fresh,prior),settings)=='improved':
                shutil.copy2(run/'latest.pt',run/'champion.pt');shutil.copy2(run/'latest.pt.json',run/'champion.pt.json')
            else:decision='retain'
        bad=checks.get('regressions',0)+1 if decision=='regressed' else 0
        if bad>=2 or (decision=='regressed' and stats['mean_delta']<=-.35):
            model.selector_halt='Substantial selector W/D/L regression';(run/'STOP').touch()
        checks.update(step=int(model.num_timesteps),checks=checks.get('checks',0)+1,regressions=bad,
            decision=decision,statistics=stats,candidate=match_summary(rows),champion=match_summary(old))
        atomic_json(run/'guard.json',checks)
    except EvaluationStopped:pass


def evaluate(run_name='selector01',pairs=2,seconds=60):
    from .chronos_league import match_suite,match_summary
    from .chronos_guard import paired_statistics,EvaluationStopped
    from filelock import Timeout
    if pairs<=0 or not np.isfinite(seconds) or seconds<=0:raise ValueError('Positive pairs and seconds are required')
    torch.set_num_threads(1)
    print(f'SELECTOR_EVALUATION_START: Torch threads={torch.get_num_threads()}, games={4*pairs*2*2}, duration={seconds:g}s simulated/game',flush=True)
    run=(RUNS/run_name).resolve()
    if run.parent!=RUNS.resolve():raise ValueError('Invalid run name')
    if not (run/'config.json').exists():raise FileNotFoundError('No selector run. Start launcher 4 and save a checkpoint first.')
    try:
        with FileLock(str(run/'train.lock'),timeout=0):
            cfg=load_config(run/'config.json');body=cfg['env']['learner_hitbox']
            latest=check_model(run/'latest.pt',CONTRACT);initial=check_model(run/'initial.pt',CONTRACT)
            print(f'Latest selector: {latest["timesteps"]} decisions, SHA256 {latest["sha256"]}',flush=True)
            print('LOADING 1/2: latest selector and Chronos / GalactusV2 / Ripple v1.1',flush=True)
            candidate=Runner(run/'latest.pt',body)
            print('LOADING 2/2: initialization and frozen experts',flush=True)
            baseline=Runner(run/'initial.pt',body)
            (run/'EVAL_STOP').unlink(missing_ok=True)
            try:
                rows,old=match_suite(cfg,candidate,baseline,pairs,seconds,29100001,run/'EVAL_STOP')
            except (EvaluationStopped,KeyboardInterrupt):
                print('EVALUATION_CANCELLED: weights unchanged; no new complete result written. Any existing wdl.json is from an earlier evaluation.',flush=True)
                return
            report=dict(kind='triad_selector_timed_matches',candidate_sha256=latest['sha256'],
                candidate_timesteps=latest['timesteps'],baseline_sha256=initial['sha256'],
                candidate=match_summary(rows),initial=match_summary(old),statistics=paired_statistics(rows,old),trials=rows,baseline_trials=old)
            atomic_json(run/'wdl.json',report)
            print(json.dumps({k:v for k,v in report.items() if k not in ('trials','baseline_trials')},indent=2),flush=True)
            print('SELECTOR_WDL_READY:',run/'wdl.json',flush=True)
    except Timeout as error:
        raise RuntimeError('Selector training is still using this run. Pause with launcher 8, wait for training to exit, then run 7.') from error
