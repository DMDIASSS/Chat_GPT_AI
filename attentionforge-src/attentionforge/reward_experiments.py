"""Two bounded reward hypotheses forked from one frozen trained checkpoint."""
import copy,json,os,shutil,tempfile,time
from pathlib import Path
import torch
from .runtime import ROOT,atomic_json,save_checkpoint,sha,source_hashes
from .train import load,lock_run
from .gpu_profile import model_hash


def fork_reward(source,target,saved,*,goal_style=False):
    source=Path(source);target=Path(target)
    if saved['config']['rewards'].get('profile')!='rlgym_simple_v1':raise ValueError('Use a standard-reward laptop01/laptop01_gpu checkpoint as the parent so only the proposed terms change.')
    if target.resolve()==source.resolve():raise ValueError('A reward experiment needs its own run folder')
    if target.exists():raise FileExistsError(f'{target} already exists; it was preserved')
    target.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.reward_fork_',dir=target.parent))
    try:
        payload=copy.deepcopy(saved);original=model_hash(payload['model']);cfg=payload['config'];before=copy.deepcopy(cfg['rewards'])
        cfg['rewards'].update({'profile':'control_shots_v1','possession_rate':.2,'control_radius':1000.,'distance_epsilon':100.,'goal_no_floor':1. if goal_style else 0.,'goal_speed':.5 if goal_style else 0.,'shot_max_age_seconds':6.})
        payload['wandb_id']=None
        for name in payload.get('history',[]):
            if Path(name).name!=name:raise ValueError('Unexpected history checkpoint name')
            (stage/'history').mkdir(exist_ok=True);shutil.copy2(source/'history'/name,stage/'history'/name)
        if (source/'baseline.pt').is_file():shutil.copy2(source/'baseline.pt',stage/'baseline.pt')
        # Pin this exact pre-change actor/critic as the comparison baseline.
        shutil.copy2(source/'latest.pt',stage/'reward_parent.pt')
        save_checkpoint(stage/'latest.pt',payload);atomic_json(stage/'config.json',cfg)
        record={'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'experiment':'control_plus_goal_style' if goal_style else 'control_ratio_only','source_run':str(source.resolve()),'source_checkpoint_sha256':sha(source/'latest.pt'),'copied_model_state_sha256':original,'starting_learning_transitions':saved['learning_transitions'],'starting_updates':saved['updates'],'reward_before':before,'reward_after':cfg['rewards'],'preserved':['model and critic','Adam moments and step values','learning counters','network/observations/actions','PPO settings','history opponents and score estimates'],'new_wandb_run':True,'source_hashes':source_hashes()}
        assert model_hash(payload['model'])==original
        atomic_json(stage/'reward_provenance.json',record);atomic_json(stage/'provenance.json',{'initialization':'fork of trained checkpoint','reward_experiment':record})
        if target.exists():raise FileExistsError(target)
        os.rename(stage,target);return record
    finally:
        if stage.exists():shutil.rmtree(stage)


def setup(source):
    source=Path(source)
    if not (source/'latest.pt').is_file():raise FileNotFoundError(source/'latest.pt')
    targets=[(source.parent/'control01',False),(source.parent/'control_shots01',True)]
    for target,_ in targets:
        if target.exists():raise FileExistsError(f'{target.name} already exists; use its RUN launcher. No existing experiment was overwritten.')
    from . import _attention_native
    if getattr(_attention_native,'reward_version',0)<1:raise RuntimeError('Extract the new native module and restart Python before creating reward experiments')
    with lock_run(source):
        saved=load(source/'latest.pt',torch.device('cpu'));before=sha(source/'latest.pt')
        for target,style in targets:
            record=fork_reward(source,target,saved,goal_style=style)
            print('REWARD_EXPERIMENT_READY:',target,flush=True)
            print('PARENT_MODEL_HASH:',record['copied_model_state_sha256'],'; inherited transitions:',saved['learning_transitions'],flush=True)
        assert sha(source/'latest.pt')==before
    print('Use CONTROL_RUN.bat first. CONTROL_SHOTS_RUN.bat is the second comparison. Run one trainer at a time.',flush=True)
