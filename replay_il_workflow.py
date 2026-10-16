"""Offline replay workflow with explicit stages, safe resume and local results."""
from pathlib import Path
from datetime import datetime,timezone
import argparse
import json
import re
import subprocess
import sys
import threading
from slater_v041_core import atomic_json,read_json,sha256,process_lock

ROOT=Path(__file__).resolve().parent
DEFAULT_RUN='replay_mixed3v3_02'


def last_event(path):
    """Read a bounded tail, tolerating a concurrent incomplete JSONL write."""
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0,2);length=stream.tell();stream.seek(max(0,length-16384));raw=stream.read()
        for line in reversed(raw.decode('utf8','replace').splitlines()):
            try:
                row=json.loads(line)
                if isinstance(row,dict) and 'update' in row:return row
            except ValueError:pass
    except OSError:pass
    return {}


def run_logged(command,*,cwd,folder,dataset):
    stop=threading.Event()
    def heartbeat():
        while not stop.wait(30):
            event=last_event(folder/'events.jsonl');parse=read_json(dataset/'parse_progress.json',{})
            if event:
                print('WORKFLOW_HEARTBEAT: last durable event',event.get('kind'),'update',event.get('update'),
                      '|',json.dumps(event.get('metrics',{})),flush=True)
            else:print('WORKFLOW_HEARTBEAT: last saved replay',parse.get('completed',0),'/',parse.get('total',0),
                       '| initialization/parsing/validation may still be working',flush=True)
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    try:return subprocess.run(command,cwd=cwd)
    finally:stop.set();thread.join(timeout=1.)


def locations(run,dataset=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,50}',run):raise ValueError('Invalid run name')
    base=ROOT/'data/isolated/replay_imitation'
    dataset=Path(dataset) if dataset is not None else base/('dataset01' if run=='replay_scratch01' else 'dataset_mixed3v3_02')
    dataset=(dataset if dataset.is_absolute() else ROOT/dataset).resolve()
    if not dataset.is_relative_to(ROOT/'data/isolated'):raise ValueError('Dataset must stay under project data/isolated')
    return base/'runs'/run,dataset,base/'workflows'/(run+'.json')


def checkpoint_progress(folder):
    """The checkpoint is authoritative if interruption left progress.json behind."""
    if not (folder/'latest.pt').is_file():return read_json(folder/'progress.json',{})
    import torch
    document=torch.load(folder/'latest.pt',map_location='cpu',weights_only=True)
    return dict(document['progress'])


def summary(run,dataset=None,*,epochs=10):
    folder,dataset,marker=locations(run,dataset)
    manifest=read_json(dataset/'manifest.json',{});progress=checkpoint_progress(folder)
    selected=read_json(folder/'selected.json',{});parse=read_json(dataset/'parse_progress.json',{})
    stage='PARSING_NOT_COMPLETE' if not manifest else 'READY_TO_TRAIN'
    if (folder/'latest.pt').exists():
        stage='CHECKPOINT_SAVED'
        if progress.get('epoch',0)>=epochs:stage='TRAINING_BUDGET_COMPLETE'
        elif progress.get('stale_epochs',0)>=4:stage='EARLY_STOPPED'
        elif (folder/'pause.flag').exists():stage='PAUSE_REQUESTED'
    if not manifest and (dataset/'pause.flag').exists():stage='PAUSE_REQUESTED'
    coverage=read_json(dataset/'format_audit.json',{})
    if manifest and coverage.get('verified_3v3_coverage') is False:stage='INSUFFICIENT_3V3_DATA'
    validation=selected.get('validation',{})
    report={'schema':'replay-il-workflow-results-v1','run':run,'dataset':str(dataset),'stage':stage,
        'last_launcher_stage':read_json(marker,{}).get('stage'),'parse_completed':parse.get('completed',0),
        'parse_total':parse.get('total',0),'parse_error_count':len(parse.get('errors',[])),
        'accepted_samples':manifest.get('samples',parse.get('samples',0)),
        'matches_by_format':manifest.get('matches_by_format',{}),'matches_by_split':manifest.get('matches_by_split',{}),
        'epoch':progress.get('epoch',0),'updates':progress.get('updates',0),'stale_epochs':progress.get('stale_epochs',0),
        'validation':validation,'selected_model':str(folder/'best.pt') if (folder/'best.pt').exists() else None,
        'tokens':str(folder/'tokens.npy') if (folder/'tokens.npy').exists() else None,
        'model':read_json(folder/'model.json',{}),'wandb':read_json(folder/'wandb_state.json',{}),
        'competitive_strength_verified':False,'note':'Offline replay metrics. Saved stages do not prove a process is currently running.'}
    if report['selected_model']:
        report['selected_hash_valid']=sha256(folder/'best.pt')==selected.get('sha256')
    latest_reports=sorted(folder.glob('epoch_*.json')) if folder.exists() else []
    if latest_reports:
        last=read_json(latest_reports[-1],{})
        report['latest_epoch_report']=str(latest_reports[-1]);report['parameter_change_l2']=last.get('parameter_change_l2')
        report['optimizer_change_verified']=bool(progress.get('updates',0)>0 and last.get('parameter_change_l2',0)>0)
    mse=validation.get('value_mse');constant=validation.get('constant_zero_value_mse')
    if mse is not None and constant and constant>0:report['value_mse_reduction_vs_zero_percent']=100*(1-mse/constant)
    return report


def show(report):
    print('STAGE:',report['stage'],'| run:',report['run'],flush=True)
    print('REPLAYS:',report['parse_completed'],'/',report['parse_total'],'| accepted samples:',report['accepted_samples'],
          '| parse errors:',report['parse_error_count'],flush=True)
    print('TRAINING: saved epoch',report['epoch'],'| updates',report['updates'],'| stale epochs',report['stale_epochs'],flush=True)
    if report['validation']:print('SELECTED VALIDATION:',json.dumps(report['validation']),flush=True)
    if report['selected_model']:print('SELECTED MODEL:',report['selected_model'],flush=True)
    print('No matches are generated or used for training. Metrics do not establish competitive strength.',flush=True)


def pause(run,dataset=None):
    folder,dataset,_=locations(run,dataset);written=[]
    for path in (folder,dataset):
        if path.exists():(path/'pause.flag').touch();written.append(str(path))
    if not written:raise ValueError('No dataset/run exists yet')
    print('PAUSE REQUESTED. Wait for the current replay or training checkpoint boundary before closing CMD.',flush=True)
    return written


def start(run,dataset=None,*,epochs=10,inputs=None,device='auto',wandb_mode='online',max_replays=3000,
          max_samples=500000,require_3v3=True):
    if not 1<=epochs<=200:raise ValueError('Epoch budget must be 1..200')
    folder,dataset,marker=locations(run,dataset)
    marker.parent.mkdir(parents=True,exist_ok=True)
    def stage(label,**details):
        atomic_json(marker,{'stage':label,'run':run,'dataset':str(dataset),
            'updated_utc':datetime.now(timezone.utc).isoformat(),'total_epoch_budget':epochs,**details})
        print('WORKFLOW:',label,flush=True)
    def invoke(command,extra=()):
        result=run_logged([sys.executable,'-u','-m','replay_il.launch',command,'--run',run,
            '--dataset',str(dataset),'--device',device,'--wandb-mode',wandb_mode,*extra],cwd=ROOT,folder=folder,dataset=dataset)
        if result.returncode:stage('STOPPED_WITH_SAVED_PROGRESS',exit_code=result.returncode)
        return result.returncode
    with process_lock(marker.with_suffix('.lock')):
        try:
            if not (dataset/'manifest.json').exists():
                stage('PREPARING_REPLAYS')
                roots=inputs or [str(ROOT/'data/replays'/n) for n in ('ranked-duels','ranked-doubles','ranked-standard')]
                from replay_il_prepare_snapshot import freeze_inputs
                frozen=freeze_inputs(dataset,roots,max_replays=max_replays,max_samples=max_samples)
                print('INPUT SNAPSHOT:',len(frozen['files']),'replays; new downloads require a new dataset.',flush=True)
                # A JSON snapshot avoids Windows' command-line length limit for
                # thousands of filenames, without editing parser source hashes.
                code=run_logged([sys.executable,'-u',str(ROOT/'replay_il_prepare_snapshot.py'),
                    '--dataset',str(dataset)],cwd=ROOT,folder=folder,dataset=dataset).returncode
                if code:stage('STOPPED_WITH_SAVED_PROGRESS',exit_code=code)
                if code:return code
            stage('VERIFYING_DATASET')
            if require_3v3:
                from audit_replay_mix import audit
                audit(dataset)
            else:
                from replay_il.train import Dataset
                Dataset(dataset)
            progress=checkpoint_progress(folder);done=int(progress.get('epoch',0))
            if done>=epochs or progress.get('stale_epochs',0)>=4:
                stage('COMPLETE' if done>=epochs else 'EARLY_STOPPED')
                show(summary(run,dataset,epochs=epochs));return 0
            resume=(folder/'latest.pt').is_file()
            if folder.exists() and not resume:
                raise ValueError('Run folder exists without latest.pt. Preserve it and choose a new --run; initialization may have been interrupted.')
            remaining=epochs-done
            stage('RESUMING_TRAINING' if resume else 'STARTING_FRESH_TRAINING',saved_epoch=done,remaining_epochs=remaining)
            code=invoke('resume' if resume else 'train',['--epochs',str(remaining)])
            if code:return code
            report=summary(run,dataset,epochs=epochs)
            stage(report['stage']);show(report)
            if folder.exists():atomic_json(folder/'results_summary.json',report)
            return 0
        except KeyboardInterrupt:
            pause(run,dataset);stage('INTERRUPTED')
            print('Resume from the last completed checkpoint. Use the pause command for a graceful checkpoint save.',flush=True)
            return 130
        except Exception as error:
            stage('STOPPED_WITH_SAVED_PROGRESS',error=str(error)[:500]);raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',nargs='?',default='status',choices=('start','pause','status','results','analyze','test','export','repair'))
    parser.add_argument('--run',default=DEFAULT_RUN);parser.add_argument('--dataset',type=Path)
    parser.add_argument('--epochs',type=int,default=10,help='Total saved-epoch target, not extra epochs per launch')
    parser.add_argument('--inputs',nargs='+');parser.add_argument('--device',choices=('auto','cpu','cuda'),default='auto')
    parser.add_argument('--wandb-mode',choices=('online','offline','disabled'),default='online')
    parser.add_argument('--max-replays',type=int,default=3000);parser.add_argument('--max-samples',type=int,default=500000)
    parser.add_argument('--allow-no-3v3',action='store_true',help='Explicitly operate on a duels/doubles-only dataset')
    parser.add_argument('--name');parser.add_argument('--folder',type=Path)
    parser.add_argument('--scripted-kickoff',action='store_true')
    parser.add_argument('--analysis-samples',type=int,default=2000)
    args=parser.parse_args(argv);folder,dataset,_=locations(args.run,args.dataset)
    if args.command=='pause':pause(args.run,dataset);return 0
    if args.command in ('status','results'):
        report=summary(args.run,dataset,epochs=args.epochs);show(report)
        if args.command=='results':
            if not folder.exists():raise ValueError('Training has not created this run yet')
            atomic_json(folder/'results_summary.json',report);print('REPORT:',folder/'results_summary.json',flush=True)
        return 0
    if args.command=='start':return start(args.run,dataset,epochs=args.epochs,inputs=args.inputs,device=args.device,
        wandb_mode=args.wandb_mode,max_replays=args.max_replays,max_samples=args.max_samples,require_3v3=not args.allow_no_3v3)
    if args.command=='test':
        return subprocess.run([sys.executable,'-u','-m','replay_il.launch','test','--run',args.run,'--dataset',str(dataset)],cwd=ROOT).returncode
    if args.command=='analyze':
        from analyze_replay_policy import analyze
        analyze(folder,dataset,device=args.device,limit=args.analysis_samples);return 0
    if args.command=='repair':
        from repair_replay_rlbot import repair
        repair(args.folder or ROOT/'data/rlbot_exports/ReplayScratch01',scripted_kickoff=args.scripted_kickoff);return 0
    if args.command=='export':
        from export_replay_rlbot import export
        export(folder,args.name or 'Replay_'+args.run,scripted_kickoff=args.scripted_kickoff);return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,RuntimeError,OSError) as error:print('STOPPED:',str(error),flush=True);raise SystemExit(1)
