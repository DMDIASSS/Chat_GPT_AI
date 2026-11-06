"""Real frozen experts and native matches; this verifies plumbing, not strength."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import zipfile
from nova.selector_routing import evaluate
from nova.selector_diagnostics import protected_hashes
from nova.research import run_path

run=run_path('ci_selector_four');before=protected_hashes(run)
path=evaluate('ci_selector_four',pairs=1,seconds=1)
assert before==protected_hashes(run)
with zipfile.ZipFile(path) as z:
    assert z.testzip() is None
    d=json.loads(z.read('routing.json'))
    assert len(d['trials'])==5 and sum(map(len,d['trials'].values()))==40
    for label in ('latest_sampled','initial_sampled'):
        rows=d['trials'][label]
        assert all(sum(x['free_choices'].values())==2 for x in rows)
        assert all(sum(x['expert_decisions'].values())==15 for x in rows)
        choices={name:sum(x['free_choices'][name] for x in rows) for name in d['experts']}
        assert sum(v>0 for v in choices.values())>=2
    assert d['protected_run_files_unchanged']
print('ACTUAL_FOUR_ROUTING_PASS')
