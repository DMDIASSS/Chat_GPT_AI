"""RLBot v5 entry point for the exported Freestyle actor."""
import json
import logging
import time
from pathlib import Path
import numpy as np
import torch
from rlbot.flat import ControllerState
from rlbot.managers import Bot
from live import LiveController
from live_audit import Recorder

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
        self.recorder=None
        if self.settings.get('diagnostic_capture',True):
            try:
                self.recorder=Recorder(ROOT/'diagnostics',self.field_info,self.settings,ROOT/'policy.pt')
                self.logger.info('Recording up to 45 seconds of local control diagnostics: %s',self.recorder.path)
            except Exception:
                self.logger.exception('Could not start local diagnostics; policy will continue')
        self.logger.info('Freestyle loaded update %s; kickoff script %s; CPU inference',
                         self.settings['update'],self.settings['scripted_kickoff'])

    def infer(self, obs, mask):
        with torch.inference_mode():
            logits=self.policy(torch.from_numpy(obs).unsqueeze(0))[0]
            logits=logits.masked_fill(~torch.from_numpy(mask),-1e10)
            if not torch.isfinite(logits).all():raise RuntimeError('Nonfinite policy logits')
            return int(logits.argmax())

    def get_output(self, packet):
        start=time.perf_counter()
        try:
            a=self.controller.act(packet,self.index)
        except Exception as exc:
            self.record(packet,np.zeros(8),start,error=str(exc));raise
        self.record(packet,a,start)
        return ControllerState(throttle=float(a[0]),steer=float(a[1]),pitch=float(a[2]),
            yaw=float(a[3]),roll=float(a[4]),jump=bool(a[5]),boost=bool(a[6]),handbrake=bool(a[7]))

    def record(self,packet,output,start,error=None):
        if self.recorder is not None:
            try:self.recorder.append(packet,self.index,output,(time.perf_counter()-start)*1000,error)
            except Exception:
                self.logger.exception('Local recording failed; policy will continue')
                self.recorder.close();self.recorder=None

    def retire(self):
        if getattr(self,'recorder',None)is not None:self.recorder.close()


if __name__=='__main__':
    # No training, network API keys, match messages, or quickchat in this runtime.
    Freestyle(json.loads((ROOT/'runtime.json').read_text())['agent_id']).run()
