"""Extract explicitly goal-labelled 10-15s clips from a directory of replays."""
import argparse
import json
from pathlib import Path
from slater_research.replay_engine import extract_goal_clips


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--replays',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--lead',type=float,default=12.)
    p.add_argument('--limit',type=int,default=0,help='Debug only: process the first N replays, 0 means all')
    args=p.parse_args()
    if not 10<=args.lead<=15:raise ValueError('Use 10-15 seconds')
    if args.limit<0:raise ValueError('--limit must be nonnegative')
    reports=[]
    replay_paths=sorted(Path(args.replays).rglob('*.replay'))
    if args.limit:replay_paths=replay_paths[:args.limit]
    for source in replay_paths:
        try:
            diagnostic={}
            clips=extract_goal_clips(source,args.out,lead_seconds=args.lead,diagnostics=diagnostic)
            reports.append({'replay':str(source),'clips':[str(c) for c in clips],
                            'diagnostics':diagnostic,'error':None})
            print(f'{source.name}: {len(clips)} clips, '
                  f'goal_periods={diagnostic.get("goal_periods",0)}, '
                  f'events={diagnostic.get("goal_events",0)}, '
                  f'skips={diagnostic.get("clip_skip_reasons",{})}, '
                  f'example_failure={diagnostic.get("sample_failures",[])[:1]}',flush=True)
        except Exception as e:
            reports.append({'replay':str(source),'clips':[],'error':f'{type(e).__name__}: {e}'})
            print('FAILED',source.name,e,flush=True)
    out=Path(args.out)/'manifest.json'
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(reports,indent=2),encoding='utf8')
    total=sum(len(r['clips']) for r in reports)
    print(f'Wrote {out}; total clips={total}; replays={len(reports)}')
    if not total:
        print('NO CLIPS: inspect manifest.json diagnostics. Do NOT start training.',flush=True)

if __name__=='__main__':main()
