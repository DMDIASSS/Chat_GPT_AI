"""Finite scoring experiments; preserve PPO and teacher-refreshed candidates."""
import argparse,json,sys,time,shutil
from pathlib import Path
import torch
from slater_native_inspect import current_checkpoint
from slater_native_actor import NativeActor
from slater_native_eval import helper,load,parity,check_pause,EvaluationPaused,evaluate,model_identity,code_identity
from slater_native_teacher_guidance import collect
from slater_focus_evaluation import episode
from slater_v041_core import read_json,atomic_json,process_lock,sha256
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'data/isolated/native_scoring_experiments'

def run(name,source=None,teacher=None,build=None,rounds=3,decisions=200000,teacher_episodes=24,seeds=8):
    from export_rlbot_v4 import validate_name
    validate_name(name);folder=BASE/name;folder.mkdir(parents=True,exist_ok=True);h=helper();build=Path(build or h.BASE/'build').resolve();saved=read_json(folder/'protocol.json')
    source=Path(source or (saved['source']['path'] if saved else current_checkpoint(require_paused=True))).resolve()
    teacher=Path(teacher or ROOT/'data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt').resolve()
    if not teacher.is_file():raise FileNotFoundError('Frozen teacher missing: '+str(teacher))
    if not 1<=rounds<=20 or not 1000<=decisions<=2000000 or not 1<=seeds<=32:raise ValueError('Invalid finite experiment budget')
    protocol=dict(source=model_identity(source),teacher=model_identity(teacher),binary=h.binary_identity(build),rounds=rounds,decisions=decisions,teacher_episodes=teacher_episodes,seeds=seeds,code={**code_identity(),'experiment':sha256(__file__),'focus_eval':sha256(ROOT/'slater_focus_evaluation.py'),'teacher_guidance':sha256(ROOT/'slater_native_teacher_guidance.py')})
    if saved and saved!=protocol:raise ValueError('Experiment changed; preserve this run and use a new name')
    stop=folder/'pause.flag';torch.set_num_threads(1)
    with process_lock(folder/'experiment.lock'):
        if not saved:atomic_json(folder/'protocol.json',protocol)
        state=read_json(folder/'status.json',dict(round=0,latest=str(source),difficulty=0.,best_drill=None,playing_model=str(teacher)))
        stop.unlink(missing_ok=True);rival=load(teacher);torch.set_num_threads(1)
        try:
            while state['round']<rounds:
                check_pause(stop)
                if shutil.disk_usage(folder).free<10*1024**3:state['status']='DISK_FLOOR_REACHED';break
                k=state['round']+1;part=folder/f'round_{k:03d}';part.mkdir(exist_ok=True);native_name=f'{name}_r{k:03d}';native=h.BASE/'runs'/native_name;active_pause=native/'pause.flag';model=NativeActor(state['latest']);existing=read_json(native/'protocol.json')
                state.update(status='COLLECTING',active_run=native_name);atomic_json(folder/'status.json',state)
                bank=part/'teacher_bank.bin';collect(bank,teacher,state['latest'],stage='ground_score',difficulty=state['difficulty'],episodes=teacher_episodes,seconds=6,seed_base=19100000000+k*10000,stop=stop)
                from slater_native_campaign import checkpoints as complete_checkpoints
                checkpoints=complete_checkpoints(native/'checkpoints') if (native/'checkpoints').exists() else []
                already=max(0,int(checkpoints[-1].name)-int(Path(state['latest']).name)) if checkpoints else 0;remaining=max(0,decisions-already)
                args=[sys.executable,'-u',h.HERE/'native_setup.py','resume' if existing else 'train','--run',native_name,'--build-dir',build,'--device','auto','--games','32','--steps','16384','--iterations',200,'--decisions',remaining,'--width',model.width,'--depth',model.depth,'--campaign','--focus','ground_score','--focus-difficulty',state['difficulty'],'--learner-team','blue' if k%2 else 'orange','--old-chance','1','--save-every','100000','--teacher-bank',bank,'--teacher-epochs','3','--kickoff-epochs','1','--kickoff-demos','32']
                if not existing:args+=['--initial-checkpoint',state['latest'],'--frozen-checkpoint',state['latest']]
                state['status']='TRAINING';atomic_json(folder/'status.json',state)
                if not existing or remaining:
                    from slater_native_focus_curriculum import child
                    child(args,stop,active_pause)
                result=read_json(native/'last_result.json');candidates={'incumbent':state['latest'],('refreshed' if result.get('teacher_refreshed') else 'trained'):result['checkpoint']}
                if result.get('before_teacher_checkpoint'):candidates['ppo_before_refresh']=result['before_teacher_checkpoint']
                state['status']='SCREENING';atomic_json(folder/'status.json',state);screen=read_json(part/'drills.json',dict(records=[]));done={(r['model'],r['seed'],r['side']) for r in screen['records']}
                for label,path in candidates.items():
                    parity(path,build);actor=NativeActor(path)
                    for j in range(seeds):
                        for side in ('blue','orange'):
                            check_pause(stop);seed=20100000000+k*10000+j*997
                            if (label,seed,side) in done:continue
                            row=episode(actor,rival,'ground_score',seed=seed,side=side,difficulty=state['difficulty']);row['model']=label;screen['records'].append(row);atomic_json(part/'drills.json',screen)
                            print('SCORING_CHECK',label,side,'scored',row['goal_scored'],'success',row['success'],'touches',row['touch_ticks'],flush=True)
                ranked=[]
                for label,path in candidates.items():
                    rows=[r for r in screen['records'] if r['model']==label]
                    ranked.append(dict(model=label,path=path,success=sum(r['success'] for r in rows),goals=sum(r['goal_scored'] for r in rows),conceded=sum(r['conceded'] for r in rows),cases=len(rows),idle=sum(r['idle_fraction'] for r in rows)/len(rows)))
                ranked.sort(key=lambda r:(-r['success'],r['conceded'],r['idle'],r['model']!='incumbent'));atomic_json(part/'ranking.json',ranked);winner=ranked[0]
                games=evaluate({label:path for label,path in candidates.items()},{'frozen_teacher':str(teacher)},out=ROOT/'data/isolated/native_quality/scoring_experiments'/name/f'round_{k:03d}.json',seeds=2,seconds=30,seed_base=21100000000+k*10000,build_dir=build,learner_scripted=False,stop_file=stop)
                atomic_json(part/'games.json',games);print('SCORING_DRILL_RANKING',json.dumps(ranked),flush=True);print('SCORING_GAME_RANKING',json.dumps(games['ranking']),flush=True)
                game_leader=games['ranking'][0]
                state.update(round=k,latest=winner['path'],best_drill=winner,best_match=dict(path=candidates[game_leader['candidate']],screen=game_leader),game_ranking=games['ranking'],active_run=None)
                winner_rows=[r for r in screen['records'] if r['model']==winner['model']]
                if all(sum(r['success'] for r in winner_rows if r['side']==side)>=.75*seeds for side in ('blue','orange')):state['difficulty']=min(1.,state['difficulty']+.25)
                state['status']='ROUND_COMPLETE';atomic_json(folder/'status.json',state)
            if state.get('status')!='DISK_FLOOR_REACHED':state['status']='FINITE_EXPERIMENT_COMPLETE'
        except EvaluationPaused:state['status']='PAUSED'
        except Exception as exc:state.update(status='ERROR',error=str(exc));atomic_json(folder/'status.json',state);raise
        atomic_json(folder/'status.json',state);return state

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('run','pause','status'));p.add_argument('--run',default='scoring_experiment01');p.add_argument('--source');p.add_argument('--teacher');p.add_argument('--build-dir');p.add_argument('--rounds',type=int,default=3);p.add_argument('--decisions',type=int,default=200000);a=p.parse_args();folder=BASE/a.run
    if a.command=='pause':
        folder.mkdir(parents=True,exist_ok=True);(folder/'pause.flag').touch();state=read_json(folder/'status.json',{})
        if state.get('active_run'):
            native=helper().BASE/'runs'/state['active_run']
            if native.is_dir():(native/'pause.flag').touch()
        print('Scoring pause requested; current native iteration saves.')
    elif a.command=='status':print(json.dumps(read_json(folder/'status.json',{}),indent=2))
    else:print(json.dumps(run(a.run,a.source,a.teacher,a.build_dir,a.rounds,a.decisions),indent=2))
