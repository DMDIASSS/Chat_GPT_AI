"""Batched neural decisions; real simulator inputs for every car."""
import numpy as np
import torch
from replay_hybrid.policy import sample


def tensors(views,device):
    return tuple(torch.as_tensor(np.stack([view[i] for view in views]),device=device,dtype=torch.float32) for i in range(3))


@torch.inference_mode()
def greedy(model,views,device):
    return model.greedy(model.encode(tensors(views,device)))[0].cpu().numpy()


@torch.inference_mode()
def opponents(worlds,views,models,device,nexto=None):
    commands=[{} for _ in worlds];groups={}
    for i,(world,obs) in enumerate(zip(worlds,views)):
        for aid in world.theirs:
            if world.opponent=='chaser':commands[i][aid]=world.chaser(aid)
            else:groups.setdefault(world.opponent,[]).append((i,aid,obs[aid]))
    for name,rows in groups.items():
        batch=[row[2] for row in rows]
        if name=='nexto':
            from nexto_teacher import nexto_actions
            if nexto is None:raise ValueError('Nexto opponent requested without its local weights')
            actions=nexto_actions()[nexto.logits(batch).argmax(-1)]
            chunks=np.repeat(actions[:,None,:],8,axis=1)
        else:chunks=greedy(models[name],batch,device)[:,:8]
        for (i,aid,_),chunk in zip(rows,chunks):commands[i][aid]=chunk.copy()
    return commands


@torch.inference_mode()
def collect(actor,critic,worlds,models,*,horizon,device,nexto=None,stop=None):
    actor.eval();critic.eval()
    storage={key:[] for key in ('q','kv','mask','codes','logp','values','next_values','rewards','terminated','truncated')}
    metrics={'goals_for':0,'goals_against':0,'own_goals':0,'airborne_touches':0,'episodes':0}
    for _ in range(horizon):
        if stop is not None and stop():break
        views=[world.observe() for world in worlds]
        ours=[obs[aid] for world,obs in zip(worlds,views) for aid in world.ours]
        obs=tensors(ours,device);chunks,codes,logp=sample(actor,obs);values=critic(obs)
        chunks=chunks.cpu().numpy();commands=opponents(worlds,views,models,device,nexto)
        position=0
        for world,command in zip(worlds,commands):
            for aid in world.ours:command[aid]=chunks[position,:8].copy();position+=1
        outcomes=[world.step(command) for world,command in zip(worlds,commands)]
        final=[view for outcome in outcomes for view in outcome[3]]
        for key,value in zip(('q','kv','mask'),obs):storage[key].append(value.cpu().numpy().copy())
        for key,value in (('codes',codes),('logp',logp),('values',values),('next_values',critic(tensors(final,device)))):
            storage[key].append(value.cpu().numpy().copy())
        storage['rewards'].append(np.array([r for world,(r,*_) in zip(worlds,outcomes) for _ in range(world.team_size)],np.float32))
        for key,index in (('terminated',1),('truncated',2)):
            storage[key].append(np.array([outcome[index] for world,outcome in zip(worlds,outcomes) for _ in range(world.team_size)],bool))
        for _,done,cut,_,info in outcomes:
            metrics['episodes']+=int(done or cut);metrics['goals_for']+=int(info['goal'] is True)
            metrics['goals_against']+=int(info['goal'] is False);metrics['own_goals']+=int(info['own_goal'])
            metrics['airborne_touches']+=int(info['airborne_touches'])
    return ({key:np.stack(value) for key,value in storage.items()} if storage['q'] else None),metrics
