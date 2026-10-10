"""Convert human 1v1 replay states into native-GigaLearn supervised examples.
Labels are inverse-dynamics approximations, NOT recorded human buttons.
This script never writes to / overwrites AFK data or models.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, pathlib, random, tempfile
from dataclasses import dataclass
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parent
HEADER='GL_REPLAY_1'


def action_table():
    actions=[]
    for throttle in (-1.,0.,1.):
        for steer in (-1.,0.,1.):
            for boost in (0.,1.):
                for handbrake in (0.,1.):
                    if boost == 1 and throttle != 1:continue
                    actions.append((throttle,steer,0.,steer,0.,0.,boost,handbrake))
    for pitch in (-1.,0.,1.):
        for yaw in (-1.,0.,1.):
            for roll in (-1.,0.,1.):
                for jump in (0.,1.):
                    for boost in (0.,1.):
                        if jump==1 and yaw!=0:continue
                        if pitch==roll==jump==0:continue
                        handbrake=float(jump==1 and (pitch!=0 or yaw!=0 or roll!=0))
                        actions.append((boost,yaw,pitch,yaw,roll,jump,boost,handbrake))
    return np.asarray(actions,dtype=np.float32)

ACTIONS=action_table()

def approx_index(action,on_ground,has_boost):
    """Nearest *valid* native GigaLearn DefaultAction; low-confidence approximation."""
    a=np.asarray(action,dtype=np.float32).reshape(-1)
    if a.shape!=(8,) or not np.isfinite(a).all():return None
    valid=[];ground_end=0
    for i,v in enumerate(ACTIONS):
        # Duplicate strict action-masking would require complete jump state;
        # only use obvious ground-vs-air, boost checks.
        if not has_boost and v[6]>0:continue
        if on_ground and v[5]==0 and (v[2]!=0 or v[4]!=0):continue
        if not on_ground and v[6]==0 and v[5]==0 and v[2]==0 and v[3]==0 and v[4]==0:
            pass
        valid.append(i)
    if not valid:return None
    w=np.array([1.,1.,1.,1.,1.,6.,4.,2.],dtype=np.float32)
    err=((ACTIONS[valid]-a)**2*w).sum(1)
    j=int(np.argmin(err))
    # refuse unreasonably imprecise reconstructed controls
    if err[j]>2.8:return None
    return valid[j],float(err[j])

def _vec(val, expected=3):
    a=np.asarray(val,dtype=np.float32).reshape(-1)
    if a.shape!=(expected,) or not np.isfinite(a).all():raise ValueError('bad 3D vector')
    return [float(x) for x in a]

def _physics(x, car=False):
    p=x.physics if car else x
    result=_vec(p.position)+_vec(p.linear_velocity)+_vec(p.angular_velocity)
    if car:
        m=np.asarray(p.rotation_mtx,dtype=np.float32)
        if m.shape!=(3,3) or not np.isfinite(m).all():raise ValueError('invalid orientation')
        f,r,u=[m[:,i] for i in range(3)]
        if any(abs(float(np.linalg.norm(v))-1)>0.1 for v in [f,r,u]):raise ValueError('unnormalized orientation')
        if abs(float(np.dot(f,r)))>0.12 or abs(float(np.dot(f,u)))>0.12:raise ValueError('invalid rotation basis')
        boost=float(getattr(x,'boost_amount',0.))
        if not np.isfinite(boost):raise ValueError('invalid boost')
        # Boost may be 0..100 in RLGym; never rescale already-0..1 values blindly.
        # RLGym boost_amount is normally already in 0..100 units.
        # Do not guess normalization based on a single low-boost frame.
        on_ground=float(bool(getattr(x,'on_ground',True)))
        result+=_vec(f)+_vec(r)+_vec(u)+[max(0.,min(100.,boost)),on_ground]
    return result

def one_line(replay_id, team, action, state, error):
    cars=sorted(state.cars.values(),key=lambda c:int(c.team_num))
    if len(cars)!=2 or [int(c.team_num) for c in cars] != [0,1]:return None
    ball=_physics(state.ball)
    blue=_physics(cars[0],True);orange=_physics(cars[1],True)
    # Clip egregious out-of-arena and physically invalid samples.
    if abs(ball[0])>4300 or abs(ball[1])>6000 or ball[2]<85 or ball[2]>2100:return None
    for c in (blue,orange):
        if abs(c[0])>4300 or abs(c[1])>6000 or c[2]<15 or c[2]>2150:return None
    values=[float(replay_id),float(team),float(action),float(error)]+ball+blue+orange
    if len(values)!=53:raise AssertionError(f'snapshot width {len(values)} !=53')
    return ' '.join(format(v,'.9g') for v in values)+'\n'

def _group(key):return int.from_bytes(hashlib.sha256(key.encode()).digest()[:4],'little')%5

def convert(inputs,output,*,every=8,max_per_replay=400,max_files=500,age_limit=0.075,seed=817249):
    output=pathlib.Path(output).resolve()
    if output.exists():raise FileExistsError(f'Dataset already exists, refusing overwrite: {output}')
    try:
        from rlgym_tools.rocket_league.replays.parsed_replay import ParsedReplay
        from rlgym_tools.rocket_league.replays.convert import replay_to_rlgym
    except ImportError as ex:raise RuntimeError('Install rlgym-tools in the AFK .venv for replay extraction') from ex
    paths=[]
    for root in inputs:
        root=pathlib.Path(root)
        paths.extend(root.rglob('*.replay') if root.is_dir() else ([root] if root.suffix=='.replay' else []))
    paths=sorted(set(p for p in paths if p.is_file()))[:max_files]
    if not paths:raise RuntimeError('No replay files found. Use --input E:\\Downloads\\Chat_GPT_AI\\data\\replays')
    output.mkdir(parents=True)
    seen_hashes=set()
    files={'train':(output/'replay_train.txt').open('w',encoding='utf8'),
           'val':(output/'replay_val.txt').open('w',encoding='utf8')}
    stats={'kind':'gigalearn_replay_approx_actions_v1','replay_files_considered':len(paths),
           'train':0,'val':0,'sources_train':0,'sources_val':0,'errors':[],
           'warning':'Actions reconstructed with rlgym-tools. Not ground-truth human controller inputs. Validate in RocketSim; no competitive skill claims.'}
    try:
        for p in files.values():p.write(HEADER+'\n')
        for n,path in enumerate(paths):
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in seen_hashes:
                stats.setdefault('duplicate_replay_binaries',0)
                stats['duplicate_replay_binaries']+=1
                continue
            seen_hashes.add(digest)
            group='val' if _group(digest)==0 else 'train'
            count=0
            try:
                replay=ParsedReplay.load(path)
                for frame_no,frame in enumerate(replay_to_rlgym(replay)):
                    if frame_no%every:continue
                    state=frame.state
                    if len(state.cars)!=2:continue
                    for agent,car in state.cars.items():
                        if count>=max_per_replay:break
                        continuous=frame.actions.get(agent)
                        age=frame.update_age.get(agent,999.0)
                        if continuous is None or age>age_limit:continue
                        label=approx_index(continuous,bool(getattr(car,'on_ground',True)),bool(getattr(car,'boost_amount',0)>0))
                        if label is None:continue
                        line=one_line(n,int(car.team_num),label[0],state,label[1])
                        if line is None:continue
                        files[group].write(line)
                        count+=1;stats[group]+=1
                    if count>=max_per_replay:break
                if count:stats['sources_'+group]+=1
            except Exception as exc:
                stats['errors'].append({'replay':path.name,'error':str(exc)[:180]})
    finally:
        for p in files.values():p.close()
    stats['action_table_size']=len(ACTIONS)
    stats['state_format']='GL_REPLAY_1: replay_id team action error, ball pos/vel/ang, two car pos/vel/ang/fwd/right/up/boost/on_ground'
    (output/'manifest.json').write_text(json.dumps(stats,indent=2),encoding='utf8')
    if stats['train']<100 or stats['val']<20:
        raise RuntimeError('Insufficient train/validation examples; see manifest. Dataset retained for debugging.')
    return stats

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',nargs='+',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--every',type=int,default=8)
    p.add_argument('--max-per-replay',type=int,default=400)
    p.add_argument('--max-files',type=int,default=500)
    a=p.parse_args()
    if not 1<=a.every<=1000 or not 1<=a.max_per_replay<=5000 or not 1<=a.max_files<=3000:p.error('Invalid limits')
    print(json.dumps(convert(a.input,a.output,every=a.every,max_per_replay=a.max_per_replay,max_files=a.max_files),indent=2))
if __name__=='__main__':main()
