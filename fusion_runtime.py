"""RLBot v4 runtime for three verified native Nexto-compatible TorchScript weights.

Connects to the existing exporter-generated bot.py and agent.py.  No RLBot
modules are imported here until the existing RLBot host starts its bot.
"""
from __future__ import annotations
import numpy as np
from agent import Agent
from fusion_logic import decide, drive_toward


class FusionController:
    def __init__(self, cycle9_agent):
        self.policies = {
            'cycle9': cycle9_agent,
            'champion': Agent(model_filename='champion-model.pt'),
            'wavedash': Agent(model_filename='wavedash-model.pt'),
        }
        self.last_policy = 'cycle9'
        self.last_switch_time = -1.e9
        self.last_debug_time = -1.e9
        self.previous_role = 'first'

    def act(self, obs, beta, player, teammates, opponents, game_state, packet, bot):
        now = float(packet.game_info.seconds_elapsed)
        ball = game_state.ball.position
        velocity = game_state.ball.linear_velocity
        d = decide(player, teammates, opponents, ball, velocity, bot.team,
                   kickoff=bool(packet.game_info.is_kickoff_pause))
        # Safety supervision of second-man behavior.  No claims of optimal
        # rotation: we intentionally prioritize a stable support position.
        if d.policy == 'support':
            self.previous_role = d.role
            controls = drive_toward(player, d.target, teammates)
            self._debug(now, 'support', d)
            return controls, None

        policy = d.policy
        # Avoid rapid swapping between networks; never delay danger response.
        if (policy != self.last_policy and not d.danger and
            now - self.last_switch_time < .55):
            policy = self.last_policy
        if policy != self.last_policy:
            self.last_switch_time = now
            self.last_policy = policy
        self.previous_role = d.role
        self._debug(now, policy, d)
        return self.policies[policy].act(obs,beta)

    def _debug(self, now, policy, d):
        if now < self.last_debug_time or now - self.last_debug_time >= 8.0:
            print(f'[Fusion] policy={policy} role={d.role} owner={d.owner_id} danger={d.danger}',flush=True)
            self.last_debug_time = now
