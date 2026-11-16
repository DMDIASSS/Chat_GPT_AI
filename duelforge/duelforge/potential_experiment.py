"""Explicit objective fork: retain actor/Adam, reset critic for changed returns."""
import copy,json,os,shutil,tempfile
from pathlib import Path
import torch
from .runtime import ROOT,config,load,save,atomic_json,sha,actor_sha,lock,CONTRACT,validate
from .model import ActorCritic

def fork_potential(source,target,overrides=None):
    source=Path(source);target=Path(target)
    if target.exists():raise FileExistsError('Existing experiment preserved: '+str(target))
    target.parent.mkdir(parents=True,exist_ok=True)
    with lock(source):
        parent=source/'latest.pt';state=load(parent);identity=sha(parent)
        if state.get('contract')!=CONTRACT:raise ValueError('Parent observation/action/timing contract differs')
        before=actor_sha({k:v for k,v in state['model'].items() if k.startswith('actor.')})
        c=copy.deepcopy(state['config']);recipe=config(ROOT/'config_potential.json');c['version']='duelforge-potential-v1';c['objective']='goals_predictive_pbrs_v1';c['rewards']['impulse']=0;c['predictive']=copy.deepcopy(recipe['predictive']);c['bootstrap']={'enabled':False};c['ppo'].pop('entropy_schedule',None);c['ppo']['entropy']=.003;c['ppo']['learning_rate']=.00005
        allowed={'horizon','samples','temperature','intercept_weight','threat_weight','shaping_weight'}
        if set(overrides or {})-allowed:raise ValueError('Unknown potential override')
        c['predictive'].update(overrides or {});c['predictive']['parent_transitions']=state['learning_transitions'];validate(c)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(c['seed']+49);fresh=ActorCritic(c['width'])
        for name,value in fresh.state_dict().items():
            if name.startswith('critic.'):state['model'][name]=value.clone()
        names=[name for name,_ in fresh.named_parameters()];ids=[i for group in state['optimizer']['param_groups'] for i in group['params']]
        if len(ids)!=len(names):raise ValueError('Optimizer parameter mapping differs; no guessed conversion')
        for name,index in zip(names,ids):
            if name.startswith('critic.'):state['optimizer']['state'].pop(index,None)
        for group in state['optimizer']['param_groups']:group['lr']=c['ppo']['learning_rate']
        state['config']=c;state['wandb_id']=None
        after=actor_sha({k:v for k,v in state['model'].items() if k.startswith('actor.')});assert before==after
        stage=Path(tempfile.mkdtemp(prefix='.potential_fork_',dir=target.parent))
        try:
            for name in state.get('history',[]):
                if Path(name).name!=name:raise ValueError('Unsafe history path')
                (stage/'history').mkdir(exist_ok=True);shutil.copy2(source/'history'/name,stage/'history'/name)
            shutil.copy2(parent,stage/'initial.pt');save(stage/'latest.pt',state);atomic_json(stage/'config.json',c)
            atomic_json(stage/'baseline.json',{'label':'frozen trained '+source.name+' parent','checkpoint_sha256':identity,'learning_transitions':state['learning_transitions']})
            atomic_json(stage/'provenance.json',{'parent_run':source.name,'parent_checkpoint_sha256':identity,'parent_actor_sha256':before,'actor_exactly_preserved':True,'actor_adam_preserved':True,'critic_reinitialized':True,'critic_adam_cleared':True,'counters_preserved':True,'objective':'goal differential + stationary bounded interception/threat PBRS; no touch, speed or approach event rewards','original_run_unchanged':True})
            os.rename(stage,target)
        finally:
            if stage.exists():shutil.rmtree(stage)
    return target

def start(minutes=60,max_updates=None):
    from .train import train
    target=ROOT/'runs/potential01'
    if not target.exists():fork_potential(ROOT/'runs/duel02',target)
    c=load(target/'latest.pt')['config']
    if not c.get('predictive',{}).get('enabled'):raise ValueError('Existing potential01 uses another objective; preserved')
    print('POTENTIAL_EXPERIMENT: existing duel02 actor fork; trained parent is the evaluation baseline. No direct touch/speed/flip bonus. Critic reset for new returns.',flush=True)
    return train(target,minutes=minutes,max_updates=max_updates)
