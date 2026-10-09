"""Optional supervised timing specialist (not a replacement for Nexto).

Trains only on *physically verified* scripted demonstrations. No learning if
there are fewer than 8 separate successful training scenarios; this prevents
accidental 'learning' from a tiny repeated sequence.
"""
from __future__ import annotations
import argparse,json,os
from pathlib import Path
import numpy as np
import torch
from torch import nn
from skillforge_core import Simulator,rollout,output_metrics

ROOT=Path(__file__).resolve().parent
DEFAULT_DIR=ROOT/'data'/'skillforge'/'wavedash'


class Specialist(nn.Module):
    def __init__(self, inputs=19):
        super().__init__()
        self.net=nn.Sequential(nn.Linear(inputs,128),nn.Tanh(),
                    nn.Linear(128,128),nn.Tanh(),nn.Linear(128,4))
    def forward(self,x): return self.net(x)


def load_policy(path):
    file=torch.load(path,map_location='cpu',weights_only=True)
    if file.get('format')!='skillforge-wavedash-specialist-v1':
        raise ValueError('Not a SkillForge wavedash checkpoint')
    net=Specialist()
    net.load_state_dict(file['model']);net.eval()
    variant=file['variant']
    def policy(features):
        with torch.inference_mode():
            logits=net(torch.as_tensor(features[None,:],dtype=torch.float32))[0].numpy()
        c=np.zeros(8,dtype=np.float32)
        # 3 continuous controls + binary jump. No throttle, steer, boost, handbrake.
        c[2:5]=np.tanh(logits[:3])
        c[5]=float(logits[3]>0)
        if variant=='forward': c[3]=0;c[4]=0
        if variant=='side': c[2]=0
        if variant=='airroll_only': c[2]=0;c[3]=0;c[5]=0
        return c
    return policy


def train(args):
    root=args.path
    result=json.loads((root/'discovery.json').read_text(encoding='utf-8'))
    if not result.get('eligible_for_imitation'):
        raise RuntimeError('CEM candidate failed holdout gate; do not imitate it')
    demonstrations=json.loads((root/'verified_demonstrations.json').read_text(encoding='utf-8'))
    examples=demonstrations['examples']
    if len(examples)<args.minimum_trajectories:
        raise RuntimeError(f'Only {len(examples)} unique demonstrated successes; '
            f'need at least {args.minimum_trajectories}. Search with more --training-seeds.')
    if len(set(e['seed'] for e in examples)) != len(examples):
        raise ValueError('Duplicate demo seeds not allowed')
    xs=[];ys=[]
    for e in examples:
        for x,control in e['trajectory']:
            xs.append(x)
            ys.append([control[2],control[3],control[4],control[5]])
    X=torch.tensor(np.asarray(xs,dtype=np.float32))
    Y=torch.tensor(np.asarray(ys,dtype=np.float32))
    torch.manual_seed(args.seed)
    net=Specialist()
    optimizer=torch.optim.Adam(net.parameters(),lr=1e-3)
    for ep in range(args.epochs):
        for ids in torch.randperm(len(X)).split(args.batch):
            logits=net(X[ids]); expected=Y[ids]
            loss=((torch.tanh(logits[:,:3])-expected[:,:3])**2).mean()+\
                1.2*nn.functional.binary_cross_entropy_with_logits(logits[:,3],expected[:,3])
            optimizer.zero_grad();loss.backward();optimizer.step()
        if (ep+1)%10==0 or ep==0 or ep+1==args.epochs:
            print(f'Imitation epoch {ep+1}/{args.epochs} loss={float(loss.detach()):.4f}',flush=True)
    dest=root/'specialist_experimental.pt'
    if dest.exists(): raise FileExistsError(f'Existing {dest}; choose a different --path')
    tmp=dest.with_suffix('.partial')
    torch.save({'format':'skillforge-wavedash-specialist-v1',
                'model':net.state_dict(),'variant':result['variant'],
                'training_seeds':[e['seed'] for e in examples],
                'discovery':str((root/'discovery.json').resolve()),
                'note':'UNVERIFIED BC POLICY. Holdout eval required before use.'},tmp)
    os.replace(tmp,dest)
    print(f'Saved experimental specialist {dest}; test on independent physics seeds.')


def evaluate(args):
    root=args.path
    results=json.loads((root/'discovery.json').read_text(encoding='utf-8'))
    candidate=results['candidate']; variant=results['variant']
    specialist=root/'specialist_experimental.pt'
    pol=load_policy(specialist) if specialist.exists() else None
    rng_seed=args.seed
    sim=Simulator()
    try:
        counts={'macro':0,'no_input':0,'imitation':0}
        raw=[]
        for seed in range(rng_seed,rng_seed+args.seeds):
            out={'seed':seed}
            for mode in ('macro','no_input','imitation'):
                if mode=='imitation' and pol is None: continue
                m,_=rollout(sim,seed,candidate,
                    policy=(lambda x:np.zeros(8,dtype=np.float32)) if mode=='no_input' else pol if mode=='imitation' else None,
                    variant=variant,difficulty=args.difficulty)
                out[mode]=output_metrics(m)
                counts[mode]+=int(m.success)
            raw.append(out)
        report={'type':'skillforge-independent-eval-v1', 'seeds':args.seeds,
               'starting_seed':rng_seed,'success_count':counts,'episodes':raw}
        path=root/f'independent_eval_{rng_seed}_{args.seeds}.json'
        if path.exists(): raise FileExistsError(f'{path} exists; use new --seed')
        path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('PHYSICS VERIFIED successes (not ranked match wins):')
        for key in ('no_input','macro','imitation'):
            if key=='imitation' and pol is None: print('imitation: not trained');continue
            print(f'  {key}: {counts[key]}/{args.seeds}')
        print(f'Report: {path}')
        if pol is not None and counts['imitation']<=counts['no_input']:
            print('IMPROVEMENT NOT VERIFIED. Do not integrate this specialist.')
        return report
    finally:
        sim.close()


def parse():
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=('train','evaluate'))
    p.add_argument('--path',type=Path,default=DEFAULT_DIR)
    p.add_argument('--epochs',type=int,default=40)
    p.add_argument('--batch',type=int,default=256)
    p.add_argument('--minimum-trajectories',type=int,default=8)
    p.add_argument('--seed',type=int,default=837219)
    p.add_argument('--seeds',type=int,default=20)
    p.add_argument('--difficulty',choices=('near','varied'),default='near')
    return p


if __name__=='__main__':
    args=parse().parse_args()
    if args.mode=='train':train(args)
    else:evaluate(args)
