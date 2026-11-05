"""RLBot v5 runtime for the Chronos 225-feature, 90-action export."""
from __future__ import annotations
import numpy as np
import torch
from rlbot.flat import ControllerState,MatchPhase
from rlbot.managers.hivemind import Hivemind
from rlgym_compat import GameState

from .core import check_model
from .chronos import CHRONOS_CONTRACT
from .giga_teachers import TABLE,build_features,native_action_mask


class ChronosClock:
    def reset(self):
        self.previous=np.zeros(8,np.float32);self.held=np.zeros(8,np.float32)
        self.pending=None;self.next_decision=None;self.last_frame=None
    def __init__(self):self.reset()

    def controls(self,state,agent,network,rng):
        frame=int(state.tick_count)
        if self.last_frame is not None and frame<self.last_frame:self.reset()
        self.last_frame=frame
        if self.pending is not None and frame>=self.pending[0]:
            self.held=self.pending[1].copy();self.pending=None
        if self.next_decision is None or frame>=self.next_decision:
            obs,mirror=build_features(state,agent,self.previous,rng,'chronos')
            with torch.inference_mode():logits=network(torch.from_numpy(obs)[None,:])[0].numpy()
            if logits.shape!=(90,) or not np.isfinite(logits).all():raise ValueError('Invalid Chronos live logits')
            mask=native_action_mask(state.cars[agent])
            if not mask.any():raise ValueError('No valid Chronos live action')
            planned=TABLE[int(np.where(mask,logits,-np.inf).argmax())].copy()
            if mirror:planned[[1,3,4]]*=-1
            self.previous=planned.copy();self.pending=(frame+7,planned);self.next_decision=frame+8
        return self.held.copy()


class ChronosBot(Hivemind):
    def __init__(self,policy_path,agent_id):
        super().__init__(agent_id);torch.set_num_threads(1)
        check_model(policy_path,CHRONOS_CONTRACT)
        self.network=torch.jit.load(str(policy_path),map_location='cpu').eval()
        self.clock=ChronosClock();self.rng=np.random.default_rng(631099);self.last_frame=None

    def initialize(self):
        self._create_state()
        self._logger.info('NovaChronos: 1v1, original 225 features / 90 masked actions, 8-tick decisions, 7-tick planned delay')

    def _create_state(self):
        # Keep stable player IDs inside rlgym-compat. Its initialization check
        # uses player_id, so remapping to packet indices recreates cars each tick.
        self.game_state=GameState.create_compat_game_state(self.field_info,self.match_config)

    def get_outputs(self,packet):
        if not packet.balls or len(packet.players)!=2 or len(self.indices)!=1:
            return {i:ControllerState() for i in self.indices}
        frame=packet.match_info.frame_num
        if self.last_frame is not None and frame<self.last_frame:self._create_state();self.clock.reset()
        self.last_frame=frame;self.game_state.update(packet)
        if packet.match_info.match_phase not in (MatchPhase.Active,MatchPhase.Kickoff):
            self.clock.reset();return {i:ControllerState() for i in self.indices}
        index=next(iter(self.indices))
        controls=self.clock.controls(self.game_state,packet.players[index].player_id,self.network,self.rng)
        return {index:ControllerState(*[float(v) for v in controls[:5]],*[bool(v) for v in controls[5:]])}
