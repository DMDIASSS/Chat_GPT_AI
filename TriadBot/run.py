"""Second project; shares the installed NovaForge Python runtime for setup."""
from pathlib import Path
import argparse
import sys
root=Path(__file__).resolve().parents[1]/'novaforge'
if not root.exists():root=Path(__file__).resolve().parents[1]/'NovaForge'
sys.path.insert(0,str(root))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description='TriadBot frozen experts, Fusion selection and isolated four-way training')
    parser.add_argument('command',choices=['check','watch','export','league','selector-train','selector-pause','selector-status','selector-evaluate','selector-diagnose','selector-routing-evaluate','selector-six-create','selector-six-diagnose','research-backup','research-fork','research-report','fusion-select','fusion-refine-prepare','fusion-refine-train','fusion-refine-pause','selector-four-create'])
    parser.add_argument('--selector',default=None);parser.add_argument('--run',default='selector01');parser.add_argument('--source',default='selector01')
    parser.add_argument('--objective',choices=['current','field_only','goals_only'],default='current');parser.add_argument('--seed',type=int,default=271)
    parser.add_argument('--split',choices=['development','validation','test'],default='development')
    parser.add_argument('--skip-body-check',action='store_true')
    parser.add_argument('--routing-seed',type=int,default=451000001)
    parser.add_argument('--fusion-run',default='all');parser.add_argument('--refinement',default='fusion_refine01');parser.add_argument('--direct',action='store_true')
    parser.add_argument('--max-candidates',type=int,default=12);parser.add_argument('--confirmation-pairs',type=int,default=2);parser.add_argument('--confirmation-seconds',type=float,default=60)
    parser.add_argument('--steps',type=int,default=32768);parser.add_argument('--once',action='store_true');parser.add_argument('--wandb',choices=['online','offline','off'],default='online');parser.add_argument('--pairs',type=int,default=2);parser.add_argument('--seconds',type=float,default=60);args=parser.parse_args()
    from nova import triad
    if args.command in ('fusion-select','fusion-refine-prepare','fusion-refine-train','fusion-refine-pause','selector-four-create'):
        from nova import fusion_selection as fusion
        if args.command=='fusion-select':fusion.select_best(args.fusion_run,args.pairs,args.seconds,args.confirmation_pairs,args.confirmation_seconds,args.max_candidates)
        elif args.command=='fusion-refine-prepare':fusion.prepare_refinement(args.refinement)
        elif args.command=='fusion-refine-train':fusion.train_refinement(args.refinement,args.wandb)
        elif args.command=='fusion-refine-pause':
            from nova.core import ROOT
            run=(ROOT/'runs'/args.refinement).resolve()
            if run.parent!=(ROOT/'runs').resolve() or not (run/'config.json').exists():raise ValueError('No valid refinement run')
            (run/'STOP').touch();print('Fusion refinement stop requested')
        else:fusion.create_four(args.run,args.refinement,args.direct)
    elif args.command.startswith('research-'):
        from nova import research
        if args.command=='research-backup':research.backup(args.run)
        elif args.command=='research-report':research.report(args.run)
        else:research.fork(args.source,args.run,args.objective,args.seed)
    elif args.command.startswith('selector-'):
        from nova import triad_selector as selector
        from nova.research import run_path
        run=run_path(args.run)
        if args.command=='selector-train':selector.train(args.run,steps=args.steps,forever=not args.once,wandb=args.wandb)
        elif args.command=='selector-six-create':
            from nova.six_selector import create
            create(args.run,args.source)
        elif args.command=='selector-six-diagnose':
            from nova.six_selector import diagnose
            diagnose(args.run,args.pairs,args.seconds)
        elif args.command=='selector-evaluate':selector.evaluate(args.run,pairs=args.pairs,seconds=args.seconds,split=args.split)
        elif args.command=='selector-diagnose':
            from nova.selector_diagnostics import diagnose
            diagnose(args.run,pairs=args.pairs,seconds=args.seconds,body_check=not args.skip_body_check)
        elif args.command=='selector-routing-evaluate':
            from nova.selector_routing import evaluate
            evaluate(args.run,pairs=args.pairs,seconds=args.seconds,seed_start=args.routing_seed)
        elif args.command=='selector-pause':
            if not (run/'config.json').exists():raise FileNotFoundError('No selector01 run')
            (run/'STOP').touch();print('Selector stop requested')
        else:print((run/'status.json').read_text())
    elif args.command in ('watch','export'):getattr(triad,args.command)(selector_path=args.selector)
    else:getattr(triad,args.command)()
