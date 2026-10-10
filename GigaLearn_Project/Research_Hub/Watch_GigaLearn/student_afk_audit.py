"""Headless, read-only .lt student movement comparison across checkpoints.

Relies on the installed watch_teacher_core.play and GigaLearnWatchTeacher.exe,
which drive the real RocketSim simulation and the actual frozen .pt policy.
Model files never modified. Only a new report file in Watch_GigaLearn/reports.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import sys

HERE=Path(__file__).resolve().parent
HUB=HERE.parent
sys.path.insert(0,str(HERE))
import watch_teacher_core as core

THRESHOLD=150.0
DISPLACEMENT=50.0
TPS=15.0

def magnitude(v):return math.sqrt(sum(float(x)*float(x) for x in v))
def distance(a,b):return math.sqrt(sum((float(x)-float(y))**2 for x,y in zip(a,b)))

class AuditCapture:
    def __init__(self, mode, log):
        if mode!='headless':raise RuntimeError('The student audit is intentionally headless')
        self.by_episode={}
        self.active=None
        self.ep=None
    def send(self,frame):
        core.check_frame(frame)
        episode=int(frame['episode'])
        if episode!=self.ep:
            self.ep=episode
            self.active={
                'episode':episode,'a_blue':bool(frame['a_blue']),
                'roles':{who:{'initial_position':None,'first_movement_decision':None,
                              'speeds':[],'touch_frames':0,'max_displacement':0.0,
                              'distance_to_ball_end':None}
                          for who in ('student','teacher')}
            }
            self.by_episode[episode]=self.active
        d=int(frame['decision']); a_blue=bool(frame['a_blue'])
        cars={int(c['team']):c for c in frame['cars']}
        for who,team in [('student',0 if a_blue else 1),('teacher',1 if a_blue else 0)]:
            car=cars[team];p=car['phys']['pos'];v=car['phys']['vel'];role=self.active['roles'][who]
            if role['initial_position'] is None:role['initial_position']=list(p)
            speed=magnitude(v);displacement=distance(p,role['initial_position'])
            role['max_displacement']=max(role['max_displacement'],displacement)
            role['distance_to_ball_end']=round(distance(p,frame['ball']['pos']),1)
            if d and role['first_movement_decision'] is None and (speed>THRESHOLD or displacement>DISPLACEMENT):
                role['first_movement_decision']=d
            if d:role['speeds'].append(speed)
            if car.get('ball_touched'):role['touch_frames']+=1
    def close(self): pass


def summarize_capture(capture):
    result=[]
    for episode,obj in sorted(capture.by_episode.items()):
        roles={}
        for who,p in obj['roles'].items():
            speed=p['speeds']
            roles[who]={
                'first_motion_s':None if p['first_movement_decision'] is None else round(p['first_movement_decision']/TPS,2),
                'max_speed':round(max(speed) if speed else 0.0,1),
                'mean_speed':round(statistics.mean(speed) if speed else 0.0,1),
                'stationary_fraction':round(sum(s<THRESHOLD for s in speed)/len(speed),3) if speed else None,
                'max_displacement':round(p['max_displacement'],1),
                'ball_touch_frames':p['touch_frames'],
                'ball_distance_end':p['distance_to_ball_end'],
            }
        result.append({'episode':episode,'student_team':'BLUE' if obj['a_blue'] else 'ORANGE',
                       'frames':len(obj['roles']['student']['speeds']), 'roles':roles})
    return result


def select_checkpoints(experiment,kind='representative'):
    cfolder=experiment/'checkpoints'
    candidates=sorted((x for x in cfolder.iterdir() if x.is_dir() and x.name.isdecimal()
       and (x/'POLICY.lt').is_file() and (x/'SHARED_HEAD.lt').is_file()), key=lambda p:int(p.name))
    if not candidates:raise ValueError('No valid checkpoints in '+str(cfolder))
    if kind=='all':return candidates
    # Beginning, middle and end preserve behavior history without a 100-launch audit.
    indexes=sorted(set([0,len(candidates)//2,len(candidates)-1]))
    return [candidates[i] for i in indexes]


def format_row(model,mode,episodes):
    ss=[ep['roles']['student'] for ep in episodes]
    ts=[ep['roles']['teacher'] for ep in episodes]
    if not ss:return model+' '+mode+': ERROR no episodes'
    stopped=sum(x['first_motion_s'] is None for x in ss)
    first=[x['first_motion_s'] for x in ss if x['first_motion_s'] is not None]
    return (f'{model:<33s} {mode:<8s} '
            f'{stopped}/{len(ss)} AFK  student max speed={max(x["max_speed"] for x in ss):6.0f} '
            f'touches={sum(x["ball_touch_frames"] for x in ss):2d} '
            f'first move={min(first) if first else "NEVER"}s | '
            f'teacher max speed={max(x["max_speed"] for x in ts):5.0f} '
            f'touches={sum(x["ball_touch_frames"] for x in ts):2d}')


def interpretation(result):
    rows=[r for r in result if 'episodes' in r]
    greedy=[r for r in rows if r['mode']=='greedy']
    sampled=[r for r in rows if r['mode']=='sampled']
    def all_idle(row):
        eps=row['episodes']
        return bool(eps) and all(e['roles']['student']['first_motion_s'] is None for e in eps)
    note=[]
    if any(not e['roles']['teacher']['first_motion_s'] is None for r in rows for e in r['episodes']):
        note.append('CONTROL: frozen teacher physically moves in RocketSim. An entirely broken opponent is unlikely.')
    final=[r for r in greedy if r.get('is_latest_challenger')]
    if final and all_idle(final[-1]):
        note.append('FINAL GREEDY POLICY: final student stays idle in both observed kickoffs.')
    pairs={(r['model'],r['checkpoint']):r for r in sampled}
    if any(all_idle(g) and k in pairs and not all_idle(pairs[k]) for g in greedy for k in [(g['model'],g['checkpoint'])]):
        note.append('GREEDY vs SAMPLED: student moves when sampling but not with greedy actions. This suggests a neutral-action argmax/policy-selection issue (not an action-application failure).')
    chall=[r for r in greedy if r['model']=='tri_teacher_challenger_01']
    if len(chall)>1 and not all_idle(chall[0]) and all_idle(chall[-1]):
        note.append('TRAINING REGRESSION: initial challenger could move greedily but the final checkpoint cannot. Investigate PPO collapse/reward dynamics.')
    if chall and all(all_idle(r) for r in chall):
        note.append('PREEXISTING FAILURE: sampled challenger checkpoints all show idle greedy behavior. Investigate initial replay foundation and observation/inference setup before blaming only frozen-teacher PPO.')
    if rows and all(all_idle(r) for r in rows):
        note.append('ALL POLICIES IDLE: even stochastic sampled actions produced no motion. Inspect inferred action IDs and control values in the native viewer; physics alone cannot explain the cause.')
    if not note:note.append('Not enough evidence for a definitive cause: compare per-checkpoint rows and send the full report.')
    return note


def run(args,play_fn=core.play):
    models=core.discover()
    if args.model not in models:raise RuntimeError('Unknown experiment '+args.model+' (found: '+', '.join(models)+')')
    experiment=HUB/'experiments'/args.model
    checkpoints=select_checkpoints(experiment,args.checkpoints)
    probes=[]
    for cp in checkpoints:probes.append((args.model,cp,cp==checkpoints[-1]))
    if args.include_replay and 'replay_foundation_01' in models:
        probes.insert(0,('replay_foundation_01',models['replay_foundation_01'],False))
    results=[]
    failures=0
    for model,cp,islatest in probes:
        for mode in ('greedy','sampled'):
            tag=f'{model} / {cp.name} {mode}'
            print('RUNNING',tag,flush=True)
            capture_list=[]
            def capture_factory(kind,log):
                c=AuditCapture(kind,log)
                capture_list.append(c)
                return c
            try:
                play_fn(cp,Path('frozen:'+args.teacher),viewer='headless',speed=5.0,
                        sample=mode=='sampled',decisions=args.decisions,episodes=args.episodes,
                        gpu=False,sender_factory=capture_factory,log=lambda s:None)
                if not capture_list:raise RuntimeError('No headless capture was opened')
                episodes=summarize_capture(capture_list[0])
                if len(episodes)!=args.episodes:raise RuntimeError('Expected '+str(args.episodes)+' episodes, got '+str(len(episodes)))
                row={'model':model,'checkpoint':str(cp),'mode':mode,
                     'is_latest_challenger':islatest and model==args.model, 'episodes':episodes}
                print(format_row(model+' / '+cp.name,mode,episodes),flush=True)
            except Exception as ex:
                failures+=1
                row={'model':model,'checkpoint':str(cp),'mode':mode,'error':repr(ex)}
                print('ERROR',tag,repr(ex),flush=True)
            results.append(row)
    notes=interpretation(results)
    print('\nDIAGNOSIS:',flush=True)
    for note in notes:print('-',note,flush=True)
    now=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    reportdir=HERE/'reports';reportdir.mkdir(exist_ok=True)
    report=reportdir/('student_afk_audit_'+now+'.json')
    report.write_text(json.dumps({'teacher':args.teacher,'model':args.model,
        'total_probes':len(results),'failures':failures,'notes':notes,'results':results},
        indent=2),encoding='utf-8')
    print('\nREPORT:',report,flush=True)
    print('READ-ONLY. Models and training configuration untouched.',flush=True)
    return 1 if failures else 0


def main():
    p=argparse.ArgumentParser(description='Headless read-only RocketSim audit: student kickoff motion, sampled vs greedy and checkpoints')
    p.add_argument('--model',default='tri_teacher_challenger_01')
    p.add_argument('--teacher',choices=('nexto','cycle9','wavedash'),default='nexto')
    p.add_argument('--episodes',type=int,default=2)
    p.add_argument('--decisions',type=int,default=120)
    p.add_argument('--checkpoints',choices=('representative','all'),default='representative')
    p.add_argument('--include-replay',action='store_true')
    args=p.parse_args()
    if not 1<=args.episodes<=8 or not 60<=args.decisions<=300:
        p.error('episodes must be 1..8; decisions must be 60..300')
    print('READ-ONLY STUDENT AUDIT - no training, no model changes.',flush=True)
    print('Reference: frozen:'+args.teacher+'; target: '+args.model,flush=True)
    try:raise SystemExit(run(args))
    except (ValueError,OSError,RuntimeError,core.WatchError) as e:
        print('AUDIT ERROR:',e,file=sys.stderr,flush=True)
        raise SystemExit(2)

if __name__=='__main__':main()
