"""Defensive/boost shaping on a copy of the current FinishingMatch curriculum."""
from __future__ import annotations
import random
from chatgpt_ai.curriculum import ChatGPTCurriculum
from finishing_match import FinishingMatch
from balance_core import BalanceTracker


class BalanceMatch(FinishingMatch):
    def reset(self):
        # 40% regular scenarios, 35% existing shooting curriculum, 25% kickoff.
        # The default grounded preset intentionally provides defensive situations.
        roll = random.random()
        self.scenarios = 'kickoff' if roll < .25 else ('curriculum_defense' if roll < .65 else 'grounded')
        if self.scenarios == 'curriculum_defense':
            # Match initialization with grounded RLGym scenario distribution.
            base=self.engine.create_base_state()
            self.team_mutator.apply(base,{})
            ChatGPTCurriculum('grounded').apply(base,{})
            self.current_scenario='curriculum_defense'
            self.state=self.engine.set_state(base,{})
            self.previous={}
            self.ours=next(a for a,c in self.state.cars.items() if bool(c.is_orange)==self.our_orange)
            self.opponent=next(a for a in self.state.cars if a!=self.ours)
            self.decisions=0
            self.contacts={'ours':0,'nexto':0}
            from finishing_core import FinishingTracker
            self.shot_tracker=FinishingTracker(self.our_orange)
            self.shot_tracker.begin(self.state)
        else:
            super().reset()
        self.balance_tracker=BalanceTracker(self.our_orange)
        return self.observe()

    def step(self,our_action_id,opponent_id,max_decisions):
        # Must keep previous state values; RocketSim can recycle mutable memory.
        from types import SimpleNamespace
        import numpy as np
        def snap_car(car):
            return SimpleNamespace(boost_amount=float(car.boost_amount),physics=SimpleNamespace(
                position=np.asarray(car.physics.position).copy(),
                linear_velocity=np.asarray(car.physics.linear_velocity).copy()))
        pre = SimpleNamespace(ball=SimpleNamespace(
            position=np.asarray(self.state.ball.position).copy(),
            linear_velocity=np.asarray(self.state.ball.linear_velocity).copy()),
            cars={k:snap_car(c) for k,c in self.state.cars.items()})
        r,done,winner=super().step(our_action_id,opponent_id,max_decisions)
        touch=bool(getattr(self.state.cars[self.ours],'ball_touches',0))
        bonus=self.balance_tracker.step(before=pre,after=self.state,ours=self.ours,
                                        opponent=self.opponent,our_touch=touch,
                                        goal=bool(getattr(self.state,'goal_scored',False)))
        return r+bonus,done,winner
