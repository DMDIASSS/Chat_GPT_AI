"""Balanced-color seeded match panels; candidates remain unverified."""
import copy,json,math,secrets,time
from pathlib import Path
import numpy as np
import torch
from .runtime import config,batch,device,model,pin,sha,atomic_json,load

CONTEXTS={'center':0,'diagonal_left':1,'diagonal_right':2,'offcenter_left':3,'offcenter_right':4,'open_play':5,'match':-2}


def summary(rows):
    n=len(rows);w=sum(x['outcome']==1 for x in rows);d=sum(x['outcome']==0 for x in rows);l=n-w-d
    blocks={}
    for row in rows:blocks.setdefault((row['context'],row['pair']),[]).append((row['outcome']+1)/2)
    scores=np.array([np.mean(v) for v in blocks.values()]);mean=(w+.5*d)/n
    # Paired-color blocks, never games falsely treated as independent.
    if len(scores)<2 or np.std(scores,ddof=1)<1e-12:
        radius=math.sqrt(math.log(40)/(2*len(scores)));method='Bounded Hoeffding fallback for zero block variance'
    else:
        df=len(scores)-1
        table=[12.706,4.303,3.182,2.776,2.571,2.447,2.365,2.306,2.262,2.228,2.201,2.179,2.160,2.145,2.131,2.120,2.110,2.101,2.093,2.086,2.080,2.074,2.069,2.064,2.060,2.056,2.052,2.048,2.045,2.042]
        z=1.95996398454;tcrit=table[df-1] if df<=30 else z+(z**3+z)/(4*df)+(5*z**5+16*z**3+3*z)/(96*df**2)
        radius=tcrit*np.std(scores,ddof=1)/math.sqrt(len(scores));method='Approximate paired-seed Student-t 95% interval; small-df table / asymptotic quantile' 
    return {'games':n,'wins':w,'draws':d,'losses':l,'score_rate':mean,'score_interval_95':[max(0,mean-radius),min(1,mean+radius)],'interval_method':method,'goals_for':sum(x['goals_for'] for x in rows),'goals_against':sum(x['goals_against'] for x in rows)}


def evaluate(folder,games_per_context=20,seconds=60,seed=None,opponent=None,contexts=None,automatic=False):
    folder=Path(folder);contexts=contexts or list(CONTEXTS)[:6]
    if games_per_context<4 or games_per_context%2 or games_per_context>2000:raise ValueError('Use an even 4..2000 games per context')
    if not 1<=seconds<=300 or any(k not in CONTEXTS for k in contexts):raise ValueError('Invalid duration/context')
    pinned,candidate_hash=pin(folder,folder/'latest.pt','evaluation')
    candidate,ck,path=model(folder,checkpoint=pinned);cfg=copy.deepcopy(ck['config']);dev=device(cfg);torch.set_num_threads(cfg['torch_threads']);candidate.to(dev)
    source=folder/'initial.pt' if opponent is None else Path(opponent)
    nexto=None;baseline=None
    if str(opponent)=='nexto':
        from .nexto import Nexto
        nexto=Nexto();opponent_hash=nexto.identity;opponent_label='Nexto neural, no scripted kickoff'
    else:
        basepin,opponent_hash=pin(folder,source,'opponent');baseline,bck,_=model(folder,checkpoint=basepin,dev=dev)
        if any(cfg[k]!=bck['config'][k] for k in ('width','tick_skip','action_delay')):raise ValueError('Opponent contract differs')
        opponent_label=str(source)
    master=seed if seed is not None else 0xC0000000+secrets.randbelow(0x10000000);pairs=games_per_context//2;rows=[];begin=time.perf_counter();total=games_per_context*len(contexts)
    print('EVAL_START:',total,'games;',seconds,'simulated seconds each; blue/orange seed pairs; opponent',opponent_label,flush=True)
    tasks=[(name,k) for name in contexts for k in range(pairs)]
    # Batch several contexts together. Swapped-color runs share exact initialization seeds.
    with torch.inference_mode():
        for begin_task in range(0,len(tasks),32):
            group=tasks[begin_task:begin_task+32];n=len(group);base=0xC0000000+(int(master)+begin_task*1000003)%0x10000000
            for color in (0,1):
                env=batch(cfg,n=n,seed=base,seconds=seconds+10)
                for j,(context,k) in enumerate(group):env.set_scene(j,CONTEXTS[context])
                raw=env.observe();locations=env.pad_locations();ticks=np.zeros(n,np.int64);gf=ticks.copy();ga=ticks.copy();contacts=ticks.copy();target=int(round(seconds*120));iterations=0;next_progress=time.perf_counter()+5
                while np.any(ticks<target):
                    ac=np.full((n,2),8,np.int64);x=torch.as_tensor(raw['obs'][:,color],device=dev);lm=torch.as_tensor(raw['mask'][:,color],device=dev);ac[:,color]=candidate(x,lm)[0].argmax(-1).cpu().numpy()
                    if nexto is not None:ac[:,1-color]=nexto.act(raw,locations,np.full(n,1-color))
                    else:ac[:,1-color]=baseline(torch.as_tensor(raw['obs'][:,1-color],device=dev),torch.as_tensor(raw['mask'][:,1-color],device=dev))[0].argmax(-1).cpu().numpy()
                    active=ticks<target;raw=env.step(ac,np.maximum(0,target-ticks));g=raw['info'][:,0]*(1 if color==0 else -1);gf+=active&(g>0);ga+=active&(g<0);contacts+=active*raw['info'][:,1+color].astype(np.int64);ticks+=raw['info'][:,3].astype(np.int64);iterations+=1
                    if time.perf_counter()>=next_progress:
                        print('EVAL_RUNNING:',len(rows),'/',total,'complete;',round(float(ticks.min()/120),1),'/',seconds,'seconds in current batch',flush=True);next_progress=time.perf_counter()+5
                for j,(context,k) in enumerate(group):rows.append({'context':context,'pair':begin_task+j,'context_pair':k,'color':color,'native_seed':int(base+7919*j)%(1<<32),'seconds':ticks[j]/120,'goals_for':int(gf[j]),'goals_against':int(ga[j]),'touch_decisions':int(contacts[j]),'outcome':int(np.sign(gf[j]-ga[j]))})
                print('EVAL_PROGRESS:',len(rows),'/',total,summary(rows),flush=True)
    result={'version':'duelforge-panel-v1','candidate_sha256':candidate_hash,'candidate_actor_pin':str(pinned.relative_to(folder)),'candidate_learning_transitions':ck['learning_transitions'],'opponent':opponent_label,'opponent_sha256':opponent_hash,'master_seed':int(master),'scope':'Scenario-stratified discovery validation. Each goal resets to the declared context. Not a regulation tournament or held-out promotion test.','automatic':automatic,'overall':summary(rows),'contexts':{name:summary([x for x in rows if x['context']==name]) for name in contexts},'games':rows,'wall_seconds':time.perf_counter()-begin,'promotion':'none; pinned candidates are unverified'}
    out=folder/f'eval_{time.time_ns()}.json';atomic_json(out,result)
    bestfile=folder/('validation_best_nexto.json' if nexto is not None else 'validation_best.json');prior=json.loads(bestfile.read_text()) if bestfile.is_file() else None
    if 'open_play' in result['contexts'] and (prior is None or (prior['opponent_sha256']==opponent_hash and result['contexts']['open_play']['score_rate']>prior['score_rate'])):
        atomic_json(bestfile,{'score_rate':result['contexts']['open_play']['score_rate'],'actor_path':str(pinned.relative_to(folder)),'actor_sha256':candidate_hash,'learning_transitions':ck['learning_transitions'],'opponent_sha256':opponent_hash,'report':out.name,'status':'best repeated open-play validation; not verified champion'})
    result['verdict']='advantage' if result['overall']['score_interval_95'][0]>.5 else 'disadvantage' if result['overall']['score_interval_95'][1]<.5 else 'uncertain'
    atomic_json(out,result)
    print('EVAL_SAVED:',out,flush=True);return result
