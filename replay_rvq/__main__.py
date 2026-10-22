"""Run the separate cached-data RVQ experiment, preserving legacy training."""
import argparse,re,sys
from pathlib import Path
from slater_v041_core import read_json,atomic_json
from replay_rvq.train import train,ROOT


def locations(run,dataset=None):
    if not re.fullmatch('[A-Za-z0-9_-]{1,50}',run):raise ValueError('Invalid RVQ run name')
    base=ROOT/'data/isolated/replay_imitation'
    root=base/'rvq_runs'/run
    if dataset is None:
        preferred=base/'dataset_mixed3v3_02'
        dataset=preferred if (preferred/'manifest.json').is_file() else base/'dataset01'
        saved=read_json(root/'dataset.json')
        if saved:dataset=Path(saved['path'])
    dataset=Path(dataset).resolve()
    if not dataset.is_relative_to(ROOT/'data/isolated'):raise ValueError('Use an existing project data/isolated dataset')
    return root,dataset


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',nargs='?',default='status',choices=('start','pause','status','benchmark','export'))
    parser.add_argument('--run',default='replay_rvq01');parser.add_argument('--dataset',type=Path)
    parser.add_argument('--codec-epochs',type=int,default=15);parser.add_argument('--policy-epochs',type=int,default=15)
    parser.add_argument('--device',choices=('auto','cpu','cuda'),default='auto')
    parser.add_argument('--batch-size',type=int);parser.add_argument('--wandb-mode',choices=('online','offline','disabled'),default='online')
    parser.add_argument('--candidates',nargs='+',type=int,default=[4,16,64]);parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--name',default='ReplayRVQ01')
    args=parser.parse_args(argv);root,dataset=locations(args.run,args.dataset)
    if args.command=='pause':
        if not root.exists():raise ValueError('No RVQ run exists yet')
        (root/'pause.flag').touch();print('RVQ_PAUSE_REQUESTED: wait for checkpoint save before closing CMD',flush=True);return 0
    if args.command=='status':
        print('RVQ_RUN:',root,'| cached dataset:',dataset,flush=True)
        for stage in ('codec','policy'):print(stage,read_json(root/stage/'progress.json',{}),flush=True)
        print('No replays are parsed by this workflow. Existing legacy runs are separate.',flush=True);return 0
    if args.command=='benchmark':
        from replay_rvq.planner import benchmark
        benchmark(root,device=args.device,candidates=args.candidates,repeats=args.repeats);return 0
    if args.command=='export':
        if read_json(root/'policy/selected.json',{}).get('updates',0)<1:
            raise ValueError('No policy improved over its initial validation baseline. Inspect reports before exporting.')
        from replay_rvq.export import export
        export(root,args.name);return 0
    if not (dataset/'manifest.json').is_file():raise ValueError('Prepared dataset manifest missing. Preserve caches and finish the existing preparation first.')
    protocol=read_json(root/'protocol.json',{})
    batch_size=args.batch_size or protocol.get('batch_size',128)
    root.mkdir(parents=True,exist_ok=True)
    saved=read_json(root/'dataset.json')
    if saved and Path(saved['path'])!=dataset:raise ValueError('RVQ dataset path changed. Use the original dataset or a new run.')
    if not saved:atomic_json(root/'dataset.json',{'path':str(dataset)})
    train(dataset,root,codec_epochs=args.codec_epochs,policy_epochs=args.policy_epochs,device=args.device,
        batch_size=batch_size,wandb_mode=args.wandb_mode)
    print('RVQ_RUN_SAVED:',root,flush=True);return 0


if __name__=='__main__':
    from replay_il_prepare_snapshot import ClosingSafeTee
    log=ROOT/'data/isolated/replay_imitation/rvq_launcher.log';log.parent.mkdir(parents=True,exist_ok=True)
    original_stdout,original_stderr=sys.stdout,sys.stderr;code=0
    with log.open('a',encoding='utf8') as stream:
        sys.stdout=ClosingSafeTee(original_stdout,stream);sys.stderr=ClosingSafeTee(original_stderr,stream)
        try:code=main()
        except (ValueError,RuntimeError,OSError) as error:print('STOPPED:',str(error),flush=True);code=1
        except KeyboardInterrupt:print('Interrupted. Resume from the last checkpoint; use the pause command for a graceful save.',flush=True);code=130
        finally:sys.stdout,sys.stderr=original_stdout,original_stderr
    raise SystemExit(code)
