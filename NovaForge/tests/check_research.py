"""Actual pinned-teacher fork/resume check, run after CI creates ci_selector."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
from nova import research,triad_selector as selector
from nova.core import sha256

source=selector.RUNS/'ci_selector'
names=('full.zip','latest.pt','initial.pt','champion.pt')
before={n:sha256(source/n) for n in names}
run=research.fork('ci_selector','ci_ablation','field_only',811)
start=json.loads((run/'fork.json').read_text())['start_timesteps']
for expected in (start+512,start+1024):
    selector.train('ci_ablation',steps=512,forever=False,wandb='off')
    assert json.loads((run/'status.json').read_text())['timesteps']==expected
assert len(list((run/'logs').glob('*/progress.csv')))==2
assert before=={n:sha256(source/n) for n in names}
assert json.loads((run/'config.json').read_text())['objective']['distance']==0
research.backup('ci_ablation')
research.report('ci_ablation')
print('ACTUAL_RESEARCH_FORK_RESUME_PASS')
