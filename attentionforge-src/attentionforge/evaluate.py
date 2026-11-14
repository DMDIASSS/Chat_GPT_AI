"""Frozen-policy comparison on fresh seeds; no training, promotion or reward scores."""
import json,secrets,time,hashlib
from pathlib import Path
import numpy as np
import torch
from .runtime import batch,device,atomic_json
from .model import ActorCritic
from .observation import encode
from .train import load

def evaluate(folder,rounds=100,seconds=60,opponent=None,seed=None):
    folder=Path(folder);latest=folder/'latest.pt'
    if not latest.is_file():raise FileNotFoundError(latest)
    candidate=load(latest,torch.device('cpu'));cfg=candidate['config']
    if rounds<4 or rounds%2:raise ValueError('Use an even number of games, at least 4; both colors form one seed block.')
    if seconds<1 or seconds>600:raise ValueError('Match duration must be 1..600 seconds')
    if opponent is None:
        choices=[folder/'baseline.pt'] if (folder/'baseline.pt').is_file() else []
        if not choices:raise FileNotFoundError('No frozen history yet. Train through the first 1,000,000 learning transitions, or pass --opponent path/to/checkpoint.pt.')
        opponent=choices[0]
    opponent=Path(opponent);baseline=load(opponent,torch.device('cpu'))
    keys=('network','team_size','tick_skip','action_delay')
    if any(cfg[k]!=baseline['config'][k] for k in keys):raise ValueError('Evaluation models must share the same network, team size and timing contract')
    if hashlib.sha256(latest.read_bytes()).digest()==hashlib.sha256(opponent.read_bytes()).digest():raise ValueError('Candidate and baseline weights are the same checkpoint; choose a different frozen checkpoint')
    cfg=json.loads(json.dumps(cfg));cfg['episode_seconds']=seconds+10;cfg['no_touch_seconds']=seconds+10
    torch.set_num_threads(cfg['torch_threads']);dev=device(cfg);model=ActorCritic(**cfg['network']).to(dev).eval();other=ActorCritic(**cfg['network']).to(dev).eval();model.load_state_dict(candidate['model']);other.load_state_dict(baseline['model'])
    seed=int(seed if seed is not None else secrets.randbelow(1000000000)+1000000000);start=time.perf_counter();games=[];pairs=rounds//2;team=cfg['team_size'];a=team*2
    print(f'EVAL: {rounds} games, {seconds}s, two colors per seed block, fresh seed {seed}. Candidate vs {opponent}. No training.',flush=True)
    with torch.no_grad():
        for begin in range(0,pairs,32):
            n=min(32,pairs-begin)
            for color in (0,1):
                env=batch(cfg,n=n,seed=seed+7919*begin,kickoffs=True);loc=env.pad_locations();raw=env.observe();ticks=np.zeros(n,np.int64);gf=np.zeros(n,np.int64);ga=np.zeros(n,np.int64)
                while np.any(ticks<seconds*120):
                    active=ticks<seconds*120;ob,lm=encode(raw['world'],raw['pads'],loc);ot=torch.as_tensor(ob.reshape(-1,43,40),device=dev);mt=torch.as_tensor(lm.reshape(-1,90),device=dev)
                    ac=model(ot,mt)[0].argmax(-1).cpu().numpy().reshape(n,a);bc=other(ot,mt)[0].argmax(-1).cpu().numpy().reshape(n,a)
                    if color==0:ac[:,team:]=bc[:,team:]
                    else:ac[:,:team]=bc[:,:team]
                    raw=env.step(ac);g=raw['info'][:,0]*(1 if color==0 else -1);gf+=(active&(g>0));ga+=(active&(g<0));ticks+=raw['info'][:,7].astype(np.int64)*active
                for j in range(n):games.append(dict(seed=seed+7919*(begin+j),color=color,goals_for=int(gf[j]),goals_against=int(ga[j]),ticks=int(ticks[j]),score=1. if gf[j]>ga[j] else 0. if gf[j]<ga[j] else .5))
                print('EVAL_PROGRESS:',len(games),'/',rounds,flush=True)
    scores=np.array([g['score'] for g in games]);block={}
    for g in games:block.setdefault(g['seed'],[]).append(g['score'])
    means=np.array([np.mean(x) for x in block.values()]);mean=float(means.mean())
    # Distribution-free bounded-mean interval; intentionally conservative for small panels.
    radius=float(np.sqrt(np.log(2/0.05)/(2*len(means))));ci=[max(0.,mean-radius),min(1.,mean+radius)]
    result={'contract':'attentionforge-eval-v1','candidate_sha256':hashlib.sha256(latest.read_bytes()).hexdigest(),'baseline_sha256':hashlib.sha256(opponent.read_bytes()).hexdigest(),'candidate_transitions':candidate['learning_transitions'],'baseline_transitions':baseline['learning_transitions'],'baseline_path':str(opponent),'master_seed':seed,'rounds':rounds,'seconds':seconds,'wins':int((scores==1).sum()),'draws':int((scores==.5).sum()),'losses':int((scores==0).sum()),'score_rate':mean,'score_interval_95':ci,'interval_method':'Two-color seed-block scores; bounded Hoeffding 95% interval. No automatic promotion.','wall_seconds':time.perf_counter()-start,'hitbox':'Octane','timing':{'physics_hz':120,'tick_skip':cfg['tick_skip'],'action_delay':cfg['action_delay']},'timeout_note':'No overtime. Each match lasts at least the requested duration and at most 7 extra physics ticks.','games':games}
    out=folder/f'eval_{time.strftime("%Y%m%d_%H%M%S",time.gmtime())}_{seed}.json';atomic_json(out,result)
    print('EVAL_RESULT:',{k:result[k] for k in ('wins','draws','losses','score_rate','score_interval_95')},flush=True);print('EVAL_SAVED:',out,flush=True);return result
