from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
from filelock import FileLock


def setup(tmp_path,monkeypatch):
    from nova import triad,viewer,teachers,environment
    import rlgym.rocket_league.rlviser as adapter
    root=tmp_path/'novaforge';root.mkdir();entry=tmp_path/'triadbot';entry.mkdir();monkeypatch.chdir(entry)
    monkeypatch.setattr(triad,'ROOT',root)
    monkeypatch.setattr(teachers,'fetch_teachers',lambda *a:None)
    events=[]
    monkeypatch.setattr(viewer,'prepare_viewer',lambda **kw:events.append(('prepare',Path.cwd())))
    from nova.training import load_config
    cfg=load_config();cfg['env'].update(episode_seconds=2,no_touch_seconds=3)
    monkeypatch.setattr('nova.training.load_config',lambda *a:cfg)
    original=environment.ArenaEnv
    monkeypatch.setattr(environment,'ArenaEnv',lambda *a,**kw:original(cfg,opponent='scorer',scenario='kickoff'))
    class Policy:
        def __init__(self):self.clock=NS(selector=NS(status=lambda:{}))
        def reset(self,*a):pass
        def controls_for_ticks(self,*a):return np.zeros((4,8),np.float32)
    monkeypatch.setattr(triad,'TriadPolicy',Policy)
    class Renderer:
        def __init__(self,**kw):events.append(('renderer',Path.cwd()))
        def render(self,state,info):events.append(('frame',Path.cwd()));raise KeyboardInterrupt()
        def close(self):events.append(('closed',Path.cwd()))
    monkeypatch.setattr(adapter,'RLViserRenderer',Renderer)
    return triad,root,entry,events


def test_random_watch_uses_prepared_viewer_directory_and_restores_launch_directory(tmp_path,monkeypatch):
    triad,root,entry,events=setup(tmp_path,monkeypatch)
    triad.watch()
    assert [n for n,p in events]==['prepare','renderer','frame','closed']
    assert all(p==root for n,p in events) and Path.cwd()==entry


def test_selector_watch_resolves_relative_model_before_changing_directory(tmp_path,monkeypatch):
    triad,root,entry,events=setup(tmp_path,monkeypatch)
    from nova.core import write_model_meta
    from nova.triad_selector import CONTRACT
    path=entry/'runs/selector01/latest.pt';path.parent.mkdir(parents=True);path.write_bytes(b'fixture')
    write_model_meta(path,contract=CONTRACT,timesteps=512,hitbox='breakout')
    seen=[]
    def clock(selector_path,body):
        seen.append((selector_path,Path.cwd()))
        return NS(selector=NS(status=lambda:{}))
    monkeypatch.setattr(triad,'TriadClock',clock)
    triad.watch('runs/selector01/latest.pt')
    assert seen==[(path.resolve(),root)] and Path.cwd()==entry


def test_watch_setup_failure_restores_directory_and_busy_session_explains_recovery(tmp_path,monkeypatch):
    triad,root,entry,events=setup(tmp_path,monkeypatch)
    lock=root/'work/rlviser-watch.lock';lock.parent.mkdir()
    with FileLock(str(lock)):
        with pytest.raises(RuntimeError,match='already running'):triad.watch()
    assert Path.cwd()==entry
    from nova import viewer
    def fail(**kw):raise RuntimeError('setup failed')
    monkeypatch.setattr(viewer,'prepare_viewer',fail)
    with pytest.raises(RuntimeError,match='setup failed'):triad.watch()
    assert Path.cwd()==entry
