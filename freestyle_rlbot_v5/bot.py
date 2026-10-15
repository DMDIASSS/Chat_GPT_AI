"""RLBot v5 entry point for the exported Freestyle actor."""
import json
import logging
from pathlib import Path
import numpy as np
import torch
from rlbot.flat import ControllerState
from rlbot.managers import Bot
from live import LiveController

ROOT=Path(__file__).resolve().parent


class Freestyle(Bot):
    def initialize(self):
        self.settings=json.loads((ROOT/'runtime.json').read_text())
        torch.set_num_threads(1)
        self.policy=torch.jit.load(str(ROOT/'policy.pt'),map_location='cpu').eval()
        with torch.inference_mode():
            warm=self.policy(torch.zeros(1,512))
        if warm.shape!=(1,94) or not torch.isfinite(warm).all():
            raise RuntimeError('Exported policy does not match the flat512/stall94 contract')
        self.controller=LiveController(self.infer,self.field_info,self.settings)
        self.logger.info('Freestyle loaded update %s; kickoff script %s; CPU inference',
                         self.settings['update'],self.settings['scripted_kickoff'])

    def infer(self, obs, mask):
        with torch.inference_mode():
            logits=self.policy(torch.from_numpy(obs).unsqueeze(0))[0]
            logits=logits.masked_fill(~torch.from_numpy(mask),-1e10)
            if not torch.isfinite(logits).all():raise RuntimeError('Nonfinite policy logits')
            return int(logits.argmax())

    def get_output(self, packet):
        a=self.controller.act(packet,self.index)
        return ControllerState(throttle=float(a[0]),steer=float(a[1]),pitch=float(a[2]),
            yaw=float(a[3]),roll=float(a[4]),jump=bool(a[5]),boost=bool(a[6]),handbrake=bool(a[7]))


if __name__=='__main__':
    # No training, network API keys, match messages, or quickchat in this runtime.
    Freestyle(json.loads((ROOT/'runtime.json').read_text())['agent_id']).run()
