"""Bounded native improvement experiments; promotion requires independent matches."""
from __future__ import annotations
import argparse,json,shutil,subprocess,sys,time
from pathlib import Path
import numpy as np
from slater_v041_core import atomic_json,read_json,sha256,process_lock
from slater_native_actor import NativeActor,checkpoint_identity
from slater_native_eval import ROOT,BASE,helper,model_identity,identity_digest,evaluate,paired_verdict,code_identity

DEFAULT={
 'screen_seeds':2,'screen_seconds':60,'qualify_seeds':8,'qualify_seconds':90,
 'confirm_seeds':12,'confirm_seconds':120,'final_confirm_seeds':16,'final_confirm_seconds':300,'skill_seeds':4,'skill_seconds':8,
 'rounds':2,'decisions_per_branch':2000000,'branch_iteration_limit':200,
 'games':64,'steps':32768,'threads':2,'old_chance':.4,'save_every':500000,'family_alpha':.05,
 'bootstrap':True,'bootstrap_bc_epochs':5,
}
INCUMBENT=ROOT/'data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt'
BANK=ROOT/'data/isolated/ranked_duels_bank01.bin'
SKILLS=('ground','defense','recovery','aerial','wall','air_dribble','air_finish','reset_use','low_boost')

def checkpoints(folder):
    return sorted([p for p in Path(folder).glob('*') if p.is_dir() and p.name.isdigit() and all((p/f).is_file() for f in ('POLICY.lt','SHARED_HEAD.lt','CRITIC.lt','RUNNING_STATS.json'))],key=lambda p:int(p.name))

def discover():
    root=ROOT/'data/isolated/gigalearn_native/runs';candidates={}
    basic=checkpoints(root/'native_train01/checkpoints')
    replay=checkpoints(root/'ranked_duels_train01/checkpoints')
    if basic:candidates['cpp_before_replays']=str(basic[-1])
    if replay:
        for name,index in (('cpp_after_bc',0),('cpp_replay_middle',len(replay)//2),('cpp_replay_latest',len(replay)-1)):
            path=str(replay[index])
            if path not in candidates.values():candidates[name]=path
    if INCUMBENT.is_file():candidates['update180']=str(INCUMBENT)
    candidates['nexto']=str(ROOT/'vendor/nexto/nexto-model.pt')
    if not any(Path(p).is_dir() for p in candidates.values()):raise ValueError('No trained native checkpoints found; use --candidate paths')
    return candidates

def frozen_rivals(candidates):
    rivals={'nexto':str(ROOT/'vendor/nexto/nexto-model.pt')}
    if INCUMBENT.is_file():rivals['update180']=str(INCUMBENT)
    return rivals

def paths(run):
    if not run or not run.replace('_','').replace('-','').isalnum() or len(run)>40:raise ValueError('Invalid campaign name')
    return BASE/'campaigns'/run

def ensure_protocol(folder,candidates,rivals,config,bank,build_dir):
    h=helper();build=Path(build_dir or h.BASE/'build').resolve();binary=build/('SlaterGigaNative.exe' if sys.platform=='win32' else 'SlaterGigaNative')
    if not binary.is_file():raise ValueError('Build the updated native executable first')
    protocol={'candidates':{n:model_identity(p) for n,p in candidates.items()},'rivals':{n:model_identity(p) for n,p in rivals.items()},
        'config':config,'bank':str(Path(bank).resolve()),'bank_sha':sha256(bank),'binary':h.binary_identity(build),
        'build_dir':str(build),'code':{**code_identity(),'campaign':sha256(__file__)}}
    old=read_json(folder/'protocol.json')
    if old and old!=protocol:raise ValueError('Campaign inputs/settings changed; use a new campaign name')
    if not old:atomic_json(folder/'protocol.json',protocol)
    return protocol

def qualify(candidates,rivals,folder,cfg,namespace,build_dir,incumbent):
    screen=evaluate(candidates,rivals,out=folder/'screen.json',seeds=cfg['screen_seeds'],seconds=cfg['screen_seconds'],seed_base=namespace,build_dir=build_dir)
    names=[r['candidate'] for r in screen['ranking'][:2]]
    if incumbent not in names:names.append(incumbent)
    finalists={n:candidates[n] for n in names}
    qualification=evaluate(finalists,rivals,out=folder/'qualification.json',seeds=cfg['qualify_seeds'],seconds=cfg['qualify_seconds'],seed_base=namespace+100000,build_dir=build_dir)
    leader=qualification['ranking'][0]['candidate']
    # Leader is frozen before opening confirmation. Never re-rank on holdout.
    selection={'leader':leader,'finalists':finalists,'incumbent':incumbent,'qualification_sha':sha256(folder/'qualification.json')}
    old=read_json(folder/'frozen_finalists.json')
    if old and old!=selection:raise ValueError('Frozen finalists changed')
    atomic_json(folder/'frozen_finalists.json',selection)
    confirmation=evaluate(finalists,rivals,out=folder/'confirmation.json',seeds=cfg['confirm_seeds'],seconds=cfg['confirm_seconds'],seed_base=namespace+200000,build_dir=build_dir)
    alpha=cfg['family_alpha']/max(1,(cfg['rounds']+3)*len(names))
    verdicts={n:paired_verdict(confirmation,leader,n,alpha=alpha) for n in names if n!=leader}
    passed=bool(verdicts) and all(v['passed'] for v in verdicts.values())
    chosen=leader if passed else incumbent
    result={'status':'CONFIRMED_SIMULATOR_LEADER' if passed else 'CLOSE_OR_INCONCLUSIVE','leader':leader,
        'selected':chosen,'selected_path':candidates[chosen],'verdicts':verdicts,'alpha_per_comparison':alpha,
        'note':'Conservative incumbent retention; confirmation is not reused to select another challenger.'}
    atomic_json(folder/'selection.json',result);print('NATIVE_SELECTION',result['status'],chosen,flush=True)
    return result,screen

def skills(candidate,rival,folder,cfg,namespace,build_dir):
    report=evaluate({'model':candidate},{'fixed':rival},out=folder/'skills.json',seeds=cfg['skill_seeds'],seconds=cfg['skill_seconds'],
        seed_base=namespace,build_dir=build_dir,tasks=SKILLS)
    rows={task:[r for r in report['records'] if r['task']==task] for task in SKILLS}
    rates={task:sum(r['successes'] for r in data)/max(1,sum(r['episodes'] for r in data)) for task,data in rows.items()}
    # Finish is coupled to the air-control curriculum, not a separate setter.
    focus=min(rates,key=lambda key:(rates[key],list(SKILLS).index(key)))
    if focus=='air_finish':focus='air_dribble'
    atomic_json(folder/'weaknesses.json',{'success_rates':rates,'focus':focus,'note':'Practice screen chooses training focus; not final test mastery.'})
    return focus

def guard(candidate,reference,rivals,folder,cfg,namespace,build_dir):
    report=evaluate({'candidate':candidate,'reference':reference},rivals,out=folder/'skill_guard.json',
        seeds=cfg['skill_seeds'],seconds=cfg['skill_seconds'],seed_base=namespace,build_dir=build_dir,tasks=SKILLS)
    checks={}
    for task in SKILLS:
        scores={n:[r for r in report['records'] if r['candidate']==n and r['task']==task] for n in ('candidate','reference')}
        rates={n:sum(r['successes'] for r in data)/max(1,sum(r['episodes'] for r in data)) for n,data in scores.items()}
        delta=rates['candidate']-rates['reference'];checks[task]={'success_delta':delta,'passed':delta>=-.125}
    passed=all(c['passed'] for c in checks.values());atomic_json(folder/'skill_guard_verdict.json',{'passed':passed,'checks':checks})
    team_checks={}
    for size in (2,3):
        team=evaluate({'candidate':candidate,'reference':reference},rivals,out=folder/f'team{size}_guard.json',
            seeds=cfg['skill_seeds'],seconds=max(8,cfg['skill_seconds']),seed_base=namespace+size*10000,build_dir=build_dir,team_size=size)
        scores={n:np.mean([r['goal_diff'] for r in team['records'] if r['candidate']==n]) for n in ('candidate','reference')}
        delta=(scores['candidate']-scores['reference'])*60/max(8,cfg['skill_seconds'])
        team_checks[str(size)]={'goal_diff_delta_per_minute':float(delta),'passed':bool(delta>=-.5)}
    passed &= all(c['passed'] for c in team_checks.values())
    atomic_json(folder/'skill_guard_verdict.json',{'passed':passed,'checks':checks,'team_checks':team_checks})
    return passed

def native_run(name,source,bank,focus,pool,cfg,build_dir):
    h=helper();run=h.BASE/'runs'/name;protocol=read_json(run/'protocol.json');result=read_json(run/'last_result.json')
    if result and result.get('campaign_completed'):
        checkpoint_identity(result['checkpoint']);return result
    actor=NativeActor(source)
    args=[sys.executable,'-u',str(ROOT/'GigaLearn_Project/Native_Backend/native_setup.py'),
        'resume' if protocol else 'train','--run',name,'--build-dir',str(build_dir),'--campaign','--device','auto',
        '--games',str(cfg['games']),'--steps',str(cfg['steps']),'--threads',str(cfg['threads']),
        '--iterations',str(cfg['branch_iteration_limit']),'--width',str(actor.width),'--depth',str(actor.depth),
        '--focus',focus,'--old-chance',str(cfg['old_chance']),'--save-every',str(cfg['save_every']),'--bc-epochs','0']
    # Budget is total additional decisions for this branch, including resumed work.
    initial=int(Path(source).name);latest=checkpoints(run/'checkpoints')
    already=max(0,int(latest[-1].name)-initial) if latest else 0
    remaining=cfg['decisions_per_branch']-already
    if remaining>0:
        args+=['--decisions',str(remaining)]
        if not protocol:
            args+=['--initial-checkpoint',source,'--replay-bank',str(bank)]
            for path in pool:args+=['--frozen-checkpoint',path]
        print('NATIVE_BRANCH',name,'focus',focus,'remaining_decisions',remaining,flush=True)
        subprocess.run([str(x) for x in args],cwd=ROOT,check=True)
    result=read_json(run/'last_result.json')
    if not result:raise ValueError('Native branch has no verified result')
    result['campaign_completed']=True;result['source_checkpoint']=source
    result['additional_decisions']=result['total_timesteps']-initial
    if result['additional_decisions']<cfg['decisions_per_branch']:raise RuntimeError('Iteration limit reached before the requested decision budget')
    atomic_json(run/'last_result.json',result);return result

def workflow(run,*,candidates=None,bank=BANK,build_dir=None,config=None,select_only=False):
    folder=paths(run);cfg={**DEFAULT,**(config or {})}
    for name in ('screen_seeds','qualify_seeds','confirm_seeds','skill_seeds'):
        if not 1<=cfg[name]<=64:raise ValueError('Invalid '+name)
    if cfg['confirm_seeds']<8 or cfg['qualify_seeds']<8:raise ValueError('Independent confirmation needs at least eight seeds')
    if not 0<=cfg['bootstrap_bc_epochs']<=10:raise ValueError('Invalid BC epoch budget')
    if not 0<cfg['family_alpha']<=.05 or not 0<=cfg['old_chance']<=1:raise ValueError('Invalid confidence or opponent probability')
    if not 0<=cfg['rounds']<=4 or not 1000<=cfg['decisions_per_branch']<=10000000:raise ValueError('Invalid bounded training budget')
    candidates=candidates or discover();rivals=frozen_rivals(candidates)
    folder.mkdir(parents=True,exist_ok=True)
    with process_lock(folder/'workflow.lock'):
        protocol=ensure_protocol(folder,candidates,rivals,cfg,bank,build_dir);build_dir=protocol['build_dir']
        state=read_json(folder/'progress.json')
        incumbent='update180' if 'update180' in candidates else 'nexto' if 'nexto' in candidates else next(iter(candidates))
        initial,screen=qualify(candidates,rivals,folder/'initial',cfg,950000000,build_dir,incumbent)
        native_names=[r['candidate'] for r in screen['ranking'] if Path(candidates[r['candidate']]).is_dir()]
        if not native_names:raise ValueError('No native learner among candidates')
        if not state:
            state={'round':0,'native_champion':candidates[native_names[0]],'playing_champion':initial['selected_path'],'history':[],
                'initial_selection':initial,'status':'INITIAL_SELECTION_COMPLETE'};atomic_json(folder/'progress.json',state)
        if select_only:return state
        if cfg['bootstrap'] and not state.get('bootstrap_done'):
            source=state['native_champion'];name=run+'_replay_bootstrap';actor=NativeActor(source)
            bootstrap_run=helper().BASE/'runs'/name;result=read_json(bootstrap_run/'last_result.json')
            if not result:
                command='resume' if (bootstrap_run/'protocol.json').exists() else 'train'
                args=[sys.executable,'-u',str(ROOT/'GigaLearn_Project/Native_Backend/native_setup.py'),command,
                    '--run',name,'--build-dir',str(build_dir),'--initial-checkpoint',source,'--replay-bank',str(bank),
                    '--bc-epochs',str(cfg['bootstrap_bc_epochs']),'--device','auto','--games',str(cfg['games']),
                    '--steps',str(cfg['steps']),'--iterations','2','--width',str(actor.width),'--depth',str(actor.depth)]
                subprocess.run(args,cwd=ROOT,check=True);result=read_json(bootstrap_run/'last_result.json')
            bc_candidates={'native_incumbent':source,'after_bc':str(bootstrap_run/'checkpoints'/Path(source).name),'after_bc_ppo':result['checkpoint']}
            decision,_=qualify(bc_candidates,rivals,folder/'bootstrap_selection',cfg,953000000,build_dir,'native_incumbent')
            state['native_champion']=decision['selected_path'];state['bootstrap_done']=True;state['bootstrap_selection']=decision
            atomic_json(folder/'progress.json',state)
        pool=[candidates[n] for n in native_names if (NativeActor(candidates[n]).width,NativeActor(candidates[n]).depth)==
            (NativeActor(state['native_champion']).width,NativeActor(state['native_champion']).depth)][:4]
        for index in range(state['round'],cfg['rounds']):
            round_folder=folder/f'round_{index+1:02d}';namespace=960000000+index*1000000
            before=state['native_champion'];focus=skills(before,next(iter(rivals.values())),round_folder,cfg,namespace,build_dir)
            contenders={'incumbent':before};branches={}
            for label,practice in (('mixed','mixed'),('focused',focus)):
                name=f'{run}_r{index+1:02d}_{label}'
                result=native_run(name,before,bank,practice,list(dict.fromkeys([before,*pool]))[:4],cfg,build_dir)
                branches[label]=result
                saved=checkpoints(helper().BASE/'runs'/name/'checkpoints')
                saved=[p for p in saved if int(p.name)>int(Path(before).name)]
                if len(saved)>1:contenders[label+'_middle']=str(saved[len(saved)//2])
                contenders[label+'_latest']=result['checkpoint']
            decision,_=qualify(contenders,rivals,round_folder/'selection',cfg,namespace+300000,build_dir,'incumbent')
            selected=decision['selected_path'];passed=decision['status']=='CONFIRMED_SIMULATOR_LEADER'
            if passed and selected!=before:passed=guard(selected,before,rivals,round_folder,cfg,namespace+600000,build_dir)
            if passed:
                state['native_champion']=selected;pool=list(dict.fromkeys([selected,*pool]))[:4]
            else:selected=before
            state['history'].append({'round':index+1,'focus':focus,'branches':{k:{'checkpoint':v['checkpoint'],'decisions':v['additional_decisions']} for k,v in branches.items()},
                'selected':selected,'confirmed_and_retained':passed,'decision':decision})
            state['round']=index+1;state['status']='ROUND_COMPLETE';atomic_json(folder/'progress.json',state)
        # Fresh final qualification/confirmation compares the retained native
        # lineage with the protected playing incumbent. It never rewrites either.
        final_candidates={'native_champion':state['native_champion'],'playing_incumbent':state['playing_champion']}
        final_cfg={**cfg,'qualify_seconds':180,'confirm_seeds':cfg['final_confirm_seeds'],'confirm_seconds':cfg['final_confirm_seconds']}
        final,_=qualify(final_candidates,rivals,folder/'final',final_cfg,970000000,build_dir,'playing_incumbent')
        state['playing_champion']=final['selected_path'];state['status']='COMPLETE';state['final_selection']=final
        from slater_native_holdout import test_report
        test_report(state['native_champion'],bank,folder/'untouched_replay_test.json')
        atomic_json(folder/'progress.json',state);atomic_json(folder/'selected.json',{
            'native_checkpoint':state['native_champion'],'playing_checkpoint':state['playing_champion'],
            'native_status':'CONFIRMED_NATIVE_LINEAGE' if any(h['confirmed_and_retained'] for h in state['history']) else 'PROVISIONAL_SCREEN_LEADER',
            'playing_identity':model_identity(state['playing_champion']),'status':final['status'],
            'note':'Simulator-selected candidate; native RLBot/browser deployment still requires its own adapter/live verification.'})
        print('NATIVE_CAMPAIGN_COMPLETE',folder,state['playing_champion'],final['status'],flush=True);return state

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('prepare','all','select','status'))
    p.add_argument('--run',default='native_quality01');p.add_argument('--candidate',action='append')
    p.add_argument('--bank',default=str(BANK));p.add_argument('--build-dir');p.add_argument('--config')
    p.add_argument('--inputs',default=str(ROOT/'data/replays/ranked-duels'))
    p.add_argument('--dataset',default=str(ROOT/'data/isolated/ranked_duels_quality_dataset01'))
    p.add_argument('--max-replays',type=int,default=500)
    a=p.parse_args()
    if a.command=='status':print(json.dumps(read_json(paths(a.run)/'progress.json',{}),indent=2));return
    if a.command=='prepare':
        from slater_versatile_data import prepare
        from importlib.util import spec_from_file_location,module_from_spec
        prepare([a.inputs],a.dataset,workers=2,per_replay=1024,max_replays=a.max_replays,max_samples=500000)
        spec=spec_from_file_location('quality_bank',ROOT/'GigaLearn_Project/Native_Backend/prepare_bank.py')
        module=module_from_spec(spec);spec.loader.exec_module(module)
        bank=Path(a.bank).resolve()
        if bank.exists():
            report=read_json(bank.with_suffix('.json'))
            if not report or report['sha256']!=sha256(bank) or report['source_manifest_sha']!=sha256(Path(a.dataset)/'manifest.json'):
                raise ValueError('Existing replay bank has different inputs')
            print('NATIVE_BANK_REUSED',bank);return
        module.make(a.dataset,bank,players=2,limit=100000);return
    candidates={f'candidate_{i}_{Path(path).name}':str(Path(path).resolve()) for i,path in enumerate(a.candidate)} if a.candidate else None
    workflow(a.run,candidates=candidates,bank=a.bank,build_dir=a.build_dir,config=read_json(a.config,{}) if a.config else None,select_only=a.command=='select')

if __name__=='__main__':main()
