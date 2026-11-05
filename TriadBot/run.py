"""Second project; shares the installed NovaForge Python runtime for setup."""
from pathlib import Path
import argparse
import sys
root=Path(__file__).resolve().parents[1]/'novaforge'
if not root.exists():root=Path(__file__).resolve().parents[1]/'NovaForge'
sys.path.insert(0,str(root))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description='TriadBot three frozen experts')
    parser.add_argument('command',choices=['check','watch','export','league','selector-train','selector-pause','selector-status','selector-evaluate','research-backup','research-fork','research-report'])
    parser.add_argument('--selector',default=None);parser.add_argument('--run',default='selector01');parser.add_argument('--source',default='selector01')
    parser.add_argument('--objective',choices=['current','field_only','goals_only'],default='current');parser.add_argument('--seed',type=int,default=271)
    parser.add_argument('--split',choices=['development','validation','test'],default='development')
    parser.add_argument('--steps',type=int,default=32768);parser.add_argument('--once',action='store_true');parser.add_argument('--wandb',choices=['online','offline','off'],default='online');parser.add_argument('--pairs',type=int,default=2);parser.add_argument('--seconds',type=float,default=60);args=parser.parse_args()
    from nova import triad
    if args.command.startswith('research-'):
        from nova import research
        if args.command=='research-backup':research.backup(args.run)
        elif args.command=='research-report':research.report(args.run)
        else:research.fork(args.source,args.run,args.objective,args.seed)
    elif args.command.startswith('selector-'):
        from nova import triad_selector as selector
        from nova.research import run_path
        run=run_path(args.run)
        if args.command=='selector-train':selector.train(args.run,steps=args.steps,forever=not args.once,wandb=args.wandb)
        elif args.command=='selector-evaluate':selector.evaluate(args.run,pairs=args.pairs,seconds=args.seconds,split=args.split)
        elif args.command=='selector-pause':
            if not (run/'config.json').exists():raise FileNotFoundError('No selector01 run')
            (run/'STOP').touch();print('Selector stop requested')
        else:print((run/'status.json').read_text())
    elif args.command in ('watch','export'):getattr(triad,args.command)(selector_path=args.selector)
    else:getattr(triad,args.command)()
