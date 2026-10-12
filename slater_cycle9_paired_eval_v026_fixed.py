"""Slater v0.2.6: READ-ONLY, paired Blue/Orange evaluation of Cycle 9 PPO candidate.

Compares Cycle9-vs-Cycle9 and candidate-vs-Cycle9 on identical kickoff seeds
for BOTH candidate teams. No optimizer, no PPO, no replay use, no promotion.
Run in project root with the already-tested v0.2.5 training script present.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import time

import numpy as np
import torch

import slater_cycle9_native_ppo_v025 as old

EXPECTED_NEXTO_SHA256 = 'bf5343b5eeacac6bf7cdb75dac4a5c14ba0f94d820eae75f00a211b6119d69fa'


def protected_output(path: str | Path, root: Path) -> Path:
    dest = old.check_output(path, root, '.json')
    return dest


def result_for_side(goal: bool, final_y: float, side: str) -> int:
    """+1 candidate-side goal, -1 conceded, 0 no score within horizon."""
    if side not in ('blue', 'orange'):
        raise ValueError('Invalid team side')
    if not goal:
        return 0
    if not np.isfinite(final_y) or final_y == 0:
        raise ValueError('Invalid scoring ball y')
    scorer = 'blue' if final_y > 0 else 'orange'
    return 1 if scorer == side else -1


def paired_interval(values: list[float], repeats=3000, seed=773):
    """Bootstrap across independent kickoff SEEDS, combining both team sides per seed."""
    a = np.asarray(values, dtype=np.float64)
    if a.ndim != 1 or len(a) < 2 or not np.isfinite(a).all():
        raise ValueError('Need 2+ finite seed-paired differences')
    gen = np.random.default_rng(seed)
    draw = gen.integers(0, len(a), size=(repeats, len(a)))
    avgs = a[draw].mean(axis=1)
    return {'delta': round(float(a.mean()), 5),
            'bootstrap_95ci': [round(float(v), 5) for v in np.quantile(avgs, [.025, .975])],
            'num_seed_pairs': len(a)}


def greedy_action(actor, obs, device='cpu'):
    with torch.no_grad():
        logits = old.logits_of(actor, old.to_tensors(obs, device))
    return int(logits.argmax(dim=-1).item())


class RoleSwap1v1(old.Native1v1):
    """Candidate controls ORANGE, frozen Cycle9 opponent controls BLUE."""
    def reset(self, seed: int):
        super().reset(seed)
        self.obs = old.read_obs(self.state, self.previous, self.observer, 'orange-0')
        return self.obs

    def step(self, student_action: int):
        opponent_obs = old.read_obs(self.state, self.previous, self.observer, 'blue-0')
        opponent_action = greedy_action(self.opponent, opponent_obs, self.device)
        orange = np.array(self.actions[int(student_action)], dtype=np.float32, copy=True)
        blue = np.array(self.actions[opponent_action], dtype=np.float32, copy=True)
        cmds = {'blue-0': np.repeat(blue[None], old.ACTION_REPEAT, axis=0),
                'orange-0': np.repeat(orange[None], old.ACTION_REPEAT, axis=0)}
        self.state = self.engine.step(cmds, {})
        self.previous = {'blue-0': blue, 'orange-0': orange}
        self.t += 1
        self.touches += int(self.state.cars['orange-0'].ball_touches)
        self.opponent_touches += int(self.state.cars['blue-0'].ball_touches)
        goal = bool(self.state.goal_scored)
        ball_y = float(self.state.ball.position[1])
        outcome = result_for_side(goal, ball_y, 'orange')
        done = goal or self.t >= self.max_steps
        self.obs = old.read_obs(self.state, self.previous, self.observer, 'orange-0')
        return self.obs, 0., done, {
            'outcome': outcome, 'student_touches': self.touches,
            'opponent_touches': self.opponent_touches,
            'steps': self.t, 'ball_y': ball_y, 'timeout': bool(done and not goal),
        }


def one_game(env, actor, seed, side):
    obs = env.reset(seed)
    while True:
        a = greedy_action(actor, obs, env.device)
        obs, _, done, info = env.step(a)
        if done:
            return {'seed': seed, 'side': side,
                    'outcome': info['outcome'], 'touches': info['student_touches'],
                    'opponent_touches': info['opponent_touches'],
                    'steps': info['steps'],
                    'final_ball_progress_uu': round(float(info['ball_y']) * (1 if side == 'blue' else -1), 3)}


def aggregate(items):
    n = len(items)
    return {'games': n, 'wins': sum(x['outcome'] == 1 for x in items),
            'losses': sum(x['outcome'] == -1 for x in items),
            'timeouts': sum(x['outcome'] == 0 for x in items),
            'goal_diff_per_game': round(float(np.mean([x['outcome'] for x in items])), 5),
            'avg_touches': round(float(np.mean([x['touches'] for x in items])), 5),
            'avg_opponent_touches': round(float(np.mean([x['opponent_touches'] for x in items])), 5),
            'avg_steps': round(float(np.mean([x['steps'] for x in items])), 5),
            'avg_final_ball_progress_uu': round(float(np.mean([x['final_ball_progress_uu'] for x in items])), 3)}


def comparison(records):
    per_seed = {}
    for r in records:
        key = (r['seed'], r['side'])
        per_seed.setdefault(key, {})[r['policy']] = r
    seeds = sorted({k[0] for k in per_seed})
    diffs = {'goal_diff': [], 'win': [], 'touches': [], 'ball_progress_uu': []}
    for seed in seeds:
        samples = []
        for side in ('blue', 'orange'):
            item = per_seed[(seed, side)]
            orig = item['original']
            candidate = item['candidate']
            samples.append({'goal_diff': float(candidate['outcome'] - orig['outcome']),
                            'win': float(int(candidate['outcome'] == 1) - int(orig['outcome'] == 1)),
                            'touches': float(candidate['touches'] - orig['touches']),
                            'ball_progress_uu': float(candidate['final_ball_progress_uu'] - orig['final_ball_progress_uu'])})
        for k in diffs:
            diffs[k].append(sum(x[k] for x in samples) / 2.)
    return {k: paired_interval(v) for k, v in diffs.items()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--seeds', type=int, default=32)
    p.add_argument('--max-episode-steps', type=int, default=360,
                   help='360 decisions at action_repeat=8 corresponds to 24 seconds')
    p.add_argument('--seed', type=int, default=20271227)
    args = p.parse_args()
    if not (4 <= args.seeds <= 512 and 30 <= args.max_episode_steps <= 1800):
        p.error('Use 4-512 seeds and 30-1800 episode decisions')
    root = Path.cwd().resolve()
    checkpoint = Path(args.checkpoint).resolve()
    # Evaluation must read a candidate under the isolated directory, NEVER a source checkpoint.
    isolated = (root/'data'/'isolated').resolve()
    if not checkpoint.is_relative_to(isolated) or not checkpoint.is_file() or checkpoint.suffix != '.pt':
        p.error('Candidate checkpoint must be an existing .pt inside data/isolated')
    output = protected_output(args.out, root)
    if output == checkpoint:
        p.error('Report cannot overwrite checkpoint')

    from slater_research.checkpoint import CYCLE9, CYCLE9_SHA, cycle9_pair
    from afk_team_research import TeamObserver
    from nexto_teacher import nexto_actions
    torch.set_num_threads(2)
    torch.manual_seed(20261011)
    source = root/CYCLE9
    nexto = root/'vendor/nexto/nexto-model.pt'
    source_sha = old.sha256(source)
    nexto_sha = old.sha256(nexto)
    if source_sha != CYCLE9_SHA:
        raise RuntimeError('Original Cycle9 checksum mismatch')
    if nexto_sha != EXPECTED_NEXTO_SHA256:
        raise RuntimeError('Protected Nexto script checksum mismatch')
    actor, teacher = cycle9_pair(root)
    candidate = torch.load(checkpoint, map_location='cpu', weights_only=True)
    if candidate.get('source_sha') != CYCLE9_SHA or not isinstance(candidate.get('actor'), dict):
        raise RuntimeError('Candidate is not derived from protected Cycle9')
    actor.load_state_dict(candidate['actor'], strict=True)
    actor.eval(); teacher.eval()
    # TorchScript ScriptModule does not expose nn.Module.requires_grad_().
    # Freeze each underlying parameter instead; this evaluator also uses no_grad.
    for model in (actor, teacher):
        for parameter in model.parameters():
            parameter.requires_grad_(False)
    lookup = nexto_actions()
    actions = np.stack([np.asarray(lookup[i],dtype=np.float32).reshape(8) for i in range(90)])
    if actions.shape != (90,8):
        raise RuntimeError(f'Unexpected native action format: {actions.shape}')
    actor_diff = float(np.sqrt(sum((p-q).detach().square().sum().item() for p,q in zip(actor.parameters(),teacher.parameters()))))
    print('READ_ONLY_SIDE_SWAPPED_EVAL original_cycle9_vs_candidate', flush=True)
    print('SOURCE_CYCLE9_SHA256', source_sha, 'CANDIDATE_SHA256', old.sha256(checkpoint), 'ACTOR_L2_DELTA', round(actor_diff,6), flush=True)
    print('SEEDS', args.seeds, 'SIDES 2', 'MAX_STEPS', args.max_episode_steps, 'ACTION_REPEAT', old.ACTION_REPEAT, flush=True)
    begin = time.perf_counter()
    obs_builder = TeamObserver()
    blue_env = old.Native1v1(actions, obs_builder, teacher, max_steps=args.max_episode_steps, device='cpu')
    orange_env = RoleSwap1v1(actions, obs_builder, teacher, max_steps=args.max_episode_steps, device='cpu')
    results = []
    try:
        for i in range(args.seeds):
            seed = args.seed + 997*i
            for side,env in (('blue',blue_env),('orange',orange_env)):
                for name,model in (('original',teacher),('candidate',actor)):
                    r = one_game(env,model,seed,side)
                    r['policy'] = name
                    results.append(r)
            if (i+1)%8==0 or i+1==args.seeds:
                print('PROGRESS',i+1,'/',args.seeds,'paired kickoff seeds complete',flush=True)
    finally:
        blue_env.close(); orange_env.close()
    aggs = {name:aggregate([r for r in results if r['policy']==name]) for name in ('original','candidate')}
    per_side = {name:{side:aggregate([r for r in results if r['policy']==name and r['side']==side])
                       for side in ('blue','orange')} for name in ('original','candidate')}
    paired = comparison(results)
    if old.sha256(source) != source_sha or old.sha256(nexto) != nexto_sha:
        raise RuntimeError('Protected sources changed')
    meta = {'version':'v026','purpose':'read_only_side_swapped_greedy_cycle9_evaluation',
            'warnings':['Matched kickoff seeds and mirrored team roles; not a full match benchmark.',
                        'Outcomes of short games often time out; goal difference confidence intervals may be wide.',
                        'Never promotes, resumes, or optimizes a checkpoint.'],
            'checkpoint':str(checkpoint),'source_cycle9_sha256':source_sha,
            'candidate_sha256':old.sha256(checkpoint),'nexto_sha256':nexto_sha,
            'actor_l2_difference':actor_diff,'max_episode_steps':args.max_episode_steps,
            'action_repeat':old.ACTION_REPEAT,'seed_count':args.seeds,
            'elapsed_seconds':time.perf_counter()-begin,
            'overall':aggs,'by_side':per_side,'paired_comparisons':paired,
            'game_results':results}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as f:
        json.dump(meta,f,indent=2)
    print('OVERALL_ORIGINAL',json.dumps(aggs['original'],sort_keys=True),flush=True)
    print('OVERALL_CANDIDATE',json.dumps(aggs['candidate'],sort_keys=True),flush=True)
    print('BY_SIDE',json.dumps(per_side,sort_keys=True),flush=True)
    print('PAIRED_COMPARISONS',json.dumps(paired,sort_keys=True),flush=True)
    print('SAVED_READ_ONLY_EVAL',output,flush=True)
    print('NO_TRAINING_NO_PROMOTION_CYCLE9_AND_NEXTO_UNCHANGED',flush=True)

if __name__=='__main__':
    main()
