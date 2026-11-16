import importlib.util,sys
from pathlib import Path
import pytest

def entry():
    p=Path(__file__).resolve().parents[1]/'tools/contact_curriculum.py'
    spec=importlib.util.spec_from_file_location('stage_entry',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

@pytest.mark.parametrize('command',['watch','evaluate'])
def test_exact_possession_dispatch_bypasses_simple_run_name_parser(tmp_path,monkeypatch,command):
    from duelforge import acquisition_experiment,watch,evaluate
    m=entry();monkeypatch.setattr(m,'ROOT',tmp_path)
    f=tmp_path/'runs/contact01/02_possession';f.mkdir(parents=True);(f/'latest.pt').write_bytes(b'preserved')
    def forbidden(*args,**kw):raise AssertionError('Must not substitute the active trajectory')
    monkeypatch.setattr(acquisition_experiment,'active',forbidden)
    calls=[]
    def target(folder,**kw):calls.append((folder,kw))
    monkeypatch.setattr(watch,'watch',target);monkeypatch.setattr(evaluate,'evaluate',target)
    monkeypatch.setattr(sys,'argv',['contact_curriculum.py',command,'--stage','possession','--games','200','--seconds','100'])
    m.main();assert calls[0][0]==f and calls[0][1]['seconds']==100
    if command=='evaluate':assert calls[0][1]['contexts']==['match'] and calls[0][1]['games_per_context']==200
    assert (f/'latest.pt').read_bytes()==b'preserved'

def test_missing_stage_is_not_replaced_by_active_stage(tmp_path,monkeypatch):
    m=entry();monkeypatch.setattr(m,'ROOT',tmp_path)
    with pytest.raises(FileNotFoundError):m.stage_target(None,'possession')
