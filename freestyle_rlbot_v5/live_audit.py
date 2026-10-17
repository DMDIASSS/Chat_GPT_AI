"""Bounded local packet capture and deterministic replay of the live adapter."""
from __future__ import annotations
import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import time

import numpy as np

try:
    from .live import LiveController, controls
    from .runtime import ACTIONS
except ImportError:
    from live import LiveController, controls
    from runtime import ACTIONS


class Recorder:
    def __init__(self, folder, field_info, settings, policy_path, *, packets=3600, seconds=45):
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        self.path=folder/('live_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')+'.jsonl.gz')
        self.file=gzip.open(self.path,'wt',encoding='utf-8',compresslevel=1)
        self.limit=packets;self.seconds=seconds;self.start=time.perf_counter();self.count=0
        self.file.write(json.dumps({'schema':1,'type':'header','settings':settings,
            'field_info':base64.b64encode(field_info.pack()).decode('ascii'),
            'policy_sha256':hashlib.sha256(Path(policy_path).read_bytes()).hexdigest()})+'\n')

    def append(self, packet, index, output, callback_ms, error=None):
        if self.file is None:return
        if self.count>=self.limit or time.perf_counter()-self.start>=self.seconds:
            self.close();return
        self.file.write(json.dumps({'type':'packet','index':index,
            'packet':base64.b64encode(packet.pack()).decode('ascii'),
            'output':[float(x)for x in output],'callback_ms':callback_ms,'error':error},separators=(',',':'))+'\n')
        self.count+=1
        if self.count%120==0:self.file.flush()
        if self.count>=self.limit:self.close()

    def close(self):
        if self.file is not None:
            self.file.close();self.file=None


def audit(path, policy_path):
    import torch
    from rlbot import flat
    with gzip.open(path,'rt',encoding='utf-8')as stream:
        header=json.loads(next(stream));rows=[json.loads(line)for line in stream if line.strip()]
    if header.get('schema')!=1:raise ValueError('Unsupported capture schema')
    if hashlib.sha256(Path(policy_path).read_bytes()).hexdigest()!=header['policy_sha256']:
        raise ValueError('The capture belongs to different policy weights')
    torch.set_num_threads(1)
    policy=torch.jit.load(str(policy_path),map_location='cpu').eval()
    actions=Counter();contexts=Counter();callback=[];mismatches=0;errors=[];replay_errors=[];history={}
    echo={lag:[0,0]for lag in range(13)};speeds=[];gaps=[];previous_frame=None;distances=[];behaviour=Counter()
    def infer(obs,mask):
        with torch.inference_mode():logits=policy(torch.from_numpy(obs)[None])[0].numpy()
        if not np.isfinite(logits).all():raise ValueError('Nonfinite live policy logits')
        chosen=int(np.where(mask,logits,-1e10).argmax());actions[chosen]+=1
        distance=float(np.linalg.norm(obs[27:30])*6000);distances.append(distance)
        action=ACTIONS[chosen]
        behaviour['ground_decisions']+=bool(obs[46]);behaviour['jump_decisions']+=bool(action[5])
        behaviour['boost_decisions']+=bool(action[6]);behaviour['zero_control_decisions']+=not action.any()
        behaviour['far_ball_decisions']+=distance>1500
        behaviour['far_ball_jump_decisions']+=distance>1500 and bool(action[5])
        return chosen
    controller=LiveController(infer,flat.FieldInfo.unpack(base64.b64decode(header['field_info'])),header['settings'])
    for row in rows:
        packet=flat.GamePacket.unpack(base64.b64decode(row['packet']));index=row['index']
        frame=int(packet.match_info.frame_num);phase=int(packet.match_info.match_phase)
        callback.append(row['callback_ms'])
        if row.get('error'):errors.append(row['error'])
        if previous_frame is not None and frame<previous_frame:history.clear()
        if previous_frame is not None and frame>previous_frame and phase in (2,3):gaps.append(frame-previous_frame)
        previous_frame=frame
        try:expected=controller.act(packet,index)
        except Exception as exc:
            replay_errors.append({'frame':frame,'error':str(exc)});expected=np.zeros(8)
        if not np.allclose(expected,row['output'],atol=1e-6,rtol=0):mismatches+=1
        if 0<=index<len(packet.players)and phase in (2,3):
            player=packet.players[index];contexts['ground_packets'if int(player.air_state)==0 else'air_packets']+=1
            speeds.append(float(np.linalg.norm([player.physics.velocity.x,player.physics.velocity.y,player.physics.velocity.z])))
            actual=controls(player.last_input)
            for lag,counts in echo.items():
                prior=history.get(frame-lag)
                if prior is not None:
                    counts[1]+=1;counts[0]+=bool(np.allclose(actual,prior,atol=1e-5,rtol=0))
            history[frame]=row['output']
            for old in list(history):
                if old<frame-16:del history[old]
    rates={str(lag):{'fraction':match/total,'samples':total}for lag,(match,total)in echo.items()if total}
    best=max(rates,key=lambda lag:rates[lag]['fraction'])if rates else None
    result={'schema':1,'packets':len(rows),'policy_update':header['settings']['update'],
        'adapter_replay_output_mismatches':mismatches,'recorded_callback_errors':errors[:10],
        'adapter_replay_errors':replay_errors[:10],
        'policy_decisions':sum(actions.values()),'policy_action_counts':dict(actions),
        'top_policy_controls':[{'action_index':i,'decisions':n,
            'controls':dict(zip(('throttle','steer','pitch','yaw','roll','jump','boost','handbrake'),map(float,ACTIONS[i])))}
            for i,n in actions.most_common(8)],'behaviour_counts':dict(behaviour),
        'mean_ball_distance_at_decision':float(np.mean(distances))if distances else None,
        'callback_ms_p50':float(np.median(callback))if callback else None,
        'callback_ms_p95':float(np.percentile(callback,95))if callback else None,
        'physics_frames_between_callbacks_median':float(np.median(gaps))if gaps else None,
        'callbacks_skipping_physics_frames':sum(g>1 for g in gaps),
        'last_input_echo_by_physics_frame_lag':rates,'best_echo_lag_frames':int(best)if best is not None else None,
        **contexts,'mean_speed':float(np.mean(speeds))if speeds else None,
        'scope':'Observed packets and controller echo; replay consistency is not proof of correct learning or live physics parity.',
        'echo_caution':'Repeated controls can inflate echo agreement. Packet loss and game input filtering can reduce it.'}
    output=Path(path).with_name(Path(path).name.removesuffix('.jsonl.gz')+'_report.json')
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(output),**result},indent=2));return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('capture',nargs='?',type=Path)
    parser.add_argument('--policy',type=Path,default=Path(__file__).parent/'policy.pt');args=parser.parse_args()
    captures=sorted((Path(__file__).parent/'diagnostics').glob('live_*.jsonl.gz'))
    path=args.capture or(captures[-1]if captures else None)
    if path is None:raise FileNotFoundError('No live recording. Play this exported bot for 45 seconds first.')
    try:audit(path,args.policy)
    except (EOFError,gzip.BadGzipFile):raise RuntimeError('Capture is still open. End the match, then run AUDIT_LIVE.bat again.')from None


if __name__=='__main__':main()
