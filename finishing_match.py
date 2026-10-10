"""Shooting curriculum and conservative event rewards, separate from AutoLeague."""
from __future__ import annotations
import random
from native_nexto import Match
from finishing_core import FinishingTracker
from finishing_scenarios import configure_shot, SCENARIOS

class FinishingMatch(Match):
    def reset(self):
        base = self.engine.create_base_state()
        self.team_mutator.apply(base, {})
        self.kickoff.apply(base, {})
        scenario = self.scenarios
        if scenario == 'grounded':
            scenario = random.choices(SCENARIOS, weights=[.40, .25, .20, .15])[0]
        elif scenario == 'kickoff':
            pass  # Retain normal kickoffs to prevent forgetting them altogether.
        elif scenario not in SCENARIOS:
            raise ValueError(f'Invalid finishing scenario: {scenario}')
        if scenario != 'kickoff':
            configure_shot(base, self.our_orange, scenario)
        self.current_scenario = scenario
        self.state = self.engine.set_state(base, {})
        self.previous = {}
        self.ours = next(a for a,c in self.state.cars.items() if bool(c.is_orange) == self.our_orange)
        self.opponent = next(a for a in self.state.cars if a != self.ours)
        self.decisions = 0
        self.contacts = {'ours':0,'nexto':0}
        self.shot_tracker = FinishingTracker(self.our_orange)
        self.shot_tracker.begin(self.state)
        return self.observe()

    def step(self, our_action_id, opponent_id, max_decisions):
        reward, done, winner = super().step(our_action_id, opponent_id, max_decisions)
        scored = bool(getattr(self.state, 'goal_scored', False))
        bonus, events = self.shot_tracker.step(self.state, self.ours, self.opponent,
                                               goal=scored, winner=winner)
        self.last_shot_events = events
        return reward + bonus, done, winner
