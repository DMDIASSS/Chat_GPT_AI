"""Compare stock Nexto *live RLBot trace* to the v038b physics-tick scheduler.

Does not read/mutate checkpoints, bots, or existing reports. Only checks the
scheduling and controls from actual RLBot packets; no RocketSim input-state
parity claims are made.
"""
from __future__ import annotations
import argparse
from collections import Counter
from pathlib import Path
import json
import numpy as np
from slater_nexto_scheduler_v038b import NextoV4Clock


def load(path):
    with path.open(encoding='utf8') as f:
        lines=[json.loads(line) for line in f if line.strip()]
    if not lines or lines[0].get('schema')!='slater_nexto_live_v038c_v1':
        raise ValueError('Not a v038c live trace')
    if any(row.get('kind')!='frame' for row in lines[1:]):
        raise ValueError('Unexpected non-frame JSONL record')
    return lines[0],lines[1:]


def compare(meta, records):
    flags=meta['flags']
    machine=NextoV4Clock(hardcoded=flags['hardcoded'],stochastic=flags['stochastic'],
                        beta=flags['beta'],tick_skip=flags['tick_skip'])
    if not records:
        return {'frames':0,'status':'NO_FRAMES','errors':[]}
    errors=[]; metrics=Counter(); samples=[]
    for i,r in enumerate(records):
        pos=np.asarray([c['pos'] for c in r['cars']],dtype=float)
        teams=np.asarray([c['team'] for c in r['cars']],dtype=int)
        actual_action=np.asarray(r['post_action'],dtype=np.float32)
        actual_controls=np.asarray(r['controls'],dtype=np.float32)
        neural=np.asarray(r['selected_nn_action'],dtype=np.float32) if r['selected_nn_action'] is not None else None
        calls=[]
        def infer(prev,beta):
            calls.append(beta)
            return -1,neural if neural is not None else np.zeros(8,dtype=np.float32)
        f=machine.frame(is_kickoff_pause=bool(r['is_kickoff_pause']),ball_xy=r['ball_xy'],
                  positions=pos,teams=teams,index=int(r['player_index']),
                  infer=infer,ticks_elapsed=int(r['ticks_elapsed']),
                  match_ended=bool(r['is_match_ended']))
        issues=[]
        if f.neural_updated!=bool(r['neural_updated']):issues.append('neural_update_schedule')
        if f.neural_updated and neural is None:issues.append('missing_logged_neural_action')
        if f.neural_updated and r['selected_beta'] is not None and abs(float(r['selected_beta'])-float(f.beta))>1e-6:
            issues.append('neural_beta')
        if f.kickoff_index!=int(r['kickoff_index']):issues.append('kickoff_index')
        if not np.allclose(f.controls,actual_controls,rtol=0,atol=2e-5):issues.append('final_controls')
        if not np.allclose(f.action,actual_action,rtol=0,atol=2e-5):issues.append('post_action')
        if issues:
            metrics.update(issues)
            if len(errors)<30:
                errors.append({'packet_index':r['packet_index'],'seconds_elapsed':r['seconds_elapsed'],
                               'issues':issues,'kickoff_pause':r['is_kickoff_pause'],
                               'actual_kickoff_index':r['kickoff_index'],'predicted_kickoff_index':f.kickoff_index,
                               'actual_controls':actual_controls.tolist(),
                               'predicted_controls':f.controls.tolist(),
                               'ticks_elapsed':r['ticks_elapsed']})
        metrics['frames']+=1
        metrics['neural_updates_live']+=int(r['neural_updated'])
        metrics['neural_updates_predicted']+=int(f.neural_updated)
        metrics['script_applied_predicted']+=int(f.script_applied)
        metrics['kickoff_pause_packets']+=int(r['is_kickoff_pause'])
        if r['selected_nn_action'] is not None:metrics['nn_actions_logged']+=1
        if (i<5 or issues) and len(samples)<30:
            samples.append({'packet_index':i,'actual_kickoff_index':r['kickoff_index'],
                            'predicted_kickoff_index':f.kickoff_index,
                            'actual_nn':r['neural_updated'],'predicted_nn':f.neural_updated,'issues':issues})
    return {'frames':len(records),
            'status':'LIVE_CONTROL_SCHEDULER_PARITY_PASS' if not metrics['final_controls'] and not metrics['kickoff_index'] and not metrics['neural_update_schedule'] and not metrics['post_action'] and not metrics['neural_beta'] and not metrics['missing_logged_neural_action'] else 'LIVE_CONTROL_SCHEDULER_MISMATCH',
            'mismatch_by_field':{k:metrics[k] for k in ('neural_update_schedule','missing_logged_neural_action','neural_beta','kickoff_index','final_controls','post_action')},
            'neural_updates_live':metrics['neural_updates_live'],
            'neural_updates_predicted':metrics['neural_updates_predicted'],
            'script_applied_predicted':metrics['script_applied_predicted'],
            'kickoff_pause_packets':metrics['kickoff_pause_packets'],
            'nn_actions_logged':metrics['nn_actions_logged'],
            'ticks_elapsed_counts':dict(sorted(Counter(int(r['ticks_elapsed']) for r in records).items())),
            'first_30_differences':errors,'sample':samples}


def summarize(folder):
    files=sorted(folder.glob('nexto_live_*.jsonl'))
    if not files:raise FileNotFoundError(f'No nexto_live_*.jsonl captures in {folder}')
    records=[]
    for p in files:
        meta,frames=load(p)
        d=compare(meta,frames)
        records.append({'file':p.name,'flags':meta['flags'],'summary':d})
    return {'version':'v0.3.8c','kind':'stock_nexto_live_rlbot_control_schedule_audit',
            'status':'PASS' if all(x['summary']['status']=='LIVE_CONTROL_SCHEDULER_PARITY_PASS' for x in records) else 'REVIEW',
            'traces':records,
            'limits':['Only one fixed stock Nexto controller reference and packets it actually received.',
                      'Uses *logged* neural actions, does not prove neural inference or RLGym observation parity.',
                      'Comparing RocketSim to live Rocket League physics requires synchronized identical initial states.',
                      'Missing packets cannot be recovered; actual round state and packet timing are authoritative.',
                      'Logging adds overhead. Do not use probe to measure competitive win rates.']}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture-dir',default='data/isolated/slater_v038c_nexto_live01/capture_v038c')
    p.add_argument('--out',default='data/isolated/v038c_nexto_live01.json')
    a=p.parse_args(argv)
    root=Path.cwd().resolve()
    capture=(root/a.capture_dir).resolve()
    isolated=(root/'data'/'isolated').resolve()
    output=(root/a.out).resolve()
    if not capture.is_relative_to(isolated) or output.suffix!='.json' or not output.is_relative_to(isolated):
        raise ValueError('All input traces/output reports must be under data/isolated')
    if output.exists() or output.with_name(output.name+'.partial').exists():
        raise FileExistsError(f'Report already exists, choose different --out: {output}')
    result=summarize(capture)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf8') as f:json.dump(result,f,indent=2,sort_keys=True)
    for t in result['traces']:
        s=t['summary']
        print('V038C_LIVE',t['file'],s['status'],'FRAMES',s['frames'],
              'MISMATCH',s.get('mismatch_by_field',{}),flush=True)
    print('V038C_REPORT',output,flush=True)


if __name__=='__main__':main()
