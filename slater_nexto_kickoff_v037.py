"""Slater v0.3.7: physically stepped Nexto v4 kickoff opponent + gated PPO.

Uses the exact 168-tick sequence from RLBotPack Necto/Nexto/bot.py as of the
supplied archive, not a learned Slater kickoff. Keeps V60 and vendor assets read-only.

NOTE: the RocketSim kickoff flag / RLBot packet scheduling are not identical.
This is a controlled SIMULATOR APPROXIMATION, not a proof of in-game parity.
The 90-action policy cannot reproduce every continuous scripted controller value.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import time

import numpy as np
import torch

import slater_cycle9_native_ppo_v025 as base
import slater_cycle9_train_v027 as previous_train

VERSION = 'v0.3.7'
EXPECTED_NEXTO_SHA = previous_train.EXPECTED_NEXTO_SHA
# RLBotPack-master/RLBotPack/Necto/Nexto/bot.py supplied by user (2026-10-11)
# Control layout: throttle, steer, pitch, yaw, roll, jump, boost, handbrake.
STAGES = (
    (44, (1, 0, 0, 0, 0, 0, 1, 0)),
    (16, (1, -1, 0, 0, 0, 0, 1, 0)),
    (8,  (1, 0, 0, 0, 0, 1, 1, 0)),
    (4,  (1, 0, 0, 0, 0, 0, 1, 0)),
    (4,  (1, 0, -.7, .8, 0, 1, 1, 0)),
    (52, (1, 0, 1, 0, 0, 0, 1, 0)),
    (40, (1, 0, .5, 0, 1, 0, 0, 0)),
)
SCRIPT_TICKS = sum(n for n, _ in STAGES)
EXPECTED_SCRIPT_SHA256 = '6f3b9fadf306e5f1275a149ecb672028258086586cbdd1190fe533c25248fc88'
KICKOFF_CONTROLS = np.concatenate([
    np.tile(np.asarray(row, dtype=np.float32), (n, 1))
    for n, row in STAGES], axis=0)
assert KICKOFF_CONTROLS.shape == (168, 8)


def control_hash(arr=KICKOFF_CONTROLS):
    return hashlib.sha256(np.asarray(arr, dtype='<f4').tobytes()).hexdigest()


def grouped_control(tick: int, *, enabled: bool, active: bool, nn_control, action_repeat=8):
    """One 8-tick RocketSim action, including 4-tick RLBot script boundaries.

    `active`: result of the current RocketSim ball-y kickoff predicate.
    Updates the controller every physics tick within RocketSimEngine.step().
    Falls back to the current NN action past the 168-tick scripted window.
    """
    fallback = np.asarray(nn_control, dtype=np.float32).reshape(8)
    out = np.tile(fallback[None], (action_repeat, 1))
    if enabled and active and tick < SCRIPT_TICKS:
        count = min(action_repeat, SCRIPT_TICKS - tick)
        out[:count] = KICKOFF_CONTROLS[tick:tick + count]
    return out


def is_stationary_center(ball_y: float, *, tolerance=1e-4):
    """Approximate RLBot's `ball.location.y == 0` kickoff override condition."""
    return math.isfinite(ball_y) and abs(ball_y) <= tolerance


def sample_nexto_action(opponent, obs, *, beta: float, device='cpu'):
    with torch.no_grad():
        logits = base.logits_of(opponent, base.to_tensors(obs, device)).reshape(-1)
        if beta == 1:
            return int(logits.argmax().item())
        if beta != .5:
            raise ValueError('Only RLBot beta 1 and 0.5 are implemented')
        # RLBotPack Agent.act: log((beta+1)/(1-beta), 3) => 1.0 when beta==0.5.
        return int(torch.distributions.Categorical(logits=logits).sample().item())


class ScriptedNextoEnv(previous_train.SideBalanced1v1):
    """Same 1v1 physics/rewards as v027, with Nexto controller override.

    Modes:
      nexto_greedy: Nexto NN argmax (same as v027)
      nexto_script: hardcoded kickoff, no stochastic NN actions
      nexto_stock_approx: hardcoded kickoff + beta=.5 sampling when ball y=0
      cycle9: frozen original Cycle9
    Each mode is played on both team sides before advancing to next mode.
    """
    VALID_MODES = ('nexto_greedy', 'nexto_script', 'nexto_stock_approx', 'cycle9')

    def __init__(self, actions, observer, opponents, max_steps, device,
                 modes=('nexto_script', 'nexto_greedy', 'cycle9'), fixed_side=None):
        if not modes or any(m not in self.VALID_MODES for m in modes):
            raise ValueError('Unknown/empty opponent mode')
        if fixed_side not in (None, 'blue', 'orange'):
            raise ValueError('Invalid fixed side')
        self.modes = tuple(modes)
        self.fixed_side = fixed_side
        self.script_action_steps = 0
        self.stochastic_action_steps = 0
        self.neural_action_steps = 0
        self.last_control_source = None
        self.kickoff_ball_touched = False
        super().__init__(actions, observer, opponents, max_steps, device)
        self.opponents = tuple(opponents)
        if len(self.opponents) != 2:
            raise ValueError('Expected frozen Cycle9 and frozen Nexto')

    def reset(self, seed):
        # Base SideBalanced.reset increments episode count. Replace opponent
        # selection afterwards; do NOT inherit its 2-way alternation.
        obs = super().reset(seed)
        index = self.episode_count - 1
        self.student_side = self.fixed_side or ('blue' if index % 2 == 0 else 'orange')
        mode = self.modes[(index // 2) % len(self.modes)]
        self.current_opponent = mode
        self.opponent = self.opponents[0] if mode == 'cycle9' else self.opponents[1]
        self.script_action_steps = 0
        self.stochastic_action_steps = 0
        self.neural_action_steps = 0
        self.last_control_source = None
        self.kickoff_ball_touched = False
        self.obs = base.read_obs(self.state, self.previous, self.observer,
                                 'blue-0' if self.student_side == 'blue' else 'orange-0')
        return self.obs

    def _opponent_commands(self, oid):
        mode = self.current_opponent
        ball_y = float(self.state.ball.position[1])
        active = (not self.kickoff_ball_touched and is_stationary_center(ball_y)
                  and self.t * base.ACTION_REPEAT < SCRIPT_TICKS)
        opp_obs = base.read_obs(self.state, self.previous, self.observer, oid)
        beta = .5 if mode == 'nexto_stock_approx' and active else 1.
        index = sample_nexto_action(self.opponent, opp_obs, beta=beta, device=self.device)
        nn = np.asarray(self.actions[index], dtype=np.float32)
        uses_script = mode in ('nexto_script', 'nexto_stock_approx') and active
        cmds = grouped_control(self.t * base.ACTION_REPEAT, enabled=uses_script,
                               active=active, nn_control=nn,
                               action_repeat=base.ACTION_REPEAT)
        if uses_script:
            self.script_action_steps += 1
            self.last_control_source = 'script'
        elif beta == .5:
            self.stochastic_action_steps += 1
            self.last_control_source = 'stochastic'
        else:
            self.neural_action_steps += 1
            self.last_control_source = 'nn'
        return cmds

    def step(self, student_action: int):
        sid = 'blue-0' if self.student_side == 'blue' else 'orange-0'
        oid = 'orange-0' if sid == 'blue-0' else 'blue-0'
        sign = 1. if self.student_side == 'blue' else -1.
        before_ball_y = float(self.state.ball.position[1])
        before_dist = float(np.linalg.norm(
            self.state.cars[sid].physics.position - self.state.ball.position))
        opponent_commands = self._opponent_commands(oid)
        student_control = np.asarray(self.actions[int(student_action)], dtype=np.float32).reshape(8)
        student_commands = np.repeat(student_control[None], base.ACTION_REPEAT, axis=0)
        self.state = self.engine.step({sid: student_commands, oid: opponent_commands}, {})
        # RLBot observes the controller last applied. The real RLBot action
        # updates each frame, while TeamObserver here only tracks one per 8 ticks.
        self.previous = {sid: student_control.copy(), oid: opponent_commands[-1].copy()}
        self.t += 1
        car = self.state.cars[sid]
        ball = self.state.ball
        progress = float(np.clip(sign * (ball.position[1] - before_ball_y) / 500., -.5, .5))
        closing = float(np.clip((before_dist - np.linalg.norm(
            car.physics.position - ball.position)) / 500., -.5, .5))
        stouches = int(car.ball_touches)
        otouches = int(self.state.cars[oid].ball_touches)
        if stouches or otouches:
            self.kickoff_ball_touched = True
        self.touches += stouches
        self.opponent_touches += otouches
        goal = bool(self.state.goal_scored)
        outcome = int(sign * np.sign(float(ball.position[1]))) if goal else 0
        reward = .20 * progress + .07 * closing + .35 * stouches - .002 + 10. * outcome
        if not math.isfinite(reward):
            raise FloatingPointError('Nonfinite reward')
        self.total_reward += reward
        done = bool(goal or self.t >= self.max_steps)
        self.obs = base.read_obs(self.state, self.previous, self.observer, sid)
        return self.obs, float(reward), done, {
            'outcome': outcome, 'student_side': self.student_side,
            'opponent': self.current_opponent,
            'student_touches': self.touches,
            'opponent_touches': self.opponent_touches,
            'reward': self.total_reward, 'steps': self.t,
            'ball_y': float(ball.position[1]),
            'timeout': bool(done and not goal),
            'script_action_steps': self.script_action_steps,
            'neural_action_steps': self.neural_action_steps,
            'stochastic_action_steps': self.stochastic_action_steps,
        }


def load_protected(root: Path, checkpoint: Path):
    from slater_research.checkpoint import CYCLE9, CYCLE9_SHA, cycle9_pair
    from nexto_teacher import nexto_actions
    source = root / CYCLE9
    nexto_file = root / 'vendor' / 'nexto' / 'nexto-model.pt'
    source_sha, nexto_sha = base.sha256(source), base.sha256(nexto_file)
    if source_sha != CYCLE9_SHA or nexto_sha != EXPECTED_NEXTO_SHA:
        raise RuntimeError('Protected Cycle9 / Nexto SHA mismatch')
    if not checkpoint.is_relative_to((root / 'data' / 'isolated').resolve()) or not checkpoint.is_file():
        raise ValueError('Checkpoint must exist under data/isolated')
    doc = torch.load(checkpoint, map_location='cpu', weights_only=True)
    if doc.get('stage') not in ('slater_v027', 'slater_v037') or doc.get('source_sha') != CYCLE9_SHA:
        raise ValueError('Expected original V27 or V37 Cycle9-derived checkpoint')
    if doc.get('meta', {}).get('nexto_sha') != EXPECTED_NEXTO_SHA:
        raise ValueError('Nexto provenance mismatch')
    actor, original = cycle9_pair(root)
    actor.load_state_dict(doc['actor'], strict=True)
    actor.eval(); original.eval()
    for p in original.parameters():p.requires_grad_(False)
    nexto = torch.jit.load(str(nexto_file), map_location='cpu')
    nexto.eval()
    for p in nexto.parameters():p.requires_grad_(False)
    actions = np.stack([np.asarray(nexto_actions()[i], dtype=np.float32).reshape(8) for i in range(90)])
    if actions.shape != (90, 8):
        raise ValueError('Unexpected Nexto action shape')
    return (actor, original, nexto, actions, doc,
            {'source_sha': source_sha, 'nexto_sha': nexto_sha,
             'candidate_sha': base.sha256(checkpoint),
             'script_sha256': control_hash()})


def evaluate(actor, original, nexto, actions, *, modes, seeds, horizon, seed_base):
    """Fresh RocketSim environment per episode, both sides, same seeds."""
    from afk_team_research import TeamObserver
    from slater_cycle9_paired_eval_v026_fixed import greedy_action
    records = []
    for i in range(seeds):
        seed = seed_base + 997 * i
        for side in ('blue', 'orange'):
            for mode in modes:
                for policy, model in (('original', original), ('candidate', actor)):
                    env = ScriptedNextoEnv(actions, TeamObserver(), (original, nexto),
                                           horizon, 'cpu', modes=(mode,), fixed_side=side)
                    try:
                        obs = env.reset(seed)
                        while True:
                            obs, _, done, info = env.step(greedy_action(model, obs, 'cpu'))
                            if done:
                                records.append({
                                    'seed': seed, 'side': side, 'mode': mode,
                                    'policy': policy, 'steps': info['steps'],
                                    'outcome': info['outcome'],
                                    'touches': info['student_touches'],
                                    'opponent_touches': info['opponent_touches'],
                                    'script_steps': info['script_action_steps'],
                                })
                                break
                    finally:
                        env.close()
    summary = {}
    for mode in modes:
        summary[mode] = {}
        for pol in ('original', 'candidate'):
            rr = [r for r in records if r['mode'] == mode and r['policy'] == pol]
            summary[mode][pol] = dict(
                episodes=len(rr), wins=sum(r['outcome'] == 1 for r in rr),
                losses=sum(r['outcome'] == -1 for r in rr),
                timeouts=sum(r['outcome'] == 0 for r in rr),
                scripted_decisions=sum(r['script_steps'] for r in rr),
                win_rate=sum(r['outcome'] == 1 for r in rr) / len(rr),
                mean_outcome=float(np.mean([r['outcome'] for r in rr])),
            )
    return {'summary': summary, 'records': records, 'seed_count': seeds,
            'episode_steps': horizon, 'paired_blue_orange': True,
            'notes': ['Episode tests, not full five-minute matches.',
                      'Simulator action/observation parity with official RLBot Nexto is not yet established.',
                      'Script toggle is a RocketSim approximation of RLBot kickoff-pause behavior.']}


def report_create(path: str, root: Path, payload: dict):
    dest = base.check_output(path, root, '.json')
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('x', encoding='utf-8') as out:
        json.dump(payload, out, indent=2, sort_keys=True)
    print('V037_REPORT', str(dest))
    return dest


def train_loop(args, root, actor, original, nexto, actions, doc, provenance):
    from afk_team_research import TeamObserver
    if 'critic' not in doc or 'actor_optimizer' not in doc or 'critic_optimizer' not in doc:
        raise ValueError('Training requires complete v027/v037 PPO checkpoint with critic and optimizers')
    isolated = root / 'data' / 'isolated'
    run = previous_train.safe_run(args.run)
    if any(isolated.glob(run + '_u*')) or (isolated / (run + '_manifest.json')).exists():
        raise FileExistsError('Experiment run prefix already exists: ' + run)
    if not (1 <= args.updates <= 200 and 128 <= args.rollout_steps <= 16384 and
            1 <= args.eval_seeds <= 64 and 30 <= args.eval_steps <= 4500 and
            1 <= args.checkpoint_every <= args.updates and
            16 <= args.minibatch <= args.rollout_steps):
        raise ValueError('Training guardrail failed')
    # Learning continues from V60's critic and optimizers; do not start from Cycle9.
    critic = base.ValueNet()
    actor_opt = torch.optim.Adam(actor.parameters(), lr=args.actor_lr)
    critic_opt = torch.optim.Adam(critic.parameters(), lr=args.critic_lr)
    critic.load_state_dict(doc['critic'])
    actor_opt.load_state_dict(doc['actor_optimizer'])
    critic_opt.load_state_dict(doc['critic_optimizer'])
    # Override learning rate explicitly rather than unknowingly inheriting source.
    for opt, lr in ((actor_opt, args.actor_lr), (critic_opt, args.critic_lr)):
        for group in opt.param_groups:group['lr'] = lr
    start = int(doc.get('global_updates', 0))
    if start < 1:raise ValueError('Invalid source update index')
    # Anchor KL to the STARTING u60 policy, NOT original Cycle9.
    # This reduces needless reversion to an older policy.
    teacher = copy.deepcopy(actor)
    teacher.eval()
    for p in teacher.parameters():p.requires_grad_(False)
    teacher_initial = [p.detach().clone() for p in teacher.parameters()]
    before = evaluate(actor, original, nexto, actions,
                      modes=('nexto_greedy', 'nexto_script'),
                      seeds=args.eval_seeds, horizon=args.eval_steps,
                      seed_base=args.seed + 500001)
    print('V037_BEFORE', json.dumps(before['summary'], sort_keys=True), flush=True)
    if before['summary']['nexto_script']['candidate']['scripted_decisions'] == 0:
        raise RuntimeError('Scripted Nexto never activated in baseline evaluation; refusing training')
    mix = ('nexto_script', 'nexto_greedy', 'cycle9') if args.mix_cycle9 else ('nexto_script', 'nexto_greedy')
    env = ScriptedNextoEnv(actions, TeamObserver(), (original, nexto),
                           max_steps=args.max_episode_steps, device='cpu', modes=mix)
    original_weights = [p.detach().clone() for p in original.parameters()]
    nexto_weights = [p.detach().clone() for p in nexto.parameters()]
    source_hashes = (provenance['source_sha'], provenance['nexto_sha'], provenance['candidate_sha'])
    logs = []
    try:
        for i in range(args.updates):
            update_id = start + i + 1
            rollouts, ends = base.collect(actor, critic, env, args.rollout_steps,
                                          args.seed + update_id * 1373, 'cpu')
            log = base.update(actor, teacher, critic, actor_opt, critic_opt,
                              rollouts, args.epochs, args.minibatch,
                              args.teacher_weight, args.seed + update_id, 'cpu')
            log.update(update=update_id, opponents=[e['opponent'] for e in ends],
                       training_decisions=args.rollout_steps,
                       scripted_decisions=sum(e['script_action_steps'] for e in ends),
                       wins=sum(e['outcome'] == 1 for e in ends),
                       losses=sum(e['outcome'] == -1 for e in ends))
            logs.append(log)
            print('V037_UPDATE', json.dumps(log, sort_keys=True), flush=True)
            if (i + 1) % args.checkpoint_every != 0 and i + 1 != args.updates:
                continue
            from slater_research.checkpoint import CYCLE9
            hashes_now = (base.sha256(root/CYCLE9), base.sha256(root/'vendor'/'nexto'/'nexto-model.pt'),
                          base.sha256(root/args.from_checkpoint))
            if hashes_now != source_hashes:
                raise RuntimeError('Protected file changed during training')
            if any(not torch.equal(p, before) for p, before in zip(teacher.parameters(), teacher_initial)):
                raise RuntimeError('Frozen u60 teacher mutated')
            if any(not torch.equal(p, before) for p, before in zip(original.parameters(), original_weights)):
                raise RuntimeError('Original Cycle9 parameter mutated')
            if any(not torch.equal(p, before) for p, before in zip(nexto.parameters(), nexto_weights)):
                raise RuntimeError('Frozen Nexto parameter mutated')
            ev = evaluate(actor, original, nexto, actions,
                          modes=('nexto_greedy', 'nexto_script'),
                          seeds=args.eval_seeds, horizon=args.eval_steps,
                          seed_base=args.seed + 500001)
            print('V037_EVAL', update_id, json.dumps(ev['summary'], sort_keys=True), flush=True)
            ck = isolated / f'{run}_u{update_id:04d}.pt'
            rp = isolated / f'{run}_u{update_id:04d}.json'
            base.check_output(ck, root); base.check_output(rp, root, '.json')
            metadata = {'stage': 'slater_v037', 'source_sha': provenance['source_sha'],
                        'nexto_sha': provenance['nexto_sha'], 'candidate_sha': provenance['candidate_sha'],
                        'script_sha256': provenance['script_sha256'], 'starting_updates': start,
                        'global_updates': update_id, 'run': run, 'mix': list(mix),
                        'args': vars(args), 'baseline_eval': before, 'evaluation': ev,
                        'kl_teacher': 'source_u60_frozen',
                        'training_logs': logs[-args.checkpoint_every:],
                        'note': 'Experimental; do not promote until independent RLBot validation.'}
            payload = {'stage': 'slater_v037', 'source_sha': provenance['source_sha'],
                       'global_updates': update_id, 'actor': actor.state_dict(),
                       'critic': critic.state_dict(),
                       'actor_optimizer': actor_opt.state_dict(),
                       'critic_optimizer': critic_opt.state_dict(), 'meta': metadata}
            base.save_create_only(ck, payload)
            report_create(str(rp), root, metadata)
    finally:
        env.close()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('audit', 'benchmark', 'train'))
    p.add_argument('--from-checkpoint', default='data/isolated/slater_v027_campaign01_u0060.pt')
    p.add_argument('--out', help='Non-overwriting JSON output for audit or benchmark')
    p.add_argument('--run', default='v037_scripted_nexto_run01', help='New isolated training name')
    p.add_argument('--seeds', type=int, default=4)
    p.add_argument('--episode-steps', type=int, default=240)
    p.add_argument('--updates', type=int, default=2)
    p.add_argument('--rollout-steps', type=int, default=1024)
    p.add_argument('--max-episode-steps', type=int, default=450)
    p.add_argument('--checkpoint-every', type=int, default=2)
    p.add_argument('--eval-seeds', type=int, default=4)
    p.add_argument('--eval-steps', type=int, default=240)
    p.add_argument('--epochs', type=int, default=2)
    p.add_argument('--minibatch', type=int, default=128)
    p.add_argument('--actor-lr', type=float, default=2e-6)
    p.add_argument('--critic-lr', type=float, default=1e-4)
    p.add_argument('--teacher-weight', type=float, default=.35)
    p.add_argument('--mix-cycle9', action='store_true')
    p.add_argument('--seed', type=int, default=20261012)
    a = p.parse_args(argv)
    root = Path.cwd().resolve()
    if control_hash() != EXPECTED_SCRIPT_SHA256:
        raise RuntimeError('Bundled Nexto scripted control table was modified')
    if a.command == 'audit':
        summary = {'version': VERSION, 'reference': 'RLBotPack Necto/Nexto/bot.py',
                   'control_layout': ['throttle','steer','pitch','yaw','roll','jump','boost','handbrake'],
                   'script_ticks': SCRIPT_TICKS, 'script_steps': list(STAGES),
                   'script_sha256': control_hash(),
                   'reference_sha256_matches': control_hash() == EXPECTED_SCRIPT_SHA256,
                   'rocket_sim_timing_warning': 'RLBot kickoff_pause/packet scheduling cannot be matched exactly;',
                   'student_action_limitation': '90 discrete Nexto actions; no continuous mechanics head'}
        print('V037_SCRIPT_AUDIT', json.dumps(summary, sort_keys=True))
        if a.out: report_create(a.out, root, summary)
        return
    if not (2 <= a.seeds <= 64 and 1 <= a.seed < 2**31 - 2000000 and
            30 <= a.episode_steps <= 4500 and 0 < a.actor_lr <= 1e-5 and
            0 < a.critic_lr <= 1e-3 and 0.05 <= a.teacher_weight <= 1 and
            1 <= a.epochs <= 8):
        p.error('Invalid command parameters')
    torch.set_num_threads(2)
    torch.manual_seed(a.seed); np.random.seed(a.seed); random.seed(a.seed)
    checkpoint = (root / a.from_checkpoint).resolve()
    actor, original, nexto, actions, doc, provenance = load_protected(root, checkpoint)
    if a.command == 'benchmark':
        if not a.out:p.error('Benchmark requires --out')
        result = evaluate(actor, original, nexto, actions,
                          modes=('nexto_greedy','nexto_script'),
                          seeds=a.seeds, horizon=a.episode_steps, seed_base=a.seed)
        result.update(provenance=provenance, version=VERSION,
                      status='SIMULATOR_ABLATION_NOT_RLBOT')
        if result['summary']['nexto_script']['candidate']['scripted_decisions'] == 0:
            raise RuntimeError('Scripted Nexto was never activated; check kickoff state/predicate')
        print('V037_BENCHMARK', json.dumps(result['summary'], sort_keys=True))
        report_create(a.out, root, result)
    else:
        if a.out: p.error('Training writes isolated checkpoints; omit --out')
        train_loop(a, root, actor, original, nexto, actions, doc, provenance)

if __name__ == '__main__':
    main()
