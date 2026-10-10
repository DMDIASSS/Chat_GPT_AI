"""Join UNPAIRED TAS controller-cadence patterns with existing replay BC samples.

TAS controls are NOT mapped to RocketSim actions because their field semantics
are unverified. All labels remain replay-derived; TAS ONLY reweights verified
replay (observation, approximate action) pairs by coarse control cadence.
No trajectory reconstruction. No assignment of random TAS inputs to game states.

This is an experimental, conservative replay-context curriculum, not verified
TAS mechanics imitation. It produces GL_REPLAY_1 width-54 rows which require
our isolated C++ BC reader patch. The validation file is bit-for-bit copied.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import hashlib,json,math,os,pathlib,shutil,statistics,struct,tempfile
import numpy as np

HERE=pathlib.Path(__file__).resolve().parent
CROOT=HERE.parent
FRAME=struct.Struct('<I7f')
HEADER=struct.Struct('<II')
TRAILER=128

def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for piece in iter(lambda:f.read(1<<20),b''): h.update(piece)
    return h.hexdigest()

def tas_clips(directory,maximum=2000):
    root=pathlib.Path(directory)
    if not root.is_dir():raise FileNotFoundError('TAS directory missing: '+str(root))
    files=sorted(root.rglob('*.data'), key=lambda p:str(p).casefold())
    if len(files)>maximum:raise ValueError('Too many TAS clips; narrow folder')
    result,problems=[],[]
    hashes=set()
    for p in files:
        try:
            size=p.stat().st_size
            with p.open('rb') as f:
                head=f.read(8)
            if len(head)!=8:raise ValueError('short header')
            v,n=HEADER.unpack(head)
            if v!=1 or not 1<=n<=400000:raise ValueError('unsupported TAS header/version')
            if size!=8+32*n+TRAILER:raise ValueError('record/trailer length mismatch')
            digest=sha(p)
            if digest in hashes:continue
            hashes.add(digest)
            with p.open('rb') as f:
                f.seek(8)
                arr=np.frombuffer(f.read(n*32),dtype=np.dtype([('flags','<u4'),('analog','<f4',(7,))]))
            if len(arr)!=n or (arr['flags']>127).any() or not np.isfinite(arr['analog']).all() or (np.abs(arr['analog'])>1.001).any():
                raise ValueError('invalid input values')
            result.append({'path':str(p),'sha256':digest,'flags':arr['flags'].astype(np.int32),
                           'analog':arr['analog'].astype(np.float32),'frames':n})
        except (OSError,ValueError) as e:problems.append({'file':p.name,'error':str(e)})
    if not result:raise ValueError('No valid TAS files')
    return result,problems

def table():
    a=[]
    for throttle in (-1.,0.,1.):
        for steer in (-1.,0.,1.):
            for boost in (0.,1.):
                for hb in (0.,1.):
                    if boost and throttle!=1:continue
                    a.append((throttle,steer,0.,steer,0.,0.,boost,hb))
    for pitch in (-1.,0.,1.):
        for yaw in (-1.,0.,1.):
            for roll in (-1.,0.,1.):
                for jump in (0.,1.):
                    for boost in (0.,1.):
                        if jump and yaw!=0:continue
                        if pitch==roll==jump==0:continue
                        hb=float(jump==1 and (pitch!=0 or yaw!=0 or roll!=0))
                        a.append((boost,yaw,pitch,yaw,roll,jump,boost,hb))
    if len(a)!=90:raise AssertionError('Expected native GigaLearn 90 actions')
    return np.asarray(a,dtype=np.float32)
ACTIONS=table()

def sig(analog:np.ndarray,flags:np.ndarray):
    """Cadence invariants; no assumption about individual TAS field semantics."""
    if analog.ndim!=2 or len(flags)!=len(analog):raise ValueError('bad cadence shape')
    if len(analog)==0:return []
    prev=np.vstack((analog[:1],analog[:-1]))
    changed=np.abs(analog-prev).mean(axis=1)/2
    activity=np.abs(analog).mean(axis=1)
    pop=(flags>0).sum(axis=1)/max(1,flags.shape[1])
    prevbits=np.vstack((flags[:1],flags[:-1]))
    bitdiff=(flags!=prevbits).sum(axis=1)/max(1,flags.shape[1])
    # Quantized coarse time-local behavior, unrelated clip/replay states remain unpaired.
    return [tuple(int(np.clip(round(float(v)*5),0,5)) for v in vals)
            for vals in zip(changed,activity,pop,bitdiff)]

def tas_cadences(clips,stride=8):
    if not 1<=stride<=64:raise ValueError('TAS stride must be 1..64')
    cadence=Counter()
    for clip in clips:
        a=clip['analog'][::stride]
        f=np.asarray([[(int(v)>>bit)&1 for bit in range(7)] for v in clip['flags'][::stride]],dtype=np.float32)
        cadence.update(sig(a,f))
    return cadence

def read_replay_rows(path):
    with pathlib.Path(path).open('r',encoding='utf-8-sig') as f:
        if f.readline().strip()!='GL_REPLAY_1':raise ValueError('Not a GL_REPLAY_1 replay file: '+str(path))
        for n,line in enumerate(f,2):
            if not line.strip():continue
            values=line.split()
            if len(values)!=53:raise ValueError(f'Replay row {n} does not contain 53 fields; refuse ambiguous data')
            try:rid,team,idx=int(float(values[0])),int(float(values[1])),int(float(values[2]))
            except ValueError:raise ValueError(f'Invalid replay identity at line {n}')
            if not (0<=idx<90 and team in (0,1)):raise ValueError(f'Invalid replay action at {n}')
            yield line.rstrip('\n\r'),rid,team,idx

def build(tas_dir,dataset_dir,out_dir,*,stride=8,cap=1.20):
    original=pathlib.Path(dataset_dir)
    source_train=original/'replay_train.txt';source_val=original/'replay_val.txt'
    if not source_train.is_file() or not source_val.is_file():raise FileNotFoundError('Missing original replay_train.txt and replay_val.txt')
    if not (1<=stride<=64 and 1<=cap<=1.25):raise ValueError('Invalid cadence stride/weight cap')
    out=pathlib.Path(out_dir).resolve()
    if out.exists():raise FileExistsError(f'Refusing overwrite: {out}')
    clips,errors=tas_clips(tas_dir)
    cadence=tas_cadences(clips,stride)
    if not cadence:raise ValueError('Empty TAS cadence index')
    # Group replay samples by replay ID and player side; global ordering in
    # GL_REPLAY_1 is interleaved, so never compute cadence across different cars.
    rows=list(read_replay_rows(source_train))
    if len(rows)<100:raise ValueError('At least 100 replay rows required')
    groups=defaultdict(list)
    for i,(_,rid,team,act) in enumerate(rows):groups[(rid,team)].append((i,act))
    keys=[None]*len(rows)
    for _,seq in groups.items():
        indices=[i for i,_ in seq];acts=ACTIONS[[a for _,a in seq]]
        digital=acts[:,[5,6,7]]
        features=sig(acts[:,[0,1,2,3,4]],digital)
        for row,k in zip(indices,features):keys[row]=k
    replay_count=Counter(keys)
    # Invariant-key overlap; TAS inputs NEVER become action labels.
    # Convert density into conservative 0-20% sample emphasis. High-frequency
    # stationary/no-op pattern matches are capped and not promoted.
    tas_total=sum(cadence.values())
    weights=[];matched=0
    for key in keys:
        freq=cadence.get(key,0)
        if freq<3:
            weights.append(1.0);continue
        matched+=1
        # More common TAS pattern -> higher (bounded) weight, 3 minimum matches
        density=min(1.0,math.log1p(freq)/math.log1p(max(10,tas_total//30)))
        weights.append(1.0+(cap-1)*density)
    if matched<10:raise ValueError('Insufficient TAS-replay cadence overlap. No mislabeled or fabricated samples will be made.')
    out.parent.mkdir(parents=True,exist_ok=True)
    staging=out.with_name(out.name+'.partial')
    if staging.exists():raise FileExistsError('Previous partial run exists: '+str(staging))
    staging.mkdir()
    try:
        with (staging/'replay_train.txt').open('w',encoding='utf8',newline='\n') as f:
            f.write('GL_REPLAY_1\n')
            for row,w in zip(rows,weights):f.write(row[0]+' '+format(w,'.7g')+'\n')
        shutil.copyfile(source_val,staging/'replay_val.txt')
        if sha(source_val)!=sha(staging/'replay_val.txt'):raise IOError('Validation file copy integrity mismatch')
        manifest={'kind':'gigalearn_tas_cadence_replay_link_v1',
            'purpose':'TAS cadence gently reweights REAL replay state/action samples; no TAS states or controller-to-action conversions are fabricated',
            'replay_labels':'rlgym-tools reconstructed, not ground-truth human inputs',
            'tas_inputs':'raw analog+7-bit flags; semantics not validated',
            'replay_train_rows':len(rows),'replay_val_rows':sum(1 for _ in read_replay_rows(source_val)),
            'tas_unique_files':len(clips),'tas_recorded_frames':sum(c['frames'] for c in clips),
            'tas_cadence_windows':tas_total,'tas_replay_cadence_matching_rows':matched,
            'matched_percent':round(100*matched/len(rows),3),
            'mean_weight':round(statistics.mean(weights),5),'max_weight':round(max(weights),5),
            'weight_cap':cap,'tas_stride':stride,'tas_errors':errors,
            'replay_train_sha256':sha(source_train),'replay_val_sha256':sha(source_val),
            'tas_sources':[{'name':pathlib.Path(c['path']).name,'sha256':c['sha256'],'frames':c['frames']} for c in clips],
            'unmodified_validation':True,'cpp_reader':'HubReplayBC TAS_LNK_V1 supports 53 or 54 columns',
            'can_seed_native_nexto':False,'can_claim_tas_mechanics':False,'can_claim_competitive_improvement':False}
        (staging/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
        staging.rename(out)
        return {**manifest,'folder':str(out)}
    except BaseException:
        # Leave partial for inspection: user may need forensic information.
        raise

def cli():
    p=argparse.ArgumentParser(description='Connect TAS control cadence to existing replay BC without fake state/action alignment')
    p.add_argument('--tas',required=True);p.add_argument('--dataset',required=True);p.add_argument('--out',required=True)
    p.add_argument('--tas-stride',type=int,default=8);p.add_argument('--max-multiplier',type=float,default=1.20)
    a=p.parse_args()
    print(json.dumps(build(a.tas,a.dataset,a.out,stride=a.tas_stride,cap=a.max_multiplier),indent=2))
if __name__=='__main__':cli()
