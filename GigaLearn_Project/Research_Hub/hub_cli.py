import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from hub_core import (HERE,PROJECT,PRESETS,HubError,atomic_json,new_experiment,make_plan,
  list_experiments,check_runtime,request_safe_stop,start_experiment,replay_tas_audit,
  read_json, exp_path)


def main(argv=None):
    ap=argparse.ArgumentParser(prog='hub_cli.py',description='GigaLearn Research Hub - isolated C++ experiments')
    sp=ap.add_subparsers(dest='cmd',required=True)
    sp.add_parser('check');sp.add_parser('patch');sp.add_parser('build');sp.add_parser('list')
    p=sp.add_parser('create');p.add_argument('name');p.add_argument('--preset',required=True,choices=list(PRESETS));p.add_argument('--seed-dir');p.add_argument('--lr',type=float);p.add_argument('--games',type=int)
    p=sp.add_parser('run');p.add_argument('name')
    p=sp.add_parser('stop');p.add_argument('name')
    p=sp.add_parser('plan');p.add_argument('--variants',type=int,default=12,choices=(6,12,24));p.add_argument('--seed-dir')
    p=sp.add_parser('materialize');p.add_argument('--seed-dir');p.add_argument('--variants',type=int,default=12,choices=(6,12,24))
    sp.add_parser('audit-replays')
    a=ap.parse_args(argv)
    try:
        if a.cmd=='check':out=check_runtime()
        elif a.cmd=='patch':
            from hub_cpp_patch import patch
            out=patch()
        elif a.cmd=='build':
            if os.name!='nt':raise HubError('Build requires a Windows VS2022 x64 Developer Command Prompt')
            root=PROJECT.parent
            cmake=str(root/'.venv/Lib/site-packages/torch')
            call=['cmake','--build',str(PROJECT/'build_py311'),'--config','Release','--parallel','4']
            print('Using build_py311 (the working Python 3.11 C++ build).',flush=True)
            subprocess.run(call,cwd=PROJECT,check=True)
            out={'build':'completed','binary':str(PROJECT/'build_py311/Release/GigaLearnBot.exe')}
        elif a.cmd=='list':out=list_experiments()
        elif a.cmd=='create':
            cfg={k:v for k,v in {'lr':a.lr,'games':a.games}.items() if v is not None}
            out={'created':str(new_experiment(a.name,a.preset,a.seed_dir,cfg))}
        elif a.cmd=='run':out={'pid':start_experiment(a.name)}
        elif a.cmd=='stop':out={'stop_request':str(request_safe_stop(a.name))}
        elif a.cmd=='plan':out=make_plan(a.seed_dir,a.variants)
        elif a.cmd=='materialize':
            plan=make_plan(a.seed_dir,a.variants)
            out=[]
            for x in plan:
                out.append(str(new_experiment(x['name'],x['preset'],a.seed_dir,x['settings'])))
        elif a.cmd=='audit-replays':out=replay_tas_audit()
        print(json.dumps(out,indent=2,default=str))
        return 0
    except (HubError,FileNotFoundError,RuntimeError,subprocess.CalledProcessError) as e:
        print('ERROR:',e,file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
