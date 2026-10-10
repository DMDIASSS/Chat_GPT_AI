"""AFK Improved Replay + TAS Learning v1.

- Replays: approximate action reconstruction -> selective native Nexto demonstrations.
- TAS .data: structural audit ONLY. Never assume inputs are aligned with game states.
- BC: conservative, CPU-only isolated fine tuning, no automatic promotion.
- Gate: comparison against original Nexto and Cycle 9 in independent RocketSim episodes.

Uses original Nexto weights under the project's existing noncommercial license.
"""
from __future__ import annotations
import argparse
import contextlib
import collections
import csv
import glob
import hashlib
import json
import math
import os
import random
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parent
BASE=Path(os.environ.get('AFK_REPLAY_EXPERIMENT_DIR', str(ROOT/'data'/'afk_improved'/'learning')))
DATA=BASE/'native_replay_dataset.npz'
MANIFEST=BASE/'dataset_manifest.json'
CANDIDATE=BASE/'replay_candidate.pt'
REPORT=BASE/'training_report.json'
PAUSE=BASE/'learning.pause'
NEXTOPATH=ROOT/'vendor'/'nexto'/'nexto-model.pt'


def utc(): return datetime.now(timezone.utc).isoformat()
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):h.update(chunk)
    return h.hexdigest()
def write_json(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding='utf8'); os.replace(tmp,path)
def atomic_torch_save(path, data):
    import torch
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.partial')
    try:torch.save(data,temp);os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)
def expand_files(patterns,suffix):
    seen=set();out=[]
    for pattern in patterns:
        # Expand PowerShell/CMD literals recursively; do not interpret wildcard as a literal filename.
        found=glob.glob(pattern,recursive=True) if any(c in pattern for c in '*?[') else [pattern]
        for item in found:
            p=Path(item)
            it=p.rglob('*'+suffix) if p.is_dir() else (p,)
            for child in it:
                if child.suffix.lower()!=suffix or not child.is_file():continue
                s=str(child.resolve()).lower()
                if s not in seen:seen.add(s);out.append(child.resolve())
    return sorted(out)

@contextlib.contextmanager
def exclusive_learning():
    """OS lock. Never delete another process's lock file to 'fix' contention."""
    BASE.mkdir(parents=True,exist_ok=True)
    lock=BASE/'.learning.lock'
    with lock.open('a+b') as fh:
        fh.seek(0);fh.write(b'0');fh.flush();fh.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(fh.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as e:raise RuntimeError('Another replay/TAS learner is running') from e
        else:
            import fcntl
            try:fcntl.flock(fh.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as e:raise RuntimeError('Another replay/TAS learner is running') from e
        try:yield
        finally:
            if os.name=='nt':fh.seek(0);msvcrt.locking(fh.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(fh.fileno(),fcntl.LOCK_UN)


def archive_existing(path):
    """Save a byte-exact named snapshot before intentional replacement."""
    import shutil
    p=Path(path)
    if not p.exists():return None
    dest=BASE/'archive'/(p.stem+'_'+sha(p)[:16]+p.suffix)
    dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():
        tmp=dest.with_name(dest.name+'.partial')
        try:shutil.copy2(p,tmp);os.replace(tmp,dest)
        finally:tmp.unlink(missing_ok=True)
    return dest

# TAS is a demonstration format, NOT a native Nexto observation dataset.
# These observations require validated RocketSim state transitions aligned to the controls.
def inspect_tas(path):
    data=Path(path).read_bytes()
    if len(data)<136:raise ValueError('File too small for 8-byte header and 128-byte trailer')
    version, count=struct.unpack_from('<II',data,0)
    if version!=1 or not (1<=count<=10_000_000):raise ValueError('Unexpected version/frame count')
    if len(data)!=8+32*count+128:raise ValueError('TAS file has unexpected byte length')
    flags=collections.Counter();ranges=[[math.inf,-math.inf] for _ in range(7)]
    for i in range(count):
        bits,*floats=struct.unpack_from('<I7f',data,8+i*32)
        flags[bits]+=1
        if not all(math.isfinite(v) for v in floats):raise ValueError('Non-finite TAS controller value')
        for j,v in enumerate(floats):ranges[j][0]=min(ranges[j][0],v);ranges[j][1]=max(ranges[j][1],v)
    return dict(filename=Path(path).name,sha256=hashlib.sha256(data).hexdigest(),format_version=version,
                frame_count=count,approx_seconds_if_120hz=round(count/120,3),
                unique_raw_flag_fields=len(flags),raw_flag_counts=dict(flags),
                raw_float_min_max=ranges,record_stride=32,trailer_bytes=128,
                training_ready=False,
                reason='Actual field semantics, state trailer, capture tick rate and RocketSim synchronization NOT verified')


def tas_audit(args):
    paths=expand_files(args.inputs,'.data')
    if not paths:raise RuntimeError('No .data files found; use a folder path or a quoted glob like "data/tas/*.data"')
    rows=[];fail=[]
    for p in paths:
        try:r=inspect_tas(p);rows.append(r);print('TAS',p.name,r['frame_count'],'frames (audit only)',flush=True)
        except (ValueError,OSError,struct.error) as e:fail.append({'filename':p.name,'error':str(e)});print('BAD TAS:',p,e)
    write_json(args.report,{'created_utc':utc(),'files':rows,'errors':fail,'training_ready':False,
        'note':'TAS cannot be learned without validated per-frame world states and discrete-action alignment.'})
    print('Saved:',args.report)
    if fail:raise RuntimeError(f'{len(fail)} TAS files invalid')


def action_options(controls, table):
    """Use near-matches rather than falsely claiming exact human control reconstruction.
    Exact boost/jump/handbrake mismatches are heavily penalized.
    """
    c=np.asarray(controls,dtype=np.float32)
    if c.shape!=(8,) or not np.isfinite(c).all():return None
    if np.max(np.abs(c[:5]))>1.05 or np.any(c[5:] < -0.05) or np.any(c[5:]>1.05):return None
    w=np.array([1.0,1.0,1.0,1.0,1.0,7.0,7.0,3.0],np.float32)
    cost=np.sum((table-c[None,:])**2*w[None,:],axis=1)
    ix=int(cost.argmin());d=float(cost[ix])
    return ix,d


def replay_bucket(state, car):
    """Broad stratification, NOT a claim to identify a flick, shot or successful play."""
    bp=np.asarray(state.ball.position,dtype=np.float32)
    cp=np.asarray(car.physics.position,dtype=np.float32)
    dist=float(np.linalg.norm(bp-cp))
    if dist<450 and 150<bp[2]<550:return 'close_control'
    # own half for blue y<0, orange y>0
    own_half=(bp[1]>0) if car.is_orange else (bp[1]<0)
    if own_half and (abs(float(bp[1]))>1750):return 'defense'
    if bp[2]>500:return 'aerial'
    if (not own_half) and abs(float(bp[1]))>1700:return 'attack'
    if float(car.boost_amount)<18:return 'low_boost'
    return 'general'


def replay_split(digest,validation_pct):
    # split by unique replay SHA, never by frame (avoids train/val leakage)
    return 'val' if int(digest[:8],16)%100 < validation_pct else 'train'


def build(args):
    from rlgym_tools.rocket_league.replays.parsed_replay import ParsedReplay
    from rlgym_tools.rocket_league.replays.convert import replay_to_rlgym
    from rlgym_tools.rocket_league.replays.pick_action import get_best_action_options
    from nexto_teacher import NextoTeacher,nexto_actions
    paths=expand_files(args.inputs,'.replay')
    if not paths:raise RuntimeError('No .replay files found under given paths')
    if args.every<1 or args.max_replays<1 or args.per_replay<1 or args.validation_pct<10:
        raise ValueError('Need every>=1, max_replays>=1, per_replay>=1, validation>=10%')
    if DATA.exists() and not args.replace:raise FileExistsError(f'{DATA} exists; use --replace ONLY if intentional')
    # Loading original TorchScript actor is necessary for original Nexto's observation builder;
    # no inference labels are fabricated here. Uses CPU to avoid fixed-device JIT tensors.
    teacher=NextoTeacher('cpu');table=np.asarray(nexto_actions(),dtype=np.float32)
    if table.shape!=(90,8):raise RuntimeError('Native Nexto action space not 90x8')
    rng=np.random.default_rng(args.seed)
    cache_root=BASE/'replay_cache';cache_root.mkdir(parents=True,exist_ok=True)
    cfg_data=dict(every=args.every,per_replay=args.per_replay,max_age=args.max_age,
        max_cost=args.max_cost,validation_pct=args.validation_pct,action_table_sha=hashlib.sha256(table.tobytes()).hexdigest(),
        parser='v2_feasible_approx_human_rlgym')
    cfg_id=hashlib.sha256(json.dumps(cfg_data,sort_keys=True).encode()).hexdigest()
    cache_hits=0
    arrays={key:[] for key in ('q','kv','mask','action','weight','is_val','bucket','source_id')}
    from_counts=collections.Counter();errors=[];files=[];duplicate=set();total=0
    bucket_names=['general','close_control','defense','aerial','attack','low_boost']
    for path in paths:
        if PAUSE.exists():
            print('Build paused between replays; completed replay caches preserved. Clear pause and rerun to resume.',flush=True)
            return
        if len(files)>=args.max_replays or total>=args.max_samples:break
        digest=sha(path)
        if digest in duplicate:from_counts['duplicate_files']+=1;continue
        duplicate.add(digest)
        try:
            cached=cache_root/(digest+'_'+cfg_id[:12]+'.npz')
            if cached.exists():
                with np.load(cached,allow_pickle=False) as z:
                    if int(z['count'])<1:raise ValueError('Cached replay contains no samples')
                    local=list(zip(z['q'],z['kv'],z['mask'],z['action'],z['weight'],z['is_val'],z['bucket']))
                cache_hits+=1
            else:
                replay=ParsedReplay.load(path)
                past={};local=[]
                for i,frame in enumerate(replay_to_rlgym(replay)):
                    cars=frame.state.cars
                    if len(cars)!=2 or sum(bool(c.is_orange) for c in cars.values())!=1:
                        from_counts['non_1v1_frames']+=1;continue
                    # Update previous actions even for unselected frames; observation prev-action tracks replay data.
                    current={}
                    for agent in cars:
                        raw=frame.actions.get(agent)
                        if raw is not None:
                            v=np.asarray(raw,dtype=np.float32).reshape(-1)
                            if v.shape==(8,) and np.isfinite(v).all():current[agent]=v.copy()
                    if i%args.every==0 and len(local)<args.per_replay:
                        obs=teacher.observe(frame.state,past)
                        views={agent:(q,kv,mask) for agent,q,kv,mask in obs}
                        for agent,car in cars.items():
                            if len(local)>=args.per_replay:break
                            if not math.isfinite(float(frame.update_age.get(agent,999))) or float(frame.update_age.get(agent,999))>args.max_age:from_counts['stale']+=1;continue
                            if bool(getattr(car,'is_demoed',False)):from_counts['demoed']+=1;continue
                            if agent not in current:from_counts['unknown_controls']+=1;continue
                            res=action_options(current[agent],table)
                            if res is None:from_counts['invalid_controls']+=1;continue
                            action,cost=res
                            if cost>args.max_cost:from_counts['high_cost']+=1;continue
                            # Physics-aware feasibility filter from RLGym Tools; nearest control alone
                            # can be impossible under the car's jump/flip state.
                            try:
                                candidates=np.asarray(get_best_action_options(car,current[agent],table,greedy=True))
                                if (candidates.shape!=(90,) or not np.isfinite(candidates).all() or
                                    candidates.max()<=0 or int(candidates.argmax())!=action):
                                    from_counts['infeasible_or_ambiguous']+=1;continue
                            except (ValueError,AssertionError,IndexError,TypeError):
                                from_counts['action_picker_error']+=1;continue
                            q,kv,mask=views[agent]
                            if q.shape!=(1,32) or kv.shape!=(37,24) or mask.shape!=(37,):
                                raise ValueError(f'Native observation shape unexpectedly changed: {q.shape},{kv.shape},{mask.shape}')
                            if not (np.isfinite(q).all() and np.isfinite(kv).all() and np.isfinite(mask).all()):
                                from_counts['invalid_observations']+=1;continue
                            group=replay_bucket(frame.state,car)
                            # Avoid upweighting uncertain controls; favor class-balanced samples later in training.
                            quality=max(0.15,min(1.0, math.exp(-cost/0.35)))
                            local.append((q,kv,mask,action,quality,replay_split(digest,args.validation_pct)=='val',
                                          bucket_names.index(group)))
                    past=current
            if local and not cached.exists():
                # Incrementally commit a replay shard before moving to the next replay.
                temp=cached.with_name(cached.name+'.partial')
                with temp.open('wb') as f:
                    np.savez_compressed(f,
                        q=np.asarray([x[0] for x in local],np.float32),
                        kv=np.asarray([x[1] for x in local],np.float32),
                        mask=np.asarray([x[2] for x in local],np.float32),
                        action=np.asarray([x[3] for x in local],np.int64),
                        weight=np.asarray([x[4] for x in local],np.float32),
                        is_val=np.asarray([x[5] for x in local],bool),
                        bucket=np.asarray([x[6] for x in local],np.uint8),count=len(local))
                os.replace(temp,cached)
            if not local:
                from_counts['empty_replays']+=1;continue
            # Bound each replay's influence and avoid using adjacent, nearly-identical frames too often.
            take=min(len(local),args.per_replay,args.max_samples-total)
            if take<len(local):
                idx=np.sort(rng.choice(len(local),size=take,replace=False));local=[local[int(x)] for x in idx]
            for x in local:
                for k,val in zip(('q','kv','mask','action','weight','is_val','bucket'),x):arrays[k].append(val)
                arrays['source_id'].append(len(files))
            total+=len(local);files.append({'file':str(path),'sha256':digest,'samples':len(local),
                                               'partition':replay_split(digest,args.validation_pct)})
            print(f'[{len(files)}] {path.name}: {len(local)} high-confidence approx actions ({total} total)',flush=True)
        except Exception as exc:
            errors.append({'file':str(path),'error':f'{type(exc).__name__}: {exc}'})
            print('Skipping broken replay',path.name,errors[-1]['error'],flush=True)
            if args.strict:raise
    if total<args.min_samples:raise RuntimeError(f'Only {total} samples (< {args.min_samples}); refusing dataset/training')
    ntrain=sum(not x for x in arrays['is_val']);nval=total-ntrain
    train_replays=sum(x['partition']=='train' for x in files);val_replays=len(files)-train_replays
    if train_replays<args.min_train_replays or val_replays<args.min_val_replays:
        raise RuntimeError(f'Need >= {args.min_train_replays} training and >= {args.min_val_replays} validation replays; have {train_replays}/{val_replays}')
    if ntrain<args.min_samples*.3 or nval<args.min_samples*.10:
        raise RuntimeError(f'Train/validation sample split too small: {ntrain}/{nval}')
    dataset={'q':np.asarray(arrays['q'],np.float32), 'kv':np.asarray(arrays['kv'],np.float32),
             'mask':np.asarray(arrays['mask'],np.float32),'action':np.asarray(arrays['action'],np.int64),
             'weight':np.asarray(arrays['weight'],np.float32), 'is_val':np.asarray(arrays['is_val'],bool),
             'bucket':np.asarray(arrays['bucket'],np.uint8),'source_id':np.asarray(arrays['source_id'],np.int32)}
    DATA.parent.mkdir(parents=True,exist_ok=True)
    if DATA.exists():
        print('Archived old dataset:',archive_existing(DATA),flush=True)
        archive_existing(MANIFEST)
    tmp=DATA.with_name(DATA.name+'.partial')
    with tmp.open('wb') as fh:np.savez_compressed(fh,**dataset)
    os.replace(tmp,DATA)
    manifest=dict(created_utc=utc(),source='Human replays: approximated controls, NOT exact inputs',
                  dataset=str(DATA.relative_to(ROOT)),dataset_sha256=sha(DATA),frames=total,
                  train_samples=ntrain,val_samples=nval,train_replays=train_replays,val_replays=val_replays,
                  unique_replays=len(files),cache_hits=cache_hits,errors=errors,filter_counts=dict(from_counts),bucket_names=bucket_names,
                  bucket_counts=dict(collections.Counter(bucket_names[x] for x in arrays['bucket'])),
                  args=dict(every=args.every,per_replay=args.per_replay,max_age=args.max_age,
                            max_cost=args.max_cost,validation_pct=args.validation_pct,seed=args.seed),
                  replay_files=files, training_ready=True, tas_mixed=False,
                  warning='Replay actions are reconstructed. Dataset validation is not an independent skill benchmark.')
    write_json(MANIFEST,manifest)
    print('Saved',total,'samples to',DATA,'; train',ntrain,'val',nval,'from',len(files),'unique replays')
    print('Replay errors',len(errors),' - see',MANIFEST)


def dataset_load():
    if not DATA.is_file() or not MANIFEST.is_file():raise FileNotFoundError('Build dataset first')
    m=json.loads(MANIFEST.read_text(encoding='utf8'))
    if sha(DATA)!=m['dataset_sha256']:raise RuntimeError('Dataset hash differs from manifest; refusing to train')
    with np.load(DATA,allow_pickle=False) as z: d={k:z[k] for k in ('q','kv','mask','action','weight','is_val','bucket','source_id')}
    n=len(d['action'])
    if not (d['q'].shape==(n,1,32) and d['kv'].shape==(n,37,24) and d['mask'].shape==(n,37)):
        raise ValueError('Dataset cannot feed native Nexto actor')
    if not (len(d['is_val'])==len(d['weight'])==len(d['source_id'])==n and
            np.isfinite(d['q']).all() and np.isfinite(d['kv']).all() and np.isfinite(d['weight']).all() and
            np.all((d['action']>=0)&(d['action']<90))):raise ValueError('Invalid dataset')
    groups_train=set(d['source_id'][~d['is_val']]);groups_val=set(d['source_id'][d['is_val']])
    if not groups_train or not groups_val or groups_train&groups_val:raise ValueError('Train/validation replay leakage')
    return d,m


def train(args):
    import torch
    import torch.nn.functional as F
    from native_nexto import actor_logits
    from afk_improved_core import CYCLE9,CYCLE9_SHA
    if args.lr<=0 or args.lr>3e-6 or args.epochs<1 or args.epochs>20 or args.batch_size<8:
        raise ValueError('Conservative limits: lr in (0,3e-6], epochs 1..20, batch>=8')
    if sha(CYCLE9)!=CYCLE9_SHA:raise RuntimeError('Original Cycle 9 checkpoint has changed; refusing to train')
    d,m=dataset_load()
    n=len(d['action']);idx_train=np.flatnonzero(~d['is_val']);idx_val=np.flatnonzero(d['is_val'])
    if len(idx_train)<500 or len(idx_val)<100:raise RuntimeError('Insufficient train or val samples')
    if CANDIDATE.exists():
        if not args.replace_candidate:
            raise FileExistsError('Candidate already exists; safe default is never overwrite. Use --replace-candidate intentionally.')
        print('Archived old model:',archive_existing(CANDIDATE),flush=True)
    torch.set_num_threads(min(4,max(1,torch.get_num_threads())))
    torch.manual_seed(args.seed);rng=np.random.default_rng(args.seed)
    actor=torch.jit.load(str(NEXTOPATH),map_location='cpu')
    origin=torch.load(str(CYCLE9),map_location='cpu',weights_only=True)
    actor.load_state_dict(origin['actor'],strict=True);actor.eval()
    anchor=torch.jit.load(str(NEXTOPATH),map_location='cpu');anchor.load_state_dict(origin['actor'],strict=True);anchor.eval()
    for p in anchor.parameters():p.requires_grad_(False)
    opt=torch.optim.Adam(actor.parameters(),lr=args.lr)
    # Cached frozen anchor logits: avoids repeating expensive forward passes on each epoch.
    cache=BASE/'anchor_logits.npy'
    meta=BASE/'anchor_meta.json'
    anchor_identity=hashlib.sha256((m['dataset_sha256']+CYCLE9_SHA).encode()).hexdigest()
    ameta=json.loads(meta.read_text()) if meta.exists() else {}
    if cache.exists() and ameta.get('key')==anchor_identity:
        anchor_logits=np.load(cache,mmap_mode='r')
        if anchor_logits.shape!=(n,90):raise ValueError('Corrupt cached anchor logits')
        print('Using precomputed anchor logits',flush=True)
    else:
        result=[]
        with torch.inference_mode():
            for st in range(0,n,args.batch_size):
                end=min(st+args.batch_size,n)
                q=torch.from_numpy(d['q'][st:end]);kv=torch.from_numpy(d['kv'][st:end]);mask=torch.from_numpy(d['mask'][st:end])
                a=actor_logits(anchor,q,kv,mask).detach().cpu().numpy().astype(np.float32)
                if not np.isfinite(a).all():raise RuntimeError('Anchor returned nonfinite logits')
                result.append(a)
        anchor_logits=np.concatenate(result,axis=0)
        BASE.mkdir(parents=True,exist_ok=True)
        temp=cache.with_name(cache.name+'.tmp')
        with temp.open('wb') as f:np.save(f,anchor_logits)
        os.replace(temp,cache);write_json(meta,dict(key=anchor_identity,sha256=sha(cache)))
    # Sample reweighting prevents easy/abundant categories from drowning rarer decisions.
    counts=np.bincount(d['bucket'][idx_train],minlength=6)
    bucket_weight=np.clip(np.sqrt(max(1,len(idx_train))/np.maximum(counts,1)),1,3)
    def batches(indices,shuffle=False):
        ix=np.array(indices,copy=True)
        if shuffle:rng.shuffle(ix)
        for k in range(0,len(ix),args.batch_size):yield ix[k:k+args.batch_size]
    def tensor_data(ids):
        return (torch.from_numpy(d['q'][ids]),torch.from_numpy(d['kv'][ids]),
                torch.from_numpy(d['mask'][ids]),torch.from_numpy(d['action'][ids]),
                torch.from_numpy((d['weight'][ids]*bucket_weight[d['bucket'][ids]]).astype(np.float32)),
                torch.from_numpy(np.asarray(anchor_logits[ids],dtype=np.float32)))
    def evaluate():
        actor.eval();weighted_ce=0.;weight_total=0.;kl_total=0.;agree=0;sample_count=0
        with torch.inference_mode():
            for ids in batches(idx_val):
                q,kv,mask,action,w,alogits=tensor_data(ids)
                output=actor_logits(actor,q,kv,mask)
                original_logp=F.log_softmax(alogits,dim=-1)
                logp=F.log_softmax(output,dim=-1)
                ce=F.nll_loss(logp,action,reduction='none')
                weighted_ce+=float((ce*w).sum());weight_total+=float(w.sum())
                kl=(original_logp.exp()*(original_logp-logp)).sum(-1)
                kl_total+=float(kl.sum());agree+=int((output.argmax(-1)==alogits.argmax(-1)).sum())
                sample_count+=len(ids)
        return dict(ce=weighted_ce/max(weight_total,1e-9),kl=kl_total/sample_count,
                    action_agreement=agree/sample_count)
    baseline=evaluate()
    results=[{'epoch':0,**baseline}];print('Baseline replay imitation/anchor metrics:',baseline,flush=True)
    best=None;best_ce=baseline['ce'];best_epoch=0;bad=0
    if PAUSE.exists():raise RuntimeError(f'Pause file exists: {PAUSE}; delete it only when intentionally resuming')
    try:
        for epoch in range(1,args.epochs+1):
            if PAUSE.exists():print('Safe pause requested; leaving after last completed epoch',flush=True);break
            actor.eval() # Maintain original TorchScript forward convention with gradients enabled.
            train_losses=[]
            for ids in batches(idx_train,shuffle=True):
                q,kv,mask,target,w,alogits=tensor_data(ids)
                logits=actor_logits(actor,q,kv,mask)
                logp=F.log_softmax(logits,dim=-1)
                prior=F.softmax(alogits,dim=-1)
                ce=(F.nll_loss(logp,target,reduction='none')*w).sum()/w.sum().clamp_min(1e-6)
                kl=(prior*(F.log_softmax(alogits,dim=-1)-logp)).sum(-1).mean()
                loss=ce+args.anchor*kl
                if not torch.isfinite(loss):raise RuntimeError('Nonfinite loss; stopped without promotion')
                opt.zero_grad(set_to_none=True);loss.backward()
                torch.nn.utils.clip_grad_norm_(actor.parameters(),max_norm=0.5)
                opt.step();train_losses.append(float(loss.detach()))
            ev=evaluate();ev.update(epoch=epoch,train_loss=float(np.mean(train_losses)))
            results.append(ev)
            print('Epoch',epoch,'validation CE',round(ev['ce'],4),'KL',round(ev['kl'],5),
                  'action agreement',round(ev['action_agreement'],4),flush=True)
            # Replay-validation improvement AND bounded policy drift, NOT competitive superiority.
            safe=(ev['kl']<=args.max_kl and ev['action_agreement']>=args.min_agreement)
            if safe and ev['ce'] < best_ce-args.min_improvement:
                best_ce=ev['ce'];best_epoch=epoch;bad=0
                payload=dict(actor={k:v.detach().cpu().clone() for k,v in actor.state_dict().items()},
                             timesteps=0, parent_sha=CYCLE9_SHA, dataset_sha=m['dataset_sha256'],
                             train_type='approx_replay_bc',bc_epoch=epoch,source='human_replay',
                             saved_utc=utc(),validation=ev)
                atomic_torch_save(CANDIDATE,payload)
                best=ev;print('Saved isolated BC candidate',CANDIDATE,flush=True)
            else:
                bad+=1
                if not safe:print('Policy drift threshold exceeded; stopping before further damage',flush=True);break
            write_json(REPORT,dict(created_utc=utc(),status='training',baseline=baseline,
                    history=results,best_epoch=best_epoch,best=best,dataset_sha=m['dataset_sha256'],
                    source_sha=CYCLE9_SHA,checkpoint=str(CANDIDATE) if best else None,
                    warning='No competitive promotion. Run independent RocketSim evaluation first.'))
            if bad>=args.patience:print('Early stopped: no val improvement',flush=True);break
    finally:
        write_json(REPORT,dict(created_utc=utc(),status='paused' if PAUSE.exists() else 'complete',baseline=baseline,history=results,
                   best_epoch=best_epoch,best=best,source_sha=CYCLE9_SHA,
                   dataset_sha=m['dataset_sha256'],candidate=str(CANDIDATE) if best else None,
                   competition_verified=False,
                   warning='Replay validation alone does NOT establish Rocket League improvement.'))
    if best is None:print('No checkpoint met the safety + replay-validation gates. Cycle 9 remains untouched.')
    else:print('Candidate saved ONLY as isolated experiment; now run verify. Original Cycle 9 unchanged.')


def verify(args):
    import torch
    from afk_improved_core import CYCLE9,CYCLE9_SHA
    import auto_league as league
    from nexto_teacher import NextoTeacher
    if not CANDIDATE.is_file():raise FileNotFoundError('No accepted isolated replay candidate')
    if sha(CYCLE9)!=CYCLE9_SHA:raise RuntimeError('Cycle 9 source changed; refusing comparison')
    if args.games<100 or args.decisions<300:raise ValueError('Verification requires >=100 games and >=300 decisions')
    candidate=league.actor_from(CANDIDATE,'cpu')
    champion=league.actor_from(CYCLE9,'cpu')
    teacher=NextoTeacher('cpu')
    result=league.run_gate(candidate,champion,teacher.actor,teacher,games=args.games,
                           decisions=args.decisions,seed=args.seed)
    result.update(note='Read-only first-goal test; not full five-minute games',
                  source_checkpoint_sha=CYCLE9_SHA,candidate_checkpoint_sha=sha(CANDIDATE))
    path=BASE/'reports'/f'competition_{int(time.time())}.json'
    write_json(path,result)
    write_json(BASE/'verification_last.json',dict(candidate_sha=result['candidate_checkpoint_sha'],source_sha=CYCLE9_SHA,
        games=args.games,decisions=args.decisions,seed=args.seed,report=str(path),verdict=result['verdict']))
    print('Read-only competitive verdict',result['verdict'],'- saved',path,flush=True)
    print('No checkpoint was promoted or overwritten.')


def pipeline(args):
    """End-to-end, single command. Completed outputs reused, no implicit overwrite."""
    tas_paths=expand_files([args.tas_folder],'.data') if args.tas_folder else []
    if tas_paths:
        from types import SimpleNamespace
        try:
            tas_audit(SimpleNamespace(inputs=[str(p) for p in tas_paths],report=BASE/'tas_audit.json'))
        except RuntimeError as e:
            print('WARNING: Some TAS files failed structural audit; quarantining them and continuing replay-only training:',e,flush=True)
        print('TAS files audited; none are mixed into native replay imitation without synchronized observations.',flush=True)
    if PAUSE.exists():
        print('PAUSED before beginning; remove pause request intentionally to resume',flush=True)
        return
    from types import SimpleNamespace
    if DATA.exists() and MANIFEST.exists():
        print('Reusing previously built and SHA-verified replay dataset',flush=True)
        dataset_load()
    else:
        if DATA.exists()!=MANIFEST.exists():raise RuntimeError('Partial dataset state; manual inspection required')
        build(SimpleNamespace(inputs=[args.replays],every=args.every,max_replays=args.max_replays,
                max_samples=args.max_samples,per_replay=args.per_replay,max_age=.075,max_cost=.65,
                validation_pct=20,min_samples=1500,min_train_replays=5,min_val_replays=2,
                seed=817249,strict=False,replace=False))
    if PAUSE.exists() or not DATA.exists() or not MANIFEST.exists():return
    if CANDIDATE.exists():
        print('Existing candidate found; refusing to overwrite it. Proceeding to read-only verification.',flush=True)
    else:
        train(SimpleNamespace(epochs=args.epochs,batch_size=args.batch_size,lr=args.lr,
                  anchor=2.0,max_kl=.03,min_agreement=.80,min_improvement=.002,
                  patience=2,seed=913572,replace_candidate=False))
    if PAUSE.exists():return
    if CANDIDATE.exists():
        prior=json.loads((BASE/'verification_last.json').read_text()) if (BASE/'verification_last.json').exists() else {}
        if (prior.get('candidate_sha')==sha(CANDIDATE) and prior.get('games')==args.games and
            prior.get('decisions')==750 and prior.get('seed')==592381017):
            print('Independent RocketSim verification cached:',prior.get('verdict'),'at',prior.get('report'),flush=True)
        else:verify(SimpleNamespace(games=args.games,decisions=750,seed=592381017))
    else:print('No candidate passed replay policy-drift gates. No competitive test needed.',flush=True)


def main():
    p=argparse.ArgumentParser(description='AFK Improved safe native Replay + TAS Learning')
    sub=p.add_subparsers(dest='command',required=True)
    t=sub.add_parser('tas-audit',help='Inspect TAS .data sequences: does NOT train')
    t.add_argument('inputs',nargs='+');t.add_argument('--report',type=Path,default=BASE/'tas_audit.json')
    b=sub.add_parser('build',help='Reconstruct selective replay observations + discrete actions')
    b.add_argument('inputs',nargs='+');b.add_argument('--every',type=int,default=8)
    b.add_argument('--max-replays',type=int,default=500);b.add_argument('--max-samples',type=int,default=60000)
    b.add_argument('--per-replay',type=int,default=500);b.add_argument('--max-age',type=float,default=.075)
    b.add_argument('--max-cost',type=float,default=.65);b.add_argument('--validation-pct',type=int,default=20)
    b.add_argument('--min-samples',type=int,default=1500);b.add_argument('--min-train-replays',type=int,default=5)
    b.add_argument('--min-val-replays',type=int,default=2)
    b.add_argument('--seed',type=int,default=817249);b.add_argument('--strict',action='store_true');b.add_argument('--replace',action='store_true')
    tr=sub.add_parser('train',help='Conservative isolated Cycle 9 BC on validated replay dataset')
    tr.add_argument('--epochs',type=int,default=4);tr.add_argument('--batch-size',type=int,default=128)
    tr.add_argument('--lr',type=float,default=8e-7);tr.add_argument('--anchor',type=float,default=2.0)
    tr.add_argument('--max-kl',type=float,default=.03);tr.add_argument('--min-agreement',type=float,default=.80)
    tr.add_argument('--min-improvement',type=float,default=.002);tr.add_argument('--patience',type=int,default=2)
    tr.add_argument('--seed',type=int,default=913572);tr.add_argument('--replace-candidate',action='store_true')
    v=sub.add_parser('verify',help='Independent, read-only candidate vs Cycle 9 and original Nexto')
    v.add_argument('--games',type=int,default=200);v.add_argument('--decisions',type=int,default=750)
    v.add_argument('--seed',type=int,default=592381017)
    allin=sub.add_parser('pipeline',help='Single guarded run: TAS audit, replay dataset, native imitation, competitive benchmark')
    allin.add_argument('--replays',default=str(ROOT/'data'/'replays'))
    allin.add_argument('--tas-folder',default=str(ROOT/'data'/'tas'))
    allin.add_argument('--max-replays',type=int,default=500);allin.add_argument('--max-samples',type=int,default=60000)
    allin.add_argument('--every',type=int,default=8);allin.add_argument('--per-replay',type=int,default=500)
    allin.add_argument('--epochs',type=int,default=4);allin.add_argument('--batch-size',type=int,default=128)
    allin.add_argument('--lr',type=float,default=8e-7);allin.add_argument('--games',type=int,default=200)
    a=p.parse_args()
    try:
        with exclusive_learning():
            if a.command=='tas-audit':tas_audit(a)
            elif a.command=='build':build(a)
            elif a.command=='train':train(a)
            elif a.command=='verify':verify(a)
            elif a.command=='pipeline':pipeline(a)
    except Exception as e:
        print(f'ERROR: {type(e).__name__}: {e}',file=sys.stderr,flush=True)
        return 1
    return 0

if __name__=='__main__':sys.exit(main())
