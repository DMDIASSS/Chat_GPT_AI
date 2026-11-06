import json
from types import SimpleNamespace as NS
import pytest
from filelock import FileLock,Timeout
from nova import autopilot as a


def test_maintenance_exports_only_a_new_champion_and_reports_failures(tmp_path,monkeypatch):
    import nova.triad as triad
    import nova.triad_selector as selector
    import nova.research as research
    calls=[];meta={'sha256':'one','timesteps':1024}
    monkeypatch.setattr(selector,'selector_meta',lambda *args:dict(meta))
    monkeypatch.setattr(research,'report_locked',lambda run:run/'report.zip')
    def export(**kw):
        folder=tmp_path/f'export{len(calls)}';folder.mkdir();(folder/'bot.bot.toml').write_text('config');calls.append(kw);return folder
    monkeypatch.setattr(triad,'export',export)
    a.maintenance(tmp_path);a.maintenance(tmp_path);assert len(calls)==1
    meta['sha256']='two';result=a.maintenance(tmp_path)
    assert len(calls)==2 and result['champion_export']['sha256']=='two'
    def fail(*args,**kw):raise OSError('disk unavailable')
    monkeypatch.setattr(research,'report_locked',fail)
    result=a.maintenance(tmp_path);assert result['artifact_errors']==['report: disk unavailable']
    assert result['champion_export']['sha256']=='two'


def test_unattended_entry_keeps_disabled_preference_and_uses_single_training_session(tmp_path,monkeypatch):
    import nova.triad_selector as selector
    import nova.research as research
    import nova.opponent_sampling as sampling
    monkeypatch.setattr(selector,'RUNS',tmp_path)
    run=tmp_path/'selector06';run.mkdir();(run/'full.zip').write_bytes(b'checkpoint')
    (run/'config.json').write_text(json.dumps({'selector_experts':list(selector.SIX_NAMES)}))
    (run/'opponent_sampling_policy.json').write_text('{"enabled":false}')
    calls=[]
    monkeypatch.setattr(selector,'selector_meta',lambda *args:{})
    monkeypatch.setattr(research,'backup',lambda name:calls.append(('backup',name)))
    monkeypatch.setattr(sampling,'configure',lambda *args:pytest.fail('Explicit disabled policy must be retained'))
    monkeypatch.setattr(selector,'train',lambda name,**kw:calls.append(('train',name,kw)))
    a.run(once=True,steps=512,wandb='off')
    assert calls[0][0]=='backup' and calls[1][2]==dict(steps=512,forever=False,wandb='off',autopilot=True,clear_stop=False)
    assert (run/'full.zip').read_bytes()==b'checkpoint'
    with FileLock(str(run/'autopilot.lock')):
        with pytest.raises(Timeout):a.run(once=True)
