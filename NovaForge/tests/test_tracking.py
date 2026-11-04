from types import SimpleNamespace
import json

import pytest

from nova.tracking import Tracker, EpisodeWindow, WandBWriter, check_login
from nova.training import learn_segments


def test_continuous_training_crosses_segments_and_honors_pause(tmp_path):
    stop=tmp_path/'STOP'
    class Model:
        def __init__(self): self.calls=[];self.num_timesteps=0
        def learn(self,**kwargs):
            self.calls.append(kwargs)
            self.num_timesteps+=kwargs['total_timesteps']
            if len(self.calls)==3: stop.touch()
    model=Model(); callback=object()
    assert learn_segments(model,callback,32,True,stop)=='stopped'
    assert model.num_timesteps==96
    assert len(model.calls)==3
    assert all(c['callback'] is callback and c['reset_num_timesteps'] is False for c in model.calls)
    stop.unlink()
    once=Model()
    assert learn_segments(once,callback,32,False,stop)=='finished'
    assert len(once.calls)==1


def test_timeout_is_not_a_win_in_dashboard():
    window=EpisodeWindow()
    for outcome,opponent in [(1,'chronos'),(-1,'chronos'),(0,'nexto')]:
        window.add(dict(outcome=outcome,opponent=opponent,timeout=outcome==0,
            practice_success=outcome==1,scenario='shot',episode={'r':outcome},touches=1,
            reward_parts={'goal':10*outcome}))
    m=window.metrics()
    assert m['window/first_goal_score_fraction']==pytest.approx(1/3)
    assert m['window/timeout_fraction']==pytest.approx(1/3)
    assert m['opponents/chronos/first_goal_score_fraction']==.5
    assert m['opponents/nexto/timeout_fraction']==1
    assert m['mechanics/shot/success_fraction']==pytest.approx(1/3)


class FakeRun:
    def __init__(self,**kwargs):
        self.id=kwargs['id'];self.project=kwargs['project'];self.entity=kwargs['entity'] or 'test-user'
        self.url=f'https://wandb.example/{self.id}';self.dir='local';self.summary={};self.logs=[]
    def define_metric(self,*args,**kwargs): pass
    def log(self,metrics): self.logs.append(metrics)
    def finish(self,**kwargs): self.closed=True


def fake_sdk(monkeypatch):
    runs=[];logins=[];inits=[]
    def login(**kwargs): logins.append(kwargs);return True
    def init(**kwargs):
        inits.append(kwargs);r=FakeRun(**kwargs);runs.append(r);return r
    module=SimpleNamespace(login=login,init=init,Settings=lambda **kwargs:kwargs)
    monkeypatch.setattr('nova.tracking.sdk',lambda:module)
    return runs,logins,inits


def test_reuses_sdk_login_and_online_run_id_without_accepting_a_key(tmp_path,monkeypatch,cfg):
    runs,logins,inits=fake_sdk(monkeypatch)
    first=Tracker(tmp_path,cfg,mode='online',continuous=True)
    first.log({'train/loss':.3,'bad':float('nan')},64)
    first.finish('stopped')
    second=Tracker(tmp_path,cfg,mode=None,continuous=True)
    assert inits[0]['id']==inits[1]['id']
    assert all(i['resume']=='allow' for i in inits)
    assert logins==[dict(prompt=False,verify=True)]*2
    assert 'key' not in inits[0] and 'key' not in logins[0]
    assert runs[0].logs==[{'train/loss':.3,'trainer/timesteps':64}]
    assert json.loads((tmp_path/'wandb_status.json').read_text())['url']==second.url
    second.finish('stopped')
    Tracker(tmp_path,cfg,mode='off')
    disabled=Tracker(tmp_path,cfg,mode=None)
    assert disabled.mode=='off' and len(inits)==2
    assert json.loads((tmp_path/'wandb_status.json').read_text())['id']==first.id


def test_log_failure_keeps_training_status_visible(tmp_path,monkeypatch,cfg):
    runs,_,_=fake_sdk(monkeypatch)
    tracker=Tracker(tmp_path,cfg,mode='offline')
    def fail(_): raise OSError('connection failure')
    runs[0].log=fail
    tracker.log({'train/loss':1},100)
    assert tracker.status()['state']=='logging_error'
    assert tracker.status()['error']=='OSError'
    tracker.finish('stopped')


def test_unavailable_login_fails_without_prompting_for_a_key(monkeypatch):
    calls=[]
    def login(**kwargs): calls.append(kwargs);return False
    monkeypatch.setattr('nova.tracking.sdk',lambda:SimpleNamespace(login=login))
    with pytest.raises(RuntimeError,match='no usable saved login'): check_login()
    assert calls==[dict(prompt=False,verify=True)]
