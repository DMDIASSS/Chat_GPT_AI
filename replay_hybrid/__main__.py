"""Train, pause, inspect or export the isolated replay-initialized hybrid."""
import argparse,json,re,shutil,sys,tempfile
from pathlib import Path
from replay_hybrid.train import train,ROOT
from slater_v041_core import read_json,atomic_json,sha256


def run_path(name):
    if not re.fullmatch('[A-Za-z0-9_-]{1,50}',name):raise ValueError('Invalid run name')
    return ROOT/'data/isolated/replay_imitation/rvq_runs'/name


def export_run(root,name,latest=False,search=False):
    from replay_rvq.export import export
    selected=read_json(root/'policy/selected.json',{})
    if read_json(root/'protocol.json',{}).get('schema')!='replay-hybrid-training-v1':raise ValueError('Not a hybrid run; use its original exporter')
    if not latest:
        if selected.get('updates',0)<1:raise ValueError('No validation improvement selected yet. Use --latest only for an explicitly experimental comparison.')
        target=export(root,name)
    else:
        with tempfile.TemporaryDirectory(prefix='.hybrid_export_',dir=root) as directory:
            view=Path(directory);(view/'policy').mkdir();shutil.copy2(root/'protocol.json',view/'protocol.json')
            shutil.copy2(root/'policy/latest.pt',view/'policy/best.pt')
            atomic_json(view/'policy/selected.json',{'sha256':sha256(view/'policy/best.pt'),
                'validation':{'experimental_latest':True,'competitive_strength_verified':False}})
            target=export(view,name)
    info=read_json(target/'EXPORT_INFO.json');protocol=read_json(root/'protocol.json')
    heldout=read_json(root/'heldout_matches.json',{})
    matches=heldout.get('checkpoint_sha256')==info['checkpoint_sha256']
    settings=read_json(target/'runtime.json');settings['mode']='search' if search else 'policy';atomic_json(target/'runtime.json',settings)
    info['mode']=settings['mode']
    info['learning']='Human replay initialization followed by simulated PPO and replay anchoring; frozen during live play'
    info['hybrid']={'learning':'Replay-initialized PPO with human replay anchor','source_sha256':protocol['source_sha256'],
        'team_size_trained':protocol['team_size'],'experimental_latest':bool(latest),
        'heldout':heldout if matches else {},'heldout_checkpoint_matches':matches,'live_game_verified':False}
    atomic_json(target/'EXPORT_INFO.json',info)
    cfg=(target/'bot.cfg').read_text(encoding='utf8')
    cfg=cfg.replace('Offline human-replay residual VQ policy with value-guided all-car search',
        'Replay-initialized PPO policy with learned action chunks and optional search')
    (target/'bot.cfg').write_text(cfg,encoding='utf8')
    with (target/'README_IMPORT.txt').open('a',encoding='utf8') as stream:
        stream.write('\nHybrid export: default direct policy; optional search requires --search at export.\n'
            'The model learned in simulation after replay initialization. It never trains during live play.\n'
            'The PPO return critic is not exported as the next-goal search value head.\n')
    return target


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',nargs='?',default='status',choices=('check','start','pause','status','export'))
    parser.add_argument('--run');parser.add_argument('--source-run')
    parser.add_argument('--device',choices=('auto','cpu','cuda'),default='auto')
    parser.add_argument('--steps',type=int);parser.add_argument('--envs',type=int)
    parser.add_argument('--team-size',type=int,choices=(1,2,3));parser.add_argument('--horizon',type=int)
    parser.add_argument('--minibatch',type=int);parser.add_argument('--evaluate-every',type=int)
    parser.add_argument('--evaluation-games',type=int);parser.add_argument('--evaluation-seconds',type=int)
    parser.add_argument('--final-games',type=int);parser.add_argument('--final-seconds',type=int)
    parser.add_argument('--wandb-mode',choices=('online','offline','disabled'),default='online')
    parser.add_argument('--name',default='ReplayHybrid01');parser.add_argument('--latest',action='store_true')
    parser.add_argument('--nexto',type=Path,help='Optional original Nexto model; otherwise vendor/nexto is detected')
    parser.add_argument('--search',action='store_true',help='Opt into search in the export; default is the trained direct policy')
    args=parser.parse_args(argv);root=run_path(args.run or ('replay_hybrid_check' if args.command=='check' else 'replay_hybrid01'))
    saved=read_json(root/'protocol.json',{})
    if saved and saved.get('schema')!='replay-hybrid-training-v1':raise ValueError('Run belongs to another workflow; choose a new --run')
    if args.command=='pause':
        if not root.exists():raise ValueError('Hybrid run has not started')
        (root/'pause.flag').touch();print('HYBRID_PAUSE_REQUESTED: wait for HYBRID_SAVED before closing CMD',flush=True);return 0
    if args.command=='status':
        print('HYBRID_RUN:',root,flush=True)
        print(json.dumps({'progress':read_json(root/'progress.json',{}),'status':read_json(root/'status.json',{}),
            'selected':read_json(root/'policy/selected.json',{})},indent=2),flush=True);return 0
    if args.command=='export':export_run(root,args.name,args.latest,args.search);return 0
    source=run_path(args.source_run) if args.source_run else Path(saved.get('source_run',run_path('replay_rvq01')))
    if source.resolve()==root.resolve():raise ValueError('Source and child run must be different')
    defaults={'steps':1000000,'envs':4,'team_size':1,'horizon':128,'minibatch':128,
        'evaluate_every':50000,'evaluation_games':6,'evaluation_seconds':120,'final_games':12,'final_seconds':300}
    budget=read_json(root/'budget.json',{})
    settings={key:getattr(args,key) if getattr(args,key) is not None else budget.get(key,saved.get(key,value)) for key,value in defaults.items()}
    if args.command=='check':settings.update(steps=256,envs=2,team_size=1,horizon=32,minibatch=64,
        evaluate_every=128,evaluation_games=2,evaluation_seconds=2,final_games=2,final_seconds=2)
    root.mkdir(parents=True,exist_ok=True);atomic_json(root/'budget.json',settings)
    train(source,root,**settings,device=args.device,wandb_mode='disabled' if args.command=='check' else args.wandb_mode,
        nexto_path=args.nexto or saved.get('nexto_path'))
    return 0


if __name__=='__main__':
    from replay_il_prepare_snapshot import ClosingSafeTee
    log=ROOT/'data/isolated/replay_imitation/hybrid_launcher.log';log.parent.mkdir(parents=True,exist_ok=True)
    stdout,stderr=sys.stdout,sys.stderr;code=0
    with log.open('a',encoding='utf8') as stream:
        sys.stdout=ClosingSafeTee(stdout,stream);sys.stderr=ClosingSafeTee(stderr,stream)
        try:code=main()
        except (ValueError,RuntimeError,OSError,KeyError) as error:print('STOPPED:',str(error),flush=True);code=1
        except KeyboardInterrupt:print('Interrupted; last checkpoint is preserved. Prefer the pause command for a fresh save.',flush=True);code=130
        finally:sys.stdout,sys.stderr=stdout,stderr
    raise SystemExit(code)
