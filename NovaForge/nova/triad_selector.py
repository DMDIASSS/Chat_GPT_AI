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
FOUR_NAMES=NAMES+('fusion',)
FOUR_CONTRACT=dict(name='triad-selector-four-v1',observation=236,actions=list(FOUR_NAMES),decision_ticks=8,hold_decisions=8)
RUNS=ROOT.parent/'triadbot/runs'
TRAINING_SETTINGS=dict(learning_rate=1e-4,n_steps=512,batch_size=256,n_epochs=4,
    gae_lambda=.97,clip_range=.1,ent_coef=.003,target_kl=.02)


def contract_for(names):
    names=tuple(names)
    if names==NAMES:return CONTRACT
    if names==FOUR_NAMES:return FOUR_CONTRACT
    raise ValueError('Supported expert sets are the original three, or those three plus frozen Fusion')


def selector_meta(path):
    data=json.loads(Path(str(path)+'.json').read_text())
    contract=data.get('contract')
    if contract not in (CONTRACT,FOUR_CONTRACT):raise ValueError('Unsupported selector contract')
    return check_model(path,contract)


def fusion_asset(folder,record):
    from .chronos import CHRONOS_CONTRACT
    folder=Path(folder).resolve();path=(folder/record['path']).resolve()
    if not path.is_relative_to(folder):raise ValueError('Frozen Fusion path escapes its bundle')
    meta=check_model(path,CHRONOS_CONTRACT)
    if meta['sha256']!=record['sha256']:raise ValueError('Frozen Fusion teacher changed')
    return path


def teacher_pool(fusion=None):
    if fusion is None:
        from .chronos_fusion import TeacherFusion
        return TeacherFusion()
    from .fusion_teacher import ExpertPool
    return ExpertPool(fusion)


class Context:
    def __init__(self,body='breakout',names=NAMES):
        if body not in ('breakout','octane'):raise ValueError('Unsupported selector body')
        contract_for(names);self.names=tuple(names);self.n=len(names)
        self.body=body;self.last=None;self.remaining=0
    def observation(self,features):
        previous=np.zeros(self.n,np.float32)
        if self.last is not None:previous[self.last]=1
        mask=np.ones(self.n,np.float32) if self.remaining==0 else previous.copy()
        return np.concatenate((features,previous,[self.remaining/8],
            [self.body=='breakout',self.body=='octane'],mask)).astype(np.float32)
    def advance(self,choice):
        if choice not in range(self.n) or (self.remaining and choice!=self.last):raise ValueError('Expert is committed during this option')
        self.remaining=7 if self.remaining==0 else self.remaining-1
        self.last=int(choice)


class SelectorPolicy(ActorCriticPolicy):
    def distribution(self,obs):
        features=self.extract_features(obs);latent=self.mlp_extractor.forward_actor(features)
        logits=self.action_net(latent);mask=obs[:,-self.action_space.n:]>0
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
        path=resolve(path);meta=selector_meta(path);self.names=tuple(meta['contract']['actions']);self.n=len(self.names)
        self.fusion_path=fusion_asset(path.parent,meta['fusion_teacher']) if self.n==4 else None
        if meta['hitbox']!=body:raise ValueError('Selector was trained for a different hitbox')
        if meta['teacher_lock_sha256']!=sha256(ROOT/'teachers.lock.json'):raise ValueError('Selector teacher pins changed')
        self.network=torch.jit.load(str(path),map_location='cpu').eval();self.body=body;self.training_steps=meta['timesteps'];self.reset()
    def reset(self):
        self.context=Context(self.body,self.names);self.last_free_choice_probabilities=None
    def choose(self,features):
        obs=self.context.observation(features)
        with torch.inference_mode():logits=self.network(torch.from_numpy(obs)[None,:])[0].numpy()
        if logits.shape!=(self.n,) or not np.isfinite(logits).all():raise ValueError('Invalid selector output')
        if self.context.remaining==0:
            values=logits.astype(np.float64);values=np.exp(values-values.max());values/=values.sum()
            self.last_free_choice_probabilities=dict(zip(self.names,map(float,values)))
        choice=int(np.where(obs[-self.n:]>0,logits,-np.inf).argmax());self.context.advance(choice)
        return choice

    def status(self):
        return dict(last_free_choice_probabilities=self.last_free_choice_probabilities,
            decisions_until_free_choice=self.context.remaining)


def resolve(path):
    path=Path(path)
    if not path.exists() and len(path.parts)==1:path=RUNS/path
    elif not path.exists() and not path.is_absolute():path=RUNS.parent/path
    if path.is_dir():path=path/'champion.pt'
    selector_meta(path)
    return path


class SelectorEnv(Env):
    def __init__(self,cfg,run=None):
        self.body=cfg['env']['learner_hitbox']
        self.names=tuple(cfg.get('selector_experts',NAMES));contract=contract_for(self.names)
        self.fusion_path=fusion_asset(run,cfg['fusion_teacher']) if len(self.names)==4 else None
        self.inner=ChronosEnv(cfg)
        self.action_space=spaces.Discrete(len(self.names));self.observation_space=spaces.Box(-np.inf,np.inf,(contract['observation'],),np.float32)
        self.teacher=None
    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed)
        if self.teacher is None:
            self.teacher=teacher_pool(self.fusion_path)
        self.features,info=self.inner.reset(seed=seed,options=options);self.context=Context(self.body,self.names)
        pool_seed=int(self.np_random.integers(2**32)) if len(self.names)==4 else seed
        self.teacher.reset(self.inner.arena.state,self.inner.arena.agent,np.random.default_rng(pool_seed))
        self.counts=np.zeros(len(self.names),dtype=int)
        return self.context.observation(self.features[:225]),info
    def step(self,choice):
        choice=int(choice);self.context.advance(choice);self.counts[choice]+=1
        controls=self.teacher.proposals(self.inner.arena.state,self.inner.previous,self.features[:225],self.inner.mirror)
        self.features,reward,terminal,truncated,info=self.inner.step_world_controls(controls[choice])
        if 'episode' in info:info['selector_counts']=dict(zip(self.names,map(int,self.counts)))
        return self.context.observation(self.features[:225]),reward,terminal,truncated,info
    def close(self):self.inner.close()


class Runner:
    def __init__(self,path,body):
        self.gate=Gate(path,body)
        self.teacher=teacher_pool(self.gate.fusion_path)
        self.counts=np.zeros(self.gate.n,dtype=np.int64)
    def bind(self,env):
        self.env=env;self.gate.reset()
        self.teacher.reset(env.arena.state,env.arena.agent,np.random.default_rng(271))
    def world_controls(self,obs):
        env=self.env;choice=self.gate.choose(obs[:225])
        self.counts[choice]+=1
        return self.teacher.proposals(env.arena.state,env.previous,obs[:225],env.mirror)[choice]


def save_actor(model,path,body,fusion_teacher=None):
    actor=nn.Sequential(copy.deepcopy(model.policy.mlp_extractor.policy_net),copy.deepcopy(model.policy.action_net)).cpu().eval()
    script=torch.jit.script(actor)
    path=Path(path);temp=path.with_suffix('.tmp.pt');torch.jit.save(script,str(temp));_sync_serialized_file(temp);temp.replace(path)
    names=FOUR_NAMES if model.action_space.n==4 else NAMES
    details=dict(fusion_teacher=fusion_teacher) if len(names)==4 else {}
    write_model_meta(path,contract=contract_for(names),timesteps=int(model.num_timesteps),hitbox=body,
        teacher_lock_sha256=sha256(ROOT/'teachers.lock.json'),**details)


def train(run_name='selector01',steps=32768,forever=True,wandb='online'):
    from .teachers import fetch_teachers
    from .tracking import Tracker,EpisodeWindow,WandBWriter
    fetch_teachers(['chronos','galactus','ripple','nexto']);torch.set_num_threads(1)
    run=(RUNS/run_name).resolve()
    if run.parent!=RUNS.resolve():raise ValueError('Invalid selector run name')
    run.mkdir(parents=True,exist_ok=True)
    with FileLock(str(run/'train.lock'),timeout=0):
        cfg=load_config(run/'config.json' if (run/'config.json').exists() else ROOT/'configs/chronos.json')
        cfg['env'].setdefault('learner_hitbox','breakout');cfg['league']['weights']=dict(cfg.get('selector_opponents',{n:.25 for n in ('chronos','galactus','ripple','nexto')}))
        cfg.update(workers=1,threads=1,device='cpu')
        names=tuple(cfg.get('selector_experts',NAMES));contract=contract_for(names)
        from .research import session
        start=check_model(run/'full.zip',contract)['timesteps'] if (run/'full.zip').exists() else 0
        experiment=session(run,cfg,start)
        atomic_json(run/'config.json',cfg);env=SelectorEnv(cfg,run);tracker=Tracker(run,cfg,mode=wandb,continuous=forever)
        model=None;state='error';before=None;window=EpisodeWindow()
        try:
            if (run/'full.zip').exists():
                check_model(run/'full.zip',contract);model=PPO.load(run/'full.zip',env=env,device='cpu')
            else:
                model=PPO(SelectorPolicy,env,device='cpu',**TRAINING_SETTINGS,
                    gamma=cfg['ppo']['gamma'],seed=cfg.get('selector_seed',271),verbose=1,
                    policy_kwargs=dict(net_arch=dict(pi=[128,128],vf=[128,128])))
                with torch.no_grad():
                    model.policy.action_net.weight.zero_();model.policy.action_net.bias.copy_(torch.tensor([1.]+[0.]*(len(names)-1)))
                save_actor(model,run/'initial.pt',cfg['env']['learner_hitbox'],cfg.get('fusion_teacher'))
                shutil.copy2(run/'initial.pt',run/'champion.pt');shutil.copy2(run/'initial.pt.json',run/'champion.pt.json')
            model.set_random_seed(experiment['seed'])
            model.set_logger(configure(str(run/'logs'/experiment['session_id']),['stdout','csv']))
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
                save_ppo(model,run/'full.zip',contract=contract)
                save_actor(model,run/'latest.pt',cfg['env']['learner_hitbox'],cfg.get('fusion_teacher'))
                if not (run/'STOP').exists() and model.num_timesteps-checks.get('step',0)>=131072:
                    atomic_json(run/'status.json',dict(state='evaluating',timesteps=model.num_timesteps))
                    check_progress(run,cfg,model,checks)
                if not forever:state='finished';break
            else:state='stopped'
            if (run/'STOP').exists():state='stopped'
        except KeyboardInterrupt:state='stopped'
        finally:
            if model is not None:
                save_ppo(model,run/'full.zip',contract=contract)
                save_actor(model,run/'latest.pt',cfg['env']['learner_hitbox'],cfg.get('fusion_teacher'))
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
        atomic_json(run/'research/guard_checks'/f'{int(model.num_timesteps):012d}.json',checks)
        atomic_json(run/'guard.json',checks)
    except EvaluationStopped:pass


def evaluate(run_name='selector01',pairs=2,seconds=60,split='development'):
    from .chronos_league import match_suite,match_summary
    from .chronos_guard import paired_statistics,EvaluationStopped
    from filelock import Timeout
    from .research import SEED_BANKS,evaluation_record
    if split not in SEED_BANKS:raise ValueError('Unknown evaluation split')
    if not isinstance(pairs,int) or not 1<=pairs<=256 or not np.isfinite(seconds) or seconds<=0:raise ValueError('Use 1..256 pairs and positive seconds')
    torch.set_num_threads(1)
    print(f'SELECTOR_EVALUATION_START: Torch threads={torch.get_num_threads()}, games={4*pairs*2*2}, duration={seconds:g}s simulated/game',flush=True)
    run=(RUNS/run_name).resolve()
    if run.parent!=RUNS.resolve():raise ValueError('Invalid run name')
    if not (run/'config.json').exists():raise FileNotFoundError('No selector run. Start launcher 4 and save a checkpoint first.')
    try:
        with FileLock(str(run/'train.lock'),timeout=0):
            cfg=load_config(run/'config.json');body=cfg['env']['learner_hitbox']
            latest=selector_meta(run/'latest.pt');initial=selector_meta(run/'initial.pt')
            print(f'Latest selector: {latest["timesteps"]} decisions, SHA256 {latest["sha256"]}',flush=True)
            print('LOADING 1/2: latest selector and Chronos / GalactusV2 / Ripple v1.1',flush=True)
            candidate=Runner(run/'latest.pt',body)
            print('LOADING 2/2: initialization and frozen experts',flush=True)
            baseline=Runner(run/'initial.pt',body)
            (run/'EVAL_STOP').unlink(missing_ok=True)
            try:
                rows,old=match_suite(cfg,candidate,baseline,pairs,seconds,SEED_BANKS[split],run/'EVAL_STOP')
            except (EvaluationStopped,KeyboardInterrupt):
                print('EVALUATION_CANCELLED: weights unchanged; no new complete result written. Any existing wdl.json is from an earlier evaluation.',flush=True)
                return
            report=dict(kind='triad_selector_timed_matches',candidate_sha256=latest['sha256'],
                candidate_timesteps=latest['timesteps'],baseline_sha256=initial['sha256'],
                candidate=match_summary(rows),initial=match_summary(old),statistics=paired_statistics(rows,old),trials=rows,baseline_trials=old)
            report['split']=split
            report['expert_decisions']={label:dict(zip(getattr(getattr(policy,'gate',None),'names',NAMES),map(int,policy.counts)))
                for label,policy in (('candidate',candidate),('initial',baseline)) if hasattr(policy,'counts')}
            archived=evaluation_record(run,cfg,report,split,SEED_BANKS[split],pairs,seconds)
            print('EVALUATION_ARCHIVE_READY:',archived,flush=True)
            atomic_json(run/'wdl.json',report)
            print(json.dumps({k:v for k,v in report.items() if k not in ('trials','baseline_trials')},indent=2),flush=True)
            print('SELECTOR_WDL_READY:',run/'wdl.json',flush=True)
    except Timeout as error:
        raise RuntimeError('Selector training is still using this run. Pause with launcher 8, wait for training to exit, then run 7.') from error
