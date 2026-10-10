"""Read-only RocketSim kickoff probe for REAL frozen Nexto-family .pt teachers.

Uses existing GigaLearnWatchTeacher.exe, FrozenNextoBridge, and watch_teacher_core.
Does not change training code, policies, or checkpoints. No rebuild needed.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from pathlib import Path
import math
import time

import watch_teacher_core as core

TICKS_PER_SECOND = 15.0
SAMPLE_FRAMES = {0, 1, 3, 5, 10, 15, 30, 45, 60, 90, 120}


def _distance(p, q):
    return math.sqrt(sum((float(a)-float(b))**2 for a,b in zip(p,q)))


def _magnitude(p):
    return math.sqrt(sum(float(a)**2 for a in p))


class KickoffTelemetry:
    """Drop-in sender factory for watch_teacher_core.play; pass-through or headless."""
    def __init__(self, mode: str, log):
        self.log=log
        self.inner=None if mode=='headless' else core.Sender(mode, log)
        self.previous_wall=None
        self.current_episode=None
        self.frames=0
        self.first_move={}
        self.initial_positions={}
        self.max_gap=0.0
        self.max_gap_decision=0
        self.touches=defaultdict(int)

    def _summarize(self):
        if self.current_episode is None:return
        first=self.first_move
        def movement(who):
            d=first.get(who)
            return f'{d/TICKS_PER_SECOND:.2f} simulated sec' if d is not None else 'NO MOTION DETECTED'
        self.log(f'EPISODE {self.current_episode} SUMMARY | first motion (speed >150 OR distance >50):'
                 f' student={movement("student")}, teacher={movement("teacher")}'
                 f' | teacher_touch_frames={self.touches["teacher"]} student_touch_frames={self.touches["student"]}')
        self.log(f'Largest actual wall-clock frame gap = {self.max_gap:.3f}s at decision {self.max_gap_decision}. '
                 'A large gap early on can look like AFK in the viewer without simulated inactivity.')
        if first.get('teacher') is None:
            self.log('WARNING: teacher never started physically moving in this sampled episode.')
        elif first['teacher']>=30:
            self.log('WARNING: teacher initially stood still for >=2 SIMULATED seconds.')
        elif self.max_gap>1.0:
            self.log('NOTE: teacher physically started moving early, but the output stalled in real time: '
                     'suspect first-inference warmup/viewer buffering, not a learned AFK policy.')
        else:
            self.log('NOTE: teacher was not initially AFK in simulated physics by the 150uu/s motion threshold. '
                     'Slow/boostless kickoff play remains possible.')

    def send(self, frame:dict):
        core.check_frame(frame)
        now=time.monotonic()
        ep=frame['episode']
        d=int(frame['decision'])
        if ep!=self.current_episode:
            self._summarize()
            self.current_episode=ep
            self.previous_wall=None
            self.first_move={}
            self.initial_positions={}
            self.touches=defaultdict(int)
            self.max_gap=0.0
            self.max_gap_decision=0
            self.log(f'\n=== Episode {ep}: student is {"BLUE" if frame["a_blue"] else "ORANGE"}, '
                     f'frozen teacher is {"ORANGE" if frame["a_blue"] else "BLUE"} ===')
        if self.previous_wall is not None:
            gap=now-self.previous_wall
            if gap>self.max_gap:
                self.max_gap=gap
                self.max_gap_decision=d
            if gap>1.0:
                self.log(f'WALL-CLOCK GAP: {gap:.2f}s before simulated decision {d} ({d/TICKS_PER_SECOND:.2f}s game time)')
        self.previous_wall=now
        cars={int(c['team']):c for c in frame['cars']}
        roles={'student':cars[0 if frame['a_blue'] else 1],
               'teacher':cars[1 if frame['a_blue'] else 0]}
        for who,car in roles.items():
            phys=car['phys']
            p=phys['pos'];v=phys['vel']
            if who not in self.initial_positions:self.initial_positions[who]=p
            if who not in self.first_move and (d>0 and (_magnitude(v)>150 or _distance(p,self.initial_positions[who])>50)):
                self.first_move[who]=d
            if car.get('ball_touched'):self.touches[who]+=1
        if d in SAMPLE_FRAMES:
            ballpos=frame['ball']['pos']
            teacher=roles['teacher']['phys']
            student=roles['student']['phys']
            self.log(f't={d/TICKS_PER_SECOND:5.2f}s (sim) | '
                     f'teacher_speed={_magnitude(teacher["vel"]):6.0f}uu/s '
                     f'displacement={_distance(teacher["pos"],self.initial_positions["teacher"]):6.0f}uu '
                     f'ball_distance={_distance(teacher["pos"],ballpos):6.0f}uu | '
                     f'student_speed={_magnitude(student["vel"]):6.0f}uu/s')
        if self.inner is not None:self.inner.send(frame)
        self.frames+=1

    def close(self):
        self._summarize()
        if self.inner is not None:self.inner.close()
        self.inner=None


def main():
    parser=argparse.ArgumentParser(description='Diagnose physical AFK vs first-frame latency at RocketSim kickoff.')
    parser.add_argument('--model',default='tri_teacher_challenger_01')
    parser.add_argument('--teacher',choices=('nexto','cycle9','wavedash'),default='nexto')
    parser.add_argument('--viewer',choices=('headless','rlviser','rocketsimvis'),default='headless')
    parser.add_argument('--decisions',type=int,default=120)
    parser.add_argument('--episodes',type=int,default=2)
    args=parser.parse_args()
    models=core.discover()
    if args.model not in models:
        parser.error('Model not found: '+args.model+'; available: '+', '.join(models))
    if not 60<=args.decisions<=9000 or not 1<=args.episodes<=100:
        parser.error('decisions must be >=60; episodes must be 1..100')
    print('READ-ONLY kickoff diagnostic. NO training or model edits.', flush=True)
    print('Teacher: frozen:'+args.teacher+'; student: '+args.model, flush=True)
    print('Sim seconds are different from real wall-clock seconds.',flush=True)
    try:
        core.play(models[args.model],Path('frozen:'+args.teacher),viewer=args.viewer,
                  speed=5.0 if args.viewer=='headless' else 1.0,
                  sample=False,decisions=args.decisions,episodes=args.episodes,
                  gpu=False,sender_factory=KickoffTelemetry,log=lambda s:print(s,flush=True))
    except (core.WatchError, OSError,RuntimeError) as exc:
        print('ERROR:',exc,flush=True)
        raise SystemExit(2)
    print('Finished. Copy the console output when reporting the first-motion results.',flush=True)


if __name__=='__main__':main()
