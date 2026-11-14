"""Learned ground-driving warm start, physical skill tests, then normal PPO.
The analytic tutor labels training data only. Deployment uses the network alone.
"""
import copy,json,math,random,time
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from functools import lru_cache
from .runtime import ROOT,atomic_json,save_checkpoint,config,device,batch,sha,source_hashes
from .model import ActorCritic
from .observation import encode,ACTIONS
from .train import load,lock_run

GROUND=np.flatnonzero((ACTIONS[:,0]==1)&(ACTIONS[:,5]==0)&(ACTIONS[:,7]==0))

@lru_cache(maxsize=8)
def action_tensor(device_name):
    return torch.as_tensor(ACTIONS,device=torch.device(device_name))

def tutor(tokens,legal):
    """Ground pure-pursuit labels in the exact exported ego coordinate frame."""
    x=tokens[:,1,:3]*4096
    bv=(tokens[:,1,3:6]+tokens[:,0,3:6])*2300
    distance=torch.linalg.vector_norm(x[:,:2],dim=-1)
    horizon=(distance/1800).clamp(0,.5)
    target=x+bv*horizon[:,None]
    angle=torch.atan2(target[:,1],target[:,0])
    steer=torch.where(angle>.10,1.,torch.where(angle<-.10,-1.,0.))
    boost=(angle.abs()<.15)&(distance>850)&(tokens[:,0,15]>.05)
    desired=torch.stack((torch.ones_like(steer),steer,torch.zeros_like(steer),steer,torch.zeros_like(steer),torch.zeros_like(steer),boost.float(),torch.zeros_like(steer)),dim=-1)
    table=action_tensor(str(tokens.device))
    cost=((desired[:,None]-table[None])**2).sum(-1)
    return cost.masked_fill(~legal,1e6).argmin(-1)

def random_world(rng,n,moving=True):
    w=np.zeros((n,3,32),np.float32);w[:,:,9]=1;w[:,:,14]=1
    w[:,0,:2]=rng.uniform([-2400,-3200],[2400,3200],(n,2));w[:,0,2]=94
    if moving:w[:,0,3:5]=rng.uniform(-700,700,(n,2))
    for a in (1,2):
        angle=rng.uniform(-np.pi,np.pi,n);d=rng.uniform(250,2200,n);yaw=angle+rng.uniform(-1.8,1.8,n)
        w[:,a,0]=np.clip(w[:,0,0]-np.cos(angle)*d,-3500,3500);w[:,a,1]=np.clip(w[:,0,1]-np.sin(angle)*d,-4500,4500);w[:,a,2]=17
        w[:,a,9:12]=np.stack((np.cos(yaw),np.sin(yaw),np.zeros(n)),axis=-1)
        speed=rng.uniform(0,1600,n);w[:,a,3:6]=w[:,a,9:12]*speed[:,None]
        w[:,a,15]=rng.uniform(0,100,n);w[:,a,16]=1
        w[:,a,21:29]=ACTIONS[rng.integers(0,90,n)]
    return w

def driving_data(cfg,n=8192,seed=123):
    rng=np.random.default_rng(seed);env=batch(cfg,n=1);loc=env.pad_locations()
    w=random_world(rng,n);pads=np.zeros((n,34,2),np.float32);pads[:,:,0]=1
    ob,lm=encode(w,pads,loc);return ob.reshape(-1,43,40),lm.reshape(-1,90)

def drills(model,cfg,seed=8107001,n=32,seconds=6):
    """Fresh controlled states; success is an actual RocketSim contact, not CE."""
    dev=next(model.parameters()).device;cfg=copy.deepcopy(cfg);cfg['episode_seconds']=seconds+5;cfg['no_touch_seconds']=seconds+5
    results={};model.eval()
    for name,moving in [('stationary',False),('moving',True)]:
        env=batch(cfg,n=n,seed=seed,kickoffs=True);raw=env.observe();world=random_world(np.random.default_rng(seed),n,moving)
        # Park the other car away. Test each side separately on matched public scenes.
        rates=[];times=[]
        for color in (0,1):
            world=random_world(np.random.default_rng(seed),n,moving)
            other=2 if color==0 else 1;world[:,other,:3]=[3600,4500 if color==0 else -4500,17];world[:,other,3:6]=0
            for j in range(n):env.set_ground(j,world[j])
            raw=env.observe();seen=np.zeros(n,bool);first=np.full(n,seconds,np.float64)
            loc=env.pad_locations()
            with torch.no_grad():
                for k in range(int(seconds*120/cfg['tick_skip'])):
                    ob,lm=encode(raw['world'],raw['pads'],loc);x=torch.as_tensor(ob[:,color],device=dev);l=torch.as_tensor(lm[:,color],device=dev)
                    ac=np.full((n,2),8,np.int64)
                    ac[:,color]=model(x,l)[0].argmax(-1).cpu().numpy()
                    raw=env.step(ac);hit=raw['info'][:,1+color]>0;first[hit&~seen]=(k+1)*cfg['tick_skip']/120;seen|=hit
            rates.append(float(seen.mean()));times.append(float(first.mean()))
        results[name]={'blue_contact_fraction':rates[0],'orange_contact_fraction':rates[1],'contact_fraction':sum(rates)/2,'capped_mean_contact_seconds':sum(times)/2}
    return results

class TutorModel(torch.nn.Module):
    def __init__(self):super().__init__();self.dummy=torch.nn.Parameter(torch.zeros(()))
    def forward(self,x,l):
        a=tutor(x,l);logits=torch.full((len(x),90),-100.,device=x.device);logits.scatter_(1,a[:,None],100.);return logits,torch.zeros(len(x),device=x.device)

def checkpoint(model,opt,cfg,steps,base=None):
    return {'format':'attentionforge-checkpoint-v1','config':cfg,'model':model.state_dict(),'optimizer':opt.state_dict(),'learning_transitions':0,'updates':0,'history':[],'history_scores':{},'wandb_id':None,'python_rng':random.getstate(),'numpy_rng':np.random.get_state(),'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,'bootstrap_updates':steps,'training_wall_seconds':0,'physics_ticks':0,'env_decisions':0}

def prepare(folder,updates=900):
    folder=Path(folder)
    if (folder/'latest.pt').exists():return
    folder.mkdir(parents=True,exist_ok=True);(folder/'STOP').unlink(missing_ok=True)
    from . import _attention_native as native
    if getattr(native,'reward_version',0)<2:raise RuntimeError('Install the Skills update native module and restart Python')
    base=config(ROOT/'laptop_tuned.json' if (ROOT/'laptop_tuned.json').exists() else ROOT/'laptop_config.json');cfg=copy.deepcopy(base)
    cfg['version']='attentionforge-skills-v1'
    cfg['rewards']={'profile':'skills_v1','goal':10.,'approach':1.,'touch':1.,'control_progress':0.}
    cfg['network']['critic_detach']=True
    cfg['ppo'].update(learning_rate=.00002,entropy=.005)
    cfg['skills']={'version':1,'auxiliary_initial':.1,'auxiliary_decay_transitions':10000000,'bootstrap_updates':updates,'auto_evaluate_every':250000}
    atomic_json(folder/'config.json',cfg);dev=device(cfg);torch.set_num_threads(cfg['torch_threads'])
    random.seed(cfg['seed']);np.random.seed(cfg['seed']);torch.manual_seed(cfg['seed'])
    model=ActorCritic(**cfg['network']).to(dev);opt=torch.optim.Adam(model.parameters(),lr=.0003,eps=1e-5)
    progress=folder/'bootstrap.pt';start=0
    if progress.exists():
        saved=load(progress,dev);model.load_state_dict(saved['model']);opt.load_state_dict(saved['optimizer']);start=saved['bootstrap_updates']
        random.setstate(saved['python_rng']);np.random.set_state(saved['numpy_rng']);torch.set_rng_state(saved['torch_rng'].cpu())
    ob,lm=driving_data(cfg)
    # Store compact synthetic data on host; a minibatch is the only GPU copy.
    before=drills(model,cfg,n=16);atomic_json(folder/'skills_before.json',before)
    print('WARM_START: learning ground approaches; no scripted controls are used in deployment. Ctrl+C saves bootstrap progress.',flush=True)
    completed=start
    try:
        model.train()
        for k in range(start,updates):
            if (folder/'STOP').exists():raise KeyboardInterrupt
            ix=np.random.randint(0,len(ob),256);x=torch.as_tensor(ob[ix],device=dev);l=torch.as_tensor(lm[ix],device=dev)
            labels=tutor(x,l);logits,_=model(x,l)
            logp=logits.log_softmax(-1)
            diversity=-(logp.masked_fill(~l,0).sum(-1)/l.sum(-1)).mean()
            loss=.97*F.cross_entropy(logits,labels)+.03*diversity # legal-only smoothing preserves exploration
            opt.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.,error_if_nonfinite=True);opt.step();completed=k+1
            if completed%100==0:
                save_checkpoint(progress,checkpoint(model,opt,cfg,completed));print('WARM_START_UPDATE:',completed,'/',updates,'loss:',round(float(loss.detach()),4),flush=True)
        after=drills(model,cfg,n=32)
        quality={'before':before,'after':after,'updates':completed,'scope':'Ground-contact drill results; not match strength. Synthetic analytic labels, not human replays.'};atomic_json(folder/'bootstrap_quality.json',quality)
        print('GROUND_CONTACT_RESULTS:',json.dumps(quality),flush=True)
        # Preserve the candidate even if it fails its physical gate; never silently
        # call a failed warm start a successful bot or begin an endless PPO run.
        save_checkpoint(progress,checkpoint(model,opt,cfg,completed))
        if min(v[k] for v in after.values() for k in ('blue_contact_fraction','orange_contact_fraction'))<.45:raise RuntimeError('Warm start failed physical contact gate. bootstrap.pt and quality report preserved; PPO not started.')
        # PPO optimizer starts fresh deliberately: CE and PPO are different phases.
        from .execution import make_optimizer
        ppo_opt,_=make_optimizer(model,cfg,dev)
        with torch.no_grad():model.critic.weight.zero_();model.critic.bias.zero_()
        payload=checkpoint(model,ppo_opt,cfg,completed);save_checkpoint(folder/'latest.pt',payload);save_checkpoint(folder/'reward_parent.pt',payload);save_checkpoint(folder/'best_contact.pt',payload)
        atomic_json(folder/'best_contact.json',{'minimum_contact_fraction':min(x[k] for x in after.values() for k in ('blue_contact_fraction','orange_contact_fraction')),'learning_transitions':0,'quality':after})
        atomic_json(folder/'provenance.json',{'initialization':'random attention then analytic ground-driving BC','bootstrap_updates':completed,'PPO_optimizer':'fresh at phase boundary','source_run':'No old run overwritten','quality':quality,'bootstrap_data_seed':123,'initialization_seed':cfg['seed'],'public_state_contract':'attentionforge-v1-raw32-delay1','source_hashes':source_hashes()})
    except KeyboardInterrupt:
        save_checkpoint(progress,checkpoint(model,opt,cfg,completed));print('BOOTSTRAP_PAUSED: resume the same launcher.',flush=True);return


def run(folder):
    folder=Path(folder)
    with lock_run(folder):prepare(folder)
    if not (folder/'latest.pt').is_file():return
    from .train import train
    while True:
        train(config(folder/'config.json'),folder)
        flag=folder/'skill_regression.json'
        if not flag.exists():break
        record=json.loads(flag.read_text());flag.unlink();state=load(folder/'latest.pt',torch.device('cpu'));prior=load(folder/'best_contact.pt',torch.device('cpu'))
        attempt=int(state.get('recovery_attempts',0))+1
        archive=folder/'regressions';archive.mkdir(exist_ok=True)
        import shutil
        shutil.copy2(folder/'latest.pt',archive/f'failed_{state["learning_transitions"]:016d}.pt')
        atomic_json(archive/f'failed_{state["learning_transitions"]:016d}.config.json',state['config'])
        prior['history']=state['history'];prior['history_scores']=state.get('history_scores',{});prior['learning_transitions']=state['learning_transitions'];prior['updates']=state['updates'];prior['training_wall_seconds']=state['training_wall_seconds'];prior['physics_ticks']=state['physics_ticks'];prior['env_decisions']=state['env_decisions'];prior['wandb_id']=state.get('wandb_id');prior['recovery_attempts']=attempt
        rate=max(.000003,state['config']['ppo']['learning_rate']*.5);prior['config']['ppo']['learning_rate']=rate
        for g in prior['optimizer']['param_groups']:g['lr']=rate
        save_checkpoint(folder/'latest.pt',prior);atomic_json(folder/'config.json',prior['config'])
        with (folder/'recovery.jsonl').open('a') as f:f.write(json.dumps({'attempt':attempt,'reason':record,'restored_from':'best_contact.pt','consumed_transition_counter':state['learning_transitions'],'learning_rate':rate})+'\n')
        print('RECOVERY: restored retained contact policy, archived failed checkpoint; reduced LR to',rate,flush=True)
        if attempt>=3:
            print('RECOVERY_LIMIT: paused with restored contact policy. Create a report; no endless retry loop.',flush=True);break


def monitor(model,cfg,folder,count):
    model.eval();quality=drills(model,cfg,seed=880001,n=16)
    score=min(x[k] for x in quality.values() for k in ('blue_contact_fraction','orange_contact_fraction'))
    record={'learning_transitions':count,'quality':quality,'minimum_contact_fraction':score,'purpose':'Repeated validation, not final held-out testing'}
    with (folder/'skill_validation.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
    bestfile=folder/'best_contact.json';best=json.loads(bestfile.read_text()) if bestfile.exists() else {'minimum_contact_fraction':0.}
    if score>best['minimum_contact_fraction']:
        import shutil
        shutil.copy2(folder/'latest.pt',folder/'best_contact.pt');atomic_json(bestfile,record)
    print('SKILL_VALIDATION:',json.dumps(record),flush=True)
    model.train()
    okay=score>=max(.30,best['minimum_contact_fraction']*.6)
    if not okay:atomic_json(folder/'skill_regression.json',record)
    if okay and count//2000000>(count-cfg['skills']['auto_evaluate_every'])//2000000:
        from .evaluate import evaluate
        evaluate(folder,rounds=100,seconds=60,opponent=folder/'reward_parent.pt')
    return okay


def menu(run='skills01'):
    folder=ROOT/'runs'/run
    while True:
        print('\nATTENTIONFORGE SKILLS — '+run+'\n1 Start / resume (automatic warm start, then PPO)\n2 Watch latest vs frozen warm-start parent\n3 Physical contact diagnostics\n4 Create report ZIP\n5 Export bot\n6 Longer match evaluation vs parent\n7 Request pause\n8 Watch current self-play\n0 Exit',flush=True)
        try:
            choice=input('Choose: ').strip()
            if choice=='0':return
            if choice=='1':globals()['run'](folder)
            elif choice in ('2','8'):
                from .cli import watch
                watch(config(),folder,opponent=folder/'reward_parent.pt' if choice=='2' else None)
            elif choice=='3':
                from .cli import policy
                import secrets
                model,s=policy(folder,device(config(folder/'config.json')));result=drills(model,s['config'],seed=secrets.randbelow(1000000000)+2000000000,n=64)
                atomic_json(folder/f'contact_test_{time.time_ns()}.json',result);print(json.dumps(result,indent=2))
            elif choice=='4':
                from .cli import report
                report(folder)
            elif choice=='5':
                from .cli import export
                export(folder)
            elif choice=='6':
                from .evaluate import evaluate
                evaluate(folder,rounds=500,seconds=180,opponent=folder/'reward_parent.pt')
            elif choice=='7':
                if not folder.exists():raise FileNotFoundError(folder)
                (folder/'STOP').write_text('pause\n');print('Wait for PAUSED_AND_SAVED in trainer console.')
        except KeyboardInterrupt:print('Interrupted; completed checkpoints preserved.',flush=True)
        except Exception as ex:
            print(type(ex).__name__+': '+str(ex),flush=True)
            print('Operation failed; keep this output. Existing runs were preserved.',flush=True)
