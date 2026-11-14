"""A live native match, streamed to ZealanL/RocketSimVis; never replay playback."""
import json,os,socket,subprocess
from pathlib import Path
from .runtime import ROOT

def find_viewer():
    if os.environ.get('ATTENTIONFORGE_VIEWER'):
        candidates=[Path(os.environ['ATTENTIONFORGE_VIEWER'])]
    else:candidates=[]
    for parent in (ROOT,ROOT.parent,ROOT.parent.parent):
        candidates.append(parent/'third_party/RocketSimVis')
        candidates.append(parent/'RocketHive_Replicar_v2/third_party/RocketSimVis')
    for p in candidates:
        script=p/'src/main.py';exe=p/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        if script.is_file() and exe.is_file():return p,exe
    raise FileNotFoundError('RocketSimVis not found. Run SETUP_VIEWER.bat once. The match was not silently run without a viewer.')

class Viewer:
    def __init__(self):
        root,exe=find_viewer();print('VIEWER:',root,flush=True)
        self.proc=subprocess.Popen([str(exe),str(root/'src/main.py')],cwd=root)
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    def send(self,raw,locations):
        if self.proc.poll() is not None:raise RuntimeError('RocketSimVis closed or failed; read its error in this console.')
        world=raw['world'][0];n=len(world)-1
        def phys(s):return dict(pos=s[:3].tolist(),vel=s[3:6].tolist(),ang_vel=s[6:9].tolist(),forward=s[9:12].tolist(),up=s[12:15].tolist())
        cars=[]
        for a,s in enumerate(world[1:]):
            c=s[21:29];cars.append(dict(team_num=int(a>=n//2),phys=phys(s),boost_amount=float(s[15]),on_ground=bool(s[16]),is_demoed=bool(s[20]),has_flipped_or_double_jumped=bool(s[18]),controls={k:float(v) if j<5 else bool(v) for j,(k,v) in enumerate(zip(('throttle','steer','pitch','yaw','roll','jump','boost','handbrake'),c))}))
        packet=dict(ball_phys=phys(world[0]),cars=cars,boost_pad_states=raw['pads'][0,:,0].astype(bool).tolist(),boost_pad_locations=locations[:,:3].tolist())
        self.sock.sendto(json.dumps(packet,allow_nan=False).encode(),('127.0.0.1',9273))
    def close(self):self.sock.close()
