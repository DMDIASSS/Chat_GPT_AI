"""Stream ONE evaluation arena to RLViser (native protocol, normally UDP 45243).

RLViser must be running, and rlviser-py installed. Never broadcast all workers.
"""
from __future__ import annotations
import time

class VisualizerTap:
    def __init__(self,render_hz=15.0):
        from rlgym.rocket_league.rlviser import RLViserRenderer
        self.renderer=RLViserRenderer(tick_rate=render_hz)
        self.interval=1.0/render_hz
        self.next_at=0.

    def maybe_render(self,state):
        t=time.monotonic()
        if t>=self.next_at:
            self.renderer.render(state,{})
            self.next_at=t+self.interval

    def close(self):self.renderer.close()
