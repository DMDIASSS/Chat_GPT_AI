"""Real frozen-Fusion selection/refinement/four-expert smoke, not strength evidence."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import torch
from nova.core import ROOT,atomic_json
from nova.training import load_config
from nova.chronos import ChronosEnv,CHRONOS_CONTRACT
from nova.chronos_training import new_chronos_model,export_chronos_actor
from nova.fusion_selection import select_best,prepare_refinement,train_refinement,create_four,parameter_fingerprint
from nova.triad_selector import train,Gate,FOUR_NAMES
from nova.selector_diagnostics import diagnose

torch.set_num_threads(1)
fixture=ROOT/'runs/fusion_ci';fixture.mkdir(parents=True,exist_ok=True)
cfg=load_config(ROOT/'configs/chronos.json');cfg.update(workers=1,device='cpu')
cfg['ppo'].update(n_steps=16,batch_size=16,n_epochs=1)
cfg['chronos']['critic_warmup_updates']=0
cfg['env'].update(episode_seconds=.5,no_touch_seconds=1)
atomic_json(fixture/'config.json',cfg);atomic_json(fixture/'fusion_state.json',dict(phase='complete'))
env=ChronosEnv(cfg,opponent='scorer')
try:
    model=new_chronos_model(cfg,env);initial=parameter_fingerprint(model.policy.actor)
    model.learn(32);export_chronos_actor(model,fixture/'snapshots/step_000000000032.lt')
    assert parameter_fingerprint(model.policy.actor)!=initial
    model.learn(32,reset_num_timesteps=False);export_chronos_actor(model,fixture/'snapshots/step_000000000064.lt')
finally:env.close()
select_best('fusion_ci',pairs=1,seconds=1,confirmation_pairs=1,confirmation_seconds=1)
refine=prepare_refinement('fusion_refine_ci')
cfg=json.loads((refine/'config.json').read_text());cfg['fusion_refinement']['target_decisions']=32
cfg['workers']=1;cfg['chronos']['guard']['enabled']=False
atomic_json(refine/'config.json',cfg)
train_refinement('fusion_refine_ci',wandb='off')
run=create_four('ci_selector_four',refinement='fusion_refine_ci')
for target in (512,1024):
    train('ci_selector_four',steps=512,forever=False,wandb='off')
    assert json.loads((run/'status.json').read_text())['timesteps']==target
gate=Gate(run/'latest.pt');assert gate.names==FOUR_NAMES and gate.fusion_path.is_file()
diagnose('ci_selector_four',pairs=1,seconds=1,body_check=False)
print('ACTUAL_FUSION_SELECTION_REFINEMENT_FOUR_EXPERT_PASS')
