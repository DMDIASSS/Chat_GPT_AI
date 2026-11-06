"""Real warm resume with checkpointed opponent sampling; not a strength test."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import zipfile
import torch
from stable_baselines3 import PPO
from nova.research import fork,report,backup,run_path
from nova.selector_diagnostics import protected_hashes
from nova.opponent_sampling import configure,ConcessionSampler,policy_for
from nova.triad_selector import train,Gate
from nova.core import atomic_json,sha256

torch.set_num_threads(1);source=run_path('ci_selector_six');before=protected_hashes(source)
run=fork('ci_selector_six','ci_selector_adaptive')
cfg=json.loads((run/'config.json').read_text());original_config=sha256(run/'config.json')
original_champion=sha256(run/'champion.pt');fusion=sha256(run/'frozen_fusion.pt')
start=PPO.load(run/'full.zip',device='cpu').num_timesteps
configure('ci_selector_adaptive',True)
train('ci_selector_adaptive',steps=512,forever=False,wandb='off')
first=PPO.load(run/'full.zip',device='cpu')
state=first.opponent_sampling_state
assert first.num_timesteps==start+512 and state['episodes']>0
assert state['updates']>0 and sum(map(len,state['records'].values()))>0
restored=ConcessionSampler(cfg['selector_opponents'],policy_for(run,cfg['selector_opponents']),state)
assert restored.state()==state
assert sha256(run/'config.json')==original_config
# A display file is not an authoritative recovery source.
atomic_json(run/'opponent_sampling.json',dict(episodes=999999999,weights={'corrupt':1}))
train('ci_selector_adaptive',steps=512,forever=False,wandb='off')
second=PPO.load(run/'full.zip',device='cpu');summary=json.loads((run/'opponent_sampling.json').read_text())
assert second.num_timesteps==start+1024
assert state['episodes']<second.opponent_sampling_state['episodes']<999999999
assert summary['episodes']==second.opponent_sampling_state['episodes']
assert all(.05-1e-12<=x<=.30+1e-12 for x in summary['weights'].values())
sessions=list((run/'research/sessions').glob('*.json'))
assert any(json.loads(p.read_text()).get('opponent_sampling_policy',{}).get('enabled') for p in sessions)
with zipfile.ZipFile(report('ci_selector_adaptive')) as z:
    assert {'opponent_sampling_policy.json','opponent_sampling.json'}<=set(z.namelist())
out=backup('ci_selector_adaptive');assert (out/'opponent_sampling_policy.json').is_file()
configure('ci_selector_adaptive',False)
train('ci_selector_adaptive',steps=512,forever=False,wandb='off')
third=PPO.load(run/'full.zip',device='cpu')
assert third.num_timesteps==start+1536 and third.opponent_sampling_state is None
assert json.loads((run/'status.json').read_text())['opponent_sampling']=={'enabled':False}
assert sha256(run/'champion.pt')==original_champion and sha256(run/'frozen_fusion.pt')==fusion
assert protected_hashes(source)==before
Gate(run/'latest.pt','octane')
print('ACTUAL_ADAPTIVE_OPPONENT_ENABLE_TRAIN_RESUME_DISABLE_PASS')
