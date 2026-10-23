"""Replay-anchored PPO with a fixed action decoder and independent evaluation."""
from pathlib import Path
from importlib.metadata import version
import copy,math,random,time,shutil,tempfile
import numpy as np
import torch
from torch.nn import functional as F
from replay_rvq.inference import load
from replay_rvq.data import RVQData
from replay_il.train import save
from replay_il.monitor import Monitor
from replay_hybrid.policy import ReturnCritic,fixed_decoder,statistics,gae,clipped_loss
from replay_hybrid.env import World,GAMMA
from replay_hybrid.rollout import collect,tensors
from replay_hybrid.evaluate import evaluate
from slater_v041_core import read_json,atomic_json,sha256,process_lock

ROOT=Path(__file__).resolve().parents[1]


def snapshot_parent(source,root,digest):
    target=root/'source_snapshot'
    if target.exists():return target
    temporary=Path(tempfile.mkdtemp(prefix='.source_snapshot_',dir=root))
    try:
        (temporary/'policy').mkdir();shutil.copy2(source/'protocol.json',temporary/'protocol.json')
        original=torch.load(source/'policy/best.pt',map_location='cpu',weights_only=True)
        payload={key:original[key] for key in ('schema','stage','model','config','protocol_sha256')}
        save(temporary/'policy/best.pt',payload)
        atomic_json(temporary/'policy/selected.json',{'sha256':sha256(temporary/'policy/best.pt'),'original_parent_sha256':digest})
        if sha256(source/'policy/best.pt')!=digest:raise RuntimeError('Parent changed while snapshotting; preserve source and try a new run')
        # Validate the same inference/model contract before publishing snapshot.
        load(temporary)
        temporary.rename(target);return target
    finally:
        if temporary.exists():shutil.rmtree(temporary)


def identity():
    names=[str(p.relative_to(ROOT)) for p in (ROOT/'replay_hybrid').glob('*.py')]
    names+=['replay_rvq/model.py','replay_rvq/data.py','replay_il/model.py','replay_il/train.py',
        'replay_il/monitor.py','replay_rvq/packet.py','replay_rlbot_core.py','slater_v041_core.py']
    return {name:sha256(ROOT/name) for name in sorted(names)}


def verify_protocol(root,prior,current):
    if prior is None:
        atomic_json(root/'protocol.json',current);return
    if prior==current:return
    # One narrowly scoped compatibility update for the original CPU-only
    # traced Nexto adapter. Preserve protocol/checkpoint hashes and all progress.
    old_code={
        'replay_hybrid/nexto.py':'339c48a8328e0913f9ce31b5f4bb3f9c3b5a71f96b10a4a55e568d18f70cad41',
        'replay_hybrid/train.py':'417c67843592c9d9f5ef6474fbb297ab090e0748f55be57aa5ff398a16a98456'}
    before=prior.get('code',{});after=current.get('code',{})
    changed={key for key in before.keys()|after.keys() if before.get(key)!=after.get(key)}
    same_settings={k:v for k,v in prior.items() if k!='code'}=={k:v for k,v in current.items() if k!='code'}
    compatible=bool(changed) and changed<=old_code.keys() and all(before.get(k)==old_code[k] for k in changed)
    record={'fix':'original-nexto-cpu-constants-v1','protocol_sha256':sha256(root/'protocol.json'),
        'code':after,'nexto_device':'cpu'}
    approved=read_json(root/'runtime_compatibility.json')
    if not same_settings or not compatible or approved is not None and approved!=record:
        raise ValueError('Hybrid source/data/settings changed. Preserve this run; use a new name.')
    if approved is None:atomic_json(root/'runtime_compatibility.json',record)
    print('HYBRID_COMPATIBILITY: Nexto CPU adapter fix; existing checkpoints and replay caches preserved',flush=True)


def replay_batch(data,model,rng,device,count=64):
    # One replay per update preserves cache locality; replays are selected by
    # their sample counts. Never use validation/test demonstrations for SGD.
    records=sorted({record for record,_ in data.raw.rows['train']})
    sizes=np.array([data.raw.records[r]['samples'] for r in records],float)
    record=records[int(rng.choice(len(records),p=sizes/sizes.sum()))]
    indexes=rng.choice(int(data.raw.records[record]['samples']),min(count,int(data.raw.records[record]['samples'])),replace=False)
    return data.take([(record,int(i)) for i in indexes],device)


def goal_batch(worlds,rng,device,count=64):
    populated=[world for world in worlds if world.goal_examples]
    if not populated:return None
    samples=[]
    for _ in range(count):
        world=populated[int(rng.integers(len(populated)))];samples.append(world.goal_examples[int(rng.integers(len(world.goal_examples)))])
    return tensors([row[0] for row in samples],device),torch.tensor([row[1] for row in samples],device=device)


def heldout(root,anchor,device,nexto,team_size,games,seconds):
    selected=read_json(root/'policy/selected.json')
    if selected['updates']==0:return False
    prior=read_json(root/'heldout_matches.json',{})
    if prior.get('checkpoint_sha256')==selected['sha256']:return True
    if (root/'pause.flag').exists():return False
    best=load(root,device);print('HYBRID_HELDOUT: independent seeds, full matches; never used for selection',flush=True)
    result=evaluate(best,anchor,device=device,games=games,seconds=seconds,team_size=team_size,seed=1800000,nexto=nexto,
        stop=lambda:(root/'pause.flag').exists())
    if result.get('interrupted'):return False
    result.update(checkpoint_sha256=selected['sha256'],source_sha256=read_json(root/'protocol.json')['source_sha256'],
        improvement_on_tested_pool=result['paired_bootstrap_95pct_interval'][0]>0 and result['by_opponent'].get('nexto',{}).get('paired_goal_difference_per_minute',0.)>=0,
        competitive_strength_verified=False)
    atomic_json(root/'heldout_matches.json',result)
    print('HYBRID_HELDOUT_RESULT:',{key:val for key,val in result.items() if key!='rows'},flush=True)
    return True


def optimize(actor,critic,anchor,actor_optimizer,critic_optimizer,batch,data,worlds,*,device,update,minibatch=128,epochs=3):
    actor.train();actor.codec.eval();critic.train()
    obs=tuple(torch.tensor(batch[key].reshape(-1,*batch[key].shape[2:]),device=device) for key in ('q','kv','mask'))
    codes=torch.tensor(batch['codes'].reshape(-1,4),device=device)
    old_logp=torch.tensor(batch['logp'].reshape(-1),device=device)
    rewards=torch.tensor(batch['rewards'],device=device);values=torch.tensor(batch['values'],device=device)
    next_values=torch.tensor(batch['next_values'],device=device)
    advantage,returns=gae(rewards,values,next_values,torch.tensor(batch['terminated'],device=device),
        torch.tensor(batch['truncated'],device=device),GAMMA)
    advantage=advantage.reshape(-1);returns=returns.reshape(-1)
    raw_advantage_std=float(advantage.std(unbiased=False))
    advantage=(advantage-advantage.mean())/advantage.std(unbiased=False).clamp_min(1e-6)
    rng=np.random.default_rng(20261023+update)
    replay=replay_batch(data,actor,rng,device);outcomes=goal_batch(worlds,rng,device)
    initial={n:p.detach().clone() for n,p in actor.named_parameters() if p.requires_grad}
    totals={key:0. for key in ('policy_loss','return_critic_mse','replay_bc','anchor_kl','next_goal_mse','entropy','approx_kl')}
    updates=0;stopped=False
    for _ in range(epochs):
        order=torch.randperm(len(codes),device=device)
        for start in range(0,len(order),minibatch):
            ids=order[start:start+minibatch];x=tuple(value[ids] for value in obs)
            logp,entropy,_,logits=statistics(actor,x,codes[ids])
            policy_loss,kl=clipped_loss(logp,old_logp[ids],advantage[ids])
            if float(kl.detach())>.03:stopped=True;break
            with torch.no_grad():reference=anchor.teacher_logits(anchor.encode(x),codes[ids]).log_softmax(-1)
            anchor_kl=(reference.exp()*(reference-logits.log_softmax(-1))).sum(-1).mean()
            replay_obs,target,replay_codes,replay_value,bootstrap=replay
            features=actor.encode(replay_obs);teacher=actor.teacher_logits(features,replay_codes)
            ce=F.cross_entropy(teacher.reshape(-1,64),replay_codes.reshape(-1),reduction='none').reshape(-1,4).mean(-1)
            weight=1.+.5*(target[:,:8,5]>.5).any(1).to(ce.dtype)
            bc=(ce*weight).sum()/weight.sum()
            next_goal=(((actor.value(features)-replay_value[:,None])**2)*bootstrap).sum()/bootstrap.sum().clamp_min(1)
            if outcomes is not None:
                outcome_obs,outcome_values=outcomes
                next_goal=next_goal+((actor.value(actor.encode(outcome_obs))-outcome_values[:,None])**2).mean()
            loss=policy_loss-.003*entropy.mean()+.05*bc+.01*anchor_kl+.1*next_goal
            predicted=critic(x);critic_loss=.5*((predicted-returns[ids])**2).mean()
            if not torch.isfinite(loss+critic_loss):raise RuntimeError('Nonfinite hybrid loss; previous checkpoints preserved')
            actor_optimizer.zero_grad(set_to_none=True);loss.backward()
            grad=torch.nn.utils.clip_grad_norm_([p for p in actor.parameters() if p.requires_grad],.5)
            if not torch.isfinite(grad):raise RuntimeError('Nonfinite hybrid actor gradient')
            actor_optimizer.step()
            critic_optimizer.zero_grad(set_to_none=True);critic_loss.backward()
            critic_grad=torch.nn.utils.clip_grad_norm_(critic.parameters(),1.)
            if not torch.isfinite(critic_grad):raise RuntimeError('Nonfinite hybrid critic gradient')
            critic_optimizer.step();updates+=1
            for key,value in (('policy_loss',policy_loss),('return_critic_mse',critic_loss*2),('replay_bc',bc),
                ('anchor_kl',anchor_kl),('next_goal_mse',next_goal),('entropy',entropy.mean()),('approx_kl',kl)):
                totals[key]+=float(value.detach())
        if stopped:break
    change=float(torch.sqrt(sum(((p.detach()-initial[n])**2).sum() for n,p in actor.named_parameters() if n in initial)))
    return {**{key:value/max(updates,1) for key,value in totals.items()},'optimizer_minibatches':updates,
        'kl_stopped_early':stopped,'parameter_change_l2':change,'raw_advantage_std':raw_advantage_std,
        'simulated_outcome_labels':0 if outcomes is None else len(outcomes[1])}


def train(source,root,*,steps=1000000,envs=4,team_size=1,horizon=128,minibatch=128,
          device='auto',wandb_mode='online',evaluate_every=50000,evaluation_games=6,evaluation_seconds=120,
          final_games=12,final_seconds=300,nexto_path=None):
    source=Path(source).resolve();root=Path(root).resolve()
    if root==source or not root.is_relative_to(ROOT/'data/isolated'):raise ValueError('Use a separate child run under data/isolated')
    if not 1<=envs<=16 or team_size not in (1,2,3) or not 1<=horizon<=512 or not 4<=minibatch<=1024 or steps<1 or evaluate_every<1:
        raise ValueError('Invalid hybrid training budget')
    if device=='auto':device='cuda' if torch.cuda.is_available() else 'cpu'
    if device not in ('cpu','cuda') or device=='cuda' and not torch.cuda.is_available():raise ValueError('Requested device unavailable')
    if wandb_mode not in ('online','offline','disabled'):raise ValueError('Invalid W&B mode')
    if not 2<=evaluation_games<=64 or not 1<=evaluation_seconds<=600 or not 2<=final_games<=64 or not 1<=final_seconds<=600:
        raise ValueError('Invalid paired evaluation budget')
    frozen=root/'source_snapshot';existing=read_json(root/'protocol.json',{})
    if existing and existing.get('schema')!='replay-hybrid-training-v1':raise ValueError('Run belongs to another workflow; choose a new hybrid run name')
    using_snapshot=(frozen/'policy/best.pt').is_file() and bool(existing)
    dataset=Path(read_json((root if using_snapshot else source)/'dataset.json')['path']).resolve()
    source_digest=existing['source_sha256'] if using_snapshot else sha256(source/'policy/best.pt')
    source_config=torch.load((frozen if using_snapshot else source)/'policy/best.pt',map_location='cpu',weights_only=True)['config']
    if nexto_path is None:
        default=ROOT/'vendor/nexto/nexto-model.pt';nexto_path=default if default.is_file() else None
    else:
        nexto_path=Path(nexto_path).resolve()
        if not nexto_path.is_file():raise ValueError('Specified Nexto weights do not exist')
    protocol={'schema':'replay-hybrid-training-v1','source_run':str(source),'source_sha256':source_digest,
        'dataset_sha256':sha256(dataset/'manifest.json'),'code':identity(),'config':source_config,
        'envs':envs,'team_size':team_size,'horizon':horizon,'minibatch':minibatch,'gamma':GAMMA,'seed':20261023,
        'actor_lr':1e-5,'critic_lr':3e-4,'replay_bc_weight':.05,'anchor_kl_weight':.01,'next_goal_weight':.1,
        'value_contract':'policy.values predicts discounted next goal; ReturnCritic separately predicts shaped PPO return',
        'decoder':'codec fixed; continuous offset disabled and frozen in child only, maximum initial analogue change 0.05',
        'nexto_path':str(nexto_path) if nexto_path is not None else None,
        'nexto_sha256':sha256(nexto_path) if nexto_path is not None else None,
        'evaluate_every':evaluate_every,'evaluation_games':evaluation_games,'evaluation_seconds':evaluation_seconds,
        'final_games':final_games,'final_seconds':final_seconds,
        'runtime':{name:version(name) for name in ('torch','numpy','rlgym','rlgym-rocket-league','rlgym-tools','rocketsim')}}
    root.mkdir(parents=True,exist_ok=True)
    with process_lock(root/'train.lock'):
        prior=read_json(root/'protocol.json')
        verify_protocol(root,prior,protocol)
        atomic_json(root/'dataset.json',{'path':str(dataset)});(root/'pause.flag').unlink(missing_ok=True)
        torch.set_num_threads(2);torch.manual_seed(20261023);random.seed(20261023)
        print('HYBRID_INITIALIZING: validating/snapshotting the parent model; existing weights are preserved',flush=True)
        frozen=snapshot_parent(source,root,source_digest)
        anchor=load(frozen,device);actor=fixed_decoder(copy.deepcopy(anchor));peer=copy.deepcopy(anchor)
        critic=ReturnCritic().to(device)
        atomic_json(root/'model.json',{'actor_parameters':sum(p.numel() for p in actor.parameters()),
            'trainable_actor_parameters':sum(p.numel() for p in actor.parameters() if p.requires_grad),
            'return_critic_parameters':sum(p.numel() for p in critic.parameters()),
            'initialization':'parent replay policy; child offset zeroed to fix PPO action mapping',
            'learning':'simulation PPO plus human replay anchor; not replay-only'})
        actor_optimizer=torch.optim.Adam([p for p in actor.parameters() if p.requires_grad],lr=1e-5)
        critic_optimizer=torch.optim.Adam(critic.parameters(),lr=3e-4)
        resume=root/'training/latest.pt';progress={'steps':0,'updates':0,'next_evaluation':evaluate_every,
            'best_validation_delta':0.,'stale_evaluations':0}
        if resume.exists():
            saved=torch.load(resume,map_location='cpu',weights_only=True)
            if saved['protocol_sha256']!=sha256(root/'protocol.json'):raise ValueError('Hybrid checkpoint identity mismatch')
            actor.load_state_dict(saved['actor']);critic.load_state_dict(saved['critic']);peer.load_state_dict(saved['peer'])
            actor_optimizer.load_state_dict(saved['actor_optimizer']);critic_optimizer.load_state_dict(saved['critic_optimizer'])
            progress=saved['progress'];torch.set_rng_state(saved['torch_rng']);random.setstate(saved['python_rng'])
            if device=='cuda' and saved.get('cuda_rng') is not None:torch.cuda.set_rng_state_all(saved['cuda_rng'])
        for folder in ('policy','training','evaluations'):(root/folder).mkdir(exist_ok=True)
        def document(model):
            return {'schema':'replay-rvq-stage-v1','stage':'policy','model':model.state_dict(),'config':source_config,
                'progress':dict(progress),'protocol_sha256':sha256(root/'protocol.json')}
        def checkpoint():
            save(root/'policy/latest.pt',document(actor))
            save(resume,{'actor':actor.state_dict(),'critic':critic.state_dict(),'peer':peer.state_dict(),
                'actor_optimizer':actor_optimizer.state_dict(),'critic_optimizer':critic_optimizer.state_dict(),
                'progress':dict(progress),'protocol_sha256':sha256(root/'protocol.json'),
                'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all() if device=='cuda' else None,
                'python_rng':random.getstate()})
            atomic_json(root/'progress.json',progress)
        if not resume.exists():
            save(root/'policy/best.pt',document(actor))
            atomic_json(root/'policy/selected.json',{'sha256':sha256(root/'policy/best.pt'),'updates':0,
                'validation':{'paired_goal_difference_per_minute':0.,'competitive_strength_verified':False},
                'note':'Initialization only; parent offset disabled in child. No improvement verified.'})
            checkpoint()
        nexto=None
        if protocol['nexto_sha256'] is not None:
            from replay_hybrid.nexto import NextoOpponent
            nexto=NextoOpponent(nexto_path,device=device)
            print('HYBRID_NEXTO: cpu | original traced opponent; learning model remains on',device,flush=True)
        if progress['steps']>=steps or progress['stale_evaluations']>=6:
            complete=heldout(root,anchor,device,nexto,team_size,final_games,final_seconds)
            selected=read_json(root/'policy/selected.json')
            atomic_json(root/'status.json',{'progress':progress,'paused':(root/'pause.flag').exists(),'finished':True,
                'selected_improved_in_validation':selected['updates']>0,'heldout_pending':selected['updates']>0 and not complete,
                'competitive_strength_verified':False})
            print('HYBRID_COMPLETE:',progress,flush=True);return root
        print('HYBRID_DATA: verifying existing cached shard hashes, no replay parsing',flush=True)
        data=RVQData(dataset,root/'labels');data.use_codec(actor.codec,source_digest,device)
        kinds=('source','source','chaser','peer','peer')+(('nexto','nexto') if nexto is not None else ())
        print('HYBRID_READY:',device,'| worlds',envs,'| team size',team_size,'| opponents',sorted(set(kinds)),flush=True)
        print('Hybrid is replay-anchored RL. Pausing preserves completed updates; worlds reset on resume.',flush=True)
        worlds=[];monitor=None
        try:
            worlds=[World(20261023+i*7919+progress['steps']*101,team_size,opponents=kinds) for i in range(envs)]
            monitor=Monitor(root/'training',{'mode':wandb_mode,'project':'slater-replay-hybrid','entity':''},protocol,prompt=True)
            while progress['steps']<steps and progress['stale_evaluations']<6:
                started=time.perf_counter();remaining=math.ceil((steps-progress['steps'])/(envs*team_size))
                batch,episodes=collect(actor,critic,worlds,{'source':anchor,'peer':peer},horizon=min(horizon,remaining),
                    device=device,nexto=nexto,stop=lambda:(root/'pause.flag').exists())
                if batch is None:break
                count=int(np.prod(batch['rewards'].shape));progress['steps']+=count;progress['updates']+=1
                metrics=optimize(actor,critic,anchor,actor_optimizer,critic_optimizer,batch,data,worlds,
                    device=device,update=progress['updates'],minibatch=minibatch)
                if metrics['optimizer_minibatches']==0 or not metrics['parameter_change_l2']>0:
                    raise RuntimeError('No actor weights updated; previous checkpoints preserved. Inspect hybrid loss/likelihood diagnostics.')
                metrics.update(episodes);metrics.update(controlled_decisions=count,samples_per_second=count/(time.perf_counter()-started))
                if progress['updates']%100==0:peer.load_state_dict(actor.state_dict())
                monitor.emit(progress['updates'],'hybrid_update',{'train':{'update':progress['updates'],**metrics},'learning':{'controlled_decisions':progress['steps']}})
                print('HYBRID_UPDATE:',progress['updates'],'steps',progress['steps'],'/',steps,metrics,flush=True)
                paused=(root/'pause.flag').exists()
                if not paused and progress['steps']>=progress['next_evaluation']:
                    print('HYBRID_VALIDATION: paired fixed-seed matches, greedy policy, no search',flush=True)
                    result=evaluate(actor,anchor,device=device,games=evaluation_games,seconds=evaluation_seconds,team_size=team_size,nexto=nexto,
                        stop=lambda:(root/'pause.flag').exists())
                    if result.get('interrupted'):checkpoint();break
                    atomic_json(root/'evaluations'/f'validation_{progress["updates"]:06d}.json',result)
                    delta=result['paired_goal_difference_per_minute']
                    nexto_delta=result['by_opponent'].get('nexto',{}).get('paired_goal_difference_per_minute',0.)
                    if delta>progress['best_validation_delta']+.05 and nexto_delta>=0:
                        progress['best_validation_delta']=delta;progress['stale_evaluations']=0
                        save(root/'policy/best.pt',document(actor))
                        atomic_json(root/'policy/selected.json',{'sha256':sha256(root/'policy/best.pt'),'updates':progress['updates'],
                            'validation':result,'competitive_strength_verified':False})
                    else:progress['stale_evaluations']+=1
                    progress['next_evaluation']=progress['steps']+evaluate_every
                    monitor.emit(progress['updates'],'validation',{'evaluation':result})
                    print('HYBRID_VALIDATION_RESULT:',{key:val for key,val in result.items() if key!='rows'},flush=True)
                    checkpoint()
                if progress['updates']%5==0 or paused or progress['steps']>=steps:checkpoint()
                if paused:break
            checkpoint()
            finished=progress['steps']>=steps or progress['stale_evaluations']>=6
            selected=read_json(root/'policy/selected.json')
            complete=heldout(root,anchor,device,nexto,team_size,final_games,final_seconds) if finished else False
            atomic_json(root/'status.json',{'progress':progress,'paused':(root/'pause.flag').exists(),
                'finished':finished,'selected_improved_in_validation':selected['updates']>0,
                'heldout_pending':finished and selected['updates']>0 and not complete,'competitive_strength_verified':False})
            print('HYBRID_SAVED:',root,flush=True)
        finally:
            for world in worlds:world.close()
            if monitor is not None:monitor.close()
    return root
