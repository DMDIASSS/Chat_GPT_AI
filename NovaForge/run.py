"""Windows entry point; all child process creation is behind the main guard."""
from __future__ import annotations

import argparse
import json
import multiprocessing
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def positive_int(value):
    n=int(value)
    if n<=0: raise argparse.ArgumentTypeError('Must be positive')
    return n


def positive_float(value):
    n=float(value)
    if not 0<n<100000: raise argparse.ArgumentTypeError('Must be positive and finite')
    return n


def main():
    os.chdir(ROOT)
    parser=argparse.ArgumentParser(description='NovaForge 1v1 training lab')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('doctor',help='Real simulator and optional teacher checks')
    p.add_argument('--teachers',default=None,help='Comma-separated bot names (download them first)')
    p.add_argument('--config',default=None)
    p=sub.add_parser('fetch-teachers',help='Download pinned public models and preserve notices')
    p.add_argument('--names',default='nexto,ripple,chronos,galactus')
    p=sub.add_parser('smoke',help='Short real PPO run, save/resume, and frozen actor checks')
    p.add_argument('--run',default='smoke01')
    p.add_argument('--workers',type=positive_int,default=2)
    p.add_argument('--config',default=None)
    p.add_argument('--teachers',default=None)
    p=sub.add_parser('train')
    p.add_argument('--run',default='laptop01')
    p.add_argument('--steps',type=positive_int,default=2_000_000,help='Additional decisions; rounded up to a PPO rollout')
    p.add_argument('--forever',action='store_true',help='Continue segments until pause/Ctrl+C; --steps is the segment size')
    p.add_argument('--wandb',choices=['online','offline','off'],default=None,help='W&B mode; defaults to saved mode or off')
    p.add_argument('--wandb-project',default=None,help='W&B project (default: novaforge)')
    p.add_argument('--wandb-entity',default=None,help='Optional W&B team/user; default is the saved login entity')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--init',default=None,help='NovaForge BC model to initialize a new run')
    p.add_argument('--config',default=None)
    p.add_argument('--workers',type=positive_int,default=None)
    p.add_argument('--device',choices=['cpu','cuda'],default=None)
    p.add_argument('--teachers',default=None,help='Comma-separated nexto,ripple,chronos,galactus')
    p.add_argument('--replay-bank',default=None)
    p=sub.add_parser('collect',help='Collect actual teacher controls in RocketSim')
    p.add_argument('--teacher',default='ripple',help='One bot or a comma-separated mixture of demonstration teachers')
    p.add_argument('--opponent',default='scripted',help='One opponent or comma-separated episode mixture')
    p.add_argument('--samples',type=positive_int,default=20000)
    p.add_argument('--out',default='datasets/ripple20k.npz')
    p.add_argument('--seed',type=int,default=2217)
    p.add_argument('--config',default=None)
    p.add_argument('--replay-bank',default=None)
    p=sub.add_parser('pretrain',help='Behavioral cloning with an episode-disjoint validation split')
    p.add_argument('--dataset',default='datasets/ripple20k.npz')
    p.add_argument('--out',default='models/ripple_bc.zip')
    p.add_argument('--epochs',type=positive_int,default=5)
    p.add_argument('--lr',type=positive_float,default=.0003)
    p.add_argument('--device',choices=['cpu','cuda'],default='cpu')
    p.add_argument('--seed',type=int,default=1109)
    p.add_argument('--config',default=None)
    p=sub.add_parser('replay-import',help='Parse .replay files into starting states, without action labels')
    p.add_argument('source',help='A .replay file or folder of .replay files (1v1 only)')
    p.add_argument('--out',default='datasets/replay_resets.npz')
    p.add_argument('--stride',type=positive_int,default=30)
    p.add_argument('--max-states',type=positive_int,default=5000)
    p.add_argument('--carball',default=None,help='Optional custom carball executable')
    p=sub.add_parser('evaluate',help='Seeded first-goal trials on both teams; no automatic promotion')
    p.add_argument('--model',required=True,help='Run folder, full .zip checkpoint, or exported actor .pt')
    p.add_argument('--baseline',default=None)
    p.add_argument('--opponents',default='scripted')
    p.add_argument('--scenarios',default='kickoff')
    p.add_argument('--pairs',type=positive_int,default=5)
    p.add_argument('--seconds',type=positive_float,default=30)
    p.add_argument('--seed',type=int,default=900001)
    p.add_argument('--out',default='reports/evaluation01.json')
    p.add_argument('--config',default=None)
    p=sub.add_parser('export',help='Export a full NovaForge PPO/BC model for RLBot v5')
    p.add_argument('--model',required=True)
    p=sub.add_parser('watch',help='Stream the bot to the standalone RLViser application')
    p.add_argument('--model',required=True)
    p.add_argument('--opponent',choices=['scripted','scorer','nexto','ripple','chronos','galactus'],default='scorer')
    p.add_argument('--scenario',choices=['kickoff','shot','defense','aerial','dribble','recovery','wall'],default='kickoff')
    p.add_argument('--seconds',type=positive_float,default=30)
    p.add_argument('--seed',type=int,default=5555)
    p.add_argument('--config',default=None)
    p.add_argument('--viewer-mode',choices=['auto','existing','manual'],default='auto')
    p.add_argument('--viewer-exe',default=None,help='Optional explicit viewer path; normal project paths are searched automatically')
    for command in ['status','pause']:
        p=sub.add_parser(command)
        p.add_argument('--run',default='laptop01')
    sub.add_parser('wandb-check',help='Verify the SDK can reuse a saved local W&B login; never displays a key')
    p=sub.add_parser('report',help='Export a metrics-only progress ZIP to share for review')
    p.add_argument('--run',default='diverse01')
    p=sub.add_parser('compare-progress',help='Compare initial and current checkpoints on fixed opponents; pause first')
    p.add_argument('--run',default='diverse01')
    p.add_argument('--opponents',default='nexto,ripple,chronos,galactus')
    p.add_argument('--scenarios',default='kickoff')
    p.add_argument('--pairs',type=positive_int,default=5)
    p.add_argument('--seconds',type=positive_float,default=20)
    p.add_argument('--seed',type=int,default=910001)
    p=sub.add_parser('copy-train',help='Copy frozen teachers with supervised learning and fresh demonstration rounds')
    p.add_argument('--run',default='copy02')
    p.add_argument('--config',default='configs/copy.json')
    p.add_argument('--teachers',default='nexto,ripple,chronos,galactus')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--init',default=None)
    p.add_argument('--forever',action='store_true')
    p.add_argument('--rounds',type=positive_int,default=5,help='Additional rounds unless --forever is set')
    p.add_argument('--samples',type=positive_int,default=50000,help='Teacher decisions per fresh demonstration round')
    p.add_argument('--validation-samples',type=positive_int,default=10000)
    p.add_argument('--buffer-samples',type=positive_int,default=250000)
    p.add_argument('--epochs',type=positive_int,default=2,help='Epochs per fresh demonstration round')
    p.add_argument('--lr',type=positive_float,default=.0001)
    p.add_argument('--seed',type=int,default=29017)
    p.add_argument('--wandb',choices=['online','offline','off'],default=None)
    p=sub.add_parser('copy-report',help='Export imitation metrics and matching evaluations to a shareable ZIP')
    p.add_argument('--run',default='copy02')
    p=sub.add_parser('copy-upgrade',help='Preserve copy02 weights and switch to varied correction collection')
    p.add_argument('--run',default='copy02')
    p=sub.add_parser('pt-to-toml',help='Package a NovaForge TorchScript .pt actor for RLBot v5')
    p.add_argument('model',nargs='?',help='Actor .pt path; omit to open the Windows file picker')
    p.add_argument('--name',default=None,help='Display name for the packaged bot')
    p.add_argument('--assume-novaforge',action='store_true',help='Declare NovaForge features/actions for an actor missing its metadata')
    p.add_argument('--weights-format',choices=['lt','pt'],default='lt',help='Output archive format; lt is LibTorch TorchScript')
    p=sub.add_parser('export-v5',help='Export a trained NovaForge bot as .lt + RLBot v5 .bot.toml + runtime')
    p.add_argument('--model',required=True,help='Run folder, NovaForge full .zip checkpoint, or supported actor')
    p.add_argument('--name',default=None)
    p=sub.add_parser('viewer-setup',help='Find/install RLViser and apply the learner ballcam preset')
    p.add_argument('--exe',default=None)
    p.add_argument('--mode',choices=['auto','existing'],default='auto')
    args=parser.parse_args()
    if args.command in ('status','pause'):
        run=(ROOT/'runs'/args.run).resolve()
        if run.parent!=(ROOT/'runs').resolve(): raise ValueError('Invalid run name')
        if args.command=='pause':
            if not (run/'config.json').exists(): raise FileNotFoundError('No such training run')
            (run/'STOP').touch()
            print('Stop requested. The trainer saves its current policy and exits at the next environment step.')
        else:
            print((run/'status.json').read_text())
    elif args.command=='viewer-setup':
        from nova.viewer import setup_command
        setup_command(args)
    elif args.command in ('pt-to-toml','export-v5'):
        from nova.packaging import package_actor,export_v5
        (package_actor if args.command=='pt-to-toml' else export_v5)(args)
    elif args.command in ('copy-train','copy-report','copy-upgrade'):
        from nova.imitation import train_copy, report_copy, upgrade_copy
        {'copy-train':train_copy,'copy-report':report_copy,'copy-upgrade':upgrade_copy}[args.command](args)
    elif args.command in ('report','compare-progress'):
        from nova.reporting import report_command, compare_command
        (report_command if args.command=='report' else compare_command)(args)
    elif args.command=='wandb-check':
        from nova.tracking import check_login
        check_login()
    elif args.command=='fetch-teachers':
        from nova.teachers import fetch_teachers
        fetch_teachers([n.strip() for n in args.names.split(',')])
    elif args.command in ('doctor','smoke'):
        from nova import diagnostics
        getattr(diagnostics,args.command)(args)
    elif args.command=='train':
        from nova.training import train
        train(args)
    elif args.command in ('collect','pretrain','replay-import'):
        from nova import data
        getattr(data,args.command.replace('-','_'))(args)
    else:
        from nova import evaluation
        function={'evaluate':evaluation.evaluate,'export':evaluation.export_rlbot,'watch':evaluation.watch}[args.command]
        function(args)


if __name__=='__main__':
    multiprocessing.freeze_support()
    main()
