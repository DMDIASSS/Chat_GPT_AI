"""Pure-Python statistics and planning for the scenario evaluation add-on.

A *pair* shares a simulator initialization seed and swaps the evaluated policy's
team side. Pair-level bootstrap avoids treating correlated sides as independent.
"""
from __future__ import annotations

import random
import statistics
from typing import Any

KINDS = ('kickoff', 'ground', 'defense', 'aerial', 'wall')


def generate_plan(master_seed: int, pairs_per_kind: int) -> dict[str, list[int]]:
    if pairs_per_kind <= 0:
        raise ValueError('pairs_per_kind must be >= 1')
    # Each scenario gets its OWN deterministic stream, so extending from 8 to 30
    # pairs keeps the original 8 per scenario for persistent-cache reuse.
    plan = {}
    for i, kind in enumerate(KINDS):
        rng = random.Random(f'{master_seed}:scenario:{i}:{kind}')
        plan[kind] = [rng.randrange(1, 2**31) for _ in range(pairs_per_kind)]
    return plan


def score(outcome: str) -> float:
    if outcome == 'ours':
        return 1.0
    if outcome == 'draw':
        return 0.5
    if outcome == 'nexto':
        return 0.0
    raise ValueError(f'Unknown outcome: {outcome}')


def _mean(xs: list[float]) -> float:
    return statistics.mean(xs) if xs else 0.0


def interval(pair_scores: list[float], *, seed: int, resamples: int = 2000) -> tuple[float, float]:
    if not pair_scores:
        raise ValueError('no observations')
    if len(pair_scores) == 1:
        return (0.0, 1.0)  # one pair is insufficient to quantify uncertainty
    rng = random.Random(seed)
    n = len(pair_scores)
    means = [sum(pair_scores[rng.randrange(n)] for _ in range(n)) / n
             for _ in range(resamples)]
    means.sort()
    return (means[int((resamples-1)*0.025)], means[int((resamples-1)*0.975)])


def aggregate_pair_rows(rows: list[dict], *, ci_seed: int = 9021) -> dict[str, Any]:
    if not rows:
        raise ValueError('no pair rows')
    values, outcomes = [], {'ours': 0, 'nexto': 0, 'draw': 0}
    unique_fingerprints = set()
    side_start_mismatches = 0
    touches_a = touches_b = total_decisions = 0
    for row in rows:
        sides = row['sides']
        if len(sides) != 2 or {s['orange'] for s in sides} != {False, True}:
            raise ValueError('each pair needs one blue and one orange episode')
        values.append(_mean([score(s['outcome']) for s in sides]))
        for s in sides:
            outcomes[s['outcome']] += 1
            unique_fingerprints.add(s['fingerprint'])
            touches_a += s['touches_a']
            touches_b += s['touches_b']
            total_decisions += s['decisions']
        if sides[0]['fingerprint'] != sides[1]['fingerprint']:
            side_start_mismatches += 1
    lower, upper = interval(values, seed=ci_seed)
    return {
        'pairs': len(rows), 'episodes': 2*len(rows), 'outcomes': outcomes,
        'score': _mean(values), 'bootstrap_95_percent_interval': [lower, upper],
        'pair_scores': values,
        'unique_initial_states': len(unique_fingerprints),
        'paired_initial_state_mismatches': side_start_mismatches,
        'touches': {'model_a': touches_a, 'model_b': touches_b},
        'decisions': total_decisions,
    }


def paired_difference(a: list[dict], b: list[dict], *, seed: int = 817, resamples: int = 2000) -> dict:
    """Same scenario+seed *and both sides* for A and B vs a common opponent."""
    def by_key(rows):
        return {(r['scenario'],r['seed']): r for r in rows}
    a_map, b_map = by_key(a), by_key(b)
    keys = sorted(set(a_map).intersection(b_map))
    if not keys:
        raise ValueError('no matched starts for comparison')
    def pair_value(r):
        return _mean([score(s['outcome']) for s in r['sides']])
    diffs = [pair_value(a_map[k])-pair_value(b_map[k]) for k in keys]
    if len(diffs) == 1:
        bounds=(-1.0, 1.0)
    else:
        # Bootstrap differences at paired-start granularity.
        rng = random.Random(seed)
        n = len(diffs)
        samples = sorted(sum(diffs[rng.randrange(n)] for _ in range(n))/n
                         for _ in range(resamples))
        bounds=(samples[int((resamples-1)*.025)],samples[int((resamples-1)*.975)])
    return {'paired_starts': len(keys), 'score_difference': _mean(diffs),
            'bootstrap_95_percent_interval': list(bounds),
            'interpretation': 'Exploratory paired confidence interval; selection and multiple comparisons inflate optimism.'}

# Kickoff-quality is a *separate* metric from first-goal W/L/D.
# Both players can gain boost safely. For this reason the per-player success
# flags are not forced to add up to 100%; the exclusive result is 'contested'.
KICKOFF_SNAPSHOT_DECISIONS = 60  # 4 seconds at 15 actions per second
KICKOFF_GOAL_DECISIONS = 90      # 6 seconds at 15 actions per second
KICKOFF_CLOSE_DISTANCE = 1400.0  # Unreal units (roughly one car-length x ~12)
KICKOFF_CLOSER_MARGIN = 150.0
KICKOFF_MIN_PICKUP = 10.0       # A small-pad pickup may be partially consumed
KICKOFF_MIN_END_BOOST = 30.0


def kickoff_is_dangerous(*, ball_x: float, oriented_ball_y: float,
                         oriented_ball_vy: float, my_distance: float,
                         opponent_distance: float) -> bool:
    """Conservative kickoff danger heuristic, not a goal-probability model.

    Oriented coordinate system: negative Y is toward the evaluated player's own
    goal. A close ball in the goal mouth or a fast opponent-favored ball into our
    half means collecting boost alone should not be called a won kickoff.
    """
    goal_mouth_threat = oriented_ball_y < -3450 and abs(ball_x) < 2100
    fast_opponent_counter = (oriented_ball_y < -900 and oriented_ball_vy < -600
                             and opponent_distance + 250 < my_distance)
    return bool(goal_mouth_threat or fast_opponent_counter)


def kickoff_player_status(snapshot: dict, side: str) -> dict:
    """Classify a single player's quality at the 4s kickoff snapshot."""
    p = snapshot[side]
    opp = snapshot['b' if side == 'a' else 'a']
    close = (p['ball_distance'] <= KICKOFF_CLOSE_DISTANCE
             and p['ball_distance'] + KICKOFF_CLOSER_MARGIN <= opp['ball_distance'])
    danger = kickoff_is_dangerous(
        ball_x=snapshot['ball_x'], oriented_ball_y=p['oriented_ball_y'],
        oriented_ball_vy=p['oriented_ball_vy'],
        my_distance=p['ball_distance'], opponent_distance=opp['ball_distance'])
    boost = (p['boost_gained'] >= KICKOFF_MIN_PICKUP
             and p['boost_remaining'] >= KICKOFF_MIN_END_BOOST and not danger)
    reasons = []
    if close:
        reasons.append('ball_control')
    if boost:
        reasons.append('safe_boost_pickup')
    return {'success': bool(reasons), 'reasons': reasons,
            'danger': danger, 'ball_distance': p['ball_distance'],
            'boost_gained': p['boost_gained'], 'boost_remaining': p['boost_remaining']}


def kickoff_quality(snapshot: dict | None, early_goal: str | None) -> dict:
    """Goal within 6s takes precedence over possession/boost at 4s.

    early_goal is 'ours', 'nexto' or None. 'Contested' means both players meet
    the requested quality rules, and 'neutral' means neither one does.
    """
    if early_goal not in (None, 'ours', 'nexto'):
        raise ValueError(f'invalid early goal {early_goal!r}')
    if snapshot is None and early_goal is None:
        return {'result': 'neutral', 'model_a_success': False,
                'model_b_success': False, 'reason_a': [], 'reason_b': [],
                'snapshot_available': False}
    a = kickoff_player_status(snapshot, 'a') if snapshot is not None else {'success': False, 'reasons': []}
    b = kickoff_player_status(snapshot, 'b') if snapshot is not None else {'success': False, 'reasons': []}
    if early_goal is not None:
        result = early_goal
        a['success'] = early_goal == 'ours'
        b['success'] = early_goal == 'nexto'
        if early_goal == 'ours':
            a['reasons'] = ['early_goal']
            b['reasons'] = []
        else:
            b['reasons'] = ['early_goal']
            a['reasons'] = []
    elif a['success'] and b['success']:
        result = 'contested'
    elif a['success']:
        result = 'ours'
    elif b['success']:
        result = 'nexto'
    else:
        result = 'neutral'
    return {'result': result, 'model_a_success': a['success'],
            'model_b_success': b['success'], 'reason_a': a['reasons'],
            'reason_b': b['reasons'], 'snapshot_available': snapshot is not None}


def aggregate_kickoff_quality(rows: list[dict], *, ci_seed: int = 602) -> dict:
    """Report kickoff status separately from conventional first-goal score."""
    if not rows:
        raise ValueError('no kickoff episodes')
    outcomes = {key: 0 for key in ('ours', 'nexto', 'contested', 'neutral')}
    reasons = {'a': {}, 'b': {}}
    a_success = b_success = 0
    pair_scores = []
    for row in rows:
        sides = row['sides']
        if len(sides) != 2:
            raise ValueError('expected both paired team sides')
        scores = []
        for side in sides:
            quality = side['kickoff_quality']
            outcomes[quality['result']] += 1
            a_success += int(quality['model_a_success'])
            b_success += int(quality['model_b_success'])
            scores.append(1.0 if quality['result'] == 'ours' else
                          0.0 if quality['result'] == 'nexto' else 0.5)
            for who, key in (('a','reason_a'), ('b','reason_b')):
                for reason in quality[key]:
                    reasons[who][reason] = reasons[who].get(reason, 0) + 1
        pair_scores.append(_mean(scores))
    n = 2 * len(rows)
    return {'pairs': len(rows), 'episodes': n,
            'exclusive_outcomes': outcomes,
            'model_a_quality_success_rate': a_success / n,
            'model_b_quality_success_rate': b_success / n,
            'kickoff_quality_score': _mean(pair_scores),
            'bootstrap_95_percent_interval': list(interval(pair_scores, seed=ci_seed)),
            'reason_counts': reasons,
            'note': ('Ball control and safe boost are independently eligible, so both players may '
                     'succeed on one kickoff. Tied eligibility is marked contested; goals by 6s override.')}
