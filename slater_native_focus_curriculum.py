"""Native C++ curriculum: one skill, varied tests, rehearsal and preserved checkpoints."""
import argparse,json,os,shutil,subprocess,sys,time
from pathlib import Path
from slater_native_eval import helper,load,model_identity,code_identity,evaluate,check_pause,EvaluationPaused,parity
from slater_native_actor import NativeActor
from slater_v041_core import atomic_json,read_json,sha256,process_lock
from slater_focus_evaluation import STAGES,episode,mastery
from slater_event_windows import BASE,prepare
from slater_native_campaign import checkpoints
ROOT=Path(__file__).resolve().parent
DEFAULT={'games':32,'steps':32768,'decisions':500000,'stage_chunks':30,'eval_seeds':16,'required_streak':10,'bc_epochs':5,'difficulty':0.0,'rehearsal_fraction':.2,'min_disk_gb':10,'compare_every':5}

def verify_windows(folder,build=None):
    h=helper();folder=Path(folder);manifest=read_json(folder/'manifest.json');bank=Path(manifest['bank']);windows=Path(manifest['windows']);out=folder/'cpp_window_audit.json';verified=folder/'windows.native.json'
    if sha256(bank)!=manifest['bank_sha'] or sha256(windows)!=manifest['windows_sha']:raise ValueError('Prepared windows changed')
    build=Path(build or h.BASE/'build');binary=build/('SlaterGigaNative.exe' if os.name=='nt' else 'SlaterGigaNative');identity=h.binary_identity(build)
    if verified.exists():
        doc=read_json(verified)
        if doc['binary']!=identity or doc['bank_sha']!=sha256(bank):raise ValueError('Window audit binary/bank changed; use a new prepared folder')
        return verified
    args=[binary,'--meshes',h.meshes(),'--checkpoints',folder/'audit_unused','--replay-bank',bank,'--event-windows',windows,'--event-audit-out',out,'--device','cpu']
    proc=subprocess.run([str(x) for x in args],cwd=build,env=h.runtime_environment(binary,folder/'pause.flag'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (folder/'cpp_window_audit.log').write_text(proc.stdout,encoding='utf8')
    if proc.returncode or 'SLATER_EVENT_AUDIT_COMPLETE' not in proc.stdout:raise RuntimeError('C++ window audit failed; inspect cpp_window_audit.log')
    raw=read_json(windows);records=read_json(out);accepted=[raw['windows'][r['index']] for r in records if r['accepted']]
    atomic_json(verified,dict(version=1,bank_sha=sha256(bank),cpp_verified=True,binary=identity,windows=accepted))
    print('NATIVE_WINDOWS_VERIFIED',len(accepted),'/',len(raw['windows']),flush=True);return verified

def child(args,stop,child_pause):
    child_pause.unlink(missing_ok=True)
    proc=subprocess.Popen([str(a) for a in args])
    while proc.poll() is None:
        if stop.exists() and child_pause.parent.exists():child_pause.touch()
        time.sleep(.25)
    if proc.returncode:raise RuntimeError('Native child failed; completed checkpoints/logs are preserved')
    check_pause(stop)

def stage_check(actor,rival,stage,folder,*,seed_base,seeds,streak,difficulty,window_data=None,bank=None,stop=None):
    protocol=dict(stage=stage,actor=getattr(actor,'identity',None),seed_base=seed_base,seeds=seeds,streak=streak,difficulty=difficulty)
    cached=read_json(folder)
    if cached and cached.get('protocol')!=protocol:raise ValueError('Stage evaluation inputs changed')
    if cached and cached.get('complete'):return cached
    records=cached['records'] if cached else []
    done={(r['seed'],r['side']) for r in records}
    for j in range(seeds):
        for side in ('blue','orange'):
            check_pause(stop)
            if (seed_base+j*997,side) in done:continue
            team=0 if side=='blue' else 1;window=None
            if stage.startswith('replay_'):
                options=[w for w in window_data['windows'] if w['split']==1 and w['kind']==stage and w['query_team']==team]
                groups={}
                for w in options:groups.setdefault(w.get('replay_group',w['replay_sha']),[]).append(w)
                if len(groups)<6:raise ValueError('Need at least six independent validation replays for this role/color')
                keys=sorted(groups);choices=groups[keys[j%len(keys)]];window=choices[(j//len(keys))%len(choices)]
            row=episode(actor,rival,stage,seed=seed_base+j*997,side=side,difficulty=difficulty,window=window,bank=bank);records.append(row)
            print('FOCUS_CHECK',stage,j+1,'/',seeds,side,'success',row['success'],'idle',round(row['idle_fraction'],3),flush=True)
            atomic_json(folder,dict(protocol=protocol,stage=stage,records=records,complete=False))
    result=dict(protocol=protocol,stage=stage,records=records,complete=True,mastery=mastery(records,streak));atomic_json(folder,result);return result

def run(name,*,source,prepared,build=None,max_chunks=0,config=None,skip_bc=False):
    from export_rlbot_v4 import validate_name
    validate_name(name);h=helper();folder=BASE/name;folder.mkdir(parents=True,exist_ok=True);stop=folder/'pause.flag';cfg={**DEFAULT,**(config or {})}
    if not 5<=cfg['required_streak']<=15 or not cfg['eval_seeds']>=cfg['required_streak'] or not 1<=cfg['stage_chunks']<=200 or not 1000<=cfg['decisions']<=10000000:raise ValueError('Invalid curriculum budget')
    if not 0<=cfg['rehearsal_fraction']<=.5 or not 0<=cfg['difficulty']<=1:raise ValueError('Invalid rehearsal/difficulty')
    prepared=Path(prepared);manifest=read_json(prepared/'manifest.json');bank=Path(manifest['bank']);windows=verify_windows(prepared,build);window_data=read_json(windows)
    if sha256(bank)!=manifest['bank_sha']:raise ValueError('Event bank changed')
    build=Path(build or h.BASE/'build');playing=ROOT/'data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt';teacher=playing if playing.is_file() else ROOT/'vendor/nexto/nexto-model.pt'
    protocol=dict(source=model_identity(source),bank_sha=sha256(bank),windows_sha=sha256(windows),binary=h.binary_identity(build),teacher=model_identity(teacher),config=cfg,
                  code={**code_identity(),'runner':sha256(__file__),'focus_eval':sha256(ROOT/'slater_focus_evaluation.py'),'windows_prepare':sha256(ROOT/'slater_event_windows.py')})
    with process_lock(folder/'curriculum.lock'):
        stop.unlink(missing_ok=True);old=read_json(folder/'protocol.json')
        if old and old!=protocol:raise ValueError('Curriculum inputs changed; preserve this run and choose a new name')
        if not old:atomic_json(folder/'protocol.json',protocol)
        state=read_json(folder/'status.json',dict(stage_index=0,stage_chunks=0,total_chunks=0,mastered=[],latest=str(Path(source).resolve()),trusted=None,bc_done=skip_bc,difficulty=cfg['difficulty']))
        state['playing_model']=str(teacher)
        state['status']='RUNNING';atomic_json(folder/'status.json',state)
        rival=load(teacher);initial_total=state['total_chunks']
        try:
            while state['stage_index']<len(STAGES):
                if max_chunks and state['total_chunks']-initial_total>=max_chunks:state['status']='BUDGET_REACHED';break
                if shutil.disk_usage(folder).free/1024**3<cfg['min_disk_gb']:state['status']='DISK_FLOOR_REACHED';break
                stage=STAGES[state['stage_index']];chunk=state['total_chunks']+1;side='blue' if chunk%2 else 'orange';native_name=f'{name}_{chunk:05d}_{stage}';native_run=h.BASE/'runs'/native_name
                if state['stage_chunks']>=cfg['stage_chunks']:state['status']='STAGE_BUDGET_REACHED';break
                planned=read_json(native_run/'source_checkpoint.json')
                src=planned['path'] if planned else state['latest'];actor=NativeActor(src);existing=read_json(native_run/'protocol.json')
                saved=checkpoints(native_run/'checkpoints')
                already=max(0,int(saved[-1].name)-int(Path(src).name)) if saved else 0
                remaining=max(0,cfg['decisions']-already)
                every=round(1/cfg['rehearsal_fraction']) if cfg['rehearsal_fraction'] else 0
                training_stage=state['mastered'][(chunk-1)%len(state['mastered'])] if state['mastered'] and every and chunk%every==0 else stage
                args=[sys.executable,'-u',h.HERE/'native_setup.py','resume' if existing else 'train','--run',native_name,'--build-dir',build,'--device','auto',
                    '--games',cfg['games'],'--steps',cfg['steps'],'--iterations',max(200,(remaining+cfg['steps']-1)//cfg['steps']+2),'--decisions',remaining,'--threads','2',
                    '--campaign','--focus',training_stage,'--old-chance','1','--learner-team',side,'--focus-difficulty',state['difficulty'],
                    '--width',actor.width,'--depth',actor.depth,'--save-every','200000','--kickoff-epochs',1 if stage=='kickoff' and state['stage_chunks']==0 and not existing else 0,'--bc-epochs',0 if state['bc_done'] else cfg['bc_epochs']]
                if training_stage.startswith('replay_'):args+=['--event-windows',windows]
                if not existing:args+=['--initial-checkpoint',src,'--replay-bank',bank,'--frozen-checkpoint',src]
                state.update(active_run=native_name,status='TRAINING');atomic_json(folder/'status.json',state)
                if not existing or remaining:child(args,stop,native_run/'pause.flag')
                latest=checkpoints(native_run/'checkpoints')[-1]
                if int(latest.name)-int(Path(src).name)<cfg['decisions']:raise RuntimeError('Native chunk stopped before its decision budget; saved checkpoints retained')
                state['bc_done']=True
                state.update(latest=str(latest),status='CHECKING',training_stage=training_stage);atomic_json(folder/'status.json',state)
                check_dir=folder/f'chunk_{chunk:05d}';check_dir.mkdir(exist_ok=True);candidate=NativeActor(latest);parity(latest,build)
                from slater_native_teacher_repair import validation
                fit=validation(latest,bank);fit['reconstructed_label_kl']=fit.pop('teacher_kl');atomic_json(check_dir/'imitation_fit.json',fit)
                print('IMITATION_FIT',json.dumps(fit),flush=True)
                check=stage_check(candidate,rival,stage,check_dir/'stage.json',seed_base=10100000000+chunk*100000,seeds=cfg['eval_seeds'],streak=cfg['required_streak'],difficulty=state['difficulty'],window_data=window_data,bank=bank,stop=stop)
                passed=check['mastery']['passed']
                if passed:
                    # Practice old stages again before moving forward. No old weights are deleted.
                    for k,old_stage in enumerate(state['mastered']):
                        prior=stage_check(candidate,rival,old_stage,check_dir/f'retention_{old_stage}.json',seed_base=11100000000+chunk*100000+k*1000,seeds=cfg['eval_seeds'],streak=cfg['required_streak'],difficulty=1.0,window_data=window_data,bank=bank,stop=stop)
                        passed&=prior['mastery']['passed']
                if passed or (cfg['compare_every'] and chunk%cfg['compare_every']==0):
                    rivals={'nexto':str(ROOT/'vendor/nexto/nexto-model.pt')}
                    if playing.is_file():rivals['update180']=str(playing)
                    report=evaluate({'candidate':str(latest),'starting_native':str(Path(source).resolve())},rivals,out=ROOT/'data/isolated/native_quality/focus_curriculum'/name/f'chunk_{chunk:05d}.json',seeds=2,seconds=45,seed_base=12100000000+chunk*100000,build_dir=build,stop_file=stop)
                    state['latest_game_ranking']=report['ranking']
                    print('FOCUS_GAME_COMPARISON',json.dumps(report['ranking']),flush=True)
                state['total_chunks']=chunk;state['stage_chunks']+=1
                if passed:
                    if not stage.startswith('replay_') and stage!='kickoff' and state['difficulty']<1:
                        state['difficulty']=min(1.0,state['difficulty']+.25);state['stage_chunks']=0
                        print('FOCUS_DIFFICULTY_INCREASED',stage,state['difficulty'],flush=True)
                    else:
                        state['mastered'].append(stage);state['stage_index']+=1;state['stage_chunks']=0;state['trusted']=str(latest);state['difficulty']=cfg['difficulty']
                        print('FOCUS_STAGE_PASSED',stage,'checkpoint',latest,flush=True)
                state.update(active_run=None,status='RUNNING');atomic_json(folder/'status.json',state)
            state['status']='CURRICULUM_COMPLETE' if state['stage_index']>=len(STAGES) else state['status'];atomic_json(folder/'status.json',state)
        except EvaluationPaused:state['status']='PAUSED';atomic_json(folder/'status.json',state)
        except Exception as exc:state.update(status='ERROR',reason=str(exc));atomic_json(folder/'status.json',state);raise
        return state

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('prepare','run','pause','status'));p.add_argument('--run',default='focused_curriculum01');p.add_argument('--prepared',default=str(BASE/'windows01'))
    p.add_argument('--inputs',default='data/replays/ranked-duels');p.add_argument('--source',default=str(ROOT/'data/isolated/gigalearn_native/runs/ranked_duels_train01/checkpoints/3711232'));p.add_argument('--build-dir');p.add_argument('--max-chunks',type=int,default=0);p.add_argument('--config');p.add_argument('--skip-bc',action='store_true');a=p.parse_args()
    folder=BASE/a.run
    if a.command=='prepare':prepare(a.inputs,a.prepared,max_replays=212);verify_windows(a.prepared,a.build_dir)
    elif a.command=='pause':
        folder.mkdir(parents=True,exist_ok=True);(folder/'pause.flag').touch();state=read_json(folder/'status.json',{})
        if state.get('active_run'):
            active=helper().BASE/'runs'/state['active_run']
            if active.is_dir():(active/'pause.flag').touch()
        print('Pause requested; current native iteration saves before stopping.')
    elif a.command=='status':print(json.dumps(read_json(folder/'status.json',{}),indent=2))
    else:print(json.dumps(run(a.run,source=a.source,prepared=a.prepared,build=a.build_dir,max_chunks=a.max_chunks,config=read_json(a.config,{}) if a.config else None,skip_bc=a.skip_bc),indent=2))
