"""Isolated 1..3-car team worlds using the original attention actor contract.

The learner is one car. Every teammate and opponent is controlled by a frozen
policy, with the source-matched kickoff clock. No existing trainer is changed.
"""
from __future__ import annotations

import random
import numpy as np
import torch

from afk_team_research import encode_multi
from mechanics_scenarios import configure, set_ball, set_car
from nexto_teacher import nexto_actions
from slater_nexto_scheduler_v038b import NextoV4Clock
from slater_versatile_env import TASKS
import slater_cycle9_native_ppo_v025 as base

FORMATS = tuple((ours, theirs) for ours in range(1, 4) for theirs in range(1, 4))
TEAM_TASKS = ('match', 'teamplay', 'ground', 'defense', 'recovery', 'low_boost')


def validate_format(our_size, their_size):
    if type(our_size) is not int or type(their_size) is not int:
        raise ValueError('Team sizes must be integers')
    if (our_size, their_size) not in FORMATS:
        raise ValueError('Each team must contain 1..3 cars')
    return f'{our_size}v{their_size}'


def goal_outcome(state, learner_id):
    """Credit the team goal regardless of which car touched the ball last."""
    if not state.goal_scored:
        return 0
    sign = -1 if state.cars[learner_id].is_orange else 1
    return int(sign * np.sign(float(state.ball.position[1])))


class TeamObserver:
    """Exact Nexto features; hidden absent-player rows contain zero features."""
    def __init__(self):
        from vendor.nexto.nexto_obs import NextoObsBuilder
        self.builder = NextoObsBuilder(n_players=6, tick_skip=8)

    def observe(self, state, previous):
        encoded, ids = encode_multi(state)
        raw = self.builder.batched_build_obs(encoded[None])
        result = {}
        for i, aid in enumerate(ids):
            action = np.asarray(previous.get(aid, np.zeros(8)), dtype=np.float64)
            if action.shape != (8,) or not np.isfinite(action).all() or np.any(np.abs(action) > 1.001):
                raise ValueError('Invalid previous controller input')
            self.builder.add_actions(raw, action, i)
            q, kv, original_mask = raw[i]
            q = q[0].astype(np.float32)
            kv = kv[0].astype(np.float32)
            hidden = original_mask[0] > 0
            kv[hidden] = 0  # Relative-position conversion otherwise moves padded zeros.
            mask = np.where(hidden, -10000., 0.).astype(np.float32)
            if q.shape != (1, 32) or kv.shape != (41, 24) or mask.shape != (41,):
                raise ValueError('Original attention observation dimensions changed')
            if not all(np.isfinite(x).all() for x in (q, kv, mask)):
                raise FloatingPointError('Nonfinite attention observation')
            result[aid] = (q, kv, mask)
        return result


class TeamEnv:
    def __init__(self, rivals, *, our_size=1, their_size=1, fixed_side=None,
                 fixed_rival=None, teammate_actor=None, task_name='match',
                 max_seconds=12., scripted_student=False, anchor_weight=.03):
        from rlgym.rocket_league.sim import RocketSimEngine
        from rlgym.rocket_league.state_mutators import KickoffMutator
        self.format = validate_format(our_size, their_size)
        if task_name not in TEAM_TASKS:
            raise ValueError(f'Team task must be one of {TEAM_TASKS}')
        if fixed_side not in (None, 'blue', 'orange'):
            raise ValueError('Learner side must be blue or orange')
        if not rivals or fixed_rival is not None and fixed_rival not in rivals:
            raise ValueError('At least one named frozen rival is required')
        if not np.isfinite(max_seconds) or max_seconds <= 0:
            raise ValueError('Episode duration must be positive')
        self.engine = RocketSimEngine(rlbot_delay=True)
        self.kickoff = KickoffMutator()
        self.observer = TeamObserver()
        self.actions = nexto_actions()
        self.rivals = dict(rivals)
        self.our_size, self.their_size = our_size, their_size
        self.fixed_side, self.fixed_rival = fixed_side, fixed_rival
        self.teammate_actor = teammate_actor
        self.task_name, self.max_seconds = task_name, float(max_seconds)
        self.scripted_student = bool(scripted_student)
        self.anchor_weight = float(anchor_weight)
        self.retention = True
        self.episode_count = self.total_ticks = self.total_script_ticks = 0
        self.last_commands = {}

    @property
    def task(self):
        return TASKS.index(self.task_name)

    def reset(self, seed):
        from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator
        self.episode_count += 1
        self.side = self.fixed_side or ('blue' if self.episode_count % 2 else 'orange')
        self.ours = f'{self.side}-0'
        self.opponent = 'orange-0' if self.side == 'blue' else 'blue-0'
        self.rival_name = self.fixed_rival or tuple(self.rivals)[(int(seed) + self.episode_count - 1) % len(self.rivals)]
        self.rival = self.rivals[self.rival_name]
        state = self.engine.create_base_state()
        blue, orange = (self.our_size, self.their_size) if self.side == 'blue' else (self.their_size, self.our_size)
        FixedTeamSizeMutator(blue_size=blue, orange_size=orange).apply(state, {})
        # The installed mutator uses Python's global RNG. Restore it to avoid
        # perturbing unrelated learner sampling when creating paired matches.
        saved = random.getstate()
        try:
            random.seed(int(seed))
            self.kickoff.apply(state, {})
        finally:
            random.setstate(saved)
        rng = np.random.default_rng(seed)
        sign = 1 if self.side == 'blue' else -1
        if self.task_name in ('ground', 'low_boost', 'teamplay'):
            ball = np.array([rng.uniform(-2200, 2200), sign * rng.uniform(-2600, 2600), 93.])
            set_ball(state.ball, ball, [rng.uniform(-300, 300), sign * rng.uniform(-500, 500), 0])
            for car in state.cars.values():
                pos = [rng.uniform(-3300, 3300), rng.uniform(-4300, 4300), 17.]
                set_car(car, pos, [ball[0], ball[1], 17.], on_ground=True,
                        speed=rng.uniform(0, 900), boost=rng.uniform(0, 20) if self.task_name == 'low_boost' else rng.uniform(20, 90))
        elif self.task_name == 'defense':
            ball = np.array([rng.uniform(-600, 600), -sign * rng.uniform(2200, 3100), 93.])
            set_ball(state.ball, ball, [rng.uniform(-100, 100), -sign * rng.uniform(700, 1100), 0])
            for team_is_ours in (True, False):
                cars = [c for c in state.cars.values() if (bool(c.is_orange) == (self.side == 'orange')) == team_is_ours]
                for j, car in enumerate(cars):
                    x = (j - (len(cars) - 1) / 2) * 1400 + rng.uniform(-120, 120)
                    y = -sign * (4300 if team_is_ours else 1300) + rng.uniform(-120, 120)
                    set_car(car, [x, y, 17.], [ball[0], ball[1], 17.], on_ground=True, boost=rng.uniform(20, 70))
        elif self.task_name == 'recovery':
            configure(state, 'recovery', self.ours, self.opponent, rng)
        self.state = self.engine.set_state(state, {})
        self.our_ids = tuple(aid for aid, car in self.state.cars.items() if bool(car.is_orange) == (self.side == 'orange'))
        self.their_ids = tuple(aid for aid in self.state.cars if aid not in self.our_ids)
        if len(self.our_ids) != self.our_size or len(self.their_ids) != self.their_size:
            raise RuntimeError('RocketSim roster does not match requested team sizes')
        self.frozen_actors = {aid: (self.teammate_actor or self.rival) if aid in self.our_ids else self.rival
                              for aid in self.state.cars if aid != self.ours}
        self.clocks = {aid: NextoV4Clock(hardcoded=True, stochastic=False) for aid in self.frozen_actors}
        self.student_clock = NextoV4Clock(hardcoded=True, stochastic=False) if self.scripted_student else None
        self.previous = {}
        self.tick_count = self.touch_payments = self.learner_touch_ticks = self.team_touch_ticks = 0
        self.frozen_batch_calls = self.frozen_observations = 0
        self.ball_touched = self.recovered = self.saved = False
        self.reward_sum = 0.
        self.potential = self.phi(self.state)
        self.last_commands = {}
        return self.observe()

    def observe(self):
        return self.observer.observe(self.state, self.previous)[self.ours]

    def observation_contract(self):
        rows = {}
        for aid, (q, kv, mask) in self.observer.observe(self.state, self.previous).items():
            same = sum(c.team_num == self.state.cars[aid].team_num for c in self.state.cars.values())
            n = len(self.state.cars)
            valid = mask == 0
            facts = {'self_tokens': int(kv[:6, 0].sum()),
                     'teammates_excluding_self': int(kv[:6, 1].sum()) - 1,
                     'opponents': int(kv[:6, 2].sum()),
                     'player_tokens': int(valid[:6].sum()),
                     'ball_tokens': int(kv[:, 3].sum()), 'boost_tokens': int(kv[:, 4].sum()),
                     'padding_tokens': int((~valid).sum()),
                     'padding_features_zero': bool(np.all(kv[~valid] == 0)),
                     'valid_mask_zero': bool(np.all(mask[valid] == 0)),
                     'hidden_mask_negative': bool(np.all(mask[~valid] == -10000)),
                     'query_previous_controls': q[0, 24:].tolist()}
            facts['passed'] = bool(facts['self_tokens'] == 1 and facts['teammates_excluding_self'] == same - 1
                                   and facts['opponents'] == n - same and facts['player_tokens'] == n
                                   and facts['ball_tokens'] == 1 and facts['boost_tokens'] == 34
                                   and facts['padding_tokens'] == 6 - n and facts['padding_features_zero']
                                   and facts['valid_mask_zero'] and facts['hidden_mask_negative'])
            rows[aid] = facts
        return rows

    def phi(self, state):
        sign = 1 if self.side == 'blue' else -1
        ball = state.ball.position
        distance = min(float(np.linalg.norm(ball - state.cars[self.ours].physics.position)) / 6000, 1.)
        # Small bounded shaping. Team goals dominate; speed has no direct reward.
        return .15 * sign * float(ball[1]) / 5120 - .03 * distance

    def frozen_predictions(self):
        ready = [aid for aid, clock in self.clocks.items() if clock.update_action]
        if not ready:
            return {}
        previous = dict(self.previous)
        for aid in ready:
            previous[aid] = self.clocks[aid].action
        views = self.observer.observe(self.state, previous)
        groups = {}
        for aid in ready:
            actor = self.frozen_actors[aid]
            groups.setdefault(id(actor), (actor, []))[1].append(aid)
        predicted = {}
        for actor, aids in groups.values():
            device = next(actor.parameters(), torch.empty(0)).device
            x = tuple(torch.as_tensor(np.stack([views[aid][i] for aid in aids]), device=device) for i in range(3))
            with torch.inference_mode():
                indices = base.logits_of(actor, x).argmax(-1).cpu().tolist()
            predicted.update(zip(aids, map(int, indices)))
            self.frozen_batch_calls += 1
            self.frozen_observations += len(aids)
        return predicted

    def step(self, action):
        if not isinstance(action, (int, np.integer)) or not 0 <= action < len(self.actions):
            raise ValueError('Learner action must be a valid original Nexto action index')
        learner = self.actions[int(action)]
        reward = 0.
        done = timeout = goal = False
        for _ in range(8):
            state = self.state
            ids = sorted(state.cars)
            positions = np.array([state.cars[aid].physics.position[:2] for aid in ids])
            teams = np.array([state.cars[aid].team_num for aid in ids])
            kickoff = self.task_name == 'match' and not self.ball_touched and self.tick_count < 168 and np.linalg.norm(state.ball.position[:2]) < 1 and state.ball.position[2] < 100
            predictions = self.frozen_predictions()
            commands = {self.ours: learner.copy()}
            if self.student_clock:
                frame = self.student_clock.frame(is_kickoff_pause=kickoff, ball_xy=state.ball.position[:2],
                    positions=positions, teams=teams, index=ids.index(self.ours), infer=lambda previous, beta: (int(action), learner))
                commands[self.ours] = frame.controls
            for aid, clock in self.clocks.items():
                index = predictions.get(aid)
                def infer(previous, beta, index=index):
                    if index is None:
                        raise RuntimeError('Frozen clock requested an unbatched policy prediction')
                    return index, self.actions[index]
                frame = clock.frame(is_kickoff_pause=kickoff, ball_xy=state.ball.position[:2],
                    positions=positions, teams=teams, index=ids.index(aid), infer=infer)
                commands[aid] = frame.controls
                self.total_script_ticks += int(frame.script_applied)
            if set(commands) != set(state.cars):
                raise RuntimeError('Every car must receive policy or scripted controls')
            if not all(c.shape == (8,) and np.isfinite(c).all() and np.all(np.abs(c) <= 1.001) for c in commands.values()):
                raise FloatingPointError('Invalid team controller output')
            self.state = self.engine.step({aid: control[None] for aid, control in commands.items()}, {})
            self.previous = {aid: control.copy() for aid, control in commands.items()}
            self.last_commands = self.previous
            self.tick_count += 1
            self.total_ticks += 1
            self.ball_touched |= any(car.ball_touches > 0 for car in self.state.cars.values())
            goal = bool(self.state.goal_scored)
            potential = 0. if goal else self.phi(self.state)
            reward += (.995 ** (1 / 8)) * potential - self.potential - .02 / 120
            self.potential = potential
            car = self.state.cars[self.ours]
            team_touched = any(self.state.cars[aid].ball_touches > 0 for aid in self.our_ids)
            self.team_touch_ticks += int(team_touched)
            self.learner_touch_ticks += int(car.ball_touches > 0)
            sign = 1 if self.side == 'blue' else -1
            if self.task_name == 'defense' and team_touched and sign * self.state.ball.linear_velocity[1] > 100:
                self.saved = True
            if self.task_name == 'recovery' and not self.recovered and car.on_ground and car.physics.rotation_mtx[2, 2] > .8:
                self.recovered = True
                reward += .25
            if goal:
                reward += 10. * goal_outcome(self.state, self.ours)
            timeout = not goal and self.tick_count >= round(self.max_seconds * 120)
            done = goal or timeout
            if done:
                break
        self.reward_sum += reward
        outcome = goal_outcome(self.state, self.ours)
        info = {'outcome': outcome, 'timeout': bool(timeout),
                'success': bool(self.saved and outcome >= 0 if self.task_name == 'defense' else self.recovered if self.task_name == 'recovery' else outcome > 0),
                'defensive_clear_proxy': bool(self.saved),
                'task_name': self.task_name, 'format': self.format, 'our_size': self.our_size,
                'their_size': self.their_size, 'side': self.side, 'opponent': self.rival_name,
                'steps': self.tick_count / 8, 'physics_ticks': self.tick_count,
                'script_physics_ticks': sum(c.script_physics_ticks for c in self.clocks.values()),
                'student_script_physics_ticks': self.student_clock.script_physics_ticks if self.student_clock else 0,
                'student_scripted_kickoff': self.scripted_student,
                'learner_touch_ticks': self.learner_touch_ticks, 'team_touch_ticks': self.team_touch_ticks,
                'frozen_batch_calls': self.frozen_batch_calls, 'frozen_observations': self.frozen_observations,
                'reward': self.reward_sum}
        if not np.isfinite(reward):
            raise FloatingPointError('Nonfinite team reward')
        return self.observe(), float(reward), bool(done), info

    def close(self):
        self.engine.close()
