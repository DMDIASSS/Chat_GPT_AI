"""Real unattended segment; exports are local and source/Fusion remain intact."""
from pathlib import Path
import json,sys,zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nova.autopilot import run as unattended,maintenance
from nova.research import fork,run_path
from nova.selector_diagnostics import protected_hashes
from nova.core import sha256
from nova.triad_selector import selector_meta,Gate

source=run_path('ci_selector_six');before=protected_hashes(source)
run=fork('ci_selector_six','ci_selector_autopilot')
frozen=sha256(run/'frozen_fusion.pt');champion=sha256(run/'champion.pt');start=selector_meta(run/'full.zip')['timesteps']
unattended('ci_selector_autopilot',once=True,steps=512,wandb='off')
status=json.loads((run/'status.json').read_text());state=json.loads((run/'autopilot.json').read_text())
assert status['state']=='finished' and status['timesteps']==start+512
assert status['throughput']['throughput/training_decisions_per_second']>0
assert status['throughput']['throughput/effective_decisions_per_second']>0
assert not state['artifact_errors'] and state['champion_export']['sha256']==champion
assert Path(state['champion_export']['toml']).is_file()
with zipfile.ZipFile(state['report_zip']) as z:
    assert json.loads(z.read('status.json'))['state']=='finished'
    assert 'opponent_sampling.json' in z.namelist()
Gate(Path(state['champion_export']['folder'])/'selector.pt','octane')
assert sha256(run/'frozen_fusion.pt')==frozen and sha256(run/'champion.pt')==champion
assert before==protected_hashes(source)
print('ACTUAL_AUTOPILOT_BACKUP_RESUME_REPORT_EXPORT_PASS')
