import copy,json,os,shutil,tempfile,time,zipfile
from pathlib import Path
import numpy as np
import torch
from .runtime import ROOT,load,save,sha,atomic_json,batch,model,device,lock
from .acquisition_experiment import fork_stage
from .air_recovery import air_states,elevated_hits

def setup(root,source):
    root=Path(root);source=Path(source)
    if root.exists():
        state=json.loads((root/'curriculum.json').read_text())
        if state['version']!='air-contact-v1' or sha(root/'baseline.pt')!=state['source_sha256']:raise ValueError('Air experiment identity differs; preserved')
        return root/'03_trajectory'
    root.parent.mkdir(parents=True,exist_ok=True)
    with lock(source.parent):
        stage=Path(tempfile.mkdtemp(prefix='.air_fork_',dir=root.parent))
        try:
            shutil.copy2(source,stage/'baseline.pt');ck=load(source);folder=stage/'03_trajectory'
            fork_stage(stage/'baseline.pt',folder,stage/'baseline.pt','trajectory',ck['learning_transitions'])
            child=load(folder/'latest.pt');c=child['config']
            c['objective']='elevated_contact_rehabilitation_v1';c['acquisition'].update(drill_fraction=0.,contact_ground_only=False)
            c['air_recovery']={'version':'air-contact-v1','fraction':.4,'seconds':1.4,'approach_weight':.02,'contact_bonus':1.}
            c['ppo']['entropy']=.01;c['wandb']['name']='air01_jump_recovery'
            (folder/'history').mkdir(exist_ok=True)
            save(folder/'history/source_reference.pt',{'model':ck['model'],'config':ck['config'],'learning_transitions':ck['learning_transitions']})
            child['history']=['source_reference.pt']
            child['config']=c;save(folder/'latest.pt',child);atomic_json(folder/'config.json',c)
            atomic_json(stage/'curriculum.json',{'version':'air-contact-v1','stage_index':2,'origin_transitions':ck['learning_transitions'],
                'source_sha256':sha(stage/'baseline.pt'),'status':'ready','active_folder':'03_trajectory',
                'scope':'Separate bounded air-contact experiment. Not a replacement for the confirmed match reference.'})
            os.rename(stage,root)
        finally:
            if stage.exists():shutil.rmtree(stage)
    return root/'03_trajectory'

def probe(checkpoint,seed=0x90001000,pairs=32):
    actor,ck,_=model(Path(checkpoint).parent,checkpoint=checkpoint);c=copy.deepcopy(ck['config']);c['predictive']={'enabled':False}
    dev=device(c);torch.set_num_threads(c['torch_threads']);actor.to(dev)
    n=2*pairs;worlds=np.empty((n,3,32),np.float32);w=air_states(np.random.default_rng(seed),pairs)
    w[:,2,:3]=[3600,4300,17];w[:,2,3:9]=0;w[:,2,15]=0
    worlds[0::2]=w;rotated=w.copy();rotated[:,:,:15]*=np.array([-1,-1,1]*5);rotated[:,[1,2]]=rotated[:,[2,1]];worlds[1::2]=rotated
    e=batch(c,n=n,seed=seed,seconds=3)
    for i,state in enumerate(worlds):e.inject(i,state)
    raw=e.observe();colors=np.arange(n)%2;ix=np.arange(n);ticks=np.zeros(n,np.int64);success=np.zeros(n,bool);jumped=success.copy();lifted=success.copy();target=168
    from .observation import ACTIONS
    with torch.inference_mode():
        while (ticks<target).any():
            ac=np.full((n,2),10,np.int64)
            ac[ix,colors]=actor(torch.as_tensor(raw['obs'][ix,colors],device=dev),torch.as_tensor(raw['mask'][ix,colors],device=dev))[0].argmax(-1).cpu().numpy()
            active=ticks<target;jumped|=active&(ACTIONS[ac[ix,colors],5]>.5)
            before=raw['world'];raw=e.step(ac,np.maximum(0,target-ticks));ticks+=raw['info'][:,3].astype(np.int64)
            success|=active&elevated_hits(before,raw)[ix,colors];lifted|=active&(raw['final_world'][ix,colors+1,2]>65)
    return {'checkpoint_sha256':sha(checkpoint),'seed':seed,'pairs':pairs,'trials':n,'duration':1.4,
            'elevated_contact_rate':float(success.mean()),'jump_used_rate':float(jumped.mean()),'lifted_rate':float(lifted.mean()),
            'raw':{'elevated_contact':success.tolist(),'jump_used':jumped.tolist(),'lifted':lifted.tolist()},
            'scope':'Discovery skill check with full native masks; real contacts above 220 and car center above 65. Not general aerial mastery.'}

def report(root):
    from .report import report as stage_report
    root=Path(root);stage=stage_report(root/'03_trajectory');out=ROOT/f'DuelForge_air01_report_{time.time_ns()}.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for f in root.glob('*.json'):z.write(f,f.name)
        z.write(stage,'stage_reports/'+stage.name);z.write(ROOT/'AIR_RECOVERY.md','AIR_RECOVERY.md')
    print('AIR_REPORT_READY:',out,flush=True);return out

def start(root=None,source=None,steps=500_000):
    from .train import train
    from .evaluate import evaluate
    root=Path(root or ROOT/'runs/air01')
    if not 0<steps<=2_000_000:raise ValueError('Use a bounded 1..2M step experiment')
    if not root.exists() and source is None:
        from .match_guard import reference
        old=ROOT/'runs/contact01';folder=old/'03_trajectory';ref=reference(old,folder)
        if ref is None:raise RuntimeError('Confirmed trajectory reference required; no arbitrary weights substituted')
        source=folder/ref['actor_path']
    folder=setup(root,source) if not root.exists() else setup(root,root/'baseline.pt')
    with lock(root):
        results=sorted(root.glob('air_result_*.json'))
        if results:
            last=json.loads(results[-1].read_text());after=last.get('after',{})
            if after.get('checkpoint_sha256')==sha(folder/'latest.pt') and after.get('elevated_contact_rate')==0 and after.get('jump_used_rate')==0:
                state=json.loads((root/'curriculum.json').read_text());state['status']='air_recovery_failed_jump_gate'
                atomic_json(root/'curriculum.json',state)
                print('AIR_RECOVERY_STOPPED: the last trial learned no jump/contact skill. Preserve results; use 50_BOOTSTRAP_JUMP_SKILL.bat.',flush=True)
                report(root);return state
        root.joinpath('STOP').unlink(missing_ok=True)
        ck=load(folder/'latest.pt');count=ck['learning_transitions'];target=count+steps
        # Compare source and student on exactly the same discovery cases.
        before=probe(folder/'latest.pt');atomic_json(root/f'air_before_{count}.json',before)
        if before['jump_used_rate']>=.5 and before['elevated_contact_rate']>=.5:
            state=json.loads((root/'curriculum.json').read_text());state.update(status='air_skill_present_in_controlled_probe',learning_transitions=count,additional_steps=count-state['origin_transitions'])
            atomic_json(root/'curriculum.json',state)
            print('AIR_SKILL_PRESENT: actor can jump and contact these raised targets. No training performed; inspect match usage rather than forcing extra jumps.',flush=True)
            report(root);return state
        reached=train(folder,minutes=90,stop_at_transitions=target,external_stop_file=root/'STOP')
        if reached>=target and not (folder/'STOP').exists() and not (root/'STOP').exists():
            after=probe(folder/'latest.pt');baseline=probe(root/'baseline.pt')
            matches=evaluate(folder,games_per_context=200,seconds=100,contexts=['match'])
            atomic_json(root/f'air_result_{reached}.json',{'before':before,'after':after,'frozen_source':baseline,'matches':matches['overall'],
                'increased_elevated_contact':bool(after['elevated_contact_rate']>baseline['elevated_contact_rate']),
                'clear_match_regression':bool(matches['overall']['score_interval_95'][1]<.5),
                'promotion':'none; review aerial and match results together'})
        state=json.loads((root/'curriculum.json').read_text());state.update(status='paused',learning_transitions=reached,
             additional_steps=reached-state['origin_transitions']);atomic_json(root/'curriculum.json',state)
        report(root);return state
