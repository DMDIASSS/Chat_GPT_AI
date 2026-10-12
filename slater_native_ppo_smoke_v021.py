"""Slater v0.2.1: isolated, from-scratch solo-shooting PPO smoke experiment.

IMPORTANT:
* Does not load, overwrite, promote, or train the Cycle 9/teacher/champion models.
* Does NOT train on replays, and is not Nexto/Slater Cycle 9 architecture-compatible.
* Experimental skill warmup / PPO-integration check, NOT competitive self-play.
* Torch, numpy, RLGym + RocketSim required; Windows: existing project .venv.

Run at PROJECT ROOT:
  .venv\\Scripts\\python.exe slater_native_ppo_smoke_v021.py --updates 2 \\
      --rollout-steps 768 --out data/isolated/native_ppo_v021_smoke_01.pt
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import time

import numpy as np
import torch
from torch import nn
from torch.distributions import Categorical

ACTION_REPEAT = 8
PHYSICS_HZ = 120
ACTION_NAMES = (
    'forward', 'left', 'right', 'soft_left', 'soft_right',
    'boost_forward', 'boost_left', 'boost_right',
    'reverse', 'reverse_slide_left', 'reverse_slide_right',
    'jump_boost', 'jump_boost_left', 'jump_boost_right', 'coast'
)
# Throttle, steer, pitch, yaw, roll, jump, boost, handbrake
ACTION_TABLE = np.array([
    [1, 0, 0, 0, 0, 0, 0, 0],
    [1, -1, 0, 0, 0, 0, 0, 0],
    [1, +1, 0, 0, 0, 0, 0, 0],
    [1, -.35, 0, 0, 0, 0, 0, 0],
    [1, +.35, 0, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 1, 0],
    [1, -.6, 0, 0, 0, 0, 1, 0],
    [1, +.6, 0, 0, 0, 0, 1, 0],
    [-1, 0, 0, 0, 0, 0, 0, 0],
    [-1, -1, 0, 0, 0, 0, 0, 1],
    [-1, +1, 0, 0, 0, 0, 0, 1],
    [1, 0, -1, 0, 0, 1, 1, 0],
    [1, -.6, -1, -.6, 0, 1, 1, 0],
    [1, +.6, -1, +.6, 0, 1, 1, 0],
    [0, 0, 0, 0, 0, 0, 0, 0],
], dtype=np.float32)
assert ACTION_TABLE.shape == (len(ACTION_NAMES), 8)


def make_observation(state, aid):
    """20-dim, present-state-only features, no replay future or oracle data."""
    car = state.cars[aid]
    p = car.physics.position
    v = car.physics.linear_velocity
    b = state.ball.position
    bv = state.ball.linear_velocity
    f = car.physics.forward
    return np.asarray([
        *((b - p) / 4096), * (p / 4096), * (v / 2300), * (bv / 2300),
        *f, car.boost_amount / 100, float(car.on_ground),
        b[1] / 5200, np.linalg.norm(b - p) / 5200,
        car.physics.angular_velocity[2] / 5,
    ], dtype=np.float32)

OBS_SIZE = 20


class SoloShootingEnv:
    """1 blue car, stationary ball, no opponents. Shaped training task only."""
    def __init__(self, seed: int, max_steps: int = 120):
        from rlgym.rocket_league.sim import RocketSimEngine
        from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator, KickoffMutator
        self.engine = RocketSimEngine(rlbot_delay=False)
        self.mutate_team = FixedTeamSizeMutator(blue_size=1, orange_size=0)
        self.mutate_kickoff = KickoffMutator()
        self.rng = np.random.default_rng(seed)
        self.max_steps = max_steps
        self.aid = 'blue-0'
        self.t = 0
        self.touches = 0
        self.scored = False
        self.total_reward = 0.
        self.state = None

    def reset(self):
        # Starting positions are valid, close enough for early touches.
        # Do not use any replay snapshots, checkpoint states, or test labels.
        s = self.engine.create_base_state()
        self.mutate_team.apply(s, {})
        self.mutate_kickoff.apply(s, {})
        rng = self.rng
        bx = float(rng.uniform(-650, 650))
        by = float(rng.uniform(1500, 3150))
        ball = s.ball
        ball.position = np.array([bx, by, 93.15], dtype=np.float32)
        ball.linear_velocity = np.zeros(3, dtype=np.float32)
        ball.angular_velocity = np.zeros(3, dtype=np.float32)
        car = s.cars[self.aid]
        dx = float(rng.uniform(-290, 290))
        dy = float(rng.uniform(550, 1050))
        car.physics.position = np.array([bx + dx, by - dy, 17.], dtype=np.float32)
        car.physics.linear_velocity = np.zeros(3, dtype=np.float32)
        car.physics.angular_velocity = np.zeros(3, dtype=np.float32)
        yaw = math.atan2(-dx, dy) + float(rng.uniform(-.3, .3))
        car.physics.euler_angles = np.array([0., yaw, 0.], dtype=np.float32)
        car.boost_amount = 80.
        self.state = self.engine.set_state(s, {})
        self.t = 0
        self.touches = 0
        self.scored = False
        self.total_reward = 0.
        obs = make_observation(self.state, self.aid)
        if obs.shape != (OBS_SIZE,) or not np.isfinite(obs).all():
            raise RuntimeError(f'Unexpected RocketSim observation {obs.shape}: {obs}')
        return obs

    def step(self, action_index: int):
        action = ACTION_TABLE[int(action_index)]
        old_p = self.state.cars[self.aid].physics.position
        old_ball = self.state.ball.position
        old_dist = float(np.linalg.norm(old_p - old_ball))
        old_y = float(old_ball[1])
        controls = np.repeat(action[None, :], ACTION_REPEAT, axis=0)
        self.state = self.engine.step({self.aid: controls}, {})
        self.t += 1
        b = self.state.ball.position
        car = self.state.cars[self.aid]
        dist = float(np.linalg.norm(b - car.physics.position))
        touches = int(car.ball_touches)
        self.touches += touches
        # Dense shaping: approach ball, touch, and move ball toward positive-y goal.
        # Small clip prevents large spurious impulse from dominating advantages.
        approach = float(np.clip((old_dist - dist) / 500., -.5, .5))
        ball_advance = float(np.clip((float(b[1]) - old_y) / 500., -.5, .5))
        goal = bool(self.state.goal_scored and b[1] > 0.)
        reward = .14 * approach + .30 * ball_advance + 2.0 * touches - .003
        if goal:
            reward += 12.
        self.scored = self.scored or goal
        self.total_reward += reward
        done = bool(self.state.goal_scored or self.t >= self.max_steps)
        obs = make_observation(self.state, self.aid)
        if not np.isfinite(obs).all() or not np.isfinite(reward):
            raise FloatingPointError('Nonfinite simulator observation/reward')
        info = dict(touches=self.touches, scored=self.scored,
                    ball_y=float(b[1]), total_reward=float(self.total_reward),
                    steps=self.t)
        return obs, float(reward), done, info

    def close(self):
        self.engine.close()


class ActorCritic(nn.Module):
    def __init__(self):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(OBS_SIZE, 128), nn.Tanh(),
                                  nn.Linear(128, 128), nn.Tanh())
        self.actor = nn.Linear(128, len(ACTION_NAMES))
        self.critic = nn.Linear(128, 1)

    def forward(self, observations):
        f = self.body(observations)
        return self.actor(f), self.critic(f).squeeze(-1)


def gae(rewards, values, dones, bootstrap, gamma=0.99, lam=0.95):
    """Correctly mask resets and bootstrap unfinished rollout at final sample."""
    r = np.asarray(rewards, dtype=np.float32)
    v = np.asarray(values, dtype=np.float32)
    d = np.asarray(dones, dtype=np.float32)
    adv = np.zeros_like(r)
    acc = 0.
    for i in reversed(range(len(r))):
        nonterminal = 1. - d[i]
        next_value = float(v[i+1]) if i+1 < len(r) else float(bootstrap)
        delta = r[i] + gamma * nonterminal * next_value - v[i]
        acc = delta + gamma * lam * nonterminal * acc
        adv[i] = acc
    return adv, adv + v


@torch.no_grad()
def sample_action(net, obs, device, greedy=False):
    inp = torch.from_numpy(obs).to(device=device).unsqueeze(0)
    logits, value = net(inp)
    dist = Categorical(logits=logits)
    action = logits.argmax(-1) if greedy else dist.sample()
    lp = dist.log_prob(action)
    return int(action.item()), float(lp.item()), float(value.item())


def collect(net, env, nsteps, device, obs):
    rows = dict(obs=[], action=[], logp=[], value=[], reward=[], done=[])
    complete = []
    for _ in range(nsteps):
        action, logp, val = sample_action(net, obs, device)
        next_obs, reward, done, info = env.step(action)
        rows['obs'].append(obs.copy())
        rows['action'].append(action)
        rows['logp'].append(logp)
        rows['value'].append(val)
        rows['reward'].append(reward)
        rows['done'].append(done)
        if done:
            complete.append(info)
            next_obs = env.reset()
        obs = next_obs
    _, _, bootstrap = sample_action(net, obs, device, greedy=True)
    rows['adv'], rows['ret'] = gae(rows['reward'], rows['value'], rows['done'], bootstrap)
    return rows, obs, complete


def ppo_update(net, opt, rows, device, epochs, minibatch, seed):
    rng = np.random.default_rng(seed)
    tensors = {
        'obs': torch.as_tensor(np.asarray(rows['obs']), dtype=torch.float32, device=device),
        'action': torch.tensor(rows['action'], dtype=torch.long, device=device),
        'logp': torch.tensor(rows['logp'], dtype=torch.float32, device=device),
        'ret': torch.as_tensor(rows['ret'], dtype=torch.float32, device=device),
        'adv': torch.as_tensor(rows['adv'], dtype=torch.float32, device=device),
    }
    tensors['adv'] = (tensors['adv'] - tensors['adv'].mean()) / (tensors['adv'].std(unbiased=False) + 1.e-8)
    losses = []
    for _ in range(epochs):
        for chunk in np.array_split(rng.permutation(len(rows['obs'])),
                                    max(1, math.ceil(len(rows['obs'])/minibatch))):
            indices = torch.as_tensor(chunk, device=device)
            logits, value = net(tensors['obs'][indices])
            dist = Categorical(logits=logits)
            lp = dist.log_prob(tensors['action'][indices])
            ratio = torch.exp(lp - tensors['logp'][indices])
            a = tensors['adv'][indices]
            clipped = torch.clamp(ratio, .8, 1.2)
            policy_loss = -torch.min(a * ratio, a * clipped).mean()
            value_loss = .5 * (value - tensors['ret'][indices]).square().mean()
            entropy = dist.entropy().mean()
            loss = policy_loss + .5 * value_loss - .01 * entropy
            if not torch.isfinite(loss):
                raise FloatingPointError('Nonfinite PPO loss')
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), .5)
            opt.step()
            losses.append([float(loss.item()), float(entropy.item()), float(value_loss.item())])
    avg = np.mean(losses, axis=0)
    return dict(total_loss=float(avg[0]), entropy=float(avg[1]), value_loss=float(avg[2]))


@torch.no_grad()
def evaluate(net, seed, episodes, max_steps, device, random_policy=False):
    env = SoloShootingEnv(seed=seed, max_steps=max_steps)
    metrics = []
    try:
        for _ in range(episodes):
            obs = env.reset()
            while True:
                if random_policy:
                    action = int(env.rng.integers(len(ACTION_NAMES)))
                else:
                    action, _, _ = sample_action(net, obs, device)
                obs, _, done, info = env.step(action)
                if done:
                    metrics.append(info)
                    break
    finally:
        env.close()
    return dict(episodes=episodes,
                goal_rate=float(np.mean([e['scored'] for e in metrics])),
                touch_rate=float(np.mean([e['touches'] > 0 for e in metrics])),
                avg_touches=float(np.mean([e['touches'] for e in metrics])),
                avg_return=float(np.mean([e['total_reward'] for e in metrics])),
                avg_final_ball_y=float(np.mean([e['ball_y'] for e in metrics])))


def checked_output(path):
    """Only allow a new file in data/isolated. Existing output NEVER overwritten."""
    allowed = (Path.cwd() / 'data' / 'isolated').resolve()
    dest = Path(path).resolve()
    if not dest.is_relative_to(allowed):
        raise ValueError(f'Output MUST be inside {allowed}, not {dest}')
    if dest.suffix != '.pt' or dest.name.endswith('.partial.pt'):
        raise ValueError('Output must have a .pt filename')
    if dest.exists() or dest.with_name(dest.name+'.partial').exists():
        raise FileExistsError(f'Output/partial already exists: {dest}')
    return dest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--updates', type=int, default=2)
    p.add_argument('--rollout-steps', type=int, default=768)
    p.add_argument('--epochs', type=int, default=3)
    p.add_argument('--minibatch', type=int, default=128)
    p.add_argument('--max-episode-steps', type=int, default=120)
    p.add_argument('--eval-episodes', type=int, default=8)
    p.add_argument('--lr', type=float, default=3.e-4)
    p.add_argument('--seed', type=int, default=20261011)
    p.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    p.add_argument('--out', required=True)
    args = p.parse_args()
    if min(args.updates, args.rollout_steps, args.epochs, args.minibatch,
           args.max_episode_steps, args.eval_episodes) < 1:
        p.error('All counts must be positive')
    if not (0 < args.lr <= .01):
        p.error('Learning rate must be between 0 and .01')
    if args.device == 'cuda' and not torch.cuda.is_available():
        p.error('CUDA requested but unavailable')
    out = checked_output(args.out)  # Safety check BEFORE importing RocketSim/training.
    torch.set_num_threads(2)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device(args.device)
    model = ActorCritic().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    print('EXPERIMENT: isolated from-scratch solo-shooting PPO, NOT full Slater / Cycle9', flush=True)
    print('DEVICE:', device, 'ACTION_REPEAT:', ACTION_REPEAT, 'OUTPUT:', out, flush=True)
    tstart = time.perf_counter()
    # Eval RNG independent of training; exact same episode seeds before and after.
    pre = evaluate(model, args.seed + 100000, args.eval_episodes, args.max_episode_steps, device)
    random_baseline = evaluate(model, args.seed + 200000, args.eval_episodes, args.max_episode_steps,
                               device, random_policy=True)
    print('PRE_EVAL', json.dumps(pre, sort_keys=True), flush=True)
    print('RANDOM_BASELINE', json.dumps(random_baseline, sort_keys=True), flush=True)
    first_weights = [p.detach().cpu().clone() for p in model.parameters()]
    env = SoloShootingEnv(args.seed, max_steps=args.max_episode_steps)
    obs = env.reset()
    train_metrics=[]
    try:
        for n in range(args.updates):
            rows, obs, complete = collect(model, env, args.rollout_steps, device, obs)
            stats = ppo_update(model, opt, rows, device, args.epochs, args.minibatch, args.seed+n)
            stats.update(update=n+1, transitions=len(rows['obs']),
                         episodes_completed=len(complete),
                         episode_touches=sum(c['touches'] for c in complete),
                         episode_goals=sum(c['scored'] for c in complete))
            train_metrics.append(stats)
            print('UPDATE', json.dumps(stats, sort_keys=True), flush=True)
    finally:
        env.close()
    post = evaluate(model, args.seed + 100000, args.eval_episodes, args.max_episode_steps, device)
    param_change = float(sum((p.detach().cpu() - orig).square().sum().item()
                             for p, orig in zip(model.parameters(), first_weights)) ** .5)
    if param_change < 1.e-9 or not np.isfinite(param_change):
        raise RuntimeError('Policy did not update; abort saving')
    print('POST_EVAL', json.dumps(post, sort_keys=True), flush=True)
    print('POLICY_WEIGHT_DELTA_L2', round(param_change, 6), flush=True)
    elapsed = time.perf_counter() - tstart
    meta = dict(kind='scratch_solo_shooting_ppo_smoke', schema_version=1,
                authoring_warning='NOT Nexto/Cycle9 architecture compatible; NOT self-play; no replay training',
                seed=args.seed, args=vars(args), pre_eval=pre,
                random_baseline=random_baseline, post_eval=post,
                train_updates=train_metrics,
                param_delta_l2=param_change,
                seconds=elapsed, cumulative_env_decisions=args.updates*args.rollout_steps)
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_name(out.name + '.partial')
    # exclusive create prevents unexpected overwrite even if path appeared during training
    payload = {'model': model.cpu().state_dict(), 'optimizer': opt.state_dict(), 'meta': meta}
    try:
        with temp.open('xb') as f:
            torch.save(payload, f)
        # Recheck target did not materialize during training.
        if out.exists():
            raise FileExistsError(f'Output appeared while training: {out}')
        os.rename(temp, out)  # Windows rename fails if destination exists
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    h = hashlib.sha256(out.read_bytes()).hexdigest()
    print('SAVED_NEW_ISOLATED_CHECKPOINT', str(out), flush=True)
    print('SHA256', h, flush=True)
    print('SUMMARY', json.dumps({k: meta[k] for k in ('cumulative_env_decisions', 'param_delta_l2', 'seconds', 'pre_eval', 'post_eval')},sort_keys=True),flush=True)
    print('IMPORTANT: A changed policy is not proof of improved skill; these tiny evaluations are noisy.',flush=True)
    print('ORIGINAL CYCLE 9 / CHAMPION / REPLAY FILES WERE NOT OPENED.',flush=True)


if __name__ == '__main__':
    main()
