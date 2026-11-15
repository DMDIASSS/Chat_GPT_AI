"""A small library-reward continuation; training, watch, evaluation and export."""
import copy,json,os,shutil,tempfile,time
from pathlib import Path
import torch
from .runtime import ROOT,atomic_json,save_checkpoint,sha,source_hashes,config
from .train import lock_run,load
from .gpu_profile import model_hash
from .library_rewards import PRESET,NAMES


def setup(source,target):
    source=Path(source);target=Path(target)
    if target.exists():
        if (target/'latest.pt').is_file() and (target/'library_provenance.json').is_file():
            saved=load(target/'latest.pt',torch.device('cpu'))
            if saved['config']['rewards']['profile']!='rlgym_tools_v1':raise ValueError('Existing run has different rewards; preserved')
            return
        raise FileExistsError(f'{target} already exists without a valid library run; preserved')
    if not (source/'latest.pt').is_file():raise FileNotFoundError(f'{source}/latest.pt is missing. No random or substitute model was created.')
    with lock_run(source):
        original=source/'latest.pt';saved=load(original,torch.device('cpu'));before=sha(original);weights=model_hash(saved['model'])
        if saved['config']['team_size']!=1:raise ValueError('This reward adapter supports 1v1 only')
        stage=Path(tempfile.mkdtemp(prefix='.library_',dir=target.parent))
        try:
            payload=copy.deepcopy(saved);cfg=payload['config'];start=payload['learning_transitions']
            cfg['version']='attentionforge-library-v1';cfg['rewards']=copy.deepcopy(PRESET)
            cfg.pop('skills',None);cfg.pop('attack',None)
            cfg['library']={'version':1,'start_learning_transitions':start,'validation_every':500000,'match_every':2000000,'games_per_context':40,'seconds':60,'reward_definitions':{'rlgym-rocket-league':'2.0.1','rlgym-tools':'2.6.5','classes':list(NAMES)},'reset_distribution':'Existing standard native kickoff/varied-ground resets, no skills or attack curriculum','auxiliary_losses':False}
            payload['wandb_id']=None;payload['recovery_attempts']=0
            for name in payload.get('history',[]):
                if Path(name).name!=name:raise ValueError('Invalid historical checkpoint name')
                (stage/'history').mkdir(exist_ok=True);shutil.copy2(source/'history'/name,stage/'history'/name)
            shutil.copy2(original,stage/'reward_parent.pt');save_checkpoint(stage/'latest.pt',payload);atomic_json(stage/'config.json',cfg)
            record={'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'parent':str(original.resolve()),'parent_sha256':before,'parent_actor_state_sha256':weights,'starting_learning_transitions':start,'initial_actor_unchanged':model_hash(payload['model'])==weights,'optimizer':'Full optimizer state, LR and step counts inherited unchanged','old_rewards':saved['config']['rewards'],'new_rewards':cfg['rewards'],'removed':['custom reward bonuses','skills/attack curricula','ground tutor loss','mechanics rehearsal loss'],'source_hashes':source_hashes()}
            atomic_json(stage/'library_provenance.json',record);atomic_json(stage/'provenance.json',record)
            assert sha(original)==before;os.rename(stage,target)
        finally:
            if stage.exists():shutil.rmtree(stage)
    print('LIBRARY_FORK_READY:',target,'; inherited actor/optimizer; five library rewards only; source preserved.',flush=True)


def monitor(model,cfg,folder,count):
    from .skills import drills
    from .offense import evaluate
    was=model.training
    try:
        model.eval();quality=drills(model,cfg,seed=880001,n=16)
        score=min(v[k] for v in quality.values() for k in ('blue_contact_fraction','orange_contact_fraction'))
        baseline=json.loads((folder/'library_initial_contact.json').read_text())
        flag=folder/'library_guard.json';last=json.loads(flag.read_text()) if flag.exists() else {'bad_contact':0,'bad_match':0}
        last['bad_contact']=last['bad_contact']+1 if score<max(.25,baseline['minimum_contact_fraction']*.6) else 0
        record={'learning_transitions':count,'minimum_contact_fraction':score,'quality':quality,'purpose':'Repeated contact validation; not held-out strength testing'}
        with (folder/'library_validation.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
        print('LIBRARY_CONTACT:',score,flush=True)
        elapsed=count-cfg['library']['start_learning_transitions'];period=cfg['library']['match_every']
        previous=last.get('last_match_bucket',0)
        if elapsed//period>previous:
            r=evaluate(folder,cfg['library']['games_per_context'],cfg['library']['seconds'])
            last['bad_match']=last['bad_match']+1 if r['macro_score_rate']<.4 else 0;last['last_match_bucket']=elapsed//period
        atomic_json(flag,last)
        okay=last['bad_contact']<2 and last['bad_match']<2
        if not okay:print('LIBRARY_REGRESSION_PAUSE: two poor validation panels; latest, parent and pinned candidates preserved. Generate report.',flush=True)
        return okay
    finally:model.train(was)


def run(folder,max_updates=None):
    from .skills import drills
    from .cli import policy
    from .runtime import device
    folder=Path(folder);cfg=config(folder/'config.json')
    if not (folder/'library_initial_contact.json').exists():
        with lock_run(folder):
            torch.set_num_threads(cfg['torch_threads']);model,_=policy(folder,device(cfg));q=drills(model,cfg,seed=880001,n=16)
            atomic_json(folder/'library_initial_contact.json',{'minimum_contact_fraction':min(v[k] for v in q.values() for k in ('blue_contact_fraction','orange_contact_fraction')),'quality':q})
    from .train import train
    train(cfg,folder,max_updates=max_updates)


def menu(run_name='library01'):
    folder=ROOT/'runs'/run_name
    while True:
        print('\nLIBRARY REWARDS — '+run_name+'\n1 Continue from skills01 once / resume library training\n2 Watch open play vs frozen parent\n3 Watch all five kickoffs vs frozen parent\n4 Report ZIP\n5 Export PT/CFG + LT/TOML\n6 Balanced scoring evaluation (600 games, 90s)\n7 Pause\n8 Watch best pinned open-play candidate\n9 First create from attack01 instead (optional)\n0 Exit',flush=True)
        try:
            choice=input('Choose: ').strip()
            if choice=='0':return
            if choice in ('1','9'):
                if choice=='9' and folder.exists():raise FileExistsError('library01 already exists; its parent cannot be changed')
                setup(ROOT/'runs'/('attack01' if choice=='9' else 'skills01'),folder);run(folder)
            elif choice in ('2','3'):
                from .cli import watch
                watch(config(),folder,opponent=folder/'reward_parent.pt',scenario=5 if choice=='2' else -2)
            elif choice=='4':
                from .cli import report
                report(folder)
            elif choice=='5':
                from .cli import export
                export(folder)
            elif choice=='6':
                from .offense import evaluate
                evaluate(folder,100,90)
            elif choice=='7':
                if not folder.exists():raise FileNotFoundError(folder)
                (folder/'STOP').write_text('pause\n');print('Wait for PAUSED_AND_SAVED in trainer console.')
            elif choice=='8':
                from .offense import selected_pin
                from .cli import watch
                watch(config(),folder,opponent=folder/'reward_parent.pt',scenario=5,checkpoint=selected_pin(folder,'open_play'))
        except KeyboardInterrupt:print('Interrupted; saved checkpoints preserved.')
        except Exception as ex:print(type(ex).__name__+': '+str(ex)+'\nOperation failed; existing runs preserved.',flush=True)
