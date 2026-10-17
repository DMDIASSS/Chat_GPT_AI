"""Evaluate every requested c0001..c0006 actor against Nexto; no training."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
CONFIG=ROOT/'COMPARE_C0001_C0006_NEXTO.json'
RUN='u271_c0001_c0006_nexto_all01'

def expected_paths():
    return [f'data/isolated/native_attention/runs/u271_targets01_c{cycle:04d}/checkpoints/checkpoint_{step:06d}/actor.pt'
            for cycle in range(1,7) for step in range((80 if cycle<=2 else 100)+1)]

def audit(root=ROOT):
    paths=expected_paths()
    missing=[p for p in paths if not (root/p).is_file()]
    return {'expected':len(paths),'present':len(paths)-len(missing),'missing':missing,
            'nexto_present':(root/'vendor/nexto/nexto-model.pt').is_file()}

def export_csv(folder):
    """Keep every original alias and raw results, including per-format outcomes."""
    inventory=json.loads((folder/'inventory.json').read_text(encoding='utf8'))
    plan=json.loads((folder/'stages/screen/plan.json').read_text(encoding='utf8'))
    from slater_model_selection import cached_records
    records,_=cached_records(folder,plan['jobs'])
    fields=['checkpoint','weights_id','format','completed_games','expected_games','wins','draws','losses',
            'goals_for','goals_against','goal_difference_per_minute','complete']
    path=folder/'EVERY_CHECKPOINT_VS_NEXTO.csv'
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for weights_id,model in inventory['models'].items():
            sources=[s['path'] for s in model['source_paths'] if s['families']]
            for mode in ((1,1),(2,2),(3,3)):
                jobs=[j for j in plan['jobs'] if j['candidate_id']==weights_id and tuple(j['format'])==mode]
                if not jobs:continue
                rows=[r for r in records if r['candidate_id']==weights_id and tuple(r['format'])==mode]
                gf=sum(r['goals_for'] for r in rows);ga=sum(r['goals_against'] for r in rows)
                seconds=sum(r['seconds'] for r in rows)
                for source in sources:
                    writer.writerow(dict(checkpoint=source,weights_id=weights_id,format=f'{mode[0]}v{mode[1]}',
                        completed_games=len(rows),expected_games=len(jobs),wins=sum(r['goals_for']>r['goals_against'] for r in rows),
                        draws=sum(r['goals_for']==r['goals_against'] for r in rows),losses=sum(r['goals_for']<r['goals_against'] for r in rows),
                        goals_for=gf,goals_against=ga,goal_difference_per_minute=(gf-ga)*60/seconds if seconds else '',complete=len(rows)==len(jobs)))
    print('RESULTS:',path,flush=True)
    return path

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['run','audit','results','pause'],nargs='?',default='run')
    p.add_argument('--run',default=RUN)
    a=p.parse_args(argv)
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',a.run):p.error('Invalid run name')
    folder=ROOT/'data/isolated/model_selection/runs'/a.run
    # Resolve the selector's actual output directory rather than assume its layout.
    if a.command in ('results','pause'):
        from slater_model_selection import run_path
        folder=run_path(a.run)
        if a.command=='results':export_csv(folder)
        else:
            if not (folder/'config.json').exists():raise ValueError('No such comparison run')
            (folder/'PAUSE').touch();print('Pause requested; completed games remain cached.')
        return
    report=audit()
    print(f"CHECKPOINTS: {report['present']}/{report['expected']} | Nexto: {report['nexto_present']}",flush=True)
    if report['missing']:
        for path in report['missing'][:12]:print('MISSING:',path,flush=True)
        print('No checkpoints are silently skipped. Full missing list is saved in the audit report.',flush=True)
    destination=ROOT/'data/isolated/checkpoint_comparison_audit.json'
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,indent=2),encoding='utf8')
    if a.command=='audit':return report
    if report['missing'] or not report['nexto_present']:raise ValueError('Restore missing files before starting the complete comparison; see '+str(destination))
    from slater_model_selection import run_path
    folder=run_path(a.run)
    command='resume' if (folder/'config.json').exists() else 'run'
    args=[sys.executable,'-u',str(ROOT/'slater_model_selection.py'),command,'--run',a.run,'--until','screen','--max-games','100000']
    if command=='run':args+=['--config',str(CONFIG)]
    result=subprocess.run(args,cwd=ROOT)
    if (folder/'stages/screen/plan.json').exists():export_csv(folder)
    if result.returncode:raise SystemExit(result.returncode)

if __name__=='__main__':
    try:main()
    except (ValueError,FileNotFoundError) as error:
        print('STOPPED:',error,file=sys.stderr);sys.exit(1)
