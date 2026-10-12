"""Compare original vs repaired RocketSim goal-tail positive controls (read only).

Repaired clips are not automatically validated. Same selected start index,
reference goal, both physics modes, trajectory match and actual goal are
required. A positive result is NOT a successful save, training approval, or
long-horizon replay fidelity.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from slater_research.scenario_gate import _is_verified


def checked_windows(report: dict) -> dict:
    if int(report.get('schema_version',-1)) != 3:
        raise ValueError('Expected goal-tail report schema=3')
    result = {}
    for case in report.get('cases', []):
        name=case.get('file')
        if not isinstance(name,str) or Path(name).name!=name or name in result:
            raise ValueError('Invalid/duplicate case names in physics report')
        result[name]=case
    return result


def check_pair(case: dict, candidate: dict) -> tuple[bool, str]:
    window=float(candidate['window_s'])
    by_mode={}
    for row in case.get('windows',[]):
        if abs(float(row.get('window_s',-999))-window) >= 1e-6:
            continue
        mode=row.get('mode')
        if mode not in ('ghosted','all_dynamic') or mode in by_mode:
            return False,'bad_or_duplicate_mode'
        by_mode[mode]=row
    if set(by_mode)!= {'ghosted','all_dynamic'}:
        return False,'missing_mode'
    for mode,row in by_mode.items():
        if (int(row.get('start_step',-1))!=int(candidate['start_step']) or
            int(row.get('reference_goal_step',-1))!=int(candidate['reference_goal_step'])):
            return False,'start_or_goal_changed'
        if not _is_verified(row):
            return False,mode+'_failed_fidelity'
    return True,'pass'


def compare(catalog: dict, repair_report: dict, original_report: dict,
            derived_report: dict) -> dict:
    if int(repair_report.get('schema_version',-1)) != 1:
        raise ValueError('Expected car-state repair report schema=1')
    original=checked_windows(original_report); derived=checked_windows(derived_report)
    candidates={x['clip_file']:x for x in catalog['candidates']}
    rows=[]
    seen=set()
    for row in repair_report['cases']:
        name=row['clip_file']
        if name in seen:
            raise ValueError('Duplicate repair row')
        seen.add(name)
        cand=candidates.get(name)
        if cand is None or cand.get('split')!='train':
            raise ValueError('Comparison only supports train-split catalog entries')
        if name in original and original[name].get('replay_sha256') != cand.get('replay_sha256'):
            raise ValueError(f'{name}: original report replay hash mismatch')
        if name in derived and derived[name].get('replay_sha256') != cand.get('replay_sha256'):
            raise ValueError(f'{name}: derived report replay hash mismatch')
        ok_source, reason_source=(check_pair(original[name],cand)
                                  if name in original else (False,'missing_original_audit'))
        ok_derived,reason_derived=(check_pair(derived[name],cand)
                                   if name in derived else (False,'missing_derived_audit'))
        ok=bool(ok_source and ok_derived and row['status']!='excluded_all_defenders_demoed')
        rows.append({'clip_file':name,'repair_status':row['status'],
                     'original_baseline_pass':ok_source,
                     'repaired_baseline_pass':ok_derived,
                     'original_reason':reason_source,'repaired_reason':reason_derived,
                     'retain_for_further_investigation':ok,
                     'NOT_PPO_CERTIFIED':True})
    return {'schema_version':1,'created_utc':datetime.now(timezone.utc).isoformat(),
            'purpose':'Compare original/derived positive controls; no training',
            'warning':'Reproducing a goal after repair does not prove saveability or valid player-state inference.',
            'summary':{'compared':len(rows),
                       'retained_positive_controls':sum(x['retain_for_further_investigation'] for x in rows),
                       'lost_or_missing_positive_controls':sum(not x['retain_for_further_investigation'] for x in rows),
                       'original_baseline_failures':sum(not x['original_baseline_pass'] for x in rows),
                       'derived_baseline_failures':sum(not x['repaired_baseline_pass'] for x in rows)},
            'cases':rows}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('catalog','repair-report','original-audit','derived-audit','out'):
        parser.add_argument('--'+arg,required=True)
    args=parser.parse_args(argv)
    dst=Path(args.out)
    if dst.exists() or dst.with_name(dst.name+'.partial').exists():
        parser.error('Output exists; never overwrite')
    def load(path):
        with Path(path).open('r',encoding='utf8') as h: return json.load(h)
    result=compare(load(args.catalog),load(args.repair_report),
                   load(args.original_audit),load(args.derived_audit))
    dst.parent.mkdir(parents=True,exist_ok=True)
    tmp=dst.with_name(dst.name+'.partial')
    with tmp.open('x',encoding='utf8') as h:json.dump(result,h,indent=2,allow_nan=False)
    os.replace(tmp,dst)
    print('SUMMARY',result['summary'])
    print('READ-ONLY; derived data still not certified for PPO')
    return result

if __name__=='__main__':main()
