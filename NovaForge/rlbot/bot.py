from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import numpy as np
import torch
from rlbot.flat import ControllerState, MatchPhase
from rlbot.managers.hivemind import Hivemind
from rlgym_compat import V1GameState

from nova.core import ACTIONS, DecisionClock, observe_v1
from nova.models import FrozenActor


class NovaForge(Hivemind):
    def __init__(self,policy_path=None,agent_id='DMDIASSS/NovaForge-v1'):
        super().__init__(agent_id)
        torch.set_num_threads(1)
        self.actor=FrozenActor(Path(policy_path) if policy_path is not None else Path(__file__).with_name('policy.pt'))
        self.previous=np.zeros(8,dtype=np.float32)
        self.clock=DecisionClock()
        self.previous_phase=None
        self.last_frame=None
        self.warned_size=False

    def initialize(self):
        self.game_state=V1GameState(self.field_info,self.match_config,tick_skip=4)
        self._logger.info('NovaForge v1 ready: 1v1 only, four-tick policy, 100 observations, 276 actions')

    def get_outputs(self,packet):
        if not packet.balls or len(packet.players)!=2 or len(self.indices)!=1:
            if not self.warned_size:
                self._logger.error('NovaForge v1 needs exactly one car per team and one controlled car')
                self.warned_size=True
            return {i:ControllerState() for i in self.indices}
        phase=packet.match_info.match_phase
        frame=packet.match_info.frame_num
        rewind=self.last_frame is not None and frame<self.last_frame
        if rewind:
            self.game_state=V1GameState(self.field_info,self.match_config,tick_skip=4)
        self.last_frame=frame
        kickoff=(phase in (MatchPhase.Countdown,MatchPhase.Kickoff) and
                 self.previous_phase not in (MatchPhase.Countdown,MatchPhase.Kickoff))
        self.previous_phase=phase
        self.game_state.update(packet)
        if kickoff or rewind:
            self.previous[:]=0
            self.clock=DecisionClock()
        if phase not in (MatchPhase.Active,MatchPhase.Kickoff):
            self.previous[:]=0
            self.clock=DecisionClock()
            return {i:ControllerState() for i in self.indices}
        index=next(iter(self.indices))
        if self.clock.due(frame):
            obs=observe_v1(self.game_state,index,self.previous)
            self.previous=ACTIONS[self.actor.action(obs)].copy()
        return {index:ControllerState(*[float(v) for v in self.previous[:5]],
                                     *[bool(v) for v in self.previous[5:]])}


if __name__=='__main__':
    NovaForge().run()
