"""Summarize read-only Nexto kickoff A/B telemetry from v036 bot folders.

Usage: python slater_v036_analyze.py --root data/rlbot_exports/slater_v036_nexto_modes --out data/isolated/v036_report01.json
"""
import argparse
from collections import defaultdict, Counter
import json
from pathlib import Path


def analyze(logs):
    groups = defaultdict(list)
    for path in sorted(logs):
        events=[]
        try:
            with Path(path).open(encoding='utf8') as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
        except (OSError, ValueError) as e:
            raise ValueError(f'Unreadable log {path}: {e}') from e
        if not events or events[0].get('type') != 'metadata':
            raise ValueError(f'Invalid v036 log: {path}')
        m=events[0]
        mode=m['mode']; team=int(m['team']); idx=int(m['index'])
        starts=[x for x in events if x['type']=='kickoff_start']
        touches=[x for x in events if x['type']=='first_touch']
        score_changes=[x for x in events if x['type']=='score_change']
        ends=[x for x in events if x['type']=='match_end']
        current_score=ends[-1].get('score') if ends else (score_changes[-1]['score'] if score_changes else None)
        if current_score is None:
            ss=[x['score'] for x in events if x.get('score') is not None]
            current_score=ss[-1] if ss else None
        outcome=None
        if ends and current_score is not None:
            ours=current_score[team]; theirs=current_score[1-team]
            outcome='win' if ours>theirs else 'loss' if ours<theirs else 'draw'
        session={
            'path': str(path), 'mode': mode, 'team': team, 'index': idx,
            'finished': bool(ends), 'score_blue_orange':current_score,
            'outcome_for_nexto':outcome, 'kickoffs':len(starts),
            'first_touches_logged':len(touches),
            'nexto_first_touches':sum(int(x['player_index']==idx) for x in touches),
            'opponent_first_touches':sum(int(x['player_index']!=idx and x['player_index']>=0) for x in touches),
            'score_changes':len(score_changes), 'samples':sum(x['type']=='snapshot' for x in events),
        }
        groups[mode].append(session)
    report={'schema_version':1,'description':'RLBot v4 Nexto kickoff modes: actual match logs, NOT RocketSim outcomes',
            'modes':{},'sessions':[]}
    for mode,sessions in sorted(groups.items()):
        completed=[s for s in sessions if s['finished']]
        outcomes=Counter(s['outcome_for_nexto'] for s in completed)
        report['modes'][mode]={
            'sessions':len(sessions), 'completed_matches':len(completed),
            'wins':outcomes['win'],'losses':outcomes['loss'],'draws':outcomes['draw'],
            'win_rate':round(outcomes['win']/len(completed),4) if completed else None,
            'kickoffs_recorded':sum(s['kickoffs'] for s in sessions),
            'first_touch_nexto':sum(s['nexto_first_touches'] for s in sessions),
            'first_touch_opponent':sum(s['opponent_first_touches'] for s in sessions),
            'samples':sum(s['samples'] for s in sessions),
        }
        report['sessions']+=sessions
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default='data/rlbot_exports/slater_v036_nexto_modes')
    p.add_argument('--out',required=True)
    a=p.parse_args(argv)
    root=Path(a.root).resolve()
    logs=list(root.rglob('kickoff_logs_v036/*.jsonl'))
    if not logs:
        raise FileNotFoundError('No v036 logs found. Play a game with one of the v036 Nexto folders first.')
    out=Path(a.out).resolve()
    out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():
        raise FileExistsError('Refusing to overwrite '+str(out))
    result=analyze(logs)
    with out.open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
    for mode,stat in result['modes'].items(): print('NEXTOV036',mode,json.dumps(stat))
    print('SAVED',out)
    print('CAUTION: Different opponents, sides or match settings make mode-to-mode comparisons invalid.')


if __name__=='__main__':main()
