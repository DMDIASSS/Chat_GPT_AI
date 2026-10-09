"""AutoLeague: safeguarded native-Nexto PPO self-play, champion league and rollback.

Existing dependencies: native_nexto.py, nexto_teacher.py, vendor/nexto/nexto-model.pt,
rlgym + RocketSim, torch. Derived Nexto weights CC BY-NC-SA 4.0.

No writes anywhere under data/native_nexto, data/mechanics, or vendor/nexto.
A candidate never becomes the champion until the held-out gate accepts it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import sys
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.distributions import Categorical

from native_nexto import (Critic, Match, actor_logits, discounted_gae,
                          unpack_obs, select_action, SOURCE_MODEL)
from nexto_teacher import NextoTeacher

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT / 'data' / 'native_nexto' / 'best_10k.pt'
DATA = ROOT / 'data' / 'autoleague'
PROTECTED = [ROOT/'data'/'native_nexto', ROOT/'data'/'mechanics',
             ROOT/'data'/'mechanics_v2', ROOT/'vendor']


def timestamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')


def log(message):
    print(f'[{datetime.now().strftime("%H:%M:%S")}] {message}', flush=True)


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def json_safe(value):
    """Normalize numpy scalar/array values for strict, portable JSON reports.

    Avoid rounding or modifying physics data during an actual simulation; this
    applies only to diagnostics/report serialization, never to the policy.
    """
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def strict_json_dumps(value, **kwargs):
    return json.dumps(json_safe(value), allow_nan=False, **kwargs)


def atomic_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.partial')
    with temp.open('w', encoding='utf-8') as f:
        f.write(strict_json_dumps(obj, indent=2, sort_keys=True))
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def atomic_copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.with_name(dst.name + '.partial')
    try:
        shutil.copy2(src, temp)
        os.replace(temp, dst)
    finally:
        temp.unlink(missing_ok=True)


def guard_output(path):
    p = path.resolve()
    for protected in PROTECTED:
        if p == protected.resolve() or protected.resolve() in p.parents:
            raise ValueError(f'REFUSING to write inside protected folder: {p}')
    if p == SOURCE_MODEL.resolve():
        raise ValueError('Refusing to overwrite Nexto')
    return p


def safe_load(path):
    return torch.load(path, map_location='cpu', weights_only=True)


def actor_from(path, device='cpu'):
    if not path.is_file():
        raise FileNotFoundError(path)
    model = torch.jit.load(str(SOURCE_MODEL), map_location=device)
    checkpoint = safe_load(path)
    if 'actor' not in checkpoint:
        raise ValueError(f'Not a native Nexto checkpoint: {path}')
    model.load_state_dict(checkpoint['actor'], strict=True)
    model.eval()
    return model


def action_greedy(actor, view, device='cpu'):
    q,k,m = unpack_obs(view, device)
    with torch.inference_mode():
        return int(actor_logits(actor, q,k,m).argmax(-1).item())


def outcome_points(outcomes):
    total = sum(outcomes.get(x, 0) for x in ('ours','nexto','draw'))
    return (outcomes.get('ours',0) + 0.5*outcomes.get('draw',0)) / max(1,total)


def verdict(candidate_nexto, champion_nexto, direct, *, loss_margin=.10,
            gain_margin=.04, min_h2h=.55):
    """Conservative policy for automated promotions; scores include draws as halves.
    Bad => rejected and blacklisted; ambiguous => rejected without promotion too.
    """
    c, b, h = map(outcome_points, (candidate_nexto,champion_nexto,direct))
    if c < b-loss_margin or h < 0.45:
        return 'REJECT', f'performance dropped: candidate_vs_nexto={c:.3f}, champion={b:.3f}, h2h={h:.3f}'
    if c >= b+gain_margin and h >= min_h2h and direct.get('ours',0) > direct.get('nexto',0):
        return 'PROMOTE', f'competitive improvement: candidate={c:.3f} vs champion={b:.3f}; head2head={h:.3f}'
    return 'INCONCLUSIVE', f'not a proven improvement: candidate={c:.3f}, champion={b:.3f}, head2head={h:.3f}'


def scenarios_for(seed, games):
    """Mix randomized non-kickoff states with kickoffs; alternate team sides.
    Seeded independently from training, and paired across comparisons.
    """
    rng = random.Random(seed)
    result=[]
    for i in range(games):
        scenario = 'grounded' if (i % 4) != 0 else 'kickoff'
        result.append((int(rng.randrange(1, 2**31)), bool(i%2), scenario))
    return result


def initial_fingerprint(match):
    ball = np.asarray(match.state.ball.position).round(0).tolist()
    cars = [np.asarray(car.physics.position).round(0).tolist()
            for _,car in sorted(match.state.cars.items(), key=lambda it: bool(it[1].is_orange))]
    return strict_json_dumps([ball,cars])


def duel(actor, enemy, teacher, engine, test_cases, max_decisions, *, label='eval'):
    """Direct competing checkpoints, NOT a shadow/teacher-only proxy."""
    results=Counter(); ticks=0; touches=Counter(); fingerprints=[]
    for i, (seed, orange, scenario) in enumerate(test_cases):
        random.seed(seed); np.random.seed(seed % (2**32))
        match=Match(teacher,engine,training_side_orange=orange,scenarios=scenario)
        fingerprints.append(initial_fingerprint(match))
        for _ in range(max_decisions):
            a,b=match.observe()
            own=action_greedy(actor,a)
            other=action_greedy(enemy,b)
            _,done,winner=match.step(own,other,max_decisions)
            if done: break
        results[winner]+=1
        ticks+=match.decisions
        touches.update(match.contacts)
    log(f' {label}: W={results["ours"]} L={results["nexto"]} D={results["draw"]} '
        f'| score={outcome_points(results):.3f} | unique starts={len(set(fingerprints))}/{len(fingerprints)}')
    return {'outcomes':dict(results),'score':outcome_points(results),
            'decisions':ticks,'touches':dict(touches),
            'unique_starts':len(set(fingerprints)), 'episodes':len(fingerprints)}


def run_gate(candidate, champion, nexto, teacher, *, games, decisions, seed, engine_factory=None):
    if engine_factory is None:
        from rlgym.rocket_league.sim import RocketSimEngine
        engine_factory=lambda: RocketSimEngine(rlbot_delay=False)
    cases=scenarios_for(seed,games)
    engine=engine_factory()
    try:
        base=duel(champion,nexto,teacher,engine,cases,decisions,label='CHAMPION vs original Nexto')
        test=duel(candidate,nexto,teacher,engine,cases,decisions,label='CANDIDATE vs original Nexto')
        direct=duel(candidate,champion,teacher,engine,cases,decisions,label='CANDIDATE vs champion')
    finally:
        engine.close()
    dec,why=verdict(test['outcomes'],base['outcomes'],direct['outcomes'])
    if min(x['unique_starts'] for x in (base,test,direct)) < max(4,games//3):
        dec,why='INCONCLUSIVE','too many identical initial scenarios; not safe to promote'
    return {'verdict':dec,'reason':why,'candidate_vs_nexto':test,
            'champion_vs_nexto':base,'candidate_vs_champion':direct,
            'seed':seed,'games':games,'max_decisions':decisions,'created_utc':timestamp()}


def save_candidate(path, actor, critic, ao, co, decisions, parent_sha, cycle, seed):
    guard_output(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.partial')
    obj={'actor':{k:v.detach().cpu().clone() for k,v in actor.state_dict().items()},
         'critic':{k:v.detach().cpu().clone() for k,v in critic.state_dict().items()},
         'actor_optimizer':ao.state_dict(),'critic_optimizer':co.state_dict(),
         'timesteps':decisions, 'league_cycle':cycle,'parent_sha':parent_sha,'seed':seed,
         'saved_utc':timestamp()}
    try:
        torch.save(obj,temp)
        os.replace(temp,path)
    finally:
        temp.unlink(missing_ok=True)


def move_optim(optim,device):
    for state in optim.state.values():
        for k,v in state.items():
            if isinstance(v,torch.Tensor):
                state[k]=v.to(device)


def start_candidate(champion_path, candidate_path, device, cycle, seed, actor_lr=3e-6, critic_lr=2e-4):
    actor=actor_from(champion_path,device)
    critic=Critic().to(device)
    ao=torch.optim.Adam(actor.parameters(),lr=actor_lr)
    co=torch.optim.Adam(critic.parameters(),lr=critic_lr)
    current=0
    parent=sha256(champion_path)
    if candidate_path.exists():
        saved=safe_load(candidate_path)
        if saved.get('parent_sha')!=parent or saved.get('league_cycle')!=cycle:
            raise ValueError('Candidate checkpoint parent/cycle mismatch; refusing unsafe resume')
        actor.load_state_dict(saved['actor'])
        critic.load_state_dict(saved['critic'])
        ao.load_state_dict(saved['actor_optimizer']);co.load_state_dict(saved['critic_optimizer'])
        move_optim(ao,device);move_optim(co,device)
        current=int(saved['timesteps'])
        log(f'Resumed candidate cycle {cycle} after {current:,} decisions.')
    return actor,critic,ao,co,current,parent


def train_segment(args, actor,critic,ao,co,champion,nexto,teacher,
                  *, existing,current,cycle,parent_sha, save_hook=None):
    """True PPO: learner explores, opponent chosen between prior champion,
    refreshed learner snapshot (self-play), and original frozen Nexto.
    """
    from rlgym.rocket_league.sim import RocketSimEngine
    seed=args.seed+cycle*7919 + current
    random.seed(seed);np.random.seed(seed%(2**32));torch.manual_seed(seed)
    rng=np.random.default_rng(seed)
    snapshot=torch.jit.load(str(SOURCE_MODEL), map_location='cpu')  # frozen self-play snapshot
    snapshot.load_state_dict(actor.state_dict(),strict=True)
    snapshot.eval()
    for param in snapshot.parameters(): param.requires_grad_(False)
    engine=RocketSimEngine(rlbot_delay=False)
    match=Match(teacher,engine,training_side_orange=bool(rng.integers(0,2)),scenarios='grounded')
    enemy_mode='selfplay'
    counts=Counter()
    def reset_match():
        nonlocal match,enemy_mode
        q=float(rng.random())
        enemy_mode='selfplay' if q < .55 else ('champion' if q < .80 else 'nexto')
        match.our_orange=bool(rng.integers(0,2))
        match.scenarios='grounded' if rng.random()<.75 else 'kickoff'
        match.reset()
        counts['games']+=1
    reset_match()
    losses=[];reward_total=0; completed=0
    try:
        while completed < args.segment_decisions:
            n=min(args.rollout,args.segment_decisions-completed)
            obs_q=[];obs_k=[];obs_m=[];actions=[];old_logps=[];values=[];rewards=[];dones=[]
            for _ in range(n):
                own,opp=match.observe()
                action,logp,(q,k,m)=select_action(actor,own,args.device,temperature=args.temperature,sample=True)
                with torch.inference_mode():
                    val=float(critic(q,k).item())
                opponent={'selfplay':snapshot,'champion':champion,'nexto':nexto}[enemy_mode]
                other=action_greedy(opponent,opp)
                r,done,winner=match.step(action,other,args.episode_decisions)
                # Don't pay for raw ball-contact count: previous trainer incentivized touch-spam.
                our_touch=int(getattr(match.state.cars[match.ours],'ball_touches',0))
                other_touch=int(getattr(match.state.cars[match.opponent],'ball_touches',0))
                r=r-.12*bool(our_touch)+.04*bool(other_touch)
                obs_q.append(q[0].detach().cpu().numpy());obs_k.append(k[0].detach().cpu().numpy())
                obs_m.append(m[0].detach().cpu().numpy())
                actions.append(action);old_logps.append(logp);values.append(val)
                rewards.append(float(r));dones.append(bool(done))
                if done:
                    counts[winner]+=1
                    reset_match()
            with torch.no_grad():
                if dones[-1]:bootstrap=0.
                else:
                    our,_=match.observe();q,k,_=unpack_obs(our,args.device)
                    bootstrap=float(critic(q,k).item())
            gae,returns=discounted_gae(rewards,values,dones,bootstrap)
            gae=(gae-gae.mean())/(gae.std()+1e-8)
            Xq=torch.as_tensor(np.stack(obs_q),device=args.device)
            Xk=torch.as_tensor(np.stack(obs_k),device=args.device)
            Xm=torch.as_tensor(np.stack(obs_m),device=args.device)
            Xa=torch.as_tensor(actions,device=args.device,dtype=torch.long)
            Xold=torch.as_tensor(old_logps,device=args.device)
            Xadv=torch.as_tensor(gae,device=args.device)
            Xret=torch.as_tensor(returns,device=args.device)
            for _ in range(args.epochs):
                for ix in torch.randperm(n,device=args.device).split(args.minibatch):
                    logits=actor_logits(actor,Xq[ix],Xk[ix],Xm[ix])/args.temperature
                    dist=Categorical(logits=logits)
                    ratio=torch.exp(dist.log_prob(Xa[ix])-Xold[ix])
                    surrogate=torch.minimum(ratio*Xadv[ix],torch.clamp(ratio,1-args.clip,1+args.clip)*Xadv[ix]).mean()
                    with torch.no_grad():
                        reference=actor_logits(champion,Xq[ix].cpu(),Xk[ix].cpu(),Xm[ix].cpu()).to(args.device)/args.temperature
                    kl=F.kl_div(F.log_softmax(logits,-1),F.softmax(reference,-1),reduction='batchmean')
                    obj=-surrogate+args.anchor*kl-args.entropy*dist.entropy().mean()
                    ao.zero_grad(set_to_none=True);obj.backward()
                    torch.nn.utils.clip_grad_norm_(actor.parameters(),.5);ao.step()
                    co.zero_grad(set_to_none=True)
                    critic_loss=F.mse_loss(critic(Xq[ix],Xk[ix]),Xret[ix])
                    critic_loss.backward();torch.nn.utils.clip_grad_norm_(critic.parameters(),.5);co.step()
            completed+=n;current+=n;reward_total+=sum(rewards)
            save_candidate(existing,actor,critic,ao,co,current,parent_sha,cycle,seed)
            log(f'cycle {cycle} decisions {current:,}/{args.segment_decisions:,} | '
                f'reward {np.mean(rewards):+.4f} | KL {kl.item():.4f} | '
                f'games {counts["games"]} | modes selfplay/champion/Nexto (55/25/20%)')
            if save_hook:
                save_hook(current)
    finally:
        engine.close()
    return current,{'rollout_mean_reward':reward_total/max(1,completed),
                    'episodes':dict(counts), 'decisions':completed}


class BackupClock:
    def __init__(self, folder, interval_minutes, clock=None):
        self.folder=folder
        self.interval=interval_minutes*60
        self.clock=clock or time.monotonic
        self.next_due=self.clock()+self.interval
        self.folder.mkdir(parents=True,exist_ok=True)

    def snapshot(self, candidate, champion,cycle,steps,force=False):
        now=self.clock()
        if not force and now<self.next_due:return []
        files=[]
        suffix=f'{timestamp()}_cycle{cycle:04d}_steps{steps:09d}'
        for label,source in [('candidate',candidate),('champion',champion)]:
            if source.exists():
                target=self.folder/f'{suffix}_{label}.pt'
                atomic_copy(source,target);files.append(target)
        self.next_due=now+self.interval
        log('Timestamped safety backups: '+', '.join(p.name for p in files))
        return files


def log_decision(folder,record):
    path=folder/'history.jsonl'
    with path.open('a',encoding='utf8') as f:
        f.write(strict_json_dumps(record,sort_keys=True)+'\n')
        f.flush();os.fsync(f.fileno())


@contextmanager
def exclusive_league_lock(data):
    """Process-scoped OS lock; releases automatically even after a crash."""
    data.mkdir(parents=True,exist_ok=True)
    lockfile=data/'.training.lock'
    with lockfile.open('a+b') as f:
        f.seek(0);f.write(b'0');f.flush();f.seek(0)
        if os.name=='nt':
            import msvcrt
            try: msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc: raise RuntimeError('Another AutoLeague is running for this data-dir') from exc
            try: yield
            finally:
                f.seek(0)
                msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            try: fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc: raise RuntimeError('Another AutoLeague is running for this data-dir') from exc
            try: yield
            finally: fcntl.flock(f.fileno(),fcntl.LOCK_UN)


def initialize(data,source):
    data=guard_output(data)
    data.mkdir(parents=True,exist_ok=True)
    champion=data/'champion.pt'
    progress=data/'league_state.json'
    if not progress.exists():
        if champion.exists():
            raise RuntimeError('Found champion.pt without league_state.json; refusing to reset or overwrite it')
        if not source.is_file():
            raise FileNotFoundError(f'Missing source {source}. Keep your original checkpoint safe.')
        saved=safe_load(source)
        if 'actor' not in saved:raise ValueError('Source is not a native Nexto checkpoint')
        atomic_copy(source,champion)
        state={'version':1,'cycle':1,'champion_origin':str(source.resolve()),
               'champion_sha':sha256(champion),'promotions':0,'initialized_utc':timestamp(),
               'phase':'train'}
        atomic_json(progress,state)
        log('Created independent LEAGUE CHAMPION from '+str(source))
    else:
        if not champion.is_file():raise RuntimeError('Missing champion.pt; restore from backups before continuing')
        state=json.loads(progress.read_text(encoding='utf-8'))
        if state.get('phase')=='promoting':
            # Transactional recovery if machine powered off after file replacement but
            # before updated state.json. Never guess which checkpoint is best.
            candidate=data/'candidate.pt'
            old_sha=state['champion_sha']
            desired_sha=state['pending_sha']
            current_sha=sha256(champion)
            if current_sha==old_sha:
                if not candidate.is_file() or sha256(candidate)!=desired_sha:
                    raise RuntimeError('Interrupted promotion: candidate missing/mismatched; manual recovery required')
                atomic_copy(candidate,champion)
                current_sha=sha256(champion)
            if current_sha!=desired_sha:
                raise RuntimeError('Interrupted promotion: champion SHA changed unexpectedly')
            state['champion_sha']=desired_sha
            state['promotions']+=1
            state['cycle']+=1
            state['phase']='train'
            state['last_decision']='PROMOTE'
            state.pop('pending_sha',None)
            atomic_json(progress,state)
        if sha256(champion)!=state['champion_sha']:
            raise RuntimeError('CHAMPION SHA mismatch; refusing to start with an altered checkpoint')
    return champion,progress,state


def blacklist(folder,checkpoint,reason,cycle):
    digest=sha256(checkpoint)
    file=folder/'blacklist.json'
    record=json.loads(file.read_text(encoding='utf8')) if file.exists() else {}
    record[digest]={'utc':timestamp(),'reason':reason,'cycle':cycle}
    atomic_json(file,record)
    archived=folder/'rejected'/f'{timestamp()}_cycle{cycle:04d}_{digest[:12]}.pt'
    atomic_copy(checkpoint,archived)
    log(f'BLACKLISTED {digest[:12]} reason: {reason}; archived {archived.name}')
    return digest


def ensure_not_blacklisted(folder,checkpoint):
    file=folder/'blacklist.json'
    if file.exists() and sha256(checkpoint) in json.loads(file.read_text(encoding='utf8')):
        raise RuntimeError('This exact candidate hash is blacklisted; not promoting it.')


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=DEFAULT_SOURCE)
    p.add_argument('--data-dir',type=Path,default=DATA)
    p.add_argument('--device',choices=['cpu','cuda:0'],default='cpu')
    p.add_argument('--segment-decisions',type=int,default=8192)
    p.add_argument('--rollout',type=int,default=512)
    p.add_argument('--minibatch',type=int,default=128)
    p.add_argument('--epochs',type=int,default=2)
    p.add_argument('--episode-decisions',type=int,default=450)
    p.add_argument('--eval-decisions',type=int,default=750)
    p.add_argument('--eval-games',type=int,default=40)
    p.add_argument('--seed',type=int,default=20261009)
    p.add_argument('--backup-minutes',type=int,default=5)
    p.add_argument('--max-cycles',type=int,default=0,help='0=keep going until Ctrl+C')
    p.add_argument('--actor-lr',type=float,default=3e-6)
    p.add_argument('--critic-lr',type=float,default=2e-4)
    p.add_argument('--anchor',type=float,default=.6)
    p.add_argument('--entropy',type=float,default=.001)
    p.add_argument('--clip',type=float,default=.10)
    p.add_argument('--temperature',type=float,default=.9)
    p.add_argument('--replay-interval-minutes',type=int,default=60)
    p.add_argument('--replay-max-files',type=int,default=3)
    p.add_argument('--no-replays',action='store_true')
    p.add_argument('--preflight',action='store_true',help='Verify config/models; do not train')
    p.add_argument('--no-promote',action='store_true',help='Smoke-test only: never promote a candidate')
    return p


def validate_args(args):
    if min(args.segment_decisions,args.rollout,args.minibatch,args.epochs,args.episode_decisions,
           args.eval_decisions,args.eval_games,args.backup_minutes,args.replay_interval_minutes) < 1:
        raise ValueError('Training counts, eval games and backup intervals must be positive')
    if args.segment_decisions<args.rollout:raise ValueError('--segment-decisions must be >= --rollout')
    if not (0<args.clip<1 and args.temperature>0 and args.actor_lr>0 and args.critic_lr>0 and args.anchor>=0):
        raise ValueError('Invalid optimizer settings')
    if args.device=='cuda:0' and not torch.cuda.is_available():raise ValueError('CUDA unavailable')
    guard_output(args.data_dir)
    if args.max_cycles<0 or args.replay_max_files<0:raise ValueError('Invalid cycles/replay count')


def main(argv=None):
    args=parser().parse_args(argv)
    validate_args(args)
    torch.set_num_threads(2)
    if args.preflight:
        log('Checking original Nexto and source, without changing checkpoint files...')
        teacher=NextoTeacher('cpu')
        assert len(list(teacher.actor.parameters()))>0
        source=args.source if not (args.data_dir/'champion.pt').exists() else args.data_dir/'champion.pt'
        model=actor_from(source,args.device)
        from rlgym.rocket_league.sim import RocketSimEngine
        engine=RocketSimEngine(rlbot_delay=False)
        try:
            m=Match(teacher,engine,scenarios='grounded')
            a,b=m.observe()
            own=action_greedy(model,a,args.device)
            other=action_greedy(teacher.actor,b)
            m.step(own,other,3)
            # Exercise the evaluator's exact previously crashing JSON path too.
            fingerprint = initial_fingerprint(m)
            assert len(json.loads(fingerprint)) == 2
            strict_json_dumps({'fingerprint': fingerprint,
                               'test_np_float32': np.float32(1.25),
                               'test_np_int64': np.int64(2)})
            if len(m.state.cars)!=2:
                raise RuntimeError('Unexpected non-1v1 simulator state')
        finally:
            engine.close()
        log(f'REAL ROCKETSIM PREFLIGHT PASSED: source={source}; SHA256={sha256(source)[:16]}')
        log('Note: training supports 1v1 only. 1v2 and 1v3 are DISABLED.')
        return 0
    with exclusive_league_lock(args.data_dir):
        return run_locked(args)


def run_locked(args):
    champion_path,progress_path,state=initialize(args.data_dir,args.source)
    backups=BackupClock(args.data_dir/'backups',args.backup_minutes)
    candidate_path=args.data_dir/'candidate.pt'
    backups.snapshot(candidate_path,champion_path,state['cycle'],0,force=True)
    replay_worker=None
    if not args.no_replays:
        try:
            from league_replays import ReplayWorker
            replay_worker=ReplayWorker(ROOT,args.data_dir,args.replay_interval_minutes*60,args.replay_max_files)
            replay_worker.maybe_start(force=True)
        except Exception as exc:
            log(f'Replays unavailable ({exc}); training continues without downloaded replays.')
    log('SAFE AutoLeague: 1v1 PPO selfplay + frozen Nexto + historical champion; use Ctrl+C to stop.')
    log('Protected source and data/native_nexto are never overwritten. No automatic 1v2/1v3.')
    teacher=NextoTeacher('cpu')
    nexto=teacher.actor
    cycle_done=0
    while args.max_cycles==0 or cycle_done<args.max_cycles:
        state=json.loads(progress_path.read_text(encoding='utf8'))
        cycle=int(state['cycle'])
        log(f'=== CYCLE {cycle}: champion={sha256(champion_path)[:12]} ===')
        if candidate_path.is_file():
            old=safe_load(candidate_path)
            if old.get('league_cycle')!=cycle:
                dest=args.data_dir/'interrupted'/f'{timestamp()}_cycle{old.get("league_cycle",0)}.pt'
                atomic_copy(candidate_path,dest)
                candidate_path.unlink()
                log(f'Preserved previous-cycle candidate in {dest.name}; starting current cycle clean.')
        effective_lr=args.actor_lr*float(state.get('actor_lr_scale',1.0))
        actor,critic,ao,co,current,parent=start_candidate(champion_path,candidate_path,args.device,cycle,args.seed+cycle,actor_lr=effective_lr,critic_lr=args.critic_lr)
        log(f'Conservative actor learning rate: {effective_lr:.2g}')
        champion=actor_from(champion_path,'cpu')
        while current<args.segment_decisions:
            n=min(args.segment_decisions-current,args.rollout*max(1,min(8,(args.segment_decisions-current+args.rollout-1)//args.rollout)))
            subargs=argparse.Namespace(**vars(args));subargs.segment_decisions=n
            current,stats=train_segment(subargs,actor,critic,ao,co,champion,nexto,teacher,
                existing=candidate_path,current=current,cycle=cycle,parent_sha=parent,
                save_hook=lambda steps:backups.snapshot(candidate_path,champion_path,cycle,steps))
            if replay_worker:replay_worker.maybe_start()
        backups.snapshot(candidate_path,champion_path,cycle,current,force=True)
        log(f'Evaluating cycle {cycle} in independent seeded matches...')
        report=run_gate(actor,champion,nexto,teacher,games=args.eval_games,
                        decisions=args.eval_decisions,seed=args.seed+100003*cycle)
        report['cycle']=cycle;report['candidate_sha']=sha256(candidate_path)
        report['champion_sha_before']=sha256(champion_path)
        decision=report['verdict']
        if args.no_promote:
            decision='INCONCLUSIVE'
            report['verdict']=decision
            report['reason']='--no-promote smoke evaluation: candidate never accepted'
        if decision=='PROMOTE':
            ensure_not_blacklisted(args.data_dir,candidate_path)
            backups.snapshot(candidate_path,champion_path,cycle,current,force=True)
            # Two-phase promotion: the state announces the intended checkpoint first.
            # initialize() can finish safely if interrupted between these writes.
            state['phase']='promoting'
            state['pending_sha']=sha256(candidate_path)
            atomic_json(progress_path,state)
            atomic_copy(candidate_path,champion_path)
            state['champion_sha']=sha256(champion_path)
            state['promotions']+=1
            state.pop('pending_sha',None)
            log('PROMOTED new champion: '+report['reason'])
        else:
            if decision=='REJECT':
                blacklist(args.data_dir,candidate_path,report['reason'],cycle)
                streak=int(state.get('failed_streak',0))+1
                state['failed_streak']=streak
                state['actor_lr_scale']=max(.20, .7**min(streak,5))
                log(f'ROLLBACK: candidate blacklisted; next actor LR scale={state["actor_lr_scale"]:.2f}')
            else:
                dest=args.data_dir/'inconclusive'/f'{timestamp()}_cycle{cycle:04d}.pt'
                atomic_copy(candidate_path,dest)
                log('INCONCLUSIVE: champion unchanged; candidate archived, not blacklisted.')
        if decision=='PROMOTE':
            state['failed_streak']=0
            state['actor_lr_scale']=1.0
        report['champion_sha_after']=sha256(champion_path)
        atomic_json(args.data_dir/'reports'/f'cycle{cycle:04d}_{timestamp()}.json',report)
        log_decision(args.data_dir,report)
        # State cycle advances BEFORE deleting old candidate. Interrupted cleanup
        # is handled at next startup without ever using stale candidate weights.
        state['cycle']=cycle+1;state['phase']='train';state['last_decision']=decision
        atomic_json(progress_path,state)
        candidate_path.unlink(missing_ok=True)
        cycle_done+=1
        if replay_worker:replay_worker.maybe_start()
    log(f'Finished {cycle_done} cycles; champion: {champion_path}')
    return 0


if __name__=='__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log('Stopped by Ctrl+C. Champion safe. Candidate resume state saved at last completed rollout.')
        sys.exit(130)
    except Exception as exc:
        log(f'ERROR: {type(exc).__name__}: {exc}')
        raise
