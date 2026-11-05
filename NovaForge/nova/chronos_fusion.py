"""Experimental multi-teacher probability fusion and a single-network distillation.

Different tensor shapes cannot be weight-averaged. Ripple's 276 actions are
projected to the 90-action Chronos table, preserving jump/boost where possible.
Its longer reaction queue is approximated with held controls; benchmark this
experiment against original Chronos before trusting it.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import numpy as np
import torch
from filelock import FileLock
from .core import ROOT,atomic_json,as_v1
from .giga_teachers import TABLE,GigaNetwork,BallForecast,build_features,native_action_mask
from .teachers import Ripple,verify_teacher


def softmax(logits,mask=None):
    values=np.asarray(logits,dtype=np.float64)
    if mask is not None:values=np.where(mask,values,-np.inf)
    if not np.isfinite(values).any():raise ValueError('No finite teacher proposal')
    values=np.exp(values-np.max(values));return values/values.sum()


def project_probabilities(probabilities,source_table,mirror,mask):
    table=np.asarray(source_table,dtype=np.float32).copy()
    if mirror:table[:,[1,3,4]]*=-1
    distance=np.square(table[:,None,:]-TABLE[None,:,:])*np.array([1,1,1,1,1,8,8,2])
    distance=distance.sum(-1);distance[:,~mask]=np.inf
    destination=distance.argmin(-1)
    result=np.bincount(destination,weights=probabilities,minlength=90).astype(np.float32)
    result[~mask]=0
    return result/result.sum()


class TeacherFusion:
    def __init__(self):
        # Initialize the packaged Soccar meshes before creating ball predictors.
        from rlgym.rocket_league.sim import RocketSimEngine
        setup=RocketSimEngine();setup.close()
        self.chronos=GigaNetwork(verify_teacher('chronos'),'chronos')
        self.galactus=GigaNetwork(verify_teacher('galactus'),'galactus')
        self.forecast=BallForecast();self.ripple=Ripple()
        self.ripple_table=self.ripple.parser.parser.lookup_table
        self.weights=np.array([.5,.25,.25])
    def reset(self,state,agent,rng):
        self.agent=agent;self.rng=rng;self.forecast.reset();self.ripple.reset(state,agent,rng)
    def probabilities(self,state,previous,chronos_features,mirror):
        components=self.distributions(state,previous,chronos_features,mirror)
        target=np.sum(self.weights[:,None]*components,axis=0).astype(np.float32)
        return target/target.sum()

    def distributions(self,state,previous,chronos_features,mirror):
        mask=native_action_mask(state.cars[self.agent])
        with torch.inference_mode():
            chronos=self.chronos(torch.from_numpy(chronos_features)[None,:])[0].numpy()
            galactus,_=build_features(state,self.agent,previous,self.rng,'galactus',self.forecast.samples(state))
            galactus=self.galactus(torch.from_numpy(galactus)[None,:])[0].numpy()
        legacy=as_v1(state,self.agent)
        self.ripple.queue[:]=previous
        self.ripple.obs.prev_prev_actions[:1]=previous
        self.ripple.obs.pre_step(legacy,controlled_count=1,elapsed_ticks=8)
        ripple=self.ripple.session.run(['logits'],dict(zip(('main','others','ball','actions','boosts'),self.ripple.obs.current_obs)))[0][0]
        chronos_command=TABLE[int(np.where(mask,chronos,-np.inf).argmax())].copy()
        if mirror:chronos_command[[1,3,4]]*=-1
        self.native_proposals=np.stack((chronos_command,
            TABLE[int(np.where(mask,galactus,-np.inf).argmax())].copy(),
            self.ripple_table[int(np.argmax(ripple))].copy())).astype(np.float32)
        p0=softmax(chronos,mask)
        p1=project_probabilities(softmax(galactus,native_action_mask(state.cars[self.agent])),TABLE,mirror,mask)
        p2=project_probabilities(softmax(ripple),self.ripple_table,mirror,mask)
        components=np.stack((p0,p1,p2)).astype(np.float32)
        if not np.isfinite(components).all():raise ValueError('Nonfinite teacher fusion')
        return components

    def proposals(self,state,previous,chronos_features,mirror):
        self.distributions(state,previous,chronos_features,mirror)
        return self.native_proposals.copy()


class FusionRunner:
    def __init__(self):self.teacher=TeacherFusion()
    def bind(self,env):
        self.env=env;self.teacher.reset(env.arena.state,env.arena.agent,np.random.default_rng(271))
    def action(self,obs):
        env=self.env
        return int(self.teacher.probabilities(env.arena.state,env.previous,obs[:225],env.mirror).argmax())


def combine_command(args):
    from .training import load_config,prepare_config
    from .chronos import ChronosEnv,CHRONOS_CONTRACT,ChronosPPO
    from .chronos_training import new_chronos_model,ChronosCallback,recover_chronos
    from .chronos_guard import ensure_champion
    from .tracking import Tracker
    from .core import sha256
    from .models import save_ppo
    torch.set_num_threads(1)
    run=(ROOT/'runs'/args.run).resolve()
    if run.parent!=(ROOT/'runs').resolve():raise ValueError('Invalid run name')
    run.mkdir(parents=True,exist_ok=True)
    with FileLock(str(run/'train.lock'),timeout=0):
        cfg=prepare_config(load_config(ROOT/'configs/chronos.json'));cfg['trainer']='chronos_ppo_v1'
        state_path=run/'fusion_state.json'
        saved=json.loads(state_path.read_text()) if state_path.exists() else {}
        if (run/'config.json').exists() and not state_path.exists():raise ValueError('Existing run is not a fusion experiment')
        if saved.get('phase')=='complete':
            (run/'STOP').unlink(missing_ok=True)
            print('FUSION_ALREADY_COMPLETE: resume PPO with the training launcher');return
        env=ChronosEnv(cfg,opponent='galactus');tracker=Tracker(run,cfg,mode='off');callback=None;model=None
        try:
            model=ChronosPPO.load(recover_chronos(run),env=env,device=cfg['device']) if saved else new_chronos_model(cfg,env)
            if not saved:
                atomic_json(run/'config.json',cfg)
                atomic_json(run/'provenance.json',dict(contract=CHRONOS_CONTRACT,teacher_lock_sha256=sha256(ROOT/'teachers.lock.json'),
                    initialization='Chronos plus bounded multi-teacher probability distillation'))
                atomic_json(state_path,dict(phase='collect_fit',decisions=0))
            from stable_baselines3.common.logger import configure
            model.set_logger(configure(str(run/'logs/fusion'),['stdout','csv']))
            callback=ChronosCallback(run,cfg,tracker,False);callback.init_callback(model);callback.persist(force=True)
            ensure_champion(run);(run/'STOP').unlink(missing_ok=True)
            teacher=TeacherFusion();collected=max(int(saved.get('decisions',0)),int(model.num_timesteps));buffer=[]
            obs,_=env.reset(seed=271+collected);teacher.reset(env.arena.state,env.arena.agent,np.random.default_rng(271+collected))
            def fit_buffer():
                if not buffer:return
                x=torch.as_tensor(np.stack([r[0] for r in buffer]),device=model.device)
                target=torch.as_tensor(np.stack([r[1] for r in buffer]),device=model.device)
                before=copy.deepcopy(model.policy.actor.state_dict())
                model.policy.optimizer.param_groups[0]['lr']=2e-6
                logits=model.policy.logits(x);loss=torch.nn.functional.kl_div(torch.log_softmax(logits,-1),target,reduction='batchmean')+.2*model.policy.anchor_kl(x)
                if not torch.isfinite(loss):raise FloatingPointError('Invalid distillation loss')
                model.policy.optimizer.zero_grad(set_to_none=True);loss.backward()
                torch.nn.utils.clip_grad_norm_(model.policy.actor.parameters(),.5,error_if_nonfinite=True)
                model.policy.optimizer.step()
                with torch.no_grad():kl=float(model.policy.anchor_kl(x))
                if not np.isfinite(kl) or kl>.05:
                    model.policy.actor.load_state_dict(before);model.policy.optimizer.state.clear()
                buffer.clear()
            while collected<args.samples and not (run/'STOP').exists():
                probabilities=teacher.probabilities(env.arena.state,env.previous,obs[:225],env.mirror)
                buffer.append((obs.copy(),probabilities))
                action=int(model.predict(obs,deterministic=True)[0])
                obs,_,terminal,truncated,_=env.step(action);collected+=1;model.num_timesteps=collected
                if len(buffer)>=256:fit_buffer()
                if terminal or truncated:
                    # Rotate all four frozen opponents; the learner supplies reached states.
                    env.arena.forced_opponent=('chronos','ripple','galactus','nexto')[(collected//1000)%4]
                    obs,_=env.reset();teacher.reset(env.arena.state,env.arena.agent,np.random.default_rng(271+collected))
                if collected%4096==0:
                    callback.persist(force=True,replace=True)
                    atomic_json(state_path,dict(phase='collect_fit',decisions=collected))
                    print('FUSION_DISTILL_DECISIONS:',collected,flush=True)
            fit_buffer()
            model.policy.optimizer.state.clear() # PPO starts without distillation momentum.
            callback.persist(force=True,replace=collected>0)
            atomic_json(state_path,dict(phase='complete' if collected>=args.samples else 'collect_fit',decisions=collected))
            print('FUSION_SAVED:',run,'decisions',collected,flush=True)
        except KeyboardInterrupt:
            if model is not None and callback is not None:
                callback.persist(force=True,replace=model.num_timesteps>0)
                atomic_json(state_path,dict(phase='collect_fit',decisions=int(model.num_timesteps)))
                (run/'STOP').touch()
        finally:env.close();tracker.finish('stopped')
