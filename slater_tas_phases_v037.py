"""Slater v0.3.7: conservative TAS phase discovery. NOT action decoding/training.

Binary v1: uint32(version), uint32(frame_count), frame_count*(uint32 flags + 7
float32), 128-byte opaque trailer. The analog-axis and flag meanings have NOT
been verified. Phase boundaries are only structural change points, not skill
labels; operator MUST verify recordings in the original TAS editor.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np

HDR=struct.Struct('<II')
REC=struct.Struct('<I7f')
TRAILER=128


def read_raw(path:Path):
    raw=path.read_bytes()
    if len(raw)<HDR.size+TRAILER:
        raise ValueError('Truncated TAS')
    version,n=HDR.unpack_from(raw)
    if version!=1 or not (1<=n<=2_000_000):
        raise ValueError('Expected TAS v1 frame header')
    if len(raw)!=HDR.size+n*REC.size+TRAILER:
        raise ValueError('Frame count/size disagreement')
    analogs=np.empty((n,7),dtype=np.float32)
    flags=np.empty(n,dtype=np.uint32)
    for i in range(n):
        vals=REC.unpack_from(raw,8+REC.size*i)
        flags[i]=vals[0]
        analogs[i]=vals[1:]
    if not np.isfinite(analogs).all() or np.max(np.abs(analogs))>1.001:
        raise ValueError('Non-finite or out-of-bounds analog controls')
    return flags,analogs,raw


def split_phases(flags:np.ndarray,analog:np.ndarray,*,min_frames=12,max_frames=180,change_threshold=.75):
    """Detect button-edge and large analog-change boundary, no button semantics."""
    if not 2<=min_frames<=max_frames or max_frames>720 or change_threshold<=0:
        raise ValueError('Invalid segmentation parameters')
    n=len(flags)
    if analog.shape!=(n,7) or n<1:
        raise ValueError('Invalid arrays')
    cuts=[0]
    for i in range(1,n):
        delta=float(np.linalg.norm(analog[i]-analog[i-1]))
        if i-cuts[-1]>=max_frames or (i-cuts[-1]>=min_frames and
                                   (flags[i]!=flags[i-1] or delta>=change_threshold)):
            cuts.append(i)
    if cuts[-1]!=n:cuts.append(n)
    result=[]
    for start,end in zip(cuts,cuts[1:]):
        values=analog[start:end]
        unique,count=np.unique(flags[start:end],return_counts=True)
        dominant=int(unique[np.argmax(count)])
        result.append({'start_frame':start,'end_frame_exclusive':end,'frames':end-start,
                       'dominant_button_mask_u32':dominant,
                       'mean_analog_channels':[round(float(v),5) for v in values.mean(axis=0)],
                       'channel_min':[round(float(v),5) for v in values.min(axis=0)],
                       'channel_max':[round(float(v),5) for v in values.max(axis=0)]})
    return result


def tentative_label(filename:str)->str:
    """Filename-derived category, not a verified semantic segment label."""
    name=filename.lower()
    if 'flip reset' in name:return 'flip_reset_demo'
    if 'wall' in name or 'wll' in name:return 'wall_transition_demo'
    if 'backwards' in name:return 'reverse_flip_demo'
    if '360' in name:return 'rotation_demo'
    if '2 player' in name:return 'multi_actor_named_demo_single_extracted_stream'
    return 'unlabeled_demo'


def analyze_file(path:Path,*,min_frames=12,max_frames=180,threshold=.75):
    flags,values,raw=read_raw(path)
    phases=split_phases(flags,values,min_frames=min_frames,max_frames=max_frames,
                        change_threshold=threshold)
    return {'source_file':path.name,'source_sha256':hashlib.sha256(raw).hexdigest(),
            'label_source':'FILENAME_ONLY_UNVERIFIED','tentative_label':tentative_label(path.name),
            'frames':len(flags),'phases':phases,'phase_count':len(phases),
            'raw_128b_start_state_hex':raw[-TRAILER:].hex(),
            'controller_type':'UNVERIFIED (possibly gamepad: user observation)',
            'controller_mapping_verified':False,'initial_state_decoded':False,
            'ready_for_behavior_cloning':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--min-frames',type=int,default=12)
    p.add_argument('--max-frames',type=int,default=180)
    a=p.parse_args()
    files=sorted(Path(a.input_dir).glob('*.data'))
    if not files: p.error('No TAS .data files found')
    analyses=[analyze_file(f,min_frames=a.min_frames,max_frames=a.max_frames) for f in files]
    result={'version':'v0.3.7','schema':'candidate_tas_phases_unverified','records':analyses,
            'total_frames':sum(x['frames'] for x in analyses),
            'intended_pipeline':[
                'Verify button-bit and 7-channel controller mappings against TAS plugin source',
                'Decode exact initial car and ball state in opaque 128-byte block',
                'Play input sequence in RocketSim from exact state and compare final pose',
                'Segment into physically validated approach/trigger/contact/recovery skills',
                'Train approach controller and continuous-action residual with closed-loop feedback',
                'Use outcome/uncertainty and opponent threat to abort or switch mechanics',
                'Evaluate holdout poses and real RLBot matches; do not blindly autoplay TAS',
            ],
            'not_deployable':True}
    dst=Path(a.out)
    if dst.exists():raise FileExistsError('Will not overwrite: '+str(dst))
    dst.parent.mkdir(parents=True,exist_ok=True)
    with dst.open('x',encoding='utf-8') as out:json.dump(result,out,indent=2)
    print('V037_TAS_PHASES',len(analyses),'FILES',result['total_frames'],'FRAMES',
          sum(x['phase_count'] for x in analyses),'HEURISTIC_SEGMENTS',str(dst))
    print('NOT_TRAINING_READY: Button/axis decoding and exact physics still unverified')

if __name__=='__main__':main()
