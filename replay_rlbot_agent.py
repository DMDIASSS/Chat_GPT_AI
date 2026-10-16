"""RLBot v4 entry point for a self-contained offline-imitation policy export."""
from pathlib import Path
import hashlib
import json
import numpy as np
import torch
from rlbot.agents.base_agent import BaseAgent,SimpleControllerState
from replay_rlbot_core import PacketObserver,ReplayController

HERE=Path(__file__).resolve().parent


class ReplayBot(BaseAgent):
    def initialize_agent(self):
        torch.set_num_threads(1)
        metadata=json.loads((HERE/'EXPORT_INFO.json').read_text(encoding='utf8'))
        for name,digest in metadata['runtime_sha256'].items():
            if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=digest:raise ValueError('Export file changed: '+name)
        settings=json.loads((HERE/'runtime.json').read_text(encoding='utf8'));device=settings.get('device','auto')
        if device not in ('auto','cpu','cuda'):raise ValueError('Runtime device must be auto, cpu or cuda')
        if device=='auto':device='cuda' if torch.cuda.is_available() else 'cpu'
        if device=='cuda' and not torch.cuda.is_available():raise ValueError('CUDA requested but unavailable in RLBot Python')
        kernel=torch.jit.load(str(HERE/'policy.pt'),map_location=device).eval()
        book=np.load(HERE/'tokens.npy',allow_pickle=False)
        self.controller=ReplayController(kernel,book,PacketObserver(self.get_field_info()),history=metadata['history'],device=device)
        self.reported_error=False
        print('REPLAY_MODEL_READY:',metadata['name'],'device',device,'| policy inference, 8-tick replanning | no training',flush=True)

    def get_output(self,packet):
        try:
            action=self.controller.output(packet,self.index);self.reported_error=False
        except (ValueError,RuntimeError,IndexError) as error:
            self.controller.reset();action=np.zeros(8,np.float32)
            if not self.reported_error:print('REPLAY_MODEL_PAUSED:',str(error),flush=True)
            self.reported_error=True
        return SimpleControllerState(throttle=float(action[0]),steer=float(action[1]),pitch=float(action[2]),
            yaw=float(action[3]),roll=float(action[4]),jump=bool(action[5]),boost=bool(action[6]),handbrake=bool(action[7]))
