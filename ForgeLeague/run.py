"""Separate direct-policy league; shares the installed NovaForge environment."""
import argparse
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1]/'novaforge'
if not root.exists():root=Path(__file__).resolve().parents[1]/'NovaForge'
sys.path.insert(0,str(root))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Two independent actors; controlled critic pilot, frozen challenge league, protected exports')
    parser.add_argument('command',choices=['check','create','fork','train','pause','status','report','export','watch','test'])
    parser.add_argument('--run',default='duel01');parser.add_argument('--config');parser.add_argument('--fusion')
    parser.add_argument('--source',default='duel01')
    parser.add_argument('--wandb',choices=['online','offline','off'],default='online')
    parser.add_argument('--family',choices=['chronos','galactus'],default='chronos')
    parser.add_argument('--once',action='store_true');parser.add_argument('--max-tasks',type=int)
    args=parser.parse_args()
    from nova import forge_league as league
    alias=league.PROJECT/'active_run.json'
    if alias.exists() and args.run==league.read(alias).get('source'):args.run=league.read(alias)['active']
    if args.command in ('train','watch','export'):args.run=league.breakout_run(args.run)
    if args.command=='create':league.create(args.run,args.config,args.fusion)
    elif args.command=='fork':league.fork(args.source,args.run,args.config)
    elif args.command=='train':league.run(args.run,wandb=args.wandb,once=args.once,max_tasks=args.max_tasks)
    elif args.command=='pause':league.pause(args.run)
    elif args.command=='status':print((league.run_path(args.run)/'status.json').read_text())
    elif args.command=='report':league.report(args.run)
    elif args.command=='export':
        from nova.forge_export import export
        export(args.run)
    elif args.command=='watch':
        from nova.forge_export import watch
        watch(args.run,args.family)
    elif args.command=='test':
        from filelock import FileLock
        from nova.forge_eval import suite
        path=league.run_path(args.run);cfg=league.read(path/'config.json')
        with FileLock(str(path/'train.lock'),timeout=0):
            settings=cfg['evaluation']
            for family in league.FAMILIES:
                suite(cfg,family,league.champion(path,family),path/f'parents/{family}.lt',
                    [dict(name=n) for n in ('chronos','galactus','nexto','ripple')],'test',0,path/'TEST_STOP',
                    pairs=settings['test_pairs'],seconds=settings['test_seconds'],output=path/f'evaluations/heldout_{family}.json')
        league.report(args.run)
    else:
        import subprocess
        result=subprocess.run([sys.executable,'-m','pytest','tests/test_forge_league.py','-q'],cwd=root)
        if result.returncode:raise SystemExit(result.returncode)
        print('FORGE_CHECK_PASS: use 1_CREATE then 2_START_OR_RESUME. No run was reset.')
