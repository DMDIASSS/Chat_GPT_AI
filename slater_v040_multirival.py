"""Slater v0.4.0 — protected V60 PPO continuation against four frozen rivals.

Uses existing v0.3.7a RocketSim trainer and action/observation encoding.
Does NOT train on replay/TAS data, does NOT certify a stronger live RLBot bot,
and does not overwrite source checkpoints. See SLATER_V040_README.md.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import random
import time

import numpy as np
import torch

import slater_cycle9_native_ppo_v025 as base
import slater_nexto_kickoff_v037a as prev
from slater_cycle9_train_v027 import safe_run

VERSION = 'v0.4.0'
EXPECTED_V60_SHA256 = '5f9bf7cb6a0bcfb3bcf801ade021b11499181d80fb36b0cfad827e2648936c74'
RIVALS = ('nexto_script', 'nexto_greedy', 'cycle9', 'frozen_u60')
GAMMA = .995


def normalize_modes(arg: str) -> tuple[str, ...]:
    names = tuple(x.strip() for x in arg.split(','))
    if not (2 <= len(names) <= len(RIVALS)) or len(names) != len(set(names)):
        raise ValueError('Select 2-4 distinct opponents')
    if any(x not in RIVALS for x in names):
        raise ValueError(f'Unknown mode. Allowed: {RIVALS}')
    if 'nexto_script' not in names or 'frozen_u60' not in names:
        raise ValueError('Training must include scripted Nexto and frozen V60')
    return names


class RivalEnv(prev.ScriptedNextoEnv):
    """Existing physics/rewards; one new opponent is independent frozen V60.

    reset() of the parent chooses one mode for each pair of episodes, which
    balances student Blue/Orange when fixed_side=None.
    """
    VALID_MODES = tuple(prev.ScriptedNextoEnv.VALID_MODES) + ('frozen_u60',)

    def __init__(self, actions, observer, originals, frozen_u60, max_steps,
                 device='cpu', modes=RIVALS, fixed_side=None):
        self.frozen_u60 = frozen_u60
        super().__init__(actions, observer, originals, max_steps, device,
                         modes=modes, fixed_side=fixed_side)

    def reset(self, seed):
        obs = super().reset(seed)
        if self.current_opponent == 'frozen_u60':
            self.opponent = self.frozen_u60
        return obs

    def _opponent_commands(self, oid):
        if self.current_opponent == 'nexto_script':
            # This legacy simulator script entirely overrides the feedforward
            # NN action during its active interval. Avoid wasted inference.
            ball_y = float(self.state.ball.position[1])
            active = (not self.kickoff_ball_touched and prev.is_stationary_center(ball_y)
                      and self.t * base.ACTION_REPEAT < prev.SCRIPT_TICKS)
            if active:
                self.script_action_steps += 1
                self.last_control_source = 'script'
                return prev.grouped_control(self.t * base.ACTION_REPEAT,
                                            enabled=True, active=True,
                                            nn_control=np.zeros(8, dtype=np.float32),
                                            action_repeat=base.ACTION_REPEAT)
        if self.current_opponent != 'frozen_u60':
            return super()._opponent_commands(oid)
        observation = base.read_obs(self.state, self.previous, self.observer, oid)
        with torch.no_grad():
            logits = base.logits_of(self.frozen_u60, base.to_tensors(observation, self.device))
            index = int(logits.argmax(-1).item())
        control = np.asarray(self.actions[index], dtype=np.float32)
        self.neural_action_steps += 1
        self.last_control_source = 'frozen_u60'
        return np.repeat(control.reshape(1, 8), base.ACTION_REPEAT, axis=0)


def adjusted_timeout_reward(reward: float, done: bool, timeout: bool, next_value: float,
                            gamma: float = GAMMA) -> float:
    """Bootstrap time-limit truncations but not actual scored goals.

    The end-of-episode 'done' still breaks GAE across the subsequent reset.
    This correction is equivalent to adding gamma*V(s_next) to the final reward.
    """
    if not all(map(math.isfinite, [reward, next_value, gamma])):
        raise FloatingPointError('Nonfinite bootstrap input')
    if timeout and not done:
        raise ValueError('Timeout requires done=True')
    if not 0 <= gamma <= 1:
        raise ValueError('Invalid discount')
    return float(reward + (gamma * next_value if timeout else 0.0))


def collect_continuous(actor, critic, env, observations, episode_seed,
                       rollout_steps: int, device='cpu'):
    """Never discard partial episodes at PPO boundaries.

    Return the active state for continuation in the next update, and terminal
    corrected rewards for GAE. Only actual env.done triggers reset.
    """
    if rollout_steps < 1:
        raise ValueError('rollout_steps must be positive')
    rows = {'q': [], 'kv': [], 'mask': [], 'action': [], 'old_logp': [],
            'value': [], 'reward': [], 'done': []}
    finished = []
    timeout_bootstraps = 0
    obs = observations
    for _ in range(rollout_steps):
        action, log_prob, value = base.choose(actor, critic, obs, device)
        next_obs, reward, done, info = env.step(action)
        is_timeout = bool(info.get('timeout', False))
        next_value = 0.
        if is_timeout:
            with torch.no_grad():
                next_value = float(critic(base.to_tensors(next_obs, device)).item())
            timeout_bootstraps += 1
        corrected = adjusted_timeout_reward(reward, bool(done), is_timeout, next_value)
        for key, x in zip(('q', 'kv', 'mask'), obs):
            rows[key].append(x)
        rows['action'].append(action)
        rows['old_logp'].append(log_prob)
        rows['value'].append(value)
        rows['reward'].append(corrected)
        rows['done'].append(bool(done))
        if done:
            finished.append(info)
            episode_seed += 1
            next_obs = env.reset(episode_seed)
        obs = next_obs
    with torch.no_grad():
        bootstrap = float(critic(base.to_tensors(obs, device)).item())
    rows['adv'], rows['ret'] = base.gae(rows['reward'], rows['value'], rows['done'], bootstrap)
    return rows, finished, obs, episode_seed, timeout_bootstraps


def compare_policies(actor, anchor, original, nexto, actions, *, modes,
                     seeds, episode_steps, seed_base):
    """Paired side/seed evaluation; u60 is frozen reference, not Cycle9."""
    from afk_team_research import TeamObserver
    records = []
    for i in range(seeds):
        seed = seed_base + 997*i
        for side in ('blue', 'orange'):
            for mode in modes:
                for name, model in (('frozen_u60', anchor), ('candidate', actor)):
                    env = RivalEnv(actions, TeamObserver(), (original, nexto), anchor,
                                   max_steps=episode_steps, modes=(mode,), fixed_side=side)
                    try:
                        obs = env.reset(seed)
                        while True:
                            with torch.no_grad():
                                logits = base.logits_of(model, base.to_tensors(obs))
                                chosen = int(logits.argmax(-1).item())
                            obs, _, done, info = env.step(chosen)
                            if done:
                                records.append({'mode': mode, 'side': side, 'seed': seed,
                                                'policy': name, 'outcome': info['outcome'],
                                                'steps': info['steps'], 'timeout': info['timeout'],
                                                'reward': info['reward'],
                                                'scripted_steps': info['script_action_steps']})
                                break
                    finally:
                        env.close()
    summary = {}
    for mode in modes:
        summary[mode] = {}
        for policy in ('frozen_u60', 'candidate'):
            rows = [r for r in records if r['mode'] == mode and r['policy'] == policy]
            summary[mode][policy] = {
                'episodes': len(rows),
                'wins': sum(r['outcome'] == 1 for r in rows),
                'losses': sum(r['outcome'] == -1 for r in rows),
                'timeouts': sum(r['timeout'] for r in rows),
                'mean_outcome': float(np.mean([r['outcome'] for r in rows])),
            }
    return {'summary': summary, 'records': records, 'seeds': seeds,
            'episode_steps': episode_steps, 'warning': 'First-goal RocketSim episodes, not full RLBot matches'}


def check_output_prefix(root: Path, run: str):
    isolated = (root / 'data' / 'isolated').resolve()
    safe_run(run)
    if any(isolated.glob(run + '_*')):
        raise FileExistsError(f'Run prefix already exists: {run}')
    return isolated



def load_original_v60_anchor(root: Path, actor, *, checkpoint_arg: str,
                             source_sha: str, nexto_sha: str):
    """Read-only SHA-pinned u60, independent of the current candidate.

    Never silently replace the original V60 teacher after resuming from a
    newer experimental checkpoint. No deepcopy of TorchScript parameters.
    """
    candidate = (root / checkpoint_arg).resolve()
    allowed = (root / 'data' / 'isolated').resolve()
    if not candidate.is_relative_to(allowed) or not candidate.is_file() or candidate.suffix != '.pt':
        raise ValueError('V60 anchor must be a .pt file inside data/isolated')
    pin = base.sha256(candidate)
    if pin != EXPECTED_V60_SHA256:
        raise RuntimeError(f'Original V60 SHA mismatch: {pin}')
    doc = torch.load(candidate, map_location='cpu', weights_only=True)
    if (doc.get('stage') != 'slater_v027' or doc.get('source_sha') != source_sha or
            doc.get('meta',{}).get('nexto_sha') != nexto_sha or
            not isinstance(doc.get('actor'), dict)):
        raise ValueError('V60 anchor provenance mismatch')
    target = root / 'vendor' / 'nexto' / 'nexto-model.pt'
    anchor = torch.jit.load(str(target), map_location='cpu')
    anchor.load_state_dict(doc['actor'], strict=True)
    anchor.eval()
    with torch.no_grad():
        own = list(anchor.parameters())
        student = list(actor.parameters())
        if len(own) != len(student):
            raise ValueError('Incompatible V60 anchor architecture')
        if {p.untyped_storage().data_ptr() for p in own} & \
                {p.untyped_storage().data_ptr() for p in student}:
            raise RuntimeError('Anchor shares parameter storage with candidate')
        if any(not torch.equal(x, doc['actor'][key])
               for key, x in anchor.state_dict().items()):
            raise RuntimeError('V60 anchor weights differ from protected checkpoint')
    return anchor, pin


def params_unchanged(model, snapshots):
    with torch.no_grad():
        current = list(model.parameters())
        return len(current) == len(snapshots) and all(
            torch.equal(p, initial) for p, initial in zip(current, snapshots))


def make_parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--from-checkpoint', default='data/isolated/slater_v027_campaign01_u0060.pt')
    p.add_argument('--anchor-checkpoint', default='data/isolated/slater_v027_campaign01_u0060.pt',
                   help='Original SHA-pinned V60; cannot substitute an experimental candidate')
    p.add_argument('--run', required=True)
    p.add_argument('--modes', default=','.join(RIVALS))
    p.add_argument('--eval-modes', default='nexto_script,frozen_u60',
                   help='Subset of training rivals to evaluate (faster than all four)')
    p.add_argument('--updates', type=int, default=20)
    p.add_argument('--rollout-steps', type=int, default=1024)
    p.add_argument('--max-episode-steps', type=int, default=300)
    p.add_argument('--checkpoint-every', type=int, default=10)
    p.add_argument('--eval-seeds', type=int, default=2)
    p.add_argument('--eval-steps', type=int, default=600)
    p.add_argument('--epochs', type=int, default=2)
    p.add_argument('--minibatch', type=int, default=128)
    p.add_argument('--actor-lr', type=float, default=2e-6)
    p.add_argument('--critic-lr', type=float, default=1e-4)
    p.add_argument('--teacher-weight', type=float, default=.35)
    p.add_argument('--max-train-seconds', type=float, default=0,
                   help='Stop after next completed update once training exceeds this duration; zero disables')
    p.add_argument('--seed', type=int, default=20261011)
    return p


def validate_args(a):
    modes = normalize_modes(a.modes)
    eval_modes = tuple(x.strip() for x in a.eval_modes.split(','))
    if not eval_modes or len(eval_modes) != len(set(eval_modes)) or any(x not in modes for x in eval_modes):
        raise ValueError('Evaluation opponents must be distinct and included in training rivals')
    safe_run(a.run)
    if not (1 <= a.updates <= 1000 and 128 <= a.rollout_steps <= 32768
            and 120 <= a.max_episode_steps <= 4500 and 1 <= a.checkpoint_every <= 1000
            and 1 <= a.eval_seeds <= 32 and 60 <= a.eval_steps <= 4500
            and 1 <= a.epochs <= 8 and 16 <= a.minibatch <= a.rollout_steps
            and 1 <= a.seed < 2**31 - 2_000_000):
        raise ValueError('Unsafe count/seed bounds')
    if not (0 < a.actor_lr <= 1e-5 and 0 < a.critic_lr <= 1e-3
            and .05 <= a.teacher_weight <= 1 and
            math.isfinite(a.max_train_seconds) and a.max_train_seconds >= 0):
        raise ValueError('Unsafe optimizer/clock bounds')
    return modes


def run(argv=None):
    a = make_parser().parse_args(argv)
    modes = validate_args(a)
    eval_modes = tuple(x.strip() for x in a.eval_modes.split(','))
    root = Path.cwd().resolve()
    checkpoint = (root / a.from_checkpoint).resolve()
    if prev.control_hash() != prev.EXPECTED_SCRIPT_SHA256:
        raise RuntimeError('Bundled original Nexto kickoff controls have changed')
    output_dir = check_output_prefix(root, a.run)
    torch.set_num_threads(2)
    torch.manual_seed(a.seed); np.random.seed(a.seed); random.seed(a.seed)
    actor, original, nexto, actions, doc, provenance = prev.load_protected(root, checkpoint)
    if not all(k in doc for k in ('critic', 'actor_optimizer', 'critic_optimizer')):
        raise ValueError('Full PPO checkpoint required')
    critic = base.ValueNet()
    critic.load_state_dict(doc['critic'])
    ao = torch.optim.Adam(actor.parameters(), lr=a.actor_lr)
    co = torch.optim.Adam(critic.parameters(), lr=a.critic_lr)
    ao.load_state_dict(doc['actor_optimizer']); co.load_state_dict(doc['critic_optimizer'])
    for opt, lr in ((ao, a.actor_lr), (co, a.critic_lr)):
        for group in opt.param_groups:group['lr'] = lr
    anchor, anchor_sha = load_original_v60_anchor(
        root, actor, checkpoint_arg=a.anchor_checkpoint,
        source_sha=provenance['source_sha'], nexto_sha=provenance['nexto_sha'])
    protected = {k: [p.detach().clone() for p in m.parameters()]
                 for k, m in (('anchor', anchor), ('original', original), ('nexto', nexto))}
    original_sha = base.sha256(checkpoint)
    if original_sha != provenance['candidate_sha']:
        raise RuntimeError('Source checkpoint hash mismatch')
    begin_eval = compare_policies(actor, anchor, original, nexto, actions,
                                  modes=eval_modes, seeds=a.eval_seeds, episode_steps=a.eval_steps,
                                  seed_base=a.seed + 700001)
    print('V040_BASELINE', json.dumps(begin_eval['summary'], sort_keys=True), flush=True)
    from afk_team_research import TeamObserver
    env = RivalEnv(actions, TeamObserver(), (original, nexto), anchor,
                   max_steps=a.max_episode_steps, modes=modes)
    logs = []
    try:
        episode_seed = a.seed + 10000
        obs = env.reset(episode_seed)
        start_update = int(doc['global_updates'])
        start_time = time.perf_counter()
        for i in range(a.updates):
            rows, completed, obs, episode_seed, trunc_boot = collect_continuous(
                actor, critic, env, obs, episode_seed, a.rollout_steps)
            metrics = base.update(actor, anchor, critic, ao, co, rows,
                                  a.epochs, a.minibatch, a.teacher_weight,
                                  a.seed + i + start_update + 1, 'cpu')
            update_id = start_update + i + 1
            metrics.update({'update': update_id, 'decisions': a.rollout_steps,
                            'episodes_finished': len(completed),
                            'timeouts_bootstrapped': trunc_boot,
                            'rivals_finished': [x['opponent'] for x in completed],
                            'wins': sum(x['outcome'] == 1 for x in completed),
                            'losses': sum(x['outcome'] == -1 for x in completed),
                            'timeout_episodes': sum(bool(x['timeout']) for x in completed)})
            logs.append(metrics)
            print('V040_UPDATE', json.dumps(metrics, sort_keys=True), flush=True)
            due_to_time = bool(a.max_train_seconds > 0 and
                               time.perf_counter()-start_time >= a.max_train_seconds)
            is_last = i+1 == a.updates or due_to_time
            if (i+1) % a.checkpoint_every != 0 and not is_last:
                continue
            if base.sha256(checkpoint) != original_sha or \
                    base.sha256(root / a.anchor_checkpoint) != anchor_sha or \
                    base.sha256(root / 'vendor/nexto/nexto-model.pt') != provenance['nexto_sha']:
                raise RuntimeError('Protected artifact checksum mismatch')
            from slater_research.checkpoint import CYCLE9
            if base.sha256(root / CYCLE9) != provenance['source_sha']:
                raise RuntimeError('Protected Cycle9 checkpoint changed')
            for name, model in (('anchor', anchor), ('original', original), ('nexto', nexto)):
                if not params_unchanged(model, protected[name]):
                    raise RuntimeError(f'Frozen {name} parameters were modified')
            test = compare_policies(actor, anchor, original, nexto, actions,
                                    modes=eval_modes, seeds=a.eval_seeds,
                                    episode_steps=a.eval_steps, seed_base=a.seed + 700001)
            print('V040_EVAL', update_id, json.dumps(test['summary'], sort_keys=True), flush=True)
            pt = output_dir / f'{a.run}_u{update_id:04d}.pt'
            rp = output_dir / f'{a.run}_u{update_id:04d}.json'
            base.check_output(pt, root)
            base.check_output(rp, root, '.json')
            meta = {'version': VERSION, 'stage': 'slater_v040',
                    'status': 'EXPERIMENT_ONLY_NOT_VALIDATED_RLBOT',
                    'source_checkpoint_sha': original_sha,
                    'protected_v60_sha256': anchor_sha,
                    'source_checkpoint': str(checkpoint),
                    'base_cycle9_sha': provenance['source_sha'],
                    'nexto_sha': provenance['nexto_sha'],
                    'script_sha256': provenance['script_sha256'],
                    'args': vars(a), 'modes': list(modes), 'eval_modes': list(eval_modes),
                    'total_new_decisions': (i+1)*a.rollout_steps,
                    'global_updates': update_id,
                    'starting_evaluation': begin_eval,
                    'evaluation': test,
                    'recent_updates': logs[-a.checkpoint_every:],
                    'exit_due_to_time_budget': due_to_time,
                    'warning': 'Never promote until paired long/full matches vs real stock Nexto.'}
            payload = {'stage': 'slater_v037', 'source_sha': provenance['source_sha'],
                       'global_updates': update_id, 'actor': actor.state_dict(),
                       'critic': critic.state_dict(),
                       'actor_optimizer': ao.state_dict(),
                       'critic_optimizer': co.state_dict(), 'meta': {
                            'nexto_sha': provenance['nexto_sha'],
                            'origin_stage': 'slater_v040',
                            'full_report': meta}}
            base.save_create_only(pt, payload)
            prev.report_create(str(rp), root, meta)
            print('V040_SAVED', pt, flush=True)
            if due_to_time:
                print('V040_TIME_LIMIT_REACHED', flush=True)
                break
    finally:
        env.close()


if __name__ == '__main__':
    run()
