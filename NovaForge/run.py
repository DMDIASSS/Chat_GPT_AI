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
    p.add_argument('--teachers',default=None,help='nexto,ripple (download them first)')
    p.add_argument('--config',default=None)
    p=sub.add_parser('fetch-teachers',help='Download pinned public models and preserve notices')
    p.add_argument('--names',default='nexto,ripple')
    p=sub.add_parser('smoke',help='Short real PPO run, save/resume, and frozen actor checks')
    p.add_argument('--run',default='smoke01')
    p.add_argument('--workers',type=positive_int,default=2)
    p=sub.add_parser('train')
    p.add_argument('--run',default='laptop01')
    p.add_argument('--steps',type=positive_int,default=2_000_000,help='Additional decisions; rounded up to a PPO rollout')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--init',default=None,help='NovaForge BC model to initialize a new run')
    p.add_argument('--config',default=None)
    p.add_argument('--workers',type=positive_int,default=None)
    p.add_argument('--device',choices=['cpu','cuda'],default=None)
    p.add_argument('--teachers',default=None,help='nexto, ripple, or nexto,ripple')
    p.add_argument('--replay-bank',default=None)
    p=sub.add_parser('collect',help='Collect actual teacher controls in RocketSim')
    p.add_argument('--teacher',choices=['scripted','nexto','ripple'],default='ripple')
    p.add_argument('--opponent',choices=['scripted','nexto','ripple'],default='scripted')
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
    p.add_argument('--opponent',choices=['scripted','nexto','ripple'],default='scripted')
    p.add_argument('--scenario',choices=['kickoff','shot','defense','aerial','dribble','recovery','wall'],default='kickoff')
    p.add_argument('--seconds',type=positive_float,default=30)
    p.add_argument('--seed',type=int,default=5555)
    p.add_argument('--config',default=None)
    for command in ['status','pause']:
        p=sub.add_parser(command)
        p.add_argument('--run',default='laptop01')
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
