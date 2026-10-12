"""Slater v0.3.1: extract VERIFIED-LIKE kickoff *starting poses* from .replay files.

Uses real replay parser and gameplay_periods start_frame; DOES NOT label inferred
player controls as exact ground truth, nor claim a replay is a fake kickoff.
One 1v1 kickoff per accepted period, split by entire replay SHA to avoid leakage.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for x in iter(lambda:f.read(1<<20),b''):h.update(x)
    return h.hexdigest()


def split_replay(sha):
    number=int(sha[:8],16)%100
    return 'train' if number<80 else ('validation' if number<90 else 'test')


def kickoff_pose(state):
    """Return minimally sufficient legal starting pose, or reject non-kickoffs."""
    try:
        cars=list(state.cars.values())
        blue=[c for c in cars if not c.is_orange]
        orange=[c for c in cars if c.is_orange]
        if len(blue)!=1 or len(orange)!=1:return None
        ball=np.asarray(state.ball.position,dtype=float)
        bvel=np.asarray(state.ball.linear_velocity,dtype=float)
        if (not np.isfinite(ball).all() or not np.isfinite(bvel).all() or
                np.linalg.norm(ball[:2])>140 or abs(ball[2]-93)>35 or np.linalg.norm(bvel)>250):return None
        out={'ball_position':ball.astype(np.float32)}
        for label,c,sign in (('blue',blue[0],-1),('orange',orange[0],1)):
            physics=c.physics
            pos=np.asarray(physics.position,dtype=float)
            vel=np.asarray(physics.linear_velocity,dtype=float)
            euler=np.asarray(physics.euler_angles,dtype=float)
            # A legal pre-kickoff vehicle should be on its OWN half, near the ground.
            if (pos.shape!=(3,) or euler.shape!=(3,) or not np.isfinite(pos).all()
                or not np.isfinite(vel).all() or not np.isfinite(euler).all()
                or sign*pos[1]<1500 or sign*pos[1]>4600 or abs(pos[0])>3200
                or not 10<=pos[2]<=45 or np.linalg.norm(vel)>350):return None
            # Reject corrupted/late frames in which car isn't facing center.
            # If this replay parser doesn't expose forward, rely on pose bounds.
            facing=getattr(physics,'forward',None)
            if facing is not None:
                fwd=np.asarray(facing,dtype=float).reshape(-1)
                to_ball=ball[:2]-pos[:2]
                if fwd.size>=2 and np.linalg.norm(fwd[:2])>.1 and np.linalg.norm(to_ball)>1:
                    align=float(np.dot(fwd[:2],to_ball)/(np.linalg.norm(fwd[:2])*np.linalg.norm(to_ball)))
                    if align<.35:return None
            out[label+'_position']=pos.astype(np.float32)
            out[label+'_euler']=euler.astype(np.float32)
            out[label+'_boost']=np.float32(np.clip(c.boost_amount,0,100))
        return out
    except (ValueError,KeyError,AttributeError,TypeError):return None


def select_kickoff(frames, start_time, max_lag=.50):
    """Find earliest valid snapshot from just after replay gameplay period begins."""
    for f in frames:
        t=float(f.state.tick_count)/120.
        if t<start_time-0.04:continue
        if t>start_time+max_lag:break
        record=kickoff_pose(f.state)
        if record is not None:
            record['replay_tick']=np.int64(round(float(f.state.tick_count)))
            record['lag_seconds']=np.float32(t-start_time)
            return record
    return None


def extract_one(path, out_dir, dry_run=False):
    from rlgym_tools.rocket_league.replays.parsed_replay import ParsedReplay
    from rlgym_tools.rocket_league.replays.convert import replay_to_rlgym
    parsed=ParsedReplay.load(str(path))
    periods=parsed.analyzer.get('gameplay_periods',[])
    if not periods:return {'source':str(path),'periods':0,'accepted':0,'skipped':{'no_periods':1}}
    # Existing replay workflow uses game_df times and 120-Hz converted ticks.
    times=[]
    for i,period in enumerate(periods):
        try:
            row=parsed.game_df.loc[int(period['start_frame'])]
            if getattr(row,'ndim',1)!=1:row=row.iloc[0]
            t=float(row['time'])
            if np.isfinite(t):times.append((i,t))
        except (KeyError,ValueError,TypeError,IndexError):pass
    if not times:return {'source':str(path),'periods':len(periods),'accepted':0,'skipped':{'bad_period_times':len(periods)}}
    # rlgym-tools conversion is expensive: do it once for all periods per replay.
    frames=sorted(replay_to_rlgym(parsed,interpolation='linear'),key=lambda f:float(f.state.tick_count))
    sha=digest(path)
    split=split_replay(sha)
    saved=[];skipped={}
    def skip(why):skipped[why]=skipped.get(why,0)+1
    if not frames:
        skip('no_converted_frames')
    else:
        # Single-pass, using tick lookup for efficient search rather than rescanning a large replay.
        ticks=np.asarray([float(f.state.tick_count)/120. for f in frames])
        for period_idx, start_time in times:
            begin=int(np.searchsorted(ticks,start_time-0.04,side='left'))
            rec=select_kickoff(frames[begin:],start_time)
            if rec is None:
                skip('not_clean_1v1_kickoff_or_unaligned_frame');continue
            name=f'{sha[:14]}_kickoff{period_idx:03d}.npz'
            dest=out_dir/split/name
            if dest.exists():raise FileExistsError(f'Refusing to overwrite {dest}')
            if not dry_run:
                dest.parent.mkdir(parents=True,exist_ok=True)
                np.savez_compressed(dest,**rec,replay_sha=np.array(sha),
                    split=np.array(split),source_period=np.int64(period_idx),
                    provenance=np.array('snapshot only; NO inferred controller labels'))
            saved.append(str(dest))
    return {'source':str(path),'sha256':sha,'split':split,'periods':len(periods),
            'accepted':len(saved),'saved':saved,'skipped':skipped}


def load_poses(path,split='train'):
    root=Path(path)
    paths=sorted((root/split).glob('*_kickoff*.npz'))
    rows=[]
    for path in paths:
        with np.load(path,allow_pickle=False) as f:
            if str(f['split'])!=split:raise ValueError(f'Wrong split: {path}')
            row={k:np.asarray(f[k]).copy() for k in ('blue_position','orange_position',
                     'blue_euler','orange_euler','ball_position','blue_boost','orange_boost')}
            if any(not np.isfinite(v).all() for v in row.values()):raise ValueError(f'NaN {path}')
            row['file']=str(path)
            rows.append(row)
    return rows


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--replays',required=True,help='folder containing original .replay files (NOT goal clips)')
    ap.add_argument('--out',required=True,help='new scenario root e.g. data/kickoffs_v031')
    ap.add_argument('--limit',type=int,default=0)
    a=ap.parse_args()
    if a.limit<0:ap.error('limit must be >=0')
    source=Path(a.replays).resolve();out=Path(a.out).resolve()
    if not source.is_dir():ap.error(f'No replay folder: {source}')
    if out.exists():ap.error(f'Refusing existing output folder: {out}')
    if out==source or source in out.parents:ap.error('Output cannot be inside replay input folder')
    files=sorted(source.rglob('*.replay'))
    if a.limit:files=files[:a.limit]
    if not files:ap.error('No .replay files found')
    reports=[]
    for path in files:
        try:r=extract_one(path,out)
        except Exception as exc:r={'source':str(path),'accepted':0,'error':f'{type(exc).__name__}: {exc}'}
        reports.append(r)
        print('REPLAY',path.name,'accepted',r['accepted'],'split',r.get('split'),'skipped',r.get('skipped'),'error',r.get('error'),flush=True)
    out.mkdir(parents=True,exist_ok=True)
    with (out/'manifest_v031.json').open('x',encoding='utf8') as f:
        json.dump(reports,f,indent=2)
    counts={k:len(list((out/k).glob('*.npz'))) for k in ('train','validation','test')}
    print('KICKOFF_EXTRACTION',json.dumps(counts,sort_keys=True),'failed_replays',sum('error' in r for r in reports),flush=True)
    print('IMPORTANT: These are kickoff starting poses, not ground-truth speedflip/fake labels.')
    if not counts['train']:print('WARNING: No train kickoffs. Curriculum can use procedural kickoffs; supply additional replays for replay starts.')
if __name__=='__main__':main()
