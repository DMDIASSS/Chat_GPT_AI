"""Native six-way integration. Short runs establish execution, not strength."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import zipfile
import torch
from nova.core import atomic_json,sha256
from nova.six_selector import create,diagnose
from nova.triad_selector import train,Gate,SIX_NAMES,SIX_CONTRACT
from nova.research import run_path,report,backup
from nova.selector_diagnostics import protected_hashes

torch.set_num_threads(1)
source=run_path('ci_selector_four');before=protected_hashes(source)
run=create('ci_selector_six','ci_selector_four')
assert before==protected_hashes(source)
assert sha256(run/'frozen_fusion.pt')==sha256(source/'frozen_fusion.pt')
cfg=json.loads((run/'config.json').read_text());assert cfg['env']['learner_hitbox']=='octane'
assert 'ripple' not in cfg['selector_experts'] and 'ripple' not in cfg['selector_opponents']
cfg['env'].update(episode_seconds=.5,no_touch_seconds=1);atomic_json(run/'config.json',cfg)
teacher=sha256(run/'frozen_fusion.pt')
for expected in (512,1024):
    train('ci_selector_six',steps=512,forever=False,wandb='off')
    assert json.loads((run/'status.json').read_text())['timesteps']==expected
    assert sha256(run/'frozen_fusion.pt')==teacher
gate=Gate(run/'latest.pt','octane');assert gate.names==SIX_NAMES
assert gate.context.observation(__import__('numpy').zeros(225)).shape==(240,)
assert json.loads((run/'full.zip.json').read_text())['contract']==SIX_CONTRACT
from nova.chronos_league import match_suite
from nova.triad_selector import Runner
rows,old=match_suite(cfg,Runner(run/'latest.pt','octane'),Runner(run/'initial.pt','octane'),1,1,511000001,run/'CHECK_STOP')
assert len(rows)==len(old)==14
path=diagnose('ci_selector_six',pairs=1,seconds=1)
with zipfile.ZipFile(path) as z:
    data=json.loads(z.read('diagnostic.json'))
    assert sum(map(len,data['trials'].values()))==98 and data['protected_run_files_unchanged']
    audit=data['free_choice_probabilities'];decisions=sum(data['latest_expert_decisions'].values())
    assert audit['latest']['free_choices']+audit['forced_decisions_excluded']==decisions
with zipfile.ZipFile(report('ci_selector_six')) as z:assert 'latest_six_diagnostic.json' in z.namelist()
out=backup('ci_selector_six');assert sha256(out/'frozen_fusion.pt')==teacher
print('ACTUAL_SIX_CREATE_TRAIN_RESUME_DIAGNOSTIC_BACKUP_PASS')
