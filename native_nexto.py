"""Native Nexto baseline and *experimental* PPO fine-tuning on RocketSim.

Unlike the old 92-feature student, this keeps Nexto's original attention-based
observation and actor weights. Nothing modifies vendor/nexto/nexto-model.pt.
For offline RocketSim experiments only. Nexto CC BY-NC-SA 4.0 terms apply.
"""
from __future__ import annotations

import argparse
import os
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical

from nexto_teacher import NextoTeacher, nexto_actions

HERE = Path(__file__).resolve().parent
SOURCE_MODEL = HERE / 'vendor' / 'nexto' / 'nexto-model.pt'
SAVE_DIR = HERE / 'data' / 'native_nexto'


def features(q: torch.Tensor, kv: torch.Tensor) -> torch.Tensor:
    """Small value network input; actor still receives full Nexto observations."""
    if q.ndim != 3 or q.shape[-2:] != (1, 32):
        raise ValueError(f'Expected Bx1x32 query, got {tuple(q.shape)}')
    if kv.ndim != 3 or kv.shape[1:] != (37, 24):
        raise ValueError(f'Expected Bx37x24 entities, got {tuple(kv.shape)}')
    return torch.cat((q[:, 0], kv.mean(dim=1), kv[:, 0], kv[:, 2]), dim=-1)


class Critic(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(104, 128), nn.Tanh(),
                                 nn.Linear(128, 128), nn.Tanh(), nn.Linear(128, 1))

    def forward(self, q, kv):
        return self.net(features(q, kv)).squeeze(-1)


def unpack_obs(view, device):
    """An individual Nexto view: (agent, query, key_values, mask)."""
    _, q, kv, mask = view
    return (torch.as_tensor(q[None, ...], dtype=torch.float32, device=device),
            torch.as_tensor(kv[None, ...], dtype=torch.float32, device=device),
            torch.as_tensor(mask[None, ...], dtype=torch.float32, device=device))


def actor_logits(actor, q, kv, mask):
    out, _ = actor((q, kv, mask))
    if out.shape[-1] != 90:
        raise RuntimeError(f'Nexto actor returned {tuple(out.shape)} instead of Bx90')
    return out


def discounted_gae(rewards, values, dones, bootstrap, gamma=0.995, lam=0.95):
    """Returns generalized-advantage estimates and critic targets."""
    rewards = np.asarray(rewards, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    dones = np.asarray(dones, dtype=bool)
    if not (len(rewards) == len(values) == len(dones)):
        raise ValueError('rollout arrays have inconsistent lengths')
    advantages = np.zeros(len(rewards), dtype=np.float64)
    running = 0.0
    next_value = float(bootstrap)
    for i in range(len(rewards) - 1, -1, -1):
        live = 0.0 if dones[i] else 1.0
        delta = rewards[i] + gamma * next_value * live - values[i]
        running = delta + gamma * lam * live * running
        advantages[i] = running
        next_value = values[i]
    return advantages.astype(np.float32), (advantages + values).astype(np.float32)


def ball_distance(state, car_id):
    return float(np.linalg.norm(np.asarray(state.cars[car_id].physics.position, dtype=np.float64)
                               - np.asarray(state.ball.position, dtype=np.float64)))


def outcome_owner(ball_y, our_orange):
    return 'ours' if ((ball_y > 0) != our_orange) else 'nexto'


def shaped_reward(before_distance, before_ball_y, after, our_id, opp_id, our_orange):
    """Small, bounded potential-shaping plus scoring and touch rewards.

    These are experimental weights; evaluate performance, never equate reward
    changes with match wins. Potential uses discounting to reduce stalling abuse.
    """
    d1 = ball_distance(after, our_id)
    proximity = 0.15 * (before_distance - 0.995 * d1) / 6000.0
    # Ball toward opponent's goal: positive Y if blue; negative Y if orange.
    sign = -1.0 if our_orange else 1.0
    progress = 0.08 * sign * (
        float(after.ball.position[1]) - before_ball_y) / 5200.0
    touch_us = int(getattr(after.cars[our_id], 'ball_touches', 0))
    touch_opp = int(getattr(after.cars[opp_id], 'ball_touches', 0))
    r = float(proximity + progress + 0.12 * bool(touch_us) - 0.04 * bool(touch_opp) - 0.0005)
    goal = bool(getattr(after, 'goal_scored', False))
    if goal:
        r += 10.0 if outcome_owner(float(after.ball.position[1]), our_orange) == 'ours' else -10.0
    return r, goal, touch_us, touch_opp


class Match:
    """One learner car versus an independent, *frozen* Nexto policy."""
    def __init__(self, teacher, engine, training_side_orange=False, scenarios='kickoff'):
        from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator, KickoffMutator
        self.teacher = teacher
        self.engine = engine
        self.team_mutator = FixedTeamSizeMutator(blue_size=1, orange_size=1)
        self.scenarios = scenarios
        self.kickoff = KickoffMutator()
        self.our_orange = training_side_orange
        self.reset()

    def reset(self):
        base = self.engine.create_base_state()
        self.team_mutator.apply(base, {})
        if self.scenarios == 'grounded':
            from chatgpt_ai.curriculum import ChatGPTCurriculum
            ChatGPTCurriculum('grounded').apply(base, {})
        else:
            self.kickoff.apply(base, {})
        self.state = self.engine.set_state(base, {})
        self.previous = {}
        self.ours = next(agent for agent, car in self.state.cars.items()
                         if bool(car.is_orange) == self.our_orange)
        self.opponent = next(agent for agent in self.state.cars if agent != self.ours)
        self.decisions = 0
        self.contacts = {'ours': 0, 'nexto': 0}
        return self.observe()

    def observe(self):
        views = self.teacher.observe(self.state, self.previous)
        return (next(v for v in views if v[0] == self.ours),
                next(v for v in views if v[0] == self.opponent))

    def step(self, our_action_id, opponent_id, max_decisions):
        our_control = nexto_actions()[int(our_action_id)]
        opp_control = nexto_actions()[int(opponent_id)]
        commands = {self.ours: np.tile(our_control, (8, 1)),
                    self.opponent: np.tile(opp_control, (8, 1))}
        # Capture pre-step physics by value: some simulators may reuse mutable state.
        previous_distance = ball_distance(self.state, self.ours)
        previous_ball_y = float(self.state.ball.position[1])
        self.state = self.engine.step(commands, {})
        self.previous = {self.ours: our_control, self.opponent: opp_control}
        self.decisions += 1
        reward, goal, our_touch, opp_touch = shaped_reward(
            previous_distance, previous_ball_y, self.state, self.ours, self.opponent, self.our_orange)
        self.contacts['ours'] += our_touch
        self.contacts['nexto'] += opp_touch
        finished = goal or self.decisions >= max_decisions
        winner = outcome_owner(float(self.state.ball.position[1]), self.our_orange) if goal else 'draw'
        return reward, finished, winner


def select_action(actor, view, device, temperature=1.0, sample=True):
    with torch.inference_mode():
        q, kv, m = unpack_obs(view, device)
        logits = actor_logits(actor, q, kv, m) / temperature
        dist = Categorical(logits=logits)
        action = dist.sample() if sample else logits.argmax(dim=-1)
        return int(action.item()), float(dist.log_prob(action).item()), (q, kv, m)


def evaluation(actor, teacher, device='cpu', games=20, decisions=750, seed=123,
               render=False, speed=1.0):
    from rlgym.rocket_league.sim import RocketSimEngine
    if games < 1 or decisions < 1:
        raise ValueError('games and decisions must be positive')
    random.seed(seed)
    np.random.seed(seed)
    outcomes = {'ours': 0, 'nexto': 0, 'draw': 0}
    contacts = {'ours': 0, 'nexto': 0}
    time_used = 0
    engine = RocketSimEngine(rlbot_delay=False)
    renderer = None
    if render:
        from rlgym.rocket_league.rlviser import RLViserRenderer
        renderer = RLViserRenderer(tick_rate=15 * speed)
    actor.eval()
    try:
        for episode in range(games):
            match = Match(teacher, engine, training_side_orange=bool(episode % 2), scenarios='kickoff')
            winner = 'draw'
            for t in range(decisions):
                start = time.perf_counter()
                if renderer:
                    renderer.render(match.state, {})
                our_view, their_view = match.observe()
                our_action, _, _ = select_action(actor, our_view, device, sample=False)
                opp_logits = teacher.logits([(their_view[1], their_view[2], their_view[3])])
                opp_action = int(opp_logits[0].argmax())
                _, done, winner = match.step(our_action, opp_action, decisions)
                if renderer:
                    delay = 1 / (15 * speed) - (time.perf_counter() - start)
                    if delay > 0:
                        time.sleep(delay)
                if done:
                    break
            time_used += match.decisions
            outcomes[winner] += 1
            for k in contacts:
                contacts[k] += match.contacts[k]
            print(f'Episode {episode+1}/{games}: {winner}, our touches={match.contacts["ours"]}, '
                  f'Nexto touches={match.contacts["nexto"]}', flush=True)
    finally:
        if renderer:
            renderer.close()
        engine.close()
    print(f'Results: {outcomes}; touches={contacts}; total_decision_ticks={time_used}')
    print('Touches per 1000 decision ticks:',
          {k: round(v * 1000.0 / max(1, time_used), 2) for k, v in contacts.items()})
    print('This is first-to-score evaluation of the learned policy only, not full-game win rate.')
    return {'outcomes': outcomes, 'touches': contacts, 'decision_ticks': time_used}


def save_checkpoint(actor, critic, actor_optim, critic_optim, steps, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix('.partial')
    torch.save({'actor': {k: v.detach().cpu() for k, v in actor.state_dict().items()},
                'critic': critic.state_dict(), 'actor_optimizer': actor_optim.state_dict(),
                'critic_optimizer': critic_optim.state_dict(), 'timesteps': steps}, temp)
    os.replace(temp, output)


def load_checkpoint(actor, critic, actor_optim, critic_optim, path, device):
    state = torch.load(path, map_location='cpu', weights_only=True)
    actor.load_state_dict(state['actor'], strict=True)
    critic.load_state_dict(state['critic'])
    actor_optim.load_state_dict(state['actor_optimizer'])
    critic_optim.load_state_dict(state['critic_optimizer'])
    return int(state['timesteps'])


def training(args, actor, frozen_teacher, device):
    from rlgym.rocket_league.sim import RocketSimEngine
    torch.set_num_threads(2)
    np.random.seed(args.seed)
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    # Frozen teacher used as opponent *and* as KL regularization anchor.
    reference = frozen_teacher.actor
    reference.eval()
    for p in reference.parameters():
        p.requires_grad_(False)
    critic = Critic().to(device)
    actor_optim = torch.optim.Adam(actor.parameters(), lr=args.actor_lr)
    critic_optim = torch.optim.Adam(critic.parameters(), lr=args.critic_lr)
    cumulative = 0
    if args.resume and args.checkpoint.is_file():
        cumulative = load_checkpoint(actor, critic, actor_optim, critic_optim, args.checkpoint, device)
        print(f'Resumed {cumulative:,} decision ticks from {args.checkpoint}', flush=True)
    actor.eval()  # Keeps inference consistent with the original Nexto TorchScript baseline.
    engine = RocketSimEngine(rlbot_delay=False)
    match = Match(frozen_teacher, engine, scenarios=args.scenarios)
    rng = np.random.default_rng(args.seed)
    try:
        while cumulative < args.steps:
            qlist, kvlist, mlist, actions, old_logps, vals, rewards, dones = [], [], [], [], [], [], [], []
            maxsteps = min(args.rollout, args.steps - cumulative)
            wins = {'ours': 0, 'nexto': 0, 'draw': 0}
            for _ in range(maxsteps):
                our_view, opp_view = match.observe()
                our_action, old_logp, (q, kv, mask) = select_action(
                    actor, our_view, device, args.temperature, sample=True)
                with torch.inference_mode():
                    value = float(critic(q, kv).item())
                their_probs = frozen_teacher.logits([(opp_view[1], opp_view[2], opp_view[3])])
                their_action = int(their_probs[0].argmax())
                r, done, winner = match.step(our_action, their_action, args.episode_decisions)
                qlist.append(q.cpu().numpy()[0]); kvlist.append(kv.cpu().numpy()[0]); mlist.append(mask.cpu().numpy()[0])
                actions.append(our_action); old_logps.append(old_logp)
                vals.append(value); rewards.append(r); dones.append(done)
                if done:
                    wins[winner] += 1
                    match.our_orange = bool(rng.integers(0, 2))
                    match.reset()
            with torch.inference_mode():
                if dones[-1]:
                    bootstrap = 0.0
                else:
                    our_view, _ = match.observe()
                    q, kv, _ = unpack_obs(our_view, device)
                    bootstrap = float(critic(q, kv).item())
            advantage, returns = discounted_gae(rewards, vals, dones, bootstrap)
            advantage = (advantage - advantage.mean()) / (advantage.std() + 1e-8)
            Xq = torch.tensor(np.stack(qlist), device=device)
            Xkv = torch.tensor(np.stack(kvlist), device=device)
            Xm = torch.tensor(np.stack(mlist), device=device)
            old_a = torch.tensor(actions, dtype=torch.long, device=device)
            old_logp = torch.tensor(old_logps, dtype=torch.float32, device=device)
            advantage = torch.tensor(advantage, device=device)
            returns = torch.tensor(returns, device=device)
            for _ in range(args.epochs):
                indices = torch.randperm(len(actions), device=device)
                for ix in indices.split(args.minibatch):
                    logits = actor_logits(actor, Xq[ix], Xkv[ix], Xm[ix]) / args.temperature
                    dist = Categorical(logits=logits)
                    logp = dist.log_prob(old_a[ix])
                    ratio = (logp - old_logp[ix]).exp()
                    surr = torch.minimum(ratio * advantage[ix],
                        torch.clamp(ratio, 1 - args.clip, 1 + args.clip) * advantage[ix])
                    with torch.no_grad():
                        ref_logits = actor_logits(reference, Xq[ix].to('cpu'), Xkv[ix].to('cpu'), Xm[ix].to('cpu')).to(device)
                    anchor = F.kl_div(F.log_softmax(logits, -1), F.softmax(ref_logits / args.temperature, -1), reduction='batchmean')
                    objective = -surr.mean() + args.anchor * anchor - args.entropy * dist.entropy().mean()
                    actor_optim.zero_grad(set_to_none=True)
                    objective.backward()
                    torch.nn.utils.clip_grad_norm_(actor.parameters(), 0.5)
                    actor_optim.step()
                    critic_loss = F.mse_loss(critic(Xq[ix], Xkv[ix]), returns[ix])
                    critic_optim.zero_grad(set_to_none=True)
                    critic_loss.backward()
                    torch.nn.utils.clip_grad_norm_(critic.parameters(), 0.5)
                    critic_optim.step()
            cumulative += len(actions)
            print(f'Decisions {cumulative:,}/{args.steps:,} | rewards/step={np.mean(rewards):+.4f} '
                  f'| wins this rollout={wins} | actor_loss={float(objective.detach()):.4f} '
                  f'| anchor_KL={float(anchor.detach()):.5f}', flush=True)
            save_checkpoint(actor, critic, actor_optim, critic_optim, cumulative, args.checkpoint)
    finally:
        engine.close()
    print(f'Finished. Saved native Nexto PPO state to {args.checkpoint}. Evaluate before scaling up.')


def main():
    p = argparse.ArgumentParser(description='Experimental native-Nexto RocketSim PPO training / evaluation')
    p.add_argument('--mode', choices=['baseline', 'train', 'eval'], default='baseline')
    p.add_argument('--checkpoint', type=Path, default=SAVE_DIR/'last.pt')
    p.add_argument('--device', choices=['cpu', 'cuda:0'], default='cpu')
    p.add_argument('--steps', type=int, default=2000, help='cumulative policy decision ticks, not physics ticks')
    p.add_argument('--rollout', type=int, default=256)
    p.add_argument('--minibatch', type=int, default=64)
    p.add_argument('--epochs', type=int, default=2)
    p.add_argument('--episode-decisions', type=int, default=450)
    p.add_argument('--eval-decisions', type=int, default=750)
    p.add_argument('--scenarios', choices=['kickoff','grounded'], default='grounded')
    p.add_argument('--actor-lr', type=float, default=1e-5)
    p.add_argument('--critic-lr', type=float, default=3e-4)
    p.add_argument('--anchor', type=float, default=0.15)
    p.add_argument('--entropy', type=float, default=0.001)
    p.add_argument('--clip', type=float, default=0.15)
    p.add_argument('--temperature', type=float, default=0.8)
    p.add_argument('--seed', type=int, default=123)
    p.add_argument('--games', type=int, default=20)
    p.add_argument('--render', action='store_true')
    p.add_argument('--speed', type=float, default=1.0)
    p.add_argument('--resume', action='store_true')
    args = p.parse_args()
    if args.steps < 1 or args.rollout < 1 or args.minibatch < 1 or args.epochs < 1:
        p.error('steps, rollout, minibatch, epochs must all be >= 1')
    if args.speed <= 0 or args.temperature <= 0 or not 0 < args.clip < 1:
        p.error('speed, temperature must be positive; clip in (0,1)')
    if args.actor_lr <= 0 or args.critic_lr <= 0 or args.anchor < 0:
        p.error('learning rates must be positive and anchor >= 0')
    if args.device == 'cuda:0' and not torch.cuda.is_available():
        p.error('CUDA unavailable in this PyTorch installation')
    torch.set_num_threads(2)
    torch.manual_seed(args.seed)
    actor = torch.jit.load(str(SOURCE_MODEL), map_location=args.device)
    # Always load a separate frozen copy of Nexto for the opponent and the anchor.
    teacher = NextoTeacher('cpu')
    if args.mode == 'train':
        training(args, actor, teacher, args.device)
    else:
        if args.mode == 'eval':
            if not args.checkpoint.exists():
                p.error(f'No native checkpoint at {args.checkpoint}; run training first')
            saved = torch.load(args.checkpoint, map_location='cpu', weights_only=True)
            actor.load_state_dict(saved['actor'])
        evaluation(actor, teacher, device=args.device, games=args.games,
                   decisions=args.eval_decisions,
                   seed=args.seed, render=args.render, speed=args.speed)


if __name__ == '__main__':
    main()
