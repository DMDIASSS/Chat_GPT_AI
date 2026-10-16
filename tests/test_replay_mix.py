"""Prevent a nominal mixed run from silently training without actual 3v3 data."""
import json
import numpy as np
import pytest
from audit_replay_mix import audit
from slater_v041_core import atomic_json,sha256


def dataset(folder,missing=None):
    sources=[]
    for split in ('train','validation','test'):
        for number in range(2):
            path=folder/f'{split}_{number}.npz'
            np.savez_compressed(path,players=np.full(10,2 if split==missing else 6,np.uint8))
            sources.append({'group':f'{split}-{number}','split':split,'samples':10,'shard':str(path),'sha256':sha256(path)})
    atomic_json(folder/'manifest.json',{'schema':'replay-il-v2-raw','sources':sources})


def test_format_audit_checks_actual_shards_and_does_not_score_heldout_labels(tmp_path):
    dataset(tmp_path);report=audit(tmp_path)
    assert report['verified_3v3_coverage']
    assert report['matches_by_split_and_format']=={s:{'3v3':2} for s in ('train','validation','test')}
    assert report['samples_by_split_and_format']['test']=={'3v3':20}


def test_format_audit_stops_when_3v3_was_rejected_or_lacks_a_split(tmp_path):
    dataset(tmp_path,missing='validation')
    with pytest.raises(ValueError,match='Missing: validation'):audit(tmp_path)
    report=json.loads((tmp_path/'format_audit.json').read_text())
    assert not report['verified_3v3_coverage'] and report['insufficient_3v3_splits']==['validation']


def test_mixed_launcher_audits_before_training_and_preserves_custom_paths(tmp_path,monkeypatch):
    import replay_il_mixed as mixed
    calls=[]
    def run(command,**kwargs):
        calls.append(command)
        return type('Result',(),{'returncode':0})()
    def verify(path):
        assert len(calls)==1 and str(path)==str(tmp_path)
        calls.append('audit')
    monkeypatch.setattr(mixed.subprocess,'run',run);monkeypatch.setattr(mixed,'audit',verify)
    assert mixed.main(['--dataset',str(tmp_path),'--run','new_mixed','--epochs','2'])==0
    assert calls[0][4]=='prepare' and calls[1]=='audit' and calls[2][4]=='run'
    assert calls[0][-2:]==['--epochs','2']
    assert str(tmp_path) in calls[0] and str(tmp_path) in calls[2]
