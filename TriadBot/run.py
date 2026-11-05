"""Second project; shares the installed NovaForge Python runtime for setup."""
from pathlib import Path
import argparse
import sys
root=Path(__file__).resolve().parents[1]/'novaforge'
if not root.exists():root=Path(__file__).resolve().parents[1]/'NovaForge'
sys.path.insert(0,str(root))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description='TriadBot three frozen experts')
    parser.add_argument('command',choices=['check','watch','export','league','selector-train','selector-pause','selector-status','selector-evaluate']);parser.add_argument('--selector',default=None);parser.add_argument('--steps',type=int,default=32768);parser.add_argument('--once',action='store_true');parser.add_argument('--wandb',choices=['online','offline','off'],default='online');parser.add_argument('--pairs',type=int,default=2);parser.add_argument('--seconds',type=float,default=60);args=parser.parse_args()
    from nova import triad
    if args.command.startswith('selector-'):
        from nova import triad_selector as selector
        run=selector.RUNS/'selector01'
        if args.command=='selector-train':selector.train(steps=args.steps,forever=not args.once,wandb=args.wandb)
        elif args.command=='selector-evaluate':selector.evaluate(pairs=args.pairs,seconds=args.seconds)
        elif args.command=='selector-pause':
            if not (run/'config.json').exists():raise FileNotFoundError('No selector01 run')
            (run/'STOP').touch();print('Selector stop requested')
        else:print((run/'status.json').read_text())
    elif args.command in ('watch','export'):getattr(triad,args.command)(selector_path=args.selector)
    else:getattr(triad,args.command)()
