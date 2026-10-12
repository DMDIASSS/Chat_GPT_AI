"""Slater v0.2.5: first *isolated* Cycle 9-initialized 1v1 PPO smoke experiment.

Uses native Nexto 90 actions, TeamObserver, RocketSimEngine, a frozen
Cycle 9 opponent and a frozen independent Cycle 9 teacher KL anchor.
No replay data, PPO checkpoint promotion, champion updates, or source changes.

Windows project-root example:
.venv\\Scripts\\python.exe slater_cycle9_native_ppo_v025.py --updates 2 --rollout-steps 256 --eval-episodes 12 --out data/isolated/cycle9_ppo_v025_smoke01.pt

The first run validates integration and policy optimization. It is NOT proof
that a stronger bot was trained; evaluate it on separate longer matches first.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from torch.distributions import Categorical

ACTION_REPEAT = 8
S_HORIZON = 180  # 12 sec at 120 Hz, for smoke-only episodes
OBS_Q = (1, 32)
OBS_KV = (41, 24)
OBS_MASK = (41,)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def check_output(path: str | Path, root: Path, suffix: str = '.pt') -> Path:
    allowed = (root / 'data' / 'isolated').resolve()
    dst = Path(path).resolve()
    if not dst.is_relative_to(allowed) or dst.suffix != suffix:
        raise ValueError(f'New {suffix} output must be under {allowed}: {dst}')
    if dst.exists() or dst.with_name(dst.name + '.partial').exists():
        raise FileExistsError(f'Output or partial already exists: {dst}')
    return dst


def logits_of(model, obs):
    output = model(obs)
    logits = output[0] if isinstance(output, tuple) else output
    if tuple(logits.shape)[-1:] != (90,) or not torch.isfinite(logits).all():
        raise RuntimeError(f'Bad native Nexto logits: {tuple(logits.shape)}')
    return logits


class ValueNet(nn.Module):
    """Small independent critic using the preflight's native observation layout."""
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(32 + 24 + 24, 192), nn.Tanh(),
            nn.Linear(192, 192), nn.Tanh(), nn.Linear(192, 1),
        )

    def forward(self, observations):
        q, kv, mask = observations
        valid = (1. - mask).unsqueeze(-1).clamp(0., 1.)
        pooled = (kv * valid).sum(dim=1) / valid.sum(dim=1).clamp_min(1.)
        # Equivalent semantic ball-token selection as in existing slater_research.train_scenarios.
        ball_idx = torch.argmax(kv[:, :, 3], dim=1)
        ball = kv[torch.arange(kv.shape[0], device=kv.device), ball_idx]
        return self.net(torch.cat((q[:, 0], pooled, ball), dim=-1)).squeeze(-1)


def to_tensors(obs, device='cpu'):
    return tuple(torch.as_tensor(a[None], dtype=torch.float32, device=device) for a in obs)


def read_obs(state, previous, observer, side='blue-0'):
    data = observer.observe(state, previous)
    if side not in data:
        raise RuntimeError(f'Missing observer side {side}: {list(data)}')
    obs = tuple(np.asarray(v, dtype=np.float32).copy() for v in data[side])
    if tuple(v.shape for v in obs) != (OBS_Q, OBS_KV, OBS_MASK):
        raise RuntimeError(f'Unexpected Nexto observation shapes {tuple(v.shape for v in obs)}')
    if not all(np.isfinite(v).all() for v in obs):
        raise FloatingPointError('Nonfinite observation')
    return obs


def gae(rewards, values, dones, bootstrap, gamma=.995, lam=.95):
    r = np.asarray(rewards, dtype=np.float32)
    v = np.asarray(values, dtype=np.float32)
    d = np.asarray(dones, dtype=np.float32)
    if not (len(r) == len(v) == len(d) and len(r)):
        raise ValueError('Bad GAE vector lengths')
    adv = np.zeros_like(r)
    accum = 0.
    for i in range(len(r)-1, -1, -1):
        next_value = v[i+1] if i+1 < len(v) else float(bootstrap)
        keep = 1. - d[i]
        delta = r[i] + gamma * keep * next_value - v[i]
        accum = delta + gamma * lam * keep * accum
        adv[i] = accum
    return adv, adv + v


class Native1v1:
    """Student blue vs frozen Cycle 9 orange, true RocketSim kickoff states."""
    def __init__(self, actions, observer, opponent, max_steps=S_HORIZON, device='cpu'):
        from rlgym.rocket_league.sim import RocketSimEngine
        from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator, KickoffMutator
        self.engine = RocketSimEngine(rlbot_delay=False)
        self.teams = FixedTeamSizeMutator(blue_size=1, orange_size=1)
        self.kickoff = KickoffMutator()
        self.actions = actions
        self.observer = observer
        self.opponent = opponent
        self.max_steps = max_steps
        self.device = device
        self.previous = {}
        self.state = None
        self.obs = None
        self.t = 0
        self.total_reward = 0.
        self.touches = 0
        self.opponent_touches = 0

    def reset(self, seed: int):
        # KickoffMutator randomizes spawn locations; reseed per episode for matched evaluation.
        random.seed(int(seed))
        state = self.engine.create_base_state()
        self.teams.apply(state, {})
        self.kickoff.apply(state, {})
        self.state = self.engine.set_state(state, {})
        self.previous = {}
        self.t = 0
        self.total_reward = 0.
        self.touches = 0
        self.opponent_touches = 0
        self.obs = read_obs(self.state, self.previous, self.observer)
        return self.obs

    def step(self, student_action: int):
        before_ball_y = float(self.state.ball.position[1])
        before_dist = float(np.linalg.norm(self.state.cars['blue-0'].physics.position - self.state.ball.position))
        other_view = read_obs(self.state, self.previous, self.observer, 'orange-0')
        with torch.no_grad():
            opponent_action = int(logits_of(self.opponent, to_tensors(other_view, self.device)).argmax(-1).item())
        blue = np.array(self.actions[int(student_action)], dtype=np.float32, copy=True)
        orange = np.array(self.actions[opponent_action], dtype=np.float32, copy=True)
        commands = {'blue-0': np.repeat(blue[None], ACTION_REPEAT, axis=0),
                    'orange-0': np.repeat(orange[None], ACTION_REPEAT, axis=0)}
        self.state = self.engine.step(commands, {})
        self.previous = {'blue-0': blue, 'orange-0': orange}
        self.t += 1
        car = self.state.cars['blue-0']
        ball = self.state.ball
        progress = float(np.clip((ball.position[1] - before_ball_y) / 500, -.5, .5))
        closing = float(np.clip((before_dist - np.linalg.norm(car.physics.position - ball.position))/500, -.5, .5))
        touch = int(car.ball_touches)
        other_touch = int(self.state.cars['orange-0'].ball_touches)
        self.touches += touch
        self.opponent_touches += other_touch
        goal = bool(self.state.goal_scored)
        outcome = (1 if ball.position[1] > 0 else -1) if goal else 0
        reward = .20 * progress + .07 * closing + .35 * touch - .002 + 10. * outcome
        self.total_reward += reward
        done = bool(goal or self.t >= self.max_steps)
        self.obs = read_obs(self.state, self.previous, self.observer)
        if not np.isfinite(reward):
            raise FloatingPointError('Nonfinite reward')
        return self.obs, float(reward), done, {
            'outcome': outcome, 'student_touches': self.touches,
            'opponent_touches': self.opponent_touches,
            'reward': self.total_reward, 'steps': self.t,
            'ball_y': float(ball.position[1]),
            'timeout': bool(not goal and done),
        }

    def close(self):
        self.engine.close()


def choose(actor, critic, obs, device, greedy=False):
    with torch.no_grad():
        tensors = to_tensors(obs, device)
        logits = logits_of(actor, tensors)
        dist = Categorical(logits=logits)
        action = logits.argmax(-1) if greedy else dist.sample()
        old_logp = dist.log_prob(action)
        v = critic(tensors)
    return int(action.item()), float(old_logp.item()), float(v.item())


def collect(actor, critic, env, rollout_steps, seed, device):
    rows = {'q': [], 'kv': [], 'mask': [], 'action': [], 'old_logp': [],
            'value': [], 'reward': [], 'done': []}
    completed = []
    obs = env.reset(seed)
    episode_seed = seed
    for _ in range(rollout_steps):
        action, logp, value = choose(actor, critic, obs, device)
        next_obs, reward, done, info = env.step(action)
        for key, x in zip(('q', 'kv', 'mask'), obs):
            rows[key].append(x)
        rows['action'].append(action)
        rows['old_logp'].append(logp)
        rows['value'].append(value)
        rows['reward'].append(reward)
        rows['done'].append(done)
        if done:
            completed.append(info)
            episode_seed += 1
            next_obs = env.reset(episode_seed)
        obs = next_obs
    with torch.no_grad():
        boot = float(critic(to_tensors(obs, device)).item())
    rows['adv'], rows['ret'] = gae(rows['reward'], rows['value'], rows['done'], boot)
    return rows, completed


def update(actor, teacher, critic, actor_opt, critic_opt, rows,
           epochs, minibatch, teacher_weight, seed, device):
    n = len(rows['action'])
    ts = {key: torch.as_tensor(np.stack(rows[key]), dtype=torch.float32, device=device)
          for key in ('q', 'kv', 'mask')}
    ts['action'] = torch.tensor(rows['action'], device=device, dtype=torch.long)
    ts['old_logp'] = torch.tensor(rows['old_logp'], device=device, dtype=torch.float32)
    ts['adv'] = torch.as_tensor(rows['adv'], device=device)
    ts['ret'] = torch.as_tensor(rows['ret'], device=device)
    ts['adv'] = (ts['adv'] - ts['adv'].mean()) / (ts['adv'].std(unbiased=False) + 1e-7)
    rng = np.random.default_rng(seed)
    losses = []
    for _ in range(epochs):
        for chunk in np.array_split(rng.permutation(n), max(1, math.ceil(n/minibatch))):
            inds = torch.as_tensor(chunk, dtype=torch.long, device=device)
            x = tuple(ts[k][inds] for k in ('q', 'kv', 'mask'))
            logits = logits_of(actor, x)
            with torch.no_grad():
                fixed_logits = logits_of(teacher, x)
            dist = Categorical(logits=logits)
            logp = dist.log_prob(ts['action'][inds])
            ratio = (logp - ts['old_logp'][inds]).exp()
            clipped = ratio.clamp(.85, 1.15)
            adv = ts['adv'][inds]
            surrogate = torch.minimum(ratio*adv, clipped*adv).mean()
            temp = 1.5
            kl = F.kl_div(F.log_softmax(logits/temp, dim=-1),
                          F.softmax(fixed_logits/temp, dim=-1),
                          reduction='batchmean') * (temp*temp)
            ent = dist.entropy().mean()
            actor_loss = -surrogate + teacher_weight * kl - .003 * ent
            if not torch.isfinite(actor_loss):
                raise FloatingPointError('Actor loss became nonfinite')
            actor_opt.zero_grad(set_to_none=True)
            actor_loss.backward()
            torch.nn.utils.clip_grad_norm_(actor.parameters(), .5)
            actor_opt.step()
            value = critic(x)
            value_loss = F.smooth_l1_loss(value, ts['ret'][inds])
            if not torch.isfinite(value_loss):
                raise FloatingPointError('Value loss became nonfinite')
            critic_opt.zero_grad(set_to_none=True)
            value_loss.backward()
            torch.nn.utils.clip_grad_norm_(critic.parameters(), .5)
            critic_opt.step()
            losses.append((float(actor_loss.detach().item()), float(value_loss.detach().item()),
                           float(kl.detach().item()), float(ent.detach().item()),
                           float((ratio.detach()-1).abs().gt(.15).float().mean().item())))
    a = np.mean(losses, axis=0)
    return dict(actor_loss=float(a[0]), value_loss=float(a[1]),
                teacher_kl=float(a[2]), entropy=float(a[3]), clip_fraction=float(a[4]))


def evaluate(actor, frozen_opponent, actions, observer, seeds, max_steps, device):
    env = Native1v1(actions, observer, frozen_opponent, max_steps=max_steps, device=device)
    metrics = []
    try:
        for ep_seed in seeds:
            obs = env.reset(ep_seed)
            while True:
                with torch.no_grad():
                    ai = int(logits_of(actor, to_tensors(obs, device)).argmax(-1).item())
                obs, _, done, info = env.step(ai)
                if done:
                    metrics.append(info)
                    break
    finally:
        env.close()
    return {
        'episodes': len(metrics),
        'wins': sum(x['outcome'] == 1 for x in metrics),
        'losses': sum(x['outcome'] == -1 for x in metrics),
        'timeouts': sum(x['outcome'] == 0 for x in metrics),
        'avg_student_touches': float(np.mean([x['student_touches'] for x in metrics])),
        'avg_opponent_touches': float(np.mean([x['opponent_touches'] for x in metrics])),
        'avg_return': float(np.mean([x['reward'] for x in metrics])),
        'avg_final_ball_y': float(np.mean([x['ball_y'] for x in metrics])),
        'avg_steps': float(np.mean([x['steps'] for x in metrics])),
    }


def save_create_only(output: Path, payload: dict):
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + '.partial')
    try:
        with tmp.open('xb') as stream:
            torch.save(payload, stream)
        if output.exists():
            raise FileExistsError(f'Output materialized during experiment: {output}')
        os.rename(tmp, output)  # Windows os.rename fails if target exists
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--updates', type=int, default=2)
    parser.add_argument('--rollout-steps', type=int, default=256)
    parser.add_argument('--eval-episodes', type=int, default=12)
    parser.add_argument('--max-episode-steps', type=int, default=S_HORIZON)
    parser.add_argument('--epochs', type=int, default=2)
    parser.add_argument('--minibatch', type=int, default=64)
    parser.add_argument('--actor-lr', type=float, default=3e-5)
    parser.add_argument('--critic-lr', type=float, default=2e-4)
    parser.add_argument('--teacher-weight', type=float, default=.08)
    parser.add_argument('--seed', type=int, default=20261011)
    parser.add_argument('--device', choices=('cpu',), default='cpu')
    parser.add_argument('--out', required=True)
    parser.add_argument('--report', default=None)
    args = parser.parse_args()
    if min(args.updates, args.rollout_steps, args.eval_episodes,
           args.max_episode_steps, args.epochs, args.minibatch) < 1:
        parser.error('Counts must be strictly positive')
    if not (0 < args.actor_lr <= 1e-3 and 0 < args.critic_lr <= 1e-2):
        parser.error('Learning rates out of safety bounds')
    if not (0 <= args.teacher_weight <= 1):
        parser.error('Teacher weight must be between 0 and 1')
    root = Path.cwd().resolve()
    target = check_output(args.out, root)
    report = check_output(args.report, root, '.json') if args.report is not None else None
    if report is not None and report == target:
        parser.error('Report and checkpoint cannot be same path')
    torch.set_num_threads(2)
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    np.random.seed(args.seed)
    device = torch.device(args.device)
    from slater_research.checkpoint import CYCLE9, CYCLE9_SHA, cycle9_pair
    from afk_team_research import TeamObserver
    from nexto_teacher import nexto_actions
    source = root / CYCLE9
    original_sha = sha256(source)
    if original_sha != CYCLE9_SHA:
        raise RuntimeError(f'Protected Cycle9 checkpoint SHA mismatch: {original_sha}')
    nexto_path = root / 'vendor/nexto/nexto-model.pt'
    nexto_sha = sha256(nexto_path)
    actor, teacher = cycle9_pair(root)
    actor.eval(); teacher.eval()
    for p in teacher.parameters():
        p.requires_grad_(False)
    if set(int(p.data_ptr()) for p in actor.parameters()) & set(int(p.data_ptr()) for p in teacher.parameters()):
        raise RuntimeError('Teacher/student parameter storage overlaps')
    # Use independent frozen opponent (same immutable teacher, no optimizer)
    lookup = nexto_actions()
    actions = np.stack([np.asarray(lookup[i], dtype=np.float32).reshape(8) for i in range(90)])
    if actions.shape != (90, 8) or not np.isfinite(actions).all():
        raise RuntimeError(f'Bad Nexto actions: {actions.shape}')
    critic = ValueNet().to(device)
    ao = torch.optim.Adam(actor.parameters(), lr=args.actor_lr)
    co = torch.optim.Adam(critic.parameters(), lr=args.critic_lr)
    original_actor_weights = [p.detach().clone() for p in actor.parameters()]
    original_teacher_weights = [p.detach().clone() for p in teacher.parameters()]
    observer = TeamObserver()
    seeds = [args.seed + 100000 + 37*i for i in range(args.eval_episodes)]
    print('EXPERIMENT Cycle9-native 1v1 PPO vs frozen Cycle9 opponent', flush=True)
    print('GUARDS source_sha', original_sha, 'nexto_sha', nexto_sha,
          'output', target, flush=True)
    began = time.perf_counter()
    before = evaluate(teacher, teacher, actions, observer, seeds, args.max_episode_steps, device)
    print('PRE_EVAL_FROZEN_CYCLE9', json.dumps(before, sort_keys=True), flush=True)
    env = Native1v1(actions, observer, teacher, max_steps=args.max_episode_steps, device=device)
    stats = []
    try:
        for i in range(args.updates):
            rows, completed = collect(actor, critic, env, args.rollout_steps,
                                      args.seed+10000+1000*i, device)
            info = update(actor, teacher, critic, ao, co, rows, args.epochs,
                          args.minibatch, args.teacher_weight, args.seed+i, device)
            info.update(update=i+1, transitions=args.rollout_steps,
                        finished_episodes=len(completed),
                        student_touches=sum(e['student_touches'] for e in completed),
                        opponent_touches=sum(e['opponent_touches'] for e in completed),
                        wins=sum(e['outcome']==1 for e in completed),
                        losses=sum(e['outcome']==-1 for e in completed))
            stats.append(info)
            print('UPDATE', json.dumps(info, sort_keys=True), flush=True)
    finally:
        env.close()
    after = evaluate(actor, teacher, actions, observer, seeds, args.max_episode_steps, device)
    print('POST_EVAL_STUDENT_VS_FROZEN_CYCLE9', json.dumps(after, sort_keys=True), flush=True)
    delta = math.sqrt(sum(float((p.detach()-o).square().sum().item())
                          for p,o in zip(actor.parameters(), original_actor_weights)))
    frozen_delta = math.sqrt(sum(float((p.detach()-o).square().sum().item())
                                 for p,o in zip(teacher.parameters(), original_teacher_weights)))
    if not math.isfinite(delta) or delta <= 1e-9:
        raise RuntimeError('Student policy parameters did not change')
    if frozen_delta != 0:
        raise RuntimeError(f'Frozen teacher modified unexpectedly: delta={frozen_delta}')
    if sha256(source) != original_sha or sha256(nexto_path) != nexto_sha:
        raise RuntimeError('Protected source model on disk changed')
    seconds = time.perf_counter() - began
    meta = dict(kind='cycle9_native_1v1_frozen_opponent_ppo_smoke_v025',
                warning='EXPERIMENT ONLY. NOT REPLAY TRAINING, NOT SELF-PLAY, NOT CERTIFIED BETTER. Do not promote.',
                source_cycle9_sha256=original_sha, source_nexto_sha256=nexto_sha,
                args=vars(args), pre_eval_frozen_cycle9=before,
                post_eval_student=after, updates=stats, env_decisions=args.updates*args.rollout_steps,
                student_delta_l2=delta, frozen_teacher_delta_l2=frozen_delta,
                seconds=seconds)
    payload = {'actor':actor.state_dict(), 'critic':critic.state_dict(),
               'actor_optimizer':ao.state_dict(), 'critic_optimizer':co.state_dict(),
               'source_sha':original_sha, 'meta':meta}
    save_create_only(target, payload)
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open('x', encoding='utf-8') as fp:
            json.dump(meta, fp, indent=2)
    print('SAVED_NEW_ISOLATED_CHECKPOINT', target, 'SHA256', sha256(target), flush=True)
    print('SUMMARY', json.dumps({
        'train_decisions':meta['env_decisions'], 'elapsed_seconds':seconds,
        'student_delta_l2':delta, 'teacher_delta_l2':frozen_delta,
        'frozen_cycle9_pre_eval':before, 'trained_candidate_post_eval':after,
        'source_cycle9_sha256':original_sha}, sort_keys=True), flush=True)
    print('ORIGINAL_CYCLE9_AND_NEXTO_SHA256_UNCHANGED; CHAMPION_AND_REPLAYS_UNTOUCHED', flush=True)
    print('NO_CHECKPOINT_PROMOTION. Small greedy eval samples cannot prove skill improvement.', flush=True)

if __name__ == '__main__':
    main()
