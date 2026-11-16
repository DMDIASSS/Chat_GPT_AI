"""Step-bounded, resumable orchestration and physical-contact skill checks."""
import copy,json,os,shutil,tempfile,time,zipfile
from pathlib import Path
import numpy as np
import torch
from .runtime import ROOT,CONTRACT,load,save,sha,atomic_json,actor_sha,lock,batch,device,model
from .model import ActorCritic
from .acquisition import RECIPE,STAGES,stage_config,drill_states
from .observation import ACTIONS

def initialize(root,source):
    root=Path(root);source=Path(source)
    if root.exists():
        s=json.loads((root/'curriculum.json').read_text())
        if s['recipe']!=RECIPE:raise ValueError('Existing curriculum recipe differs; preserved')
        if sha(root/'baseline.pt')!=s['baseline_sha256']:raise ValueError('Frozen curriculum baseline changed')
        return s
    with lock(source):
        checkpoint=source/'latest.pt';ck=load(checkpoint)
        if ck['contract']!=CONTRACT:raise ValueError('Source policy contract differs')
        root.parent.mkdir(parents=True,exist_ok=True)
        stage=Path(tempfile.mkdtemp(prefix='.contact_setup_',dir=root.parent))
        try:
            shutil.copy2(checkpoint,stage/'baseline.pt')
            s={'version':RECIPE['version'],'recipe':copy.deepcopy(RECIPE),
               'baseline_sha256':sha(stage/'baseline.pt'),'source_run':source.name,
               'origin_transitions':ck['learning_transitions'],'stage_index':0,
               'status':'ready','created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
               'promotion':'none; independent unverified curriculum experiment',
               'checkpoints':{},'probes':[]}
            atomic_json(stage/'curriculum.json',s);os.rename(stage,root)
        finally:
            if stage.exists():shutil.rmtree(stage)
    return s

def stage_folder(root,index):return Path(root)/f'{index+1:02d}_{STAGES[index]}'

def fork_stage(source,target,baseline,stage,origin):
    """Preserve actor/its Adam moments; reset critic only at an objective fork."""
    source=Path(source);target=Path(target);baseline=Path(baseline)
    if target.exists():raise FileExistsError('Existing stage preserved')
    ck=load(source);old_actor=actor_sha({k:v for k,v in ck['model'].items() if k.startswith('actor.')})
    cfg=stage_config(ck['config'],stage);cfg['seed']=(cfg['seed']+6007*(1+STAGES.index(stage)))%0x40000000
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(cfg['seed']);fresh=ActorCritic(cfg['width'])
    names=[k for k,_ in fresh.named_parameters()]
    ids=[i for g in ck['optimizer']['param_groups'] for i in g['params']]
    if len(ids)!=len(names):raise ValueError('Optimizer mapping differs; no guessed conversion')
    for name,index in zip(names,ids):
        if name.startswith('critic.'):
            ck['model'][name]=fresh.state_dict()[name].clone()
            ck['optimizer']['state'].pop(index,None)
    for g in ck['optimizer']['param_groups']:g['lr']=cfg['ppo']['learning_rate']
    ck.update(config=cfg,history=[],wandb_id=None)
    assert old_actor==actor_sha({k:v for k,v in ck['model'].items() if k.startswith('actor.')})
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix='.stage_',dir=target.parent))
    try:
        save(temp/'latest.pt',ck);shutil.copy2(baseline,temp/'initial.pt')
        atomic_json(temp/'config.json',cfg)
        atomic_json(temp/'provenance.json',{'objective':cfg['objective'],'parent_checkpoint_sha256':sha(source),
            'baseline_sha256':sha(baseline),'stage_start_transitions':ck['learning_transitions'],
            'curriculum_origin_transitions':origin,'actor_sha256':old_actor,
            'actor_adam_preserved':True,'critic_reinitialized_once_at_stage_fork':True,
            'counters_preserved':True,'history':'starts empty for the new objective'})
        os.rename(temp,target)
    finally:
        if temp.exists():shutil.rmtree(temp)
    return ck['learning_transitions']

def probe_checkpoint(checkpoint,baseline,seed,pairs=32,seconds=6.,race=False):
    """Balanced player colors, frozen models, no sampling or gradient updates.

    One game ends at the first actual contact, not a favorable predicted ETA.
    Unopposed trials park the other car far away; races use the frozen parent.
    The same case is repeated with car/team indices rotated by 180 degrees.
    """
    actor,ck,_=model(Path(checkpoint).parent,checkpoint=checkpoint)
    cfg=copy.deepcopy(ck['config']);cfg['predictive']={'enabled':False};dev=device(cfg)
    torch.set_num_threads(cfg['torch_threads']);actor.to(dev).eval()
    other=None
    if race:other,_,_=model(Path(baseline).parent,checkpoint=baseline,dev=dev)
    n=2*pairs;states=drill_states(np.random.default_rng(seed),pairs,moving=race)
    if not race:
        states[:,2,:3]=[3600,4300,17];states[:,2,3:9]=0;states[:,2,15]=0
    worlds=np.empty((n,3,32),np.float32);worlds[0::2]=states
    rotated=states.copy();rotated[:,:,:15]*=np.asarray([-1,-1,1]*5,np.float32)
    rotated[:,[1,2]]=rotated[:,[2,1]];worlds[1::2]=rotated
    colors=np.arange(n)%2
    env=batch(cfg,n=n,seed=seed,seconds=seconds+1)
    for i,w in enumerate(worlds):env.inject(i,w)
    raw=env.observe();ticks=np.zeros(n,np.int64);done=np.zeros(n,bool)
    own=np.zeros(n,bool);opp=own.copy();first=np.full(n,seconds,np.float32)
    neutral=int(np.flatnonzero(np.all(ACTIONS==0,axis=1))[0])
    target=int(round(seconds*120))
    with torch.inference_mode():
        while not done.all():
            ix=np.arange(n);ac=np.full((n,2),neutral,np.int64)
            ac[ix,colors]=actor(torch.as_tensor(raw['obs'][ix,colors],device=dev),torch.as_tensor(raw['mask'][ix,colors],device=dev))[0].argmax(-1).cpu().numpy()
            if race:ac[ix,1-colors]=other(torch.as_tensor(raw['obs'][ix,1-colors],device=dev),torch.as_tensor(raw['mask'][ix,1-colors],device=dev))[0].argmax(-1).cpu().numpy()
            raw=env.step(ac,np.where(done,0,np.maximum(0,target-ticks)))
            active=~done;ticks+=raw['info'][:,3].astype(np.int64)
            touched=raw['info'][:,1:3]>.5
            hit_own=active&touched[ix,colors];hit_opp=active&touched[ix,1-colors]
            hit=hit_own|hit_opp;own|=hit_own;opp|=hit_opp
            first[hit]=ticks[hit]/120
            done|=hit|(ticks>=target)|raw['terminated']
    w=int((own&~opp).sum());l=int((opp&~own).sum());draws=n-w-l
    return {'checkpoint_sha256':sha(checkpoint),'baseline_sha256':sha(baseline),
            'seed':int(seed),'purpose':'discovery skill gate; never held-out promotion',
            'race':race,'games':n,'pairs':pairs,'seconds':seconds,
            'success_rate':float(own.mean()),'median_contact_seconds':float(np.median(first)),
            'wins':w,'draws':draws,'losses':l,'race_score':(w+.5*draws)/n,
            'by_color':[{'color':c,'success_rate':float(own[colors==c].mean())} for c in (0,1)],
            'raw':{'own_first_touch':own.tolist(),'opponent_first_touch':opp.tolist(),'first_contact_seconds':first.tolist()}}

def contact_gate(probe,baseline_probe):
    return (probe['success_rate']>=RECIPE['contact_success_required']
            and probe['median_contact_seconds']<=RECIPE['contact_median_seconds_max']
            and probe['success_rate']>=baseline_probe['success_rate']-.05
            and probe['median_contact_seconds']<=baseline_probe['median_contact_seconds']+.35)

def start(root=None,source=None,steps=5_000_000,chunk_steps=None,max_checks=None):
    """One click trains up to an additional step budget; no infinite sessions."""
    from .train import train
    root=Path(root or ROOT/'runs/contact01');source=Path(source or ROOT/'runs/potential01')
    if not 0<steps<=100_000_000:raise ValueError('Use a positive step budget <=100M')
    chunk_steps=chunk_steps or RECIPE['checkpoint_steps']
    initialize(root,source)
    with lock(root):
        root.joinpath('STOP').unlink(missing_ok=True)
        state=json.loads((root/'curriculum.json').read_text())
        match_reference=None
        if state['stage_index']==2:
            from .match_guard import reference
            match_reference=reference(root,stage_folder(root,2))
        if state['stage_index']==2 and state['probes'] and match_reference is None:
            prior=json.loads((root/state['probes'][-1]).read_text())
            if prior['stage']=='trajectory' and not prior['gate_passed']:
                state['status']='trajectory_gate_failed_paused';atomic_json(root/'curriculum.json',state)
                print('TRAJECTORY_GATE_FAILED: preserving weights; evaluate trajectory and possession before further training.',flush=True)
                report(root);return state
        if state['status']=='match_regression_paused':
            print('MATCH_REGRESSION_PAUSED: pinned reference retained; review the report before more training.',flush=True)
            report(root);return state
        invocation_start=None;checks=0
        while not (root/'STOP').exists():
            index=state['stage_index'];stage=STAGES[index];folder=stage_folder(root,index)
            if not (folder/'latest.pt').is_file():
                previous=root/'baseline.pt' if index==0 else stage_folder(root,index-1)/'latest.pt'
                fork_stage(previous,folder,root/'baseline.pt',stage,state['origin_transitions'])
            ck=load(folder/'latest.pt');count=ck['learning_transitions']
            initial=json.loads((folder/'provenance.json').read_text())['stage_start_transitions']
            invocation_start=count if invocation_start is None else invocation_start
            if count-invocation_start>=steps:break
            cap=RECIPE.get(stage+'_max_steps',100_000_000)
            remaining=cap-(count-initial)
            if remaining<=0:
                state['status']='stage_gate_not_met';break
            goal=count+min(chunk_steps,steps-(count-invocation_start),remaining)
            state.update(status='training',active_folder=str(folder.relative_to(root)),
                         additional_steps=count-state['origin_transitions'])
            atomic_json(root/'curriculum.json',state)
            print('CONTACT_CURRICULUM:',stage,'additional steps',count-state['origin_transitions'],
                  '; next skill check at total',goal,flush=True)
            if (root/'STOP').exists():
                state['status']='paused';break
            reached=train(folder,minutes=90,stop_at_transitions=goal,external_stop_file=root/'STOP')
            state['checkpoints'][stage]={'learning_transitions':reached,'sha256':sha(folder/'latest.pt')}
            state['additional_steps']=reached-state['origin_transitions']
            if reached<goal or (root/'STOP').exists() or (folder/'STOP').exists():
                state['status']='paused';break
            # Discovery seeds are distinct from native training (<0x40000000)
            # and the existing validation panel (0xC0000000 and above).
            seed=0x80000000+len(state['probes'])*7919
            probe=probe_checkpoint(folder/'latest.pt',root/'baseline.pt',seed,
                                   pairs=RECIPE['probe_pairs'],seconds=RECIPE['probe_seconds'])
            baseline=probe_checkpoint(root/'baseline.pt',root/'baseline.pt',seed,
                                      pairs=RECIPE['probe_pairs'],seconds=RECIPE['probe_seconds'])
            probe['baseline_same_cases']=baseline
            passed=contact_gate(probe,baseline);race=None
            if stage=='possession':
                race=probe_checkpoint(folder/'latest.pt',root/'baseline.pt',seed+1,
                                       pairs=RECIPE['probe_pairs'],seconds=RECIPE['probe_seconds'],race=True)
                passed=passed and race['race_score']>=RECIPE['race_score_required']
            output={'stage':stage,'stage_steps':reached-initial,'additional_steps':state['additional_steps'],
                    'contact':probe,'race':race,'gate_passed':bool(passed),
                    'warning':'Discovery gate only, not verified playing strength.'}
            file=root/f'skill_{stage}_{reached:016d}.json';atomic_json(file,output)
            state['probes'].append(file.name);checks+=1
            print('CONTACT_SKILL:',round(probe['success_rate']*100,1),'% touch;',
                  round(probe['median_contact_seconds'],2),'s median; gate',passed,flush=True)
            if stage=='trajectory':
                if match_reference is not None:
                    state['contact_skill_warning']=not bool(passed)
                    state['status']='trajectory_training'
                    from .match_guard import check
                    check(root,folder,state,reached,match_reference)
                else:state['status']='trajectory_training' if passed else 'trajectory_gate_failed_paused'
            elif passed and reached-initial>=RECIPE[stage+'_min_steps']:
                state['stage_index']+=1;state['status']='stage_advanced'
                print('CURRICULUM_ADVANCED:',STAGES[state['stage_index']],flush=True)
            elif reached-initial>=cap:
                state['status']='stage_gate_not_met'
            else:state['status']='more_practice_needed'
            atomic_json(root/'curriculum.json',state)
            if len(state['probes'])==1:report(root)
            if state['status'] in ('stage_gate_not_met','trajectory_gate_failed_paused','match_regression_paused') or (max_checks is not None and checks>=max_checks):break
        if state['status'] not in ('paused','stage_gate_not_met','trajectory_gate_failed_paused','match_regression_paused'):state['status']='step_budget_saved'
        atomic_json(root/'curriculum.json',state)
        print('CURRICULUM_SAVED:',state['status'],'additional steps',state.get('additional_steps',0),flush=True)
        report(root)
        return state

def active(root=None):
    root=Path(root or ROOT/'runs/contact01');s=json.loads((root/'curriculum.json').read_text())
    # A stage may have just passed but its successor has not been forked yet.
    for index in range(s['stage_index'],-1,-1):
        folder=stage_folder(root,index)
        if (folder/'latest.pt').is_file():return folder
    raise FileNotFoundError('No trained curriculum stage exists')

def pause(root=None):
    root=Path(root or ROOT/'runs/contact01')
    if not root.is_dir():raise FileNotFoundError('Curriculum not created')
    (root/'STOP').write_text('pause requested\n')
    for index in range(3):
        folder=stage_folder(root,index)
        if folder.is_dir():(folder/'STOP').write_text('pause requested\n')
    print('CURRICULUM_PAUSE_REQUESTED: completed update will be saved.',flush=True)

def report(root=None):
    from .report import report as stage_report
    root=Path(root or ROOT/'runs/contact01');reports=[]
    for index in range(3):
        folder=stage_folder(root,index)
        if (folder/'latest.pt').is_file():reports.append(stage_report(folder))
    output=ROOT/f'DuelForge_contact01_report_{time.time_ns()}.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for p in root.glob('*.json'):z.write(p,p.name)
        for p in reports:z.write(p,'stage_reports/'+p.name)
        z.write(ROOT/'CONTACT_CURRICULUM.md','CONTACT_CURRICULUM.md')
    print('CURRICULUM_REPORT_READY:',output,flush=True);return output
