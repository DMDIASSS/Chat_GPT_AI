"""Bounded no-boost ground-flip experiment; no scripted match controller."""
import copy,json,os,shutil,tempfile,time,zipfile
from pathlib import Path
import numpy as np
import torch
from .runtime import ROOT,batch,model,device,load,save,sha,atomic_json,lock
from .acquisition_experiment import fork_stage
from .ground_flip import GroundFlipBatch,drill_states,RECIPE,VERSION,NEUTRAL
from .observation import ACTIONS

DRIVE=int(np.flatnonzero((ACTIONS[:,0]==1)&(ACTIONS[:,1]==0)&(ACTIONS[:,5]==0)&(ACTIONS[:,6]==0)&(ACTIONS[:,7]==0))[0])
JUMP=int(np.flatnonzero((ACTIONS[:,5]==1)&(ACTIONS[:,2]==0)&(ACTIONS[:,4]==0)&(ACTIONS[:,6]==0))[0])
DODGE=int(np.flatnonzero((ACTIONS[:,5]==1)&(ACTIONS[:,2]==-1)&(ACTIONS[:,4]==0)&(ACTIONS[:,6]==0))[0])

def install_cases(env,worlds,colors):
    """Initial reset only, used by frozen probes and physics-control tests."""
    for i,w in enumerate(worlds):env.env.inject(i,w)
    env.colors[:]=colors;env.trial_ticks[:]=0;env.elapsed[:]=0;env.seen[:]=False;env.flipped[:]=False
    env.raw=env._mask(env.env.observe());ix=np.arange(len(worlds))
    env.initial_distance[:]=np.linalg.norm(worlds[ix,colors+1,:3]-worlds[:,0,:3],axis=-1)

def balanced_cases(seed,pairs):
    w,_=drill_states(np.random.default_rng(seed),pairs,colors=np.zeros(pairs,np.int64))
    out=np.empty((2*pairs,3,32),np.float32);out[0::2]=w
    rotated=w.copy();rotated[:,:,:15]*=np.array([-1,-1,1]*5,np.float32)
    rotated[:,[1,2]]=rotated[:,[2,1]];out[1::2]=rotated
    return out,np.arange(2*pairs)%2

def calibrated_controls(cfg,kind='flip',seed=0xE1100000,pairs=32,jump_at=14,jump_hold=1):
    """Test-only physical witnesses, never labels or controls in training/watch."""
    c=copy.deepcopy(cfg);c['flip_drill']=copy.deepcopy(RECIPE)
    from .acquisition import stage_config
    if not c.get('acquisition'):c=stage_config(c,'trajectory')
    e=GroundFlipBatch(batch(c,n=2*pairs,seconds=5),c,seed,force=True)
    w,col=balanced_cases(seed,pairs);install_cases(e,w,col)
    n=len(w);ix=np.arange(n);done=np.zeros(n,bool);success=done.copy();touch=done.copy();physical=done.copy();max_boost=0.;max_control_boost=0.
    for t in range(RECIPE['ticks']//8):
        a=np.full((n,2),NEUTRAL,np.int64);choice=DRIVE
        if kind!='drive':
            if jump_at<=t<jump_at+jump_hold:choice=JUMP
            elif kind=='flip' and jump_at+jump_hold+1<=t<jump_at+jump_hold+2:choice=DODGE
            elif t>=jump_at+jump_hold:choice=NEUTRAL
        a[ix,col]=choice
        raw=e.step(a,np.where(done,0,8));d=raw['flip_drill'];active=~done
        physical|=active&d['flipped'];success|=active&d['success'];touch|=active&(raw['info'][ix,col+1]>.5)
        max_boost=max(max_boost,float(raw['final_world'][ix,col+1,15].max()))
        max_control_boost=max(max_control_boost,float(raw['final_world'][ix,col+1,27].max()))
        done|=d['completed']
        if done.all():break
    return {'kind':kind,'trials':n,'contacts':int(touch.sum()),'successes':int(success.sum()),
            'physical_flips':int(physical.sum()),'peak_active_car_boost':max_boost,
            'peak_active_boost_control':max_control_boost,'jump_at_decision':jump_at,'jump_hold_decisions':jump_hold}

def calibration(cfg,pairs=32):
    drive=calibrated_controls(cfg,'drive',pairs=pairs)
    jump=calibrated_controls(cfg,'jump',pairs=pairs)
    flip=calibrated_controls(cfg,'flip',pairs=pairs)
    passed=drive['contacts']==0 and jump['contacts']==0 and flip['successes']==2*pairs and flip['peak_active_car_boost']==0 and flip['peak_active_boost_control']==0
    if not passed:raise RuntimeError('Ground-flip physics calibration failed. No training started; report these controls.')
    return {'passed':True,'recipe':RECIPE,'drive':drive,'single_jump':jump,'jump_release_dodge':flip,
            'scope':'Concrete physical witnesses, not a proof over every imaginable control sequence. Calibrated against straight full throttle and jump controls.'}

def setup(root,source):
    root=Path(root);source=Path(source)
    if root.exists():
        state=json.loads((root/'curriculum.json').read_text())
        if state['version']!=VERSION or sha(root/'baseline.pt')!=state['source_sha256']:raise ValueError('Existing flip experiment identity changed; preserved')
        return root/'03_trajectory'
    root.parent.mkdir(parents=True,exist_ok=True);temp=Path(tempfile.mkdtemp(prefix='.flip_setup_',dir=root.parent))
    try:
        shutil.copy2(source,temp/'baseline.pt');ck=load(source);folder=temp/'03_trajectory'
        fork_stage(temp/'baseline.pt',folder,temp/'baseline.pt','trajectory',ck['learning_transitions'])
        child=load(folder/'latest.pt');c=child['config']
        for key in ('held_ball','air_recovery'):c.pop(key,None)
        if 'jump_bootstrap' in c:c['parent_jump_bootstrap']=c.pop('jump_bootstrap')
        c['objective']='no_boost_ground_flip_deadline_v1';c['flip_drill']=copy.deepcopy(RECIPE)
        c['acquisition'].update(drill_fraction=0,contact_ground_only=False)
        c['wandb']['name']='flip01_no_boost_ground_deadline';child['config']=c;child.pop('held_curriculum',None)
        (folder/'history').mkdir(exist_ok=True)
        save(folder/'history/source_reference.pt',{'model':ck['model'],'config':ck['config'],'learning_transitions':ck['learning_transitions']})
        child['history']=['source_reference.pt'];save(folder/'latest.pt',child);atomic_json(folder/'config.json',c)
        provenance=json.loads((folder/'provenance.json').read_text());provenance.update(objective=c['objective'],
            history='Frozen source reference seeded; snapshots rotate normally',parked_drill_rows='excluded from PPO')
        atomic_json(folder/'provenance.json',provenance)
        atomic_json(temp/'curriculum.json',{'version':VERSION,'stage_index':2,'status':'ready','source_sha256':sha(source),
           'origin_transitions':ck['learning_transitions'],'recipe':RECIPE,'promotion':'none'})
        os.rename(temp,root)
    finally:
        if temp.exists():shutil.rmtree(temp)
    return root/'03_trajectory'

def source_checkpoint():
    folder=ROOT/'runs/jump01/03_trajectory';resultfile=ROOT/'runs/jump01/bootstrap_result.json'
    if not (folder/'latest.pt').is_file() or not resultfile.is_file():
        raise FileNotFoundError('Tested jump01 candidate required. Finish 50_BOOTSTRAP_JUMP_SKILL.bat first. No source was substituted.')
    r=json.loads(resultfile.read_text())
    if sha(folder/'latest.pt')!=r['candidate_sha256'] or r['heldout_candidate']['contact_rate']<.5 or r['matches']['score_interval_95'][1]<.5:
        raise ValueError('Source hash or jump/match retention checks differ; original files preserved')
    return folder/'latest.pt'

def probe(checkpoint,seed=0xE1300000,pairs=32):
    actor,ck,_=model(Path(checkpoint).parent,checkpoint=checkpoint);c=copy.deepcopy(ck['config'])
    from .acquisition import stage_config
    c=stage_config(c,'trajectory');c.pop('held_ball',None);c.pop('air_recovery',None);c['flip_drill']=copy.deepcopy(RECIPE)
    dev=device(c);torch.set_num_threads(c['torch_threads']);actor.to(dev)
    e=GroundFlipBatch(batch(c,n=2*pairs,seconds=5),c,seed,force=True)
    w,col=balanced_cases(seed,pairs);install_cases(e,w,col);raw=e.observe();n=len(w);ix=np.arange(n)
    done=np.zeros(n,bool);success=done.copy();flipped=done.copy();penalties=np.zeros(n,np.float32);distance=np.zeros(n,np.float32);ticks=np.zeros(n,np.int64)
    with torch.inference_mode():
        while not done.all():
            a=np.full((n,2),NEUTRAL,np.int64)
            a[ix,col]=actor(torch.as_tensor(raw['obs'][ix,col],device=dev),torch.as_tensor(raw['mask'][ix,col],device=dev))[0].argmax(-1).cpu().numpy()
            raw=e.step(a,np.where(done,0,8));r=raw['flip_drill'];completed=r['completed']&~done
            flipped|=(~done)&r['flipped'];success|=completed&r['success'];penalties[completed]=r['penalty'][completed]
            distance[completed]=r['distance'][completed];ticks[completed]=r['ticks'][completed];done|=completed
    return {'checkpoint_sha256':sha(checkpoint),'seed':seed,'trials':n,'pairs':pairs,'success_rate':float(success.mean()),
       'flip_rate':float(flipped.mean()),'mean_terminal_penalty':float(penalties.mean()),
       'mean_final_distance':float(distance.mean()),'recipe':RECIPE,
       'raw':{'success':success.tolist(),'physical_flip':flipped.tolist(),'penalty':penalties.tolist(),'distance':distance.tolist(),'ticks':ticks.tolist()},
       'scope':'No-boost ground drill, balanced colors. Not a normal match or playing-strength certification.'}

def report(root=None):
    from .report import report as stage_report
    root=Path(root or ROOT/'runs/flip01');stage=stage_report(root/'03_trajectory');out=ROOT/f'DuelForge_flip01_report_{time.time_ns()}.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for f in root.glob('*.json'):z.write(f,f.name)
        z.write(stage,'stage_reports/'+stage.name);z.write(ROOT/'GROUND_FLIP.md','GROUND_FLIP.md');z.write(ROOT/'tools/ground_flip.py','source/tools/ground_flip.py')
    print('FLIP_REPORT_READY:',out,flush=True);return out

def start(root=None,source=None,steps=500_000,pairs=32,games=200,warmup_updates=300):
    from .train import train
    from .evaluate import evaluate
    root=Path(root or ROOT/'runs/flip01')
    if not 0<steps<=2_000_000:raise ValueError('Use a bounded 1..2M-step trial')
    folder=setup(root,source or source_checkpoint()) if not root.exists() else setup(root,root/'baseline.pt')
    with lock(root):
        root.joinpath('STOP').unlink(missing_ok=True);count=load(folder/'latest.pt')['learning_transitions']
        prior=sorted(root.glob('flip_result_*.json'))
        if prior:
            r=json.loads(prior[-1].read_text())
            if r['candidate_sha256']==sha(folder/'latest.pt') and (r['clear_match_regression'] or r['after']['success_rate']<.5):
                print('FLIP_RETENTION_PAUSED: match regression or greedy drill success below 50%; source and warm-up pin preserved. Review report.',flush=True);report(root);return
        atomic_json(root/'physics_calibration.json',calibration(load(folder/'latest.pt')['config']))
        atomic_json(root/f'flip_before_{count}.json',probe(folder/'latest.pt',seed=0xE1200000,pairs=pairs))
        if warmup_updates:
            warmup=root/'flip_warmup_result.json'
            origin=json.loads((root/'curriculum.json').read_text())['origin_transitions']
            if count==origin:
                from .flip_bootstrap import fit
                if not warmup.is_file():accepted=fit(root,updates=warmup_updates)
                else:
                    wr=json.loads(warmup.read_text())
                    if wr['candidate_sha256']!=sha(folder/'latest.pt'):raise ValueError('Warm-up candidate changed; no guessed resumption')
                    accepted=wr['heldout']['success_rate']>=.5 and wr['normal_kl']<=.05
                if not accepted:
                    state=json.loads((root/'curriculum.json').read_text());state.update(status='warmup_not_passed',additional_steps=0)
                    atomic_json(root/'curriculum.json',state)
                    print('FLIP_WARMUP_PAUSED: warm-up did not pass the greedy contact/KL gate. No RL steps added. Send report.',flush=True)
                    report(root);return
        state=json.loads((root/'curriculum.json').read_text());state.update(status='training');atomic_json(root/'curriculum.json',state)
        print('GROUND_FLIP: +',steps,'learner transitions; 2240-2260 units, 2.2s, zero starting boost and boost disabled. 50% drill arenas / 50% normal.',flush=True)
        reached=train(folder,minutes=90,stop_at_transitions=count+steps,external_stop_file=root/'STOP')
        if reached>=count+steps and not (root/'STOP').exists() and not (folder/'STOP').exists():
            after=probe(folder/'latest.pt',seed=0xE1300000,pairs=pairs);baseline=probe(root/'baseline.pt',seed=0xE1300000,pairs=pairs)
            matches=evaluate(folder,games_per_context=games,seconds=100,contexts=['match'])
            atomic_json(root/f'flip_result_{reached}.json',{'candidate_sha256':sha(folder/'latest.pt'),'after':after,'source_same_cases':baseline,
              'matches':matches['overall'],'clear_match_regression':bool(matches['overall']['score_interval_95'][1]<.5),'promotion':'none'})
        state.update(status='paused',learning_transitions=reached,additional_steps=reached-state['origin_transitions']);atomic_json(root/'curriculum.json',state);report(root)
