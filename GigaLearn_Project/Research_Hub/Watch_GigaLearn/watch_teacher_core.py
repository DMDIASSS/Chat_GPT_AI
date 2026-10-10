"""Inference-only GigaLearn .lt -> RLViser / RocketSimVis bridge.

All model folders are scanned read-only. 1v1 only. The actual simulation
and neural-network actions come from the separate C++ GigaLearnWatch target.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time
from typing import Callable

HERE=Path(__file__).resolve().parent
HUB=HERE.parent
GL=HUB.parent
ROOT=GL.parent
EXE=GL/'build_py311'/'Release'/'GigaLearnWatchTeacher.exe'
LOG=Callable[[str],None]


class WatchError(Exception):
    pass


def latest_checkpoint(experiment:Path)->Path|None:
    folder=experiment/'checkpoints'
    if not folder.is_dir():return None
    candidates=[p for p in folder.iterdir() if p.is_dir() and p.name.isdecimal() and
                (p/'POLICY.lt').is_file() and (p/'SHARED_HEAD.lt').is_file()]
    return max(candidates,key=lambda p:int(p.name)) if candidates else None


def discover(root:Path|None=None)->dict[str,Path]:
    base=(root or HUB)/'experiments'
    found={}
    if not base.is_dir():return found
    for exp in sorted(base.iterdir()):
        if not exp.is_dir() or not (exp/'experiment.json').is_file():continue
        try:
            obj=json.loads((exp/'experiment.json').read_text(encoding='utf-8-sig'))
            settings=obj.get('settings') or {}
            if int(settings['blue'])!=1 or int(settings['orange'])!=1:continue
            cp=latest_checkpoint(exp)
            if cp is not None:found[exp.name]=cp
        except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):continue
    return found


def environment()->dict[str,str]:
    env=os.environ.copy()
    meshes=Path(env.get('GIGALEARN_MESHES') or (ROOT/'.venv/Lib/site-packages/rlgym/rocket_league/sim/collision_meshes'))
    if not meshes.is_dir():raise WatchError('RocketSim collision meshes missing: '+str(meshes))
    env['GIGALEARN_MESHES']=str(meshes)
    py=Path(os.environ.get('GIGALEARN_PYTHON311') or Path(os.environ.get('LOCALAPPDATA','C:/Users/Public/AppData/Local'))/'Programs/Python/Python311')
    if not py.is_dir():py=Path(sys.base_prefix)
    env['PYTHONHOME']=str(py)
    env['PYTHONPATH']=os.pathsep.join((str(GL/'build_py311'),str(ROOT/'.venv/Lib/site-packages')))
    env['PATH']=os.pathsep.join((str(py),str(ROOT/'.venv/Lib/site-packages/torch/lib'),env.get('PATH','')))
    return env


def check_frame(frame:dict)->None:
    if frame.get('type')!='frame':raise ValueError('Not a frame')
    if not isinstance(frame.get('cars'),list) or len(frame['cars'])!=2:raise ValueError('Only 1v1 frames supported')
    if len(frame.get('boost_pad_states',[]))!=34:raise ValueError('Expected 34 boost pad states')
    for item in [frame['ball']]+[p['phys'] for p in frame['cars']]:
        for field in ['pos','vel','ang_vel','forward','right','up']:
            if len(item[field])!=3:raise ValueError('Invalid '+field)


def as_rocketsimvis(frame:dict)->dict:
    """Official RocketSimVis UDP JSON wire schema (port 9273)."""
    check_frame(frame)
    return {'ball_phys':frame['ball'],
            'cars':[{'team_num':int(c['team']), 'phys':c['phys'],
                     'boost_amount':float(c['boost']), 'on_ground':bool(c['on_ground']),
                     'is_demoed':bool(c['demoed']),'has_flip':bool(c['has_flip'])}
                    for c in frame['cars']],
            'boost_pad_states':frame['boost_pad_states']}


class Sender:
    def __init__(self, mode:str,log:LOG):
        self.mode=mode
        self.log=log
        self.tick=0
        self.closed=False
        if mode=='rocketsimvis':
            self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            self.peer=('127.0.0.1',9273)
            log('RocketSimVis: open the viewer separately; sending to UDP 127.0.0.1:9273')
        elif mode=='rlviser':
            venv_site=ROOT/'.venv/Lib/site-packages'
            if venv_site.is_dir() and str(venv_site) not in sys.path:
                sys.path.insert(0,str(venv_site))
            try:
                import RocketSim as rs
                import rlviser_py as vis
                from rlgym.rocket_league.common_values import BOOST_LOCATIONS
            except ImportError as e:
                raise WatchError('RLViser Python dependency missing: '+str(e)+'; test existing WATCH_ORIGINAL_NEXTO.bat') from e
            self.rs=rs
            self.vis=vis
            self.vis.set_boost_pad_locations(BOOST_LOCATIONS)
            self.car_cfg=self._make_car_config()
        else:raise WatchError('Unknown viewer type: '+mode)

    def _make_car_config(self):
        rs=self.rs
        # The installed RLViserRenderer uses CarConfig(car.hitbox_type).
        # An OCTANE hitbox is 0 in the RocketSim/RLGym enum.
        try:return rs.CarConfig(0)
        except (TypeError,ValueError) as e:
            try:
                from rlgym.rocket_league.api import HitboxType
                return rs.CarConfig(HitboxType.OCTANE)
            except (ImportError,AttributeError,TypeError,ValueError):
                raise WatchError('Installed RocketSim CarConfig API differs from RLViserRenderer. '+str(e)) from e

    def _phys(self,raw,ball):
        obj=self.rs.BallState() if ball else self.rs.CarState()
        obj.pos=self.rs.Vec(*raw['pos'])
        obj.vel=self.rs.Vec(*raw['vel'])
        obj.ang_vel=self.rs.Vec(*raw['ang_vel'])
        obj.rot_mat=self.rs.RotMat(*(raw['forward']+raw['right']+raw['up']))
        return obj

    def send(self,frame:dict)->None:
        if self.mode=='rocketsimvis':
            self.sock.sendto(json.dumps(as_rocketsimvis(frame),separators=(',',':')).encode('utf-8'),self.peer)
            return
        check_frame(frame)
        ball=self._phys(frame['ball'],True)
        car_data=[]
        for car in frame['cars']:
            state=self._phys(car['phys'],False)
            state.boost=car['boost']
            state.is_on_ground=bool(car['on_ground'])
            state.is_demoed=bool(car['demoed'])
            team=self.rs.Team.BLUE if int(car['team'])==0 else self.rs.Team.ORANGE
            car_data.append((int(car['id']),team,self.car_cfg,state))
        self.tick+=1
        self.vis.render(self.tick,15.0,self.rs.GameMode.SOCCAR,
                        [bool(v) for v in frame['boost_pad_states']],ball,car_data)

    def close(self):
        if self.closed:return
        self.closed=True
        if self.mode=='rocketsimvis':self.sock.close()
        else:
            try:self.vis.quit()
            except Exception as e:self.log('RLViser close: '+str(e))


def play(model_a:Path, model_b:Path,*,viewer='rlviser',speed=1.0,sample=False,
         decisions=900,episodes=0,seed=12345,gpu=False,
         stop:threading.Event|None=None,log:LOG=print,executable:Path|None=None,
         sender_factory=None):
    stop=stop or threading.Event()
    exe=executable or EXE
    if not exe.is_file():raise WatchError('GigaLearnWatch.exe not built: '+str(exe))
    if str(model_b) not in ('frozen:nexto','frozen:cycle9','frozen:wavedash'):
        raise WatchError('Choose an actual frozen .pt teacher')
    for cp in (model_a,):
        if not (cp/'POLICY.lt').is_file() or not (cp/'SHARED_HEAD.lt').is_file():
            raise WatchError('Checkpoint weights missing: '+str(cp))
    if not .1<=speed<=5:raise WatchError('Speed must be 0.1–5x')
    if not 60<=decisions<=9000 or not 0<=episodes<=10000:raise WatchError('Invalid decisions/episodes')
    args=[str(exe),'--a',str(model_a),'--b',str(model_b),
          '--decisions',str(decisions),'--episodes',str(episodes), '--seed',str(seed),
          '--sample','1' if sample else '0','--gpu','1' if gpu else '0']
    env=environment()
    frozen=HUB/'Frozen_Opponents'
    teacher_paths={
        'GL_FROZEN_NEXTO_PT':ROOT/'vendor/nexto/nexto-model.pt',
        'GL_FROZEN_CYCLE9_PT':ROOT/'data/afk_improved/best_verified.pt',
        'GL_FROZEN_WAVEDASH_PT':ROOT/'data/mechanics/wavedash/last.pt',
    }
    for key,path in teacher_paths.items():
        if not path.is_file():raise WatchError('Frozen checkpoint missing: '+str(path))
        env[key]=str(path)
    for fname in ('frozen_nexto_bridge.py','frozen_nexto_worker_main.py','frozen_nexto_worker_core.py','nexto_obs.py'):
        if not (frozen/fname).is_file():raise WatchError('Frozen bridge worker file missing: '+str(frozen/fname))
    env['GL_FROZEN_BRIDGE_DIR']=str(frozen)
    env['GL_FROZEN_SITE_PACKAGES']=str(ROOT/'.venv/Lib/site-packages')
    py=Path(os.environ.get('LOCALAPPDATA','C:/Users/Public/AppData/Local'))/'Programs/Python/Python311/python.exe'
    if not py.is_file():py=Path(sys.executable)
    env['GL_FROZEN_PYTHON_EXE']=str(py)
    if not Path(env['GL_FROZEN_SITE_PACKAGES']).is_dir():raise WatchError('Project site-packages not found')
    log('Frozen model: '+str(model_b)+' | true frozen inference, not .lt student')
    log('Model A: '+str(model_a));log('Model B: '+str(model_b))
    log('Viewer: '+viewer+' | '+('sampled' if sample else 'greedy')+' actions | speed '+str(speed)+'x')
    if viewer=='rlviser' and not (ROOT/'rlviser.exe').is_file():
        log('WARNING: rlviser.exe was not found in project root; try your existing viewer installation.')
    # RLViser-Py looks for rlviser.exe in Python's current working directory.
    # Launcher starts from ROOT, but direct script launches may not.
    previous_cwd=Path.cwd()
    os.chdir(ROOT)
    sender=None
    process=None
    last_ep=None
    count=0
    errorlines=[]
    try:
        sender=(sender_factory or Sender)(viewer,log)
        process=subprocess.Popen(args, cwd=str(ROOT),env=env,stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',bufsize=1)
        assert process.stdout is not None
        for line in process.stdout:
            if stop.is_set():break
            line=line.strip()
            if not line:continue
            try:frame=json.loads(line)
            except json.JSONDecodeError:
                if len(errorlines)<40:errorlines.append(line)
                if '[WATCH ERROR]' in line or 'TEACHER_EPISODE' in line:log(line)
                continue
            if not isinstance(frame,dict) or frame.get('type')!='frame':continue
            if last_ep!=frame['episode']:
                last_ep=frame['episode'];log('Episode '+str(last_ep)+' started (A blue: '+str(frame['a_blue'])+')')
            before=time.monotonic()
            sender.send(frame)
            count+=1
            if frame.get('goal'):log('Goal! Episode '+str(last_ep))
            if count%150==0:log(f'Frames: {count} | ~{count/15:.1f} sec simulated')
            delay=1/(15*speed)-(time.monotonic()-before)
            if delay>0:stop.wait(delay)
        if not stop.is_set():
            code=process.wait(timeout=15)
            if code!=0:raise WatchError('Watch C++ process exited '+str(code)+': '+'\n'.join(errorlines[-12:]))
            log('Playback finished: '+str(count)+' frames')
        else:log('Playback stopped by user')
    finally:
        if process:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            if process.stdout is not None:process.stdout.close()
        if sender is not None:sender.close()
        os.chdir(previous_cwd)


def main():
    parser=argparse.ArgumentParser(description='Watch two read-only GigaLearn policies in RocketSim')
    parser.add_argument('--a',default='replay_foundation_01')
    parser.add_argument('--b',default='smoke_balanced_01')
    parser.add_argument('--viewer',choices=['rlviser','rocketsimvis'],default='rlviser')
    parser.add_argument('--speed',type=float,default=1)
    parser.add_argument('--sample',action='store_true')
    parser.add_argument('--gpu',action='store_true')
    parser.add_argument('--episodes',type=int,default=0)
    parser.add_argument('--decisions',type=int,default=900)
    parser.add_argument('--list',action='store_true')
    args=parser.parse_args()
    names=discover()
    if args.list:
        for k,v in names.items():print(f'{k:26} {v}')
        return
    if args.a not in names or args.b not in names:parser.error('Model not found; run --list')
    try:play(names[args.a],names[args.b],viewer=args.viewer,speed=args.speed,
             sample=args.sample,gpu=args.gpu,episodes=args.episodes,decisions=args.decisions)
    except KeyboardInterrupt:print('Stopped')
    except WatchError as ex:
        print('ERROR:',ex,file=sys.stderr);raise SystemExit(2)

if __name__=='__main__':main()
