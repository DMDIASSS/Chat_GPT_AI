"""Audit legacy BakkesMod TAS binary data without inventing observed game states."""
import hashlib
import json
import math
from pathlib import Path
import struct
import numpy as np

def decode(path):
    path=Path(path)
    if path.stat().st_size>16*1024*1024:raise ValueError('TAS exceeds 16 MiB limit')
    raw=path.read_bytes()
    if len(raw)<136:raise ValueError('Truncated TAS header/trailer')
    version,frames=struct.unpack_from('<II',raw)
    if version!=1 or not 1<=frames<=450000:raise ValueError('Unsupported version or empty recording')
    if len(raw)!=8+frames*32+128:raise ValueError('Unexpected frame stride/trailer size')
    records=np.frombuffer(raw,dtype=np.dtype([('flags','<u4'),('analog','<f4',(7,))]),offset=8,count=frames)
    analog=records['analog'];flags=records['flags']
    if not np.isfinite(analog).all() or np.abs(analog).max()>1.001 or (flags>127).any():raise ValueError('Invalid controls')
    # ControllerInput axes: throttle, steer, pitch, yaw, roll, DodgeForward,
    # DodgeStrafe. The latter two are retained separately, never mislabeled axes.
    controls=np.empty((frames,8),np.float32);controls[:,:5]=np.clip(analog[:,:5],-1,1)
    controls[:,5]=(flags&2)!=0;controls[:,6]=(flags&12)!=0;controls[:,7]=(flags&1)!=0
    trailer=8+frames*32
    def body(offset):
        pos=np.array(struct.unpack_from('<3f',raw,offset),np.float64)
        angles=np.array(struct.unpack_from('<3i',raw,offset+12),np.float64)*math.pi/32768
        velocity=np.array(struct.unpack_from('<3f',raw,offset+24),np.float64)
        angular=np.array(struct.unpack_from('<3f',raw,offset+36),np.float64)
        if not all(np.isfinite(x).all() for x in (pos,angles,velocity,angular)) or np.abs(pos).max()>100000 or np.abs(velocity).max()>10000 or np.abs(angular).max()>100:raise ValueError('Invalid starting pose')
        pitch,yaw,roll=angles;cp,sp,cy,sy,cr,sr=np.cos(pitch),np.sin(pitch),np.cos(yaw),np.sin(yaw),np.cos(roll),np.sin(roll)
        rotation=np.array([[cp*cy,cy*sp*sr-cr*sy,-cr*cy*sp-sr*sy],
                           [cp*sy,sy*sp*sr+cr*cy,-cr*sy*sp+sr*cy],
                           [sp,-cp*sr,cp*cr]])
        return {'position':pos.tolist(),'rotation_mtx':rotation.tolist(),'velocity':velocity.tolist(),'angular_velocity':angular.tolist()}
    metadata={'file':path.name,'sha256':hashlib.sha256(raw).hexdigest(),'frames':frames,
        'seconds_if_120hz':frames/120,'car':body(trailer+12),'ball':body(trailer+64),
        'extra_flag_frames':int(np.count_nonzero(flags&96)),
        'dodge_axes_nonzero_frames':int(np.count_nonzero(np.any(np.abs(analog[:,5:])>1e-5,axis=1))),
        'state_action_training_ready':False,
        'needs_verification':['producer tick rate','arena collision/map','car preset/hitbox','boost and unlimited-boost setting',
                              'starting jump/flip/wheel state','playback trajectory against actual game']}
    metadata['ball_starts_near_center']=float(np.linalg.norm(metadata['ball']['position'][:2]))<10
    return controls,metadata

def audit(directory,output):
    directory,output=Path(directory),Path(output)
    files=sorted(directory.rglob('*.data'))
    if not files:raise ValueError('No TAS .data files in '+str(directory))
    accepted,rejected=[],[]
    for path in files:
        try:_,meta=decode(path);meta['path']=str(path.resolve());accepted.append(meta)
        except (ValueError,OSError,struct.error) as error:rejected.append({'file':path.name,'reason':str(error)})
    report={'schema':'replay-il-tas-audit-v1','input':str(directory),'files':accepted,'rejected':rejected,
        'scanned':len(files),'decoded':len(accepted),'frames':sum(x['frames'] for x in accepted),
        'ball_center_starts':sum(x['ball_starts_near_center'] for x in accepted),
        'automatically_added_training_examples':0,
        'note':'Input-only TAS requires verified simulation state before state-to-action learning. No fabricated match outcomes or value labels.'}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2),encoding='utf8')
    print('TAS AUDIT:',report['decoded'],'decoded /',report['scanned'],'files;',report['frames'],'frames;',report['ball_center_starts'],'center-ball starts')
    print('REPORT:',output)
    return report
