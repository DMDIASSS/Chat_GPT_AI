"""Optional low-priority Ballchasing public replay download and analysis.

This never trains the neural network. Human replay controller labels and Nexto
observation mapping require separate validation before imitation fine-tuning.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


def _jwrite(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    t=path.with_name(path.name+'.partial')
    t.write_text(json.dumps(value,indent=2,sort_keys=True),encoding='utf8')
    t.replace(path)


def summarize_replay(path):
    """Parse 1v1 replay via existing rlgym-tools, extracting physics statistics.
    If parser fails, the failure is logged; no fictitious information returned.
    """
    from rlgym_tools.rocket_league.replays.parsed_replay import ParsedReplay
    from rlgym_tools.rocket_league.replays.convert import replay_to_rlgym
    import numpy as np
    replay=ParsedReplay.load(path)
    frames=0;valid=0;max_speed=0.;airborne=0; touches=0
    goal_events=0;prev_goal=False;heights=[];speeds=[]
    for index,frame in enumerate(replay_to_rlgym(replay)):
        frames+=1
        if index % 8:
            continue
        state=frame.state
        if len(state.cars)!=2:continue
        valid+=1
        ball=state.ball
        height=float(ball.position[2]);speed=float(np.linalg.norm(ball.linear_velocity))
        heights.append(height);speeds.append(speed)
        max_speed=max(speed,max_speed)
        airborne+=int(height>300)
        touches+=sum(int(getattr(c,'ball_touches',0)) for c in state.cars.values())
        goal=bool(getattr(state,'goal_scored',False))
        if goal and not prev_goal:goal_events+=1
        prev_goal=goal
    if valid<1:raise ValueError('No valid 1v1 frames')
    return {'file':path.name,'all_frames':frames,'sampled_1v1_frames':valid,
            'avg_ball_height':round(sum(heights)/valid,1),
            'airborne_ball_fraction_gt300':round(airborne/valid,4),
            'max_ball_speed':round(max_speed,1),
            'avg_ball_speed':round(sum(speeds)/valid,1),
            'sampled_ball_contact_events':touches,'sampled_goal_events':goal_events,
            'warning':'Sampled frame stats only; reconstructed inputs may be approximate.'}


class ReplayWorker:
    def __init__(self,root,data,interval_seconds,max_files):
        self.root=Path(root)
        self.data=Path(data)
        self.interval=interval_seconds
        self.limit=max_files
        self.last=0.
        self.thread=None
        self.token_available=bool(os.environ.get('BALLCHASING_TOKEN','').strip())
        if not self.token_available:
            print('[REPLAYS] BALLCHASING_TOKEN not set. Automatic downloads DISABLED; training continues.')
        elif not (self.root/'download_ballchasing.py').exists():
            print('[REPLAYS] Missing download_ballchasing.py; replay downloads disabled.')
            self.token_available=False

    def maybe_start(self,force=False):
        if not self.token_available or self.limit==0:return False
        if self.thread and self.thread.is_alive():return False
        if not force and time.monotonic()-self.last<self.interval:return False
        self.last=time.monotonic()
        self.thread=threading.Thread(target=self._job,daemon=True,name='ballchasing-downloader')
        self.thread.start()
        return True

    def _job(self):
        output=self.data/'replays'
        output.mkdir(parents=True,exist_ok=True)
        cmd=[sys.executable,str(self.root/'download_ballchasing.py'),
             '--playlist','ranked-duels','--rank','gc-plus',
             '--max-files',str(self.limit),'--output',str(output)]
        try:
            process=subprocess.run(cmd,cwd=self.root,stdin=subprocess.DEVNULL,
                capture_output=True,text=True,timeout=240,encoding='utf8',errors='replace')
            log=(process.stdout+'\n'+process.stderr)[-4000:]
            (self.data/'replay_download_latest.log').write_text(log,encoding='utf8')
            print(f'[REPLAYS] downloader status={process.returncode}; log: data/autoleague/replay_download_latest.log',flush=True)
        except (OSError, subprocess.TimeoutExpired) as ex:
            print(f'[REPLAYS] download failed safely: {ex}',flush=True)
            return
        # Downloaded human replays are only analyzed, never used as labels automatically.
        self.analyze_available()

    def analyze_available(self):
        folder=self.data/'replays'
        indexed=self.data/'replay_analysis_index.json'
        manifest=json.loads(indexed.read_text(encoding='utf8')) if indexed.exists() else {}
        files=sorted(folder.rglob('*.replay'),key=lambda p:p.stat().st_mtime,reverse=True)
        for file in files[:max(5,self.limit*4)]:
            rel=str(file.relative_to(folder))
            fingerprint=f'{file.stat().st_size}:{file.stat().st_mtime_ns}'
            if manifest.get(rel,{}).get('fingerprint')==fingerprint:continue
            try:
                info=summarize_replay(file)
                manifest[rel]={'fingerprint':fingerprint,'summary':info}
                print(f'[REPLAYS] analyzed {rel} ball-height {info["avg_ball_height"]:.0f}',flush=True)
            except (Exception) as ex:
                manifest[rel]={'fingerprint':fingerprint,'error':type(ex).__name__+': '+str(ex)[:250]}
                print(f'[REPLAYS] Could not parse {rel}: {type(ex).__name__}: {ex}',flush=True)
            _jwrite(indexed,manifest)
        _jwrite(self.data/'replay_analysis_summary.json',
            {'updated_utc':datetime.now(timezone.utc).isoformat(),
             'analyzed':sum('summary' in v for v in manifest.values()),
             'failed':sum('error' in v for v in manifest.values()),
             'notes':'Replay analysis ONLY. Not yet used for Nexto imitation training.'})
