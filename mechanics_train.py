"""Isolated PPO fine-tuning of existing Nexto-based actor for a *single* mechanic.

This NEVER overwrites data/native_nexto/best_10k.pt or original Nexto.
Stages use a frozen 10K actor KL anchor to reduce catastrophic forgetting.
Rollout = one RocketSim engine, so this is correctness-first, not GigaLearn speed.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import random
import shutil
import numpy as np
import torch
import torch.nn.functional as F
from torch.distributions import Categorical

from mechanics_scenarios import STAGES
from mechanics_tasks import MechanicsMatch
from native_nexto import (Critic, discounted_gae, unpack_obs, actor_logits,
                          select_action, SOURCE_MODEL)
from nexto_teacher import NextoTeacher

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT / 'data' / 'native_nexto' / 'best_10k.pt'


def load_actor(source: Path, device: str):
    actor = torch.jit.load(str(SOURCE_MODEL), map_location=device)
    state = torch.load(source, map_location='cpu', weights_only=True)
    if 'actor' not in state:
        raise ValueError(f'{source} must be a native checkpoint with an actor key')
    actor.load_state_dict(state['actor'], strict=True)
    actor.eval()
    return actor


def save(path, stage, source, step, actor, critic, ao, co, stats):
    path.parent.mkdir(parents=True, exist_ok=True)
    output = {'actor': {k:v.detach().cpu() for k,v in actor.state_dict().items()},
              'critic': {k:v.detach().cpu() for k,v in critic.state_dict().items()},
              'actor_optimizer': ao.state_dict(), 'critic_optimizer': co.state_dict(),
              'timesteps': step, 'mechanic': stage, 'source': str(source.resolve()),
              'last_stats': stats}
    temp = path.with_suffix('.partial')
    torch.save(output, temp)
    os.replace(temp, path)


def make_parser():
    p = argparse.ArgumentParser(description='Native Nexto mechanical practice (experiment)')
    p.add_argument('--stage', choices=STAGES, required=True)
    p.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    p.add_argument('--steps', type=int, default=1024, help='cumulative specialist decisions')
    p.add_argument('--rollout', type=int, default=256)
    p.add_argument('--minibatch', type=int, default=64)
    p.add_argument('--epochs', type=int, default=2)
    p.add_argument('--episode-decisions', type=int, default=100)
    p.add_argument('--opponent', choices=('passive', 'nexto'), default='passive')
    p.add_argument('--device', choices=('cpu','cuda:0'), default='cpu')
    p.add_argument('--actor-lr', type=float, default=3e-6)
    p.add_argument('--critic-lr', type=float, default=2e-4)
    p.add_argument('--anchor', type=float, default=.5)
    p.add_argument('--clip', type=float, default=.12)
    p.add_argument('--entropy', type=float, default=.001)
    p.add_argument('--temperature', type=float, default=1.)
    p.add_argument('--seed', type=int, default=20261009)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--checkpoint', type=Path, default=None,
                   help='defaults to data/mechanics/<stage>/last.pt')
    return p


def _move_optim_state(optim, device):
    for state in optim.state.values():
        for k, v in state.items():
            if isinstance(v, torch.Tensor):
                state[k] = v.to(device)


def train(args):
    if min(args.steps,args.rollout,args.minibatch,args.epochs,args.episode_decisions) < 1:
        raise ValueError('steps, rollout, minibatch, epochs, episode-decisions must all be positive')
    if args.actor_lr<=0 or args.critic_lr<=0 or args.anchor<0 or args.temperature<=0:
        raise ValueError('Invalid optimizer parameters')
    if args.device=='cuda:0' and not torch.cuda.is_available():
        raise ValueError('CUDA requested but unavailable')
    source = args.source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f'BASELINE MISSING: {source}. Run from project root and check best_10k.pt')
    checkpoint = args.checkpoint or ROOT/'data'/'mechanics'/args.stage/'last.pt'
    if checkpoint.resolve() == source or checkpoint.resolve() == SOURCE_MODEL.resolve():
        raise ValueError('Cannot overwrite source or original Nexto model')
    if checkpoint.exists() and not args.resume:
        raise FileExistsError(f'{checkpoint} already exists. Use --resume or another --checkpoint')
    torch.set_num_threads(2)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    from rlgym.rocket_league.sim import RocketSimEngine
    actor = load_actor(source, args.device)
    anchor_actor = load_actor(source, 'cpu')
    anchor_actor.eval()
    for parameter in anchor_actor.parameters():
        parameter.requires_grad_(False)
    teacher = NextoTeacher('cpu')
    critic = Critic().to(args.device)
    ao = torch.optim.Adam(actor.parameters(), lr=args.actor_lr)
    co = torch.optim.Adam(critic.parameters(), lr=args.critic_lr)
    current = 0
    if args.resume:
        if not checkpoint.exists():
            raise FileNotFoundError(f'Cannot resume; {checkpoint} missing')
        old = torch.load(checkpoint, weights_only=True, map_location='cpu')
        if old.get('mechanic') != args.stage or str(source) != old.get('source'):
            raise ValueError('Resume stage/source mismatch; refusing unsafe load')
        actor.load_state_dict(old['actor'])
        critic.load_state_dict(old['critic'])
        ao.load_state_dict(old['actor_optimizer'])
        co.load_state_dict(old['critic_optimizer'])
        _move_optim_state(ao, args.device)
        _move_optim_state(co, args.device)
        current = int(old['timesteps'])
    if current >= args.steps:
        print(f'Already at {current} / {args.steps}; increase --steps to continue')
        return
    print(f'STAGE={args.stage} | source={source} | output={checkpoint}\n'
          f'Native Nexto actor + frozen {source.name} KL anchor | device={args.device}\n'
          'This is isolated mechanical practice; final competitive policy is NOT overwritten.', flush=True)
    rng = np.random.default_rng(args.seed)
    engine = RocketSimEngine(rlbot_delay=False)
    match = MechanicsMatch(teacher, engine, args.stage, seed=args.seed,
                          orange=False, opponent=args.opponent, max_steps=args.episode_decisions)
    try:
        while current < args.steps:
            ql, kl, ml, al, ol, vl, rl, dl = [], [], [], [], [], [], [], []
            count = min(args.rollout, args.steps-current)
            solved, completed, all_rewards = 0, 0, []
            for _ in range(count):
                us, them = match.observe()
                aid, logp, (q, kv, mask) = select_action(actor, us, args.device,
                                                        temperature=args.temperature, sample=True)
                with torch.no_grad():
                    value = float(critic(q, kv).item())
                if args.opponent == 'nexto':
                    logits = teacher.logits([(them[1], them[2], them[3])])
                    their_id = int(logits[0].argmax())
                else:
                    their_id = 0
                reward, done, success = match.step(aid, their_id)
                ql.append(q[0].cpu().numpy()); kl.append(kv[0].cpu().numpy()); ml.append(mask[0].cpu().numpy())
                al.append(aid); ol.append(logp); vl.append(value); rl.append(reward); dl.append(done)
                if done:
                    completed += 1
                    solved += int(success)
                    match.reset(orange=bool(rng.integers(0, 2)))
            with torch.no_grad():
                if dl[-1]:
                    boot = 0.
                else:
                    us, _ = match.observe()
                    q, kv, _ = unpack_obs(us, args.device)
                    boot = float(critic(q, kv).item())
            ad, returns = discounted_gae(rl, vl, dl, boot)
            ad = (ad-ad.mean())/(ad.std()+1e-8)
            Xq = torch.as_tensor(np.stack(ql), device=args.device)
            Xkv = torch.as_tensor(np.stack(kl), device=args.device)
            Xm = torch.as_tensor(np.stack(ml), device=args.device)
            Xa = torch.tensor(al, dtype=torch.long, device=args.device)
            Xol = torch.tensor(ol, dtype=torch.float32, device=args.device)
            Xad = torch.tensor(ad, dtype=torch.float32, device=args.device)
            Xret = torch.tensor(returns, dtype=torch.float32, device=args.device)
            for _ in range(args.epochs):
                for ids in torch.randperm(count, device=args.device).split(args.minibatch):
                    logits = actor_logits(actor, Xq[ids], Xkv[ids], Xm[ids]) / args.temperature
                    dist = Categorical(logits=logits)
                    lp = dist.log_prob(Xa[ids])
                    ratio = torch.exp(lp-Xol[ids])
                    objective = torch.minimum(ratio*Xad[ids],
                          torch.clamp(ratio,1-args.clip,1+args.clip)*Xad[ids]).mean()
                    with torch.no_grad():
                        reference = actor_logits(anchor_actor, Xq[ids].cpu(),
                                                 Xkv[ids].cpu(), Xm[ids].cpu()).to(args.device)
                    kl_anchor = F.kl_div(F.log_softmax(logits,-1),
                        F.softmax(reference/args.temperature,-1), reduction='batchmean')
                    loss = -objective+args.anchor*kl_anchor-args.entropy*dist.entropy().mean()
                    ao.zero_grad(set_to_none=True)
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(actor.parameters(), 0.5)
                    ao.step()
                    mse = F.mse_loss(critic(Xq[ids], Xkv[ids]),Xret[ids])
                    co.zero_grad(set_to_none=True)
                    mse.backward()
                    torch.nn.utils.clip_grad_norm_(critic.parameters(), 0.5)
                    co.step()
            current += count
            stats = {'completed_episodes': completed, 'successful_episodes':solved,
                     'mean_reward':float(np.mean(rl)), 'anchor_kl':float(kl_anchor.detach()),
                     'actor_loss':float(loss.detach())}
            save(checkpoint,args.stage,source,current,actor,critic,ao,co,stats)
            if current % 1024 == 0 or current == args.steps:
                snapshot = checkpoint.parent / f'snapshot_{current:08d}.pt'
                shutil.copy2(checkpoint,snapshot)
            print(f'{args.stage} {current:,}/{args.steps:,} | completions {solved}/{completed}'
                  f' | reward/decision {stats["mean_reward"]:+.4f} | anchor KL {stats["anchor_kl"]:.4f}', flush=True)
        print('Finished. Run MECH_EVALUATE.bat; do NOT overwrite best_10k.pt automatically.')
    finally:
        engine.close()


if __name__=='__main__':
    train(make_parser().parse_args())
