"""Actual diagnostic pipeline with pinned models; short games are not strength tests."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import zipfile
from nova.selector_diagnostics import diagnose,protected_hashes
from nova.research import run_path,report

run=run_path('ci_selector');before=protected_hashes(run)
path=diagnose('ci_selector',pairs=1,seconds=1)
assert before==protected_hashes(run)
with zipfile.ZipFile(path) as z:
    assert z.testzip() is None
    data=json.loads(z.read('diagnostic.json'))
    assert len(data['conditions'])==6 and sum(len(r) for r in data['trials'].values())==48
    audit=data['free_choice_probabilities'];n=sum(data['latest_expert_decisions'].values())
    assert 0<audit['latest']['free_choices']<n
    assert audit['latest']['free_choices']+audit['forced_decisions_excluded']==n
    assert abs(sum(audit['latest']['probability_mean'].values())-1)<1e-6
with zipfile.ZipFile(report('ci_selector')) as z:assert 'latest_diagnostic.json' in z.namelist()
print('ACTUAL_SELECTOR_DIAGNOSTICS_PASS')
