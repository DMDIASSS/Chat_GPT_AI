"""Slater v0.3.2: process-separated, fresh-arena, replay-heldout kickoff evaluation.

No training; no promotions; only test split for held-out evaluation.
Reproducibility is *measured*, not assumed; physics can differ between repetitions.
Examples in README. Needs installed v0.3.1 modules and protected original models.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from slater_kickoff_extract_v031 import load_poses
from slater_kickoff_train_v031 import EXPECTED_U60_SHA, EXPECTED_NEXTO_SHA256, MODES


def checked_destination(path: str, root: Path) -> Path:
    dest = Path(path).resolve()
    safe = (root / 'data' / 'isolated').resolve()
    if not dest.is_relative_to(safe) or dest.suffix != '.json':
        raise ValueError('Report must be a new .json in data/isolated')
    if dest.exists():
        raise FileExistsError(f'Refusing to overwrite {dest}')
    return dest


def source_guard(root: Path, candidate: Path, u60: Path) -> dict:
    import torch
    from slater_research.checkpoint import CYCLE9, CYCLE9_SHA
    from slater_cycle9_native_ppo_v025 import sha256
    safe = (root/'data'/'isolated').resolve()
    for path in (candidate,u60):
        if not path.resolve().is_relative_to(safe) or not path.is_file() or path.suffix!='.pt':
            raise ValueError('Checkpoint outside data/isolated or does not exist: '+str(path))
    if sha256(u60) != EXPECTED_U60_SHA:raise ValueError('Original u60 SHA mismatch')
    if sha256(root / CYCLE9) != CYCLE9_SHA:raise ValueError('Cycle9 source SHA mismatch')
    if sha256(root/'vendor'/'nexto'/'nexto-model.pt') != EXPECTED_NEXTO_SHA256:
        raise ValueError('Nexto source SHA mismatch')
    doc=torch.load(candidate,map_location='cpu',weights_only=True)
    if not(isinstance(doc,dict) and doc.get('stage')=='slater_kickoff_v031' and
           doc.get('source_sha')==CYCLE9_SHA and
           doc.get('meta',{}).get('u60_sha')==EXPECTED_U60_SHA and
           doc.get('global_updates') in (10,20,30,40)):
        raise ValueError('Expected a verified v0.3.1 kickoff checkpoint')
    return {'cycle9_sha256':CYCLE9_SHA,'nexto_sha256':EXPECTED_NEXTO_SHA256,
            'u60_sha256':EXPECTED_U60_SHA,'candidate_sha256':sha256(candidate),
            'candidate_updates':doc['global_updates']}


def summarize(rows: list[dict]) -> dict:
    n=len(rows)
    if not n:raise ValueError('Empty results')
    f=lambda pred:round(sum(bool(pred(r)) for r in rows)/n,4)
    out={'games':n,'wins':sum(x['outcome']>0 for x in rows),
         'losses':sum(x['outcome']<0 for x in rows),
         'draws':sum(x['outcome']==0 for x in rows),
         'win_rate':f(lambda r:r['outcome']>0),
         'first_touch_rate':f(lambda r:r['first_touch']=='student'),
         'opponent_first_rate':f(lambda r:r['first_touch']=='opponent'),
         'fake_takeover_proxy_rate':round(sum(bool(x['fake_takeover_proxy']) for x in rows)/
                                          max(1,sum(x['fake_attempted'] for x in rows)),4),
         'mean_ball_progress_uu':round(sum(float(x['final_ball_progress']) for x in rows)/n,2)}
    out['by_mode']={m:{'games':len(sub),'wins':sum(r['outcome']>0 for r in sub),
                       'first_touches':sum(r['first_touch']=='student' for r in sub)}
                    for m in MODES if (sub:=[r for r in rows if r['mode']==m])}
    return out


def seeded_stats(rows_by_policy: dict[str, list[dict]], seed: int, samples=1500) -> dict:
    """Cluster by kickoff seed+repeat. Paired bootstrap is descriptive if physics is stochastic."""
    a,b=rows_by_policy['original_u60'],rows_by_policy['candidate']
    # Run metadata includes repetitions so same physical starting state is checked even if outcomes differ.
    keys=lambda rows:{(int(r['repeat']),int(r['episode'])):r for r in rows}
    am,bm=keys(a),keys(b)
    if set(am)!=set(bm):raise RuntimeError('Missing paired episode')
    k=sorted(am)
    for id in k:
        r,s=am[id],bm[id]
        if (r['seed']!=s['seed'] or r['side']!=s['side'] or r['mode']!=s['mode'] or
            r['kickoff_signature']!=s['kickoff_signature']):
            raise RuntimeError('START_STATE_MISMATCH '+json.dumps({'id':id,'a':r,'b':s})[:1200])
    def vals(metric):
        if metric=='win':return np.array([int(bm[x]['outcome']>0)-int(am[x]['outcome']>0) for x in k],dtype=float)
        if metric=='first_touch':return np.array([int(bm[x]['first_touch']=='student')-int(am[x]['first_touch']=='student') for x in k],dtype=float)
        if metric=='ball_progress':return np.array([float(bm[x]['final_ball_progress'])-float(am[x]['final_ball_progress']) for x in k],dtype=float)
    rng=np.random.default_rng(seed)
    output={}
    for metric in ('win','first_touch','ball_progress'):
        v=vals(metric)
        boots=rng.choice(v,size=(samples,len(v)),replace=True).mean(axis=1)
        output[metric]={'delta':round(float(v.mean()),4),'bootstrap_95ci':
                        [round(float(x),4) for x in np.percentile(boots,[2.5,97.5])]}
    # Across-replicate variability matters even with identical kickoff seeds.
    rep_diff=[]
    for rep in sorted(set(x['repeat'] for x in a)):
        aa=[r for r in a if r['repeat']==rep]
        bb=[r for r in b if r['repeat']==rep]
        rep_diff.append({'repeat':rep,'baseline_wins':sum(x['outcome']>0 for x in aa),
                         'candidate_wins':sum(x['outcome']>0 for x in bb)})
    return {'paired_count':len(k),'deltas':output,'wins_by_repeat':rep_diff,
            'note':'Descriptive paired bootstrap. Cross-process physics variation and shared kickoff seeds limit inference.'}


def worker(args):
    import torch
    from slater_research.checkpoint import cycle9_pair
    from nexto_teacher import nexto_actions
    from afk_team_research import TeamObserver
    import slater_cycle9_native_ppo_v025 as base
    from slater_kickoff_train_v031 import KickoffCurriculum

    root=Path.cwd().resolve()
    torch.set_num_threads(2)
    torch.manual_seed(args.seed+args.repeat*100_003)
    random.seed(args.seed+args.repeat*100_003)
    np.random.seed((args.seed+args.repeat*100_003)%(2**32))
    ckpt=Path(args.checkpoint).resolve()
    u60=Path(args.u60).resolve()
    # Each worker validates immutable sources itself rather than relying on parent.
    source_guard(root,ckpt,u60)
    poses=load_poses(args.scenarios,args.split)
    if not poses:raise ValueError('No scenario poses for split '+args.split)
    actor,cycle9=cycle9_pair(root)
    doc=torch.load(ckpt,map_location='cpu',weights_only=True)
    if args.policy=='candidate':actor.load_state_dict(doc['actor'],strict=True)
    else:
        baseline=torch.load(u60,map_location='cpu',weights_only=True)
        actor.load_state_dict(baseline['actor'],strict=True)
    for model in (actor,cycle9):
        model.eval()
        for p in model.parameters():p.requires_grad_(False)
    nexto=torch.jit.load(str(root/'vendor'/'nexto'/'nexto-model.pt'),map_location='cpu')
    nexto.eval()
    for p in nexto.parameters():p.requires_grad_(False)
    native=nexto_actions()
    actions=np.stack([np.asarray(native[i],dtype=np.float32).reshape(8) for i in range(90)])
    opponents={'nexto':nexto,'cycle9':cycle9}
    results=[]
    for i in range(args.episodes):
        episode_seed=args.seed + args.repeat*500_009 + i*1103
        # Fresh arena AND observer for EACH episode; no match-level state shared.
        env=KickoffCurriculum(actions,TeamObserver(),opponents,poses,max_steps=args.max_steps)
        try:
            env.episode_count=i
            obs=env.reset(episode_seed)
            vals=[]
            for side in ('blue','orange'):
                phy=env.state.cars[side+'-0'].physics
                vals.extend(float(x) for x in phy.position)
                vals.extend(float(x) for x in phy.euler_angles)
                vals.append(float(env.state.cars[side+'-0'].boost_amount))
            vals.extend(float(x) for x in env.state.ball.position)
            signature=hashlib.sha256(np.round(np.array(vals),4).tobytes()).hexdigest()[:20]
            for _ in range(args.max_steps):
                with torch.no_grad():idx=int(base.logits_of(actor,base.to_tensors(obs)).argmax(-1).item())
                obs,_,done,info=env.step(idx)
                if done:break
            results.append({'repeat':args.repeat,'episode':i,'seed':episode_seed,
                            'side':info['student_side'],'mode':info['mode'],
                            'kickoff_signature':signature,'replay_used':info['replay_used'],
                            'first_touch':info['first_touch'],'fake_attempted':info['fake_attempted'],
                            'fake_takeover_proxy':info['fake_takeover_proxy'],
                            'outcome':info['outcome'],'final_ball_progress':info['final_ball_progress']})
        finally:env.close()
    print('WORKER_JSON '+json.dumps({'policy':args.policy,'repeat':args.repeat,'rows':results},allow_nan=False))


def run_parent(args):
    root=Path.cwd().resolve()
    out=checked_destination(args.out,root)
    if args.split!='test':raise ValueError('Only untouched test split allowed for this evaluator')
    ckpt=Path(args.checkpoint).resolve();u60=Path(args.u60).resolve()
    guard=source_guard(root,ckpt,u60)
    if args.episodes%12:raise ValueError('episodes must be a multiple of 12, balancing teams and modes')
    if args.episodes<12 or args.episodes>240 or args.repeats<1 or args.repeats>8 or args.max_steps<60 or args.max_steps>450:
        raise ValueError('Unsafe or invalid evaluation settings')
    rows={'original_u60':[],'candidate':[]}
    for repetition in range(args.repeats):
        order=['original_u60','candidate'] if repetition%2==0 else ['candidate','original_u60']
        for policy in order:
            argv=[sys.executable,str(Path(__file__).resolve()),'--internal-worker','--policy',policy,
                  '--repeat',str(repetition),'--checkpoint',str(ckpt),'--u60',str(u60),
                  '--scenarios',str(Path(args.scenarios).resolve()),'--split',args.split,
                  '--seed',str(args.seed),'--episodes',str(args.episodes),
                  '--max-steps',str(args.max_steps)]
            p=subprocess.run(argv,cwd=root,capture_output=True,text=True,timeout=1800)
            if p.returncode:
                raise RuntimeError('WORKER_FAILED '+policy+' '+str(repetition)+' '+p.stderr[-2500:])
            records=[line.removeprefix('WORKER_JSON ') for line in p.stdout.splitlines() if line.startswith('WORKER_JSON ')]
            if len(records)!=1:raise RuntimeError('Missing worker output: '+p.stdout[-2000:])
            msg=json.loads(records[0])
            if msg['policy']!=policy or len(msg['rows'])!=args.episodes:
                raise RuntimeError('Bad worker results')
            rows[policy].extend(msg['rows'])
            print('PROGRESS',repetition+1,'/',args.repeats,'policy',policy,'wins',sum(r['outcome']>0 for r in msg['rows']),flush=True)
    report={'version':'v0.3.2','split':args.split,'guard':guard,
            'episodes_per_policy':args.episodes*args.repeats,
            'summaries':{k:summarize(v) for k,v in rows.items()},
            'comparison':seeded_stats(rows,args.seed),
            'rows':rows,'training':False,'promotion':False}
    # Verify source model SHA once more after all subprocesses.
    if source_guard(root,ckpt,u60)!=guard:raise RuntimeError('Checkpoint SHA drift')
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf8') as f:json.dump(report,f,indent=2,allow_nan=False)
    print('HELDOUT_ORIGINAL_U60',json.dumps(report['summaries']['original_u60']),flush=True)
    print('HELDOUT_KICKOFF_CANDIDATE',json.dumps(report['summaries']['candidate']),flush=True)
    print('PAIRED_HELDOUT_COMPARISON',json.dumps(report['comparison']),flush=True)
    print('SAVED_READ_ONLY_REPORT',out,flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',required=True)
    p.add_argument('--u60',default='data/isolated/slater_v027_campaign01_u0060.pt')
    p.add_argument('--scenarios',default='data/kickoffs_v031')
    p.add_argument('--split',default='test')
    p.add_argument('--episodes',type=int,default=36)
    p.add_argument('--repeats',type=int,default=2)
    p.add_argument('--max-steps',type=int,default=180)
    p.add_argument('--seed',type=int,default=716023)
    p.add_argument('--out')
    p.add_argument('--internal-worker',action='store_true',help=argparse.SUPPRESS)
    p.add_argument('--policy',choices=('original_u60','candidate'),help=argparse.SUPPRESS)
    p.add_argument('--repeat',type=int,default=0,help=argparse.SUPPRESS)
    args=p.parse_args()
    if args.internal_worker:
        if args.split!='test':raise ValueError('worker only supports heldout test')
        if args.policy is None:raise ValueError('missing internal policy')
        worker(args)
    else:
        if not args.out:p.error('--out is required')
        run_parent(args)

if __name__=='__main__':main()
