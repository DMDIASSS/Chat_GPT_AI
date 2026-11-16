"""RocketSimVis transport; startup errors never silently become headless watch."""
import json,os,socket,subprocess,time
from pathlib import Path
from .runtime import ROOT

def find_viewer():
    candidates=[]
    if os.environ.get('DUELFORGE_VIEWER'):candidates.append(Path(os.environ['DUELFORGE_VIEWER']))
    for parent in (ROOT,ROOT.parent,ROOT.parent.parent):
        for project in ('','attention_skills','attention_forge','RocketHive_Replicar_v2'):
            candidates.append(parent/project/'third_party/RocketSimVis')
    for root in candidates:
        exe=root/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        if (root/'src/main.py').is_file() and exe.is_file():return root,exe
    return None

def listener():
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:s.bind(('127.0.0.1',9273));return False
    except OSError:return True
    finally:s.close()

class Viewer:
    def __init__(self):
        self.proc=None;self.socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.socket.setblocking(False)
        if listener():print('ROCKETSIMVIS: reusing the existing UDP listener on port 9273.',flush=True);return
        found=find_viewer()
        if found is None:
            print('Setting up pinned RocketSimVis once in its own GUI environment; existing Torch is untouched.',flush=True)
            from tools.setup_viewer import install
            install();found=find_viewer()
        if found is None:raise RuntimeError('RocketSimVis setup did not produce a runnable viewer')
        root,exe=found;print('OPENING_ROCKETSIMVIS:',root,'; FOV110 distance270 height100.',flush=True)
        self.proc=subprocess.Popen([str(exe),str(ROOT/'tools/viewer_bootstrap.py'),str(root)],cwd=root)
        start=time.monotonic()
        while time.monotonic()-start<30:
            if self.proc.poll() is not None:raise RuntimeError('RocketSimVis exited during startup. Read its error above; the match was not silently hidden.')
            if listener():print('ROCKETSIMVIS_READY: live simulation connection active.',flush=True);return
            time.sleep(.1)
        raise TimeoutError('RocketSimVis did not open its UDP listener within 30 seconds; match not started')
    def send(self,raw,locations):
        if self.proc is not None and self.proc.poll() is not None:raise RuntimeError('RocketSimVis closed; watch stopped and its recording is saved')
        world=raw.get('final_world',raw['world'])[0];pads=raw.get('final_pads',raw['pads'])[0]
        def phys(row):return {'pos':row[:3].tolist(),'vel':row[3:6].tolist(),'ang_vel':row[6:9].tolist(),'forward':row[9:12].tolist(),'up':row[12:15].tolist()}
        cars=[]
        for a,c in enumerate(world[1:]):cars.append({'team_num':a,'phys':phys(c),'boost_amount':float(c[15]/100),'on_ground':bool(c[16]),'is_demoed':bool(c[20]),'has_flipped_or_double_jumped':bool(c[18]),'controls':{name:float(v) if j<5 else bool(v) for j,(name,v) in enumerate(zip(('throttle','steer','pitch','yaw','roll','jump','boost','handbrake'),c[21:29]))}})
        packet={'ball_phys':phys(world[0]),'cars':cars,'boost_pad_states':pads[:,0].astype(bool).tolist(),'boost_pad_locations':locations[:,:3].tolist()}
        try:self.socket.sendto(json.dumps(packet,allow_nan=False).encode(),('127.0.0.1',9273))
        except BlockingIOError:pass
    def close(self):self.socket.close()
