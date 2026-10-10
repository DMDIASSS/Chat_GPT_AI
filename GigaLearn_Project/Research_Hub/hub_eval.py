"""Read-only, paired first-goal RocketSim evaluation for GigaLearn .lt checkpoints.

No promotions, no training, no touching checkpoint files. Requires compiled GigaLearnEval.exe.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import uuid

from hub_core import HERE, PROJECT, EXPERIMENTS, HubError, read_json, is_alive, check_runtime

EVAL_BINARY = PROJECT / 'build_py311' / 'Release' / 'GigaLearnEval.exe'
REPORT_ROOT = HERE / 'evaluations'


def candidates():
    """List only 1v1 GigaLearn experiment checkpoints (not .pt models)."""
    result=[]
    if not EXPERIMENTS.is_dir():return result
    for folder in sorted(EXPERIMENTS.iterdir()):
        meta_file=folder/'experiment.json'
        if not meta_file.is_file():continue
        try:
            meta=read_json(meta_file)
            cfg=meta['settings']
            if (int(cfg['blue']),int(cfg['orange']))!=(1,1):continue
            checkpoints=[]
            for cp in (folder/'checkpoints').iterdir():
                if cp.is_dir() and cp.name.isdecimal() and all((cp/f).is_file() for f in ('POLICY.lt','SHARED_HEAD.lt')):
                    checkpoints.append(cp)
            if not checkpoints:continue
            cp=max(checkpoints,key=lambda p:int(p.name))
            result.append({'name':folder.name,'checkpoint':str(cp),'steps':int(cp.name),
                           'preset':meta.get('preset',''), 'path':str(folder)})
        except (KeyError,ValueError,OSError,TypeError):continue
    return result


def _selected(names):
    if len(names)<2:raise HubError('Choose two or more distinct 1v1 experiments')
    if len(names)!=len(set(names)):raise HubError('Duplicate experiment names')
    known={r['name']:r for r in candidates()}
    unknown=[n for n in names if n not in known]
    if unknown:raise HubError('Missing usable 1v1 checkpoint for: '+', '.join(unknown))
    out=[known[n] for n in names]
    for x in out:
        if (Path(x['path'])/'running.json').exists():
            try:
                if is_alive(read_json(Path(x['path'])/'running.json').get('pid')):
                    raise HubError('Experiment currently training; stop safely before evaluation: '+x['name'])
            except (OSError,ValueError,KeyError,TypeError):
                raise HubError('Cannot verify process state for '+x['name'])
    return out


def _mesh():
    mesh=check_runtime().get('meshes')
    if not mesh or not Path(mesh).is_dir():raise HubError('GIGALEARN_MESHES missing or invalid')
    return str(mesh)


def ready():
    return {'binary':str(EVAL_BINARY),'binary_exists':EVAL_BINARY.is_file(),
            'source_exists':(PROJECT/'upstream'/'src'/'HubEvaluate.cpp').is_file(),
            'models':candidates(),'meshes':check_runtime().get('meshes')}


def run(names,*,pairs=12,decisions=900,seed=734891,cpu=True):
    if not EVAL_BINARY.is_file():
        raise HubError('GigaLearnEval.exe missing. Run EVAL_1_PATCH_CPP.bat and rebuild C++ first.')
    if not (1<=pairs<=1000 and 60<=decisions<=5000 and 1<=seed<2_000_000_000):
        raise HubError('Invalid pairs, decision cap, or seed')
    models=_selected(list(names))
    mesh=_mesh()
    REPORT_ROOT.mkdir(parents=True,exist_ok=True)
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    folder=REPORT_ROOT/run_id
    folder.mkdir() # exclusive, never overwrite a prior run
    env=dict(os.environ)
    env['GIGALEARN_MESHES']=mesh
    env['GL_HUB_MODE']='balanced'
    env['GL_HUB_BLUE']='1';env['GL_HUB_ORANGE']='1'
    env['GL_HUB_SETUP']='kickoff'
    env['PYTHONHOME']=str(Path(os.environ.get('PYTHONHOME') or __import__('sys').base_prefix))
    env['PYTHONPATH']=os.pathsep.join([str(PROJECT/'build_py311'),str(PROJECT.parent/'.venv/Lib/site-packages')])
    torchlib=PROJECT.parent/'.venv/Lib/site-packages/torch/lib'
    env['PATH']=os.pathsep.join([str(Path(env['PYTHONHOME'])),str(torchlib),env.get('PATH','')])
    results=[]
    try:
        for i,(a,b) in enumerate(itertools.combinations(models,2),start=1):
            out=folder/f'match_{i:02d}.json'; log=folder/f'match_{i:02d}.log'
            cmd=[str(EVAL_BINARY),'--a',a['checkpoint'],'--b',b['checkpoint'],
                 '--pairs',str(pairs),'--decisions',str(decisions),'--seed',str(seed),
                 '--cpu','1' if cpu else '0','--out',str(out)]
            with log.open('wb') as f:
                p=subprocess.run(cmd,cwd=str(folder),env=env,stdin=subprocess.DEVNULL,
                                 stdout=f,stderr=subprocess.STDOUT,check=False)
            if p.returncode!=0 or not out.is_file():
                tail=log.read_text(encoding='utf8',errors='replace')[-2200:]
                raise HubError(f'Evaluation {a["name"]} vs {b["name"]} failed (exit={p.returncode}). Log: {log}\n{tail}')
            data=read_json(out)
            if data.get('kind')!='gigalearn_head_to_head_first_goal_v1':
                raise HubError('Unsupported evaluator report format: '+str(out))
            results.append({'a':a['name'],'b':b['name'],
                 'wins_a':data['wins_a'],'wins_b':data['wins_b'],'draws':data['draws'],
                 'score_a':data['score_a'],'a_shot_events':data['a_shot_events'],
                 'b_shot_events':data['b_shot_events'],'a_save_events':data['a_save_events'],
                 'b_save_events':data['b_save_events'],'report':str(out)})
        scores={m['name']:{'games':0,'wins':0,'losses':0,'draws':0,'score_points':0.0} for m in models}
        for r in results:
            for key,wo,lo in [(r['a'],r['wins_a'],r['wins_b']),(r['b'],r['wins_b'],r['wins_a'])]:
                s=scores[key];s['wins']+=wo;s['losses']+=lo;s['draws']+=r['draws']
                s['games']+=wo+lo+r['draws'];s['score_points']+=wo+r['draws']*0.5
        for s in scores.values():s['score']=s['score_points']/s['games'] if s['games'] else 0.0
        summary={'kind':'gigalearn_first_goal_round_robin_v1','status':'complete',
                 'note':'Paired seeded kickoff first-goal matches; NOT full five-minute games or Nexto benchmark. No model promotion.',
                 'seed':seed,'pairs_per_matchup':pairs,'decisions_cap':decisions,'cpu_inference':cpu,
                 'models':models,'pairings':results,'standings':scores}
        (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
        (REPORT_ROOT/'last_report_path.txt').write_text(str(folder/'summary.json'),encoding='utf8')
        return folder/'summary.json'
    except Exception as exc:
        (folder/'FAILED.txt').write_text(str(exc),encoding='utf8')
        raise


def show_summary(path=None):
    if path is None:
        last=REPORT_ROOT/'last_report_path.txt'
        if not last.is_file():return 'No completed evaluation yet.'
        path=Path(last.read_text(encoding='utf8').strip())
    if not Path(path).is_file():return 'Evaluation report not found: '+str(path)
    d=read_json(path)
    lines=[f"GigaLearn 1v1 first-goal tournament: {d['pairs_per_matchup']} paired kickoffs per matchup",
           'Match win rates are not full-game win rates.', '']
    for name,s in sorted(d['standings'].items(),key=lambda p:-p[1]['score']):
        lines.append(f'{name}: {s["wins"]}W {s["losses"]}L {s["draws"]}D | score {s["score"]:.1%}')
    lines.extend(['','Individual comparisons:'])
    for r in d['pairings']:
        lines.append(f'{r["a"]} vs {r["b"]}: {r["wins_a"]}-{r["wins_b"]}-{r["draws"]} | '
                     f'shot events {r["a_shot_events"]}:{r["b_shot_events"]} | '
                     f'save events {r["a_save_events"]}:{r["b_save_events"]}')
    lines.append('\nReport: '+str(path))
    return '\n'.join(lines)


def main():
    p=argparse.ArgumentParser(description='Read-only GigaLearn head-to-head evaluator')
    p.add_argument('--check',action='store_true')
    p.add_argument('--models',nargs='*')
    p.add_argument('--pairs',type=int,default=12)
    p.add_argument('--decisions',type=int,default=900)
    p.add_argument('--seed',type=int,default=734891)
    p.add_argument('--gpu',action='store_true')
    p.add_argument('--last',action='store_true')
    args=p.parse_args()
    if args.check:
        print(json.dumps(ready(),indent=2));return
    if args.last:
        print(show_summary());return
    names=args.models or ['smoke_balanced_01','shootingv1','defense1v1']
    file=run(names,pairs=args.pairs,decisions=args.decisions,seed=args.seed,cpu=not args.gpu)
    print(show_summary(file))
if __name__=='__main__':main()
